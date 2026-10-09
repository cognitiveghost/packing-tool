"""What the pages show after they were hidden (spec section 8), in a real Chromium."""

import json
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS
from gui.sessions_payload import session_key


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


def _cover(window):
    """Packer Mode's widget over the shell: since phase 4 the one thing that
    hides the view (spec phase 4, section 10)."""
    window.stacked_widget.setCurrentWidget(window.packer_mode_widget)


def _uncover(window):
    window.stacked_widget.setCurrentWidget(window.session_widget)


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

    _cover(window)                               # the view is hidden
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-02_1", "B-2002", "SKU-BBB"),
          "2026-01-02_1")                        # session B replaces A underneath
    pushed = bridge.revision

    _uncover(window)                             # shown again
    _settle(qtbot, bridge)
    assert bridge.painted_revision >= pushed
    text = _eval(qtbot, view, "document.body.textContent")
    assert b_text in text
    assert a_text not in text


def _stamp(**ago) -> str:
    return (datetime.now().astimezone() - timedelta(**ago)).isoformat()


def _session(session_id, work_dir="") -> dict:
    return {
        "session_id": session_id, "packing_list_name": "DHL_Orders", "status": "completed",
        "worker_name": "Maria", "pc_name": "WH-PC-02",
        "started_at": _stamp(hours=3), "last_updated": _stamp(hours=1),
        "total_orders": 1, "completed_orders": 1, "skipped_orders": 0, "total_items": 1,
        "work_dir": str(work_dir), "session_path": f"/srv/{session_id}", "metrics": None,
    }


def _files(tmp_path, session_id, order):
    work_dir = tmp_path / session_id / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    summary = {
        "session_id": session_id, "packing_list_name": "DHL_Orders",
        "total_orders": 1, "completed_orders": 1, "metrics": {},
        "orders": [{"order_number": order, "duration_seconds": 30, "items_count": 1,
                    "items": [{"sku": "A", "quantity": 1, "row": 0}]}],
        "skipped_orders": [],
    }
    (work_dir / "session_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return work_dir


@pytest.fixture
def sessions(shown, qapp, monkeypatch):
    """The window's Sessions controller on its page, with the registry out of
    the way: what it shows is what the test gives it."""
    page = shown.sessions
    page.wait()
    qapp.processEvents()
    qapp.processEvents()
    monkeypatch.setattr(page, "refresh", lambda: None)
    shown.session_tabs.setCurrentIndex(PAGE_BROWSER)
    return page


def test_sessions_shown_after_being_hidden_holds_the_current_list_only(shown, sessions, qtbot):
    view, bridge = shown.session_tabs.view, shown.session_tabs.bridge
    sessions.show_entries([_session("AAA-111")])
    _settle(qtbot, bridge)
    assert "AAA-111" in _eval(qtbot, view, "document.getElementById('sessions').textContent")

    _cover(shown)
    sessions.show_entries([_session("BBB-222")])
    pushed = bridge.revision

    _uncover(shown)
    _settle(qtbot, bridge)
    assert bridge.painted_revision >= pushed
    text = _eval(qtbot, view, "document.getElementById('sessions').textContent")
    assert "BBB-222" in text
    assert "AAA-111" not in text


def test_details_shown_after_being_hidden_hold_the_current_session_only(
    shown, sessions, qtbot, tmp_path
):
    view, bridge = shown.session_tabs.view, shown.session_tabs.bridge
    a = _session("AAA-111", _files(tmp_path, "AAA-111", "#A-1001"))
    b = _session("BBB-222", _files(tmp_path, "BBB-222", "#B-2002"))
    sessions.show_entries([a, b])

    def open_details(entry):
        sessions.open_details(session_key(entry))
        qtbot.waitUntil(lambda: bridge.details.get("state") == "ready", timeout=10000)

    open_details(a)
    assert bridge.page == "details"
    _settle(qtbot, bridge)
    assert "A-1001" in _eval(qtbot, view, "document.getElementById('details').textContent")

    _cover(shown)
    open_details(b)
    pushed = bridge.revision

    _uncover(shown)
    _settle(qtbot, bridge)
    assert bridge.painted_revision >= pushed
    text = _eval(qtbot, view, "document.getElementById('details').textContent")
    assert "B-2002" in text
    assert "A-1001" not in text
    assert _eval(qtbot, view, "document.getElementById('d-id').textContent") == "BBB-222"


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
