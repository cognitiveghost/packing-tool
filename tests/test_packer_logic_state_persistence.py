"""Scan-progress persistence & crash-recovery accuracy (target #2).

Every scan is supposed to be safely persisted so a crash/restart never loses
or corrupts progress, and never resurrects stale/foreign state into a fresh
session. These tests exercise the *real* file writes (via AsyncStateWriter's
background thread + the atomic temp-file-then-rename in
PackerLogic._do_atomic_write), not a stubbed writer.
"""
import copy
import json

from packing_tool.json_cache import get_cached_json


def _read_state_file(work_dir):
    return json.loads((work_dir / "packing_state.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Round-trip save/load
# ---------------------------------------------------------------------------

def test_scan_progress_survives_a_restart(loaded_logic, packer_logic_factory, session_factory):
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")  # 1/2 packed
    loaded_logic.save_state()  # sync checkpoint, waits for the write to land

    on_disk = _read_state_file(loaded_logic.work_dir)
    assert on_disk["progress"]["packed_items"] == 1
    assert on_disk["in_progress"]["ORDER-001"][0]["packed"] == 1

    # Simulate an app restart: brand new PackerLogic over the same work_dir.
    restarted = packer_logic_factory("M", loaded_logic.work_dir)
    assert restarted.session_packing_state["in_progress"]["ORDER-001"][0]["packed"] == 1


def test_completed_order_checkpoint_is_synchronous(loaded_logic):
    """ORDER_COMPLETE must flush to disk before process_sku_scan() returns —
    the UI transitions away immediately afterwards, so this is the last chance
    to persist before the in-memory order state is cleared.
    """
    loaded_logic.start_order_packing("ORDER-002")
    loaded_logic.process_sku_scan("SKU-CCC")  # completes the only item -> ORDER_COMPLETE

    on_disk = _read_state_file(loaded_logic.work_dir)  # no explicit flush call
    assert "ORDER-002" in [o["order_number"] for o in on_disk["completed"]]
    assert on_disk["progress"]["completed_orders"] == 1


def test_sku_ok_writes_land_after_flush(loaded_logic):
    """Non-terminal scans are async (schedule() only) — flush() is required
    before the write is guaranteed to be on disk, by design (hot-path latency).
    """
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.process_sku_scan("SKU-AAA")
    loaded_logic._state_writer.flush()

    on_disk = _read_state_file(loaded_logic.work_dir)
    assert on_disk["in_progress"]["ORDER-001"][0]["packed"] == 1


# ---------------------------------------------------------------------------
# Crash-recovery validation of malformed / legacy on-disk state
# ---------------------------------------------------------------------------

def test_legacy_item_format_is_migrated_on_load(packer_logic_factory, session_factory):
    orders = [("ORDER-001", "DHL", [{"sku": "SKU-AAA", "quantity": 2, "product_name": "Widget"}])]
    _session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)

    legacy_state = {
        "in_progress": {
            "ORDER-001": [
                {"sku": "SKU-AAA", "packed": 1}  # legacy key, no 'required'/'row'/'normalized_sku'
            ]
        },
        "completed_orders": [],
    }
    (work_dir / "packing_state.json").write_text(json.dumps(legacy_state), encoding="utf-8")

    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)

    item = logic.session_packing_state["in_progress"]["ORDER-001"][0]
    assert item["original_sku"] == "SKU-AAA"
    assert item["normalized_sku"] == "skuaaa"
    assert item["packed"] == 1
    assert item["required"] == 0  # filled with a lenient default, not the real packing-list qty
    assert item["row"] == 0


def test_malformed_order_state_is_skipped_without_crashing(packer_logic_factory, session_factory):
    orders = [
        ("ORDER-GOOD", "DHL", [{"sku": "SKU-1", "quantity": 1, "product_name": "A"}]),
        ("ORDER-BAD", "DHL", [{"sku": "SKU-2", "quantity": 1, "product_name": "B"}]),
        ("ORDER-BAD2", "DHL", [{"sku": "SKU-3", "quantity": 1, "product_name": "C"}]),
    ]
    _session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)

    corrupt_state = {
        "in_progress": {
            "ORDER-GOOD": [{"sku": "SKU-1", "packed": 0, "required": 1, "row": 0}],
            "ORDER-BAD": "not-a-list",       # order_state must be a list
            "ORDER-BAD2": ["not-a-dict"],    # item_state must be a dict
        },
        "completed_orders": ["ORDER-OLD"],
    }
    (work_dir / "packing_state.json").write_text(json.dumps(corrupt_state), encoding="utf-8")

    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)  # must not raise

    assert "ORDER-GOOD" in logic.session_packing_state["in_progress"]
    assert "ORDER-BAD" not in logic.session_packing_state["in_progress"]
    assert "ORDER-BAD2" not in logic.session_packing_state["in_progress"]
    assert logic.session_packing_state["completed_orders"] == ["ORDER-OLD"]


def test_missing_state_file_starts_fresh(packer_logic_factory, session_factory):
    orders = [("ORDER-001", "DHL", [{"sku": "SKU-1", "quantity": 1, "product_name": "A"}])]
    _session_dir, work_dir, _list_path = session_factory(client_id="M", orders=orders)

    logic = packer_logic_factory("M", work_dir)
    assert logic.session_packing_state == {
        "in_progress": {}, "completed_orders": [], "skipped_orders": [], "skipped_orders_timing": {}
    }


def test_corrupted_json_state_file_starts_fresh_instead_of_crashing(packer_logic_factory, session_factory):
    orders = [("ORDER-001", "DHL", [{"sku": "SKU-1", "quantity": 1, "product_name": "A"}])]
    _session_dir, work_dir, _list_path = session_factory(client_id="M", orders=orders)
    (work_dir / "packing_state.json").write_text("{not valid json", encoding="utf-8")

    logic = packer_logic_factory("M", work_dir)  # must not raise
    assert logic.session_packing_state["in_progress"] == {}


# ---------------------------------------------------------------------------
# Regression test: pending extra-item flags used to be silently lost across
# a crash/restart.
#
# PackerLogic.__init__ used to do:
#     self._load_session_state()                        # restores current_extra_items from disk
#     self.current_extra_items: Dict[str, int] = {}      # ...then immediately wiped it again
# So `_current_extras` round-tripped to disk correctly but was dead on read:
# whatever _load_session_state() restored was discarded two lines later in
# the same constructor, every single time.
# ---------------------------------------------------------------------------

def test_unresolved_extras_survive_a_restart(packer_logic_factory, session_factory):
    orders = [("ORDER-A", "DHL", [
        {"sku": "SKU-1", "quantity": 1, "product_name": "A1"},
        {"sku": "SKU-2", "quantity": 1, "product_name": "A2"},
    ])]
    _session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)

    instance1 = packer_logic_factory("M", work_dir)
    instance1.load_packing_list_json(list_path)
    instance1.start_order_packing("ORDER-A")
    instance1.process_sku_scan("SKU-1")  # 1/1
    instance1.process_sku_scan("SKU-1")  # over-scan -> current_extra_items = {"sku1": 1}
    # SKU-2 deliberately left unscanned; extra deliberately left unresolved.
    instance1.save_state()

    # --- simulate crash + restart: fresh PackerLogic over the same work_dir ---
    instance2 = packer_logic_factory("M", work_dir)
    assert instance2.current_extra_items == {"sku1": 1}, (
        "the pending extra flagged before the crash must still be there after restart, "
        f"got {instance2.current_extra_items!r} instead"
    )

    # Consequence if it isn't: resuming and finishing the order silently completes
    # it clean, even though a real extra unit is still sitting unresolved in the box.
    instance2.load_packing_list_json(list_path)
    instance2.start_order_packing("ORDER-A")
    _result, status = instance2.process_sku_scan("SKU-2")  # the only remaining required item
    assert status == "ORDER_COMPLETE_WITH_EXTRAS", (
        f"expected the pending extra to block clean completion, got {status!r}"
    )


# ---------------------------------------------------------------------------
# Regression test: get_cached_json() used to hand out the live cached object
# by reference. _load_session_state() mutates item dicts in place
# (legacy-field migration), which used to silently poison the shared
# process-wide JSON cache for every other reader of the same path (e.g.
# Session Browser) without ever writing to disk.
# ---------------------------------------------------------------------------

def test_json_cache_is_not_mutated_by_in_memory_migration(packer_logic_factory, session_factory):
    orders = [("ORDER-001", "DHL", [{"sku": "SKU-AAA", "quantity": 2, "product_name": "Widget"}])]
    _session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)

    legacy_state = {
        "in_progress": {"ORDER-001": [{"sku": "SKU-AAA", "packed": 0}]},  # no 'required'/'row'
        "completed_orders": [],
    }
    state_path = work_dir / "packing_state.json"
    state_path.write_text(json.dumps(legacy_state), encoding="utf-8")

    disk_snapshot_before = copy.deepcopy(json.loads(state_path.read_text(encoding="utf-8")))

    # Warm the cache the way Session Browser would, before packing starts.
    get_cached_json(state_path, default=None)

    logic = packer_logic_factory("M", work_dir)  # triggers the in-place migration
    logic.load_packing_list_json(list_path)

    cache_after = get_cached_json(state_path, default=None)  # still within TTL: cache hit
    disk_after = json.loads(state_path.read_text(encoding="utf-8"))  # ground truth, bypass cache

    assert cache_after == disk_snapshot_before, (
        "in-memory field migration leaked into the shared JSON cache "
        f"even though nothing was written to disk yet: {cache_after}"
    )
    assert disk_after == disk_snapshot_before  # the file on disk is untouched, as expected
