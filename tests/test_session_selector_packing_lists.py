"""Regression test: Session Selector must see packing lists uploaded to the
file server after registry_index.json was already built, same as Session
Browser does via RegistryRefreshWorker. See session_selector.py's
_scan_shopify_sessions() registry refresh call.
"""
import json

from conftest import make_packing_list

from session_registry_manager import SessionRegistryManager
from session_selector import SessionSelectorDialog


def test_session_selector_sees_packing_list_uploaded_after_registry_build(
    server_root, profile_manager
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

    dialog = SessionSelectorDialog(profile_manager, pre_selected_client="TEST")
    try:
        assert dialog.sessions_list.count() == 1
        dialog.sessions_list.setCurrentItem(dialog.sessions_list.item(0))

        texts = [
            dialog.packing_lists_widget.item(i).text()
            for i in range(dialog.packing_lists_widget.count())
        ]
        assert any("ALL_ORDERS" in t for t in texts), (
            f"Expected the freshly-uploaded packing list to appear, got: {texts}"
        )
    finally:
        dialog.deleteLater()
