"""The connection card, the banner and what an outage disables
(spec 2026-10-08 section 6.5, frames 2d and 2e).

The server is checked on Retry and after a failed session action, never on a
timer. test_path_reachable is replaced, so no test waits on a real share.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

import gui.main_window as mw
from shared.components.toast import Toast


@pytest.fixture
def reach(monkeypatch):
    """Whether the fake server answers; count of the checks made."""
    state = {"ok": True, "calls": 0}

    def fake(_path, _timeout=5):
        state["calls"] += 1
        return state["ok"]

    monkeypatch.setattr(mw, "test_path_reachable", fake)
    return state


def _check(window, qtbot):
    window.check_connection()
    qtbot.waitUntil(lambda: window._connection_state != "checking", timeout=3000)


def test_it_starts_connected_with_no_banner(main_window):
    assert main_window._connection_state == "ok"
    assert main_window.connection_banner.isHidden()
    assert main_window.sidebar.connection_label.text() == "Server connected"
    assert main_window.sidebar.path_label.toolTip() == str(
        main_window.profile_manager.base_path
    )


def test_a_check_shows_reconnecting_while_it_runs(main_window, qtbot, reach):
    main_window.check_connection()
    assert main_window._connection_state == "checking"
    assert main_window.sidebar.connection_label.text() == "Reconnecting…"
    assert main_window.connection_banner.isHidden()
    qtbot.waitUntil(lambda: main_window._connection_state == "ok", timeout=3000)


def test_a_failed_check_raises_the_banner_and_disables_session_actions(
    main_window, qtbot, reach
):
    reach["ok"] = False
    _check(main_window, qtbot)
    assert main_window._connection_state == "down"
    assert main_window.sidebar.connection_label.text() == "Server unreachable"
    assert not main_window.connection_banner.isHidden()
    text = main_window.connection_banner.message_label.text()
    assert main_window._connection_down_since in text
    assert len(main_window._connection_down_since) == 5  # HH:MM
    assert not main_window.command_bar.open_session_button.isEnabled()
    assert main_window.session_tabs.bridge.shell["serverDown"] is True


def test_retry_recovers_hides_the_banner_and_says_so(main_window, qtbot, reach):
    reach["ok"] = False
    _check(main_window, qtbot)
    reach["ok"] = True
    main_window.connection_banner.retry_button.click()
    qtbot.waitUntil(lambda: main_window._connection_state == "ok", timeout=3000)
    assert main_window.connection_banner.isHidden()
    assert main_window.command_bar.open_session_button.isEnabled()
    assert main_window.session_tabs.bridge.shell["serverDown"] is False
    shown = Toast.for_window(main_window)
    assert shown is not None and shown.text().startswith("Server connected again · ")


def test_a_check_that_was_never_down_says_nothing(main_window, qtbot, reach):
    existing = Toast.for_window(main_window)
    if existing is not None:
        existing.dismiss()
    _check(main_window, qtbot)
    shown = Toast.for_window(main_window)
    assert shown is None or shown.isHidden()


def test_the_sidebars_retry_runs_a_check(main_window, qtbot, reach):
    reach["ok"] = False
    _check(main_window, qtbot)
    before = reach["calls"]
    main_window.sidebar.retry_button.click()
    qtbot.waitUntil(lambda: main_window._connection_state != "checking", timeout=3000)
    assert reach["calls"] == before + 1


def test_the_time_of_the_outage_is_kept_across_failed_retries(
    main_window, qtbot, reach
):
    reach["ok"] = False
    _check(main_window, qtbot)
    main_window._connection_down_since = "14:02"
    _check(main_window, qtbot)
    assert main_window._connection_down_since == "14:02"


def test_a_second_check_while_one_runs_is_ignored(main_window, qtbot, reach):
    main_window.check_connection()
    main_window.check_connection()
    main_window.check_connection()
    qtbot.waitUntil(lambda: main_window._connection_state != "checking", timeout=3000)
    assert reach["calls"] == 1


def test_a_failed_session_start_checks_the_server(main_window, qtbot, reach):
    reach["ok"] = False
    main_window._cleanup_failed_session_start()
    qtbot.waitUntil(lambda: main_window._connection_state == "down", timeout=3000)
    assert not main_window.connection_banner.isHidden()


def test_starting_from_sessions_is_refused_while_down(
    main_window, qtbot, reach, monkeypatch, tmp_path
):
    reach["ok"] = False
    _check(main_window, qtbot)
    started = []
    monkeypatch.setattr(
        main_window, "start_shopify_packing_session",
        lambda **kwargs: started.append(kwargs) or True,
    )
    main_window._start_or_resume_from_browser(
        "TESTCL", "DHL_Orders", tmp_path, tmp_path / "DHL_Orders.json",
        work_dir=tmp_path,
    )
    assert started == []
    shown = Toast.for_window(main_window)
    assert shown is not None
    assert shown.text() == "Server unreachable. Sessions cannot be opened until it answers."


def test_end_session_is_disabled_while_down(main_window_with_list, qtbot, reach):
    window = main_window_with_list
    window.current_packing_list = "DHL_Orders"
    window.enable_packing_mode()
    assert window.toolbar_end_btn.isEnabled()
    reach["ok"] = False
    _check(window, qtbot)
    assert not window.toolbar_end_btn.isEnabled()
    assert window.packer_mode_button.isEnabled()  # Start packing stays live


def test_a_work_folder_that_cannot_be_made_reports_and_checks(
    main_window, qtbot, reach, monkeypatch, tmp_path
):
    """Starting a new list on a dead share fails before the session start."""
    from packing_tool.session_manager import SessionManager

    def gone(self, **_kwargs):
        raise OSError("share is gone")

    monkeypatch.setattr(SessionManager, "get_packing_work_dir", gone)
    reach["ok"] = False
    main_window._start_or_resume_from_browser(
        "TESTCL", "DHL_Orders", tmp_path, tmp_path / "DHL_Orders.json",
    )
    qtbot.waitUntil(lambda: main_window._connection_state == "down", timeout=3000)
    session = main_window.session_tabs.bridge.session
    assert session["state"] == "failed"
    assert session["title"] == "Session could not be opened"
    assert session["text"] == "The work folder for DHL_Orders could not be made: share is gone."
    assert main_window.logic is None


def test_a_failed_session_end_checks_the_server(
    main_window_with_list, qtbot, reach, monkeypatch, tmp_path
):
    window = main_window_with_list
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("")
    window.current_work_dir = str(blocker)  # reports/ cannot be made under a file
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    reach["ok"] = False
    window.end_session()
    qtbot.waitUntil(lambda: window._connection_state == "down", timeout=3000)
    assert not window.connection_banner.isHidden()


def test_a_check_that_outlives_the_window_does_not_raise(
    config_ini, qapp, monkeypatch
):
    """The worker thread emits on a QObject that is gone by then."""
    import threading

    import shiboken6

    from packing_tool.profile_manager import ProfileManager

    release = threading.Event()

    def slow(_path, _timeout=5):
        release.wait(3)
        return True

    monkeypatch.setattr(mw, "test_path_reachable", slow)
    ProfileManager(config_path=str(config_ini)).create_client_profile("ALPHA", "Alpha")
    window = mw.MainWindow(config_path=str(config_ini))
    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args.exc_value))
    window.check_connection()
    window.sessions.shutdown()
    shiboken6.delete(window)
    release.set()
    for thread in threading.enumerate():
        if thread.name == "connection-check":
            thread.join(3)
    assert errors == []
