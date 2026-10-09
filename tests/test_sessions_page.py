"""SessionsPage: the Sessions pages' controller (spec 2026-10-08 phase 4, 4.5 and 6).

A real AppBridge and real managers; no Chromium. Where a test calls
`_on_refreshed`, `_on_details` or `_on_tick`, that is the slot a worker's or
the timer's signal is connected to: the answer arrives as it would.
"""

import csv
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import ClassVar

import pandas as pd
import pytest
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QFileDialog

from gui.app_bridge import AppBridge
from gui.sessions_page import SessionsPage
from gui.sessions_payload import default_range, session_key
from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_registry_manager import SessionRegistryManager


def stamp(**ago) -> str:
    return (datetime.now().astimezone() - timedelta(**ago)).isoformat()


# Worked out once: entries made in one test share a start time, so the page
# lists them in the order they were given.
STARTED = stamp(hours=3)
TOUCHED = stamp(hours=1)


def entry(session_id="2026-10-06_2", status="paused", **over) -> dict:
    base = {
        "session_id": session_id,
        "packing_list_name": "Afternoon_wave",
        "status": status,
        "worker_name": "Maria",
        "pc_name": "WH-PC-02",
        "started_at": STARTED,
        "last_updated": TOUCHED,
        "total_orders": 110,
        "completed_orders": 71,
        "skipped_orders": 2,
        "total_items": 402,
        "work_dir": "",
        "session_path": "/srv/2026-10-06_2",
        "metrics": None,
    }
    base.update(over)
    return base


@pytest.fixture
def made(qapp, profile_manager, server_root):
    (server_root / "Sessions" / "CLIENT_TEST").mkdir(parents=True)
    QSettings("PackingTool", "SessionBrowser").clear()
    bridge = AppBridge()
    bridge.set_page("sessions")
    toasts = []
    showing = {"on": True}
    locks = SessionLockManager(profile_manager)
    page = SessionsPage(
        bridge,
        SessionRegistryManager(profile_manager),
        locks,
        is_showing=lambda: showing["on"],
        client_label=lambda: "Test Client (TEST)",
        toast=toasts.append,
    )
    page.load_client("TEST")
    drain(page, qapp)
    started, resumed, shown = [], [], []
    page.startRequested.connect(started.append)
    page.resumeRequested.connect(resumed.append)
    page.showPackingRequested.connect(lambda: shown.append(1))
    yield SimpleNamespace(page=page, bridge=bridge, toasts=toasts, showing=showing,
                          locks=locks, started=started, resumed=resumed, shown=shown,
                          qapp=qapp)
    page.shutdown()


def drain(page, qapp):
    """Let the workers finish and their queued answers arrive."""
    page.wait()
    qapp.processEvents()
    qapp.processEvents()


def rows(made):
    return made.bridge.sessions["rows"]


def work_dir(tmp_path, name="2026-10-06_2"):
    path = tmp_path / name / "packing" / "Afternoon_wave"
    path.mkdir(parents=True, exist_ok=True)
    return path


def lock(path, *, age_seconds, pc="WH-PC-02", pid=1):
    beat = (datetime.now().astimezone() - timedelta(seconds=age_seconds)).isoformat()
    (path / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": pc, "user_name": "georgi", "lock_time": beat,
                    "heartbeat": beat, "process_id": pid, "worker_name": "Georgi"}),
        encoding="utf-8",
    )


# --- loading and refreshing --------------------------------------------------------


def test_loading_a_client_shows_the_loading_state_then_its_sessions(
    qapp, profile_manager, server_root
):
    (server_root / "Sessions" / "CLIENT_TEST").mkdir(parents=True)
    QSettings("PackingTool", "SessionBrowser").clear()
    bridge = AppBridge()
    page = SessionsPage(bridge, SessionRegistryManager(profile_manager),
                        SessionLockManager(profile_manager))
    try:
        page.load_client("TEST")
        assert bridge.sessions["mode"] == "loading"
        assert bridge.sessions["refreshing"] is True
        drain(page, qapp)
        assert bridge.sessions["mode"] == "empty"
        assert bridge.sessions["refreshing"] is False
        assert bridge.sessions["stamp"]
    finally:
        page.shutdown()


def test_show_entries_is_a_finished_refresh(made):
    made.page.show_entries([entry("a"), entry("b", "completed")])
    assert [row["id"] for row in rows(made)] == ["a", "b"]
    assert made.bridge.sessions["mode"] == "ready"


def test_a_refresh_for_another_client_is_dropped(made):
    """Review focus 4."""
    made.page.show_entries([entry("mine")])
    made.page._on_refreshed("OTHER", [entry("theirs")])
    made.page._on_refresh_failed("OTHER", "boom")
    assert [row["id"] for row in rows(made)] == ["mine"]
    assert made.bridge.sessions["failed"] is False


def test_a_failed_refresh_keeps_the_list_and_names_the_folder(made, server_root):
    made.page.show_entries([entry("mine")])
    before = made.bridge.sessions["stamp"]
    made.page._on_refresh_failed("TEST", "the network path was not found")
    sessions = made.bridge.sessions
    assert sessions["failed"] is True
    assert sessions["failure"]["path"] == str(server_root / "Sessions" / "CLIENT_TEST")
    assert sessions["failure"]["cause"] == "the network path was not found"
    assert sessions["failure"]["from"] == before
    assert [row["id"] for row in rows(made)] == ["mine"]
    made.page.show_entries([entry("mine")])
    assert made.bridge.sessions["failed"] is False


class RunningWorker(QObject):
    """A refresh that never ends: what a slow share looks like."""

    refresh_complete = Signal(str, list)
    refresh_failed = Signal(str, str)
    finished = Signal()
    started_for: ClassVar[list] = []

    def __init__(self, registry, client_id, parent=None):
        super().__init__(parent)
        RunningWorker.started_for.append(client_id)

    def start(self):
        pass

    def isRunning(self):
        return True

    def wait(self, _timeout_ms=0):
        return True


def test_a_refresh_while_one_runs_for_the_same_client_starts_no_second_worker(
    made, monkeypatch
):
    RunningWorker.started_for = []
    monkeypatch.setattr("gui.sessions_page.RegistryRefreshWorker", RunningWorker)
    made.page.refresh()
    made.page.refresh()
    assert RunningWorker.started_for == ["TEST"]
    made.page.load_client("OTHER")  # another client's sessions are another question
    assert RunningWorker.started_for == ["TEST", "OTHER"]


def test_showing_the_page_refreshes(made, monkeypatch):
    calls = []
    monkeypatch.setattr(made.page, "refresh", lambda: calls.append(1))
    made.page.page_shown()
    assert calls == [1]


def test_the_timer_refreshes_only_while_the_page_is_showing(made, monkeypatch):
    calls = []
    monkeypatch.setattr(made.page, "refresh", lambda: calls.append(1))
    made.showing["on"] = False
    made.page._on_tick()
    assert calls == []
    made.showing["on"] = True
    made.page._on_tick()
    assert calls == [1]
    assert made.page._timer.isActive()


def test_the_switch_is_saved_and_stops_the_timer(made):
    assert made.bridge.sessions["auto"] is True
    made.bridge.setAutoRefresh(False)
    assert made.bridge.sessions["auto"] is False
    assert QSettings("PackingTool", "SessionBrowser").value(
        "auto_refresh_enabled", True, type=bool) is False
    assert not made.page._timer.isActive()
    made.bridge.setAutoRefresh(True)
    assert made.page._timer.isActive()


# --- the filter ----------------------------------------------------------------------


def test_the_filter_slots_change_the_rows(made):
    made.page.show_entries([entry("a"), entry("b", "completed", worker_name="Ivan")])
    start, end = default_range(datetime.now().astimezone())
    made.bridge.setSessionsFilter("finished", "", start, end)
    assert [row["id"] for row in rows(made)] == ["b"]
    made.bridge.setSessionsFilter("all", "maria", start, end)
    assert [row["id"] for row in rows(made)] == ["a"]
    assert made.bridge.sessions["query"] == "maria"


def test_the_default_range_keeps_moving_until_a_date_is_changed(made):
    made.page.show_entries([entry("a")])
    start, end = default_range(datetime.now().astimezone())
    made.bridge.setSessionsFilter("all", "x", start, end)
    assert made.page._dates is None  # still the default: tomorrow it is tomorrow's
    made.bridge.setSessionsFilter("all", "x", "2026-01-01", end)
    assert made.bridge.sessions["dateFrom"] == "2026-01-01"
    made.bridge.setSessionsFilter("all", "x", "", "")
    assert (made.bridge.sessions["dateFrom"], made.bridge.sessions["dateTo"]) == ("", "")


def test_clear_filters_empties_the_search_and_puts_the_dates_back(made):
    made.page.show_entries([entry("a")])
    made.bridge.setSessionsFilter("open", "zzz", "2026-01-01", "2026-01-02")
    assert rows(made) == []
    made.bridge.clearSessionsFilter()
    sessions = made.bridge.sessions
    assert (sessions["tab"], sessions["query"]) == ("open", "")
    assert (sessions["dateFrom"], sessions["dateTo"]) == default_range(datetime.now().astimezone())
    assert [row["id"] for row in rows(made)] == ["a"]


def test_the_context_reaches_the_rows(made):
    made.page.show_entries([entry("a")])
    assert rows(made)[0]["enabled"] is True
    made.page.set_context("x|y", False)
    assert rows(made)[0]["enabled"] is False
    made.page.set_context("", True)
    assert rows(made)[0]["note"].startswith("Server unreachable")


# --- start, resume, take over (section 6) ----------------------------------------------


def test_start_packing_asks_main_window_with_todays_payload(made):
    fresh = entry("n", "not_started", packing_list_path="/srv/n/packing_lists/L.json",
                  session_path="/srv/n")
    made.page.show_entries([fresh])
    made.bridge.sessionAction(session_key(fresh))
    assert made.started == [{
        "session_path": "/srv/n",
        "client_id": "TEST",
        "packing_list_name": "Afternoon_wave",
        "list_file": "/srv/n/packing_lists/L.json",
    }]


def test_resume_asks_main_window_with_todays_payload(made, tmp_path):
    path = work_dir(tmp_path)
    paused = entry(work_dir=str(path))
    made.page.show_entries([paused])
    made.bridge.sessionAction(session_key(paused))
    assert made.resumed == [{
        "session_path": "/srv/2026-10-06_2",
        "client_id": "TEST",
        "packing_list_name": "Afternoon_wave",
        "work_dir": str(path),
        "session_id": "2026-10-06_2",
        "take_over": None,
    }]
    assert made.bridge.confirm == {}


def test_a_disabled_action_does_nothing(made):
    active = entry("a", "in_progress")
    made.page.show_entries([active])
    made.bridge.sessionAction(session_key(active))
    made.bridge.sessionAction("no such key")
    assert made.resumed == [] and made.started == []


def test_the_session_open_here_goes_to_packing(made):
    active = entry("a", "in_progress")
    made.page.show_entries([active])
    made.page.set_context(session_key(active), False)
    made.bridge.sessionAction(session_key(active))
    assert made.shown == [1]
    assert made.resumed == []


def test_a_stale_lock_is_asked_about_before_anything_starts(made, tmp_path):
    path = work_dir(tmp_path)
    lock(path, age_seconds=600)
    stale = entry(status="stale", work_dir=str(path))
    made.page.show_entries([stale])

    made.bridge.sessionAction(session_key(stale))
    assert made.resumed == []
    assert made.bridge.confirm["id"] == "2026-10-06_2"
    assert "WH-PC-02 stopped responding" in made.bridge.confirm["body"]
    assert "while Georgi was packing" in made.bridge.confirm["body"]

    made.bridge.answerTakeOver(False)
    assert made.bridge.confirm == {}
    assert made.resumed == []

    made.bridge.sessionAction(session_key(stale))
    made.bridge.answerTakeOver(True)
    assert made.bridge.confirm == {}
    assert len(made.resumed) == 1
    assert made.resumed[0]["take_over"]["locked_by"] == "WH-PC-02"
    assert made.resumed[0]["work_dir"] == str(path)


def test_an_answer_with_no_question_open_does_nothing(made):
    made.bridge.answerTakeOver(True)
    assert made.resumed == []


def test_a_live_lock_is_left_to_the_start_to_refuse(made, tmp_path):
    """The list was behind: it said Paused, another PC has it. Nothing is asked;
    the start refuses it and frame 3c says who has it."""
    path = work_dir(tmp_path)
    lock(path, age_seconds=5)
    paused = entry(work_dir=str(path))
    made.page.show_entries([paused])
    made.bridge.sessionAction(session_key(paused))
    assert made.bridge.confirm == {}
    assert len(made.resumed) == 1 and made.resumed[0]["take_over"] is None


def test_our_own_lock_is_not_asked_about(made, tmp_path):
    path = work_dir(tmp_path)
    lock(path, age_seconds=600, pc=made.locks.hostname, pid=made.locks.process_id)
    paused = entry(work_dir=str(path))
    made.page.show_entries([paused])
    made.bridge.sessionAction(session_key(paused))
    assert made.bridge.confirm == {}
    assert len(made.resumed) == 1


def test_changing_client_drops_an_open_question(made, tmp_path):
    path = work_dir(tmp_path)
    lock(path, age_seconds=600)
    stale = entry(status="stale", work_dir=str(path))
    made.page.show_entries([stale])
    made.bridge.sessionAction(session_key(stale))
    made.page.load_client("OTHER")
    assert made.bridge.confirm == {}
    made.bridge.answerTakeOver(True)
    assert made.resumed == []
    drain(made.page, made.qapp)


# --- details (section 7) ---------------------------------------------------------------


def summary(path, **over):
    data = {
        "session_id": "2026-10-06_2", "packing_list_name": "Afternoon_wave",
        "total_orders": 3, "completed_orders": 1, "metrics": {},
        "orders": [{"order_number": "#1", "duration_seconds": 30, "items_count": 1,
                    "items": [{"sku": "A", "quantity": 1, "row": 0}]}],
        "skipped_orders": [],
    }
    data.update(over)
    (path / "session_summary.json").write_text(json.dumps(data), encoding="utf-8")


def test_details_show_the_lists_facts_then_the_files(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    assert made.bridge.page == "details"
    assert made.bridge.details["state"] == "loading"
    assert made.bridge.details["facts"][0] == {"label": "Client", "value": "Test Client (TEST)"}
    drain(made.page, made.qapp)
    assert made.bridge.details["state"] == "ready"
    assert [order["label"] for order in made.bridge.details["orders"]] == ["#1"]


def test_view_details_is_also_a_rows_action(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionAction(session_key(done))
    assert made.bridge.page == "details"
    drain(made.page, made.qapp)


def test_unreadable_files_are_an_error_and_retry_reads_again(made, tmp_path):
    path = work_dir(tmp_path)
    (path / "session_summary.json").write_text("{", encoding="utf-8")
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    assert made.bridge.details["state"] == "error"
    assert made.bridge.details["error"]["path"].endswith("session_summary.json")

    summary(path)
    made.bridge.retryDetails()
    assert made.bridge.details["state"] == "loading"
    drain(made.page, made.qapp)
    assert made.bridge.details["state"] == "ready"


def test_closing_details_returns_to_the_list(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    made.bridge.closeDetails()
    assert made.bridge.details == {}
    assert made.bridge.page == "sessions"


def test_details_for_a_closed_session_are_dropped(made, tmp_path):
    """Review focus 4."""
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    made.bridge.closeDetails()
    drain(made.page, made.qapp)
    assert made.bridge.details == {}
    made.page._on_details("some|other", {"record": {}})
    made.page._on_details_failed("some|other", "/x", "y")
    assert made.bridge.details == {}


def test_details_on_another_page_do_not_pull_the_packer_back(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    made.bridge.set_page("packing")
    made.bridge.closeDetails()
    assert made.bridge.page == "packing"


def test_the_details_filter_reaches_the_payload(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    made.bridge.setDetailsFilter("999")
    assert made.bridge.details["noMatch"] is True
    assert made.bridge.details["query"] == "999"


def test_a_refresh_re_reads_an_active_sessions_details_without_a_flash(made, tmp_path):
    path = work_dir(tmp_path)
    state = {"started_at": stamp(hours=1), "progress": {"total_orders": 3},
             "completed": [{"order_number": "#1", "items_count": 1}], "in_progress": {}}
    (path / "packing_state.json").write_text(json.dumps(state), encoding="utf-8")
    active = entry("live", "in_progress", work_dir=str(path))
    made.page.show_entries([active])
    made.bridge.sessionDetails(session_key(active))
    drain(made.page, made.qapp)
    assert made.bridge.details["cards"][0]["value"] == "1"

    state["completed"].append({"order_number": "#2", "items_count": 2})
    (path / "packing_state.json").write_text(json.dumps(state), encoding="utf-8")
    made.page.show_entries([active])
    assert made.bridge.details["state"] == "ready"  # the old numbers stay until the new arrive
    drain(made.page, made.qapp)
    assert made.bridge.details["cards"][0]["value"] == "2"


def test_a_refresh_does_not_re_read_a_finished_sessions_details(made, tmp_path, monkeypatch):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    reads = []
    monkeypatch.setattr(made.page, "_load_details", lambda **kwargs: reads.append(kwargs))
    made.page.show_entries([done])
    assert reads == []
    assert made.bridge.details["state"] == "ready"


def test_details_left_open_are_read_once_more_when_the_session_finishes(made, tmp_path):
    path = work_dir(tmp_path)
    state = {"started_at": stamp(hours=1), "progress": {"total_orders": 3},
             "completed": [{"order_number": "#1", "items_count": 1}], "in_progress": {}}
    (path / "packing_state.json").write_text(json.dumps(state), encoding="utf-8")
    active = entry("live", "in_progress", work_dir=str(path))
    made.page.show_entries([active])
    made.bridge.sessionDetails(session_key(active))
    drain(made.page, made.qapp)
    assert made.bridge.details["cards"][0]["value"] == "1"

    state["completed"].append({"order_number": "#2", "items_count": 2})
    (path / "packing_state.json").write_text(json.dumps(state), encoding="utf-8")
    made.page.show_entries([dict(active, status="completed")])
    drain(made.page, made.qapp)
    assert made.bridge.details["cards"][0]["value"] == "2"


def test_files_the_payload_cannot_read_are_the_error_frame(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path, skipped_orders=3)  # parses, but is not a list
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    assert made.bridge.details["state"] == "error"
    assert made.bridge.details["error"]["path"] == str(path)


# --- exports (section 8) ---------------------------------------------------------------


def choose(monkeypatch, path):
    asked = []

    def fake(parent, title, name, filters):
        asked.append((title, name, filters))
        return (str(path) if path else "", "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake))
    return asked


def test_csv_export_writes_the_rows_shown(made, tmp_path, monkeypatch):
    made.page.show_entries([entry("a"), entry("b", "completed")])
    start, end = default_range(datetime.now().astimezone())
    made.bridge.setSessionsFilter("finished", "", start, end)
    out = tmp_path / "out.csv"
    asked = choose(monkeypatch, out)
    made.bridge.exportSessions("csv")
    assert asked == [("Save CSV", "sessions_TEST.csv", "CSV files (*.csv)")]
    with open(out, newline="", encoding="utf-8") as handle:
        written = list(csv.reader(handle))
    assert written[0][:3] == ["Status", "Packing List", "Session ID"]
    assert [line[2] for line in written[1:]] == ["b"]
    assert written[1][0] == "completed"
    assert made.toasts == ["Exported 1 session to out.csv"]


def test_excel_export_writes_the_status_word(made, tmp_path, monkeypatch):
    made.page.show_entries([entry("a"), entry("b", "completed")])
    out = tmp_path / "out.xlsx"
    asked = choose(monkeypatch, out)
    made.bridge.exportSessions("xlsx")
    assert asked == [("Save Excel", "sessions_TEST.xlsx", "Excel files (*.xlsx)")]
    frame = pd.read_excel(out)
    assert list(frame["Session ID"]) == ["a", "b"]
    assert list(frame["Status"]) == ["Paused", "Completed"]
    assert made.toasts == ["Exported 2 sessions to out.xlsx"]


def test_a_cancelled_export_writes_nothing(made, monkeypatch):
    made.page.show_entries([entry("a")])
    choose(monkeypatch, None)
    made.bridge.exportSessions("csv")
    assert made.toasts == []


def test_an_export_with_no_rows_does_not_ask_for_a_file(made, monkeypatch):
    asked = choose(monkeypatch, None)
    made.bridge.exportSessions("csv")
    assert asked == []


def test_the_details_export_is_one_row_per_scan(made, tmp_path, monkeypatch):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    out = tmp_path / "details.xlsx"
    asked = choose(monkeypatch, out)
    made.bridge.exportDetails()
    assert asked == [("Export Session Details", "session_2026-10-06_2.xlsx", "Excel Files (*.xlsx)")]
    frame = pd.read_excel(out, sheet_name="Session Details")
    assert list(frame["Order Number"]) == ["#1"]
    assert list(frame["SKU"]) == ["A"]
    assert made.toasts == ["Exported 2026-10-06_2 to details.xlsx"]


def test_an_export_that_fails_says_so_in_a_dialog(made, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    made.page.show_entries([entry("a")])
    choose(monkeypatch, tmp_path / "no such folder" / "out.csv")
    boxes = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *args: boxes.append(args[1])))
    made.bridge.exportSessions("csv")
    assert boxes == ["Export Failed"]
    assert made.toasts == []
