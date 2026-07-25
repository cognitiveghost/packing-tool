"""Core scanning / order-status-change business logic (targets #2, #3).

Covers PackerLogic.start_order_packing / process_sku_scan / cancel_item_scan /
force_confirm_item / skip_order / confirm_keep_extra / remove_extra_item, and
the all_orders_complete signal — the exact sequence a warehouse worker drives
via barcode scans.
"""


# ---------------------------------------------------------------------------
# start_order_packing
# ---------------------------------------------------------------------------

def test_start_order_packing_loads_order(loaded_logic):
    items, status = loaded_logic.start_order_packing("ORDER-001")
    assert status == "ORDER_LOADED"
    assert loaded_logic.current_order_number == "ORDER-001"
    assert len(items) == 2


def test_start_order_packing_unknown_order(loaded_logic):
    items, status = loaded_logic.start_order_packing("NO-SUCH-ORDER")
    assert status == "ORDER_NOT_FOUND"
    assert items is None
    assert loaded_logic.current_order_number is None


def test_start_order_packing_normalizes_barcode_noise(loaded_logic):
    """Scanner may add punctuation the printed barcode didn't strictly need."""
    _, status = loaded_logic.start_order_packing("#ORDER-001!")
    assert status == "ORDER_LOADED"
    assert loaded_logic.current_order_number == "ORDER-001"


def test_start_order_packing_already_completed(loaded_logic):
    loaded_logic.start_order_packing("ORDER-002")
    loaded_logic.process_sku_scan("SKU-CCC")  # completes the only item -> ORDER_COMPLETE
    loaded_logic.clear_current_order()

    _, status = loaded_logic.start_order_packing("ORDER-002")
    assert status == "ORDER_ALREADY_COMPLETED"
    assert loaded_logic.current_order_number is None


# ---------------------------------------------------------------------------
# process_sku_scan — happy path, multi-quantity, completion
# ---------------------------------------------------------------------------

def test_scan_no_active_order_returns_no_active_order(loaded_logic):
    result, status = loaded_logic.process_sku_scan("SKU-AAA")
    assert status == "NO_ACTIVE_ORDER"
    assert result is None


def test_scan_increments_packed_count_for_multi_quantity_item(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    result, status = loaded_logic.process_sku_scan("SKU-AAA")  # requires 2
    assert status == "SKU_OK"
    assert result == {"row": 0, "packed": 1, "is_complete": False}

    result, status = loaded_logic.process_sku_scan("SKU-AAA")
    assert status == "SKU_OK"
    assert result["packed"] == 2
    assert result["is_complete"] is True  # this item's own requirement is met


def test_scan_completes_order_only_when_every_item_done(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")
    loaded_logic.process_sku_scan("SKU-AAA")  # SKU-AAA fully packed, SKU-BBB still pending
    result, status = loaded_logic.process_sku_scan("SKU-BBB")
    assert status == "ORDER_COMPLETE"
    assert loaded_logic.current_order_number == "ORDER-001"  # not auto-cleared; caller's job
    assert "ORDER-001" in loaded_logic.session_packing_state["completed_orders"]
    assert "ORDER-001" not in loaded_logic.session_packing_state["in_progress"]


def test_scan_wrong_sku_returns_sku_not_found_and_is_recorded(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    result, status = loaded_logic.process_sku_scan("SKU-DOES-NOT-EXIST")
    assert status == "SKU_NOT_FOUND"
    assert result is None
    assert "SKU-DOES-NOT-EXIST" in loaded_logic.unknown_scans
    assert loaded_logic.current_order_unknown_scan_count == 1


def test_scan_beyond_required_quantity_is_extra_not_silently_accepted(loaded_logic):
    loaded_logic.start_order_packing("ORDER-002")  # SKU-CCC requires 1
    loaded_logic.process_sku_scan("SKU-CCC")
    result, status = loaded_logic.process_sku_scan("SKU-CCC")  # second scan of a qty-1 item
    assert status == "SKU_EXTRA"
    assert loaded_logic.current_extra_items == {"skuccc": 1}


def test_sku_normalization_ignores_case_and_punctuation(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    result, status = loaded_logic.process_sku_scan("sku-aaa")  # lowercase + dash
    assert status == "SKU_OK"
    assert result["row"] == 0


def test_sku_map_translates_barcode_to_internal_sku(packer_logic_factory, session_factory, profile_manager):
    orders = [("ORDER-001", "DHL", [{"sku": "INTERNAL-SKU-1", "quantity": 1, "product_name": "Widget"}])]
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)
    profile_manager.create_client_profile("M", "Test Client")
    profile_manager.save_sku_mapping("M", {"7290018664100": "INTERNAL-SKU-1"})

    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)
    logic.start_order_packing("ORDER-001")

    result, status = logic.process_sku_scan("7290018664100")  # scan the manufacturer barcode
    assert status == "ORDER_COMPLETE"  # single item, qty 1 -> this scan finishes the order
    assert result["is_complete"] is True


# ---------------------------------------------------------------------------
# cancel_item_scan (undo)
# ---------------------------------------------------------------------------

def test_cancel_item_scan_decrements_packed_count(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")
    result, status = loaded_logic.cancel_item_scan(0)
    assert status == "ITEM_DECREMENTED"
    assert result["packed"] == 0
    assert loaded_logic.current_order_corrections == 1


def test_cancel_item_scan_at_zero_is_a_noop(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    result, status = loaded_logic.cancel_item_scan(0)
    assert status == "ITEM_ALREADY_ZERO"
    assert result["packed"] == 0


def test_cancel_item_scan_without_active_order(loaded_logic):
    result, status = loaded_logic.cancel_item_scan(0)
    assert status == "NO_ACTIVE_ORDER"


def test_cancel_after_order_complete_is_rejected_because_current_order_is_cleared(loaded_logic):
    """UI convention: clear_current_order() runs immediately after ORDER_COMPLETE
    (see main.py::on_scanner_input). Verify cancel/force-confirm are correctly
    guarded once that happens, so a stray button click can't resurrect a
    completed order back into in_progress alongside completed_orders.
    """
    loaded_logic.start_order_packing("ORDER-002")
    loaded_logic.process_sku_scan("SKU-CCC")
    assert "ORDER-002" in loaded_logic.session_packing_state["completed_orders"]

    loaded_logic.clear_current_order()  # what the UI does right after ORDER_COMPLETE

    result, status = loaded_logic.cancel_item_scan(0)
    assert status == "NO_ACTIVE_ORDER"
    # Order must not have been resurrected into in_progress
    assert "ORDER-002" not in loaded_logic.session_packing_state["in_progress"]


def test_cancel_item_scan_removes_matching_scan_record_by_row_not_sku(loaded_logic):
    """Two rows can share a SKU (split-line orders) — cancelling one row must not
    touch the scan record belonging to the other row.
    """
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")  # row 0, packed 1/2
    loaded_logic.process_sku_scan("SKU-AAA")  # row 0, packed 2/2 -> complete
    assert len(loaded_logic.current_order_items_scanned) == 2

    loaded_logic.cancel_item_scan(0)
    assert len(loaded_logic.current_order_items_scanned) == 1
    assert loaded_logic.current_order_state[0]["packed"] == 1


# ---------------------------------------------------------------------------
# force_confirm_item
# ---------------------------------------------------------------------------

def test_force_confirm_completes_item_and_records_remaining_qty(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    result, status = loaded_logic.force_confirm_item(0)  # SKU-AAA requires 2, 0 packed
    assert status == "FORCE_CONFIRMED"
    assert result["packed"] == 2
    assert result["is_complete"] is True
    assert result["order_complete"] is False  # SKU-BBB still pending
    assert loaded_logic.current_order_items_scanned[-1]["quantity"] == 2
    assert loaded_logic.current_order_items_scanned[-1]["confirmation_method"] == "force_confirmed"


def test_force_confirm_completes_whole_order_when_last_item(loaded_logic):
    loaded_logic.start_order_packing("ORDER-002")
    result, status = loaded_logic.force_confirm_item(0)
    assert status == "FORCE_CONFIRMED"
    assert result["order_complete"] is True
    assert "ORDER-002" in loaded_logic.session_packing_state["completed_orders"]


def test_force_confirm_on_partially_scanned_item_only_adds_remaining_record(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")  # 1/2 packed via real scan
    loaded_logic.force_confirm_item(0)         # force the remaining 1 unit
    force_records = [r for r in loaded_logic.current_order_items_scanned if r["confirmation_method"] == "force_confirmed"]
    assert len(force_records) == 1
    assert force_records[0]["quantity"] == 1  # only the remaining unit, not the full requirement


def test_force_confirm_without_active_order(loaded_logic):
    result, status = loaded_logic.force_confirm_item(0)
    assert status == "NO_ACTIVE_ORDER"


# ---------------------------------------------------------------------------
# Extra items: confirm_keep_extra / remove_extra_item
# ---------------------------------------------------------------------------

def test_extra_scan_on_a_not_yet_complete_order_does_not_finish_it(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")
    loaded_logic.process_sku_scan("SKU-AAA")  # SKU-AAA done (2/2), SKU-BBB still pending
    result, status = loaded_logic.process_sku_scan("SKU-AAA")  # over-scan SKU-AAA
    assert status == "SKU_EXTRA"
    assert "ORDER-001" not in loaded_logic.session_packing_state["completed_orders"]


def test_order_complete_with_extras_status_when_last_required_item_scanned(packer_logic_factory, session_factory):
    """ORDER_COMPLETE_WITH_EXTRAS fires when the scan that completes the last
    required item lands while an earlier over-scan on a different SKU is
    still pending resolution.
    """
    orders = [("ORDER-X", "DHL", [
        {"sku": "SKU-1", "quantity": 1, "product_name": "A"},
        {"sku": "SKU-2", "quantity": 1, "product_name": "B"},
    ])]
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)
    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)

    logic.start_order_packing("ORDER-X")
    logic.process_sku_scan("SKU-1")        # 1/1, order not complete yet (SKU-2 pending)
    logic.process_sku_scan("SKU-1")        # extra on SKU-1
    result, status = logic.process_sku_scan("SKU-2")  # completes required qty for every item

    assert status == "ORDER_COMPLETE_WITH_EXTRAS"
    assert "ORDER-X" not in logic.session_packing_state["completed_orders"]
    assert logic.current_extra_items == {"sku1": 1}


def test_confirm_keep_extra_completes_order_once_all_extras_resolved(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")
    loaded_logic.process_sku_scan("SKU-AAA")  # SKU-AAA done (2/2)
    loaded_logic.process_sku_scan("SKU-AAA")  # SKU_EXTRA, current_extra_items = {"skuaaa": 1}
    loaded_logic.process_sku_scan("SKU-BBB")  # completes required qty everywhere -> WITH_EXTRAS
    assert loaded_logic.current_extra_items == {"skuaaa": 1}
    assert "ORDER-001" not in loaded_logic.session_packing_state["completed_orders"]

    result, status = loaded_logic.confirm_keep_extra("skuaaa")
    assert status == "ORDER_NOW_COMPLETE"
    assert "ORDER-001" in loaded_logic.session_packing_state["completed_orders"]
    assert loaded_logic.current_extra_items == {}


def test_remove_extra_item_decrements_before_clearing(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")
    loaded_logic.process_sku_scan("SKU-AAA")
    loaded_logic.process_sku_scan("SKU-AAA")  # extra count = 1
    loaded_logic.process_sku_scan("SKU-AAA")  # extra count = 2
    loaded_logic.process_sku_scan("SKU-BBB")  # completes required qty everywhere -> WITH_EXTRAS
    assert loaded_logic.current_extra_items["skuaaa"] == 2

    _, status = loaded_logic.remove_extra_item("skuaaa")
    assert status == "EXTRA_PENDING"
    assert loaded_logic.current_extra_items["skuaaa"] == 1

    _, status = loaded_logic.remove_extra_item("skuaaa")
    assert status == "ORDER_NOW_COMPLETE"
    assert "skuaaa" not in loaded_logic.current_extra_items
    assert "ORDER-001" in loaded_logic.session_packing_state["completed_orders"]


# ---------------------------------------------------------------------------
# skip_order / resume
# ---------------------------------------------------------------------------

def test_skip_order_preserves_progress_for_resume(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")  # 1/2 packed
    loaded_logic.skip_order()

    assert loaded_logic.current_order_number is None
    assert "ORDER-001" in loaded_logic.session_packing_state["skipped_orders"]
    assert "ORDER-001" in loaded_logic.session_packing_state["in_progress"]

    # Resume: packed progress must still be there, not reset
    loaded_logic.start_order_packing("ORDER-001")
    assert loaded_logic.current_order_state[0]["packed"] == 1


# Regression test: start_order_packing() used to never call
# _unskip_current_order_if_needed() (only full completion did). An order that
# was skipped and then resumed but not yet re-completed stayed in
# skipped_orders, so session_browser/orders_tab.py._load_orders() rendered it
# as a grey '[SKIPPED]' row even while it was being actively re-packed.
def test_resuming_a_skipped_order_should_clear_it_from_the_skipped_list(loaded_logic):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.skip_order()

    loaded_logic.start_order_packing("ORDER-001")  # worker comes back and resumes it
    assert "ORDER-001" not in loaded_logic.session_packing_state["skipped_orders"]


def test_completing_a_previously_skipped_order_unskips_it(loaded_logic):
    loaded_logic.start_order_packing("ORDER-002")
    loaded_logic.skip_order()
    assert "ORDER-002" in loaded_logic.session_packing_state["skipped_orders"]

    loaded_logic.start_order_packing("ORDER-002")
    loaded_logic.process_sku_scan("SKU-CCC")
    assert "ORDER-002" not in loaded_logic.session_packing_state["skipped_orders"]
    assert "ORDER-002" in loaded_logic.session_packing_state["completed_orders"]


def test_skip_order_without_active_order_is_a_noop(loaded_logic):
    loaded_logic.skip_order()  # must not raise
    assert loaded_logic.session_packing_state["skipped_orders"] == []


# ---------------------------------------------------------------------------
# all_orders_complete signal
# ---------------------------------------------------------------------------

def test_all_orders_complete_signal_fires_when_all_done(loaded_logic, qapp):
    received = []
    loaded_logic.all_orders_complete.connect(lambda: received.append(True))

    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")
    loaded_logic.process_sku_scan("SKU-AAA")
    loaded_logic.process_sku_scan("SKU-BBB")
    assert received == []  # only 1 of 2 orders done

    loaded_logic.start_order_packing("ORDER-002")
    loaded_logic.process_sku_scan("SKU-CCC")
    assert received == [True]


def test_all_orders_complete_counts_skipped_orders_as_done(loaded_logic, qapp):
    received = []
    loaded_logic.all_orders_complete.connect(lambda: received.append(True))

    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.skip_order()
    assert received == []

    loaded_logic.start_order_packing("ORDER-002")
    loaded_logic.process_sku_scan("SKU-CCC")
    assert received == [True]
