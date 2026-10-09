"""Regression test: the Sessions page must see packing lists uploaded to the
file server after registry_index.json was already built.

Asserted against the Qt Session Browser until phase 4 of the UI refresh
deleted it; RegistryRefreshWorker does the work either way.
"""
import json

from conftest import make_packing_list

from gui.app_bridge import AppBridge
from gui.sessions_page import SessionsPage
from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_registry_manager import SessionRegistryManager


def test_the_sessions_page_sees_a_packing_list_uploaded_after_the_registry_was_built(
    qapp, server_root, profile_manager
):
    client_dir = server_root / "Sessions" / "CLIENT_TEST"
    client_dir.mkdir(parents=True)

    # The registry is built (empty) *before* the packing list exists on disk,
    # as a registry_index.json that predates a fresh Shopify upload would be.
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

    bridge = AppBridge()
    page = SessionsPage(bridge, registry, SessionLockManager(profile_manager))
    try:
        page.load_client("TEST")
        page.wait()
        qapp.processEvents()
        qapp.processEvents()
        # The list was made on a fixed date long ago: no date bound.
        bridge.setSessionsFilter("all", "", "", "")
        names = [row["list"] for row in bridge.sessions["rows"]]
        assert "ALL_ORDERS" in names, (
            f"Expected the freshly-uploaded packing list to appear, got: {names}"
        )
    finally:
        page.shutdown()
