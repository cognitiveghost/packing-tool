"""
Profile Manager - Handles client profiles and centralized network storage.

This module manages client-specific configurations, SKU mappings, and session
directories on a centralized file server. It provides robust file locking for
concurrent access, caching for performance, and connection testing.
"""
import os
import json
import re
import shutil
import time
import configparser
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from shared.file_lock import locked_file, FileLockError, WINDOWS_LOCKING_AVAILABLE
from shared.server_connection import resolve_server_path, test_path_reachable
from logger import get_logger

logger = get_logger(__name__)


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
        self._config_cache: Dict[str, Tuple[Dict, datetime]] = {}
        self._sku_cache: Dict[str, Tuple[Dict, datetime]] = {}

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

        logger.info(f"ProfileManager initialized successfully")
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
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

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
            logger.error(f"Cannot create directories: {e}")
            raise ProfileManagerError(f"Cannot create directories on file server: {e}")

    # ========================================================================
    # CLIENT VALIDATION
    # ========================================================================

    @staticmethod
    def validate_client_id(client_id: str) -> Tuple[bool, str]:
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

    def get_available_clients(self) -> List[str]:
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

        except Exception as e:
            logger.error(f"Error listing clients: {e}")
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
                "created_at": datetime.now().isoformat(),
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
                "last_updated": datetime.now().isoformat(),
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
                "created_at": datetime.now().isoformat()
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
            logger.error(f"Failed to create client profile: {e}", exc_info=True)
            # Cleanup on failure
            if client_dir.exists():
                shutil.rmtree(client_dir, ignore_errors=True)
            raise ProfileManagerError(f"Failed to create client profile: {e}")

    def load_client_config(self, client_id: str) -> Optional[Dict]:
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
            age_seconds = (datetime.now() - cached_time).total_seconds()

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
            self._config_cache[cache_key] = (config, datetime.now())

            logger.debug(f"Loaded config for client {client_id} from {path_to_use.name}")
            return config.copy()

        except Exception as e:
            logger.error(f"Error loading config for {client_id}: {e}")
            return None

    def save_client_config(self, client_id: str, config: Dict) -> bool:
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
            config['last_updated'] = datetime.now().isoformat()
            config['updated_by'] = os.environ.get('COMPUTERNAME', 'Unknown')

            # Save new config
            with open(packer_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # Invalidate cache
            cache_key = f"config_{client_id}"
            self._config_cache.pop(cache_key, None)

            logger.info(f"Saved packer_config for client {client_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving config for {client_id}: {e}")
            return False

    def _create_backup(self, client_id: str, file_path: Path, file_type: str):
        """Create timestamped backup of a file."""
        backup_dir = self.clients_dir / f"CLIENT_{client_id}" / "backups"
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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

    def load_sku_mapping(self, client_id: str) -> Dict[str, str]:
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
            age_seconds = (datetime.now() - cached_time).total_seconds()

            if age_seconds < self.CACHE_TIMEOUT_SECONDS:
                logger.debug(f"Using cached SKU mapping for {client_id}")
                return cached_data.copy()

        # Load from packer_config.json first, fall back to sku_mapping.json
        packer_config_path = self.clients_dir / f"CLIENT_{client_id}" / "packer_config.json"
        mapping_path = self.clients_dir / f"CLIENT_{client_id}" / "sku_mapping.json"

        mappings = {}

        # Try packer_config.json first
        if packer_config_path.exists():
            try:
                with open(packer_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    mappings = data.get("sku_mapping", {})
                logger.debug(f"Loaded {len(mappings)} SKU mappings from packer_config for {client_id}")
            except Exception as e:
                logger.error(f"Error loading SKU mapping from packer_config for {client_id}: {e}")

        # Fall back to old sku_mapping.json if packer_config doesn't have mappings
        if not mappings and mapping_path.exists():
            try:
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    mappings = data.get("mappings", {})
                logger.debug(f"Loaded {len(mappings)} SKU mappings from sku_mapping.json for {client_id}")
            except Exception as e:
                logger.error(f"Error loading SKU mapping from sku_mapping.json for {client_id}: {e}")

        # Update cache
        self._sku_cache[cache_key] = (mappings, datetime.now())

        return mappings.copy()

    def save_sku_mapping(self, client_id: str, mappings: Dict[str, str]) -> bool:
        """
        Save SKU mapping to packer_config.json with file locking and merge support.

        This method uses Windows file locking to prevent concurrent write conflicts.
        It reads the current packer_config, merges with new SKU mappings, and writes atomically.

        Args:
            client_id: Client identifier
            mappings: Dictionary mapping barcode to SKU

        Returns:
            True if saved successfully

        Raises:
            ProfileManagerError: If save fails after retries
        """
        packer_config_path = self.clients_dir / f"CLIENT_{client_id}" / "packer_config.json"

        logger.info(f"Saving SKU mapping for client {client_id}: {len(mappings)} entries")

        if not WINDOWS_LOCKING_AVAILABLE:
            logger.warning("Windows file locking not available, using basic save")
            return self._save_sku_mapping_simple(client_id, mappings)

        max_retries = 5
        retry_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                # Create packer_config if doesn't exist
                if not packer_config_path.exists():
                    packer_config_path.parent.mkdir(parents=True, exist_ok=True)
                    default_config = {
                        "client_id": client_id,
                        "sku_mapping": {},
                        "last_updated": "",
                        "updated_by": ""
                    }
                    with open(packer_config_path, 'w', encoding='utf-8') as f:
                        json.dump(default_config, f)

                with open(packer_config_path, 'r+', encoding='utf-8') as f:
                    with locked_file(f):
                        # Read current data
                        f.seek(0)
                        current_data = json.load(f)

                        # Replace (not merge): callers pass the full desired mapping,
                        # so a deleted entry must not survive by merging onto disk.
                        current_data['sku_mapping'] = mappings
                        current_data['last_updated'] = datetime.now().isoformat()
                        current_data['updated_by'] = os.environ.get('COMPUTERNAME', 'Unknown')

                        # Write back (truncate and write)
                        f.seek(0)
                        f.truncate()
                        json.dump(current_data, f, indent=2, ensure_ascii=False)

                        logger.info(f"Successfully saved SKU mapping to packer_config for {client_id}")

                # Invalidate caches
                cache_key = f"sku_{client_id}"
                self._sku_cache.pop(cache_key, None)
                config_cache_key = f"config_{client_id}"
                self._config_cache.pop(config_cache_key, None)

                return True

            except (IOError, FileLockError) as e:
                # File is locked by another process
                if attempt < max_retries - 1:
                    logger.warning(f"packer_config locked, retry {attempt + 1}/{max_retries}")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Could not acquire lock on packer_config after {max_retries} attempts")
                    raise ProfileManagerError(
                        f"Configuration is locked by another user. Please try again in a moment."
                    )

            except Exception as e:
                logger.error(f"Error saving SKU mapping: {e}", exc_info=True)
                raise ProfileManagerError(f"Failed to save SKU mapping: {e}")

        return False

    def _save_sku_mapping_simple(self, client_id: str, mappings: Dict[str, str]) -> bool:
        """
        Simple save without file locking (fallback).
        Saves to packer_config.json

        Args:
            client_id: Client identifier
            mappings: Dictionary mapping barcode to SKU

        Returns:
            True if saved successfully
        """
        packer_config_path = self.clients_dir / f"CLIENT_{client_id}" / "packer_config.json"

        try:
            # Create backup
            if packer_config_path.exists():
                self._create_backup(client_id, packer_config_path, "packer_config")

            # Load current config and merge mappings
            current_config = {}
            if packer_config_path.exists():
                with open(packer_config_path, 'r', encoding='utf-8') as f:
                    current_config = json.load(f)

            # Replace (not merge): callers pass the full desired mapping, so a
            # deleted entry must not survive by merging onto disk.
            current_config['sku_mapping'] = mappings
            current_config['last_updated'] = datetime.now().isoformat()
            current_config['updated_by'] = os.environ.get('COMPUTERNAME', 'Unknown')

            # Save
            with open(packer_config_path, 'w', encoding='utf-8') as f:
                json.dump(current_config, f, indent=2, ensure_ascii=False)

            # Invalidate caches
            cache_key = f"sku_{client_id}"
            self._sku_cache.pop(cache_key, None)
            config_cache_key = f"config_{client_id}"
            self._config_cache.pop(config_cache_key, None)

            logger.info(f"Saved SKU mapping to packer_config for {client_id} (simple mode)")
            return True

        except Exception as e:
            logger.error(f"Error saving SKU mapping (simple): {e}")
            return False

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def get_session_dir(self, client_id: str, session_name: Optional[str] = None) -> Path:
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
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return client_sessions / timestamp

    def get_incomplete_sessions(self, client_id: str) -> List[Path]:
        """
        Get list of incomplete sessions for a client.

        A session is incomplete if it has a session_info.json file
        (which is removed when the session ends gracefully).

        Args:
            client_id: Client identifier

        Returns:
            List of Path objects for incomplete session directories
        """
        client_sessions_dir = self.sessions_dir / f"CLIENT_{client_id}"

        if not client_sessions_dir.exists():
            logger.debug(f"No sessions directory for client {client_id}")
            return []

        incomplete_sessions = []

        try:
            for session_dir in client_sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                # Check if session has session_info.json (incomplete session marker)
                session_info_path = session_dir / "session_info.json"
                if session_info_path.exists():
                    incomplete_sessions.append(session_dir)

            # Sort by modification time (newest first)
            incomplete_sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            logger.debug(f"Found {len(incomplete_sessions)} incomplete sessions for client {client_id}")
            return incomplete_sessions

        except Exception as e:
            logger.error(f"Error getting incomplete sessions for {client_id}: {e}", exc_info=True)
            return []

    def list_clients(self) -> List[str]:
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

        except Exception as e:
            logger.error(f"Error listing clients: {e}", exc_info=True)
            return []

    def get_sessions_root(self) -> Path:
        """
        Get the root directory for all sessions.

        Returns:
            Path to SESSIONS directory on file server
        """
        return self.sessions_dir

