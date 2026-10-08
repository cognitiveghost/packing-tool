"""Spec B3: a PC whose lock another PC took must stop writing and leave the
session without end_session()'s writes, which would stamp the other PC's
live session as ended."""

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer

from packing_tool.session_lock_manager import SessionLockManager


class LockLossLogic:
    def __init__(self):
        self.stopped = False
        self.cleaned = False

    def stop_writing(self):
        self.stopped = True

    def end_session_cleanup(self):
        self.cleaned = True


def _heartbeat(main_window):
    """One heartbeat tick as the thread and its queued signal run it, inline."""
    work_dir = main_window.current_work_dir
    if main_window._renew_lock(Path(work_dir)):
        main_window._on_heartbeat_lost(work_dir)


def test_a_lost_lock_stops_writing_and_tears_down_without_ending(main_window, tmp_path, monkeypatch):
    work_dir = tmp_path / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    now = datetime.now().astimezone().isoformat()
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": "PC-2", "user_name": "x", "lock_time": now,
                    "heartbeat": now, "process_id": 1}),
        encoding="utf-8",
    )
    logic = LockLossLogic()
    main_window.logic = logic
    main_window.current_work_dir = str(work_dir)
    main_window.current_packing_list = "DHL_Orders"

    ended, shown = [], []
    monkeypatch.setattr(main_window, "end_session", lambda: ended.append(True))
    monkeypatch.setattr(
        "gui.main_window.QMessageBox.critical",
        lambda _parent, title, text: shown.append((title, text)),
    )

    _heartbeat(main_window)

    assert logic.stopped and logic.cleaned
    assert main_window.logic is None
    assert ended == []
    assert shown[0][0] == "This list is open on another PC"
    assert "PC-2 has taken over DHL_Orders." in shown[0][1]
    assert (work_dir / SessionLockManager.LOCK_FILENAME).exists()  # not ours to delete


def test_an_unreachable_share_at_a_heartbeat_keeps_the_session(main_window, tmp_path, monkeypatch):
    # The share drops mid-session: the lock reads as missing. That is an outage,
    # not another PC's takeover, so the pending save must still get its retry.
    logic = LockLossLogic()
    main_window.logic = logic
    main_window.current_work_dir = str(tmp_path / "unreachable" / "DHL_Orders")
    monkeypatch.setattr("gui.main_window.QMessageBox.critical", lambda *a: None)

    _heartbeat(main_window)

    assert main_window.logic is logic
    assert not logic.stopped


def test_a_lost_lock_in_packer_mode_shows_the_panel_and_waits_for_exit(
    main_window, tmp_path, monkeypatch
):
    """Frame 6j. Writing stops at once; the session is torn down when the
    packer exits, not under them."""
    work_dir = tmp_path / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    now = datetime.now().astimezone().isoformat()
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": "PC-2", "user_name": "x", "lock_time": now,
                    "heartbeat": now, "process_id": 1}),
        encoding="utf-8",
    )
    logic = LockLossLogic()
    logic.clear_current_order = lambda: None
    main_window.logic = logic
    main_window.current_work_dir = str(work_dir)
    main_window.current_packing_list = "DHL_Orders"
    widget = main_window.packer_mode_widget
    main_window.stacked_widget.setCurrentWidget(widget)
    main_window.heartbeat_timer = QTimer(main_window)
    main_window.heartbeat_timer.start(60000)

    shown = []
    monkeypatch.setattr(
        "gui.main_window.QMessageBox.critical", lambda *a: shown.append(a)
    )

    _heartbeat(main_window)

    assert logic.stopped and not logic.cleaned
    assert main_window.logic is logic
    assert shown == []
    assert widget.taken_over
    assert widget.bridge.takeover == {"holder": "PC-2", "list": "DHL_Orders"}
    assert not widget.scanner_input.isEnabled()
    assert not main_window.heartbeat_timer.isActive()  # it cannot report the loss twice

    widget.exit_packing_mode.emit()

    assert logic.cleaned
    assert main_window.logic is None
    assert not widget.taken_over
    assert main_window.stacked_widget.currentWidget() is main_window.session_widget
    assert (work_dir / SessionLockManager.LOCK_FILENAME).exists()  # not ours to delete


def test_a_lock_lost_while_leaving_packer_mode_is_told_in_a_message(
    main_window, tmp_path, monkeypatch
):
    """The page is about to be covered, so its panel would never be read."""
    work_dir = tmp_path / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    now = datetime.now().astimezone().isoformat()
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": "PC-2", "user_name": "x", "lock_time": now,
                    "heartbeat": now, "process_id": 1}),
        encoding="utf-8",
    )
    logic = LockLossLogic()
    main_window.logic = logic
    main_window.current_work_dir = str(work_dir)
    main_window.current_packing_list = "DHL_Orders"
    widget = main_window.packer_mode_widget
    main_window.stacked_widget.setCurrentWidget(widget)
    main_window._leaving_packer_mode = True
    shown = []
    monkeypatch.setattr(
        "gui.main_window.QMessageBox.critical", lambda *a: shown.append(a)
    )

    _heartbeat(main_window)

    assert len(shown) == 1
    assert not widget.taken_over
    assert logic.cleaned
