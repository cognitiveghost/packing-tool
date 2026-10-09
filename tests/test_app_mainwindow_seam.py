"""MainWindow and the app document: what crosses, and when (spec sections 7 and 8)."""

import json

from PySide6.QtWidgets import QMessageBox, QTabWidget, QTreeWidget

from gui.app_bridge import session_payload
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
    window.switch_to_session_view()
    assert pushes == [1]
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
        assert raised == ["Saved.", "On Sessions."]
    finally:
        main_window.hide()


def _broken_list(session_factory):
    orders = [("#1", "DHL", [{"sku": "A", "quantity": 1, "product_name": "A"}])]
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=orders)
    data = json.loads(list_path.read_text(encoding="utf-8"))
    del data["orders"][0]["courier"]
    list_path.write_text(json.dumps(data), encoding="utf-8")
    return session_dir, work_dir, list_path


def test_a_failed_start_is_shown_in_the_page_and_not_in_a_message_box(
    main_window, session_factory, monkeypatch
):
    boxes = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: boxes.append(a))
    session_dir, work_dir, list_path = _broken_list(session_factory)
    seen = []
    bridge = _bridge(main_window)
    bridge.sessionChanged.connect(lambda: seen.append(bridge.session["state"]))

    started = main_window.start_shopify_packing_session(
        packing_list_path=list_path, work_dir=work_dir, session_path=session_dir,
        client_id="TESTCL", packing_list_name="DHL_Orders",
    )

    assert started is False
    assert boxes == []
    assert seen[0] == "opening" and seen[-1] == "failed"
    session = bridge.session
    assert session["title"] == "Packing list could not be loaded"
    assert session["text"] == "DHL_Orders has an order with no courier. Found: items, order_number."
    assert session["list"] == "DHL_Orders"
    assert main_window.logic is None
    assert main_window.current_work_dir is None
    assert not main_window.command_bar.open_session_button.isHidden()


def test_a_start_cannot_be_entered_while_one_is_running(
    main_window, session_factory, monkeypatch, tmp_path
):
    # The start spins the event loop with nothing modal up: a second start
    # from inside it (Open session, Retry) must be refused untouched.
    session_dir, work_dir, list_path = _broken_list(session_factory)
    nested = []
    real_acquire = main_window._acquire_lock

    def acquire(*args):
        # Where a click would land: inside the running start.
        nested.append(main_window.start_shopify_packing_session(
            packing_list_path=list_path, work_dir=work_dir, session_path=session_dir,
            client_id="TESTCL", packing_list_name="Other",
        ))
        before = main_window._last_start
        main_window._start_or_resume_from_browser(
            "TESTCL", "Other", tmp_path, tmp_path / "Other.json", work_dir=tmp_path)
        assert main_window._last_start is before
        return real_acquire(*args)

    monkeypatch.setattr(main_window, "_acquire_lock", acquire)
    bridge = _bridge(main_window)
    lists = []
    bridge.sessionChanged.connect(lambda: lists.append(bridge.session.get("list")))

    main_window.start_shopify_packing_session(
        packing_list_path=list_path, work_dir=work_dir, session_path=session_dir,
        client_id="TESTCL", packing_list_name="DHL_Orders",
    )

    assert nested == [False]
    assert "Other" not in lists  # the refused start never reached the page
    assert _bridge(main_window).session["list"] == "DHL_Orders"
    assert main_window._starting is False


def test_the_window_does_not_close_under_a_running_start(main_window):
    from PySide6.QtGui import QCloseEvent

    main_window._starting = True
    event = QCloseEvent()
    main_window.closeEvent(event)
    assert not event.isAccepted()
    main_window._starting = False


def test_the_worker_steps_reach_the_page(main_window):
    bridge = _bridge(main_window)
    bridge.set_session(session_payload("opening", list_name="L", session_id="S", step=1))
    main_window._on_start_step(2)
    assert (bridge.session["step"], bridge.session["stepName"]) == (2, "Reading saved progress")
    assert (bridge.session["list"], bridge.session["id"]) == ("L", "S")


def test_a_late_step_does_not_replace_a_failure(main_window):
    bridge = _bridge(main_window)
    main_window._show_start_failure("Session could not be opened", "Locked by PACK-02", "L")
    main_window._on_start_step(3)
    assert bridge.session["state"] == "failed"


def test_close_returns_to_no_session(main_window):
    bridge = _bridge(main_window)
    main_window._show_start_failure("Session could not be opened", "Locked by PACK-02", "L")
    bridge.closeFailure()
    assert bridge.session["state"] == "none"


def test_retry_starts_again_with_the_same_arguments(main_window, monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(
        main_window, "start_shopify_packing_session",
        lambda **kwargs: started.append(kwargs) or False,
    )
    main_window._start_or_resume_from_browser(
        "TESTCL", "DHL_Orders", tmp_path, tmp_path / "DHL_Orders.json",
        work_dir=tmp_path,
    )
    assert len(started) == 1
    _bridge(main_window).retryStart()
    assert len(started) == 2
    assert started[1] == started[0]


def test_retry_with_nothing_to_retry_does_nothing(main_window):
    main_window._last_start = None
    _bridge(main_window).retryStart()  # must not raise
    assert _bridge(main_window).session["state"] == "none"


def test_changing_client_drops_a_failure(main_window):
    main_window._show_start_failure("Session could not be opened", "Locked by PACK-02", "L")
    # The fixture starts on the first client listed; switch to the other one.
    other = "TESTCL" if main_window.current_client_id == "OTHERCL" else "OTHERCL"
    main_window.client_combo.setCurrentIndex(main_window.client_combo.findData(other))
    assert _bridge(main_window).session["state"] == "none"


def test_a_failed_start_leaves_the_packing_page_showing(main_window):
    main_window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    main_window._show_start_failure("Session could not be opened", "x", "L")
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING
