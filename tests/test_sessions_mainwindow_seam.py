"""MainWindow and the Sessions pages: the wiring, and the lock step of a start
(spec 2026-10-08 phase 4, sections 6 and 9)."""

import json
from datetime import datetime, timedelta

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS
from packing_tool.session_lock_manager import SessionLockManager

ORDERS = [("#1", "DHL", [{"sku": "A", "quantity": 1, "product_name": "A"}])]
STALE_SENTENCE = (
    "WH-PC-02 stopped responding while this list was open there. "
    "Resume it from Sessions to take it over."
)


def _stamp(**ago) -> str:
    return (datetime.now().astimezone() - timedelta(**ago)).isoformat()


def _lock(work_dir, *, age_seconds, pc="WH-PC-02", pid=1) -> dict:
    beat = _stamp(seconds=age_seconds)
    lock = {"locked_by": pc, "user_name": "georgi", "lock_time": beat, "heartbeat": beat,
            "process_id": pid, "worker_id": None, "worker_name": "Georgi"}
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(json.dumps(lock), encoding="utf-8")
    return lock


def _owner(work_dir) -> str:
    text = (work_dir / SessionLockManager.LOCK_FILENAME).read_text(encoding="utf-8")
    return json.loads(text)["locked_by"]


def _entry(session_id, status="paused", list_name="Afternoon_wave") -> dict:
    return {
        "session_id": session_id, "packing_list_name": list_name, "status": status,
        "worker_name": "Maria", "pc_name": "WH-PC-02",
        "started_at": _stamp(hours=3), "last_updated": _stamp(hours=1),
        "total_orders": 10, "completed_orders": 4, "skipped_orders": 0, "total_items": 20,
        "work_dir": "", "session_path": f"/srv/{session_id}", "metrics": None,
    }


def _resume_info(session_dir, work_dir, take_over=None) -> dict:
    return {
        "session_path": str(session_dir), "client_id": "TESTCL",
        "packing_list_name": "DHL_Orders", "work_dir": str(work_dir),
        "session_id": session_dir.name, "take_over": take_over,
    }


def _drain(window, qapp):
    """Let the refresh the client picker started finish and its answer land."""
    window.sessions.wait()
    qapp.processEvents()
    qapp.processEvents()


@pytest.fixture
def no_boxes(monkeypatch):
    """Every message box raised, by kind. A test asserts it stayed empty."""
    boxes = []
    for kind in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(
            QMessageBox, kind, lambda *a, _kind=kind, **k: boxes.append(_kind))
    return boxes


@pytest.fixture
def toasts(main_window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        main_window, "_toast", lambda message, role="success": seen.append(message))
    return seen


# --- the wiring (section 9) -------------------------------------------------------


def test_the_browser_widget_and_the_history_manager_are_gone(main_window):
    assert not hasattr(main_window, "session_browser")
    assert not hasattr(main_window, "session_history_manager")
    assert not hasattr(main_window, "_acquire_lock_with_stale_prompt")
    assert main_window.session_tabs.widget(PAGE_BROWSER) is main_window.session_tabs.view


def test_the_sessions_signals_reach_their_handlers(main_window, monkeypatch):
    called = []
    monkeypatch.setattr(main_window, "_handle_start_packing_from_browser",
                        lambda info: called.append(("start", info)))
    monkeypatch.setattr(main_window, "_handle_resume_session_from_browser",
                        lambda info: called.append(("resume", info)))
    main_window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    main_window.sessions.startRequested.emit({"a": 1})
    main_window.sessions.resumeRequested.emit({"b": 2})
    main_window.sessions.showPackingRequested.emit()
    assert called == [("start", {"a": 1}), ("resume", {"b": 2})]
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING


def test_showing_sessions_refreshes_it(main_window, monkeypatch):
    calls = []
    monkeypatch.setattr(main_window.sessions, "page_shown", lambda: calls.append(1))
    main_window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    assert calls == []
    main_window.session_tabs.setCurrentIndex(PAGE_BROWSER)
    assert calls == [1]
    assert main_window.session_tabs.bridge.page == "sessions"


def test_the_open_session_and_the_connection_reach_the_rows(main_window_with_list, qapp):
    window = main_window_with_list
    _drain(window, qapp)
    window.sessions.show_entries([
        _entry("2026-01-01_1", "in_progress", "DHL_Orders"),
        _entry("2026-01-02_1"),
    ])

    def rows():
        return {row["id"]: row for row in window.session_tabs.bridge.sessions["rows"]}

    # The fixture's list has no session folder yet: nothing is "open here".
    assert rows()["2026-01-02_1"]["enabled"] is True

    window.current_session_path = "/sessions/2026-01-01_1"
    window._push_pages()
    assert rows()["2026-01-01_1"]["action"] == "show"
    assert rows()["2026-01-02_1"]["enabled"] is False
    assert rows()["2026-01-02_1"]["note"] == (
        "2026-01-01_1 is open on this PC. End it before opening another.")

    window._teardown_session()
    assert rows()["2026-01-02_1"]["enabled"] is True

    window._set_connection_state("down")
    assert rows()["2026-01-02_1"]["note"].startswith("Server unreachable")
    window._set_connection_state("ok")
    assert rows()["2026-01-02_1"]["enabled"] is True


def test_closing_the_window_stops_the_sessions_timer(main_window):
    main_window.closeEvent(QCloseEvent())
    assert not main_window.sessions._timer.isActive()


# --- the lock step (section 6) -------------------------------------------------------


def test_a_free_list_is_locked(main_window, tmp_path):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    assert main_window._acquire_lock("TESTCL", work_dir) == (True, None, None)
    main_window.lock_manager.release_lock(work_dir)


def test_a_take_over_releases_that_stale_lock_and_takes_it(main_window, tmp_path):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    stale = _lock(work_dir, age_seconds=600)
    assert main_window._acquire_lock("TESTCL", work_dir, stale) == (True, None, "WH-PC-02")
    assert _owner(work_dir) == main_window.lock_manager.hostname
    main_window.lock_manager.release_lock(work_dir)


def test_a_stale_lock_nobody_was_asked_about_is_not_taken(main_window, tmp_path):
    """The list was behind, or this is a Retry of frame 3c: no question was
    answered, so nothing is released."""
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    _lock(work_dir, age_seconds=600)
    assert main_window._acquire_lock("TESTCL", work_dir) == (False, STALE_SENTENCE, None)
    assert _owner(work_dir) == "WH-PC-02"


def test_a_live_lock_is_refused_with_the_locks_own_message(main_window, tmp_path):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    live = _lock(work_dir, age_seconds=5)
    ok, message, taken_from = main_window._acquire_lock("TESTCL", work_dir, live)
    assert (ok, taken_from) == (False, None)
    assert "WH-PC-02" in message and message != STALE_SENTENCE
    assert _owner(work_dir) == "WH-PC-02"


def test_a_stale_lock_with_no_take_over_is_frame_3c(main_window, session_factory, no_boxes):
    session_dir, work_dir, _list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    _lock(work_dir, age_seconds=600)
    main_window._handle_resume_session_from_browser(_resume_info(session_dir, work_dir))
    session = main_window.session_tabs.bridge.session
    assert session["state"] == "failed"
    assert session["title"] == "Session could not be opened"
    assert session["text"] == STALE_SENTENCE
    assert _owner(work_dir) == "WH-PC-02"
    assert main_window.logic is None
    assert no_boxes == []


def test_a_take_over_of_a_lock_that_came_back_is_refused(
    main_window, session_factory, no_boxes
):
    """Review focus 5: the question (7c) was about a stale lock; its PC came
    back before the packer answered. Nothing is removed, nothing opens."""
    session_dir, work_dir, _list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    asked_about = _lock(work_dir, age_seconds=600)
    _lock(work_dir, age_seconds=1)
    main_window._handle_resume_session_from_browser(
        _resume_info(session_dir, work_dir, take_over=asked_about))
    session = main_window.session_tabs.bridge.session
    assert session["state"] == "failed"
    assert session["title"] == "Session could not be opened"
    assert "WH-PC-02" in session["text"]
    assert _owner(work_dir) == "WH-PC-02"
    assert main_window.logic is None
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING
    assert no_boxes == []


# --- a whole start: toasts, no message boxes ------------------------------------------


def test_a_resume_with_a_take_over_opens_the_session_and_says_so(
    main_window, session_factory, no_boxes, toasts
):
    session_dir, work_dir, _list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    stale = _lock(work_dir, age_seconds=600)
    try:
        main_window._handle_resume_session_from_browser(
            _resume_info(session_dir, work_dir, take_over=stale))
        assert main_window.session_tabs.bridge.session["state"] == "open"
        assert _owner(work_dir) == main_window.lock_manager.hostname
        assert toasts[0] == f"Took over {session_dir.name} from WH-PC-02."
        assert no_boxes == []
        assert main_window.session_tabs.currentIndex() == PAGE_PACKING
    finally:
        main_window._teardown_session()


def test_a_start_says_it_loaded_in_a_toast_and_no_box(
    main_window, session_factory, no_boxes, toasts
):
    session_dir, _work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    try:
        main_window._handle_start_packing_from_browser({
            "session_path": str(session_dir), "client_id": "TESTCL",
            "packing_list_name": "DHL_Orders", "list_file": str(list_path),
        })
        assert main_window.session_tabs.bridge.session["state"] == "open"
        assert toasts[0] == "Loaded 1 orders from DHL_Orders."
        assert no_boxes == []
    finally:
        main_window._teardown_session()


def test_a_start_with_a_session_open_is_a_toast(
    main_window_with_list, no_boxes, toasts, monkeypatch, tmp_path
):
    window = main_window_with_list
    window.current_session_path = "/sessions/2026-01-01_1"
    started = []
    monkeypatch.setattr(window, "start_shopify_packing_session",
                        lambda **kwargs: started.append(kwargs) or False)
    window._start_or_resume_from_browser(
        "TESTCL", "B", tmp_path, tmp_path / "B.json", work_dir=tmp_path / "B")
    assert started == []
    assert toasts == ["2026-01-01_1 is open. End it before opening another."]
    assert no_boxes == []
