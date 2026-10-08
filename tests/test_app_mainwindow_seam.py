"""MainWindow and the app document: what crosses, and when (spec sections 7 and 8)."""

from PySide6.QtWidgets import QTabWidget, QTreeWidget

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS
from shared.components.toast import Toast


def _bridge(window):
    return window.session_tabs.bridge


def test_the_qt_tree_tabs_and_statistics_widget_are_gone(main_window):
    assert not main_window.findChildren(QTreeWidget)
    assert not main_window.findChildren(QTabWidget)
    for name in ("order_tree", "statistics_widget", "packing_state_panel",
                 "packing_summary_label", "no_client_panel"):
        assert not hasattr(main_window, name), name


def test_with_no_session_the_document_is_told_so(main_window):
    bridge = _bridge(main_window)
    assert bridge.session["state"] == "none"
    assert bridge.packing == {} and bridge.statistics == {}
    assert bridge.shell == {"client": True, "clients": True, "serverDown": False}


def test_a_loaded_list_reaches_both_pages(main_window_with_list):
    window = main_window_with_list
    bridge = _bridge(window)
    assert bridge.session["state"] == "open"
    assert bridge.session["list"] == "DHL_Orders"
    assert bridge.session["meta"] == "2 orders · DHL"
    assert bridge.packing["totals"]["orders"] == 2
    assert bridge.statistics["orders"] == 2
    assert [c["name"] for c in bridge.statistics["couriers"]] == ["DHL"]


def test_the_filter_field_drives_the_packing_payload(main_window_with_list):
    window = main_window_with_list
    window.search_input.setText("SKU-OTHER")
    packing = _bridge(window).packing
    assert packing["query"] == "SKU-OTHER" and packing["hits"] == 1
    _bridge(window).clearFilter()
    assert window.search_input.text() == ""
    assert _bridge(window).packing["hits"] == 2


def test_the_pages_slots_reach_their_handlers(main_window_with_list, monkeypatch):
    window = main_window_with_list
    called = []
    monkeypatch.setattr(window, "switch_to_packer_mode", lambda: called.append("start"))
    monkeypatch.setattr(window, "end_session", lambda: called.append("end"))
    monkeypatch.setattr(window.client_combo, "showPopup", lambda: called.append("client"))
    bridge = _bridge(window)
    bridge.startPacking()
    bridge.endSession()
    bridge.chooseClient()
    assert called == ["start", "end", "client"]

    window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    bridge.showPage("packing")
    assert window.session_tabs.currentIndex() == PAGE_PACKING
    bridge.openSession()
    assert window.session_tabs.currentIndex() == PAGE_BROWSER


def test_a_scan_in_packer_mode_pushes_nothing_and_leaving_pushes_once(
    main_window_with_list, monkeypatch
):
    window = main_window_with_list
    window.logic.item_packed.connect(window._on_item_packed)
    window.switch_to_packer_mode()
    pushes = []
    real = window._push_pages
    monkeypatch.setattr(window, "_push_pages", lambda: (pushes.append(1), real())[1])
    window.on_scanner_input("#10429")
    window.logic.current_order_state[0]["required"] = 2  # so the scan is not the last one
    window.on_scanner_input("TS-4409-B")
    assert pushes == []
    assert window._pages_stale is True
    window.switch_to_session_view()
    assert pushes == [1]
    assert window._pages_stale is False
    assert _bridge(window).packing["totals"]["packed"] == 1


def test_a_complete_list_reaches_the_bar_and_disables_start_packing(main_window_with_list):
    window = main_window_with_list
    state = window.logic.session_packing_state
    state["completed_orders"] = ["#10429", "#10430"]
    window._push_pages()
    assert _bridge(window).session["complete"] is True
    assert window.toolbar_end_btn.property("role") == "primary"
    assert not window.packer_mode_button.isEnabled()
    state["completed_orders"] = ["#10429"]
    window._push_pages()
    assert window.toolbar_end_btn.property("role") == "secondary"
    assert window.packer_mode_button.isEnabled()


def test_ending_a_session_empties_the_document(main_window_with_list):
    window = main_window_with_list
    window._teardown_session()
    bridge = _bridge(window)
    assert bridge.session["state"] == "none"
    assert bridge.packing == {} and bridge.statistics == {}
    assert window.toolbar_end_btn.property("role") == "secondary"


def test_a_toast_goes_to_qt_while_the_page_is_not_on_screen(main_window):
    raised = []
    _bridge(main_window).toastRaised.connect(lambda message, _undo: raised.append(message))
    main_window._toast("Saved.")
    assert raised == []
    assert Toast.for_window(main_window).text() == "Saved."


def test_a_toast_goes_to_the_page_when_it_is_showing(main_window, qtbot):
    raised = []
    _bridge(main_window).toastRaised.connect(lambda message, _undo: raised.append(message))
    main_window.show()
    qtbot.waitExposed(main_window)
    try:
        main_window._toast("Saved.")
        assert raised == ["Saved."]
        main_window.session_tabs.setCurrentIndex(PAGE_BROWSER)
        main_window._toast("On Sessions.")
        assert raised == ["Saved."]
    finally:
        main_window.hide()
