"""What the pages show after they were hidden (spec section 8), in a real Chromium."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS


def _eval(qtbot, view, expr, timeout=5000):
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def _bridge_ready(qtbot, view):
    # Until the page has loaded there is nothing to read back: not ready yet.
    try:
        return _eval(qtbot, view, "document.documentElement.dataset.bridge") == "ready"
    except ValueError:
        return False


def _settle(qtbot, bridge):
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


def _logic(session_factory, packer_logic_factory, session_id, order, sku):
    orders = [(order, "DHL", [{"sku": sku, "quantity": 1, "product_name": f"Product {sku}"}])]
    _session, work_dir, list_path = session_factory(
        client_id="TESTCL", session_id=session_id, orders=orders)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    return logic


def _open(window, logic, session_id):
    window.logic = logic
    window.current_packing_list = "DHL_Orders"
    window.current_session_path = f"/sessions/{session_id}"
    window.enable_packing_mode()


@pytest.fixture
def shown(main_window, qtbot):
    main_window.show()
    qtbot.waitExposed(main_window)
    view = main_window.session_tabs.view
    qtbot.waitUntil(lambda: _bridge_ready(qtbot, view), timeout=20000)
    yield main_window
    main_window.hide()


@pytest.mark.parametrize("page, a_text, b_text", [
    (PAGE_PACKING, "#A-1001", "#B-2002"),
    (PAGE_STATISTICS, "SKU-AAA", "SKU-BBB"),
])
def test_a_page_shown_after_being_hidden_holds_the_current_session_only(
    shown, qtbot, session_factory, packer_logic_factory, page, a_text, b_text
):
    window = shown
    pages = window.session_tabs
    view, bridge = pages.view, pages.bridge
    pages.setCurrentIndex(page)
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, bridge)
    assert a_text in _eval(qtbot, view, "document.body.textContent")

    pages.setCurrentIndex(PAGE_BROWSER)          # the view is hidden
    window._teardown_session()                   # session A ends
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-02_1", "B-2002", "SKU-BBB"),
          "2026-01-02_1")
    pushed = bridge.revision

    pages.setCurrentIndex(page)                  # shown again
    _settle(qtbot, bridge)
    assert bridge.painted_revision >= pushed
    text = _eval(qtbot, view, "document.body.textContent")
    assert b_text in text
    assert a_text not in text


def test_start_packing_waits_for_the_covered_page_to_paint(
    shown, qtbot, session_factory, packer_logic_factory
):
    window = shown
    bridge = window.session_tabs.bridge
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, bridge)

    window.switch_to_packer_mode()
    assert bridge.covered is True
    # Not yet: the page has not reported the covered revision.
    assert window.stacked_widget.currentWidget() is window.session_widget
    window.switch_to_packer_mode()  # a second click while waiting is ignored
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.packer_mode_widget,
        timeout=5000,
    )

    window.switch_to_session_view()
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.session_widget,
        timeout=5000,
    )
    assert bridge.covered is False


def test_a_session_ended_inside_packer_mode_leaves_no_trace_in_the_page(
    shown, qtbot, session_factory, packer_logic_factory
):
    window = shown
    view, bridge = window.session_tabs.view, window.session_tabs.bridge
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, bridge)
    window.switch_to_packer_mode()
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.packer_mode_widget,
        timeout=5000,
    )
    window._teardown_session()
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.session_widget,
        timeout=5000,
    )
    _settle(qtbot, bridge)
    assert "#A-1001" not in _eval(qtbot, view, "document.body.textContent")
    assert _eval(qtbot, view, "!document.getElementById('no-session').hidden") is True


def test_the_shortcuts_still_work_after_a_click_in_the_page(
    shown, qtbot, session_factory, packer_logic_factory, monkeypatch
):
    window = shown
    pages = window.session_tabs
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, pages.bridge)
    ended = []
    monkeypatch.setattr(window, "end_session", lambda: ended.append(1))
    window.toolbar_end_btn.clicked.disconnect()
    window.toolbar_end_btn.clicked.connect(lambda: window.end_session())

    target = pages.view.focusProxy() or pages.view
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=target.rect().center())
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: pages.currentIndex() == PAGE_STATISTICS, timeout=3000)
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: pages.currentIndex() == PAGE_PACKING, timeout=3000)
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: ended == [1], timeout=3000)
