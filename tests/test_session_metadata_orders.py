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


def test_write_happens_inside_the_sidecar_lock(tmp_path, monkeypatch):
    """The Shopify tool guards this same file with an exclusive lock on the
    sidecar .lock. Without taking it here, its read-modify-write and ours
    interleave and one side's order numbers are silently lost. This pins both
    that the lock is taken and that the write happens inside it."""
    import contextlib

    import session_manager as sm

    events = []
    real_locked_file = sm.locked_file
    real_atomic_write = sm.atomic_write_json

    @contextlib.contextmanager
    def spy_locked_file(handle, *args, **kwargs):
        events.append(("lock_acquired", handle.name))
        with real_locked_file(handle, *args, **kwargs):
            yield
        events.append(("lock_released", handle.name))

    def spy_atomic_write(path, *args, **kwargs):
        events.append(("write", str(path)))
        return real_atomic_write(path, *args, **kwargs)

    monkeypatch.setattr(sm, "locked_file", spy_locked_file)
    monkeypatch.setattr(sm, "atomic_write_json", spy_atomic_write)

    _seed_session_info(tmp_path)
    _mgr().update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#1"]
    )

    names = [e[0] for e in events]
    assert names == ["lock_acquired", "write", "lock_released"], events
    assert events[0][1].endswith("session_info.json.lock")


def test_lock_guards_the_read_too_not_just_the_write(tmp_path, monkeypatch):
    """A lock taken only around the write still loses updates: two callers
    read the same snapshot first. Pin that the read is inside the lock."""
    import contextlib

    import session_manager as sm

    events = []
    real_locked_file = sm.locked_file
    real_open = open

    @contextlib.contextmanager
    def spy_locked_file(handle, *args, **kwargs):
        events.append("lock_acquired")
        with real_locked_file(handle, *args, **kwargs):
            yield
        events.append("lock_released")

    def spy_open(path, *args, **kwargs):
        if str(path).endswith("session_info.json"):
            events.append("read")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(sm, "locked_file", spy_locked_file)
    monkeypatch.setattr("builtins.open", spy_open)

    _seed_session_info(tmp_path)
    _mgr().update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#1"]
    )

    assert events.index("lock_acquired") < events.index("read")
    assert events.index("read") < events.index("lock_released")
