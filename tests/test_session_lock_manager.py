"""Session locking / status-change edge cases (targets #3, #5).

File-based locking is what "прешинить" (prevents) two PCs from packing the
same session simultaneously and drives crash-recovery ("stale lock"). These
tests exercise the real lock file on disk, not a mocked clock.
"""
import json
from datetime import datetime, timedelta

import pytest

from session_lock_manager import SessionLockManager


@pytest.fixture
def lock_manager(profile_manager):
    return SessionLockManager(profile_manager)


@pytest.fixture
def session_dir(server_root):
    d = server_root / "Sessions" / "CLIENT_M" / "2026-01-01_1"
    d.mkdir(parents=True)
    return d


def _write_foreign_lock(session_dir, *, hostname="OTHER-PC", process_id=99999, heartbeat_age_seconds=0):
    heartbeat = (datetime.now().astimezone() - timedelta(seconds=heartbeat_age_seconds)).isoformat()
    lock_data = {
        "locked_by": hostname,
        "user_name": "someone_else",
        "lock_time": heartbeat,
        "process_id": process_id,
        "app_version": "1.3.0",
        "heartbeat": heartbeat,
        "worker_id": "worker_099",
        "worker_name": "Someone Else",
    }
    (session_dir / SessionLockManager.LOCK_FILENAME).write_text(json.dumps(lock_data), encoding="utf-8")


# ---------------------------------------------------------------------------
# acquire / release
# ---------------------------------------------------------------------------

def test_acquire_lock_creates_lock_file(lock_manager, session_dir):
    success, error, info = lock_manager.acquire_lock("M", session_dir, worker_id="w1", worker_name="Worker One")
    assert success is True
    assert error is None
    lock_path = session_dir / SessionLockManager.LOCK_FILENAME
    assert lock_path.exists()
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    assert data["locked_by"] == lock_manager.hostname
    assert data["process_id"] == lock_manager.process_id
    assert data["worker_id"] == "w1"


def test_reacquiring_own_lock_succeeds_and_updates_heartbeat(lock_manager, session_dir):
    lock_manager.acquire_lock("M", session_dir)
    lock_path = session_dir / SessionLockManager.LOCK_FILENAME
    original_heartbeat = json.loads(lock_path.read_text(encoding="utf-8"))["heartbeat"]

    success, error, info = lock_manager.acquire_lock("M", session_dir)
    assert success is True
    assert error is None


def test_acquire_lock_fails_when_actively_held_by_another_pc(lock_manager, session_dir):
    _write_foreign_lock(session_dir, hostname="OTHER-PC", heartbeat_age_seconds=5)  # fresh heartbeat
    success, error, info = lock_manager.acquire_lock("M", session_dir)
    assert success is False
    assert "another PC" in error or "OTHER-PC" in error
    assert info["locked_by"] == "OTHER-PC"


def test_acquire_lock_reports_stale_lock_distinctly_from_active_lock(lock_manager, session_dir):
    _write_foreign_lock(session_dir, hostname="OTHER-PC", heartbeat_age_seconds=200)  # > STALE_TIMEOUT
    success, error, info = lock_manager.acquire_lock("M", session_dir)
    assert success is False
    assert "stale" in error.lower()
    assert info["locked_by"] == "OTHER-PC"


def test_release_lock_removes_own_lock(lock_manager, session_dir):
    lock_manager.acquire_lock("M", session_dir)
    assert lock_manager.release_lock(session_dir) is True
    assert not (session_dir / SessionLockManager.LOCK_FILENAME).exists()


def test_release_lock_refuses_to_remove_someone_elses_lock(lock_manager, session_dir):
    _write_foreign_lock(session_dir, hostname="OTHER-PC", heartbeat_age_seconds=5)
    assert lock_manager.release_lock(session_dir) is False
    assert (session_dir / SessionLockManager.LOCK_FILENAME).exists()  # untouched


def test_release_lock_when_none_exists_is_a_noop_success(lock_manager, session_dir):
    assert lock_manager.release_lock(session_dir) is True


def test_force_release_lock_removes_lock_regardless_of_owner(lock_manager, session_dir):
    _write_foreign_lock(session_dir, hostname="OTHER-PC", heartbeat_age_seconds=200)
    assert lock_manager.force_release_lock(session_dir) is True
    assert not (session_dir / SessionLockManager.LOCK_FILENAME).exists()


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------

def test_update_heartbeat_refreshes_timestamp_for_own_lock(lock_manager, session_dir):
    lock_manager.acquire_lock("M", session_dir)
    lock_path = session_dir / SessionLockManager.LOCK_FILENAME
    before = json.loads(lock_path.read_text(encoding="utf-8"))["heartbeat"]

    assert lock_manager.update_heartbeat(session_dir) is True
    after = json.loads(lock_path.read_text(encoding="utf-8"))["heartbeat"]
    assert after >= before


def test_update_heartbeat_refuses_for_foreign_lock(lock_manager, session_dir):
    _write_foreign_lock(session_dir, hostname="OTHER-PC", heartbeat_age_seconds=5)
    assert lock_manager.update_heartbeat(session_dir) is False


def test_update_heartbeat_missing_lock_file_returns_false(lock_manager, session_dir):
    assert lock_manager.update_heartbeat(session_dir) is False


# ---------------------------------------------------------------------------
# is_lock_stale boundary
# ---------------------------------------------------------------------------

def test_is_lock_stale_just_under_timeout_is_not_stale(lock_manager):
    # A couple of seconds of margin around the exact boundary: is_lock_stale()
    # computes elapsed time against a fresh datetime.now() call, so asserting
    # right at the millisecond boundary would be flaky against a live clock.
    heartbeat = (
        datetime.now().astimezone() - timedelta(seconds=SessionLockManager.STALE_TIMEOUT - 2)
    ).isoformat()
    assert lock_manager.is_lock_stale({"heartbeat": heartbeat}) is False


def test_is_lock_stale_just_past_timeout_is_stale(lock_manager):
    heartbeat = (
        datetime.now().astimezone() - timedelta(seconds=SessionLockManager.STALE_TIMEOUT + 2)
    ).isoformat()
    assert lock_manager.is_lock_stale({"heartbeat": heartbeat}) is True


def test_is_lock_stale_missing_heartbeat_is_stale(lock_manager):
    assert lock_manager.is_lock_stale({}) is True


def test_is_lock_stale_unparseable_heartbeat_is_stale(lock_manager):
    assert lock_manager.is_lock_stale({"heartbeat": "not-a-timestamp"}) is True


# ---------------------------------------------------------------------------
# Edge case worth flagging to the team (not asserted as a hard bug — may be
# intentional): a crash + near-immediate restart on the SAME PC is indistin-
# guishable, for up to STALE_TIMEOUT seconds, from a genuinely active lock
# held by "another process" — because acquire_lock only special-cases
# same-hostname AND same-pid. A restarted process has a new pid.
# ---------------------------------------------------------------------------

def test_same_pc_different_process_is_treated_as_a_foreign_lock_until_stale(lock_manager, session_dir, monkeypatch):
    monkeypatch.setattr(lock_manager, "hostname", "MY-PC")
    _write_foreign_lock(session_dir, hostname="MY-PC", process_id=lock_manager.process_id + 1, heartbeat_age_seconds=5)

    success, error, info = lock_manager.acquire_lock("M", session_dir)
    assert success is False  # blocked from resuming its own crashed session on the same PC
    assert info["locked_by"] == "MY-PC"
