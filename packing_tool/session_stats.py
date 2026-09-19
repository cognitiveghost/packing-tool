"""Live aggregation over the current session's packing list.

Pure pandas, no Qt: the Statistics screen reads these three functions and
builds widgets from what they return.

This is deliberately NOT shared/stats_manager.py. That module is a persisted,
cross-tool event log (record_analysis, record_packing, get_global_stats) that
both tools write to a shared JSON file. What is here is the opposite: a
throwaway aggregation over the DataFrame currently in memory, using Packing
Tool's own column names. Putting it in shared/ would push pandas and those
column names into a module Shopify also receives, for no caller.
"""


import pandas as pd


def session_totals(df: pd.DataFrame, completed_orders: list[str]) -> dict[str, int]:
    """Orders, completed orders, lines, distinct SKUs and percent complete."""
    if df is None or df.empty:
        return {
            "orders": 0,
            "completed": 0,
            "items": 0,
            "unique_skus": 0,
            "progress_pct": 0,
        }

    total_orders = int(df["Order_Number"].nunique())
    completed = len(completed_orders or [])
    return {
        "orders": total_orders,
        "completed": completed,
        "items": len(df),
        "unique_skus": int(df["SKU"].nunique()),
        "progress_pct": int(completed / total_orders * 100) if total_orders else 0,
    }
