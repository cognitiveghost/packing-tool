import json

from session_manager import SessionManager


def _mgr():
    return SessionManager(
        client_id="ALMADERM",
        profile_manager=None,
        lock_manager=None,
        worker_id="worker_001",
        worker_name="test",
    )


def _seed_session_info(tmp_path):
    (tmp_path / "session_info.json").write_text(
        json.dumps({"session_name": "2026-08-18_1", "client_id": "ALMADERM"}),
        encoding="utf-8",
    )


def _read(tmp_path):
    return json.loads((tmp_path / "session_info.json").read_text(encoding="utf-8"))


def test_completed_orders_are_recorded(tmp_path):
    _seed_session_info(tmp_path)

    _mgr().update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed",
        completed_orders=["#11019512", "#11019513"],
    )

    block = _read(tmp_path)["packing_progress"]["ALL_ORDERS"]
    assert block["completed_orders"] == ["#11019512", "#11019513"]
    assert block["status"] == "completed"


def test_call_without_orders_still_works(tmp_path):
    """Pre-existing three-argument callers must keep working."""
    _seed_session_info(tmp_path)

    _mgr().update_session_metadata(str(tmp_path), "ALL_ORDERS", "in_progress")

    block = _read(tmp_path)["packing_progress"]["ALL_ORDERS"]
    assert block["status"] == "in_progress"
    assert "completed_orders" not in block


def test_orders_are_merged_not_replaced_across_calls(tmp_path):
    """A resumed session must not lose orders packed before the resume."""
    _seed_session_info(tmp_path)
    mgr = _mgr()

    mgr.update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#A"]
    )
    mgr.update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#B"]
    )

    block = _read(tmp_path)["packing_progress"]["ALL_ORDERS"]
    assert sorted(block["completed_orders"]) == ["#A", "#B"]


def test_other_keys_in_session_info_are_preserved(tmp_path):
    _seed_session_info(tmp_path)

    _mgr().update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#A"]
    )

    data = _read(tmp_path)
    assert data["session_name"] == "2026-08-18_1"
    assert data["client_id"] == "ALMADERM"


def test_missing_session_info_does_not_raise(tmp_path):
    _mgr().update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#A"]
    )
    assert not (tmp_path / "session_info.json").exists()
