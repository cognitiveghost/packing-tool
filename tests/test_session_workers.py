"""The two workers behind the Sessions pages (gui/workers.py)."""

import json

from gui.workers import RegistryRefreshWorker, SessionDetailsWorker
from packing_tool.session_registry_manager import SessionRegistryManager


def test_a_refresh_returns_the_clients_entries(qtbot, profile_manager, server_root):
    (server_root / "Sessions" / "CLIENT_TEST").mkdir(parents=True)
    worker = RegistryRefreshWorker(SessionRegistryManager(profile_manager), "TEST")
    with qtbot.waitSignal(worker.refresh_complete, timeout=10000) as caught:
        worker.start()
    worker.wait(10000)
    assert caught.args == ["TEST", []]


def test_a_refresh_with_the_server_away_fails_with_the_cause(qtbot, profile_manager):
    """read_registry answers an unreachable server with an empty registry, so
    the list said "No sessions yet" during an outage."""
    profile_manager.base_path = profile_manager.base_path / "gone"
    worker = RegistryRefreshWorker(SessionRegistryManager(profile_manager), "TEST")
    with qtbot.waitSignal(worker.refresh_failed, timeout=10000) as caught:
        worker.start()
    worker.wait(10000)
    assert caught.args[0] == "TEST"
    assert caught.args[1]  # the OS's own words


def test_details_are_loaded_off_the_ui_thread(qtbot, tmp_path):
    work_dir = tmp_path / "2026-09-29_1" / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    (work_dir / "session_summary.json").write_text(
        json.dumps({"session_id": "2026-09-29_1", "total_orders": 3}), encoding="utf-8"
    )
    entry = {"session_id": "2026-09-29_1", "packing_list_name": "DHL_Orders", "work_dir": str(work_dir)}
    worker = SessionDetailsWorker("2026-09-29_1|DHL_Orders", entry)
    with qtbot.waitSignal(worker.loaded, timeout=10000) as caught:
        worker.start()
    worker.wait(10000)
    key, details = caught.args
    assert key == "2026-09-29_1|DHL_Orders"
    assert details["record"]["total_orders"] == 3


def test_details_that_cannot_be_read_report_the_file(qtbot, tmp_path):
    work_dir = tmp_path / "2026-09-29_1" / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    (work_dir / "packing_state.json").write_text("{", encoding="utf-8")
    entry = {"session_id": "2026-09-29_1", "packing_list_name": "DHL_Orders", "work_dir": str(work_dir)}
    worker = SessionDetailsWorker("k", entry)
    with qtbot.waitSignal(worker.failed, timeout=10000) as caught:
        worker.start()
    worker.wait(10000)
    key, path, cause = caught.args
    assert key == "k"
    assert path.endswith("packing_state.json")
    assert "not valid JSON" in cause
