"""Confirm clicks ("manual") and Force ("force_confirmed") are not scans.

The Orders tab only knew force_confirmed, so every Confirm click read
"✓ scan"; the metric only knew manual, so Force was never counted.
"""

from gui.session_browser.orders_tab import OrdersTab
from packing_tool.packer_logic import compute_order_timing_metrics


def _order():
    return {
        "order_number": "#1001",
        "duration_seconds": 40,
        "items_count": 5,
        "items": [
            {"sku": "A", "quantity": 1},  # older record: no method key means scanned
            {"sku": "B", "quantity": 1, "confirmation_method": "manual"},
            {"sku": "C", "quantity": 3, "confirmation_method": "force_confirmed"},
        ],
    }


def test_each_item_row_names_how_it_was_packed(qtbot):
    tab = OrdersTab({"session_summary": {"orders": [_order()], "skipped_orders": []}})
    qtbot.addWidget(tab)
    order_row = tab.tree.topLevelItem(0)
    assert [order_row.child(i).text(5) for i in range(3)] == ["✓ scan", "manual", "forced"]


def test_the_order_row_flags_both_manual_kinds(qtbot):
    tab = OrdersTab({"session_summary": {"orders": [_order()], "skipped_orders": []}})
    qtbot.addWidget(tab)
    assert tab.tree.topLevelItem(0).text(5) == "manual  forced"


def test_manual_confirms_count_confirm_and_force_units():
    metrics = compute_order_timing_metrics([_order()])
    assert metrics["total_manual_confirms"] == 4  # 1 manual + 3 forced; the scan is not counted
