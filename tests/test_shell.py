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


def test_the_search_field_lives_on_the_packing_page(window):
    """It filters the order tree. With three destinations a window-level field
    would claim to filter pages it does not touch."""
    packing_page = window.session_tabs.widget(PAGE_PACKING)
    assert window.search_input.parent() is packing_page


def test_session_browser_is_not_also_a_button_and_a_menu_item(window):
    """It is a destination now. Leaving it in the toolbar and the Session menu
    as well would mean three controls for one page."""
    from PySide6.QtWidgets import QMenu, QPushButton, QToolBar

    labels = {
        b.text() for bar in window.findChildren(QToolBar)
        for b in bar.findChildren(QPushButton)
    }
    assert "Session Browser" not in labels
    assert "Shopify Session" not in labels

    # QMenu, not type(menuBar()): a QMenuBar has no QMenuBar children, so
    # findChildren(QMenuBar) returns [] and the assertion below never ran.
    menu_actions = {
        a.text() for menu in window.menuBar().findChildren(QMenu)
        for a in menu.actions()
    }
    assert "Session Browser..." not in menu_actions


def test_the_toolbar_still_carries_the_session_actions(window):
    """What is left is the session's own state and actions."""
    from PySide6.QtWidgets import QPushButton, QToolBar

    labels = {
        b.text() for bar in window.findChildren(QToolBar)
        for b in bar.findChildren(QPushButton)
    }
    assert {"Start Packing", "SKU Mapping", "End Session"} <= labels


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
    assert browser._refresh_timer.isActive()   # still armed for the next visit
