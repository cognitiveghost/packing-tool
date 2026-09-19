"""Session aggregation, with no window in sight.

These three functions carry ~145 lines that used to live inside
MainWindow._update_statistics, where testing them meant building a window.
"""

import pandas as pd

from packing_tool.session_stats import courier_totals, session_totals, sku_summary


def _df():
    return pd.DataFrame(
        [
            {
                "Order_Number": "#1",
                "SKU": "A-1",
                "Product_Name": "Mouse",
                "Quantity": 2,
                "Courier": "DPD",
            },
            {
                "Order_Number": "#1",
                "SKU": "B-2",
                "Product_Name": "Cable",
                "Quantity": 1,
                "Courier": "DPD",
            },
            {
                "Order_Number": "#2",
                "SKU": "A-1",
                "Product_Name": "Mouse",
                "Quantity": 3,
                "Courier": "GLS",
            },
        ]
    )


def test_totals_count_orders_lines_and_distinct_skus():
    totals = session_totals(_df(), [])
    assert totals["orders"] == 2
    assert totals["items"] == 3
    assert totals["unique_skus"] == 2


def test_progress_is_the_share_of_orders_completed():
    assert session_totals(_df(), ["#1"])["progress_pct"] == 50
    assert session_totals(_df(), ["#1", "#2"])["progress_pct"] == 100


def test_an_empty_session_does_not_divide_by_zero():
    empty = pd.DataFrame(
        columns=["Order_Number", "SKU", "Product_Name", "Quantity", "Courier"]
    )
    totals = session_totals(empty, [])
    assert totals == {
        "orders": 0,
        "completed": 0,
        "items": 0,
        "unique_skus": 0,
        "progress_pct": 0,
    }


def test_courier_totals_count_orders_and_summed_quantity():
    assert courier_totals(_df()) == [
        {"courier": "DPD", "orders": 1, "items": 3},
        {"courier": "GLS", "orders": 1, "items": 3},
    ]


def test_a_session_with_no_courier_column_has_no_courier_totals():
    assert courier_totals(_df().drop(columns=["Courier"])) == []


def test_sku_summary_sums_quantity_across_orders():
    rows = sku_summary(_df(), {})
    assert [(r["sku"], r["required"]) for r in rows] == [("A-1", 5), ("B-2", 1)]


def test_an_untouched_sku_is_pending():
    assert sku_summary(_df(), {})[0]["state"] == "pending"


def test_a_partly_scanned_sku_is_partial_and_a_finished_one_is_packed():
    # session_packing_state's real shape (see packer_logic.py) nests each
    # order's item states under "in_progress"; the plan's original test used
    # a bare {"#1": [...]} which _packed_by_sku's state.get("in_progress", {})
    # would silently read as empty.
    state = {
        "in_progress": {
            "#1": [
                {"original_sku": "A-1", "packed": 2},
                {"original_sku": "B-2", "packed": 1},
            ]
        }
    }
    by_sku = {r["sku"]: r for r in sku_summary(_df(), state)}
    assert by_sku["A-1"]["state"] == "partial"
    assert by_sku["B-2"]["state"] == "packed"


def test_a_malformed_item_state_is_skipped_rather_than_crashing():
    """A restored session can carry junk; the screen must still draw."""
    state = {
        "in_progress": {"#1": ["not a dict", {"original_sku": "B-2", "packed": 1}]}
    }
    by_sku = {r["sku"]: r for r in sku_summary(_df(), state)}
    assert by_sku["B-2"]["state"] == "packed"
