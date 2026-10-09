"""MainWindow and the setup pages: the ways in, and the way back (spec section 4.4)."""

import pytest
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from setup_web import eval_js, settle, until_js

import gui.main_window as mw
from gui.main_window import PAGE_STATISTICS
from packing_tool.profile_manager import ProfileManager


def on_setup(window) -> bool:
    return window.stacked_widget.currentWidget() is window.setup_pages


def in_shell(window) -> bool:
    return window.stacked_widget.currentWidget() is window.session_widget


def test_under_test_the_window_starts_on_the_shell_with_the_setup_pages_in_the_stack(main_window):
    assert in_shell(main_window)
    assert main_window.stacked_widget.indexOf(main_window.setup_pages) != -1
    assert main_window.current_worker_name == "Test Worker"
    assert not hasattr(main_window, "_select_worker")
    assert not hasattr(main_window, "open_sku_mapping_dialog")


def test_outside_test_mode_the_window_starts_on_worker_selection(
    config_ini, monkeypatch, qtbot
):
    monkeypatch.setattr(mw, "_under_pytest", lambda: False)
    ProfileManager(config_path=str(config_ini)).create_client_profile("TESTCL", "Test Client")
    window = mw.MainWindow(config_path=str(config_ini))
    try:
        assert on_setup(window)
        bridge = window.setup_pages.bridge
        assert bridge.page == "workers"
        assert bridge.workers["context"] == "startup" and bridge.workers["leave"] == "Quit"
        assert window.current_worker_id is None

        worker = window.worker_manager.create_worker("Ivan")
        bridge.retryWorkers()
        bridge.pickWorker(worker.id)
        qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
        assert window.current_worker_id == worker.id
        assert window.current_worker_name == "Ivan"
        assert window.sidebar.worker_name.toolTip() == "Ivan"
        assert bridge.page == ""
    finally:
        window.sessions.shutdown()
        window.deleteLater()


def test_quit_on_worker_selection_closes_the_window(config_ini, monkeypatch):
    monkeypatch.setattr(mw, "_under_pytest", lambda: False)
    window = mw.MainWindow(config_path=str(config_ini))
    try:
        closed = []
        monkeypatch.setattr(window, "close", lambda: closed.append(1))
        window.setup_pages.bridge.leaveWorkers()
        assert closed == [1]
    finally:
        window.sessions.shutdown()
        window.deleteLater()


def test_switch_worker_opens_the_page_and_back_changes_nothing(main_window, qtbot):
    window = main_window
    window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    window.sidebar.switchWorkerRequested.emit()
    assert on_setup(window)
    payload = window.setup_pages.bridge.workers
    assert payload["context"] == "switch" and payload["leave"] == "Back to Test Worker"

    window.setup_pages.bridge.leaveWorkers()
    qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
    assert window.current_worker_name == "Test Worker"
    assert window.session_tabs.currentIndex() == PAGE_STATISTICS


def test_switching_to_another_worker_tells_the_sidebar(main_window, qtbot):
    window = main_window
    maria = window.worker_manager.create_worker("Maria")
    window.switch_worker()
    window.setup_pages.bridge.pickWorker(maria.id)
    qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
    assert (window.current_worker_id, window.current_worker_name) == (maria.id, "Maria")
    assert window.sidebar.worker_name.toolTip() == "Maria"


def test_sku_mapping_opens_for_the_current_client_and_close_returns(main_window, qtbot):
    window = main_window
    window.sidebar.skuMappingRequested.emit()
    assert on_setup(window)
    bridge = window.setup_pages.bridge
    assert bridge.page == "mapping"
    assert bridge.mapping["client"] == window.client_combo.currentText()
    assert bridge.mapping["quick"] == {}

    bridge.closeMapping()
    qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
    assert bridge.page == ""


def test_opening_twice_is_one_page(main_window):
    main_window.open_sku_mapping()
    main_window.switch_worker()  # ignored: a setup page is already up
    assert main_window.setup_pages.bridge.page == "mapping"


def test_with_no_client_sku_mapping_does_not_open(main_window):
    main_window.current_client_id = None
    main_window.open_sku_mapping()
    assert in_shell(main_window)


def test_a_saved_mapping_reaches_the_open_session(main_window_with_list, qtbot):
    window = main_window_with_list
    window.open_sku_mapping()
    bridge = window.setup_pages.bridge
    assert bridge.addMapping("5906000123456", "TS-4409-B") == ""
    bridge.saveMappings()
    assert window.logic.sku_map["5906000123456"] == "TS-4409-B"
    assert bridge.mapping["saved"] is True
    assert on_setup(window)  # Save stays on the page


def test_ctrl_e_does_nothing_on_a_setup_page(main_window, monkeypatch):
    window = main_window
    shortcut = next(
        s for s in window.findChildren(QShortcut) if s.key() == QKeySequence("Ctrl+E")
    )
    clicks = []
    monkeypatch.setattr(window.toolbar_end_btn, "click", lambda: clicks.append(1))
    window.open_sku_mapping()
    shortcut.activated.emit()
    assert clicks == []


def test_closing_the_window_with_unsaved_mappings_is_refused_and_asked_about(
    main_window, qtbot
):
    window = main_window
    window.open_sku_mapping()
    window.setup_pages.bridge.addMapping("5906000123456", "X")
    event = QCloseEvent()
    with qtbot.waitSignal(window.setup_pages.bridge.leaveAsked, timeout=1000):
        window.closeEvent(event)
    assert not event.isAccepted()
    assert on_setup(window)


@pytest.fixture
def shown(main_window, qtbot):
    main_window.show()
    qtbot.waitExposed(main_window)
    for view in (main_window.session_tabs.view, main_window.setup_pages.view):
        until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    yield main_window
    main_window.hide()


def test_the_setup_document_has_painted_itself_blank_before_the_shell_returns(shown, qtbot):
    """ADR 0003: a hidden view keeps its last frame, so that frame must be the
    blank one, never the mappings of a page that is gone."""
    window = shown
    view, bridge = window.setup_pages.view, window.setup_pages.bridge
    window.open_sku_mapping()
    qtbot.waitUntil(lambda: on_setup(window), timeout=3000)
    settle(qtbot, bridge)
    assert "SKU mapping" in eval_js(qtbot, view, "document.body.innerText")

    at_switch = []
    window.stacked_widget.currentChanged.connect(
        lambda _index: at_switch.append((bridge.page, bridge.painted_revision >= bridge.revision))
    )
    bridge.closeMapping()
    qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
    assert at_switch == [("", True)]
    assert window.session_tabs.bridge.covered is False
