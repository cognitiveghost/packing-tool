"""Session aggregation, with no window in sight.

These three functions carry ~145 lines that used to live inside
MainWindow._update_statistics, where testing them meant building a window.
"""

import pandas as pd
from packing_tool.session_stats import session_totals


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
