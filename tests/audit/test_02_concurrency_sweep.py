"""Audit 02: concurrent PCs, file-server behaviour, and the whole-app sweep.

Report: docs/audit/02-concurrency-sweep.md. Each AUDIT-k test reproduced the bug it names before
the fix bundles (strict xfail at audit time); it now guards against its
return. The other tests pin what the audit verified correct.
"""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from gui.main_window import MainWindow
from packing_tool.profile_manager import ProfileManager
from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_registry_manager import SessionRegistryManager
from packing_tool.worker_manager import WorkerManager


def _lock(work_dir: Path, by: str, age_seconds: int, pid: int = 1):
    stamp = (datetime.now().astimezone() - timedelta(seconds=age_seconds)).isoformat()
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": by, "user_name": "x", "lock_time": stamp,
                    "heartbeat": stamp, "process_id": pid}),
        encoding="utf-8",
    )


def _lock_owner(work_dir: Path) -> str:
    return json.loads((work_dir / SessionLockManager.LOCK_FILENAME).read_text())["locked_by"]


# ---------------------------------------------------------------------------
# Verified correct
# ---------------------------------------------------------------------------


def test_two_pcs_racing_for_a_free_list_get_one_lock(profile_manager, tmp_path):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    pc1, pc2 = SessionLockManager(profile_manager), SessionLockManager(profile_manager)
    pc2.hostname = "PC-2"
    results = [pc1.acquire_lock("M", work_dir)[0], pc2.acquire_lock("M", work_dir)[0]]
    assert results == [True, False]


def test_registry_writers_do_not_drop_each_others_entries(profile_manager):
    reg = SessionRegistryManager(profile_manager)
    for n in range(5):
        reg.register_session_start("M", f"s{n}", "L", None, None, "PC", 1, 1, "w", "p")
    assert len(reg.read_registry("M")["sessions"]) == 5


# ---------------------------------------------------------------------------
# AUDIT-02-1  Force-releasing a stale lock deletes whatever lock is there by then
# ---------------------------------------------------------------------------


def test_force_release_after_the_prompt_does_not_steal_a_fresh_lock(main_window, tmp_path, monkeypatch):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    _lock(work_dir, "PC-OLD", age_seconds=600)  # stale: its PC crashed

    def answer_yes_while_pc2_takes_it(*_args, **_kw):
        # The prompt sat open; meanwhile PC-2 force-released and opened the list.
        _lock(work_dir, "PC-2", age_seconds=0, pid=2)
        return main_window_module.QMessageBox.Yes

    import gui.main_window as main_window_module

    monkeypatch.setattr(main_window_module.QMessageBox, "question", answer_yes_while_pc2_takes_it)
    ok, _ = main_window._acquire_lock_with_stale_prompt("M", work_dir)

    assert (ok, _lock_owner(work_dir)) == (False, "PC-2")


# ---------------------------------------------------------------------------
# AUDIT-02-2  A second list can be opened on top of a running one
# ---------------------------------------------------------------------------


def test_opening_a_second_list_is_refused_while_one_is_packing(main_window, tmp_path, monkeypatch):
    main_window.logic = Mock()
    main_window.current_work_dir = str(tmp_path / "A")
    started = []
    monkeypatch.setattr(main_window, "start_shopify_packing_session", lambda **kw: started.append(kw) or False)
    monkeypatch.setattr("gui.main_window.QMessageBox.warning", lambda *a, **k: None)

    main_window._start_or_resume_from_browser(
        "TESTCL", "B", tmp_path, tmp_path / "B.json", work_dir=tmp_path / "B"
    )
    assert started == []


# ---------------------------------------------------------------------------
# AUDIT-02-3  SKU mapping saves replace the table from a stale view
# ---------------------------------------------------------------------------


def _map_on(pc: ProfileManager, barcode: str, sku: str) -> None:
    """MainWindow._save_sku_mapping as it runs on one PC."""
    window = SimpleNamespace(
        profile_manager=pc, current_client_id="M", logic=None, packer_mode_widget=Mock()
    )
    assert MainWindow._save_sku_mapping(window, barcode, sku)


def test_a_mapping_saved_on_one_pc_survives_a_save_on_another(config_ini):
    pc1, pc2 = ProfileManager(str(config_ini)), ProfileManager(str(config_ini))
    pc1.create_client_profile("M", "M")
    pc2.load_sku_mapping("M")  # PC-2 opened a list a moment ago: mapping cached

    _map_on(pc1, "111", "SKU-1")
    _map_on(pc2, "222", "SKU-2")

    assert pc1.load_sku_mapping("M") == {"111": "SKU-1", "222": "SKU-2"}


def test_an_unreadable_mapping_file_is_not_saved_over(config_ini, monkeypatch):
    pc = ProfileManager(str(config_ini))
    pc.create_client_profile("M", "M")
    pc.save_sku_mapping("M", {f"{n}": f"SKU-{n}" for n in range(50)})
    pc._sku_cache.clear()

    config = pc.clients_dir / "CLIENT_M" / "packer_config.json"
    good = config.read_text(encoding="utf-8")
    config.write_text("", encoding="utf-8")  # read mid-way through another PC's rewrite
    loaded = pc.load_sku_mapping("M")
    config.write_text(good, encoding="utf-8")  # that rewrite lands

    pc._sku_cache["sku_M"] = (loaded, datetime.now().astimezone())
    try:
        _map_on(pc, "999", "SKU-999")
    except AssertionError:
        pass  # refusing to save is an acceptable fix
    assert len(pc.load_sku_mapping("M")) >= 50


# ---------------------------------------------------------------------------
# AUDIT-02-4  Worker stats: an unlocked read-modify-write on a shared file
# ---------------------------------------------------------------------------


def test_two_pcs_ending_sessions_together_both_count(server_root):
    pc1, pc2 = WorkerManager(str(server_root)), WorkerManager(str(server_root))
    worker = pc1.create_worker("Ana")

    loaded, release = threading.Event(), threading.Event()
    plain_load = pc1._load_workers_registry

    def slow_load():
        data = plain_load()
        loaded.set()
        release.wait(2)
        return data

    pc1._load_workers_registry = slow_load
    first = threading.Thread(target=lambda: pc1.update_worker_stats(worker.id, orders=3))
    first.start()
    loaded.wait(2)
    second = threading.Thread(target=lambda: pc2.update_worker_stats(worker.id, orders=5))
    second.start()
    second.join(0.5)
    release.set()
    first.join()
    second.join()

    assert pc2.get_worker(worker.id).total_orders == 8


# ---------------------------------------------------------------------------
# AUDIT-02-5  A failed registry read is saved back as an empty registry
# ---------------------------------------------------------------------------


def test_a_failed_registry_read_does_not_wipe_it(profile_manager, monkeypatch):
    reg = SessionRegistryManager(profile_manager)
    for n in range(3):
        reg.register_session_start("M", f"s{n}", "L", None, None, "PC", 1, 1, "w", "p")

    real_open = open
    path = str(reg._get_registry_path("M"))
    failed = []

    def flaky_open(file, *a, **k):
        if str(file) == path and not failed and "r" in (a[0] if a else k.get("mode", "r")):
            failed.append(True)
            raise PermissionError(13, "sharing violation")
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", flaky_open)
    reg.register_session_start("M", "s9", "L", None, None, "PC", 1, 1, "w", "p")
    monkeypatch.undo()

    assert len(reg.read_registry("M")["sessions"]) == 4


# ---------------------------------------------------------------------------
# AUDIT-02-6  The client picker stays live during a session
# ---------------------------------------------------------------------------


def test_the_client_cannot_change_under_a_running_list(main_window_with_list, tmp_path):
    window = main_window_with_list
    combo = window.client_combo
    logic, window.logic = window.logic, None  # pick the client before the list opens
    combo.setCurrentIndex(combo.findData("TESTCL"))
    window.logic = logic
    window.current_work_dir = str(tmp_path)
    window.current_session_path = str(tmp_path)
    window.enable_packing_mode()

    combo.setCurrentIndex(combo.findData("OTHERCL"))
    assert window.current_client_id == "TESTCL"


# ---------------------------------------------------------------------------
# AUDIT-02-7  Every scan rebuilds the whole (hidden) order tree
# ---------------------------------------------------------------------------


def test_a_scan_does_not_rebuild_the_order_tree(main_window_with_list, monkeypatch):
    window = main_window_with_list
    window.logic.item_packed.connect(window._on_item_packed)  # as start_shopify_packing_session wires it
    rebuilds = []
    monkeypatch.setattr(window, "_populate_order_tree", lambda: rebuilds.append(True))
    window.on_scanner_input("#10429")
    window.logic.current_order_state[0]["required"] = 2  # so the scan is SKU_OK, not complete
    window.on_scanner_input("TS-4409-B")
    assert rebuilds == []  # the tree is on the other page; rebuild it when that page is shown


# ---------------------------------------------------------------------------
# AUDIT-02-8  The heartbeat runs off the UI thread, and still notices a takeover
# ---------------------------------------------------------------------------


def test_the_heartbeat_runs_off_the_ui_thread_and_notices_a_takeover(main_window, tmp_path, monkeypatch, qtbot):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    _lock(work_dir, "PC-2", age_seconds=0, pid=2)
    main_window.logic = Mock()
    main_window.current_work_dir = str(work_dir)
    main_window.current_packing_list = "L"
    monkeypatch.setattr("gui.main_window.QMessageBox.critical", lambda *a: None)
    threads = []
    renew = main_window.lock_manager.update_heartbeat
    monkeypatch.setattr(
        main_window.lock_manager, "update_heartbeat",
        lambda d: threads.append(threading.current_thread().name) or renew(d),
    )

    main_window._heartbeat_tick()
    qtbot.waitUntil(lambda: main_window.logic is None, timeout=3000)

    assert threads == ["heartbeat"]
    assert _lock_owner(work_dir) == "PC-2"  # not ours to delete


# ---------------------------------------------------------------------------
# AUDIT-02-9  The row's Confirm button is recorded as a scan
# ---------------------------------------------------------------------------


def test_a_confirm_click_is_not_recorded_as_a_scan(main_window_with_list):
    window = main_window_with_list
    window.on_scanner_input("#10429")
    window.packer_mode_widget._on_manual_confirm(0)
    record = window.logic.completed_orders_metadata[-1]["items"][0]
    assert record["confirmation_method"] != "scanned"


# ---------------------------------------------------------------------------
# AUDIT-02-10  The history column calls an order complete when it is opened
# ---------------------------------------------------------------------------


def test_an_opened_order_is_not_shown_as_complete(main_window_with_list):
    window = main_window_with_list
    window.on_scanner_input("#10429")
    assert {"order": "#10429", "status": "complete"} not in window.packer_mode_widget._history


def test_a_skipped_order_appears_once_in_history(main_window_with_list):
    window = main_window_with_list
    window.on_scanner_input("#10429")
    window._on_skip_order()
    orders = [h["order"] for h in window.packer_mode_widget._history]
    assert orders.count("#10429") == 1


# ---------------------------------------------------------------------------
# AUDIT-02-11  Another order's barcode mid-order reads as an unknown SKU
# ---------------------------------------------------------------------------


def test_scanning_the_next_orders_barcode_is_not_an_unknown_sku(main_window_with_list):
    logic = main_window_with_list.logic
    logic.start_order_packing("#10429")
    _, status = logic.process_sku_scan("#10430")
    assert status != "SKU_NOT_FOUND" and logic.unknown_scans == []


# ---------------------------------------------------------------------------
# AUDIT-02-12  The state snapshot handed to the writer thread is live
# ---------------------------------------------------------------------------


def test_the_state_snapshot_does_not_change_after_it_is_taken(main_window_with_list):
    logic = main_window_with_list.logic
    logic.start_order_packing("#10429")
    snapshot = logic._build_state_dict()
    frozen = json.dumps(snapshot, sort_keys=True, default=str)
    logic.process_sku_scan("TS-4409-B")  # completes #10429
    assert json.dumps(snapshot, sort_keys=True, default=str) == frozen


# ---------------------------------------------------------------------------
# AUDIT-02-13  "Order ##1001 is already packed"
# ---------------------------------------------------------------------------


def test_already_packed_message_has_one_hash(main_window_with_list):
    window = main_window_with_list
    window.on_scanner_input("#10429")
    window.on_scanner_input("TS-4409-B")
    window.on_scanner_input("#10429")
    assert "##" not in window.packer_mode_widget._feedback_text
