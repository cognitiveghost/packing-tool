"""The rail and the pages behind it are one object with two faces.

MainWindow is expensive to construct, so this module builds one and shares it.
"""

import pytest
from PySide6.QtWidgets import QTabWidget

from gui.main_window import (
    PAGE_BROWSER,
    PAGE_PACKING,
    PAGE_STATISTICS,
    RAIL_ITEMS,
    MainWindow,
    order_summary,
)
from gui.session_browser.session_browser_widget import SessionBrowserWidget


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
    mw.deleteLater()


def test_the_tab_bar_is_hidden_but_the_tab_widget_survives(window):
    """Swapping QTabWidget for QStackedWidget would rewrite every call site
    to produce a screen no user can tell apart."""
    assert isinstance(window.session_tabs, QTabWidget)
    assert not window.session_tabs.tabBar().isVisible()


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


def test_session_browser_is_a_page_not_a_dialog(window):
    page = window.session_tabs.widget(PAGE_BROWSER)
    assert isinstance(page, SessionBrowserWidget)
    assert page is window.session_browser


def test_open_session_browser_navigates_instead_of_opening_a_dialog(window):
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    window.open_session_browser()
    assert window.session_tabs.currentIndex() == PAGE_BROWSER


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


def test_the_browsers_signals_are_still_wired_to_main_window(window):
    """Both signals keep their names and payloads; only the receiver moved off
    a throwaway QDialog and onto the window itself."""
    browser = window.session_browser
    assert _is_connected(browser, "start_packing_requested")
    assert _is_connected(browser, "resume_session_requested")


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
    assert window.sku_mapping_button is bar.sku_mapping_button
    assert window.toolbar_end_btn is bar.end_session_button


def test_the_old_menu_actions_live_in_the_overflow(window):
    labels = [a.text() for a in window.command_bar.overflow.actions() if a.text()]
    assert labels == [
        "Select worker…",
        "Server connection…",
        "Toggle dark/light theme",
        "Exit",
    ]
    assert "Session Browser" not in labels  # a destination, reached by the rail


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
    assert window.command_bar.session_label.isHidden()
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    assert not window.command_bar.session_label.isHidden()


def test_auto_refresh_is_quiet_while_the_browser_page_is_not_shown(window, monkeypatch):
    """As a dialog the timer died on close. As a permanent page it must not put
    a registry rescan on the warehouse share while the packer is scanning."""
    browser = window.session_tabs.widget(PAGE_BROWSER)
    browser._auto_refresh_enabled = True

    refreshes = []
    monkeypatch.setattr(browser.sessions_list, "refresh", lambda: refreshes.append(1))

    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    browser._on_auto_refresh()
    assert refreshes == []
    assert browser._refresh_timer.isActive()  # still armed for the next visit


@pytest.mark.parametrize(
    "args, text",
    [
        ((5, 2, 1), "5 orders · 2 packed · 1 in progress"),
        ((1, 1, 0), "1 order · 1 packed · 0 in progress"),
        ((0, 0, 0), ""),
    ],
)
def test_order_summary(args, text):
    assert order_summary(*args) == text


def test_the_message_line_is_gone(window):
    """Its texts became toasts (spec E5). It also hid a bug: session teardown
    overwrote "Report saved to <path>" before anyone could read it."""
    assert not hasattr(window, "status_label")


def test_the_status_bar_is_the_artboards_strip(window):
    bar = window.statusBar()
    assert bar.minimumHeight() == bar.maximumHeight() == 40
    assert window.sb_worker_label.text() == window.current_worker_name
    assert window.sb_session_label.text() == "—"
