import json
import threading
from datetime import datetime, timedelta

import pytest

from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_registry_manager import SessionRegistryManager
from shared.metadata_utils import get_current_timestamp


@pytest.fixture
def registry(profile_manager):
    return SessionRegistryManager(profile_manager)


def _entry(tmp_path, **over):
    session_path = tmp_path / "2026-09-24_1"
    work_dir = session_path / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True, exist_ok=True)
    entry = {"status": "in_progress", "last_updated": get_current_timestamp(),
             "session_path": str(session_path), "work_dir": str(work_dir)}
    entry.update(over)
    return entry, work_dir


def _lock(work_dir, age_seconds):
    beat = (datetime.now().astimezone() - timedelta(seconds=age_seconds)).isoformat()
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": "PC-1", "heartbeat": beat}), encoding="utf-8")


def test_a_live_session_reads_in_progress_from_its_work_dir_lock(registry, tmp_path):
    entry, work_dir = _entry(tmp_path)
    _lock(work_dir, age_seconds=10)
    assert registry._resolve_status(entry) == "in_progress"


def test_a_silent_lock_reads_stale(registry, tmp_path):
    entry, work_dir = _entry(tmp_path)
    _lock(work_dir, age_seconds=600)
    assert registry._resolve_status(entry) == "stale"


def test_no_lock_reads_paused(registry, tmp_path):
    entry, _work_dir = _entry(tmp_path)
    assert registry._resolve_status(entry) == "paused"


def _start(registry, **over):
    args = {"client_id": "M", "session_id": "2026-09-24_1", "packing_list_name": "DHL_Orders",
            "worker_id": None, "worker_name": None, "pc_name": "PC-1", "total_orders": 14,
            "total_items": 30, "work_dir": "w", "session_path": "s"}
    args.update(over)
    return registry.register_session_start(**args)


def test_resuming_keeps_the_start_and_carries_the_progress(registry):
    _start(registry)
    first = registry.get_sessions("M")[0]["started_at"]
    _start(registry, completed_orders=9, skipped_orders=1)
    entry = registry.get_sessions("M")[0]
    assert entry["started_at"] == first
    assert (entry["completed_orders"], entry["skipped_orders"]) == (9, 1)


def test_progress_moves_a_live_entry_and_leaves_a_finished_one(registry):
    _start(registry)
    assert registry.update_session_progress("M", "2026-09-24_1", "DHL_Orders", 3, 0) is True
    assert registry.get_sessions("M")[0]["completed_orders"] == 3
    registry.register_session_complete("M", "2026-09-24_1", "DHL_Orders",
                                       {"total_orders": 14, "completed_orders": 14})
    assert registry.update_session_progress("M", "2026-09-24_1", "DHL_Orders", 1, 0) is False
    assert registry.get_sessions("M")[0]["completed_orders"] == 14


def test_concurrent_writers_do_not_drop_each_others_entries(registry):
    """Spec D3. Without the lock this loses entries often but not always;
    with it, it never does."""
    def add(prefix):
        for i in range(15):
            registry.register_available_list("M", f"{prefix}-{i}", "DHL_Orders", "list.json", "s", {})

    threads = [threading.Thread(target=add, args=(p,)) for p in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(registry.get_available_lists("M")) == 30
