"""End Session records what the run reached (snapshot finding 2.1).

A run ended with orders unpacked was written `completed` into session_info.json's
packing_progress, while packing_state.json and the registry said otherwise, and
the Shopify tool showed the session as done.
"""

import json

import pytest

from packing_tool.packer_logic import normalize_sku
from packing_tool.session_manager import SessionManager

ORDERS = [
    ("ORD-1", "DHL", [{"sku": "SKU-1", "quantity": 1, "product_name": "One"}]),
    ("ORD-2", "DHL", [{"sku": "SKU-2", "quantity": 1, "product_name": "Two"}]),
]


def _end_in_window(window, session_dir, work_dir, logic, monkeypatch):
    """Point a real MainWindow at a real list, End Session, return session_info.json."""
    (session_dir / "session_info.json").write_text(
        json.dumps({"session_id": session_dir.name}), encoding="utf-8"
    )
    window.logic = logic
    window.current_client_id = "TESTCL"
    window.current_work_dir = str(work_dir)
    window.current_session_path = str(session_dir)
    window.current_packing_list = "DHL_Orders"
    window.session_manager = SessionManager(client_id="TESTCL")
    failures = []
    monkeypatch.setattr(
        "gui.main_window.QMessageBox.critical", lambda *a, **k: failures.append(a)
    )
    window.end_session()
    assert failures == []
    return json.loads((session_dir / "session_info.json").read_text(encoding="utf-8"))


@pytest.fixture
def ended(main_window, session_factory, packer_logic_factory, monkeypatch):
    """End a two-order list after packing `packed`; return its packing_progress block."""

    def _run(packed):
        session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
        logic = packer_logic_factory("TESTCL", work_dir)
        logic.load_packing_list_json(list_path)
        for order, _courier, items in ORDERS:
            if order in packed:
                logic.start_order_packing(order)
                for item in items:
                    logic.process_sku_scan(item["sku"])
                logic.clear_current_order()
        info = _end_in_window(main_window, session_dir, work_dir, logic, monkeypatch)
        return info["packing_progress"]["DHL_Orders"]

    return _run


def test_a_run_ended_with_an_order_unpacked_is_incomplete(ended):
    block = ended(packed={"ORD-1"})
    assert block["status"] == "incomplete"
    assert block["completed_orders"] == ["ORD-1"]


def test_a_run_ended_with_nothing_packed_is_incomplete(ended):
    block = ended(packed=set())
    assert block["status"] == "incomplete"
    assert "completed_orders" not in block


def test_a_run_ended_with_every_order_packed_is_completed(ended):
    block = ended(packed={"ORD-1", "ORD-2"})
    assert block["status"] == "completed"
    assert sorted(block["completed_orders"]) == ["ORD-1", "ORD-2"]


# ---------------------------------------------------------------------------
# Real shapes (snapshot, 2026-10-11): lists up to 219 orders, an order of 70
# lines and 900 units, Force confirm of 56 units. Synthetic values only.
# ---------------------------------------------------------------------------

BIG_ORDER_LINES = (
    [{"sku": "BIG-00", "quantity": 56, "product_name": "Big 0"}]
    + [{"sku": f"BIG-{i:02d}", "quantity": 12, "product_name": f"Big {i}"} for i in range(1, 69)]
    + [{"sku": "BIG-69", "quantity": 28, "product_name": "Big 69"}]
)


def test_an_order_of_70_lines_and_900_units_packs_whole(packer_logic_factory, session_factory):
    assert sum(line["quantity"] for line in BIG_ORDER_LINES) == 900
    _session_dir, work_dir, list_path = session_factory(
        client_id="TESTCL", orders=[("BIG-1", "DHL", BIG_ORDER_LINES)]
    )
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    logic.start_order_packing("BIG-1")
    for _ in range(28):  # the last line is scanned unit by unit
        logic.process_sku_scan("BIG-69")
    rows = {s["normalized_sku"]: s["row"] for s in logic.current_order_state}
    for i in range(69):  # the rest by Force confirm, BIG-00's 56 units first
        _result, status = logic.force_confirm_item(rows[normalize_sku(f"BIG-{i:02d}")])
        assert status == "FORCE_CONFIRMED"
    assert logic.all_orders_packed() is True
    [meta] = logic.completed_orders_metadata
    assert meta["items_count"] == 900


def test_a_219_order_list_ended_two_short_is_incomplete(
    main_window, session_factory, packer_logic_factory, monkeypatch
):
    orders = [
        (f"L-{n:04d}", "DHL", [{"sku": f"S-{n % 23}", "quantity": 1 + n % 2, "product_name": "P"}])
        for n in range(219)
    ]
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=orders)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    for order, _courier, items in orders[:217]:
        logic.start_order_packing(order)
        for item in items:
            for _ in range(item["quantity"]):
                logic.process_sku_scan(item["sku"], "manual" if item["quantity"] == 1 else "scanned")
        logic.clear_current_order()

    info = _end_in_window(main_window, session_dir, work_dir, logic, monkeypatch)

    block = info["packing_progress"]["DHL_Orders"]
    assert block["status"] == "incomplete"
    assert len(block["completed_orders"]) == 217
    summary = json.loads((work_dir / "session_summary.json").read_text(encoding="utf-8"))
    assert (summary["completed_orders"], summary["total_orders"]) == (217, 219)
