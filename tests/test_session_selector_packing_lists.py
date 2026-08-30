"""Regression test: the Session Browser must see packing lists uploaded to the
file server after registry_index.json was already built.

This used to be asserted against SessionSelectorDialog, which 8.6 deleted --
its docstring noted the Browser did the same thing via RegistryRefreshWorker
but nothing asserted it. Now it is asserted where the behaviour actually lives.
"""
import json

from conftest import make_packing_list

from gui.session_browser.session_browser_widget import SessionBrowserWidget
from packing_tool.session_history_manager import SessionHistoryManager
from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_registry_manager import SessionRegistryManager
from packing_tool.worker_manager import WorkerManager


def test_the_browser_sees_a_packing_list_uploaded_after_the_registry_was_built(
    qapp, tmp_path, server_root, profile_manager
):
    client_dir = server_root / "Sessions" / "CLIENT_TEST"
    client_dir.mkdir(parents=True)

    # Registry gets built (empty) *before* the packing list exists on disk,
    # simulating a registry_index.json that predates a fresh Shopify upload.
    registry = SessionRegistryManager(profile_manager)
    registry.ensure_registry("TEST")

    session_dir = client_dir / "2026-07-25_1"
    (session_dir / "analysis").mkdir(parents=True)
    (session_dir / "analysis" / "analysis_data.json").write_text(
        json.dumps({"total_orders": 3}), encoding="utf-8"
    )

    (session_dir / "packing_lists").mkdir(parents=True)
    packing_list = make_packing_list(
        [("ORDER-1", "DHL", []), ("ORDER-2", "DHL", []), ("ORDER-3", "DHL", [])]
    )
    (session_dir / "packing_lists" / "ALL_ORDERS.json").write_text(
        json.dumps(packing_list), encoding="utf-8"
    )

    browser = SessionBrowserWidget(
        profile_manager=profile_manager,
        session_lock_manager=SessionLockManager(profile_manager),
        session_history_manager=SessionHistoryManager(profile_manager),
        worker_manager=WorkerManager(str(tmp_path)),
        registry_manager=registry,
    )
    try:
        # Straight to the sessions table: load_clients() is deferred to first
        # show now that the browser is a page, and the client selector is not
        # what is under test here.
        browser.sessions_list.load_client("TEST")

        # load_client() dispatches RegistryRefreshWorker on its own thread and
        # delivers the result as a queued signal. Block on the thread, then
        # pump the event loop once so _on_refresh_complete actually runs --
        # without the pump the entries are still in flight.
        worker = browser.sessions_list._refresh_worker
        assert worker is not None, "load_client did not dispatch a refresh"
        assert worker.wait(10_000), "registry refresh did not finish within 10s"
        qapp.processEvents()

        names = [
            entry.get("packing_list_name", "")
            for entry in browser.sessions_list._all_entries
        ]
        assert "ALL_ORDERS" in names, (
            f"Expected the freshly-uploaded packing list to appear, got: {names}"
        )
    finally:
        browser.deleteLater()
