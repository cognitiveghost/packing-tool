"""MainWindow's answer to each scan outcome, over a real PackerLogic.

tests/test_packer_mainwindow_seam.py stubs the logic to pin the widget calls;
these drive a real list so the outcome and the screen are checked together.
"""

import pytest

from packing_tool.packer_logic import normalize_sku

ORDERS = [
    ("ORD-1", "DHL", [
        {"sku": "SKU-A", "quantity": 1, "product_name": "A"},
        {"sku": "SKU-B", "quantity": 1, "product_name": "B"},
    ]),
    ("ORD-2", "DHL", [{"sku": "SKU-C", "quantity": 6, "product_name": "C"}]),
    ("ORD-3", "DHL", [
        {"sku": "SKU-D", "quantity": 1, "product_name": "D"},
        {"sku": "SKU-E", "quantity": 6, "product_name": "E"},
    ]),
]


@pytest.fixture
def packing(main_window, session_factory, packer_logic_factory, monkeypatch):
    monkeypatch.setattr("gui.main_window.ORDER_CLEAR_MS", 40)
    _session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    logic.item_packed.connect(main_window._on_item_packed)
    logic.all_orders_complete.connect(main_window._on_all_orders_complete)
    main_window.logic = logic
    main_window.current_packing_list = "DHL_Orders"
    return main_window, logic


def _scan(window, *texts):
    for text in texts:
        window.on_scanner_input(text)


def _feedback(window):
    fb = window.packer_mode_widget.bridge.feedback
    return fb["text"], fb["role"]


def test_an_order_already_packed_is_named(packing):
    window, _logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-B", "ORD-1")
    assert _feedback(window) == ("Order ORD-1 is already packed", "warning")


def test_an_unknown_order_is_named(packing):
    window, _logic = packing
    _scan(window, "NOPE-9")
    assert _feedback(window) == ("No order matches NOPE-9", "danger")


def test_another_orders_barcode_mid_order_is_named_as_an_order(packing):
    window, logic = packing
    _scan(window, "ORD-1", "ORD-2")
    assert _feedback(window) == ("ORD-2 is an order. Finish or skip ORD-1 first.", "warning")
    assert logic.current_order_number == "ORD-1"


def test_an_extra_item_shows_in_the_extras_panel(packing):
    window, _logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-A")
    assert window.packer_mode_widget.bridge.extras == [{"sku": normalize_sku("SKU-A"), "count": 1}]
    assert _feedback(window) == ("Extra item scanned — keep it or remove it", "warning")


def test_the_last_item_with_an_extra_pending_holds_the_order_open(packing):
    window, logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-A", "SKU-B")
    assert logic.current_order_number == "ORD-1"
    assert "ORD-1" not in logic.session_packing_state["completed_orders"]
    assert _feedback(window) == ("Review the extra items before this order can close", "warning")


@pytest.mark.parametrize("answer", ["_on_extra_confirmed", "_on_extra_removed"])
def test_resolving_the_last_extra_completes_the_order(packing, answer):
    window, logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-A", "SKU-B")
    getattr(window, answer)(normalize_sku("SKU-A"))
    assert logic.current_order_number is None
    assert "ORD-1" in logic.session_packing_state["completed_orders"]
    assert window.packer_mode_widget.bridge.history[0] == {"order": "ORD-1", "status": "complete"}


def test_removing_an_extra_before_the_order_is_done_says_so(packing):
    window, logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-A")
    window._on_extra_removed(normalize_sku("SKU-A"))
    assert _feedback(window) == ("Extra cleared — continue scanning", "success")
    assert logic.current_order_number == "ORD-1"


def test_force_confirm_on_the_last_line_completes_the_order(packing):
    window, logic = packing
    _scan(window, "ORD-2")
    window._on_force_confirm(0)
    assert logic.current_order_number is None
    assert "ORD-2" in logic.session_packing_state["completed_orders"]
    assert window.packer_mode_widget.bridge.history[0]["order"] == "ORD-2"


def test_force_confirm_with_an_extra_pending_asks_for_the_extras(packing):
    """Force confirm packs the last line, but an extra still waits: the order stays open."""
    window, logic = packing
    _scan(window, "ORD-3", "SKU-D", "SKU-D")  # SKU-D done, then one extra; SKU-E pending
    row_e = next(s["row"] for s in logic.current_order_state if s["normalized_sku"] == normalize_sku("SKU-E"))
    window._on_force_confirm(row_e)
    assert logic.current_order_number == "ORD-3"
    assert "ORD-3" not in logic.session_packing_state["completed_orders"]
    assert _feedback(window) == ("Review the extra items before this order can close", "warning")
    assert window.packer_mode_widget.bridge.extras == [{"sku": normalize_sku("SKU-D"), "count": 1}]


def test_the_last_order_shows_session_complete_and_the_held_reset_keeps_it(packing, qtbot):
    window, logic = packing
    widget = window.packer_mode_widget
    _scan(window, "ORD-1", "SKU-A", "SKU-B", "ORD-2")
    window._on_force_confirm(0)
    _scan(window, "ORD-3", "SKU-D")
    row_e = next(s["row"] for s in logic.current_order_state if s["normalized_sku"] == normalize_sku("SKU-E"))
    window._on_force_confirm(row_e)
    qtbot.waitUntil(lambda: bool(widget.bridge.sessionEnd), timeout=2000)
    qtbot.wait(150)  # past ORDER_CLEAR_MS: the order's reset must not wipe the panel
    assert widget.bridge.sessionEnd
