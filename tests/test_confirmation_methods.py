"""Confirm clicks ("manual") and Force ("force_confirmed") are not scans.

The metric once knew only manual, so Force was never counted. How Session
details names each kind is in tests/test_session_details_payload.py.
"""

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


def test_manual_confirms_count_confirm_and_force_units():
    metrics = compute_order_timing_metrics([_order()])
    assert metrics["total_manual_confirms"] == 4  # 1 manual + 3 forced; the scan is not counted
