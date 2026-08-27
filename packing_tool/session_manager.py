"""
Session Manager - Manages the lifecycle of packing sessions.

This module handles session creation, organization by client, and session
state tracking. It integrates with ProfileManager for centralized storage
on the file server.

Key responsibilities:
- Creating timestamped session directories organized by client
- Managing session lock acquisition and heartbeat mechanism
- Tracking active session state for crash recovery
- Providing paths for session data (barcodes, state files, reports)
- Coordinating with SessionLockManager for multi-PC safety

For small warehouse operations, this module ensures that:
- Multiple PCs can work on different orders simultaneously
- Sessions are properly isolated by client
- Crashes don't corrupt data or prevent session recovery
- Historical session data is preserved for analytics
"""

# Standard library imports
import json  # For session info persistence

# Local imports
import logging
import os  # For environment variables (PC name)
from pathlib import Path  # Modern path handling

from packing_tool.exceptions import (
    SessionAlreadyActiveError,
    SessionLockedError,
    StaleLockError,
)
from shared.atomic_write import atomic_write_json
from shared.file_lock import locked_file
from shared.metadata_utils import get_current_timestamp

# Initialize module-level logger
logger = logging.getLogger(__name__)

# Filename for session information file
# This file is created at session start and deleted at graceful session end
# Its presence indicates a session that may need recovery after a crash
# Contains: client_id, packing_list_path, started_at, pc_name
SESSION_INFO_FILE = "session_info.json"


class SessionManager:
    """
    Manages the lifecycle of client-specific packing sessions.

    This class handles the creation of timestamped session directories organized
    by client, tracks the active state of a session, and manages the session
    information file used for crash recovery and restoration.

    Attributes:
        client_id (str): Current client identifier
        profile_manager (ProfileManager): Reference to ProfileManager for path operations
        session_id (str | None): The unique identifier for the current session
        session_active (bool): True if a session is currently active
        output_dir (Path | None): The path to the current session's directory
        packing_list_path (str | None): Path to the original Excel packing list
    """

    def __init__(
        self,
        client_id: str,
        profile_manager,
        lock_manager,
        worker_id: str | None = None,
        worker_name: str | None = None
    ):
        """
        Initialize SessionManager for a specific client.

        Args:
            client_id: Client identifier (e.g., "M", "R")
            profile_manager: ProfileManager instance for path operations
            lock_manager: SessionLockManager instance for session locking
            worker_id: Worker ID (e.g., "worker_001")
            worker_name: Worker display name
        """
        self.client_id = client_id
        self.profile_manager = profile_manager
        self.lock_manager = lock_manager
        self.worker_id = worker_id
        self.worker_name = worker_name
        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None
        self.heartbeat_timer = None

        logger.info(f"SessionManager initialized for client {client_id} (Worker: {worker_name})")

    def start_session(self, packing_list_path: str, restore_dir: str | None = None) -> str:
        """
        Start a new packing session or restore a crashed session.

        This method handles two scenarios:
        1. **New Session**: Creates a new timestamped directory and initializes fresh state
        2. **Restore Session**: Recovers a previously crashed session from its directory

        Session Directory Structure:
            SESSIONS/CLIENT_M/2025-11-03_14-30-45/
                session_info.json       (session metadata for recovery)
                .session.lock           (lock file with heartbeat)
                barcodes/               (generated barcode images and state)
                    packing_state.json  (packing progress)
                    ORDER-123.png       (barcode labels)
                output/                 (completed reports)

        Lock Acquisition Process:
        - Before starting/restoring, check if session is locked by another process
        - If locked by another PC -> raise SessionLockedError (show user who has it)
        - If lock is stale (>2 min without heartbeat) -> raise StaleLockError (offer force-release)
        - If lock is ours (same PC, same process) -> reacquire safely
        - After successful lock, start heartbeat timer (updates every 60 seconds)

        For small warehouse operations:
        - Multiple workers on different PCs can pack different orders simultaneously
        - If a PC crashes, session can be restored without data loss
        - Prevents data corruption from concurrent access
        - Historical sessions preserved for analytics and auditing

        Args:
            packing_list_path: Absolute path to the source Excel file
            restore_dir: Optional absolute path to existing session directory to restore
                        If provided, attempts to restore that session
                        If None, creates new timestamped session

        Returns:
            The session ID (directory name, e.g., "2025-11-03_14-30-45")

        Raises:
            SessionAlreadyActiveError: If a session is already active (call end_session() first)
            SessionLockedError: If session is actively locked by another process
                               (lock_info contains: locked_by, user_name, lock_time)
            StaleLockError: If session has a stale lock (process crashed/not responding)
                           (includes stale_minutes for user decision making)
        """
        # === SAFETY CHECK: Prevent multiple active sessions ===
        # Only one session can be active per SessionManager instance
        # This prevents confusion and ensures proper lock management
        if self.session_active:
            logger.error("Attempted to start session while one is already active")
            raise SessionAlreadyActiveError("A session is already active. Please end the current session first.")

        logger.info(f"Starting session for client {self.client_id}")

        # === SCENARIO 1: Restore existing session (crash recovery) ===
        if restore_dir:
            # User selected a previously crashed/incomplete session to restore
            # This typically happens when:
            # - Application crashed during packing
            # - PC restarted unexpectedly
            # - User wants to continue yesterday's work
            self.output_dir = Path(restore_dir)
            self.session_id = self.output_dir.name

            # Ensure barcodes subdirectory exists (may have been deleted by accident)
            barcodes_dir = self.output_dir / "barcodes"
            barcodes_dir.mkdir(exist_ok=True)

            # === CRITICAL: Check if session is locked ===
            # Before restoring, verify the session isn't currently open on another PC
            # This prevents data corruption from two PCs working on same session
            is_locked, lock_info = self.lock_manager.is_locked(self.output_dir)

            if is_locked:
                # Session has an existing lock file - need to determine if it's safe to proceed

                # === CASE 1: It's our own lock (same PC, same process) ===
                # This can happen if user clicks "Restore" on a session that was never
                # properly closed (e.g., UI bug, forced window close)
                if (lock_info.get('locked_by') == self.lock_manager.hostname and
                    lock_info.get('process_id') == self.lock_manager.process_id):
                    # Safe to proceed - it's literally the same application instance
                    logger.info(f"Restoring our own locked session: {self.session_id}")
                else:
                    # Lock belongs to another process (different PC or different app instance)

                    # === CASE 2: Lock is stale (crashed process) ===
                    # Check if heartbeat hasn't been updated in over 2 minutes
                    # This indicates the locking process has crashed or is unresponsive
                    if self.lock_manager.is_lock_stale(lock_info):
                        # Calculate how long since last heartbeat (for user information)
                        stale_minutes = self.lock_manager._get_stale_minutes(lock_info)

                        logger.warning(f"Session has stale lock: {self.session_id}")

                        # Raise StaleLockError - UI will offer user option to force-release
                        # User can decide: "It's been 10 minutes, that PC probably crashed, I'll take over"
                        raise StaleLockError(
                            "Session has stale lock",
                            lock_info=lock_info,
                            stale_minutes=stale_minutes
                        )
                    else:
                        # === CASE 3: Active lock by another process ===
                        # Heartbeat is recent (< 2 minutes), another process is actively using this session
                        # Do NOT allow restore - would cause data corruption
                        logger.warning(f"Session is locked by another process: {self.session_id}")

                        # Raise SessionLockedError - UI will show "User X on PC Y is working on this"
                        # User must wait or choose a different session
                        raise SessionLockedError(
                            "Session is locked by another process",
                            lock_info=lock_info
                        )

            logger.info(f"Restoring session: {self.session_id}")

        # === SCENARIO 2: Create new session ===
        else:
            # Create new timestamped session directory
            # ProfileManager generates timestamp: "2025-11-03_14-30-45"
            # This ensures unique session IDs and natural chronological sorting
            self.output_dir = self.profile_manager.get_session_dir(self.client_id)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.session_id = self.output_dir.name

            # Create barcodes subdirectory for this session
            # This will contain:
            # - Generated barcode PNG images
            # - packing_state.json (progress tracking)
            barcodes_dir = self.output_dir / "barcodes"
            barcodes_dir.mkdir(exist_ok=True)

            logger.info(f"Created new session: {self.session_id}")
            logger.debug(f"Session directory: {self.output_dir}")

        # === ACQUIRE SESSION LOCK ===
        # This is the critical step that prevents concurrent access
        # The lock file will contain:
        # - locked_by: hostname of this PC
        # - user_name: Windows username
        # - lock_time: when lock was acquired
        # - process_id: PID of this application instance
        # - heartbeat: timestamp of last heartbeat update
        # - worker_id: Worker ID (Phase 1.3)
        # - worker_name: Worker display name (Phase 1.3)
        success, error_msg, lock_info = self.lock_manager.acquire_lock(
            self.client_id,
            self.output_dir,
            worker_id=self.worker_id,
            worker_name=self.worker_name
        )

        if not success:
            logger.error(f"Failed to acquire session lock: {error_msg}")
            if lock_info and self.lock_manager.is_lock_stale(lock_info):
                stale_minutes = self.lock_manager._get_stale_minutes(lock_info)
                raise StaleLockError(error_msg, lock_info=lock_info, stale_minutes=stale_minutes)
            raise SessionLockedError(error_msg)

        # Lock successfully acquired - we now have exclusive access to this session

        # Update instance state
        self.packing_list_path = packing_list_path
        self.session_active = True

        # === CREATE SESSION INFO FILE ===
        # This file serves multiple purposes:
        # 1. Crash recovery: If app crashes, this file helps identify incomplete sessions
        # 2. Session restoration: Contains original packing list path for reloading
        # 3. Auditing: Records when session started and on which PC
        # 4. Session discovery: UI scans for these files to show restorable sessions
        #
        # File is deleted on graceful session end, so its presence = incomplete session
        info_path = self.output_dir / SESSION_INFO_FILE
        session_info = {
            'client_id': self.client_id,
            'packing_list_path': self.packing_list_path,
            'started_at': get_current_timestamp(),  # timezone-aware ISO format for parsing
            'pc_name': os.environ.get('COMPUTERNAME', 'Unknown')  # Windows PC name
        }

        try:
            atomic_write_json(info_path, session_info, indent=2)
            logger.debug(f"Created session info file: {info_path}")
        except Exception:
            # Non-critical failure - session can still function
            # But recovery after crash will be harder without this file
            logger.exception("Failed to create session info file")

        # === START HEARTBEAT MECHANISM ===
        # Start periodic timer that updates lock file every 60 seconds
        # This proves to other PCs that this session is still actively being used
        # If heartbeat stops (crash/hang), lock becomes "stale" after 2 minutes
        # and other PCs can force-release it
        #
        # Why 60 seconds?
        # - Frequent enough to detect crashes quickly (2-minute stale timeout)
        # - Infrequent enough to not cause file server overhead
        # - Based on practical experience with small warehouse network speeds
        self._start_heartbeat()

        logger.info(f"Session {self.session_id} started successfully with lock")
        return self.session_id

    def end_session(self):
        """
        End the current session and perform cleanup.

        This resets the manager's state, releases the session lock,
        stops the heartbeat timer, and removes the `session_info.json` file,
        effectively marking the session as gracefully closed and not in need
        of restoration.
        """
        if not self.session_active:
            logger.warning("Attempted to end session when none is active")
            return

        logger.info(f"Ending session: {self.session_id}")

        # Stop heartbeat timer
        self._stop_heartbeat()

        # Release session lock
        if self.output_dir:
            self.lock_manager.release_lock(self.output_dir)

        self._cleanup_session_files()

        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

        logger.info("Session ended successfully")

    def _cleanup_session_files(self):
        """Remove the session info file to prevent it from being restored."""
        if not self.output_dir:
            return

        info_path = self.output_dir / SESSION_INFO_FILE

        if info_path.exists():
            try:
                info_path.unlink()
                logger.debug(f"Removed session info file: {info_path}")
            except OSError as e:
                logger.warning(f"Failed to remove session info file: {e}")

    def is_active(self) -> bool:
        """
        Check if a session is currently active.

        Returns:
            True if a session is active, False otherwise
        """
        return self.session_active

    def get_output_dir(self) -> str | None:
        """
        Get the output directory for the current session.

        Returns:
            Path to the session directory, or None if no session is active
        """
        return str(self.output_dir) if self.output_dir else None

    def get_barcodes_dir(self) -> str | None:
        """
        Get the barcodes subdirectory for the current session.

        Returns:
            Path to the barcodes directory, or None if no session is active
        """
        if not self.output_dir:
            return None

        barcodes_dir = self.output_dir / "barcodes"
        return str(barcodes_dir)

    def get_session_info(self) -> dict | None:
        """
        Get session information from session_info.json.

        Returns:
            Dictionary with session information, or None if not available
        """
        if not self.output_dir:
            return None

        info_path = self.output_dir / SESSION_INFO_FILE

        if not info_path.exists():
            return None

        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            logger.exception("Error reading session info")
            return None

    def _start_heartbeat(self):
        """
        Start periodic heartbeat updates for crash detection.

        This method starts a Qt timer that updates the session lock's heartbeat
        timestamp every 60 seconds. This heartbeat mechanism is critical for
        multi-PC environments to detect crashed sessions.

        How it works:
        1. Timer fires every 60 seconds
        2. Calls _update_heartbeat() which updates lock file
        3. If application crashes, timer stops -> heartbeat stops updating
        4. After 2 minutes without heartbeat, lock is considered "stale"
        5. Other PCs can then detect the crash and offer to take over the session

        For small warehouses:
        - If PC-1 crashes while packing, PC-2 can detect it within 2 minutes
        - No manual intervention needed to identify crashed sessions
        - Prevents long delays in order fulfillment due to crashed sessions
        - Workers can immediately continue work on another PC

        Note: This requires Qt event loop to be running (PySide6.QtCore.QTimer).
        Import is done inside the method to avoid circular dependencies with main.py

        Implementation details:
        - Uses QTimer for cross-platform compatibility (works on Windows/Linux/macOS)
        - 60000 milliseconds = 60 seconds (consistent with SessionLockManager timeout values)
        - Non-critical failure: if heartbeat fails to start, session still works
          (but crash detection won't work on other PCs)
        """
        try:
            # Import here to avoid circular dependency
            # (main.py imports SessionManager, which would import QTimer at module level)
            from PySide6.QtCore import QTimer

            # Safety check: prevent multiple timers from running
            if self.heartbeat_timer is not None:
                logger.debug("Heartbeat timer already running, skipping start")
                return

            # Create and configure timer
            self.heartbeat_timer = QTimer()

            # Connect timer timeout signal to our heartbeat update method
            # Every time timer fires, _update_heartbeat() will be called
            self.heartbeat_timer.timeout.connect(self._update_heartbeat)

            # Start timer with 60-second interval
            # Timer will fire continuously every 60 seconds until stopped
            self.heartbeat_timer.start(60000)  # 60 seconds in milliseconds

            logger.info(f"Heartbeat timer started for session {self.session_id}")

        except ImportError:
            # PySide6 not available (e.g., running in test environment without Qt)
            # Non-fatal: session will work, but other PCs won't be able to detect crashes
            logger.warning("PySide6 not available, heartbeat disabled")
        except Exception:
            # Unexpected error starting timer
            # Log but don't crash - session can still function without heartbeat
            logger.exception("Failed to start heartbeat timer")

    def _stop_heartbeat(self):
        """
        Stop the heartbeat timer when ending a session.

        This should be called when ending a session to stop periodic
        heartbeat updates. Stopping the timer is important to:
        - Free system resources (prevent timer from running indefinitely)
        - Ensure clean session cleanup
        - Prevent heartbeat updates after lock is released

        Called by end_session() during normal shutdown.
        """
        if self.heartbeat_timer is not None:
            try:
                # Stop timer from firing
                self.heartbeat_timer.stop()

                # Clear reference to allow garbage collection
                self.heartbeat_timer = None

                logger.info("Heartbeat timer stopped")
            except Exception:
                # Non-critical failure - log and continue
                # Timer will be garbage collected anyway when session ends
                logger.exception("Failed to stop heartbeat timer")

    def _update_heartbeat(self):
        """
        Update the heartbeat timestamp in the session lock file.

        This method is called automatically by the heartbeat timer every 60 seconds.
        It updates the 'heartbeat' field in the .session.lock file with the current
        timestamp, proving to other PCs that this session is still actively running.

        The heartbeat update process:
        1. Read current lock file contents
        2. Update 'heartbeat' field with current timestamp
        3. Write back to file (with file locking to prevent corruption)

        If heartbeat update fails:
        - Log warning but don't crash session
        - Session continues to work normally on this PC
        - Other PCs may incorrectly detect session as stale after 2 minutes
        - User would need to force-release stale lock (but our PC is still using it)

        Why this is usually reliable:
        - File server is typically stable (SMB/CIFS protocol)
        - Updates are small and fast (just a JSON timestamp)
        - Failure is rare in practice (tested in real warehouse environments)
        """
        # Safety check: ensure session is still active
        # (timer might fire one last time after end_session() is called)
        if not self.output_dir:
            return

        try:
            # Delegate to SessionLockManager to handle file locking and update
            success = self.lock_manager.update_heartbeat(self.output_dir)

            if not success:
                # Heartbeat update failed (file locked, network issue, etc.)
                # Log warning so we can investigate if this happens frequently
                logger.warning(f"Heartbeat update failed for session {self.session_id}")
                # Note: We don't raise exception - session should continue working

        except Exception:
            # Unexpected error during heartbeat update
            # Log but don't crash - this is a background operation
            logger.exception("Error updating heartbeat")

    def load_packing_list(self, session_path: str, packing_list_name: str) -> dict:
        """
        Load packing list JSON from Shopify session.

        This method loads a packing list JSON file generated by Shopify Tool
        from the packing_lists/ subdirectory within a Shopify session.

        Args:
            session_path: Full path to Shopify session
                         (e.g., "\\\\server\\...\\Sessions\\CLIENT_M\\2025-11-10_1")
            packing_list_name: Name of packing list (e.g., "DHL_Orders")
                              Can be with or without .json extension

        Returns:
            dict: Packing list data containing:
                - session_id: Session identifier
                - report_name: Name of the report
                - created_at: Timestamp of creation
                - total_orders: Number of orders in the list
                - total_items: Total number of items
                - filters_applied: Filters used to generate the list
                - orders: Array of order objects with items

        Raises:
            FileNotFoundError: If packing list file doesn't exist
            json.JSONDecodeError: If JSON file is malformed
            KeyError: If required 'orders' key is missing from JSON

        Example:
            data = sm.load_packing_list(
                "\\\\server\\...\\Sessions\\CLIENT_M\\2025-11-10_1",
                "DHL_Orders"
            )
            print(f"Orders to pack: {data['total_orders']}")
            for order in data['orders']:
                print(f"Order {order['order_number']}: {len(order['items'])} items")
        """
        # 1. Convert session_path to Path object for robust path handling
        session_dir = Path(session_path)

        # 2. Construct path to packing_lists directory
        packing_lists_dir = session_dir / "packing_lists"

        # 3. Remove .json extension if present (for flexibility)
        clean_name = packing_list_name
        clean_name = clean_name.removesuffix('.json')

        # 4. Try to find the file with .json extension
        packing_list_file = packing_lists_dir / f"{clean_name}.json"

        # 5. Check if file exists
        if not packing_list_file.exists():
            error_msg = f"Packing list not found: {packing_list_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        logger.info(f"Loading packing list: {packing_list_file}")

        # 6. Load JSON data
        try:
            with open(packing_list_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in packing list {packing_list_file}: {e}"
            logger.exception(error_msg)
            raise

        # 7. Validate that 'orders' key exists
        if 'orders' not in data:
            error_msg = f"Packing list missing 'orders' key: {packing_list_file}"
            logger.error(error_msg)
            raise KeyError(error_msg)

        # 8. Log success with order count
        order_count = len(data.get('orders', []))
        total_orders = data.get('total_orders', order_count)
        logger.info(f"Loaded packing list '{clean_name}' with {order_count} orders (total_orders={total_orders})")

        # 9. Return data dictionary
        return data

    def get_packing_work_dir(self, session_path: str, packing_list_name: str) -> Path:
        """
        Get or create working directory for packing results.

        Creates a working directory structure for a specific packing list
        within the Shopify session. This directory will contain:
        - barcodes/: Generated barcode images and packing state
        - reports/: Completed packing reports

        Directory structure created:
            session_path/packing/{packing_list_name}/
                barcodes/
                reports/

        Args:
            session_path: Full path to Shopify session
                         (e.g., "\\\\server\\...\\Sessions\\CLIENT_M\\2025-11-10_1")
            packing_list_name: Name of packing list (without extension)
                              Extensions like .json or .xlsx will be removed

        Returns:
            Path: Working directory path
                  (e.g., ...\\Sessions\\CLIENT_M\\2025-11-10_1\\packing\\DHL_Orders\\)

        Example:
            work_dir = sm.get_packing_work_dir(
                "\\\\server\\...\\Sessions\\CLIENT_M\\2025-11-10_1",
                "DHL_Orders"
            )
            # Returns: ...\\Sessions\\CLIENT_M\\2025-11-10_1\\packing\\DHL_Orders\\

            barcodes_dir = work_dir / "barcodes"
            reports_dir = work_dir / "reports"
        """
        # 1. Convert session_path to Path object
        session_dir = Path(session_path)

        # 2. Remove .json/.xlsx extension from name if present
        clean_name = packing_list_name
        for ext in ['.json', '.xlsx', '.xls']:
            if clean_name.lower().endswith(ext):
                clean_name = clean_name[:-len(ext)]
                break

        # 3. Create packing/{clean_name}/ directory structure
        work_dir = session_dir / "packing" / clean_name
        work_dir.mkdir(parents=True, exist_ok=True)

        # 4. Create subdirectories
        barcodes_dir = work_dir / "barcodes"
        barcodes_dir.mkdir(exist_ok=True)

        reports_dir = work_dir / "reports"
        reports_dir.mkdir(exist_ok=True)

        # 5. Log directory creation
        logger.info(f"Created packing work directory: {work_dir}")
        logger.debug("Subdirectories: barcodes/, reports/")

        # 6. Return work directory path
        return work_dir

    def update_session_metadata(
        self,
        session_path: str,
        packing_list_name: str,
        status: str,
        completed_orders: list[str] | None = None,
    ):
        """
        Update Shopify session metadata with packing progress.

        Updates session_info.json with packing status for tracking.
        This is a non-critical operation - failures are logged but don't stop execution.

        Args:
            session_path: Path to Shopify session
            packing_list_name: Name of packing list
            status: Status ('in_progress', 'completed', 'paused')
            completed_orders: Order numbers packed in this session, if any.
                The Shopify tool reads these back for repeat-order detection.
                Merged with any already recorded, so resuming a session does
                not drop orders packed before the resume.
        """
        session_info_file = Path(session_path) / SESSION_INFO_FILE

        if not session_info_file.exists():
            logger.warning(f"session_info.json not found: {session_path}")
            return

        try:
            # The Shopify tool guards this same file with an exclusive lock on
            # the sidecar .lock (its SessionManager._locked_session_info). Take
            # the same lock: without it, its read-modify-write and ours can
            # interleave and silently drop one side's changes.
            lock_path = session_info_file.with_name(SESSION_INFO_FILE + ".lock")
            with open(lock_path, "a+") as lock_handle, locked_file(lock_handle):
                with open(session_info_file, 'r', encoding='utf-8') as f:
                    session_info = json.load(f)

                if 'packing_progress' not in session_info:
                    session_info['packing_progress'] = {}

                block = session_info['packing_progress'].setdefault(
                    packing_list_name, {'started_at': get_current_timestamp()}
                )
                block['status'] = status
                block['updated_at'] = get_current_timestamp()

                if completed_orders:
                    merged = list(block.get('completed_orders', []))
                    merged.extend(o for o in completed_orders if o not in merged)
                    block['completed_orders'] = merged

                atomic_write_json(
                    session_info_file, session_info, indent=2, ensure_ascii=False
                )

            logger.info(f"Updated session metadata: {packing_list_name} -> {status}")

        except Exception as e:
            logger.warning(f"Could not update session metadata: {e}")
