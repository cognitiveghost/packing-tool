# Standard library imports
import os
import tempfile
import shutil

# Third-party imports for data processing
import pandas as pd  # Excel file handling and data manipulation

# Data persistence and utilities
import json
from pathlib import Path
from datetime import datetime

# Qt framework for signals/slots pattern
from PySide6.QtCore import QObject, Signal

# Type hints for better code documentation
from typing import List, Dict, Any, Tuple

# Local imports
from logger import get_logger
from json_cache import get_cached_json, invalidate_json_cache
from async_state_writer import AsyncStateWriter

# Initialize module-level logger
logger = get_logger(__name__)

# Required columns in the Excel packing list
# These columns are mandatory for the application to function correctly
# - Order_Number: Unique identifier for each order
# - SKU: Product stock keeping unit code
# - Product_Name: Human-readable product description
# - Quantity: Number of items to pack for this SKU in this order
# - Courier: Shipping courier name (e.g., "PostOne", "Speedy", "DHL")
REQUIRED_COLUMNS = ['Order_Number', 'SKU', 'Product_Name', 'Quantity', 'Courier']

# Filename for session state persistence
# This file stores packing progress and is saved after every scan
# to enable crash recovery and session restoration
STATE_FILE_NAME = "packing_state.json"

# Filename for session summary (created upon completion)
# This file contains aggregated statistics and performance metrics
# for the completed packing session
SUMMARY_FILE_NAME = "session_summary.json"

class PackerLogic(QObject):
    """
    Handles the core business logic of the Packer's Assistant application.

    This class is responsible for loading and processing packing lists,
    generating barcodes, managing the state of the packing process (what has
    been packed), and handling the logic for scanning items. It operates
    independently of the UI, communicating changes via Qt signals.

    Attributes:
        item_packed (Signal): A signal emitted when an item is packed, providing
                              real-time progress updates.
        client_id (str): Client identifier for this session
        profile_manager (ProfileManager): Manager for client profiles and SKU mappings
        work_dir (Path): Work directory for this packing list
                        (e.g., Sessions/CLIENT_M/2025-11-10_1/packing/DHL_Orders/)
        barcode_dir (Path): Subdirectory for generated barcodes (work_dir/barcodes/)
        reports_dir (Path): Subdirectory for packing reports (work_dir/reports/)
        packing_list_df (pd.DataFrame): The original, unprocessed DataFrame
                                        loaded from the Excel file.
        processed_df (pd.DataFrame): The DataFrame after column mapping and
                                     validation.
        orders_data (Dict): A dictionary containing details for each order,
                            including its barcode path and item list.
        current_order_number (str | None): The order number currently being packed.
        current_order_state (Dict): The detailed packing state for the current
                                    order (required vs. packed counts for each SKU).
        session_packing_state (Dict): The packing state for the entire session,
                                      including in-progress and completed orders.
        sku_map (Dict[str, str]): Normalized barcode-to-SKU mapping
    """
    item_packed = Signal(str, int, int)  # order_number, packed_count, required_count
    all_orders_complete = Signal()  # Emitted when every order in the session is packed

    def __init__(self, client_id: str, profile_manager, work_dir: str):
        """
        Initialize PackerLogic instance for a specific client.

        Args:
            client_id: Client identifier (e.g., "M", "R")
            profile_manager: ProfileManager instance for loading/saving SKU mappings
            work_dir: Work directory for this packing list
                     (e.g., Sessions/CLIENT_M/2025-11-10_1/packing/DHL_Orders/)
                     For legacy Excel workflow, this will be the barcodes directory
        """
        super().__init__()

        self.client_id = client_id
        self.profile_manager = profile_manager
        self.work_dir = Path(work_dir)

        # Create subdirectories
        # work_dir is packing/{list_name}/ (from Shopify session)
        # Barcode directory exists in session root (created by Shopify Tool)
        self.barcode_dir = self.work_dir.parent.parent / "barcodes"  # ../../../barcodes
        self.reports_dir = self.work_dir / "reports"

        # Ensure reports directory exists (barcodes dir created by Shopify Tool)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.packing_list_df = None
        self.processed_df = None
        self.orders_data = {}
        self._normalized_order_lookup: Dict[str, str] = {}
        self._total_items: int = 0
        self.current_order_number = None
        self.current_order_state = {}

        # Session metadata (for new state structure)
        self.session_id = None  # Will be set when loading packing list
        self.packing_list_name = None  # Name of the packing list being packed
        self.started_at = None  # Session start timestamp
        self.worker_pc = os.environ.get('COMPUTERNAME', 'Unknown')  # PC name

        # Initialize session packing state with new structure
        # This will be populated when loading an existing state or starting new
        self.session_packing_state = {
            'in_progress': {},
            'completed_orders': [],
            'skipped_orders': [],
            'skipped_orders_timing': {},  # order_num -> ISO timestamp of skip
        }

        # Phase 2b: Order-level timing tracking — initialized BEFORE _load_session_state()
        # so that _load_session_state() can populate them from disk without being overwritten.
        self.current_order_start_time = None  # ISO timestamp when order scanning started
        self.current_order_items_scanned = []  # List of items with scan timestamps
        self.completed_orders_metadata = []  # List of completed orders with timing data

        # Per-order counters for 1.7 metrics — reset by start_order_packing()
        self.current_order_corrections: int = 0           # cancel_item_scan() events
        self.current_order_extra_scan_count: int = 0      # SKU_EXTRA events
        self.current_order_unknown_scan_count: int = 0    # SKU_NOT_FOUND events

        # Load SKU mapping from ProfileManager
        self.sku_map = self._load_sku_mapping()

        # Load session state if exists (must come AFTER Phase 2b vars are declared)
        self._load_session_state()

        # Extra items tracking: normalized_sku → extra count (scanned beyond required)
        self.current_extra_items: Dict[str, int] = {}

        # Unknown/incorrect scan tracking: raw barcodes that didn't match any SKU
        self.unknown_scans: List[str] = []

        # Write-behind queue: state writes happen in background to avoid UI freezes.
        # sync_mode=True is used in tests to keep writes synchronous.
        self._state_writer = AsyncStateWriter(self._do_atomic_write)

        logger.info(f"PackerLogic initialized for client {client_id}")
        logger.debug(f"Work directory: {self.work_dir}")
        logger.debug(f"Barcode directory: {self.barcode_dir}")
        logger.debug(f"Reports directory: {self.reports_dir}")
        logger.debug(f"Loaded {len(self.sku_map)} SKU mappings")
        logger.debug("Phase 2b timing variables initialized (loaded from state if available)")

    def _load_sku_mapping(self) -> Dict[str, str]:
        """
        Load SKU mapping from ProfileManager for the current client.

        SKU mappings allow barcodes from products to be translated to internal SKU codes.
        This is useful when:
        - Products have multiple barcode standards (EAN-13, UPC, manufacturer codes)
        - Supplier barcodes differ from internal SKU system
        - Same product has different barcodes from different suppliers

        For small warehouses, this is critical because products often come from
        multiple suppliers with different barcode systems, but need to be tracked
        under a single internal SKU.

        The method normalizes all barcode keys (lowercase, alphanumeric only) to ensure
        consistent matching regardless of scanner input variations.

        Returns:
            Dictionary of normalized barcode -> SKU mappings
            Example: {"7290018664100": "SKU-CREAM-01", "8809765431234": "SKU-SERUM-02"}
            Returns empty dict if loading fails (graceful degradation)
        """
        try:
            # Load raw mappings from centralized storage (file server)
            mappings = self.profile_manager.load_sku_mapping(self.client_id)

            # Normalize all barcode keys for consistent matching
            # This handles variations in scanner output (spaces, dashes, mixed case)
            # Original SKU values are preserved as-is
            normalized = {self._normalize_sku(k): v for k, v in mappings.items()}

            logger.debug(f"Loaded {len(normalized)} SKU mappings for client {self.client_id}")
            return normalized
        except Exception as e:
            # Graceful degradation: if SKU mapping fails to load, continue without it
            # Scanned barcodes will be matched directly against order SKUs
            logger.error(f"Error loading SKU mappings: {e}")
            return {}

    def set_sku_map(self, sku_map: Dict[str, str]):
        """
        Set the SKU map and save to ProfileManager.

        The barcode (key) is normalized to ensure consistent matching with
        scanner input. The SKU (value) is left as is. Changes are persisted
        to the centralized file server.

        Args:
            sku_map: The Barcode-to-SKU mapping

        Note:
            This method now saves to ProfileManager for cross-PC synchronization.
        """
        logger.info(f"Updating SKU mapping: {len(sku_map)} entries")

        # Normalize for in-memory use
        self.sku_map = {self._normalize_sku(k): v for k, v in sku_map.items()}

        # Save to ProfileManager (original keys, not normalized)
        try:
            self.profile_manager.save_sku_mapping(self.client_id, sku_map)
            logger.info("SKU mapping saved successfully")
        except Exception as e:
            logger.error(f"Failed to save SKU mapping: {e}")

    def _get_state_file_path(self) -> str:
        """
        Return path to packing_state.json in work_dir root.

        For unified workflow: work_dir/packing_state.json
        For Excel workflow: barcodes/packing_state.json (backward compatible)
        """
        return str(self.work_dir / STATE_FILE_NAME)

    def _get_summary_file_path(self) -> str:
        """
        Return path to session_summary.json in work_dir root.

        For unified workflow: work_dir/session_summary.json
        For Excel workflow: barcodes/session_summary.json (backward compatible)
        """
        return str(self.work_dir / SUMMARY_FILE_NAME)

    def _load_session_state(self):
        """
        Load the packing state for the session from JSON file with caching.

        This method supports both old and new state file formats for backward compatibility:
        - Old format: {'in_progress': {...}, 'completed_orders': [...]}
        - New format: Full state with metadata (session_id, timestamps, progress, etc.)

        Note: Uses JSON cache with short TTL (30s) for state files since they change frequently.
        Cache is invalidated after every write to ensure consistency.
        """
        state_file = self._get_state_file_path()

        if not os.path.exists(state_file):
            logger.debug("No existing session state found, starting fresh")
            self.session_packing_state = {'in_progress': {}, 'completed_orders': [], 'skipped_orders': [], 'skipped_orders_timing': {}}
            return

        try:
            # OPTIMIZED: Use JSON cache for faster repeated reads
            # This helps when multiple workers/processes access the same state file
            # Note: Cache is invalidated after writes in _save_session_state()
            data = get_cached_json(state_file, default=None)

            if data is None:
                # File exists but couldn't be read (invalid JSON, etc.)
                logger.error("Could not load session state, starting fresh")
                self.session_packing_state = {'in_progress': {}, 'completed_orders': [], 'skipped_orders': [], 'skipped_orders_timing': {}}
                return

            # Handle both old and new format (with version)
            if isinstance(data, dict) and 'data' in data:
                # Legacy format with version wrapper
                state_data = data['data']
            else:
                # Could be new format (with metadata) or old direct format
                state_data = data

            # Load core packing state with validation
            # CRITICAL FIX: Validate in_progress structure to prevent AttributeError on resume
            raw_in_progress = state_data.get('in_progress', {})
            validated_in_progress = {}

            if isinstance(raw_in_progress, dict):
                for order_num, order_state in raw_in_progress.items():
                    # Skip internal metadata keys (like _timing)
                    if order_num.startswith('_'):
                        continue

                    # Validate that order_state is a list
                    if not isinstance(order_state, list):
                        logger.error(
                            f"CRITICAL: Invalid order state for {order_num}: expected list, got {type(order_state).__name__}. "
                            f"Skipping this order to prevent crash."
                        )
                        continue

                    # Validate that each item in the list is a dict
                    validated_items = []
                    for idx, item_state in enumerate(order_state):
                        if not isinstance(item_state, dict):
                            logger.error(
                                f"CRITICAL: Invalid item state in order {order_num} at index {idx}: "
                                f"expected dict, got {type(item_state).__name__}. Skipping this item."
                            )
                            continue

                        # Ensure critical keys exist (be lenient for backward compatibility)
                        # Support multiple legacy formats for SKU identification:
                        # - New format: 'original_sku' and/or 'normalized_sku'
                        # - Legacy format: 'sku' (used by old tests and early versions)

                        # Check if item has any form of SKU identifier
                        has_sku = 'original_sku' in item_state or 'normalized_sku' in item_state or 'sku' in item_state

                        if has_sku:
                            # Migrate legacy 'sku' field to new format if needed
                            if 'sku' in item_state and 'original_sku' not in item_state:
                                item_state['original_sku'] = item_state['sku']
                                logger.debug(f"Migrated legacy 'sku' field to 'original_sku' in {order_num}")

                            if 'original_sku' in item_state and 'normalized_sku' not in item_state:
                                # Generate normalized_sku from original_sku if missing
                                item_state['normalized_sku'] = self._normalize_sku(item_state['original_sku'])
                                logger.debug(f"Generated normalized_sku from original_sku in {order_num}")
                            elif 'normalized_sku' in item_state and 'original_sku' not in item_state:
                                # Use normalized_sku as original_sku if original is missing
                                item_state['original_sku'] = item_state['normalized_sku']
                                logger.debug(f"Used normalized_sku as original_sku in {order_num}")

                            # Fill in missing optional fields with defaults
                            if 'packed' not in item_state:
                                item_state['packed'] = 0
                                logger.debug(f"Added default packed=0 for item in {order_num}")
                            if 'required' not in item_state:
                                item_state['required'] = 0
                                logger.debug(f"Added default required=0 for item in {order_num}")
                            if 'row' not in item_state:
                                item_state['row'] = idx
                                logger.debug(f"Added default row={idx} for item in {order_num}")

                            validated_items.append(item_state)
                        else:
                            logger.error(
                                f"CRITICAL: Item state in order {order_num} at index {idx} has no SKU identifier "
                                f"(missing 'original_sku', 'normalized_sku', and 'sku'). Skipping item."
                            )

                    # Only include orders with valid items
                    if validated_items:
                        validated_in_progress[order_num] = validated_items
                    else:
                        logger.warning(f"Order {order_num} has no valid items after validation, skipping")
            else:
                logger.error(f"in_progress is not a dict: {type(raw_in_progress).__name__}, using empty state")

            self.session_packing_state['in_progress'] = validated_in_progress
            logger.debug(f"Loaded and validated {len(validated_in_progress)} in-progress orders")

            # Handle both new format (completed: list of dicts) and old format (completed_orders: list of strings)
            if 'completed' in state_data:
                # New format: list of dicts with metadata
                completed_list = state_data.get('completed', [])
                if completed_list and isinstance(completed_list[0], dict):
                    # Extract order numbers from metadata dicts
                    self.session_packing_state['completed_orders'] = [
                        item['order_number'] for item in completed_list if 'order_number' in item
                    ]

                    # ✅ CRITICAL: Restore timing metadata for Phase 2b
                    self.completed_orders_metadata = []
                    for item in completed_list:
                        metadata = {
                            'order_number': item['order_number'],
                            'started_at': item.get('started_at'),
                            'completed_at': item.get('completed_at'),
                            'duration_seconds': item.get('duration_seconds', 0),
                            'items_count': item.get('items_count', 0),
                            'items': item.get('items', []),
                            # Restore 1.7 quality counters so generate_session_summary()
                            # aggregates correctly across resumed sessions.
                            'corrections': item.get('corrections', 0),
                            'extra_scans_count': item.get('extra_scans_count', 0),
                            'unknown_scans_count': item.get('unknown_scans_count', 0),
                            'time_to_first_scan_seconds': item.get('time_to_first_scan_seconds'),
                        }
                        self.completed_orders_metadata.append(metadata)

                    logger.info(f"Restored {len(self.completed_orders_metadata)} orders with timing metadata")
                else:
                    # Fallback if completed is just a list of strings
                    self.session_packing_state['completed_orders'] = completed_list
                    self.completed_orders_metadata = []
                    logger.debug("Loaded old format state (no timing metadata)")
            else:
                # Old format: simple list of order numbers
                self.session_packing_state['completed_orders'] = state_data.get('completed_orders', [])
                self.completed_orders_metadata = []
                logger.debug("Old format: no timing metadata available")

            # Load skipped orders list (added in later versions; default to empty list)
            self.session_packing_state['skipped_orders'] = state_data.get('skipped_orders', [])
            # Load skipped orders timing (maps order_num -> ISO skip timestamp)
            self.session_packing_state['skipped_orders_timing'] = state_data.get('skipped_orders_timing', {})

            # Load metadata if present (new format)
            if 'session_id' in state_data:
                self.session_id = state_data.get('session_id')
                self.packing_list_name = state_data.get('packing_list_name')
                self.started_at = state_data.get('started_at')
                # worker_pc is set from environment in __init__, but can be overridden from state
                logger.debug(f"Loaded session metadata: {self.session_id}")

            # Phase 2b: Restore in-progress timing if present
            if 'in_progress' in state_data and '_timing' in state_data['in_progress']:
                timing_data = state_data['in_progress']['_timing']
                self.current_order_start_time = timing_data.get('current_order_start_time')
                self.current_order_items_scanned = timing_data.get('items_scanned', [])
                self.current_order_corrections = timing_data.get('corrections', 0)
                self.current_order_extra_scan_count = timing_data.get('extra_scan_count', 0)
                self.current_order_unknown_scan_count = timing_data.get('unknown_scan_count', 0)
                logger.debug(f"Restored in-progress timing: started_at={self.current_order_start_time}")
            else:
                self.current_order_start_time = None
                self.current_order_items_scanned = []
                self.current_order_corrections = 0
                self.current_order_extra_scan_count = 0
                self.current_order_unknown_scan_count = 0

            # Restore extra items if present (crash recovery)
            self.current_extra_items = state_data.get('_current_extras', {})

            in_progress_count = len(self.session_packing_state['in_progress'])
            completed_count = len(self.session_packing_state['completed_orders'])

            logger.info(f"Session state loaded: {in_progress_count} in progress, {completed_count} completed")

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading session state: {e}, starting fresh")
            self.session_packing_state = {'in_progress': {}, 'completed_orders': [], 'skipped_orders': [], 'skipped_orders_timing': {}}

    def _build_state_dict(self) -> Dict[str, Any]:
        """
        Build the complete state dictionary from current in-memory data.

        Must be called on the main thread (reads self.processed_df and
        self.session_packing_state which are mutated by packing logic).
        Returns a plain serialisable dict — safe to hand off to a background thread.
        """
        total_orders = len(self.orders_data) if self.orders_data else 0
        completed_orders_count = len(self.session_packing_state.get('completed_orders', []))

        total_items = self._total_items
        packed_items = sum(o.get('items_count', 0) for o in self.completed_orders_metadata)

        for order_state in self.session_packing_state.get('in_progress', {}).values():
            if isinstance(order_state, list):
                for item in order_state:
                    if isinstance(item, dict):
                        packed_items += item.get('packed', 0)

        from shared.metadata_utils import get_current_timestamp

        return {
            "version": "1.3.0",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "packing_list_name": self.packing_list_name,
            "started_at": self.started_at,
            "last_updated": get_current_timestamp(),
            "status": "completed" if completed_orders_count == total_orders and total_orders > 0 else "in_progress",
            "pc_name": self.worker_pc,
            "progress": {
                "total_orders": total_orders,
                "completed_orders": completed_orders_count,
                "in_progress_order": self.current_order_number,
                "total_items": total_items,
                "packed_items": packed_items
            },
            "in_progress": {
                **self.session_packing_state.get('in_progress', {}),
                **({
                    "_timing": {
                        "current_order_start_time": self.current_order_start_time,
                        "items_scanned": self.current_order_items_scanned,
                        "corrections": self.current_order_corrections,
                        "extra_scan_count": self.current_order_extra_scan_count,
                        "unknown_scan_count": self.current_order_unknown_scan_count,
                    }
                } if self.current_order_number and self.current_order_start_time else {})
            },
            "_current_extras": self.current_extra_items if self.current_extra_items else {},
            "completed": (
                self.completed_orders_metadata
                if hasattr(self, 'completed_orders_metadata') and self.completed_orders_metadata
                else self._build_completed_list()
            ),
            "skipped_orders": list(self.session_packing_state.get('skipped_orders', [])),
            "skipped_orders_timing": dict(self.session_packing_state.get('skipped_orders_timing', {})),
        }

    def _do_atomic_write(self, state_data: Dict[str, Any]) -> None:
        """
        Write state_data to disk using an atomic temp-file → rename pattern.

        Called by AsyncStateWriter from a background thread.
        state_data must be a plain serialisable dict (no shared mutable objects).
        """
        state_file = self._get_state_file_path()
        total_orders = state_data.get("progress", {}).get("total_orders", 0)
        completed_orders_count = state_data.get("progress", {}).get("completed_orders", 0)
        packed_items = state_data.get("progress", {}).get("packed_items", 0)
        total_items = state_data.get("progress", {}).get("total_items", 0)

        try:
            state_path = Path(state_file)
            state_dir = state_path.parent

            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=state_dir,
                prefix='.tmp_state_',
                suffix='.json',
                delete=False,
                encoding='utf-8'
            ) as tmp_file:
                json.dump(state_data, tmp_file, indent=2, ensure_ascii=False)
                tmp_path = tmp_file.name

            shutil.move(tmp_path, state_file)
            invalidate_json_cache(state_file)

            logger.debug(f"Session state saved: {completed_orders_count}/{total_orders} orders, {packed_items}/{total_items} items")

        except Exception as e:
            logger.error(f"CRITICAL: Failed to save session state: {e}", exc_info=True)

    def _save_session_state(self) -> None:
        """
        Flush any pending async write, then write the current state synchronously.

        Backward-compatible synchronous write — callers (including tests) that
        call this method can rely on the file being present immediately after return.
        """
        self._state_writer.flush()
        self._state_writer.schedule(self._build_state_dict())
        # Flush again so the just-scheduled write completes before we return
        self._state_writer.flush()

    def _save_session_state_async(self) -> None:
        """
        Schedule an async write of the current state (non-blocking).

        Use on the hot path (every SKU scan, cancel, extra) where a small
        write delay is acceptable and UI responsiveness matters most.
        """
        self._state_writer.schedule(self._build_state_dict())

    def _save_session_state_sync(self) -> None:
        """
        Flush any pending async write, write the current state, and wait for it to land.

        Use at order-complete and session-end checkpoints to guarantee the
        file on disk is up-to-date before the next significant action.
        """
        self._state_writer.flush()
        self._state_writer.schedule(self._build_state_dict())
        self._state_writer.flush()  # Wait for the just-scheduled write to complete

    def save_state(self) -> None:
        """Public API: flush any pending async write and save current state synchronously."""
        self._save_session_state_sync()

    def close(self) -> None:
        """
        Flush any pending state write and shut down the background writer thread.

        Call this when the session ends or the PackerLogic instance is discarded.
        """
        self._state_writer.shutdown()

    def _build_completed_list(self) -> List[Dict[str, Any]]:
        """
        Build list of completed orders with timestamps and durations.

        Returns:
            List of dicts with order metadata:
            [
                {
                    "order_number": "ORDER-001",
                    "completed_at": "2025-11-10T14:35:12",
                    "items_count": 3,
                    "duration_seconds": 45
                }
            ]

        Note: This is a basic implementation. Full timestamps tracking requires
        storing start time for each order (future enhancement).
        """
        from shared.metadata_utils import get_current_timestamp
        # Single approximate timestamp for the whole fallback list (not per-order)
        fallback_ts = get_current_timestamp()
        completed_list = []

        for order_number in self.session_packing_state.get('completed_orders', []):
            items_count = 0
            if order_number in self.orders_data:
                items_count = len(self.orders_data[order_number].get('items', []))

            completed_list.append({
                "order_number": order_number,
                "completed_at": fallback_ts,  # Approximation — no per-order timestamps available
                "items_count": items_count,
                # duration_seconds omitted: no start time available in fallback path
            })

        return completed_list

    def _complete_current_order(self):
        """Complete current order with timing metadata

        Called when all items in order are scanned. Records completion time,
        calculates duration, and stores detailed timing data for analytics.

        Phase 2b: Enhanced timing tracking
        """
        from shared.metadata_utils import get_current_timestamp, calculate_duration

        if not self.current_order_number:
            logger.warning("_complete_current_order called but no current order")
            return

        # Record completion time
        completed_at = get_current_timestamp()

        # Calculate order duration
        if self.current_order_start_time:
            duration_seconds = calculate_duration(
                self.current_order_start_time,
                completed_at
            )
        else:
            duration_seconds = 0
            logger.warning(f"Order {self.current_order_number} has no start time")

        # Extract first-scan latency from scan records (if any)
        time_to_first_scan = None
        for record in self.current_order_items_scanned:
            if "time_to_first_scan_seconds" in record:
                time_to_first_scan = record["time_to_first_scan_seconds"]
                break

        # items_count = total units packed (sum of quantities across all scan records).
        # Using sum() rather than len() correctly accounts for force-confirm records
        # that represent multiple units in a single record entry.
        items_count = sum(r.get('quantity', 1) for r in self.current_order_items_scanned)

        # Build order metadata record with full 1.7 metrics
        order_metadata = {
            "order_number": self.current_order_number,
            "started_at": self.current_order_start_time,
            "completed_at": completed_at,
            "duration_seconds": duration_seconds,
            "items_count": items_count,
            "items": self.current_order_items_scanned.copy(),
            # 1.7 per-order counters
            "corrections": self.current_order_corrections,
            "extra_scans_count": self.current_order_extra_scan_count,
            "unknown_scans_count": self.current_order_unknown_scan_count,
        }
        if time_to_first_scan is not None:
            order_metadata["time_to_first_scan_seconds"] = time_to_first_scan

        # Add to completed orders metadata
        self.completed_orders_metadata.append(order_metadata)

        logger.info(
            f"Order {self.current_order_number} completed: "
            f"duration={duration_seconds}s, items={items_count}, "
            f"corrections={self.current_order_corrections}, "
            f"extras={self.current_order_extra_scan_count}, "
            f"unknown={self.current_order_unknown_scan_count}"
        )

        # Note: We don't reset current_order_number here because it's still needed
        # for legacy state management. The reset happens in clear_current_order() or
        # when starting a new order.

    def _initialize_session_metadata(self, session_id: str = None, packing_list_name: str = None):
        """
        Initialize session metadata for state tracking.

        This should be called when starting a new packing session (loading packing list).
        Sets up timestamps and identifiers for the session.

        Args:
            session_id: Unique session identifier (e.g., "2025-11-10_1")
            packing_list_name: Name of the packing list being packed (e.g., "DHL_Orders")
        """
        if not self.started_at:
            # Only set started_at if not already set (for session restoration)
            from shared.metadata_utils import get_current_timestamp
            self.started_at = get_current_timestamp()

        if session_id:
            self.session_id = session_id
        elif not self.session_id:
            # Generate session_id from timestamp if not provided
            self.session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        if packing_list_name:
            self.packing_list_name = packing_list_name

        logger.info(f"Session metadata initialized: {self.session_id} / {self.packing_list_name}")

    def _normalize_sku(self, sku: Any) -> str:
        """
        Normalizes an SKU for consistent comparison across different input sources.

        This normalization is essential for small warehouse operations where SKUs/barcodes
        can come from multiple sources with inconsistent formatting:
        - Manual Excel entry: may include spaces, dashes, parentheses
        - Barcode scanners: may add prefixes/suffixes depending on configuration
        - Different suppliers: varying formatting conventions
        - Copy-paste from supplier websites: may include special characters

        The normalization algorithm:
        1. Convert to string (handles numeric SKUs like "12345")
        2. Remove all non-alphanumeric characters (spaces, dashes, dots, etc.)
        3. Convert to lowercase (handles case-insensitive matching)

        Examples:
            "SKU-123-A" -> "sku123a"
            "7290 0186 6410 0" -> "72900186641100"
            "Product (ABC)" -> "productabc"
            12345 -> "12345"

        Args:
            sku (Any): The SKU to normalize, typically a string or number.
                      Can be Excel cell value (str, int, float)

        Returns:
            str: The normalized SKU string (lowercase alphanumeric only)
        """
        return ''.join(filter(str.isalnum, str(sku))).lower()

    def _normalize_order_number(self, order_number: str) -> str:
        """
        Normalize order number for barcode matching.

        Identical to Shopify Tool's sanitize_order_number().
        This ensures scanned barcodes match orders regardless of special characters.

        The normalization removes special characters but preserves structural elements:
        - Keeps: alphanumeric (a-z, A-Z, 0-9), hyphen (-), underscore (_)
        - Removes: #, !, spaces, quotes, and all other special chars
        - Preserves: Case sensitivity (unlike SKU normalization)

        This allows barcodes generated by Shopify Tool to match order numbers
        stored in analysis_data.json even if the original CSV had special characters.

        Examples:
            "#1001" -> "1001"
            "ORD-123!" -> "ORD-123"
            "Test Order" -> "TestOrder"
            "ABC_123-X" -> "ABC_123-X"

        Args:
            order_number: The order number to normalize

        Returns:
            Normalized order number (alphanumeric + dash + underscore only)

        Note:
            Empty strings or None return empty string.
            Order numbers with only special chars (e.g., "###") return empty string.
        """
        if not order_number:
            return ""

        # Same normalization as Shopify Tool's sanitize_order_number()
        normalized = ''.join(c for c in str(order_number) if c.isalnum() or c in ['-', '_'])

        # Log warning if order number becomes empty after normalization
        if not normalized:
            logger.warning(f"Order number '{order_number}' has no valid alphanumeric characters")

        return normalized

    def _build_order_lookup(self):
        self._build_order_lookup()

    def start_order_packing(self, scanned_text: str) -> Tuple[List[Dict] | None, str]:
        """
        Starts or resumes packing an order based on a scanned barcode.

        It looks up the order number, validates its status (e.g., not already
        completed), and loads its packing state into memory.

        Args:
            scanned_text (str): The content from the scanned order barcode.

        Returns:
            Tuple[List[Dict] | None, str]: A tuple containing the list of items
                                           for the order and a status string
                                           ("ORDER_LOADED", "ORDER_NOT_FOUND",
                                           "ORDER_ALREADY_COMPLETED").
        """
        # STEP 1: Find order using normalized comparison
        scanned_normalized = self._normalize_order_number(scanned_text)
        logger.debug(f"Scanned text: '{scanned_text}' -> Normalized: '{scanned_normalized}'")

        # Find matching order in orders_data via pre-built normalized lookup (O(1))
        matched_order_number = self._normalized_order_lookup.get(scanned_normalized)
        if matched_order_number:
            logger.debug(f"Match found: '{scanned_text}' matches order '{matched_order_number}'")

        if not matched_order_number:
            logger.info(f"Order not found for scanned text: '{scanned_text}'")
            return None, "ORDER_NOT_FOUND"

        original_order_number = matched_order_number

        if original_order_number in self.session_packing_state['completed_orders']:
            return None, "ORDER_ALREADY_COMPLETED"

        self.current_order_number = original_order_number
        items = self.orders_data[original_order_number]['items']

        # Capture "is this a brand-new order?" BEFORE potentially adding it to in_progress.
        is_new_order = original_order_number not in self.session_packing_state['in_progress']

        if not is_new_order:
            self.current_order_state = self.session_packing_state['in_progress'][original_order_number]
        else:
            self.current_order_state = []
            for i, item in enumerate(items):
                sku = item.get('SKU')
                if not sku: continue
                try:
                    quantity = int(float(item.get('Quantity', 0)))
                except (ValueError, TypeError):
                    quantity = 1

                normalized_sku = self._normalize_sku(sku)
                self.current_order_state.append({
                    'original_sku': sku,
                    'normalized_sku': normalized_sku,
                    'required': quantity,
                    'packed': 0,
                    'row': i
                })
            self.session_packing_state['in_progress'][original_order_number] = self.current_order_state
            self._save_session_state_async()

        # Phase 2b: Record order start time.
        # Only reset timing for brand-new orders. For orders already in in_progress (resumed
        # from a previous session), preserve the start time and scanned items list that were
        # restored by _load_session_state() so timing continuity is maintained.
        from shared.metadata_utils import get_current_timestamp
        if is_new_order:
            self.current_order_start_time = get_current_timestamp()
            self.current_order_items_scanned = []
            self.current_order_corrections = 0
            self.current_order_extra_scan_count = 0
            self.current_order_unknown_scan_count = 0
            logger.info(f"Order {original_order_number} started at {self.current_order_start_time}")
        else:
            # Resumed order — all timing and per-order quality counters were restored from
            # _timing in _load_session_state(); nothing to reset here.
            # If start time is missing despite being in in_progress, fall back gracefully.
            if not self.current_order_start_time:
                self.current_order_start_time = get_current_timestamp()
                logger.warning(
                    f"Order {original_order_number} resumed but had no start time; "
                    "resetting to now"
                )
            logger.info(
                f"Order {original_order_number} resumed; "
                f"preserving start_time={self.current_order_start_time}, "
                f"{len(self.current_order_items_scanned)} items already scanned"
            )

        return items, "ORDER_LOADED"

    def process_sku_scan(self, sku: str) -> Tuple[Dict | None, str]:
        """
        Processes a scanned SKU for the currently active order.

        This is the core method called every time a warehouse worker scans a product
        barcode. It handles:
        1. SKU normalization (to handle different barcode formats)
        2. SKU mapping translation (manufacturer barcode -> internal SKU)
        3. Matching against order requirements
        4. Updating packing progress
        5. Detecting order completion
        6. Persisting state after every scan (crash recovery)

        The method implements a sophisticated matching logic that:
        - Tries to find the SKU in the current order
        - Supports multi-quantity items (scan same SKU multiple times)
        - Detects when an item is fully packed
        - Detects when entire order is complete
        - Handles error cases (wrong SKU, already packed, etc.)

        Args:
            sku (str): The raw content from the scanned product SKU barcode.
                      Can be any format (EAN-13, UPC, manufacturer code, internal SKU)

        Returns:
            Tuple[Dict | None, str]: A tuple containing:
                - Result dictionary with packing details (if successful)
                  {"row": int, "packed": int, "is_complete": bool}
                - Status string indicating what happened:
                  * "SKU_OK" - Item packed successfully, order still in progress
                  * "ORDER_COMPLETE" - Item packed and order is now complete
                  * "SKU_NOT_FOUND" - Scanned SKU is not in this order
                  * "SKU_EXTRA" - All items with this SKU are already packed
                  * "NO_ACTIVE_ORDER" - No order currently selected
        """
        # Safety check: ensure an order is actually loaded
        # This prevents errors if user somehow scans before loading an order
        if not self.current_order_number:
            return None, "NO_ACTIVE_ORDER"

        # === STEP 1: Normalize scanned barcode ===
        # Remove spaces, dashes, convert to lowercase
        # This handles variations in scanner configuration and barcode formats
        normalized_scan = self._normalize_sku(sku)

        # === STEP 2: SKU Mapping Translation (if configured) ===
        # This is a critical feature for small warehouses where:
        # - Products come from multiple suppliers with different barcodes
        # - Manufacturer barcodes don't match internal SKU system
        # - Same product has different barcodes from different batches
        #
        # Example scenarios:
        #   Scan: "7290018664100" (EAN-13 barcode)
        #   Map:  "7290018664100" -> "SKU-CREAM-01" (internal SKU)
        #   Use:  "SKU-CREAM-01" for matching
        #
        # Fallback behavior:
        #   If no mapping exists, use the scanned barcode directly
        #   This ensures backward compatibility with orders that use
        #   manufacturer barcodes directly in the packing list
        final_sku = self.sku_map.get(normalized_scan, normalized_scan)

        # Normalize the final SKU (whether mapped or direct)
        # This ensures consistent matching even if mapping returns non-normalized value
        normalized_final_sku = self._normalize_sku(final_sku)

        # === STEP 3: Find matching item in current order ===
        # Search through all items in the order for a match
        # Important: we look for the FIRST item that:
        # 1. Matches the SKU
        # 2. Is not yet fully packed (packed < required)
        #
        # This handles multi-quantity items correctly:
        # Example: Order requires 3x "SKU-CREAM-01"
        # - First scan: packed=0 -> packed=1
        # - Second scan: packed=1 -> packed=2
        # - Third scan: packed=2 -> packed=3 (complete!)
        found_item = None
        for item_state in self.current_order_state:
            if item_state['normalized_sku'] == normalized_final_sku and item_state['packed'] < item_state['required']:
                found_item = item_state
                break

        # === STEP 4: Process successful match ===
        if found_item:
            # Increment packed count for this item
            found_item['packed'] += 1

            # Check if this specific item is now complete
            # (all required quantity for this SKU has been packed)
            is_complete = found_item['packed'] == found_item['required']

            # Phase 2b: Record item scan with timestamp
            from shared.metadata_utils import get_current_timestamp, calculate_duration

            scan_timestamp = get_current_timestamp()

            # Calculate time from order start
            if self.current_order_start_time:
                time_from_order_start = calculate_duration(
                    self.current_order_start_time,
                    scan_timestamp
                )
            else:
                time_from_order_start = 0
                logger.warning("Order start time not set, cannot calculate timing")

            # Get item details from orders_data
            items_list = self.orders_data[self.current_order_number]['items']
            item_idx = found_item['row']

            # Record first-scan latency (time between order start and very first item scan)
            time_to_first_scan = (
                time_from_order_start if len(self.current_order_items_scanned) == 0 else None
            )

            # Build item scan record — quantity=1: each scan packs exactly one unit.
            # "row" is stored so cancel_item_scan() can target the correct record
            # by row index rather than by SKU (which is ambiguous when multiple
            # rows share the same SKU, e.g. split-line orders).
            item_title = (
                items_list[item_idx].get('Product_Name', normalized_final_sku)
                if item_idx < len(items_list)
                else normalized_final_sku
            )
            item_scan_record = {
                "sku": normalized_final_sku,
                "title": item_title,
                "quantity": 1,
                "row": item_idx,
                "scanned_at": scan_timestamp,
                "time_from_order_start_seconds": time_from_order_start,
                "confirmation_method": "scanned",
            }
            if time_to_first_scan is not None:
                item_scan_record["time_to_first_scan_seconds"] = time_to_first_scan

            # Add to scanned items list
            self.current_order_items_scanned.append(item_scan_record)

            logger.debug(f"Item {normalized_final_sku} scanned at +{time_from_order_start}s from order start")

            # Update session state (in-memory)
            self.session_packing_state['in_progress'][self.current_order_number] = self.current_order_state

            # === Check if ENTIRE order is complete ===
            # An order is complete when ALL items have been packed
            # (not just the current item)
            all_items_complete = all(s['packed'] == s['required'] for s in self.current_order_state)

            if all_items_complete:
                if self.current_extra_items:
                    # Extra items detected — wait for worker to resolve them before completing
                    status = "ORDER_COMPLETE_WITH_EXTRAS"
                    self._save_session_state_sync()
                    return {
                        "row": found_item['row'],
                        "packed": found_item['packed'],
                        "is_complete": is_complete,
                    }, status
                # Order is complete!
                status = "ORDER_COMPLETE"

                # Phase 2b: Complete order with timing metadata
                self._complete_current_order()

                # Move order from "in_progress" to "completed_orders"
                del self.session_packing_state['in_progress'][self.current_order_number]

                # Add to completed list (if not already there)
                # This check prevents duplicates in case of rare edge cases
                if self.current_order_number not in self.session_packing_state['completed_orders']:
                    self.session_packing_state['completed_orders'].append(self.current_order_number)

                # Remove from skipped list if this order was previously skipped
                self._unskip_current_order_if_needed()

                # Emit session-complete signal if all orders done
                self._check_all_complete()
            else:
                # Order still in progress
                status = "SKU_OK"

                # Calculate overall progress for this order
                # (total items packed vs total items required)
                total_packed = sum(s['packed'] for s in self.current_order_state)
                total_required = sum(s['required'] for s in self.current_order_state)

                # Emit Qt signal to update UI progress display
                # This allows the UI to show "5/8 items packed" in real-time
                self.item_packed.emit(self.current_order_number, total_packed, total_required)

            # === Save state to disk ===
            # ORDER_COMPLETE: flush first (checkpoint) so the completed order is persisted
            # before the UI transitions away.
            # SKU_OK / other: async write — UI returns immediately, write happens in background.
            if status == "ORDER_COMPLETE":
                self._save_session_state_sync()
            else:
                self._save_session_state_async()

            # Return success with detailed information
            return {"row": found_item['row'], "packed": found_item['packed'], "is_complete": is_complete}, status

        # === STEP 5: Handle error cases ===
        # If we reach here, the scanned SKU didn't match any unpacked item

        # Check if SKU exists in order but all items are already packed
        is_sku_in_order = any(s['normalized_sku'] == normalized_final_sku for s in self.current_order_state)

        if is_sku_in_order:
            # SKU is in order, but all required quantity already packed — track as extra
            self.current_extra_items[normalized_final_sku] = (
                self.current_extra_items.get(normalized_final_sku, 0) + 1
            )
            self.current_order_extra_scan_count += 1
            self._save_session_state_async()
            return None, "SKU_EXTRA"
        else:
            # SKU is not in this order at all
            # Example: User scanned wrong product, or product from different order
            self.unknown_scans.append(sku)
            self.current_order_unknown_scan_count += 1
            return None, "SKU_NOT_FOUND"

    def clear_current_order(self):
        """Clears the currently active order from memory."""
        self.current_order_number = None
        self.current_order_state = {}
        self.current_extra_items = {}
        self.unknown_scans = []

    def skip_order(self) -> None:
        """Mark the current order as skipped, then check for overall session completion."""
        if not self.current_order_number:
            return
        from shared.metadata_utils import get_current_timestamp
        order_num = self.current_order_number
        skipped = self.session_packing_state['skipped_orders']
        if order_num not in skipped:
            skipped.append(order_num)
        # Record the skip timestamp for metrics
        self.session_packing_state.setdefault('skipped_orders_timing', {})[order_num] = get_current_timestamp()
        self.clear_current_order()
        self._check_all_complete()
        self._save_session_state_async()

    def _unskip_current_order_if_needed(self) -> None:
        """Remove current_order_number from skipped_orders if it was previously skipped."""
        skipped = self.session_packing_state['skipped_orders']
        if self.current_order_number in skipped:
            skipped.remove(self.current_order_number)

    def cancel_item_scan(self, row: int) -> Tuple[Dict, str]:
        """
        Decrements the packed count for the item at the given row by 1.

        Args:
            row: Row index in current_order_state.

        Returns:
            Tuple of (result_dict, status_string).
            status_string values: "ITEM_DECREMENTED", "ITEM_ALREADY_ZERO", "NO_ACTIVE_ORDER"
        """
        if not self.current_order_number:
            return {}, "NO_ACTIVE_ORDER"
        item = next((s for s in self.current_order_state if s.get('row') == row), None)
        if item is None:
            return {}, "NO_ACTIVE_ORDER"
        if item['packed'] <= 0:
            return {"row": row, "packed": 0}, "ITEM_ALREADY_ZERO"
        item['packed'] -= 1
        self.current_order_corrections += 1

        # Adjust the most recent scan record for this item so that items_count in the
        # completed-order metadata reflects only the final packed quantity.
        # Match by row (precise) so that cancelling row N never accidentally modifies a
        # record belonging to a different row that happens to share the same SKU.
        # Records with quantity > 1 (e.g. a force-confirm record) are decremented rather
        # than deleted, since only one unit is being cancelled at a time.
        for i in range(len(self.current_order_items_scanned) - 1, -1, -1):
            rec = self.current_order_items_scanned[i]
            if rec.get('row') == row:
                if rec.get('quantity', 1) > 1:
                    rec['quantity'] -= 1
                else:
                    self.current_order_items_scanned.pop(i)
                break

        self.session_packing_state['in_progress'][self.current_order_number] = self.current_order_state
        self._save_session_state_async()
        return {"row": row, "packed": item['packed']}, "ITEM_DECREMENTED"

    def force_confirm_item(self, row: int) -> Tuple[Dict, str]:
        """
        Forces an item row to fully packed (packed = required).

        Args:
            row: Row index in current_order_state.

        Returns:
            Tuple of (result_dict, status_string).
            result_dict keys: "row", "packed", "is_complete", "order_complete"
            status_string values: "FORCE_CONFIRMED", "NO_ACTIVE_ORDER"
        """
        if not self.current_order_number:
            return {}, "NO_ACTIVE_ORDER"
        item = next((s for s in self.current_order_state if s.get('row') == row), None)
        if item is None:
            return {}, "NO_ACTIVE_ORDER"

        # Add a scan record for the force-confirmed quantity (remaining unpacked qty).
        # This ensures _complete_current_order() sees a full items list with timestamps.
        from shared.metadata_utils import get_current_timestamp, calculate_duration
        force_timestamp = get_current_timestamp()
        time_from_start = (
            calculate_duration(self.current_order_start_time, force_timestamp)
            if self.current_order_start_time else 0
        )
        items_list = self.orders_data[self.current_order_number]['items']
        item_idx = item.get('row', 0)
        item_title = (
            items_list[item_idx].get('Product_Name', item['normalized_sku'])
            if 0 <= item_idx < len(items_list)
            else item['normalized_sku']
        )
        # quantity = remaining units being force-confirmed (packed will jump from current to required)
        remaining_qty = item['required'] - item['packed']
        force_record = {
            "sku": item['normalized_sku'],
            "title": item_title,
            "quantity": remaining_qty,
            "row": item_idx,
            "scanned_at": force_timestamp,
            "time_from_order_start_seconds": time_from_start,
            "confirmation_method": "force_confirmed",
        }
        # Only add record if there are remaining units to force-confirm
        if remaining_qty > 0:
            self.current_order_items_scanned.append(force_record)

        item['packed'] = item['required']
        self.session_packing_state['in_progress'][self.current_order_number] = self.current_order_state
        all_done = all(s['packed'] >= s['required'] for s in self.current_order_state)
        if all_done and not self.current_extra_items:
            self._complete_current_order()
            del self.session_packing_state['in_progress'][self.current_order_number]
            if self.current_order_number not in self.session_packing_state['completed_orders']:
                self.session_packing_state['completed_orders'].append(self.current_order_number)
            self._unskip_current_order_if_needed()
            self._check_all_complete()
            self._save_session_state_sync()  # Checkpoint: order now complete
        else:
            self._save_session_state_async()
        return {
            "row": row,
            "packed": item['required'],
            "is_complete": True,
            "order_complete": all_done and not self.current_extra_items,
        }, "FORCE_CONFIRMED"

    def _check_all_complete(self):
        """Emit all_orders_complete if every order in the session is packed or skipped."""
        total = len(self.orders_data)
        done = len(self.session_packing_state['completed_orders'])
        skipped = len(self.session_packing_state['skipped_orders'])
        if total > 0 and (done + skipped) >= total:
            self.all_orders_complete.emit()

    def confirm_keep_extra(self, normalized_sku: str) -> Tuple[Dict, str]:
        """
        Acknowledges an extra item as intentionally included.
        Removes it from current_extra_items and checks if order can complete.

        Returns: ({}, "ORDER_NOW_COMPLETE") or ({}, "EXTRA_PENDING")
        """
        self.current_extra_items.pop(normalized_sku, None)
        return self._maybe_complete_after_extra_resolution()

    def remove_extra_item(self, normalized_sku: str) -> Tuple[Dict, str]:
        """
        Marks one extra item of a SKU as removed (acknowledged as a mistake).
        Decrements extra count; removes the key when count reaches 0.

        Returns: ({}, "ORDER_NOW_COMPLETE") or ({}, "EXTRA_PENDING")
        """
        count = self.current_extra_items.get(normalized_sku, 0)
        if count > 1:
            self.current_extra_items[normalized_sku] = count - 1
        else:
            self.current_extra_items.pop(normalized_sku, None)
        return self._maybe_complete_after_extra_resolution()

    def _maybe_complete_after_extra_resolution(self) -> Tuple[Dict, str]:
        """
        After an extra item is kept/removed, check if all extras are resolved
        and complete the order if so.
        """
        if self.current_extra_items:
            self._save_session_state_async()
            return {}, "EXTRA_PENDING"
        # Extras cleared — verify all required items are actually packed
        all_items_done = all(
            s['packed'] >= s['required'] for s in self.current_order_state
        )
        if not all_items_done:
            self._save_session_state_async()
            return {}, "EXTRA_CLEARED"
        # All items packed AND all extras resolved — finalize the order
        self._complete_current_order()
        del self.session_packing_state['in_progress'][self.current_order_number]
        if self.current_order_number not in self.session_packing_state['completed_orders']:
            self.session_packing_state['completed_orders'].append(self.current_order_number)
        self._unskip_current_order_if_needed()
        self._check_all_complete()
        self._save_session_state_sync()  # Checkpoint: order now complete
        return {}, "ORDER_NOW_COMPLETE"

    def load_packing_list_json(self, packing_list_path: Path) -> Tuple[int, str]:
        """
        Завантажити конкретний пакінг лист з JSON файлу.

        This method loads a specific packing list JSON file generated by Shopify Tool.
        Packing list JSONs are pre-filtered collections of orders ready for packing,
        typically organized by courier or delivery method.

        Expected JSON format:
        {
          "list_name": "DHL_Orders",
          "created_at": "2025-11-11T10:00:00",
          "courier": "DHL",  # Optional, if list is courier-specific
          "total_orders": 25,
          "orders": [
            {
              "order_number": "ORDER-001",
              "courier": "DHL",
              "items": [
                {"sku": "SKU-123", "quantity": 2, "product_name": "Product A"}
              ]
            }
          ]
        }

        Args:
            packing_list_path: Повний шлях до JSON файлу пакінг листа
                              (e.g., .../packing_lists/DHL_Orders.json)

        Returns:
            Tuple[int, str]: (кількість замовлень, назва листа)

        Raises:
            ValueError: Якщо файл не існує або невалідний JSON
            RuntimeError: If barcode generation fails
        """
        logger.info(f"Loading packing list from: {packing_list_path}")

        # Validate file exists
        packing_list_path = Path(packing_list_path)
        if not packing_list_path.exists():
            error_msg = f"Packing list file not found: {packing_list_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract list name from filename (without .json extension)
        list_name = packing_list_path.stem

        # Load JSON data
        try:
            with open(packing_list_path, 'r', encoding='utf-8') as f:
                packing_data = json.load(f)

            logger.debug(f"Loaded packing list: {packing_data.get('list_name', list_name)}")

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in packing list file: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Error reading packing list file: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract orders list
        orders_list = packing_data.get('orders', [])
        if not orders_list:
            logger.warning(f"No orders found in packing list: {list_name}")
            return 0, packing_data.get('list_name', list_name)

        # Build raw order lookup for metadata preservation
        order_raw_data = {order.get('order_number', ''): order for order in orders_list}

        # Convert to DataFrame (packing list format)
        # Each order may have multiple items, need to flatten
        rows = []

        for order in orders_list:
            # Validate required order fields
            missing_fields = []
            if 'order_number' not in order:
                missing_fields.append('order_number')
            if 'courier' not in order or not order['courier']:
                missing_fields.append('courier')

            if missing_fields:
                error_msg = f"Missing required fields in order data: {missing_fields}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            order_number = order['order_number']
            courier = order['courier']
            items = order.get('items', [])

            if not items:
                logger.warning(f"Order {order_number} has no items, skipping")
                continue

            for item in items:
                row = {
                    'Order_Number': order_number,
                    'SKU': item.get('sku', ''),
                    'Product_Name': item.get('product_name', ''),
                    'Quantity': str(item.get('quantity', 1)),  # Convert to string for consistency
                    'Courier': courier
                }

                # Add any extra fields from order
                # (e.g., customer name, address, tracking number, etc.)
                for key, value in order.items():
                    if key not in ['order_number', 'courier', 'items']:
                        # Capitalize key to match packing list style
                        formatted_key = key.replace('_', ' ').title().replace(' ', '_')
                        row[formatted_key] = str(value)

                rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows)

        if df.empty:
            logger.warning("No order items to process")
            return 0, packing_data.get('list_name', list_name)

        # Validate required columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            error_msg = f"Missing required columns in packing list: {missing_cols}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Store as packing_list_df and processed_df
        self.packing_list_df = df
        self.processed_df = df.copy()
        self._total_items = int(pd.to_numeric(df['Quantity'], errors='coerce').sum())

        logger.info(f"Converted {len(df)} items from {len(orders_list)} orders to DataFrame")

        # Group items by order and populate orders_data
        self.orders_data = {}
        for order_number in df['Order_Number'].unique():
            order_df = df[df['Order_Number'] == order_number]
            raw = order_raw_data.get(order_number, {})
            self.orders_data[order_number] = {
                'items': order_df.to_dict('records'),
                'metadata': {
                    'order_type':               raw.get('order_type') or '',
                    'shipping_provider':        raw.get('shipping_provider') or raw.get('courier') or '',
                    'destination_country':      raw.get('destination_country') or raw.get('shipping_country') or '',
                    'tags':                     list(raw.get('tags') or []),
                    'notes':                    raw.get('notes') or '',
                    'system_note':              raw.get('system_note') or '',
                    'internal_tags':            list(raw.get('internal_tags') or []),
                    'order_min_box':            raw.get('order_min_box') or '',
                    'order_fulfillment_status': raw.get('order_fulfillment_status') or '',
                },
            }

        self._build_order_lookup()

        # Initialize session metadata
        # Extract session_id from path if available (e.g., .../Sessions/CLIENT_M/2025-11-10_1/...)
        session_id = None
        try:
            # Try to extract session_id from path (parent directory name)
            parent_path = packing_list_path.parent
            if parent_path.name == 'packing_lists':
                # Path is .../packing_lists/list.json, go up one more level
                session_dir = parent_path.parent
                session_id = session_dir.name
        except Exception as e:
            logger.debug(f"Could not extract session_id from path: {e}")

        self._initialize_session_metadata(
            session_id=session_id,
            packing_list_name=packing_data.get('list_name', list_name)
        )

        # Count orders (barcodes pre-generated by Shopify Tool)
        try:
            order_count = len(self.orders_data)
            logger.info(f"Successfully loaded packing list '{list_name}': {order_count} orders")

            return order_count, packing_data.get('list_name', list_name)

        except Exception as e:
            error_msg = f"Error generating barcodes from packing list: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)

    def load_from_shopify_analysis(self, session_path: Path) -> Tuple[int, str]:
        """
        Load orders data from Shopify Tool's analysis_data.json.

        This method enables integration with Shopify Tool (Phase 1.3.2).
        It reads analysis_data.json from a Shopify session and converts it
        into the packing_list format expected by PackerLogic.

        Workflow:
        1. Read analysis_data.json from session/analysis/
        2. Convert Shopify order format to packing list DataFrame
        3. Generate barcodes for all orders
        4. Initialize orders_data structure

        Analysis data format (from Shopify Tool):
        {
          "analyzed_at": "2025-11-04T11:00:00",
          "total_orders": 150,
          "fulfillable_orders": 142,
          "orders": [
            {
              "order_number": "ORDER-001",
              "courier": "DHL",
              "status": "Fulfillable",
              "items": [
                {"sku": "SKU-123", "quantity": 2, "product_name": "Product A"}
              ]
            }
          ]
        }

        Args:
            session_path: Path to Shopify session directory
                         (e.g., Sessions/CLIENT_M/2025-11-04_1/)

        Returns:
            Tuple of (order_count, analysis_timestamp)

        Raises:
            ValueError: If analysis_data.json not found or invalid format
            RuntimeError: If barcode generation fails
        """
        logger.info(f"Loading data from Shopify session: {session_path}")

        # Locate analysis_data.json
        analysis_file = Path(session_path) / "analysis" / "analysis_data.json"

        if not analysis_file.exists():
            error_msg = f"analysis_data.json not found in {session_path}/analysis/"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Load analysis data
        try:
            with open(analysis_file, 'r', encoding='utf-8') as f:
                analysis_data = json.load(f)

            logger.debug(f"Loaded analysis data: {analysis_data.get('total_orders', 0)} orders")

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in analysis_data.json: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Error reading analysis_data.json: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract orders list
        orders_list = analysis_data.get('orders', [])
        if not orders_list:
            logger.warning("No orders found in analysis_data.json")
            return 0, analysis_data.get('analyzed_at', 'Unknown')

        # Build raw order lookup for metadata preservation
        order_raw_data_analysis = {order.get('order_number', ''): order for order in orders_list}

        # Convert to DataFrame (packing list format)
        # Each order may have multiple items, need to flatten
        rows = []

        for order in orders_list:
            # Validate required order fields
            missing_fields = []
            if 'order_number' not in order:
                missing_fields.append('order_number')

            if missing_fields:
                error_msg = f"Missing required columns in order data: {missing_fields}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            order_number = order['order_number']
            # Courier is optional in analysis_data.json (contains all orders before filtering)
            # Use default value if not present
            courier = order.get('courier', 'N/A')
            items = order.get('items', [])

            for item in items:
                row = {
                    'Order_Number': order_number,
                    'SKU': item.get('sku', ''),
                    'Product_Name': item.get('product_name', ''),
                    'Quantity': str(item.get('quantity', 1)),  # Convert to string for consistency
                    'Courier': courier
                }

                # Add any extra fields from Shopify analysis
                # (e.g., customer name, address, etc.)
                for key, value in order.items():
                    if key not in ['order_number', 'courier', 'items', 'status']:
                        # Capitalize key to match packing list style
                        formatted_key = key.replace('_', ' ').title().replace(' ', '_')
                        row[formatted_key] = str(value)

                rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows)

        if df.empty:
            logger.warning("No order items to process")
            return 0, analysis_data.get('analyzed_at', 'Unknown')

        # Validate required columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            error_msg = f"Missing required columns in analysis data: {missing_cols}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Store as packing_list_df and processed_df
        self.packing_list_df = df
        self.processed_df = df.copy()
        self._total_items = int(pd.to_numeric(df['Quantity'], errors='coerce').sum())

        logger.info(f"Converted {len(df)} items from {len(orders_list)} orders to DataFrame")

        # Group items by order and populate orders_data
        self.orders_data = {}
        for order_number in df['Order_Number'].unique():
            order_df = df[df['Order_Number'] == order_number]
            raw = order_raw_data_analysis.get(order_number, {})
            self.orders_data[order_number] = {
                'items': order_df.to_dict('records'),
                'metadata': {
                    'order_type':               raw.get('order_type') or '',
                    'shipping_provider':        raw.get('shipping_provider') or raw.get('courier') or '',
                    'destination_country':      raw.get('destination_country') or raw.get('shipping_country') or '',
                    'tags':                     list(raw.get('tags') or []),
                    'notes':                    raw.get('notes') or '',
                    'system_note':              raw.get('system_note') or '',
                    'internal_tags':            list(raw.get('internal_tags') or []),
                    'order_min_box':            raw.get('order_min_box') or '',
                    'order_fulfillment_status': raw.get('order_fulfillment_status') or '',
                },
            }

        self._build_order_lookup()

        # Initialize session metadata
        # Extract session_id from session_path (e.g., .../Sessions/CLIENT_M/2025-11-10_1)
        session_id = Path(session_path).name
        packing_list_name = "Shopify_Full_Session"

        self._initialize_session_metadata(
            session_id=session_id,
            packing_list_name=packing_list_name
        )

        # Count orders (barcodes pre-generated by Shopify Tool)
        try:
            order_count = len(self.orders_data)
            logger.info(f"Successfully loaded Shopify session: {order_count} orders")

            return order_count, analysis_data.get('analyzed_at', 'Unknown')

        except Exception as e:
            error_msg = f"Error loading Shopify data: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)

    def generate_session_summary(
        self,
        worker_id: str = None,
        worker_name: str = None,
        session_type: str = "shopify"
    ) -> dict:
        """
        Generate comprehensive session summary upon completion.

        Creates a unified v1.3.0 format session summary with:
        - Session metadata (ID, client, packing list, timestamps, worker info)
        - Counts (total orders, completed orders, items, unique SKUs)
        - Performance metrics (orders/hour, items/hour, average times)

        Args:
            worker_id: Worker who completed session (e.g., "worker_001")
            worker_name: Worker display name (e.g., "Dolphin")
            session_type: "shopify" or "excel"

        Returns:
            dict: Unified session summary (v1.3.0 format, ready for JSON serialization)

        Example structure:
        {
            "version": "1.3.0",
            "session_id": "2025-11-10_1",
            "session_type": "shopify",
            "client_id": "M",
            "packing_list_name": "DHL_Orders",
            "worker_id": "worker_001",
            "worker_name": "Dolphin",
            "pc_name": "WAREHOUSE-PC-01",
            "started_at": "2025-11-10T14:30:00+02:00",
            "completed_at": "2025-11-10T16:20:45+02:00",
            "duration_seconds": 6645,
            "total_orders": 45,
            "completed_orders": 45,
            "total_items": 156,
            "unique_skus": 42,
            "metrics": {
                "avg_time_per_order": 147.6,
                "avg_time_per_item": 42.6,
                "fastest_order_seconds": 0,
                "slowest_order_seconds": 0,
                "orders_per_hour": 24.3,
                "items_per_hour": 84.2
            },
            "orders": []
        }
        """
        from shared.metadata_utils import get_current_timestamp, calculate_duration

        logger.info("Generating session summary (v1.3.0 format)")

        # Calculate timestamps and duration
        completed_at = get_current_timestamp()
        duration_seconds = 0

        if self.started_at:
            duration_seconds = calculate_duration(self.started_at, completed_at)
            if duration_seconds == 0:
                # Fallback to old method if calculate_duration fails
                try:
                    started_dt = datetime.fromisoformat(self.started_at)
                    completed_dt = datetime.now()
                    duration_seconds = int((completed_dt - started_dt).total_seconds())
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse started_at for duration calculation: {e}")

        # Calculate order and item counts
        total_orders = len(self.orders_data) if self.orders_data else 0
        completed_orders = len(self.session_packing_state.get('completed_orders', []))

        # Calculate total items
        total_items = 0
        if self.processed_df is not None:
            try:
                import pandas as pd
                total_items = int(pd.to_numeric(self.processed_df['Quantity'], errors='coerce').sum())
            except Exception as e:
                logger.warning(f"Could not calculate total_items: {e}")

        # Count unique SKUs
        unique_skus = self._count_unique_skus()

        # Calculate metrics from completed_orders_metadata
        orders_with_timing = self.completed_orders_metadata if self.completed_orders_metadata else []

        # --- Order-level timing ---
        durations = [o['duration_seconds'] for o in orders_with_timing if o.get('duration_seconds')]
        if durations:
            avg_time_per_order = round(sum(durations) / len(durations), 1)
            fastest_order_seconds = min(durations)
            slowest_order_seconds = max(durations)
        else:
            avg_time_per_order = 0
            fastest_order_seconds = 0
            slowest_order_seconds = 0

        # --- Item-level timing ---
        all_items = []
        for order in orders_with_timing:
            all_items.extend(order.get('items', []))

        item_times = [
            item['time_from_order_start_seconds']
            for item in all_items
            if 'time_from_order_start_seconds' in item
        ]
        avg_time_per_item = round(sum(item_times) / len(item_times), 1) if item_times else 0

        total_items_from_metadata = sum(o.get('items_count', 0) for o in orders_with_timing)

        # --- 1.7 metrics: first-scan latency ---
        first_scan_latencies = [
            o['time_to_first_scan_seconds']
            for o in orders_with_timing
            if o.get('time_to_first_scan_seconds') is not None
        ]
        avg_time_to_first_scan = (
            round(sum(first_scan_latencies) / len(first_scan_latencies), 1)
            if first_scan_latencies else 0
        )

        # --- 1.7 metrics: corrections, extras, unknown scans ---
        total_corrections = sum(o.get('corrections', 0) for o in orders_with_timing)
        total_extra_scans = sum(o.get('extra_scans_count', 0) for o in orders_with_timing)
        total_unknown_scans = sum(o.get('unknown_scans_count', 0) for o in orders_with_timing)
        avg_corrections_per_order = (
            round(total_corrections / len(orders_with_timing), 2) if orders_with_timing else 0
        )

        if not orders_with_timing:
            logger.warning("No timing metadata available, metrics will be zero")

        # --- Session-level throughput ---
        orders_per_hour = 0
        items_per_hour = 0
        if duration_seconds and duration_seconds > 0:
            hours = duration_seconds / 3600.0
            if completed_orders > 0:
                orders_per_hour = round(completed_orders / hours, 1)
            items_for_rate = total_items_from_metadata if total_items_from_metadata > 0 else total_items
            if items_for_rate > 0:
                items_per_hour = round(items_for_rate / hours, 1)

        # --- Skipped orders list for the summary ---
        skipped_timing = self.session_packing_state.get('skipped_orders_timing', {})
        skipped_orders_list = [
            {"order_number": num, "skipped_at": skipped_timing.get(num), "status": "skipped"}
            for num in self.session_packing_state.get('skipped_orders', [])
        ]

        # Build unified session summary
        summary = {
            # Metadata
            "version": "1.3.0",
            "session_id": self.session_id,
            "session_type": session_type,
            "client_id": self.client_id,
            "packing_list_name": self.packing_list_name,

            # Ownership
            "worker_id": worker_id,
            "worker_name": worker_name if worker_name else "Unknown",
            "pc_name": self.worker_pc,

            # Timing
            "started_at": self.started_at,
            "completed_at": completed_at,
            "duration_seconds": duration_seconds,

            # Counts
            "total_orders": total_orders,
            "completed_orders": completed_orders,
            "in_progress_orders": len(self.session_packing_state.get('in_progress', {})),
            "skipped_orders_count": len(skipped_orders_list),
            "total_items": total_items,
            "unique_skus": unique_skus,

            # Metrics
            "metrics": {
                "avg_time_per_order": avg_time_per_order,
                "avg_time_per_item": avg_time_per_item,
                "fastest_order_seconds": fastest_order_seconds,
                "slowest_order_seconds": slowest_order_seconds,
                "orders_per_hour": orders_per_hour,
                "items_per_hour": items_per_hour,
                # 1.7 metrics
                "avg_time_to_first_scan": avg_time_to_first_scan,
                "total_corrections": total_corrections,
                "avg_corrections_per_order": avg_corrections_per_order,
                "total_extra_scans": total_extra_scans,
                "total_unknown_scans": total_unknown_scans,
            },

            # Completed orders with full timing data
            "orders": orders_with_timing,

            # Skipped orders list
            "skipped_orders": skipped_orders_list,
        }

        logger.info(
            f"Session summary generated: {completed_orders}/{total_orders} orders, "
            f"{len(skipped_orders_list)} skipped, {total_items} items, "
            f"{duration_seconds}s duration, {orders_per_hour} orders/hour"
        )

        return summary

    def _count_unique_skus(self) -> int:
        """Count unique SKUs across all orders

        Returns:
            int: Number of unique SKUs in the packing list
        """
        if self.processed_df is None:
            return 0

        try:
            unique_skus = self.processed_df['SKU'].nunique()
            return int(unique_skus)
        except Exception as e:
            logger.warning(f"Could not count unique SKUs: {e}")
            return 0

    def save_session_summary(
        self,
        summary_path: str = None,
        worker_id: str = None,
        worker_name: str = None,
        session_type: str = "shopify"
    ) -> str:
        """
        Generate and save session summary to JSON file.

        Args:
            summary_path: Optional path to save summary. If None, saves to work_dir/session_summary.json
            worker_id: Worker who completed session (e.g., "worker_001")
            worker_name: Worker display name (e.g., "Dolphin")
            session_type: "shopify" or "excel"

        Returns:
            Path to saved summary file

        Raises:
            IOError: If summary cannot be written to disk
        """
        # Generate summary with worker info
        summary = self.generate_session_summary(
            worker_id=worker_id,
            worker_name=worker_name,
            session_type=session_type
        )

        # Determine output path
        if not summary_path:
            summary_path = self._get_summary_file_path()

        # Save to file
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            logger.info(f"Session summary (v1.3.0) saved to: {summary_path}")
            return summary_path

        except Exception as e:
            logger.error(f"Failed to save session summary: {e}", exc_info=True)
            raise IOError(f"Failed to save session summary: {e}")

    def end_session_cleanup(self):
        """
        Perform cleanup when ending a session.

        New behavior (redesigned state management):
        - Does NOT remove packing_state.json (kept as history)
        - State files are permanent historical records
        - session_summary.json should be created separately via save_session_summary()

        Shuts down the async state writer (flushes any pending write).
        """
        logger.info("Session cleanup called (state files preserved as history)")
        self.close()
