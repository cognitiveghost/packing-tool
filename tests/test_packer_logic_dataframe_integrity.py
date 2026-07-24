"""Order data fidelity (target #1).

"Замовлення в датафреймі завжди повинні бути точні відповідно до пакінг
листам які приходять" — PackerLogic must faithfully mirror the incoming
packing list / Shopify analysis JSON. It is a read-only consumer of order
content: SKU, quantity, order number, and courier must reach orders_data
byte-for-byte (normalization is only ever applied to *comparison* copies,
never to the stored original).
"""
import json

import pytest

from packer_logic import PackerLogic


# ---------------------------------------------------------------------------
# load_packing_list_json — exact field fidelity
# ---------------------------------------------------------------------------

def test_loaded_items_preserve_original_sku_and_product_name_verbatim(packer_logic_factory, session_factory):
    orders = [("ORD-1", "DHL", [
        {"sku": "  SKU-123 (Special!) ", "quantity": 3, "product_name": "Крем для обличчя — 50 мл"},
    ])]
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)
    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)

    item = logic.orders_data["ORD-1"]["items"][0]
    assert item["SKU"] == "  SKU-123 (Special!) "  # not normalized/trimmed in storage
    assert item["Product_Name"] == "Крем для обличчя — 50 мл"
    assert item["Order_Number"] == "ORD-1"
    assert item["Courier"] == "DHL"
    assert item["Quantity"] == "3"


def test_loaded_order_carries_extra_metadata_fields_unmodified(packer_logic_factory, session_factory):
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=[])
    packing_list = {
        "list_name": "DHL_Orders",
        "orders": [{
            "order_number": "ORD-1",
            "courier": "DHL",
            "order_type": "wholesale",
            "destination_country": "Germany",
            "tags": ["vip", "gift"],
            "notes": "Handle with care",
            "items": [{"sku": "SKU-1", "quantity": 1, "product_name": "Widget"}],
        }],
    }
    list_path.write_text(json.dumps(packing_list, ensure_ascii=False), encoding="utf-8")

    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)

    meta = logic.orders_data["ORD-1"]["metadata"]
    assert meta["order_type"] == "wholesale"
    assert meta["destination_country"] == "Germany"
    assert meta["tags"] == ["vip", "gift"]
    assert meta["notes"] == "Handle with care"


def test_missing_order_number_raises_instead_of_silently_dropping(packer_logic_factory, session_factory):
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=[])
    packing_list = {
        "orders": [{"courier": "DHL", "items": [{"sku": "SKU-1", "quantity": 1}]}]  # no order_number
    }
    list_path.write_text(json.dumps(packing_list), encoding="utf-8")

    logic = packer_logic_factory("M", work_dir)
    with pytest.raises(ValueError):
        logic.load_packing_list_json(list_path)


def test_missing_courier_raises_for_packing_list(packer_logic_factory, session_factory):
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=[])
    packing_list = {
        "orders": [{"order_number": "ORD-1", "items": [{"sku": "SKU-1", "quantity": 1}]}]  # no courier
    }
    list_path.write_text(json.dumps(packing_list), encoding="utf-8")

    logic = packer_logic_factory("M", work_dir)
    with pytest.raises(ValueError):
        logic.load_packing_list_json(list_path)


def test_order_with_no_items_is_skipped_not_crashed(packer_logic_factory, session_factory):
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=[])
    packing_list = {
        "orders": [
            {"order_number": "ORD-EMPTY", "courier": "DHL", "items": []},
            {"order_number": "ORD-1", "courier": "DHL", "items": [{"sku": "SKU-1", "quantity": 1}]},
        ]
    }
    list_path.write_text(json.dumps(packing_list), encoding="utf-8")

    logic = packer_logic_factory("M", work_dir)
    count, _ = logic.load_packing_list_json(list_path)
    assert "ORD-EMPTY" not in logic.orders_data
    assert "ORD-1" in logic.orders_data
    assert count == 1


def test_missing_packing_list_file_raises_value_error(packer_logic_factory, session_factory):
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=[])
    missing_path = list_path.parent / "does_not_exist.json"
    logic = packer_logic_factory("M", work_dir)
    with pytest.raises(ValueError):
        logic.load_packing_list_json(missing_path)


def test_invalid_json_raises_value_error_not_a_crash(packer_logic_factory, session_factory):
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=[])
    list_path.write_text("{not valid json", encoding="utf-8")
    logic = packer_logic_factory("M", work_dir)
    with pytest.raises(ValueError):
        logic.load_packing_list_json(list_path)


# ---------------------------------------------------------------------------
# Quantity edge cases — a malformed Quantity must not silently misrepresent
# how many units the packing list actually asked for.
# ---------------------------------------------------------------------------

def test_garbage_quantity_silently_becomes_one_instead_of_erroring(loaded_logic, packer_logic_factory, session_factory):
    """Documents current (questionable) behavior: start_order_packing() coerces
    Quantity via int(float(...)) and falls back to 1 on ValueError/TypeError,
    with no warning surfaced to the worker. A packing list bug (e.g. Quantity
    == "N/A" due to an upstream Shopify export error) is silently downgraded
    to "pack 1 unit" rather than blocking/flagging the order — the exact kind
    of unnoticed order-content drift target #1 cares about.
    """
    orders = [("ORD-1", "DHL", [{"sku": "SKU-1", "quantity": "N/A", "product_name": "Widget"}])]
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)
    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)

    logic.start_order_packing("ORD-1")
    assert logic.current_order_state[0]["required"] == 1  # silently defaulted, not surfaced as an error


def test_decimal_quantity_string_is_coerced_correctly(packer_logic_factory, session_factory):
    orders = [("ORD-1", "DHL", [{"sku": "SKU-1", "quantity": "3.0", "product_name": "Widget"}])]
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)
    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)
    logic.start_order_packing("ORD-1")
    assert logic.current_order_state[0]["required"] == 3


# ---------------------------------------------------------------------------
# Duplicate order_number in the incoming list — a data-quality edge case.
# ---------------------------------------------------------------------------

def test_duplicate_order_number_silently_merges_items_and_keeps_last_metadata(packer_logic_factory, session_factory):
    """Documents current behavior: two orders sharing the same order_number in
    the source JSON are silently merged into a single order (grouped by
    Order_Number), and per-order metadata (destination_country etc.) is taken
    from whichever raw order dict was LAST in the list — the first order's
    metadata is discarded with no warning. If Shopify Tool ever emits a
    duplicate order_number (e.g. a split/re-exported order), the packer would
    show one merged order with items from both, under the second order's
    address/notes.
    """
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=[])
    packing_list = {
        "orders": [
            {
                "order_number": "ORD-DUP", "courier": "DHL", "notes": "first-notes",
                "items": [{"sku": "SKU-1", "quantity": 1}],
            },
            {
                "order_number": "ORD-DUP", "courier": "DHL", "notes": "second-notes",
                "items": [{"sku": "SKU-2", "quantity": 1}],
            },
        ]
    }
    list_path.write_text(json.dumps(packing_list), encoding="utf-8")

    logic = packer_logic_factory("M", work_dir)
    count, _ = logic.load_packing_list_json(list_path)

    assert count == 1  # merged into a single order, not two
    skus = {item["SKU"] for item in logic.orders_data["ORD-DUP"]["items"]}
    assert skus == {"SKU-1", "SKU-2"}
    assert logic.orders_data["ORD-DUP"]["metadata"]["notes"] == "second-notes"  # first is lost


# ---------------------------------------------------------------------------
# load_from_shopify_analysis
# ---------------------------------------------------------------------------

def test_shopify_analysis_defaults_missing_courier_to_na(packer_logic_factory, tmp_path, server_root):
    client_id = "M"
    session_dir = server_root / "Sessions" / f"CLIENT_{client_id}" / "2026-01-01_1"
    (session_dir / "analysis").mkdir(parents=True)
    work_dir = session_dir / "packing" / "Full"
    work_dir.mkdir(parents=True)

    analysis_data = {
        "analyzed_at": "2026-01-01T10:00:00+00:00",
        "orders": [{"order_number": "ORD-1", "items": [{"sku": "SKU-1", "quantity": 1}]}],  # no courier
    }
    (session_dir / "analysis" / "analysis_data.json").write_text(json.dumps(analysis_data), encoding="utf-8")

    logic = packer_logic_factory(client_id, work_dir)
    logic.load_from_shopify_analysis(session_dir)
    assert logic.orders_data["ORD-1"]["items"][0]["Courier"] == "N/A"


def test_shopify_analysis_missing_order_number_raises(packer_logic_factory, tmp_path, server_root):
    client_id = "M"
    session_dir = server_root / "Sessions" / f"CLIENT_{client_id}" / "2026-01-01_1"
    (session_dir / "analysis").mkdir(parents=True)
    work_dir = session_dir / "packing" / "Full"
    work_dir.mkdir(parents=True)

    analysis_data = {"orders": [{"items": [{"sku": "SKU-1", "quantity": 1}]}]}  # no order_number
    (session_dir / "analysis" / "analysis_data.json").write_text(json.dumps(analysis_data), encoding="utf-8")

    logic = packer_logic_factory(client_id, work_dir)
    with pytest.raises(ValueError):
        logic.load_from_shopify_analysis(session_dir)


def test_shopify_analysis_missing_file_raises(packer_logic_factory, tmp_path, server_root):
    client_id = "M"
    session_dir = server_root / "Sessions" / f"CLIENT_{client_id}" / "2026-01-01_1"
    session_dir.mkdir(parents=True)
    work_dir = session_dir / "packing" / "Full"
    work_dir.mkdir(parents=True)

    logic = packer_logic_factory(client_id, work_dir)
    with pytest.raises(ValueError):
        logic.load_from_shopify_analysis(session_dir)
