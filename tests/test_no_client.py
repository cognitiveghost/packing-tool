"""Frame 2a: no client chosen (spec 2026-10-08 section 6.6)."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence, QShortcut

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS, MainWindow
from packing_tool.profile_manager import ProfileManager


@pytest.fixture
def remembered():
    settings = QSettings("PackingTool", "ClientSelection")
    settings.remove("last_client")
    yield settings
    settings.remove("last_client")


def _window(config_ini, clients):
    seed = ProfileManager(config_path=str(config_ini))
    for client_id in clients:
        seed.create_client_profile(client_id, f"{client_id} name")
    return MainWindow(config_path=str(config_ini))


def _assert_no_client(window):
    assert window.current_client_id is None
    assert window.client_combo.currentIndex() == -1
    assert not window.no_client_panel.isHidden()
    assert window.session_tabs.isHidden()
    assert not any(window.nav_rail.button(i).isEnabled() for i in range(3))
    assert not window.sidebar.sku_button.isEnabled()
    assert not window.command_bar.open_session_button.isEnabled()


def _assert_client(window, client_id):
    assert window.current_client_id == client_id
    assert window.no_client_panel.isHidden()
    assert not window.session_tabs.isHidden()
    assert all(window.nav_rail.button(i).isEnabled() for i in range(3))
    assert window.sidebar.sku_button.isEnabled()
    assert window.command_bar.open_session_button.isEnabled()


def test_two_clients_and_nothing_remembered_starts_on_choose_a_client(
    config_ini, qapp, remembered
):
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        _assert_no_client(window)
        panel = window.no_client_panel
        assert panel.button.text() == "Choose a client"
    finally:
        window.deleteLater()


def test_a_single_client_is_selected(config_ini, qapp, remembered):
    window = _window(config_ini, ["ALPHA"])
    try:
        _assert_client(window, "ALPHA")
    finally:
        window.deleteLater()


def test_a_remembered_client_is_restored(config_ini, qapp, remembered):
    remembered.setValue("last_client", "BETA")
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        _assert_client(window, "BETA")
    finally:
        window.deleteLater()


def test_a_remembered_client_that_no_longer_exists_is_not_restored(
    config_ini, qapp, remembered
):
    remembered.setValue("last_client", "GONE")
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        _assert_no_client(window)
    finally:
        window.deleteLater()


def test_no_clients_at_all_shows_the_panel_without_a_button(config_ini, qapp, remembered):
    window = _window(config_ini, [])
    try:
        assert window.current_client_id is None
        assert not window.no_client_panel.isHidden()
        assert window.no_client_panel.button.isHidden()
    finally:
        window.deleteLater()


def test_choosing_a_client_brings_the_pages_back(config_ini, qapp, remembered):
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        window.client_combo.setCurrentIndex(window.client_combo.findData("BETA"))
        _assert_client(window, "BETA")
    finally:
        window.deleteLater()


def test_the_panels_button_opens_the_selector(config_ini, qapp, remembered, monkeypatch):
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        opened = []
        monkeypatch.setattr(window.client_combo, "showPopup", lambda: opened.append(1))
        window.no_client_panel.button.click()
        assert opened == [1]
    finally:
        window.deleteLater()


def _shortcut(window, keys):
    found = [s for s in window.findChildren(QShortcut) if s.key() == QKeySequence(keys)]
    assert len(found) == 1, keys
    return found[0]


def test_ctrl_1_2_3_switch_pages(main_window):
    _shortcut(main_window, "Ctrl+3").activated.emit()
    assert main_window.session_tabs.currentIndex() == PAGE_BROWSER
    _shortcut(main_window, "Ctrl+2").activated.emit()
    assert main_window.session_tabs.currentIndex() == PAGE_STATISTICS
    _shortcut(main_window, "Ctrl+1").activated.emit()
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING


def test_the_shortcuts_do_nothing_in_packer_mode(main_window):
    """The scanner owns Packer Mode: the page behind it must not change."""
    main_window.switch_to_packer_mode()
    _shortcut(main_window, "Ctrl+3").activated.emit()
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING
    assert main_window.stacked_widget.currentWidget() is main_window.packer_mode_widget


def test_the_shortcuts_do_nothing_without_a_client(config_ini, qapp, remembered):
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        before = window.session_tabs.currentIndex()
        _shortcut(window, "Ctrl+3").activated.emit()
        assert window.session_tabs.currentIndex() == before
    finally:
        window.deleteLater()


def test_a_collapsed_sidebar_is_restored_at_startup(config_ini, qapp, remembered):
    shell = QSettings("PackingTool", "Shell")
    shell.setValue("sidebar_expanded", False)
    try:
        window = _window(config_ini, ["ALPHA"])
        try:
            assert not window.sidebar.is_expanded()
            assert window.command_bar.sidebar_button.toolTip() == "Expand sidebar"
        finally:
            window.deleteLater()
    finally:
        shell.remove("sidebar_expanded")
