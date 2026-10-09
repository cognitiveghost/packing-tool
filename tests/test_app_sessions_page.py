"""The Sessions page in a real Chromium: frames 7a to 7h, the pane, 7c.

Never mark these skip -- a page nobody can run is a page nobody guards.
"""

import json
import time
from datetime import UTC, datetime

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.app_bridge import mount_app_page
from gui.sessions_payload import refresh_failure, sessions_payload, takeover_payload

NOW = datetime(2026, 10, 7, 14, 6, 31, tzinfo=UTC)


def _eval(qtbot, view, expr, timeout=5000):
    # runJavaScript cannot marshal a JS array back; route everything through JSON.
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def _until_js(qtbot, view, expr, timeout_s=20):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = max(int((deadline - time.monotonic()) * 1000), 50)
        try:
            if _eval(qtbot, view, expr, timeout=min(remaining, 5000)) is True:
                return
        except QtBotTimeoutError:
            continue
        qtbot.wait(50)
    pytest.fail(f"never became true in the page: {expr}")


def _js(qtbot, view, code):
    """Run statements in the page."""
    return _eval(qtbot, view, f"(function () {{ {code}; return true; }})()")


def _shown(view, qtbot, element_id):
    return _eval(qtbot, view, f"!document.getElementById('{element_id}').hidden")


def _text(view, qtbot, element_id):
    return _eval(qtbot, view, f"document.getElementById('{element_id}').textContent")


def _click(view, qtbot, element_id):
    _js(qtbot, view, f"document.getElementById('{element_id}').click()")


def _row_js(key):
    return ("Array.from(document.querySelectorAll('[data-session]'))"
            f".find(function (n) {{ return n.dataset.session === {json.dumps(key)}; }})")


def _select(view, qtbot, key):
    _js(qtbot, view, f"{_row_js(key)}.click()")


def _settle(qtbot, bridge):
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


def entry(session_id, status, **over):
    base = {
        "session_id": session_id,
        "packing_list_name": "Afternoon_wave",
        "status": status,
        "worker_id": "W-002",
        "worker_name": "Maria",
        "pc_name": "WH-PC-02",
        "started_at": f"{session_id[:10]}T09:00:00+00:00",
        "last_updated": f"{session_id[:10]}T11:20:00+00:00",
        "total_orders": 110,
        "completed_orders": 71,
        "skipped_orders": 2,
        "total_items": 402,
        "work_dir": f"/srv/{session_id}/packing/Afternoon_wave",
        "session_path": f"/srv/{session_id}",
        "metrics": None,
    }
    base.update(over)
    return base


ENTRIES = [
    entry("2026-10-07_2", "stale"),
    entry("2026-10-07_1", "in_progress"),
    entry("2026-10-06_2", "paused"),
    entry("2026-10-06_1", "completed"),
    entry("2026-10-05_1", "not_started", work_dir=""),
]
PAUSED = "2026-10-06_2|Afternoon_wave"
ACTIVE = "2026-10-07_1|Afternoon_wave"
STALE = "2026-10-07_2|Afternoon_wave"


def payload(entries=ENTRIES, **kwargs):
    kwargs.setdefault("stamp", "14:06:31")
    return sessions_payload(entries, now=NOW, **kwargs)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_app_page(view)
    view.resize(1166, 708)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_page("sessions")
    return view, bridge


@pytest.fixture
def listed(page, qtbot):
    view, bridge = page
    bridge.set_sessions(payload())
    _settle(qtbot, bridge)
    return view, bridge


def test_7h_with_no_client_the_card_speaks_for_sessions(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=False, clients=True, server_down=False)
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "no-client")
    assert not _shown(view, qtbot, "sessions")
    assert _text(view, qtbot, "no-client-title") == "Choose a client"
    assert _text(view, qtbot, "no-client-text") == (
        "Pick a client in the bar above to see its sessions.")


def test_7e_the_first_load_shows_dashes_and_skeleton_rows(page, qtbot):
    view, bridge = page
    bridge.set_sessions(payload([], loaded=False, refreshing=True, stamp=""))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "sessions")
    assert _shown(view, qtbot, "s-loading")
    assert _eval(qtbot, view, "document.querySelectorAll('#s-skeleton .app-skel').length") == 12
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#s-tabs .segment-count'))"
                 ".map(function (n) { return n.textContent; })") == ["–"] * 4
    assert _text(view, qtbot, "s-count") == "–"
    assert _text(view, qtbot, "s-stamp-label") == "Refreshing…"
    assert _eval(qtbot, view, "document.getElementById('s-refresh').disabled") is True
    assert not _shown(view, qtbot, "s-empty")


def test_7a_the_toolbar_the_rows_and_the_foot(listed, qtbot):
    view, _bridge = listed
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#s-tabs .segment'))"
                 ".map(function (n) { return n.textContent; })") == [
        "All5", "Open4", "Finished1", "Abandoned0"]
    assert _eval(qtbot, view,
                 "document.querySelector('#s-tabs [aria-checked=\"true\"]').dataset.tab") == "all"
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('[data-session] .app-s-id'))"
                 ".map(function (n) { return n.textContent; })") == [
        "2026-10-07_2", "2026-10-07_1", "2026-10-06_2", "2026-10-06_1", "2026-10-05_1"]
    assert _text(view, qtbot, "s-count") == "5 sessions"
    assert _text(view, qtbot, "s-stamp") == "14:06:31"
    assert _eval(qtbot, view, "document.getElementById('s-from').value") == "2026-09-07"
    assert not _shown(view, qtbot, "s-pane")
    assert not _shown(view, qtbot, "s-loading")
    # A solid dot for the status a packer set, a hollow one otherwise.
    assert _eval(qtbot, view, f"!!{_row_js(PAUSED)}.querySelector('.dot.solid')") is True
    assert _eval(qtbot, view, f"!!{_row_js(ACTIVE)}.querySelector('.dot.solid')") is False
    assert _eval(qtbot, view, f"{_row_js(PAUSED)}.title") == "Double-click: Resume session"


def test_selecting_a_row_opens_the_pane_and_folds_two_columns(listed, qtbot):
    view, _bridge = listed
    _select(view, qtbot, PAUSED)
    assert _shown(view, qtbot, "s-pane")
    assert _eval(qtbot, view,
                 "document.getElementById('s-main').classList.contains('pane-open')") is True
    assert _eval(qtbot, view, f"{_row_js(PAUSED)}.getAttribute('aria-pressed')") == "true"
    assert _text(view, qtbot, "p-id") == "2026-10-06_2"
    assert _text(view, qtbot, "p-list") == "Afternoon_wave"
    assert _text(view, qtbot, "p-why") == "Set by a person · paused by Maria, 6 Oct, 11:20"
    assert _text(view, qtbot, "p-orders") == "71 / 110"
    assert _text(view, qtbot, "p-orders-note") == "2 skipped"
    assert _eval(qtbot, view, "document.querySelectorAll('#p-facts .app-p-fact').length") == 7
    assert _text(view, qtbot, "p-action") == "Resume session"
    assert _shown(view, qtbot, "p-details")
    assert not _shown(view, qtbot, "p-note")
    # The folded columns are not laid out.
    assert _eval(qtbot, view,
                 f"{_row_js(PAUSED)}.querySelector('.app-s-touched').offsetParent === null") is True


def test_the_panes_action_reaches_python(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.sessionActionRequested.connect(asked.append)
    _select(view, qtbot, PAUSED)
    _click(view, qtbot, "p-action")
    qtbot.waitUntil(lambda: asked == [PAUSED], timeout=5000)


def test_a_double_click_runs_the_rows_action(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.sessionActionRequested.connect(asked.append)
    _js(qtbot, view,
        f"{_row_js(PAUSED)}.dispatchEvent(new MouseEvent('dblclick', {{bubbles: true}}))")
    qtbot.waitUntil(lambda: asked == [PAUSED], timeout=5000)


def test_a_disabled_action_says_why_and_does_nothing(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.sessionActionRequested.connect(asked.append)
    _select(view, qtbot, ACTIVE)
    assert _eval(qtbot, view, "document.getElementById('p-action').disabled") is True
    assert _text(view, qtbot, "p-note-text") == (
        "Open on WH-PC-02 right now. It can be taken over once that PC stops responding.")
    assert _eval(qtbot, view,
                 "document.getElementById('p-note').classList.contains('warn')") is False
    _click(view, qtbot, "p-action")
    _js(qtbot, view,
        f"{_row_js(ACTIVE)}.dispatchEvent(new MouseEvent('dblclick', {{bubbles: true}}))")
    qtbot.wait(300)
    assert asked == []


def test_a_stale_session_warns_before_it_is_resumed(listed, qtbot):
    view, _bridge = listed
    _select(view, qtbot, STALE)
    assert _shown(view, qtbot, "p-note")
    assert _eval(qtbot, view,
                 "document.getElementById('p-note').classList.contains('warn')") is True
    assert _eval(qtbot, view, "document.getElementById('p-action').disabled") is False


def test_view_details_reaches_python(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.sessionDetailsRequested.connect(asked.append)
    _select(view, qtbot, PAUSED)
    _click(view, qtbot, "p-details")
    qtbot.waitUntil(lambda: asked == [PAUSED], timeout=5000)


def test_a_session_with_no_files_offers_no_details(listed, qtbot):
    view, _bridge = listed
    _select(view, qtbot, "2026-10-05_1|Afternoon_wave")
    assert _text(view, qtbot, "p-action") == "Start packing"
    assert not _shown(view, qtbot, "p-details")


def test_a_tab_the_search_and_a_date_reach_python(listed, qtbot):
    view, bridge = listed
    got = []
    bridge.sessionsFilterChanged.connect(lambda *args: got.append(args))
    _js(qtbot, view, "document.querySelector('[data-tab=\"open\"]').click()")
    qtbot.waitUntil(lambda: got == [("open", "", "2026-09-07", "2026-10-07")], timeout=5000)

    _js(qtbot, view,
        "var q = document.getElementById('s-query'); q.focus(); q.value = 'maria';"
        "q.dispatchEvent(new Event('input', {bubbles: true}))")
    qtbot.waitUntil(lambda: got[-1] == ("all", "maria", "2026-09-07", "2026-10-07"), timeout=5000)

    _js(qtbot, view,
        "var f = document.getElementById('s-from'); f.value = '2026-10-01';"
        "f.dispatchEvent(new Event('change', {bubbles: true}))")
    qtbot.waitUntil(lambda: got[-1] == ("all", "maria", "2026-10-01", "2026-10-07"), timeout=5000)


def test_a_push_does_not_overwrite_the_input_being_typed_in(listed, qtbot):
    view, bridge = listed
    _js(qtbot, view, "var q = document.getElementById('s-query'); q.focus(); q.value = 'mar'")
    bridge.set_sessions(payload(query="ma"))
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.getElementById('s-query').value") == "mar"
    _js(qtbot, view, "document.getElementById('s-query').blur()")
    bridge.set_sessions(payload(query="m"))
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.getElementById('s-query').value") == "m"
    assert _shown(view, qtbot, "s-query-clear")


def test_changing_tab_drops_the_selection(listed, qtbot):
    view, bridge = listed
    _select(view, qtbot, PAUSED)
    bridge.set_sessions(payload(tab="open"))
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "s-pane")


def test_a_refresh_keeps_the_selection(listed, qtbot):
    view, bridge = listed
    _select(view, qtbot, PAUSED)
    bridge.set_sessions(payload(stamp="14:08:31"))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-pane")
    assert _text(view, qtbot, "p-id") == "2026-10-06_2"


def test_7d_nothing_matches_and_clear_filters(listed, qtbot):
    view, bridge = listed
    cleared = []
    bridge.sessionsFilterCleared.connect(lambda: cleared.append(1))
    bridge.set_sessions(payload(tab="open", query="2025-12"))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-no-match")
    assert _text(view, qtbot, "s-no-match-text") == (
        "Nothing in Open between 7 Sep and 7 Oct has “2025-12” in its id, "
        "packing list, worker or PC.")
    assert _text(view, qtbot, "s-count") == "0 of 4 sessions"
    assert _eval(qtbot, view, "document.getElementById('s-export').disabled") is True
    _js(qtbot, view, "document.querySelector('#s-no-match .btn').click()")
    qtbot.waitUntil(lambda: cleared == [1], timeout=5000)


def test_7f_a_failed_refresh_keeps_the_list_and_offers_retry(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.refreshSessionsRequested.connect(lambda: asked.append(1))
    failure = refresh_failure("/srv/Sessions/CLIENT_ACME", "the network path was not found",
                              "14:08:31", "14:06:31")
    bridge.set_sessions(payload(failure=failure))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-failed")
    assert _text(view, qtbot, "s-failed-path") == "/srv/Sessions/CLIENT_ACME"
    assert _text(view, qtbot, "s-failed-cause") == "the network path was not found"
    assert _shown(view, qtbot, "s-failed-from-line")
    assert _eval(qtbot, view,
                 "document.getElementById('s-stamp-line').classList.contains('failed')") is True
    assert _eval(qtbot, view, "document.querySelectorAll('[data-session]').length") == 5
    _click(view, qtbot, "s-failed-retry")
    qtbot.waitUntil(lambda: asked == [1], timeout=5000)

    first = refresh_failure("/srv/Sessions/CLIENT_ACME", "x", "14:08:31", "")
    bridge.set_sessions(payload([], failure=first, stamp=""))
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "s-failed-from-line")
    # With the server away, "No sessions yet" would be a guess.
    assert not _shown(view, qtbot, "s-empty")


def test_7g_a_client_with_no_sessions(page, qtbot):
    view, bridge = page
    bridge.set_sessions(payload([]))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-empty")
    assert not _shown(view, qtbot, "s-no-match")
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#s-tabs .segment-count'))"
                 ".map(function (n) { return n.textContent; })") == ["0"] * 4


def test_the_switch_the_refresh_button_and_f5_reach_python(listed, qtbot):
    view, bridge = listed
    auto, asked = [], []
    bridge.autoRefreshChanged.connect(auto.append)
    bridge.refreshSessionsRequested.connect(lambda: asked.append(1))
    assert _eval(qtbot, view,
                 "document.getElementById('s-auto').getAttribute('aria-checked')") == "true"
    _click(view, qtbot, "s-auto")
    qtbot.waitUntil(lambda: auto == [False], timeout=5000)
    _click(view, qtbot, "s-refresh")
    qtbot.waitUntil(lambda: asked == [1], timeout=5000)
    _js(qtbot, view,
        "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'F5', bubbles: true}))")
    qtbot.waitUntil(lambda: asked == [1, 1], timeout=5000)


def test_the_export_menu_offers_csv_and_excel(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.exportSessionsRequested.connect(asked.append)
    assert not _shown(view, qtbot, "s-export-menu")
    _click(view, qtbot, "s-export")
    assert _shown(view, qtbot, "s-export-menu")
    assert _text(view, qtbot, "s-export-title") == "Export the 5 sessions shown"
    _js(qtbot, view, "document.querySelector('[data-action=\"exportCsv\"]').click()")
    qtbot.waitUntil(lambda: asked == ["csv"], timeout=5000)
    assert not _shown(view, qtbot, "s-export-menu")
    _click(view, qtbot, "s-export")
    _js(qtbot, view, "document.querySelector('[data-action=\"exportXlsx\"]').click()")
    qtbot.waitUntil(lambda: asked == ["csv", "xlsx"], timeout=5000)


def test_7c_the_take_over_question_and_both_answers(listed, qtbot):
    view, bridge = listed
    answers = []
    bridge.takeOverAnswered.connect(answers.append)
    lock = {"locked_by": "WH-PC-02", "worker_name": "Georgi",
            "heartbeat": "2026-10-07T13:52:10+00:00"}
    bridge.set_confirm(takeover_payload(ENTRIES[0], lock, now=NOW))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "confirm")
    assert _text(view, qtbot, "confirm-id") == "2026-10-07_2"
    assert _text(view, qtbot, "confirm-body").startswith("WH-PC-02 stopped responding at 13:52")
    assert _text(view, qtbot, "confirm-carry") == (
        "Everything saved so far comes with you: 71 of 110 orders packed.")
    _click(view, qtbot, "confirm-ok")
    qtbot.waitUntil(lambda: answers == [True], timeout=5000)
    _click(view, qtbot, "confirm-cancel")
    qtbot.waitUntil(lambda: answers == [True, False], timeout=5000)
    bridge.set_confirm({})
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "confirm")


def test_escape_answers_the_question_then_closes_the_pane(listed, qtbot):
    view, bridge = listed
    answers = []
    bridge.takeOverAnswered.connect(answers.append)
    _select(view, qtbot, STALE)
    bridge.set_confirm(takeover_payload(ENTRIES[0], {"locked_by": "WH-PC-02"}, now=NOW))
    _settle(qtbot, bridge)
    escape = "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))"
    _js(qtbot, view, escape)
    qtbot.waitUntil(lambda: answers == [False], timeout=5000)
    assert _shown(view, qtbot, "s-pane")
    bridge.set_confirm({})
    _settle(qtbot, bridge)
    _js(qtbot, view, escape)
    assert not _shown(view, qtbot, "s-pane")


def test_markup_in_a_list_name_is_text(page, qtbot):
    """Review focus 3."""
    view, bridge = page
    nasty = entry("2026-10-06_2", "paused", packing_list_name="<img src=x onerror=alert(1)>",
                  worker_name="<b>Maria</b>")
    bridge.set_sessions(payload([nasty]))
    _settle(qtbot, bridge)
    _select(view, qtbot, "2026-10-06_2|<img src=x onerror=alert(1)>")
    assert _text(view, qtbot, "p-list") == "<img src=x onerror=alert(1)>"
    assert _eval(qtbot, view, "document.querySelectorAll('#sessions img, #sessions b').length") == 0


def test_covered_hides_the_page_and_the_question(listed, qtbot):
    view, bridge = listed
    bridge.set_confirm(takeover_payload(ENTRIES[0], {"locked_by": "WH-PC-02"}, now=NOW))
    bridge.set_covered(True)
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "sessions")
    assert not _shown(view, qtbot, "confirm")


def test_packing_still_draws_after_sessions(listed, qtbot):
    view, bridge = listed
    bridge.set_page("packing")
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "sessions")
    assert _shown(view, qtbot, "no-session")
    assert _text(view, qtbot, "no-client-title") == "Choose a client to begin"
