"""
Session History Manager - Manages historical session data and analytics.

This module provides functionality to retrieve, analyze, and search through
completed packing sessions, enabling historical reporting and analytics.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

import logging
from json_cache import get_cached_json

logger = logging.getLogger(__name__)


@dataclass
class SessionHistoryRecord:
    """
    Represents a historical session record with all relevant metrics.

    Attributes:
        session_id: Unique session identifier (timestamp-based directory name)
        client_id: Client identifier
        start_time: Session start timestamp
        end_time: Session end timestamp (if available)
        duration_seconds: Total session duration in seconds
        total_orders: Total number of orders in the session
        completed_orders: Number of completed orders
        in_progress_orders: Number of in-progress orders
        total_items_packed: Total number of items packed
        worker_id: Worker ID who completed the session (e.g., "worker_001")
        worker_name: Worker display name (e.g., "Dolphin")
        pc_name: Computer name where session was executed
        packing_list_path: Original packing list file path
        session_path: Full path to session directory
    """
    session_id: str
    client_id: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    duration_seconds: Optional[float]
    total_orders: int
    completed_orders: int
    in_progress_orders: int
    total_items_packed: int
    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    pc_name: Optional[str] = None
    packing_list_path: Optional[str] = None
    session_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with datetime objects as ISO strings."""
        data = asdict(self)
        if self.start_time:
            data['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()
        return data


class SessionHistoryManager:
    """
    Manages historical session data retrieval and analytics.

    This class provides methods to scan session directories, extract metrics
    from completed sessions, and generate analytics reports for clients.
    """

    def __init__(self, profile_manager):
        """
        Initialize SessionHistoryManager.

        Args:
            profile_manager: ProfileManager instance for accessing session paths
        """
        self.profile_manager = profile_manager
        logger.info("SessionHistoryManager initialized")

    def _parse_session_directory(
        self,
        client_id: str,
        session_dir: Path
    ) -> List[SessionHistoryRecord]:
        """
        Parse a session directory and extract metrics for all packing lists.

        Supports both:
        - Phase 1 (Shopify): packing/*/packing_state.json (multiple lists)
        - Legacy (Excel): barcodes/packing_state.json (single list)

        Args:
            client_id: Client identifier
            session_dir: Path to session directory

        Returns:
            List of SessionHistoryRecord objects (one per packing list), or empty list if parsing fails
        """
        session_id = session_dir.name
        records = []

        # ========================================
        # PHASE 1 (Shopify) - Try first
        # ========================================
        packing_dir = session_dir / "packing"
        if packing_dir.exists() and packing_dir.is_dir():
            logger.debug(f"Found packing/ directory in {session_id}, checking for Phase 1 data")

            # Iterate through all packing list work directories
            for work_dir in packing_dir.iterdir():
                if not work_dir.is_dir():
                    continue

                logger.debug(f"Checking work directory: {work_dir.name}")

                # Check for session_summary.json (completed session)
                summary_file = work_dir / "session_summary.json"
                if summary_file.exists():
                    logger.info(f"Found session_summary.json in {session_id}/{work_dir.name}")
                    record = self._parse_session_summary(client_id, session_dir, summary_file)
                    if record:
                        records.append(record)
                    continue  # Continue to next work_dir instead of returning

                # Check for packing_state.json (in-progress or completed)
                state_file = work_dir / "packing_state.json"
                if state_file.exists():
                    logger.info(f"Found packing_state.json in {session_id}/{work_dir.name}")
                    record = self._parse_packing_state(client_id, session_dir, state_file)
                    if record:
                        records.append(record)
                    continue  # Continue to next work_dir instead of returning

            if records:
                logger.info(f"Found {len(records)} packing list(s) in Phase 1 structure for {session_id}")
                return records

            logger.debug(f"No packing data found in Phase 1 structure for {session_id}")

        # ========================================
        # LEGACY (Excel) - Fallback
        # ========================================
        # Check barcodes/packing_state.json
        state_file = session_dir / "barcodes" / "packing_state.json"
        if state_file.exists():
            logger.info(f"Found Legacy Excel packing_state.json in {session_id}")
            record = self._parse_packing_state(client_id, session_dir, state_file)
            if record:
                return [record]

        # Check barcodes/session_summary.json (if exists)
        summary_file = session_dir / "barcodes" / "session_summary.json"
        if summary_file.exists():
            logger.info(f"Found Legacy Excel session_summary.json in {session_id}")
            record = self._parse_session_summary(client_id, session_dir, summary_file)
            if record:
                return [record]

        # ========================================
        # NO PACKING DATA FOUND
        # ========================================
        logger.info(f"No packing data found for session {session_id} - session will be skipped")
        return []

    def _parse_session_summary(
        self,
        client_id: str,
        session_dir: Path,
        summary_file: Path
    ) -> Optional[SessionHistoryRecord]:
        """
        Parse session_summary.json for completed sessions (v1.3.0 format only).

        Args:
            client_id: Client identifier
            session_dir: Path to session directory
            summary_file: Path to session_summary.json file

        Returns:
            SessionHistoryRecord or None if parsing fails
        """
        from shared.metadata_utils import load_session_summary, parse_timestamp

        session_id = session_dir.name

        try:
            # Load v1.3.0 format
            summary = load_session_summary(summary_file)

            # Parse timestamps using utility function
            start_time = parse_timestamp(summary.get('started_at', ''))
            end_time = parse_timestamp(summary.get('completed_at', ''))

            # Get duration
            duration_seconds = summary.get('duration_seconds')
            if duration_seconds is None and start_time and end_time:
                duration_seconds = (end_time - start_time).total_seconds()

            # Map v1.3.0 format to SessionHistoryRecord
            return SessionHistoryRecord(
                session_id=session_id,
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                total_orders=summary.get('total_orders', 0),
                completed_orders=summary.get('completed_orders', 0),
                in_progress_orders=0,  # No longer tracked in v1.3.0
                total_items_packed=summary.get('total_items', 0),
                worker_id=summary.get('worker_id'),
                worker_name=summary.get('worker_name'),
                pc_name=summary.get('pc_name', ''),
                packing_list_path=summary.get('packing_list_name', ''),
                session_path=str(session_dir)
            )

        except Exception as e:
            logger.error(f"Error parsing session summary {session_id}: {e}", exc_info=True)
            return None

    def _parse_packing_state(
        self,
        client_id: str,
        session_dir: Path,
        state_file: Path
    ) -> Optional[SessionHistoryRecord]:
        """
        Parse packing_state.json for in-progress or completed sessions.

        Args:
            client_id: Client identifier
            session_dir: Path to session directory
            state_file: Path to packing_state.json file

        Returns:
            SessionHistoryRecord or None if parsing fails
        """
        session_id = session_dir.name

        try:
            # OPTIMIZED: Load packing state with JSON caching
            # When scanning 100+ sessions, this reduces I/O from seconds to milliseconds
            packing_state = get_cached_json(state_file, default=None)

            if packing_state is None:
                # File exists but couldn't be parsed
                logger.warning(f"Invalid or empty packing state: {state_file}")
                return None

            # Extract session info if available
            session_info = self._load_session_info(session_dir)

            # Parse session ID to extract timestamp
            start_time = self._parse_session_timestamp(session_id)

            # Calculate metrics from packing state
            data = packing_state.get('data', {})
            in_progress = data.get('in_progress', {})
            completed = data.get('completed_orders', [])

            total_orders = len(in_progress) + len(completed)
            completed_orders = len(completed)
            in_progress_orders = len(in_progress)

            # Count total items packed
            total_items_packed = self._count_packed_items(in_progress, completed)

            # Try to determine end time from state timestamp or file modification time
            end_time = None
            duration_seconds = None

            state_timestamp = packing_state.get('timestamp')
            if state_timestamp:
                try:
                    from shared.metadata_utils import parse_timestamp
                    end_time = parse_timestamp(state_timestamp)
                    if start_time and end_time:
                        duration_seconds = (end_time - start_time).total_seconds()
                except (ValueError, TypeError):
                    pass

            # If no end time from state, use file modification time
            if not end_time:
                try:
                    from datetime import timezone
                    mtime = state_file.stat().st_mtime
                    end_time = datetime.fromtimestamp(mtime, tz=timezone.utc)
                    if start_time:
                        duration_seconds = (end_time - start_time).total_seconds()
                except Exception:
                    pass

            # Extract session info details
            pc_name = session_info.get('pc_name') if session_info else None
            packing_list_path = session_info.get('packing_list_path') if session_info else None

            # Try to extract worker info from packing_state (v1.3.0+)
            worker_id = packing_state.get('worker_id')
            worker_name = packing_state.get('worker_name')

            return SessionHistoryRecord(
                session_id=session_id,
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                total_orders=total_orders,
                completed_orders=completed_orders,
                in_progress_orders=in_progress_orders,
                total_items_packed=total_items_packed,
                worker_id=worker_id,
                worker_name=worker_name,
                pc_name=pc_name,
                packing_list_path=packing_list_path,
                session_path=str(session_dir)
            )

        except Exception as e:
            logger.error(f"Error parsing packing_state.json for {session_id}: {e}", exc_info=True)
            return None

    def _load_session_info(self, session_dir: Path) -> Optional[Dict[str, Any]]:
        """Load session_info.json if it exists."""
        info_file = session_dir / "session_info.json"
        if info_file.exists():
            try:
                # OPTIMIZED: Use JSON cache for session_info.json
                # This file is read repeatedly when scanning sessions
                return get_cached_json(info_file, default=None)
            except Exception as e:
                logger.warning(f"Error reading session_info.json: {e}")
        return None

    def _parse_session_timestamp(self, session_id: str) -> Optional[datetime]:
        """
        Parse timestamp from session ID.

        Session IDs are typically in format: YYYYMMDD_HHMMSS
        Returns timezone-aware datetime (UTC).
        """
        from datetime import timezone
        try:
            # Try standard format: YYYYMMDD_HHMMSS
            dt = datetime.strptime(session_id, "%Y%m%d_%H%M%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                # Try alternative formats
                dt = datetime.strptime(session_id, "%Y%m%d-%H%M%S")
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.debug(f"Could not parse timestamp from session ID: {session_id}")
                return None

    def _count_packed_items(
        self,
        in_progress: Dict[str, Any],
        completed: List[str]
    ) -> int:
        """
        Count total items packed across all orders.

        Args:
            in_progress: Dictionary of in-progress orders
            completed: List of completed order IDs

        Returns:
            Total count of packed items
        """
        total = 0

        # Count items in in-progress orders
        for order_data in in_progress.values():
            for sku_data in order_data.values():
                if isinstance(sku_data, dict) and 'packed' in sku_data:
                    total += sku_data['packed']

        # For completed orders, we assume all items are packed
        # This is an approximation since we don't store required counts separately
        # In a real scenario, you might want to store this differently

        return total

    def get_session_details(
        self,
        client_id: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific session.

        Supports both Phase 1 (Shopify) and Legacy (Excel) structures.

        Args:
            client_id: Client identifier
            session_id: Session identifier

        Returns:
            Dictionary with detailed session information including packing state
        """
        try:
            session_dir = self.profile_manager.get_sessions_root() / f"CLIENT_{client_id}" / session_id

            if not session_dir.exists():
                logger.warning(f"Session directory not found: {session_dir}")
                return None

            # Find packing state file (supports both Phase 1 and Legacy structures)
            state_file = None

            # Try Phase 1 structure first
            packing_dir = session_dir / "packing"
            if packing_dir.exists() and packing_dir.is_dir():
                for work_dir in packing_dir.iterdir():
                    if work_dir.is_dir():
                        candidate = work_dir / "packing_state.json"
                        if candidate.exists():
                            state_file = candidate
                            break

            # Fallback to Legacy structure
            if not state_file:
                candidate = session_dir / "barcodes" / "packing_state.json"
                if candidate.exists():
                    state_file = candidate

            if not state_file:
                logger.warning(f"No packing_state.json found for session {session_id}")
                return None

            # OPTIMIZED: Use JSON cache for packing state
            packing_state = get_cached_json(state_file, default=None)
            if packing_state is None:
                logger.warning(f"Failed to load packing state: {state_file}")
                return None

            # Load session info
            session_info = self._load_session_info(session_dir)

            # Load session summary if exists (Phase 2b data)
            session_summary = {}
            work_dir_path = state_file.parent  # work_dir containing packing_state.json
            summary_file = work_dir_path / "session_summary.json"
            if summary_file.exists():
                try:
                    from shared.metadata_utils import load_session_summary
                    session_summary = load_session_summary(summary_file)
                    logger.info(f"Loaded session_summary.json for session {session_id} with {len(session_summary.get('orders', []))} orders")
                except Exception as e:
                    logger.warning(f"Failed to load session_summary.json: {e}")

            # Get session records (may be multiple for multi-list sessions)
            records = self._parse_session_directory(client_id, session_dir)

            # For backward compatibility, return the first record
            # TODO: Future enhancement - support selecting specific packing list
            record = records[0] if records else None

            return {
                'record': record.to_dict() if record else None,
                'packing_state': packing_state,
                'session_info': session_info,
                'session_summary': session_summary
            }

        except Exception as e:
            logger.error(f"Error getting session details: {e}")
            return None
