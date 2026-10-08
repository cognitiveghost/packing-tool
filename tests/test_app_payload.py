"""The app document's payloads: pure, so the numbers need no browser."""

import json

import pandas as pd

from gui.app_bridge import (
    STEPS,
    packing_payload,
    session_payload,
    start_failure,
    statistics_payload,
)
from packing_tool.exceptions import PackingListInvalidError, PackingStateUnreadableError


def _line(sku, name, qty, courier="DHL"):
    return {"SKU": sku, "Product_Name": name, "Quantity": str(qty), "Courier": courier}


ORDERS = {
    "#10": {"items": [_line("LIP-RED", "Lip balm, red", 2), _line("CRM-50", "Day cream", 1)]},
    "#11": {"items": [_line("LST-07", "Lipstick, shade 07", 1, "DPD")]},
    "#12": {"items": [_line("LIP-RED", "Lip balm, red", 1, "DPD")]},
    "#13": {"items": [_line("SPF-50", "Sunscreen", 3)]},
}
STATE = {
    "completed_orders": ["#12"],
    "skipped_orders": ["#13"],
    "in_progress": {
        "#10": [
            {"original_sku": "LIP-RED", "packed": 2, "required": 2, "row": 0},
            {"original_sku": "CRM-50", "packed": 0, "required": 1, "row": 1},
        ],
        "#13": [{"original_sku": "SPF-50", "packed": 1, "required": 3, "row": 0}],
    },
}


def _orders(payload, key):
    return next(g for g in payload["groups"] if g["key"] == key)["orders"]


def test_totals_count_orders_units_and_what_is_packed():
    totals = packing_payload(ORDERS, STATE)["totals"]
    assert totals == {
        "orders": 4, "done": 1, "units": 8, "packed": 4, "skipped": 1,
        "in_progress": 1, "pct": 25, "complete": False,
    }


def test_groups_come_in_progress_then_not_started_then_packed():
    payload = packing_payload(ORDERS, STATE)
    assert [g["key"] for g in payload["groups"]] == ["in_progress", "not_started", "packed"]
    assert [g["label"] for g in payload["groups"]] == ["In progress", "Not started", "Packed"]
    assert [g["count"] for g in payload["groups"]] == [1, 2, 1]


def test_a_skipped_order_is_not_started_even_with_scans_and_keeps_its_count():
    payload = packing_payload(ORDERS, STATE)
    not_started = _orders(payload, "not_started")
    skipped = next(o for o in not_started if o["number"] == "#13")
    assert skipped["skipped"] is True
    assert skipped["status"] == "not_started"
    assert (skipped["packed"], skipped["units"]) == (1, 3)
    assert next(g for g in payload["groups"] if g["key"] == "not_started")["note"] == "1 skipped"


def test_an_order_row_carries_its_summary_courier_and_items():
    order = _orders(packing_payload(ORDERS, STATE), "in_progress")[0]
    assert order["label"] == "#10"
    assert order["summary"] == "2 items · Lip balm, red, Day cream"
    assert order["courier"] == "DHL"
    assert (order["packed"], order["units"]) == (2, 3)
    assert [(i["sku"], i["packed"], i["required"], i["state"]) for i in order["items"]] == [
        ("LIP-RED", 2, 2, "complete"), ("CRM-50", 0, 1, "pending"),
    ]


def test_a_packed_orders_items_are_all_complete():
    order = _orders(packing_payload(ORDERS, STATE), "packed")[0]
    assert [(i["packed"], i["state"]) for i in order["items"]] == [(1, "complete")]


def test_only_in_progress_orders_are_open_by_default():
    payload = packing_payload(ORDERS, STATE)
    assert all(o["open"] for o in _orders(payload, "in_progress"))
    assert not any(o["open"] for o in _orders(payload, "not_started"))
    assert not any(o["open"] for o in _orders(payload, "packed"))


def test_the_filter_matches_number_sku_and_product_in_any_case():
    by_number = packing_payload(ORDERS, STATE, "#11")
    assert by_number["hits"] == 1 and _orders(by_number, "not_started")[0]["number"] == "#11"

    by_sku = packing_payload(ORDERS, STATE, "lip-red")
    assert by_sku["hits"] == 2
    assert by_sku["query"] == "lip-red"

    by_product = packing_payload(ORDERS, STATE, "SUNSCREEN")
    assert by_product["hits"] == 1


def test_matching_orders_open_and_the_hit_item_is_marked():
    payload = packing_payload(ORDERS, STATE, "LIP-RED")
    listed = [o for g in payload["groups"] for o in g["orders"]]
    assert all(o["open"] for o in listed)
    order_10 = next(o for o in listed if o["number"] == "#10")
    assert [i["hit"] for i in order_10["items"]] == [True, False]


def test_an_order_number_match_marks_no_item():
    payload = packing_payload(ORDERS, STATE, "11")
    order = _orders(payload, "not_started")[0]
    assert [i["hit"] for i in order["items"]] == [False]


def test_no_match_keeps_the_totals_and_lists_nothing():
    payload = packing_payload(ORDERS, STATE, "99999")
    assert payload["hits"] == 0
    assert payload["groups"] == []
    assert payload["query"] == "99999"
    assert payload["totals"]["orders"] == 4


def test_a_blank_or_hash_only_query_is_no_filter():
    for query in ("   ", "#", " # "):
        payload = packing_payload(ORDERS, STATE, query)
        assert payload["hits"] == 4
        assert payload["query"] == ""
        assert not any(i["hit"] for g in payload["groups"] for o in g["orders"] for i in o["items"])


def test_complete_means_every_order_packed_not_packed_or_skipped():
    state = {"completed_orders": ["#10", "#11", "#12"], "skipped_orders": ["#13"], "in_progress": {}}
    assert packing_payload(ORDERS, state)["totals"]["complete"] is False
    state["completed_orders"].append("#13")
    state["skipped_orders"] = []
    totals = packing_payload(ORDERS, state)["totals"]
    assert totals["complete"] is True and totals["pct"] == 100


def test_an_empty_list_is_all_zeros_and_not_complete():
    payload = packing_payload({}, {})
    assert payload["totals"] == {
        "orders": 0, "done": 0, "units": 0, "packed": 0, "skipped": 0,
        "in_progress": 0, "pct": 0, "complete": False,
    }
    assert payload["groups"] == []
    stats = statistics_payload(None, {})
    assert stats["orders"] == 0 and stats["pct"] == 0 and stats["skus"] == []


def test_a_malformed_state_entry_does_not_break_the_payload():
    orders = {
        7: {"items": [_line("A", "Alpha", "many")]},  # an int order number, a bad quantity
        "#8": {},  # no items at all
    }
    state = {"in_progress": {7: ["not a dict", {"row": 0, "packed": 1}], "#8": "nope"}}
    payload = packing_payload(orders, state)
    numbers = [o["number"] for g in payload["groups"] for o in g["orders"]]
    assert sorted(numbers) == ["#8", "7"]
    json.dumps(payload)  # everything in it can cross the channel


def _df():
    rows = []
    for number, order in ORDERS.items():
        for item in order["items"]:
            rows.append({"Order_Number": number, **item})
    return pd.DataFrame(rows)


def test_statistics_counts_and_notes_inputs():
    stats = statistics_payload(_df(), STATE)
    assert (stats["orders"], stats["completed"], stats["items"], stats["unique_skus"]) == (4, 1, 8, 4)
    assert stats["pct"] == 25
    assert stats["in_progress"] == 1  # #13 is skipped, so only #10
    assert stats["packed"] == 4       # 2 of #10, 1 of #12, 1 of #13
    assert stats["fully_packed"] == 1  # LIP-RED: 3 of 3


def test_statistics_couriers_carry_done_and_total():
    stats = statistics_payload(_df(), STATE)
    assert stats["couriers"] == [
        {"name": "DHL", "done": 0, "total": 2},
        {"name": "DPD", "done": 1, "total": 2},
    ]


def test_statistics_skus_carry_left_and_state():
    skus = {row["sku"]: row for row in statistics_payload(_df(), STATE)["skus"]}
    assert skus["LIP-RED"] == {
        "sku": "LIP-RED", "product": "Lip balm, red", "total": 3, "packed": 3,
        "left": 0, "state": "packed",
    }
    assert (skus["SPF-50"]["left"], skus["SPF-50"]["state"]) == (2, "partial")
    assert (skus["LST-07"]["left"], skus["LST-07"]["state"]) == (1, "pending")


def test_session_payload_none_and_opening():
    assert session_payload()["state"] == "none"
    opening = session_payload("opening", list_name="DHL_Orders", session_id="2026-10-07_1", step=2)
    assert opening["step"] == 2
    assert opening["stepName"] == STEPS[1] == "Reading saved progress"
    assert (opening["list"], opening["id"]) == ("DHL_Orders", "2026-10-07_1")


def test_session_payload_open_writes_the_meta():
    one = session_payload("open", orders=1, couriers=["DHL"])
    assert one["meta"] == "1 order · DHL"
    many = session_payload("open", orders=120, couriers=["DHL", "DPD", "GLS", "Speedy", "UPS"])
    assert many["meta"] == "120 orders · DHL, DPD, GLS +2"
    assert session_payload("open", orders=3)["meta"] == "3 orders"


def test_start_failure_names_the_missing_field_and_what_was_found():
    error = PackingListInvalidError("x", ["courier"], ["items", "order_number"], "field")
    assert start_failure(error, "DHL_Orders") == (
        "Packing list could not be loaded",
        "DHL_Orders has an order with no courier. Found: items, order_number.",
    )


def test_start_failure_names_a_missing_column():
    error = PackingListInvalidError("x", ["Quantity"], ["Order_Number", "SKU"], "column")
    assert start_failure(error, "DHL_Orders")[1] == (
        "DHL_Orders has no Quantity column. Found: Order_Number, SKU."
    )


def test_start_failure_for_the_other_errors():
    assert start_failure(ValueError("bad JSON at line 3"), "L") == (
        "Packing list could not be loaded", "L could not be read: bad JSON at line 3.",
    )
    assert start_failure(FileNotFoundError("gone"), "L") == (
        "Packing list could not be loaded", "L is no longer in the session's folder.",
    )
    title, text = start_failure(PackingStateUnreadableError("state.json: boom"), "L")
    assert title == "Saved progress could not be read"
    assert text == (
        "The saved progress for L could not be read, so the list was not opened. "
        "Nothing was changed. Check the connection to the server and open it again."
    )
    assert start_failure(RuntimeError("Locked by PACK-02"), "L") == (
        "Session could not be opened", "Locked by PACK-02",
    )
