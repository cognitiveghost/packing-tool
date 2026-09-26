"""Audit 01: packing-list reading, scan matching, packing state, metrics.

Report: docs/audit/01-data-metrics.md. Every AUDIT-01-k test fails because of
the bug it names and is marked xfail(strict=True); the fix removes the marker.
The unmarked tests pin what the audit verified correct. Fixtures are synthetic
and only reproduce the shape of the production data.
"""

import json

import pytest

from packing_tool.session_stats import session_totals, sku_summary

TWO_ORDERS = [
    (
        "ORDER-001",
        "DHL",
        [
            {"sku": "SKU-AAA", "quantity": 2, "product_name": "Widget A"},
            {"sku": "SKU-BBB", "quantity": 1, "product_name": "Widget B"},
        ],
    ),
    ("ORDER-002", "DHL", [{"sku": "SKU-CCC", "quantity": 1, "product_name": "Widget C"}]),
]


def _loaded(session_factory, packer_logic_factory, orders=TWO_ORDERS, client="M"):
    _session_dir, work_dir, list_path = session_factory(client_id=client, orders=orders)
    logic = packer_logic_factory(client, work_dir)
    logic.load_packing_list_json(list_path)
    return logic, work_dir, list_path


def _completed(logic, order_number):
    return next(o for o in logic.completed_orders_metadata if o["order_number"] == order_number)


# ---------------------------------------------------------------------------
# Verified correct
# ---------------------------------------------------------------------------


def test_split_lines_of_one_sku_each_need_their_own_units(session_factory, packer_logic_factory):
    """10 production orders list one SKU on two lines; each line must be scanned."""
    orders = [(
        "#1",
        "DHL",
        [
            {"sku": "SKU-A", "quantity": 1, "product_name": "A"},
            {"sku": "SKU-A", "quantity": 2, "product_name": "A"},
        ],
    )]
    logic, _, _ = _loaded(session_factory, packer_logic_factory, orders)
    logic.start_order_packing("#1")
    statuses = [logic.process_sku_scan("SKU-A")[1] for _ in range(3)]
    assert statuses == ["SKU_OK", "SKU_OK", "ORDER_COMPLETE"]
    assert _completed(logic, "#1")["items_count"] == 3


def test_scanner_noise_and_case_still_match(session_factory, packer_logic_factory):
    logic, _, _ = _loaded(session_factory, packer_logic_factory)
    assert logic.start_order_packing("#order-001!")[1] == "ORDER_NOT_FOUND"  # order numbers keep case
    assert logic.start_order_packing("ORDER-001")[1] == "ORDER_LOADED"
    assert logic.process_sku_scan(" sku aaa ")[1] == "SKU_OK"


def test_resume_after_restart_keeps_counts(session_factory, packer_logic_factory):
    logic, work_dir, list_path = _loaded(session_factory, packer_logic_factory)
    logic.start_order_packing("ORDER-001")
    logic.process_sku_scan("SKU-AAA")
    logic.save_state()

    again = packer_logic_factory("M", work_dir)
    again.load_packing_list_json(list_path)
    again.start_order_packing("ORDER-001")
    assert [s["packed"] for s in again.current_order_state] == [1, 0]


# ---------------------------------------------------------------------------
# AUDIT-01-1  Returning to a skipped order takes over another order's timing
# ---------------------------------------------------------------------------


def test_returning_to_a_skipped_order_keeps_its_own_scan_records(session_factory, packer_logic_factory):
    logic, _, _ = _loaded(session_factory, packer_logic_factory)

    logic.start_order_packing("ORDER-001")
    started_001 = logic.current_order_start_time
    logic.process_sku_scan("SKU-AAA")
    logic.skip_order()

    logic.start_order_packing("ORDER-002")
    logic.process_sku_scan("SKU-CCC")  # ORDER-002 complete
    logic.clear_current_order()

    logic.start_order_packing("ORDER-001")
    logic.process_sku_scan("SKU-AAA")
    logic.process_sku_scan("SKU-BBB")  # ORDER-001 complete

    record = _completed(logic, "ORDER-001")
    assert sorted(r["sku"] for r in record["items"]) == ["skuaaa", "skuaaa", "skubbb"]
    assert record["started_at"] == started_001


def test_cancel_on_a_returned_order_does_not_edit_a_finished_order(session_factory, packer_logic_factory):
    orders = [
        ("#A", "DHL", [{"sku": "SKU-A", "quantity": 3, "product_name": "A"}]),
        ("#B", "DHL", [{"sku": "SKU-B", "quantity": 3, "product_name": "B"}]),
    ]
    logic, _, _ = _loaded(session_factory, packer_logic_factory, orders)
    logic.start_order_packing("#A")
    logic.process_sku_scan("SKU-A")
    logic.skip_order()
    logic.start_order_packing("#B")
    logic.force_confirm_item(0)  # one record, quantity 3; #B complete
    logic.clear_current_order()

    logic.start_order_packing("#A")
    logic.cancel_item_scan(0)  # takes back #A's one unit: must not touch #B

    assert _completed(logic, "#B")["items"][0]["quantity"] == 3


# ---------------------------------------------------------------------------
# AUDIT-01-2  Ending a list twice counts its orders twice
# ---------------------------------------------------------------------------


def _end(main_window, logic, session_dir, work_dir, monkeypatch):
    main_window.logic = logic
    main_window.current_work_dir = str(work_dir)
    main_window.current_session_path = str(session_dir)
    main_window.current_packing_list = "DHL_Orders"
    monkeypatch.setattr("gui.main_window.toast", lambda *a, **k: None)
    main_window.end_session()


@pytest.fixture
def ended_twice(main_window, session_factory, packer_logic_factory, monkeypatch):
    """ORDER-002 packed, End session (incomplete), Resume, ORDER-001 packed, End again."""
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=TWO_ORDERS)
    worker = main_window.worker_manager.create_worker("Ana")
    main_window.current_client_id = "TESTCL"
    main_window.current_worker_id = worker.id
    main_window.current_worker_name = worker.name

    first = packer_logic_factory("TESTCL", work_dir)
    first.load_packing_list_json(list_path)
    first.start_order_packing("ORDER-002")
    first.process_sku_scan("SKU-CCC")
    _end(main_window, first, session_dir, work_dir, monkeypatch)

    # The resume happens the next day: ORDER-002 was packed well before ORDER-001.
    state_path = work_dir / "packing_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["completed"][0]["completed_at"] = "2026-01-01T10:00:00+02:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    second = packer_logic_factory("TESTCL", work_dir)
    second.load_packing_list_json(list_path)
    second.start_order_packing("ORDER-001")
    for sku in ("SKU-AAA", "SKU-AAA", "SKU-BBB"):
        second.process_sku_scan(sku)
    _end(main_window, second, session_dir, work_dir, monkeypatch)
    return main_window, worker.id, work_dir


def test_a_list_ended_twice_counts_each_order_once_in_global_stats(ended_twice):
    window, _, _ = ended_twice
    stats = window.stats_manager.get_global_stats()
    assert stats["total_orders_packed"] == 2


def test_a_list_ended_twice_counts_each_order_once_in_worker_stats(ended_twice):
    window, worker_id, _ = ended_twice
    worker = window.worker_manager.get_worker(worker_id)
    assert (worker.total_orders, worker.total_items) == (2, 4)


# ---------------------------------------------------------------------------
# AUDIT-01-3  A packing list rewritten after packing started
# ---------------------------------------------------------------------------


def test_a_resumed_order_follows_the_quantity_now_on_the_list(session_factory, packer_logic_factory):
    logic, work_dir, list_path = _loaded(session_factory, packer_logic_factory)
    logic.start_order_packing("ORDER-001")
    logic.process_sku_scan("SKU-AAA")
    logic.save_state()

    data = json.loads(list_path.read_text(encoding="utf-8"))
    data["orders"][0]["items"][0]["quantity"] = 3  # Shopify re-ran: 3 × SKU-AAA now
    list_path.write_text(json.dumps(data), encoding="utf-8")

    again = packer_logic_factory("M", work_dir)
    again.load_packing_list_json(list_path)
    again.start_order_packing("ORDER-001")
    assert again.current_order_state[0]["required"] == 3


def test_an_order_dropped_from_the_list_does_not_count_toward_done(session_factory, packer_logic_factory):
    logic, work_dir, list_path = _loaded(session_factory, packer_logic_factory)
    logic.start_order_packing("ORDER-002")
    logic.process_sku_scan("SKU-CCC")
    logic.save_state()

    data = json.loads(list_path.read_text(encoding="utf-8"))
    data["orders"][1] = {
        "order_number": "ORDER-003",
        "courier": "DHL",
        "items": [{"sku": "SKU-DDD", "quantity": 1, "product_name": "D"}],
    }
    list_path.write_text(json.dumps(data), encoding="utf-8")

    again = packer_logic_factory("M", work_dir)
    again.load_packing_list_json(list_path)
    fired = []
    again.all_orders_complete.connect(lambda: fired.append(True))
    again.start_order_packing("ORDER-001")
    for sku in ("SKU-AAA", "SKU-AAA", "SKU-BBB"):
        again.process_sku_scan(sku)

    assert fired == []  # ORDER-003 is still to pack


# ---------------------------------------------------------------------------
# AUDIT-01-4  SKU table double-counts a SKU listed under two product names
# ---------------------------------------------------------------------------


def test_sku_summary_counts_a_sku_once_across_product_names(session_factory, packer_logic_factory):
    orders = [
        ("#1", "DHL", [{"sku": "NO_SKU", "quantity": 1, "product_name": "Lab Sample"}]),
        ("#2", "DHL", [{"sku": "NO_SKU", "quantity": 1, "product_name": "extra nights"}]),
    ]
    logic, _, _ = _loaded(session_factory, packer_logic_factory, orders)
    logic.start_order_packing("#1")
    logic.force_confirm_item(0)

    rows = sku_summary(logic.processed_df, logic.session_packing_state)
    assert sum(r["packed"] for r in rows) == 1


# ---------------------------------------------------------------------------
# AUDIT-01-5  The report stamps every order with the End-session time
# ---------------------------------------------------------------------------


def test_report_completed_at_is_when_the_order_was_packed(ended_twice):
    import pandas as pd

    _, _, work_dir = ended_twice
    report = pd.read_excel(work_dir / "reports" / "packing_completed.xlsx")
    stamps = report.drop_duplicates("Order_Number").set_index("Order_Number")["Completed At"]
    # ORDER-002 was packed before the first End session, ORDER-001 after it.
    assert stamps["ORDER-002"] < stamps["ORDER-001"]


# ---------------------------------------------------------------------------
# AUDIT-01-6  The Statistics "Items" card counts lines, not units
# ---------------------------------------------------------------------------


def test_items_card_counts_units_like_every_other_items_figure(session_factory, packer_logic_factory):
    logic, _, _ = _loaded(session_factory, packer_logic_factory)
    totals = session_totals(logic.processed_df, [])
    assert totals["items"] == logic._total_items == 4


def test_a_state_saved_before_the_fix_restores_timing_to_its_own_order(session_factory, packer_logic_factory):
    """Old states carry one unnamed _timing block: it belongs to progress.in_progress_order."""
    _logic, work_dir, list_path = _loaded(session_factory, packer_logic_factory)
    state_path = work_dir / "packing_state.json"
    state_path.write_text(json.dumps({
        "session_id": "s", "started_at": "2026-01-01T09:00:00+00:00",
        "progress": {"in_progress_order": "ORDER-001"},
        "in_progress": {
            "ORDER-001": [
                {"original_sku": "SKU-AAA", "normalized_sku": "skuaaa", "required": 2, "packed": 1, "row": 0},
                {"original_sku": "SKU-BBB", "normalized_sku": "skubbb", "required": 1, "packed": 0, "row": 1},
            ],
            "_timing": {"current_order_start_time": "2026-01-01T09:00:00+00:00",
                        "items_scanned": [{"sku": "skuaaa", "quantity": 1, "row": 0}]},
        },
        "_current_extras": {},
        "completed": [],
    }), encoding="utf-8")

    again = packer_logic_factory("M", work_dir)
    again.load_packing_list_json(list_path)
    again.start_order_packing("ORDER-002")  # another order first: must not take ORDER-001's timing
    assert again.current_order_items_scanned == []
    again.clear_current_order()
    again.start_order_packing("ORDER-001")
    assert again.current_order_start_time == "2026-01-01T09:00:00+00:00"
    assert len(again.current_order_items_scanned) == 1
