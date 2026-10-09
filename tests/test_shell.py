"""The rail and the pages behind it are one object with two faces.

MainWindow is expensive to construct, so this module builds one and shares it.
"""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QStatusBar

from gui.main_window import (
    PAGE_BROWSER,
    PAGE_PACKING,
    PAGE_STATISTICS,
    RAIL_ITEMS,
    MainWindow,
)


@pytest.fixture(scope="module")
def window(qapp, tmp_path_factory):
    config = tmp_path_factory.mktemp("shell") / "config.ini"
    config.write_text(
        "[Network]\n"
        f"FileServerPath = {tmp_path_factory.mktemp('server')}\n"
        "ConnectionTimeout = 5\n"
        f"LocalCachePath = {tmp_path_factory.mktemp('cache')}\n"
        "[Logging]\n"
        "LogLevel = INFO\nLogRetentionDays = 30\nMaxLogSizeMB = 10\n",
        encoding="utf-8",
    )
    mw = MainWindow(config_path=str(config))
    yield mw
    mw.sessions.shutdown()
    mw.deleteLater()


def test_the_pages_are_one_web_view_and_the_session_browser(window):
    """ADR 0003: Packing and Statistics are two pages of one document."""
    from gui.app_pages import AppPages

    assert isinstance(window.session_tabs, AppPages)
    assert window.session_tabs.widget(PAGE_PACKING) is window.session_tabs.widget(PAGE_STATISTICS)


def test_there_is_one_rail_item_per_page(window):
    assert window.session_tabs.count() == len(RAIL_ITEMS) == 3


def test_the_rail_drives_the_pages(window):
    window.nav_rail.set_current(PAGE_STATISTICS)
    assert window.session_tabs.currentIndex() == PAGE_STATISTICS


def test_the_pages_drive_the_rail_back(window):
    """The back edge is load-bearing: code that jumps pages directly must not
    leave the rail lit on the page the user left."""
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    assert window.nav_rail.current_index() == PAGE_PACKING


def test_the_two_way_binding_does_not_loop(window):
    seen = []
    window.nav_rail.currentChanged.connect(seen.append)
    try:
        window.nav_rail.set_current(PAGE_BROWSER)
        assert seen == [PAGE_BROWSER]
    finally:
        # the window is module-scoped; a live receiver would follow it around
        window.nav_rail.currentChanged.disconnect(seen.append)


def test_sessions_is_a_page_of_the_document(window):
    assert window.session_tabs.widget(PAGE_BROWSER) is window.session_tabs.view
    assert not hasattr(window, "session_browser")


def test_open_session_browser_navigates_instead_of_opening_a_dialog(window):
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    window.open_session_browser()
    assert window.session_tabs.currentIndex() == PAGE_BROWSER
    assert window.session_tabs.bridge.page == "sessions"


def _is_connected(obj, signal_name: str) -> bool:
    """Whether `signal_name` (e.g. "start_packing_requested") has a receiver.

    QObject.isSignalConnected() takes a QMetaMethod, not a SignalInstance --
    finding it by name search avoids hand-mangling the C++ signature string
    (dict -> "QVariantMap") that PySide6's own signal object won't tell you.
    """
    meta = obj.metaObject()
    for i in range(meta.methodCount()):
        method = meta.method(i)
        if bytes(method.methodSignature()).decode().startswith(f"{signal_name}("):
            return obj.isSignalConnected(method)
    raise AssertionError(f"no such signal: {signal_name}")


def test_the_sessions_signals_are_wired_to_main_window(window):
    for name in ("startRequested", "resumeRequested", "showPackingRequested"):
        assert _is_connected(window.sessions, name)


def test_the_browser_handlers_no_longer_take_a_dialog_to_close(window):
    """A page has nothing to accept(); the equivalent is navigating back."""
    import inspect

    for name in (
        "_handle_start_packing_from_browser",
        "_handle_resume_session_from_browser",
    ):
        params = list(inspect.signature(getattr(window, name)).parameters)
        assert len(params) == 1, (
            f"{name} should take only the payload dict, got {params}"
        )


def test_the_order_filter_is_the_bars_and_only_shows_on_the_packing_page(window):
    """It filters the order tree, so it must not claim to filter other pages."""
    assert window.search_input is window.command_bar.filter_input
    window.session_tabs.setCurrentIndex(PAGE_BROWSER)
    assert window.search_input.isHidden()
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    assert not window.search_input.isHidden()


def test_there_is_no_toolbar_and_no_menu_bar(window):
    """Artboard T1: the command bar is the only chrome above the pages."""
    from PySide6.QtWidgets import QMenuBar, QToolBar

    assert window.findChildren(QToolBar) == []
    assert all(not bar.actions() for bar in window.findChildren(QMenuBar))


def test_the_bar_carries_the_session_actions(window):
    bar = window.command_bar
    assert window.packer_mode_button is bar.start_packing_button
    assert window.toolbar_end_btn is bar.end_session_button
    assert not hasattr(window, "sku_mapping_button")


def test_the_overflow_keeps_only_server_connection_and_exit(window):
    """Worker, SKU mapping and the theme moved to the sidebar footer."""
    labels = [a.text() for a in window.command_bar.overflow.actions() if a.text()]
    assert labels == ["Server connection…", "Exit"]


def test_the_sidebar_footer_reaches_what_the_overflow_used_to(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "open_sku_mapping", lambda: calls.append("sku"))
    monkeypatch.setattr(window, "switch_worker", lambda: calls.append("worker"))
    monkeypatch.setattr(window, "_switch_theme", lambda name: calls.append(name))
    window.sidebar.skuMappingRequested.emit()
    window.sidebar.switchWorkerRequested.emit()
    window.sidebar.themeRequested.emit("dark")
    assert calls == ["sku", "worker", "dark"]


def test_ctrl_e_still_ends_the_session_through_the_bar_button(window, monkeypatch):
    from PySide6.QtGui import QKeySequence, QShortcut  # QtGui in Qt 6

    shortcuts = [
        s for s in window.findChildren(QShortcut) if s.key() == QKeySequence("Ctrl+E")
    ]
    assert len(shortcuts) == 1
    clicks = []
    monkeypatch.setattr(window.toolbar_end_btn, "click", lambda: clicks.append(1))
    shortcuts[0].activated.emit()
    assert clicks == [1]


def test_the_bar_follows_the_page(window):
    window.session_tabs.setCurrentIndex(PAGE_BROWSER)
    assert window.command_bar.filter_input.isHidden()
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    assert not window.command_bar.filter_input.isHidden()


def test_auto_refresh_is_quiet_while_sessions_is_not_shown(window, monkeypatch):
    """A permanent page must not put a registry read on the warehouse share
    while the packer is on another page."""
    refreshes = []
    monkeypatch.setattr(window.sessions, "refresh", lambda: refreshes.append(1))
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    window.sessions._on_tick()
    assert refreshes == []
    assert window.sessions._timer.isActive()  # still armed for the next visit


def test_the_message_line_is_gone(window):
    """Its texts became toasts (spec E5). It also hid a bug: session teardown
    overwrote "Report saved to <path>" before anyone could read it."""
    assert not hasattr(window, "status_label")


def test_there_is_no_status_bar(window):
    """ADR 0002. findChild, not statusBar(): statusBar() creates one."""
    assert window.findChild(QStatusBar) is None
    for name in ("sb_session_label", "sb_worker_label", "sb_summary_label",
                 "sb_browser_label"):
        assert not hasattr(window, name)


def test_the_worker_is_in_the_sidebar_footer(window):
    assert window.sidebar.worker_name.toolTip() == window.current_worker_name


def test_the_destinations_are_the_mockups_three(window):
    assert [label for _i, label, _t in RAIL_ITEMS] == ["Packing", "Statistics", "Sessions"]
    tips = [window.nav_rail.button(i).toolTip() for i in range(3)]
    assert tips == ["Packing  Ctrl+1", "Statistics  Ctrl+2", "Sessions  Ctrl+3"]
    assert window.nav_rail is window.sidebar.rail


def test_the_collapse_button_collapses_and_the_choice_is_remembered(window):
    settings = QSettings("PackingTool", "Shell")
    assert window.sidebar.is_expanded()
    window.command_bar.sidebar_button.click()
    try:
        assert not window.sidebar.is_expanded()
        assert window.command_bar.sidebar_button.toolTip() == "Expand sidebar"
        assert settings.value("sidebar_expanded", True, type=bool) is False
    finally:
        window.command_bar.sidebar_button.click()
    assert window.sidebar.is_expanded()
    assert settings.value("sidebar_expanded", True, type=bool) is True


def test_the_window_is_designed_for_1366_by_768(window):
    assert (window.minimumWidth(), window.minimumHeight()) == (1280, 680)





def test_ending_a_session_clears_the_session_tooltip(window):
    window._show_session("2026-09-01_1042", "packing_list_A")
    assert window.command_bar.session_label.toolTip() == "packing_list_A"
    window._show_session(None)
    assert window.command_bar.session_label.text() == ""
    assert window.command_bar.session_label.toolTip() == ""


def test_the_title_names_the_app_and_its_version(window):
    from packing_tool import APP_NAME, __version__

    assert window.windowTitle() == f"{APP_NAME} {__version__}"
