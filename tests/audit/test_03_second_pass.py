"""Audit 03: second pass over packing metrics.

Report: docs/audit/03-second-pass.md. The AUDIT-03-k test fails because of
the bug it names and is marked xfail(strict=True); the fix removes the marker.
"""

import pytest

from packing_tool.packer_logic import compute_order_timing_metrics


def _order(duration, units, offsets):
    return {
        "duration_seconds": duration,
        "items_count": units,
        "items": [{"time_from_order_start_seconds": t} for t in offsets],
    }


@pytest.mark.xfail(strict=True, reason="AUDIT-03-1: averages scan offsets, not time per item")
def test_avg_time_per_item_is_order_time_over_units():
    orders = [
        _order(30, 3, [10, 20, 30]),  # 10 s per item
        _order(10, 1, [10]),
        _order(0, 5, []),  # untimed: left out, as avg_time_per_order leaves it out
    ]
    metrics = compute_order_timing_metrics(orders)
    assert metrics["avg_time_per_item"] == 10.0  # (30 + 10) / (3 + 1)
    assert metrics["avg_time_per_order"] == 20.0
