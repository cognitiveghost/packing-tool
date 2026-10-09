"""What Session details says (spec 2026-10-08 phase 4, section 7).

The flag tests are ported from tests/test_confirmation_methods.py, which read
them off a QTreeWidget.
"""

from datetime import UTC, datetime

import pytest

from gui.sessions_payload import detail_export_rows, details_payload, fmt_time

NOW = datetime(2026, 10, 7, 14, 6, 31, tzinfo=UTC)

ORDER_A = {
    "order_number": "#10407",
    "started_at": "2026-10-06T08:14:02+00:00",
    "completed_at": "2026-10-06T08:16:16+00:00",
    "duration_seconds": 134,
    "items_count": 5,
    "corrections": 1,
    "extra_scans_count": 2,
    "unknown_scans_count": 1,
    "items": [
        {"sku": "LST-07", "title": "Lipstick, shade 07", "quantity": 1, "row": 0,
         "scanned_at": "2026-10-06T08:14:14+00:00", "time_from_order_start_seconds": 12,
         "confirmation_method": "scanned"},
        {"sku": "LST-07", "title": "Lipstick, shade 07", "quantity": 1, "row": 0,
         "scanned_at": "2026-10-06T08:14:20+00:00", "time_from_order_start_seconds": 18,
         "confirmation_method": "scanned"},
        {"sku": "CRM-15ML", "title": "Eye cream 15 ml", "quantity": 3, "row": 1,
         "scanned_at": "2026-10-06T08:15:00+00:00", "time_from_order_start_seconds": 58,
         "confirmation_method": "force_confirmed"},
    ],
}
ORDER_B = {
    "order_number": "10408",
    "started_at": "2026-10-06T08:17:00+00:00",
    "completed_at": "2026-10-06T08:18:00+00:00",
    "duration_seconds": 60,
    "items_count": 1,
    "items": [
        {"sku": "A", "title": "A", "quantity": 1, "row": 0,
         "scanned_at": "2026-10-06T08:17:30+00:00", "time_from_order_start_seconds": 30,
         "confirmation_method": "manual"},
    ],
}
METRICS = {
    "avg_time_per_order": 97,
    "fastest_order_seconds": 60,
    "slowest_order_seconds": 134,
    "avg_time_per_item": 16.2,
    "avg_time_to_first_scan": 9.5,
    "orders_per_hour": 12.44,
    "items_per_hour": 148.6,
}


def entry(**over) -> dict:
    base = {
        "session_id": "2026-10-06_1",
        "packing_list_name": "Morning_wave",
        "status": "incomplete",
        "worker_id": "W-004",
        "worker_name": "Petya",
        "pc_name": "WH-PC-01",
        "started_at": "2026-10-06T08:02:11+00:00",
        "last_updated": "2026-10-06T11:14:40+00:00",
        "total_orders": 4,
        "completed_orders": 2,
        "skipped_orders": 1,
        "total_items": 402,
        "work_dir": "/srv/2026-10-06_1/packing/Morning_wave",
    }
    base.update(over)
    return base


def details(**over) -> dict:
    made = {
        "record": {
            "session_id": "2026-10-06_1",
            "packing_list_name": "Morning_wave",
            "worker_id": "W-004",
            "worker_name": "Petya",
            "pc_name": "WH-PC-01",
            "start_time": "2026-10-06T08:02:11+00:00",
            "end_time": "2026-10-06T11:14:40+00:00",
            "duration_seconds": 11549,
            "total_orders": 4,
            "completed_orders": 2,
        },
        "packing_state": {
            "in_progress": {
                "#10410": [
                    {"original_sku": "SPF-50", "required": 2, "packed": 1, "row": 0},
                    {"original_sku": "OIL-100", "required": 3, "packed": 2, "row": 1},
                ],
                "_timing_by_order": {"#10410": {}},
            },
        },
        "session_info": {},
        "session_summary": {
            "metrics": dict(METRICS),
            "orders": [ORDER_A, ORDER_B],
            "skipped_orders": [
                {"order_number": "#10409", "skipped_at": "2026-10-06T09:00:00+00:00",
                 "status": "skipped"}
            ],
        },
    }
    made.update(over)
    return made


def ready(entry_over=None, **kwargs) -> dict:
    return details_payload(entry(**(entry_over or {})), details(), now=NOW,
                           client="Acme Cosmetics (ACME)", **kwargs)


def test_times_read_to_a_tenth_under_a_minute():
    assert fmt_time(None) == "—"
    assert fmt_time(0) == "—"
    assert fmt_time(9.5) == "9.5s"
    assert fmt_time(45) == "45s"
    assert fmt_time(134) == "2m 14s"
    assert fmt_time(3725) == "1h 2m"


def test_the_head_is_the_list_rows():
    made = ready()
    assert (made["key"], made["id"], made["list"]) == (
        "2026-10-06_1|Morning_wave", "2026-10-06_1", "Morning_wave")
    assert (made["label"], made["tone"], made["manual"]) == ("Incomplete", "danger", True)
    assert made["setBy"] == "Set by a person"
    assert made["why"] == "closed by Petya with 2 orders unpacked"
    assert made["state"] == "ready"
    assert made["active"] is False


def test_the_seven_facts():
    assert ready()["facts"] == [
        {"label": "Client", "value": "Acme Cosmetics (ACME)"},
        {"label": "Packing list", "value": "Morning_wave"},
        {"label": "Worker", "value": "Petya (W-004)"},
        {"label": "PC", "value": "WH-PC-01"},
        {"label": "Started", "value": "6 Oct, 08:02:11"},
        {"label": "Completed", "value": "6 Oct, 11:14:40"},
        {"label": "Duration", "value": "3h 12m"},
    ]


def test_an_active_session_is_still_packing_and_so_far():
    made = details_payload(
        entry(status="in_progress", started_at="2026-10-07T11:00:00+00:00"),
        details(record={"start_time": "2026-10-07T11:00:00+00:00", "end_time": None,
                        "duration_seconds": 0, "total_orders": 4, "completed_orders": 2}),
        now=NOW, stamp="14:06:31",
    )
    facts = {fact["label"]: fact["value"] for fact in made["facts"]}
    assert made["active"] is True
    assert made["pc"] == "WH-PC-01"
    assert made["stamp"] == "14:06:31"
    assert facts["Completed"] == "Still packing"
    assert facts["Duration"] == "3h 6m so far"
    assert [card["note"] for card in made["cards"][:4]] == ["so far"] * 4
    assert made["metricsNote"] == "Only data from completed orders is shown. Figures so far."
    assert [group["title"] for group in made["groups"]] == ["Order time so far", "Item time so far"]


def test_the_five_stat_cards():
    assert ready()["cards"] == [
        {"value": "2", "of": "of 4", "label": "Orders packed", "note": "2 not packed"},
        {"value": "6", "of": "of 402", "label": "Items packed", "note": ""},
        {"value": "12.4", "of": "", "label": "Orders per hour", "note": ""},
        {"value": "149", "of": "", "label": "Items per hour", "note": ""},
        {"value": "1", "of": "", "label": "Skipped orders", "note": "not packed"},
    ]


def test_timing_names_the_fastest_and_the_slowest_order():
    made = ready()
    assert made["timing"] is True
    assert made["metricsNote"] == "Only data from completed orders is shown."
    assert made["groups"] == [
        {"title": "Order time", "tiles": [
            {"value": "1m 37s", "label": "Average per order"},
            {"value": "1m 0s", "label": "Fastest · #10408"},
            {"value": "2m 14s", "label": "Slowest · #10407"},
        ]},
        {"title": "Item time", "tiles": [
            {"value": "16.2s", "label": "Average per item"},
            {"value": "9.5s", "label": "Average to first scan"},
        ]},
    ]
    assert made["scan"] == [
        {"value": "1", "label": "Scan corrections"},
        {"value": "0.50", "label": "Corrections per order"},
        {"value": "1", "label": "Unknown scans"},
        {"value": "2", "label": "Extra scans"},
    ]


def test_without_timing_the_rates_dash_out_and_scan_quality_stays():
    made = details_payload(
        entry(),
        details(session_summary={"metrics": {}, "orders": [ORDER_A, ORDER_B],
                                 "skipped_orders": []}),
        now=NOW,
    )
    assert made["timing"] is False
    assert made["groups"] == []
    assert [(card["value"], card["note"]) for card in made["cards"][2:4]] == [
        ("—", "No timing data"), ("—", "No timing data")]
    assert made["scan"][0] == {"value": "1", "label": "Scan corrections"}


def test_orders_come_packed_then_in_progress_then_skipped():
    made = ready()
    assert [(order["label"], order["kind"]) for order in made["orders"]] == [
        ("#10407", "packed"), ("#10408", "packed"),
        ("#10410", "in_progress"), ("#10409", "skipped"),
    ]
    assert made["total"] == 4
    assert made["showing"] == "Showing 4 of 4 recorded orders"
    assert made["noMatch"] is False


def test_a_packed_order_row():
    order = ready()["orders"][0]
    assert {k: order[k] for k in ("number", "duration", "count", "started", "completed")} == {
        "number": "#10407", "duration": "2m 14s", "count": "5 items",
        "started": "08:14:02", "completed": "08:16:16",
    }
    assert order["flags"] == [
        {"label": "Forced confirm", "tone": "danger"},
        {"label": "2 extra", "tone": "warning"},
        {"label": "1 correction", "tone": "info"},
        {"label": "1 unknown", "tone": "neutral"},
    ]


def test_scans_are_grouped_by_line_and_extras_get_their_own_rows():
    assert ready()["orders"][0]["items"] == [
        {"sku": "LST-07", "name": "Lipstick, shade 07", "offset": "+12s", "count": "×2",
         "time": "08:14:14", "flags": []},
        {"sku": "CRM-15ML", "name": "Eye cream 15 ml", "offset": "+58s", "count": "×3",
         "time": "08:15:00", "flags": [{"label": "Forced confirm", "tone": "danger"}]},
        {"sku": "", "name": "2 extra scans · not in this order", "offset": "", "count": "2",
         "time": "", "flags": [{"label": "Extra", "tone": "warning"}]},
        {"sku": "", "name": "1 unknown scan · barcode not recognised", "offset": "",
         "count": "1", "time": "", "flags": [{"label": "1 unknown", "tone": "neutral"}]},
    ]


def test_each_item_row_names_how_it_was_packed():
    """Ported: a Confirm click ("manual") and Force ("force_confirmed") are not scans."""
    order = {
        "order_number": "#1001", "duration_seconds": 40, "items_count": 5,
        "items": [
            {"sku": "A", "quantity": 1},  # an older record: no method means scanned
            {"sku": "B", "quantity": 1, "confirmation_method": "manual"},
            {"sku": "C", "quantity": 3, "confirmation_method": "force_confirmed"},
        ],
    }
    made = details_payload(
        entry(), details(session_summary={"orders": [order], "skipped_orders": []}), now=NOW)
    row = made["orders"][0]
    assert [[flag["label"] for flag in item["flags"]] for item in row["items"]] == [
        [], ["Manual confirm"], ["Forced confirm"]]
    assert [flag["label"] for flag in row["flags"]] == ["Forced confirm", "Manual confirm"]
    assert [item["count"] for item in row["items"]] == ["×1", "×1", "×3"]


def test_a_title_that_only_repeats_the_sku_is_not_shown_twice():
    assert ready()["orders"][1]["items"][0]["name"] == ""


def test_an_in_progress_order_shows_how_far_it_got():
    order = ready()["orders"][2]
    assert order["count"] == "3 / 5 items"
    assert (order["duration"], order["started"], order["completed"]) == ("—", "—", "—")
    assert order["flags"] == [{"label": "In progress", "tone": "info"}]
    assert [(item["sku"], item["count"]) for item in order["items"]] == [
        ("SPF-50", "1 / 2"), ("OIL-100", "2 / 3")]


def test_a_skipped_order_has_no_items():
    order = ready()["orders"][3]
    assert order["started"] == "09:00:00"
    assert order["count"] == "—"
    assert order["flags"] == [{"label": "Skipped", "tone": "warning"}]
    assert order["items"] == []


def test_an_order_in_progress_and_skipped_is_listed_once_as_skipped():
    made = details_payload(
        entry(),
        details(session_summary={"orders": [], "skipped_orders": [
            {"order_number": "#10410", "skipped_at": None, "status": "skipped"}]}),
        now=NOW,
    )
    assert [(order["label"], order["kind"]) for order in made["orders"]] == [
        ("#10410", "skipped")]


def test_a_session_with_only_a_state_file_lists_its_skipped_orders():
    made = details_payload(
        entry(status="paused"),
        {"record": {}, "session_info": {}, "session_summary": {},
         "packing_state": {"completed": [], "skipped_orders": ["#7"],
                           "skipped_orders_timing": {"#7": "2026-10-06T09:30:00+00:00"},
                           "in_progress": {}}},
        now=NOW,
    )
    assert [(o["label"], o["kind"], o["started"]) for o in made["orders"]] == [
        ("#7", "skipped", "09:30:00")]
    assert made["canExport"] is False


@pytest.mark.parametrize("query", ["10407", "#10407", "  10407 "])
def test_the_filter_matches_the_order_number_with_or_without_the_hash(query):
    made = ready(query=query)
    assert [order["label"] for order in made["orders"]] == ["#10407"]
    assert made["showing"] == "Showing 1 of 4 recorded orders"
    assert made["query"] == query


def test_a_filter_that_matches_nothing_echoes_the_query():
    made = ready(query="#10999")
    assert made["orders"] == []
    assert made["noMatch"] is True
    assert made["needle"] == "10999"
    assert made["showing"] == "Showing 0 of 4 recorded orders"


def test_while_the_files_are_read_the_page_has_the_lists_facts():
    made = details_payload(entry(), None, now=NOW, client="Acme Cosmetics (ACME)")
    assert made["state"] == "loading"
    assert made["canExport"] is False
    facts = {fact["label"]: fact["value"] for fact in made["facts"]}
    assert facts["Worker"] == "Petya (W-004)"
    assert facts["Started"] == "6 Oct, 08:02:11"
    assert facts["Completed"] == "—"
    assert "cards" not in made


def test_files_that_could_not_be_read_name_the_file_and_the_cause():
    made = details_payload(
        entry(), None, now=NOW,
        error={"path": "/srv/x/packing_state.json", "cause": "permission denied."})
    assert made["state"] == "error"
    assert made["error"] == {"path": "/srv/x/packing_state.json", "cause": "permission denied"}
    assert made["canExport"] is False


def test_the_export_is_one_row_per_scan_of_the_packed_orders():
    rows = detail_export_rows(details())
    assert len(rows) == 4
    assert rows[0] == {
        "Order Number": "#10407",
        "Order Started": "2026-10-06T08:14:02+00:00",
        "Order Completed": "2026-10-06T08:16:16+00:00",
        "Order Duration (s)": 134,
        "SKU": "LST-07",
        "Quantity": 1,
        "Scanned At": "2026-10-06T08:14:14+00:00",
        "Time from Start (s)": 12,
    }
    assert ready()["canExport"] is True
    assert detail_export_rows(None) == []


def test_odd_shapes_in_the_files_do_not_break_the_details():
    """Review focus 2."""
    made = details_payload(
        entry(),
        {
            "record": {"total_orders": "4", "completed_orders": None},
            "session_info": {},
            "session_summary": {
                "metrics": None,
                "orders": ["junk", {"order_number": 1001}, {"order_number": "#2", "items": None}],
                "skipped_orders": ["junk", {"order_number": 55}],
            },
            "packing_state": {"in_progress": {"9": "junk", "8": ["junk", {"packed": "x"}]}},
        },
        now=NOW,
    )
    assert [(o["number"], o["label"], o["kind"]) for o in made["orders"]] == [
        ("1001", "#1001", "packed"), ("#2", "#2", "packed"),
        ("8", "#8", "in_progress"), ("55", "#55", "skipped"),
    ]
    assert made["orders"][0]["items"] == [
        {"sku": "", "name": "Item details not available", "offset": "", "count": "",
         "time": "", "flags": []}]
    assert made["orders"][2]["count"] == "0 / 0 items"
    assert made["cards"][0]["value"] == "2"
    assert all(isinstance(order["number"], str) for order in made["orders"])
