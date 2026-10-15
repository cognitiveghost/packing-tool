"""What closing the window and ending a list leave on disk, including when a step fails."""

import json

from PySide6.QtGui import QCloseEvent
from test_end_session_status import ORDERS, _end_in_window

from packing_tool.session_lock_manager import SessionLockManager


def _open(window, session_factory, packer_logic_factory):
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    ok, msg, _info = window.lock_manager.acquire_lock("TESTCL", work_dir)
    assert ok, msg
    window.logic = logic
    window.current_client_id = "TESTCL"
    window.current_work_dir = str(work_dir)
    window.current_session_path = str(session_dir)
    window.current_packing_list = "DHL_Orders"
    window._start_heartbeat_timer()
    return session_dir, work_dir, logic


def test_closing_with_a_list_open_saves_it_and_frees_the_lock(
    main_window, session_factory, packer_logic_factory
):
    _session_dir, work_dir, logic = _open(main_window, session_factory, packer_logic_factory)
    logic.start_order_packing("ORD-1")
    logic.process_sku_scan("SKU-1")
    logic.clear_current_order()

    event = QCloseEvent()
    main_window.closeEvent(event)

    assert event.isAccepted()
    assert not (work_dir / SessionLockManager.LOCK_FILENAME).exists()
    assert not main_window.heartbeat_timer.isActive()
    state = json.loads((work_dir / "packing_state.json").read_text(encoding="utf-8"))
    assert [o["order_number"] for o in state["completed"]] == ["ORD-1"]


def test_a_failed_save_does_not_stop_the_lock_release_or_the_close(
    main_window, session_factory, packer_logic_factory, monkeypatch
):
    _session_dir, work_dir, logic = _open(main_window, session_factory, packer_logic_factory)

    def boom():
        raise OSError("share gone")

    monkeypatch.setattr(logic, "save_state", boom)
    event = QCloseEvent()
    main_window.closeEvent(event)

    assert event.isAccepted()
    assert not (work_dir / SessionLockManager.LOCK_FILENAME).exists()


def test_a_summary_that_cannot_be_built_still_leaves_a_minimal_one(
    main_window, session_factory, packer_logic_factory, monkeypatch
):
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)

    def boom(**_kwargs):
        raise ValueError("bad metadata")

    monkeypatch.setattr(logic, "save_session_summary", boom)
    _end_in_window(main_window, session_dir, work_dir, logic, monkeypatch)

    summary = json.loads((work_dir / "session_summary.json").read_text(encoding="utf-8"))
    assert summary["error"] == "bad metadata"
    assert summary["session_type"] == "shopify"


def test_ending_a_list_marks_its_registry_entry_from_the_summary(
    main_window, session_factory, packer_logic_factory, monkeypatch
):
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    main_window.registry_manager.register_session_start(
        client_id="TESTCL", session_id=session_dir.name, packing_list_name="DHL_Orders",
        worker_id=None, worker_name=None, pc_name="PC-1", total_orders=2, total_items=2,
        work_dir=str(work_dir), session_path=str(session_dir),
    )
    logic.start_order_packing("ORD-1")
    logic.process_sku_scan("SKU-1")
    logic.clear_current_order()

    _end_in_window(main_window, session_dir, work_dir, logic, monkeypatch)

    entries = main_window.registry_manager.get_sessions("TESTCL")
    entry = next(e for e in entries if e.get("packing_list_name") == "DHL_Orders")
    assert entry["status"] == "incomplete"
    assert entry["completed_orders"] == 1
