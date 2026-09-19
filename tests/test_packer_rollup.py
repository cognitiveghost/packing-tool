"""One row per distinct SKU, summed across the order's lines.

The SKU list shows one row per line of the order. The roll-up consolidates
them, which is what the four-column summary table did before Bundle 4 replaced
it with a single count.
"""

from gui.packer_bridge import sku_rollup


def _row(sku, product, packed, required):
    return {"sku": sku, "product": product, "packed": packed, "required": required}


def test_two_lines_of_one_sku_become_one_row():
    rows = [_row("A-1", "Mouse", 1, 2), _row("A-1", "Mouse", 0, 3)]
    assert sku_rollup(rows) == [
        {
            "sku": "A-1",
            "product": "Mouse",
            "packed": 1,
            "required": 5,
            "state": "partial",
        }
    ]


def test_state_is_complete_only_when_every_unit_is_packed():
    rows = [_row("A-1", "Mouse", 2, 2), _row("B-2", "Cable", 0, 1)]
    assert [r["state"] for r in sku_rollup(rows)] == ["complete", "pending"]


def test_rows_are_ordered_by_sku_so_the_block_does_not_reshuffle_mid_order():
    rows = [_row("B-2", "Cable", 0, 1), _row("A-1", "Mouse", 0, 1)]
    assert [r["sku"] for r in sku_rollup(rows)] == ["A-1", "B-2"]


def test_no_rows_is_an_empty_roll_up():
    assert sku_rollup([]) == []
