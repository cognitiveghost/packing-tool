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

from typing import Any

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


def courier_totals(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Orders per courier, ordered by courier name.

    Orders only: S1's courier card is one number over "DPD · orders".
    """
    if df is None or df.empty or "Courier" not in df.columns:
        return []

    grouped = (
        df.groupby("Courier").agg({"Order_Number": "nunique"}).reset_index()
    )
    # itertuples, not iterrows: 5-10x faster over the same rows.
    return [
        {"courier": row.Courier, "orders": int(row.Order_Number)}
        for row in grouped.itertuples(index=False)
    ]


def sku_summary(
    df: pd.DataFrame, session_packing_state: dict[str, Any]
) -> list[dict[str, Any]]:
    """One row per distinct SKU: what the session needs, and what is packed."""
    if df is None or df.empty:
        return []

    totals = (
        df.groupby(["SKU", "Product_Name"])
        .agg({"Quantity": lambda x: pd.to_numeric(x, errors="coerce").sum()})
        .reset_index()
    )

    state = session_packing_state or {}
    packed_by_sku = _packed_by_sku(df, state)

    rows = []
    for row in totals.itertuples(index=False):
        required = int(row.Quantity) if pd.notna(row.Quantity) else 0
        packed = packed_by_sku.get(row.SKU, 0)
        if packed >= required > 0:
            sku_state = "packed"
        elif packed > 0:
            sku_state = "partial"
        else:
            sku_state = "pending"
        rows.append(
            {
                "sku": row.SKU,
                "product": row.Product_Name,
                "required": required,
                "packed": packed,
                "state": sku_state,
            }
        )
    return rows


def _packed_by_sku(df: pd.DataFrame, state: dict[str, Any]) -> dict[str, int]:
    """Units packed per SKU: in-progress scans plus everything in a closed order."""
    packed: dict[str, int] = {}

    for order_state in state.get("in_progress", {}).values():
        for item_state in order_state:
            # A restored session can carry a non-dict here. Skip it rather
            # than let one bad entry take the whole screen down.
            if not isinstance(item_state, dict):
                continue
            sku = item_state.get("original_sku")
            if sku:
                packed[sku] = packed.get(sku, 0) + int(item_state.get("packed", 0) or 0)

    completed = state.get("completed_orders", [])
    if completed:
        closed = df[df["Order_Number"].isin(completed)]
        if not closed.empty:
            # Vectorised: O(n) instead of the nested per-order loop this
            # replaced.
            by_sku = (
                closed.groupby("SKU")["Quantity"]
                .apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
                .fillna(0)
                .astype(int)
            )
            for sku, qty in by_sku.items():
                packed[sku] = packed.get(sku, 0) + int(qty)

    return packed
