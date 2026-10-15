"""
Session Manager - the Packer's writes into a Shopify session folder.

Two jobs: make the work directory a packing list is packed in
(Sessions/CLIENT_X/<session>/packing/<list>/), and record each list's packing
progress in the session's session_info.json, which the Shopify tool reads.
"""

import json
import logging
from pathlib import Path

from shared.atomic_write import atomic_write_json
from shared.file_lock import locked_file
from shared.metadata_utils import get_current_timestamp

logger = logging.getLogger(__name__)

# The Shopify tool writes this file; the Packer adds `packing_progress` to it.
SESSION_INFO_FILE = "session_info.json"


class SessionManager:
    """Work directories and packing progress for one client's Shopify sessions."""

    def __init__(
        self,
        client_id: str,
        profile_manager,
        lock_manager,
        worker_id: str | None = None,
        worker_name: str | None = None
    ):
        """
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

        logger.info(f"SessionManager initialized for client {client_id} (Worker: {worker_name})")


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
            status: Status ('in_progress', 'paused', 'completed', 'incomplete')
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
