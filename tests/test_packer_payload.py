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


from gui.packer_bridge import banner_payload, summary_lines

META = {
    "order_type": "Retail",
    "shipping_provider": "DPD",
    "destination_country": "PL",
    "order_min_box": "M",
    "tags": ["repeat customer"],
    "internal_tags": ["checked"],
    "notes": "Fragile -- handle with care",
}


def test_the_banner_carries_bare_values_in_artboard_order():
    assert banner_payload("10429", META) == {
        "order": "10429",
        "chips": ["Retail", "DPD", "PL", "Box M", "repeat customer", "checked"],
        "notes": "Fragile -- handle with care",
    }


def test_pandas_nan_and_blanks_never_reach_a_chip():
    payload = banner_payload(
        "1",
        {
            "order_type": "nan",
            "shipping_provider": "",
            "destination_country": None,
            "order_min_box": "L",
            "tags": ["nan", "urgent"],
            "notes": "nan",
        },
    )
    assert payload == {"order": "1", "chips": ["Box L", "urgent"], "notes": ""}


def test_a_system_note_stands_in_for_a_missing_note():
    assert banner_payload("1", {"system_note": "Split shipment"})["notes"] == (
        "Split shipment"
    )


def test_no_metadata_still_names_the_order():
    assert banner_payload("10429", None) == {
        "order": "10429",
        "chips": [],
        "notes": "",
    }


def test_the_summary_dedupes_repeated_skus():
    rows = [
        {"sku": "A", "required": 2, "packed": 2},
        {"sku": "A", "required": 1, "packed": 0},
        {"sku": "B", "required": 4, "packed": 4},
    ]
    assert summary_lines(rows) == {
        "items_packed": 6,
        "items_total": 7,
        "skus_packed": 1,
        "skus_total": 2,
    }


def test_an_empty_order_summarises_to_zeroes():
    assert summary_lines([]) == {
        "items_packed": 0,
        "items_total": 0,
        "skus_packed": 0,
        "skus_total": 0,
    }


from gui.packer_bridge import flash_role


def test_every_flash_colour_names_a_status_role():
    assert flash_role("green") == "success"
    assert flash_role("orange") == "warning"
    assert flash_role("red") == "danger"


def test_an_unknown_flash_colour_raises_rather_than_passing_through():
    import pytest

    with pytest.raises(KeyError):
        flash_role("purple")


def test_the_saved_state_decides_required_not_the_packing_list():
    # PackerLogic decides completion from order_state['required']
    # (packer_logic.py:1027, 1038, 1096). On a resumed session whose saved
    # state disagrees with the packing list, the document has to agree with
    # the logic or it lies about which lines are done.
    state = _state(2, 0, 0)
    state[0]["required"] = 2
    rows = item_rows(ITEMS, state, {})
    assert rows[0]["required"] == 2
    assert rows[0]["state"] == "complete"


def test_a_state_entry_with_no_required_falls_back_to_the_packing_list():
    # packer_logic.py:440 writes required=0 when a restored entry has none.
    state = _state(0, 0, 0)
    state[0]["required"] = 0
    rows = item_rows(ITEMS, state, {})
    assert rows[0]["required"] == 3


def test_multi_flags_a_line_that_needs_more_than_one_scan():
    rows = item_rows(ITEMS, _state(0, 2, 8), {})
    # Desk Lamp is 2/2 and Laptop Stand 8/8 -- done, so the cue is spent.
    assert [r["multi"] for r in rows] == [True, False, False]


def test_a_single_unit_line_is_never_multi():
    rows = item_rows([{"SKU": "A", "Product_Name": "A", "Quantity": 1}], [], {})
    assert rows[0]["multi"] is False


from gui.packer_bridge import unknown_rows


def test_an_unmatched_scan_becomes_a_row_that_offers_only_mapping():
    rows = unknown_rows(["4006381333931"])
    assert len(rows) == 1
    row = rows[0]
    assert row["sku"] == "4006381333931"
    assert row["product"] == "Unknown SKU"
    assert row["state"] == "unknown"
    assert row["mapBarcode"] is True
    assert not any(row[flag] for flag in ("confirm", "undo", "force", "map"))


def test_the_same_barcode_scanned_twice_is_one_row_to_map():
    rows = unknown_rows(["999", "888", "999", " 999 ", ""])
    assert [r["sku"] for r in rows] == ["999", "888"]


def test_unknown_rows_carry_every_key_an_item_row_does():
    # They ride in the same `items` property, so the page can render both
    # with one function.
    item = item_rows([{"SKU": "A", "Product_Name": "A", "Quantity": 1}], [], {})[0]
    assert set(unknown_rows(["999"])[0]) == set(item)


from gui.packer_bridge import session_end_payload


def test_the_session_sentence_reads_like_the_artboard():
    payload = session_end_payload(
        packed=12, total=13, skipped=1, items=66, seconds=6480
    )
    assert payload["title"] == "Session complete"
    assert payload["body"] == "12 of 13 orders packed, 1 skipped, 66 items, in 1h 48m."


def test_nothing_skipped_says_nothing_about_skipping():
    body = session_end_payload(13, 13, 0, 66, 6480)["body"]
    assert "skipped" not in body
    assert body == "13 of 13 orders packed, 66 items, in 1h 48m."


def test_a_short_session_drops_the_hours_and_one_item_is_singular():
    assert session_end_payload(1, 1, 0, 1, 95)["body"] == (
        "1 of 1 orders packed, 1 item, in 1m."
    )


def test_an_unknown_start_time_leaves_the_duration_out():
    body = session_end_payload(2, 2, 0, 4, 0)["body"]
    assert body == "2 of 2 orders packed, 4 items."
