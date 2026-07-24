"""
Unified Statistics Manager for Shopify Tool and Packing Tool

This module provides a unified statistics tracking system that works identically
in both the Shopify Fulfillment Tool and Packing Tool. It manages centralized
statistics stored on the file server in Stats/global_stats.json.

Phase 1.4: Unified Statistics System
- Centralized storage on file server
- File locking for concurrent access from multiple PCs
- Separate tracking for analysis (Shopify) and packing operations
- Per-client statistics breakdown
- Thread-safe and process-safe operations

Usage:
    # In Shopify Tool
    stats_manager = StatsManager(base_path)
    stats_manager.record_analysis(
        client_id="M",
        session_id="2025-11-05_1",
        orders_count=150,
        metadata={...}
    )

    # In Packing Tool
    stats_manager = StatsManager(base_path)
    stats_manager.record_packing(
        client_id="M",
        session_id="2025-11-05_1",
        worker_id="001",
        orders_count=142,
        items_count=450,
        metadata={...}
    )
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from shared.file_lock import locked_file, FileLockError


class StatsManagerError(Exception):
    """Base exception for StatsManager errors."""
    pass


class StatsManager:
    """
    Unified statistics manager for both Shopify Tool and Packing Tool.

    Manages centralized statistics stored in Stats/global_stats.json on the
    file server. Provides thread-safe and process-safe operations using
    file locking.

    Structure of global_stats.json:
    {
        "total_orders_analyzed": 5420,      # From Shopify Tool
        "total_orders_packed": 4890,        # From Packing Tool
        "total_sessions": 312,
        "by_client": {
            "M": {
                "orders_analyzed": 2100,
                "orders_packed": 1950,
                "sessions": 145
            }
        },
        "analysis_history": [...],          # Shopify Tool records
        "packing_history": [...],           # Packing Tool records
        "last_updated": "2025-11-05T14:30:00"
    }

    Attributes:
        base_path (Path): Base path to 0UFulfilment directory
        stats_file (Path): Path to global_stats.json
        max_retries (int): Maximum number of retry attempts for file operations
        retry_delay (float): Delay in seconds between retries
    """

    def __init__(
        self,
        base_path: str,
        max_retries: int = 5,
        retry_delay: float = 0.1
    ):
        """
        Initialize the StatsManager.

        Args:
            base_path: Path to 0UFulfilment directory (e.g., \\\\server\\...\\0UFulfilment)
            max_retries: Maximum number of retry attempts for locked files
            retry_delay: Delay in seconds between retry attempts
        """
        self.base_path = Path(base_path)
        self.stats_file = self.base_path / "Stats" / "global_stats.json"
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Ensure Stats directory exists
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_default_stats(self) -> Dict[str, Any]:
        """
        Get default statistics structure.

        Returns:
            Dictionary with default statistics structure
        """
        from shared.metadata_utils import get_current_timestamp

        return {
            "total_orders_analyzed": 0,
            "total_orders_packed": 0,
            "total_sessions": 0,
            "by_client": {},
            "analysis_history": [],
            "packing_history": [],
            "last_updated": get_current_timestamp(),
            "version": "1.3.0"
        }

    def _load_stats(self) -> Dict[str, Any]:
        """
        Load statistics from file with file locking.

        Returns:
            Dictionary with statistics data

        Raises:
            StatsManagerError: If unable to load statistics after retries
        """
        if not self.stats_file.exists():
            return self._get_default_stats()

        for attempt in range(self.max_retries):
            try:
                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode, encoding='utf-8') as f:
                    with locked_file(f):
                        f.seek(0)
                        content = f.read()
                        if not content.strip():
                            return self._get_default_stats()

                        stats = json.loads(content)

                        # Validate structure
                        if not isinstance(stats, dict):
                            return self._get_default_stats()

                        # Ensure all required keys exist
                        default = self._get_default_stats()
                        for key in default:
                            if key not in stats:
                                stats[key] = default[key]

                        return stats

            except json.JSONDecodeError as e:
                # Corrupted JSON - return default stats without retrying
                return self._get_default_stats()
            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to load stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

        return self._get_default_stats()

    def _save_stats(self, stats: Dict[str, Any]) -> None:
        """
        Save statistics to file with file locking.

        Args:
            stats: Statistics dictionary to save

        Raises:
            StatsManagerError: If unable to save statistics after retries
        """
        from shared.metadata_utils import get_current_timestamp

        # Update timestamp
        stats["last_updated"] = get_current_timestamp()

        for attempt in range(self.max_retries):
            try:
                # Ensure directory exists
                self.stats_file.parent.mkdir(parents=True, exist_ok=True)

                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode, encoding='utf-8') as f:
                    with locked_file(f):
                        f.seek(0)
                        f.truncate()
                        json.dump(stats, f, indent=4, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())  # Ensure write to disk

                return

            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to save stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

    def _atomic_update(self, update_func) -> None:
        """
        Perform an atomic update of statistics.

        Args:
            update_func: Function that takes stats dict and modifies it
        """
        for attempt in range(self.max_retries):
            try:
                # Ensure file exists
                if not self.stats_file.exists():
                    self.stats_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.stats_file, 'w', encoding='utf-8') as f:
                        json.dump(self._get_default_stats(), f, indent=4)

                # Open file and hold lock for entire operation
                with open(self.stats_file, 'r+', encoding='utf-8') as f:
                    with locked_file(f):
                        # Load
                        f.seek(0)
                        content = f.read()
                        if content.strip():
                            try:
                                stats = json.loads(content)
                            except json.JSONDecodeError:
                                stats = self._get_default_stats()
                        else:
                            stats = self._get_default_stats()

                        # Validate and ensure structure
                        if not isinstance(stats, dict):
                            stats = self._get_default_stats()

                        default = self._get_default_stats()
                        for key in default:
                            if key not in stats:
                                stats[key] = default[key]

                        # Modify (call user function)
                        update_func(stats)

                        # Update timestamp
                        from shared.metadata_utils import get_current_timestamp
                        stats["last_updated"] = get_current_timestamp()

                        # Save
                        f.seek(0)
                        f.truncate()
                        json.dump(stats, f, indent=4, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())

                return  # Success

            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to update stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

    def record_packing(
        self,
        client_id: str,
        session_id: str,
        worker_id: Optional[str],
        orders_count: int,
        items_count: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a packing session completion from Packing Tool.

        Args:
            client_id: Client identifier (e.g., "M", "A", "B")
            session_id: Session identifier (e.g., "2025-11-05_1")
            worker_id: Worker identifier (e.g., "001", "002")
            orders_count: Number of orders packed
            items_count: Number of items packed
            metadata: Optional additional metadata (e.g., duration, start_time, end_time)

        Example:
            stats_manager.record_packing(
                client_id="M",
                session_id="2025-11-05_1",
                worker_id="001",
                orders_count=142,
                items_count=450,
                metadata={
                    "start_time": "2025-11-05T10:00:00",
                    "end_time": "2025-11-05T12:30:00",
                    "duration_seconds": 9000
                }
            )
        """
        def update(stats):
            # Update global counters
            stats["total_orders_packed"] += orders_count
            stats["total_sessions"] += 1

            # Update client stats
            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0
                }

            stats["by_client"][client_id]["orders_packed"] += orders_count
            stats["by_client"][client_id]["sessions"] += 1

            # Add to packing history
            from shared.metadata_utils import get_current_timestamp

            record = {
                "timestamp": get_current_timestamp(),
                "client_id": client_id,
                "session_id": session_id,
                "worker_id": worker_id,
                "orders_count": orders_count,
                "items_count": items_count,
            }

            if metadata:
                record["metadata"] = metadata

            stats["packing_history"].append(record)

            # Keep only last 1000 records to prevent file bloat
            if len(stats["packing_history"]) > 1000:
                stats["packing_history"] = stats["packing_history"][-1000:]

        self._atomic_update(update)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        manager = StatsManager(tmp)
        manager.record_packing(
            client_id="M",
            session_id="2025-11-05_1",
            worker_id="001",
            orders_count=142,
            items_count=450,
            metadata={"duration_seconds": 9000}
        )
        stats = manager._load_stats()
        assert stats["total_orders_packed"] == 142
        assert stats["by_client"]["M"]["sessions"] == 1
        print("stats_manager self-check OK")
