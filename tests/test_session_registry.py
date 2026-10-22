import json
import os
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


def test_stale_in_the_list_means_the_lock_can_be_taken(registry, tmp_path):
    """One threshold, the lock's: a row reads Stale exactly when Resume can
    take the session over (spec 2026-10-08 phase 4, section 5.5)."""
    entry, work_dir = _entry(tmp_path)
    _lock(work_dir, age_seconds=SessionLockManager.STALE_TIMEOUT + 10)
    assert registry._resolve_status(entry) == "stale"
    _lock(work_dir, age_seconds=SessionLockManager.STALE_TIMEOUT - 30)
    assert registry._resolve_status(entry) == "in_progress"


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


def test_two_packing_lists_in_one_shopify_session_are_two_entries(registry):
    """Entries are keyed session_id::packing_list_name, so each list of one
    Shopify session is its own Session Browser row with its own status."""
    _start(registry)
    _start(registry, packing_list_name="PostOne_Orders", work_dir="w2")
    registry.register_session_complete("M", "2026-09-24_1", "DHL_Orders",
                                       {"total_orders": 14, "completed_orders": 14})

    by_list = {e["packing_list_name"]: e for e in registry.get_sessions("M")}
    assert set(by_list) == {"DHL_Orders", "PostOne_Orders"}
    assert by_list["DHL_Orders"]["status"] == "completed"
    assert by_list["PostOne_Orders"]["status"] == "in_progress"
    assert by_list["PostOne_Orders"]["work_dir"] == "w2"


# ---------------------------------------------------------------------------
# build_from_scan / ensure_registry: the registry rebuilt from the Sessions tree
# ---------------------------------------------------------------------------

def _session_tree(profile_manager, session_id, lists, info=True):
    """Sessions/CLIENT_M/<session_id>/ with a packing list file per name in `lists`."""
    session_dir = profile_manager.get_sessions_root() / "CLIENT_M" / session_id
    (session_dir / "packing_lists").mkdir(parents=True, exist_ok=True)
    for name in lists:
        (session_dir / "packing_lists" / f"{name}.json").write_text(
            json.dumps({"list_name": name, "courier": "DHL", "orders": [{"order_number": "1"}]}),
            encoding="utf-8",
        )
    if info:
        (session_dir / "session_info.json").write_text(
            json.dumps({"pc_name": "PC-7"}), encoding="utf-8"
        )
    return session_dir


def _work_dir(session_dir, name, state=None, summary=None):
    work_dir = session_dir / "packing" / name
    work_dir.mkdir(parents=True, exist_ok=True)
    if state is not None:
        (work_dir / "packing_state.json").write_text(json.dumps(state), encoding="utf-8")
    if summary is not None:
        (work_dir / "session_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return work_dir


STATE = {"progress": {"total_orders": 2, "completed_orders": 1, "total_items": 2}}


def test_a_list_never_started_is_rebuilt_as_available(registry, profile_manager):
    _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    rebuilt = registry.build_from_scan("M")
    assert rebuilt["sessions"] == {}
    [available] = rebuilt["available_lists"].values()
    assert available["courier"] == "DHL"
    assert available["total_orders"] == 1


def test_a_finished_list_is_rebuilt_from_its_summary(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    _work_dir(session_dir, "DHL_Orders", summary={"total_orders": 2, "completed_orders": 2})
    [entry] = registry.build_from_scan("M")["sessions"].values()
    assert entry["status"] == "completed"


def test_a_list_ended_short_is_rebuilt_incomplete(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    _work_dir(session_dir, "DHL_Orders", summary={"total_orders": 2, "completed_orders": 1})
    [entry] = registry.build_from_scan("M")["sessions"].values()
    assert entry["status"] == "incomplete"


def test_a_list_left_open_without_a_lock_is_rebuilt_paused(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    _work_dir(session_dir, "DHL_Orders", state=STATE)
    [entry] = registry.build_from_scan("M")["sessions"].values()
    assert entry["status"] == "paused"
    assert entry["completed_orders"] == 1


def test_a_list_being_packed_is_rebuilt_in_progress(registry, profile_manager):
    """MainWindow locks the work folder (packing/<list>/.session.lock), not the session folder."""
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    work_dir = _work_dir(session_dir, "DHL_Orders", state=STATE)
    _lock(work_dir, age_seconds=10)
    [entry] = registry.build_from_scan("M")["sessions"].values()
    assert entry["status"] == "in_progress"


def test_a_corrupt_session_info_does_not_stop_the_rebuild(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"], info=False)
    (session_dir / "session_info.json").write_text("{not json", encoding="utf-8")
    _work_dir(session_dir, "DHL_Orders", state=STATE)
    _session_tree(profile_manager, "2026-10-02_1", ["DPD_Orders"])
    rebuilt = registry.build_from_scan("M")
    assert len(rebuilt["sessions"]) == 1
    assert len(rebuilt["available_lists"]) == 1


def test_ensure_registry_writes_the_rebuild_once(registry, profile_manager):
    _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    assert registry.registry_exists("M") is False
    assert registry.ensure_registry("M") is True
    assert registry.registry_exists("M") is True
    assert len(registry.get_available_lists("M")) == 1


def test_a_client_with_no_sessions_folder_rebuilds_empty(registry):
    rebuilt = registry.build_from_scan("NOBODY")
    assert rebuilt["sessions"] == {} and rebuilt["available_lists"] == {}


def test_pausing_a_finished_entry_leaves_it_finished(registry, tmp_path):
    session_dir = tmp_path / "2026-10-01_1"
    work_dir = session_dir / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    registry.register_session_start(
        client_id="M", session_id="2026-10-01_1", packing_list_name="DHL_Orders",
        worker_id=None, worker_name=None, pc_name="PC-1", total_orders=1, total_items=1,
        work_dir=str(work_dir), session_path=str(session_dir),
    )
    registry.register_session_complete(
        "M", "2026-10-01_1", "DHL_Orders", {"total_orders": 1, "completed_orders": 1}
    )
    registry.register_session_paused("M", "2026-10-01_1", "DHL_Orders")
    [entry] = registry.get_sessions("M")
    assert entry["status"] == "completed"


# ---------------------------------------------------------------------------
# refresh_available_lists: a regenerated or withdrawn list (spec section 8)
# ---------------------------------------------------------------------------

def _list_json(profile_manager, session_id="2026-10-01_1", name="L"):
    return profile_manager.get_sessions_root() / "CLIENT_M" / session_id / "packing_lists" / f"{name}.json"


def _write_list(path, total, created_at):
    path.write_text(json.dumps({"list_name": "L", "courier": "DHL", "created_at": created_at,
                                "total_orders": total}), encoding="utf-8")


def _bump_mtime(path, seconds=10):
    t = path.stat().st_mtime
    os.utime(path, (t + seconds, t + seconds))


def test_refresh_picks_up_a_regenerated_list(registry, profile_manager):
    _session_tree(profile_manager, "2026-10-01_1", ["L"])
    path = _list_json(profile_manager)
    _write_list(path, total=16, created_at="2026-10-01T09:00:00")
    assert registry.refresh_available_lists("M") == 1
    assert registry.get_available_lists("M")[0]["total_orders"] == 16

    _write_list(path, total=18, created_at="2026-10-01T10:00:00")
    _bump_mtime(path)
    assert registry.refresh_available_lists("M") == 1
    [entry] = registry.get_available_lists("M")
    assert entry["total_orders"] == 18
    assert entry["created_at"] == "2026-10-01T10:00:00"


def test_refresh_drops_a_withdrawn_list(registry, profile_manager):
    _session_tree(profile_manager, "2026-10-01_1", ["L"])
    registry.refresh_available_lists("M")
    path = _list_json(profile_manager)
    (path.parent / "withdrawn").mkdir()
    path.rename(path.parent / "withdrawn" / "L.json")
    registry.refresh_available_lists("M")
    assert registry.get_available_lists("M") == []


def test_refresh_leaves_a_started_list_alone(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["L"])
    _work_dir(session_dir, "L", state=STATE)
    registry.refresh_available_lists("M")
    [started] = registry.get_sessions("M")
    path = _list_json(profile_manager)
    _write_list(path, total=18, created_at="2026-10-01T10:00:00")
    _bump_mtime(path)
    registry.refresh_available_lists("M")
    assert registry.get_sessions("M") == [started]
    assert registry.get_available_lists("M") == []


def test_a_legacy_entry_without_mtime_is_reread_once(registry, profile_manager):
    _session_tree(profile_manager, "2026-10-01_1", ["L"])
    registry.refresh_available_lists("M")
    data = registry.read_registry("M")
    for entry in data["available_lists"].values():
        entry.pop("mtime", None)
    registry.write_registry("M", data)

    assert registry.refresh_available_lists("M") == 1
    [entry] = registry.get_available_lists("M")
    assert "mtime" in entry
    assert registry.refresh_available_lists("M") == 0


def test_an_unreadable_rewrite_keeps_the_old_entry(registry, profile_manager):
    _session_tree(profile_manager, "2026-10-01_1", ["L"])
    path = _list_json(profile_manager)
    _write_list(path, total=16, created_at="2026-10-01T09:00:00")
    registry.refresh_available_lists("M")
    path.write_text("{", encoding="utf-8")
    _bump_mtime(path)
    registry.refresh_available_lists("M")
    [entry] = registry.get_available_lists("M")
    assert entry["total_orders"] == 16
