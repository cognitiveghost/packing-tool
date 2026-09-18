"""The order document's payload: pure functions, no Qt, no Chromium.

Spec: docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md
"""

from gui.packer_bridge import item_rows

ITEMS = [
    {"SKU": "TS-4409-B", "Product_Name": "Wireless Mouse", "Quantity": 3},
    {"SKU": "TS-9002-C", "Product_Name": "Desk Lamp", "Quantity": 2},
    {"SKU": "BX-3311-A", "Product_Name": "Laptop Stand", "Quantity": 8},
]


def _state(*packed):
    return [
        {
            "original_sku": item["SKU"],
            "normalized_sku": item["SKU"].replace("-", "").upper(),
            "required": int(item["Quantity"]),
            "packed": p,
            "row": i,
        }
        for i, (item, p) in enumerate(zip(ITEMS, packed))
    ]


def test_state_follows_packed_against_required():
    rows = item_rows(ITEMS, _state(3, 1, 0), {})
    assert [r["state"] for r in rows] == ["complete", "partial", "pending"]


def test_a_complete_row_offers_undo_and_nothing_else_but_map():
    row = item_rows(ITEMS, _state(3, 0, 0), {})[0]
    assert (row["confirm"], row["undo"], row["force"]) == (False, True, False)


def test_confirm_shows_while_the_row_is_unfinished():
    rows = item_rows(ITEMS, _state(0, 1, 0), {})
    assert [r["confirm"] for r in rows] == [True, True, True]


def test_undo_appears_only_once_something_is_packed():
    rows = item_rows(ITEMS, _state(0, 1, 0), {})
    assert [r["undo"] for r in rows] == [False, True, False]


def test_force_needs_more_than_five_required_and_an_unfinished_row():
    rows = item_rows(ITEMS, _state(0, 0, 0), {})
    assert [r["force"] for r in rows] == [False, False, True]
    finished = item_rows(ITEMS, _state(0, 0, 8), {})
    assert finished[2]["force"] is False


def test_map_shows_only_for_a_sku_no_barcode_maps_to():
    rows = item_rows(ITEMS, _state(0, 0, 0), {"4006381333931": "TS-4409-B"})
    assert [r["map"] for r in rows] == [False, True, True]


def test_an_item_with_no_state_entry_reads_as_nothing_packed():
    rows = item_rows(ITEMS, [], {})
    assert [(r["packed"], r["state"]) for r in rows] == [
        (0, "pending"),
        (0, "pending"),
        (0, "pending"),
    ]


def test_a_non_numeric_quantity_counts_as_one():
    rows = item_rows([{"SKU": "X", "Product_Name": "Odd", "Quantity": ""}], [], {})
    assert rows[0]["required"] == 1


def test_rows_carry_no_just_changed_tint_by_default():
    assert all(
        r["just_changed"] is False for r in item_rows(ITEMS, _state(1, 1, 1), {})
    )
