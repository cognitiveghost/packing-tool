"""
Worker Profile Management

Handles worker profiles stored on file server.
Simple trust-based system without authentication.
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from shared.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)


@dataclass
class WorkerProfile:
    """Worker profile data structure (v1.3.0)"""
    # Basic info
    id: str                    # e.g., "worker_001"
    name: str                  # Display name
    created_at: str           # ISO timestamp with timezone

    # Aggregate counters
    total_sessions: int = 0
    total_orders: int = 0
    total_items: int = 0
    total_duration_seconds: int = 0

    # Calculated metrics (automatically updated)
    avg_time_per_order: float = 0.0        # Average seconds per order
    avg_orders_per_session: float = 0.0    # Average orders per session

    # Activity tracking
    last_active: str | None = None      # ISO timestamp with timezone
    last_session_id: str | None = None  # Last completed session

    # Metadata
    version: str = "1.3.0"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkerProfile':
        """Create from dictionary with backward compatibility"""
        # Provide defaults for new fields
        defaults = {
            'total_duration_seconds': 0,
            'avg_time_per_order': 0.0,
            'avg_orders_per_session': 0.0,
            'last_session_id': None,
            'version': '1.3.0'
        }

        # Merge data with defaults
        merged_data = {**defaults, **data}

        return cls(**merged_data)

    def recalculate_averages(self):
        """Recalculate derived metrics from aggregate counters"""
        # Calculate average time per order
        if self.total_orders > 0 and self.total_duration_seconds > 0:
            self.avg_time_per_order = round(
                self.total_duration_seconds / self.total_orders,
                1
            )
        else:
            self.avg_time_per_order = 0.0

        # Calculate average orders per session
        if self.total_sessions > 0:
            self.avg_orders_per_session = round(
                self.total_orders / self.total_sessions,
                1
            )
        else:
            self.avg_orders_per_session = 0.0


class WorkerManager:
    r"""Manage worker profiles

    Storage structure:
        \\server\...\Workers\
        └── workers.json  (registry of all workers)
    """

    def __init__(self, base_path: str):
        """Initialize WorkerManager

        Args:
            base_path: Base path to warehouse fulfillment folder
                      e.g., \\\\server\\...\\0UFulfilment
        """
        self.base_path = Path(base_path)
        self.workers_dir = self.base_path / "Workers"
        self.workers_file = self.workers_dir / "workers.json"

        # Create directory if doesn't exist
        self._ensure_workers_directory()

        logger.info(f"WorkerManager initialized: {self.workers_dir}")

    def _ensure_workers_directory(self):
        """Create Workers directory if doesn't exist"""
        try:
            self.workers_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Workers directory ready: {self.workers_dir}")
        except Exception:
            logger.exception("Failed to create Workers directory")
            raise

    def _load_workers_registry(self) -> dict[str, list]:
        """Load workers.json registry

        Returns:
            dict: {"workers": [list of worker dicts]}
        """
        if not self.workers_file.exists():
            # Initialize empty registry
            return {"workers": []}

        try:
            with open(self.workers_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.debug(f"Loaded {len(data.get('workers', []))} workers from registry")
            return data

        except json.JSONDecodeError:
            logger.exception("Corrupted workers.json")
            # Backup corrupted file
            backup_path = self.workers_file.with_suffix('.json.backup')
            self.workers_file.rename(backup_path)
            logger.warning(f"Corrupted file backed up to: {backup_path}")
            return {"workers": []}

        except Exception:
            logger.exception("Failed to load workers registry")
            raise

    def _save_workers_registry(self, data: dict[str, list]):
        """Save workers.json registry with version

        Args:
            data: {"workers": [list of worker dicts], "version": "1.3.0"}
        """
        try:
            # Add version to root level
            data['version'] = "1.3.0"

            atomic_write_json(self.workers_file, data, indent=2, ensure_ascii=False)

            logger.debug(f"Saved {len(data['workers'])} workers to registry (v1.3.0)")

        except Exception:
            logger.exception("Failed to save workers registry")
            raise

    def get_all_workers(self) -> list[WorkerProfile]:
        """Get all worker profiles

        Returns:
            List[WorkerProfile]: List of all workers
        """
        data = self._load_workers_registry()
        workers = [WorkerProfile.from_dict(w) for w in data.get('workers', [])]

        logger.info(f"Retrieved {len(workers)} worker profiles")
        return workers

    def get_worker(self, worker_id: str) -> WorkerProfile | None:
        """Get specific worker profile

        Args:
            worker_id: Worker ID (e.g., "worker_001")

        Returns:
            WorkerProfile if found, None otherwise
        """
        workers = self.get_all_workers()

        for worker in workers:
            if worker.id == worker_id:
                return worker

        logger.warning(f"Worker not found: {worker_id}")
        return None

    def create_worker(self, name: str) -> WorkerProfile:
        """Create new worker profile

        Args:
            name: Display name for worker

        Returns:
            WorkerProfile: Newly created worker

        Raises:
            ValueError: If name already exists
        """
        # Validate name
        if not name or not name.strip():
            raise ValueError("Worker name cannot be empty")

        name = name.strip()

        # Check for duplicate names
        existing = self.get_all_workers()
        if any(w.name.lower() == name.lower() for w in existing):
            raise ValueError(f"Worker with name '{name}' already exists")

        # Generate new ID
        worker_id = self._generate_worker_id(existing)

        # Create profile
        from shared.metadata_utils import get_current_timestamp

        worker = WorkerProfile(
            id=worker_id,
            name=name,
            created_at=get_current_timestamp(),
            total_sessions=0,
            total_orders=0,
            total_items=0,
            total_duration_seconds=0,
            avg_time_per_order=0.0,
            avg_orders_per_session=0.0,
            last_active=None,
            last_session_id=None,
            version="1.3.0"
        )

        # Save to registry
        data = self._load_workers_registry()
        data['workers'].append(worker.to_dict())
        self._save_workers_registry(data)

        logger.info(f"Created worker: {worker_id} ({name})")
        return worker

    def _generate_worker_id(self, existing_workers: list[WorkerProfile]) -> str:
        """Generate unique worker ID

        Args:
            existing_workers: List of existing workers

        Returns:
            str: New worker ID (e.g., "worker_003")
        """
        # Find highest existing ID number
        max_num = 0
        for worker in existing_workers:
            if worker.id.startswith("worker_"):
                try:
                    num = int(worker.id.split("_")[1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError):
                    continue

        # Generate next ID
        new_id = f"worker_{max_num + 1:03d}"
        return new_id

    def update_worker_stats(
        self,
        worker_id: str,
        sessions: int = 0,
        orders: int = 0,
        items: int = 0,
        duration_seconds: int = 0,
        session_id: str | None = None
    ):
        """Update worker statistics (incremental)

        Args:
            worker_id: Worker ID
            sessions: Number of sessions to add
            orders: Number of orders to add
            items: Number of items to add
            duration_seconds: Duration in seconds to add (new in v1.3.0)
            session_id: Last completed session ID (new in v1.3.0)
        """
        from shared.metadata_utils import get_current_timestamp

        data = self._load_workers_registry()
        workers = data.get('workers', [])

        for worker_dict in workers:
            if worker_dict['id'] == worker_id:
                # Increment aggregate counters
                worker_dict['total_sessions'] = worker_dict.get('total_sessions', 0) + sessions
                worker_dict['total_orders'] = worker_dict.get('total_orders', 0) + orders
                worker_dict['total_items'] = worker_dict.get('total_items', 0) + items
                worker_dict['total_duration_seconds'] = worker_dict.get('total_duration_seconds', 0) + duration_seconds

                # Update activity tracking
                worker_dict['last_active'] = get_current_timestamp()
                if session_id:
                    worker_dict['last_session_id'] = session_id

                # Ensure version field exists
                worker_dict['version'] = "1.3.0"

                # Recalculate averages using WorkerProfile
                worker = WorkerProfile.from_dict(worker_dict)
                worker.recalculate_averages()

                # Update dict with recalculated values
                worker_dict.update(worker.to_dict())

                # Save
                self._save_workers_registry(data)

                logger.info(
                    f"Updated stats for {worker_id}: "
                    f"+{sessions} sessions, +{orders} orders, +{items} items, "
                    f"+{duration_seconds}s duration (avg {worker.avg_time_per_order}s/order)"
                )
                return

        logger.warning(f"Worker not found for stats update: {worker_id}")

