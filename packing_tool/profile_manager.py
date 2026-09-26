"""
Profile Manager - Handles client profiles and centralized network storage.

This module manages client-specific configurations, SKU mappings, and session
directories on a centralized file server. It provides robust file locking for
concurrent access, caching for performance, and connection testing.
"""
import configparser
import json
import logging
import os
import re
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from shared.atomic_write import atomic_write_json
from shared.file_lock import FileLockError, locked_file
from shared.logger import setup_logging
from shared.server_connection import resolve_server_path, test_path_reachable

logger = logging.getLogger(__name__)


class ProfileManagerError(Exception):
    """Base exception for ProfileManager errors."""


class NetworkError(ProfileManagerError):
    """Raised when file server is not accessible."""


class ValidationError(ProfileManagerError):
    """Raised when validation fails."""


class ProfileManager:
    """
    Manages client profiles and centralized configuration.

    This class handles:
    - Client profile creation and management
    - SKU mapping with file locking for concurrent access
    - Session directory organization
    - Connection testing and caching
    - Validation of client IDs and data

    Attributes:
        base_path (Path): Root path on file server
        clients_dir (Path): Directory containing client profiles
        sessions_dir (Path): Directory containing session data
        cache_dir (Path): Local cache directory
        connection_timeout (int): Network connection timeout in seconds
        is_network_available (bool): Current network connectivity status
    """

    CACHE_TIMEOUT_SECONDS = 60  # Cache valid for 1 minute

    def __init__(self, config_path: str = "config.ini"):
        """
        Initialize ProfileManager with configuration.

        Args:
            config_path: Path to config.ini file

        Raises:
            ProfileManagerError: If configuration is invalid or inaccessible
        """
        logger.info("Initializing ProfileManager...")

        # Cache for loaded configurations (client_id -> (data, timestamp)).
        # Per-instance (not class-level) so two managers pointed at different
        # base_path/file servers never share each other's cached data.
        self._config_cache: dict[str, tuple[dict, datetime]] = {}
        self._sku_cache: dict[str, tuple[dict, datetime]] = {}

        # Load configuration
        self.config = self._load_config(config_path)

        # Get paths from config — resolve_server_path checks, in order:
        # FULFILLMENT_SERVER_PATH env var (same variable, same precedence
        # shopify-fulfillment-tool's ProfileManager already uses, so both
        # apps can be pointed at the same file server from one place), then
        # a path saved via the Server Connection UI, then config.ini.
        config_fallback = self.config.get('Network', 'FileServerPath', fallback=None)
        file_server_path = resolve_server_path(
            "PackingTool", "FULFILLMENT_SERVER_PATH", config_fallback
        )
        if not file_server_path:
            raise ProfileManagerError(
                "FileServerPath not configured: set FULFILLMENT_SERVER_PATH, "
                "use Settings → Server Connection, or add FileServerPath to config.ini"
            )

        self.base_path = Path(file_server_path)
        self.clients_dir = self.base_path / "Clients"
        self.sessions_dir = self.base_path / "Sessions"
        self.workers_dir = self.base_path / "Workers"
        self.stats_dir = self.base_path / "Stats"
        self.logs_dir = self.base_path / "Logs"

        # Per-process log file on the same server ProfileManager itself
        # resolved (base_path) - previously logger.py re-read config.ini
        # independently, so a saved Server Connection path or
        # FULFILLMENT_SERVER_PATH override could silently point data at
        # one server and logs at another.
        log_level_str = self.config.get('Logging', 'LogLevel', fallback='INFO')
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
        retention_days = self.config.getint('Logging', 'LogRetentionDays', fallback=30)
        setup_logging("PackingTool", str(self.base_path), level=log_level, retention_days=retention_days)

        # Local cache directory
        cache_path = self.config.get('Network', 'LocalCachePath', fallback='')
        if cache_path:
            self.cache_dir = Path(cache_path)
        else:
            self.cache_dir = Path(os.path.expanduser("~")) / ".packers_assistant" / "cache"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Connection timeout
        self.connection_timeout = self.config.getint('Network', 'ConnectionTimeout', fallback=5)

        # Test network connectivity
        self.is_network_available = test_path_reachable(
            str(self.base_path), self.connection_timeout
        )

        if not self.is_network_available:
            logger.error(f"File server not accessible: {self.base_path}")
            raise NetworkError(
                f"Cannot connect to file server at {self.base_path}\n\n"
                f"Please check:\n"
                f"1. Network connection\n"
                f"2. File server is online\n"
                f"3. Path is correct in config.ini"
            )

        # Ensure directory structure exists
        self._ensure_directories()

        logger.info("ProfileManager initialized successfully")
        logger.info(f"Base path: {self.base_path}")
        logger.info(f"Cache dir: {self.cache_dir}")

    @staticmethod
    def _load_config(config_path: str) -> configparser.ConfigParser:
        """Load configuration from config.ini."""
        config = configparser.ConfigParser()

        if not Path(config_path).exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return config

        try:
            config.read(config_path, encoding='utf-8')
            logger.info(f"Configuration loaded from {config_path}")
        except Exception:
            logger.exception("Failed to load config")

        return config

    def _ensure_directories(self):
        """Create base directory structure if it doesn't exist."""
        try:
            self.clients_dir.mkdir(parents=True, exist_ok=True)
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            self.workers_dir.mkdir(parents=True, exist_ok=True)
            self.stats_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Directory structure verified")
        except Exception as e:
            logger.exception("Cannot create directories")
            raise ProfileManagerError(f"Cannot create directories on file server: {e}")

    # ========================================================================
    # CLIENT VALIDATION
    # ========================================================================

    @staticmethod
    def validate_client_id(client_id: str) -> tuple[bool, str]:
        """
        Validate client ID format.

        Args:
            client_id: Client ID to validate

        Returns:
            Tuple of (is_valid, error_message)

        Rules:
            - Not empty
            - Max 10 characters
            - Only alphanumeric and underscore
            - No "CLIENT_" prefix
            - Not a Windows reserved name
        """
        if not client_id:
            return False, "Client ID cannot be empty"

        if len(client_id) > 10:
            return False, "Client ID too long (max 10 characters)"

        # Only alphanumeric and underscore
        if not re.match(r'^[A-Z0-9_]+$', client_id):
            return False, "Client ID can only contain letters, numbers, and underscore"

        # Don't allow "CLIENT_" prefix
        if client_id.startswith("CLIENT_"):
            return False, "Don't include 'CLIENT_' prefix, it will be added automatically"

        # Windows reserved names
        reserved = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                    'LPT1', 'LPT2', 'LPT3', 'LPT4']
        if client_id.upper() in reserved:
            return False, f"'{client_id}' is a reserved system name"

        return True, ""

    # ========================================================================
    # CLIENT PROFILE MANAGEMENT
    # ========================================================================

    def get_available_clients(self) -> list[str]:
        """
        Get list of available client IDs.

        Returns:
            List of client IDs (without "CLIENT_" prefix)
        """
        if not self.clients_dir.exists():
            logger.warning("Clients directory does not exist")
            return []

        try:
            clients = []
            for d in self.clients_dir.iterdir():
                if d.is_dir() and d.name.startswith("CLIENT_"):
                    client_id = d.name[len("CLIENT_"):]
                    clients.append(client_id)

            logger.debug(f"Found {len(clients)} clients: {clients}")
            return sorted(clients)

        except Exception:
            logger.exception("Error listing clients")
            return []

    def client_exists(self, client_id: str) -> bool:
        """Check if client profile exists."""
        client_dir = self.clients_dir / f"CLIENT_{client_id}"
        return client_dir.exists()

    def create_client_profile(self, client_id: str, client_name: str) -> bool:
        """
        Create a new client profile with default configuration.

        Args:
            client_id: Unique client identifier (e.g., "M", "R")
            client_name: Full client name (e.g., "M Cosmetics")

        Returns:
            True if created successfully, False if already exists

        Raises:
            ValidationError: If client_id is invalid
            ProfileManagerError: If creation fails
        """
        logger.info(f"Creating client profile: {client_id} ({client_name})")

        # Validate client ID
        is_valid, error_msg = self.validate_client_id(client_id)
        if not is_valid:
            raise ValidationError(error_msg)

        client_dir = self.clients_dir / f"CLIENT_{client_id}"

        if client_dir.exists():
            logger.warning(f"Client {client_id} already exists")
            return False

        try:
            # Create client directory
            client_dir.mkdir(parents=True)
            logger.debug(f"Created client directory: {client_dir}")

            # Create default packer_config with SKU mapping integrated
            default_packer_config = {
                "client_id": client_id,
                "client_name": client_name,
                "created_at": datetime.now().astimezone().isoformat(),
                "barcode_label": {
                    "width_mm": 65,
                    "height_mm": 35,
                    "dpi": 203,
                    "show_quantity": False,
                    "show_client_name": False,
                    "font_size": 10
                },
                "courier_deadlines": {
                    "PostOne": "15:00",
                    "Speedy": "16:00",
                    "DHL": "17:00"
                },
                "required_columns": {
                    "order_number": "Order_Number",
                    "sku": "SKU",
                    "product_name": "Product_Name",
                    "quantity": "Quantity",
                    "courier": "Courier"
                },
                "sku_mapping": {},
                "barcode_settings": {
                    "auto_generate": True,
                    "format": "CODE128"
                },
                "packing_rules": {},
                "last_updated": datetime.now().astimezone().isoformat(),
                "updated_by": os.environ.get('COMPUTERNAME', 'Unknown')
            }

            packer_config_path = client_dir / "packer_config.json"
            with open(packer_config_path, 'w', encoding='utf-8') as f:
                json.dump(default_packer_config, f, indent=2, ensure_ascii=False)

            logger.debug(f"Created packer_config: {packer_config_path}")

            # Also create client_config.json for compatibility with Shopify Tool
            client_config = {
                "client_id": client_id,
                "client_name": client_name,
                "created_at": datetime.now().astimezone().isoformat()
            }

            client_config_path = client_dir / "client_config.json"
            with open(client_config_path, 'w', encoding='utf-8') as f:
                json.dump(client_config, f, indent=2, ensure_ascii=False)

            logger.debug(f"Created client_config: {client_config_path}")

            # Create backups directory
            (client_dir / "backups").mkdir(exist_ok=True)

            # Create session directory for this client
            client_sessions = self.sessions_dir / f"CLIENT_{client_id}"
            client_sessions.mkdir(exist_ok=True)

            logger.info(f"Successfully created client profile: {client_id}")
            return True

        except Exception as e:
            logger.exception("Failed to create client profile")
            # Cleanup on failure
            if client_dir.exists():
                shutil.rmtree(client_dir, ignore_errors=True)
            raise ProfileManagerError(f"Failed to create client profile: {e}")

    def load_client_config(self, client_id: str) -> dict | None:
        """
        Load packer configuration for a specific client with caching.

        Args:
            client_id: Client identifier

        Returns:
            Configuration dictionary, or None if not found
        """
        # Check cache first
        cache_key = f"config_{client_id}"
        if cache_key in self._config_cache:
            cached_data, cached_time = self._config_cache[cache_key]
            age_seconds = (datetime.now().astimezone() - cached_time).total_seconds()

            if age_seconds < self.CACHE_TIMEOUT_SECONDS:
                logger.debug(f"Using cached config for {client_id}")
                return cached_data.copy()

        # Load from disk - try packer_config.json first, then fall back to config.json
        packer_config_path = self.clients_dir / f"CLIENT_{client_id}" / "packer_config.json"
        config_path = self.clients_dir / f"CLIENT_{client_id}" / "config.json"

        path_to_use = packer_config_path if packer_config_path.exists() else config_path

        if not path_to_use.exists():
            logger.warning(f"Config not found for client {client_id}")
            return None

        try:
            with open(path_to_use, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Update cache
            self._config_cache[cache_key] = (config, datetime.now().astimezone())

            logger.debug(f"Loaded config for client {client_id} from {path_to_use.name}")
            return config.copy()

        except Exception:
            logger.exception(f"Error loading config for {client_id}")
            return None

    def save_client_config(self, client_id: str, config: dict) -> bool:
        """
        Save packer configuration for a specific client with backup.

        Args:
            client_id: Client identifier
            config: Configuration dictionary

        Returns:
            True if saved successfully
        """
        packer_config_path = self.clients_dir / f"CLIENT_{client_id}" / "packer_config.json"

        try:
            # Create backup before overwriting
            if packer_config_path.exists():
                self._create_backup(client_id, packer_config_path, "packer_config")

            # Update timestamp
            config['last_updated'] = datetime.now().astimezone().isoformat()
            config['updated_by'] = os.environ.get('COMPUTERNAME', 'Unknown')

            # Save new config
            with open(packer_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # Invalidate cache
            cache_key = f"config_{client_id}"
            self._config_cache.pop(cache_key, None)

            logger.info(f"Saved packer_config for client {client_id}")
            return True

        except Exception:
            logger.exception(f"Error saving config for {client_id}")
            return False

    def _create_backup(self, client_id: str, file_path: Path, file_type: str):
        """Create timestamped backup of a file."""
        backup_dir = self.clients_dir / f"CLIENT_{client_id}" / "backups"
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{file_type}_{timestamp}.json"

        try:
            shutil.copy2(file_path, backup_path)
            logger.debug(f"Created backup: {backup_path}")

            # Keep only last 10 backups
            backups = sorted(backup_dir.glob(f"{file_type}_*.json"))
            for old_backup in backups[:-10]:
                old_backup.unlink()
                logger.debug(f"Deleted old backup: {old_backup.name}")

        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")

    # ========================================================================
    # SKU MAPPING WITH FILE LOCKING
    # ========================================================================

    def load_sku_mapping(self, client_id: str) -> dict[str, str]:
        """
        Load SKU mapping for a specific client with caching.
        Now reads from packer_config.json instead of separate sku_mapping.json

        Args:
            client_id: Client identifier

        Returns:
            Dictionary mapping barcode to SKU
        """
        # Check cache
        cache_key = f"sku_{client_id}"
        if cache_key in self._sku_cache:
            cached_data, cached_time = self._sku_cache[cache_key]
            age_seconds = (datetime.now().astimezone() - cached_time).total_seconds()

            if age_seconds < self.CACHE_TIMEOUT_SECONDS:
                logger.debug(f"Using cached SKU mapping for {client_id}")
                return cached_data.copy()

        # Load from packer_config.json first, fall back to sku_mapping.json
        packer_config_path = self.clients_dir / f"CLIENT_{client_id}" / "packer_config.json"
        mapping_path = self.clients_dir / f"CLIENT_{client_id}" / "sku_mapping.json"

        mappings = {}
        failed = False

        # Try packer_config.json first
        if packer_config_path.exists():
            try:
                with open(packer_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    mappings = data.get("sku_mapping", {})
                logger.debug(f"Loaded {len(mappings)} SKU mappings from packer_config for {client_id}")
            except Exception:
                failed = True
                logger.exception(f"Error loading SKU mapping from packer_config for {client_id}")

        # Fall back to old sku_mapping.json if packer_config doesn't have mappings
        if not mappings and mapping_path.exists():
            try:
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    mappings = data.get("mappings", {})
                logger.debug(f"Loaded {len(mappings)} SKU mappings from sku_mapping.json for {client_id}")
            except Exception:
                logger.exception(f"Error loading SKU mapping from sku_mapping.json for {client_id}")

        # A failed read is not cached: the next read tries the file again
        if not failed:
            self._sku_cache[cache_key] = (mappings, datetime.now().astimezone())

        return mappings.copy()

    @contextmanager
    def _packer_config_locked(self, client_id: str):
        """Hold packer_config.json's sidecar lock for one read-modify-write.

        A sidecar, as the session registry does: the file itself is replaced by
        rename, so no reader ever sees it half-written (AUDIT-02-3).
        """
        path = self.clients_dir / f"CLIENT_{client_id}" / "packer_config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_name(path.name + ".lock"), "a+") as handle, locked_file(handle):
            yield path

    def _change_sku_mapping(self, client_id: str, change) -> dict[str, str]:
        """Apply change(mapping) to the mapping as it is on disk now, under the lock.

        An unreadable packer_config.json raises: a mapping read as empty must
        never be saved over the real one.
        """
        try:
            with self._packer_config_locked(client_id) as path:
                config = {"client_id": client_id, "sku_mapping": {}}
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                mapping = dict(config.get("sku_mapping") or {})
                legacy = path.with_name("sku_mapping.json")
                if not mapping and legacy.exists():
                    with open(legacy, "r", encoding="utf-8") as f:
                        mapping = dict(json.load(f).get("mappings", {}))
                change(mapping)
                config["sku_mapping"] = mapping
                config["last_updated"] = datetime.now().astimezone().isoformat()
                config["updated_by"] = os.environ.get("COMPUTERNAME", "Unknown")
                atomic_write_json(path, config, indent=2, ensure_ascii=False)
        except (OSError, ValueError, FileLockError) as e:
            logger.exception(f"Could not save SKU mapping for {client_id}")
            raise ProfileManagerError(
                f"Could not save the SKU mapping to the file server: {e}"
            ) from e
        finally:
            self._sku_cache.pop(f"sku_{client_id}", None)
            self._config_cache.pop(f"config_{client_id}", None)
        logger.info(f"Saved SKU mapping for {client_id}: {len(mapping)} entries")
        return mapping

    def save_sku_mapping(self, client_id: str, mappings: dict[str, str]) -> bool:
        """Replace the whole SKU mapping. Raises ProfileManagerError on failure.

        For a caller that owns the full table. One PC's edits go through
        update_sku_mapping(), which cannot erase another PC's.
        """
        def replace(mapping):
            mapping.clear()
            mapping.update(mappings)

        self._change_sku_mapping(client_id, replace)
        return True

    def update_sku_mapping(
        self, client_id: str, add: dict[str, str] | None = None, remove=()
    ) -> dict[str, str]:
        """Apply one PC's edits to the mapping on disk now; return the whole mapping.

        Built from a cached or minutes-old copy, a full replace erased what other
        PCs had mapped meanwhile (AUDIT-02-3).
        """
        def edit(mapping):
            for barcode in remove:
                mapping.pop(barcode, None)
            mapping.update(add or {})

        return self._change_sku_mapping(client_id, edit)

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def get_session_dir(self, client_id: str, session_name: str | None = None) -> Path:
        """
        Get session directory path for a client.

        Args:
            client_id: Client identifier
            session_name: Optional session name. If None, generates new timestamped name

        Returns:
            Path to session directory
        """
        client_sessions = self.sessions_dir / f"CLIENT_{client_id}"
        client_sessions.mkdir(exist_ok=True)

        if session_name:
            return client_sessions / session_name

        # Generate new session name with timestamp
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M")
        return client_sessions / timestamp

    def list_clients(self) -> list[str]:
        """
        Get list of all client IDs.

        Returns:
            List of client identifiers (without CLIENT_ prefix)
        """
        try:
            if not self.clients_dir.exists():
                logger.warning(f"Clients directory does not exist: {self.clients_dir}")
                return []

            clients = []
            for client_dir in self.clients_dir.iterdir():
                if not client_dir.is_dir():
                    continue

                # Extract client ID from CLIENT_X format
                dir_name = client_dir.name
                if dir_name.startswith("CLIENT_"):
                    client_id = dir_name[7:]  # Remove "CLIENT_" prefix
                    clients.append(client_id)

            logger.debug(f"Found {len(clients)} clients")
            return sorted(clients)

        except Exception:
            logger.exception("Error listing clients")
            return []

    def get_sessions_root(self) -> Path:
        """
        Get the root directory for all sessions.

        Returns:
            Path to SESSIONS directory on file server
        """
        return self.sessions_dir

