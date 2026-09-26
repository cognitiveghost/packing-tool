"""Spec B3: a PC whose lock another PC took must stop writing and leave the
session without end_session()'s writes, which would stamp the other PC's
live session as ended."""

import json
from datetime import datetime
from pathlib import Path

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
