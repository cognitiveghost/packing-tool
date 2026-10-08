"""A bad packing list says what is missing and what was found (spec section 5)."""

import json

import pytest

from packing_tool.exceptions import PackingListInvalidError


def test_an_order_with_no_courier_says_what_is_missing_and_what_was_found(
    session_factory, packer_logic_factory
):
    orders = [("#1", "DHL", [{"sku": "A", "quantity": 1, "product_name": "A"}])]
    _session, work_dir, list_path = session_factory(client_id="M", orders=orders)
    data = json.loads(list_path.read_text(encoding="utf-8"))
    del data["orders"][0]["courier"]
    list_path.write_text(json.dumps(data), encoding="utf-8")
    logic = packer_logic_factory("M", work_dir)

    with pytest.raises(PackingListInvalidError) as caught:
        logic.load_packing_list_json(list_path)

    assert caught.value.missing == ["courier"]
    assert caught.value.found == ["items", "order_number"]
    assert caught.value.kind == "field"
    # Still what callers have always caught, with the text they matched.
    assert isinstance(caught.value, ValueError)
    assert "Missing required fields in order data" in str(caught.value)
