"""File save/write correctness (target #7) across the codebase (target #6).

shared/atomic_write.py::atomic_write_json is the "reference" implementation:
temp file in the same directory + atomic rename, with retries for transient
SMB errors. session_manager.py, session_lock_manager.py,
session_registry_manager.py and shared/worker_manager.py all use it directly.
This file verifies that reference implementation, then verifies the save
paths that used to diverge from it despite writing to the same kind of
network share: PackerLogic._do_atomic_write (packing_state.json — the
highest-frequency write in the app) and PackerLogic.save_session_summary
(session_summary.json) now both delegate to it; StatsManager._atomic_update
(global_stats.json, shared between Packing Tool and Shopify Tool) can't
delegate to it directly (it needs the advisory lock held across the whole
read-modify-write, not just the final write), so it gets the same
temp-file-first crash-safety applied to its own locked-write step instead.
"""
import json
from pathlib import Path

import pytest

from shared.atomic_write import atomic_write_json
from shared.stats_manager import StatsManager, StatsManagerError

# ---------------------------------------------------------------------------
# shared.atomic_write.atomic_write_json — the reference implementation
# ---------------------------------------------------------------------------

def test_atomic_write_json_creates_valid_file_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "sub" / "data.json"
    atomic_write_json(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert not list(target.parent.glob(".*_tmp_*"))


def test_atomic_write_json_retries_transient_failures_then_succeeds(tmp_path, monkeypatch):
    target = tmp_path / "data.json"
    calls = {"n": 0}
    real_replace = Path.replace

    def flaky_replace(self, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("simulated transient SMB error")
        return real_replace(self, dst)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr("shared.atomic_write.time.sleep", lambda s: None)

    atomic_write_json(target, {"ok": True}, retries=5, retry_delay=0)

    assert calls["n"] == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}


def test_atomic_write_json_raises_after_exhausting_retries_but_keeps_original_intact(tmp_path, monkeypatch):
    target = tmp_path / "data.json"
    target.write_text('{"original": true}', encoding="utf-8")

    def always_fail(self, dst):
        raise OSError("server unreachable")

    monkeypatch.setattr(Path, "replace", always_fail)
    monkeypatch.setattr("shared.atomic_write.time.sleep", lambda s: None)

    with pytest.raises(OSError):
        atomic_write_json(target, {"new": True}, retries=3, retry_delay=0)

    # The whole point of temp-file-then-rename: a failed write never
    # touches the original destination content.
    assert json.loads(target.read_text(encoding="utf-8")) == {"original": True}
    assert not list(target.parent.glob(".*_tmp_*"))


# ---------------------------------------------------------------------------
# Regression test: PackerLogic._do_atomic_write used to hand-roll its own
# temp-file + shutil.move with no retry, unlike atomic_write_json — despite
# writing the highest-frequency file in the whole app (packing_state.json,
# saved on every scan). It now delegates to atomic_write_json directly, so
# it gets the same retry-on-transient-SMB-error behavior as every other
# write path.
# ---------------------------------------------------------------------------

def test_packer_logic_state_write_retries_transient_failures_like_every_other_write_path(loaded_logic, monkeypatch):
    calls = {"n": 0}
    real_replace = Path.replace

    def flaky_replace(self, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("simulated transient SMB error")
        return real_replace(self, dst)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr("shared.atomic_write.time.sleep", lambda s: None)

    state = loaded_logic._build_state_dict()
    loaded_logic._do_atomic_write(state)

    assert calls["n"] == 3  # failed twice, succeeded on the 3rd attempt


# ---------------------------------------------------------------------------
# Regression test: PackerLogic.save_session_summary used to write with a
# plain open('w') + json.dump, no temp file — a failure partway through
# truncated the destination in place. It now goes through atomic_write_json
# like every other write path, so the previously-good summary must survive
# a failed save untouched.
# ---------------------------------------------------------------------------

def test_save_session_summary_does_not_corrupt_file_on_write_failure(loaded_logic, monkeypatch):
    summary_path = loaded_logic.work_dir / "session_summary.json"
    summary_path.write_text('{"previous": "good summary"}', encoding="utf-8")

    def failing_dump(data, fp, **kwargs):
        fp.write('{"truncated')  # simulate a write that dies partway through
        raise OSError("disk full")

    monkeypatch.setattr("shared.atomic_write.json.dump", failing_dump)
    monkeypatch.setattr("shared.atomic_write.time.sleep", lambda s: None)

    with pytest.raises(IOError):
        loaded_logic.save_session_summary()

    # The failing write only ever touches a temp file — the previously-good
    # destination is untouched, and the temp file is cleaned up.
    content = summary_path.read_text(encoding="utf-8")
    assert content == '{"previous": "good summary"}'
    assert not list(summary_path.parent.glob(".*_tmp_*"))


# ---------------------------------------------------------------------------
# Regression test: StatsManager._atomic_update's name promised atomicity, but
# it only provided *concurrency* safety (advisory file lock held across
# read-modify-write); it used to truncate the file in place before writing,
# so it was not crash-safe. global_stats.json is shared by BOTH Shopify Tool
# and Packing Tool — a single corrupted write would lose history recorded by
# every PC. It now serializes to a throwaway temp file first and only
# truncates the locked original once the new content is known-good, while
# still holding the same advisory lock the whole time (required since
# renaming a new file over the locked path would break that lock's
# cross-process guarantee).
# ---------------------------------------------------------------------------

def test_stats_manager_atomic_update_is_actually_crash_safe(tmp_path, monkeypatch):
    manager = StatsManager(str(tmp_path), max_retries=2, retry_delay=0)
    manager.record_packing(client_id="M", session_id="s1", worker_id="w1", orders_count=5, items_count=10)
    assert json.loads(manager.stats_file.read_text(encoding="utf-8"))["total_orders_packed"] == 5

    def failing_dump(data, fp, **kwargs):
        fp.write('{"start of a new record but')  # simulate a write that dies partway through
        raise OSError("network share dropped")

    monkeypatch.setattr("shared.stats_manager.json.dump", failing_dump)

    with pytest.raises(StatsManagerError):
        manager.record_packing(client_id="M", session_id="s2", worker_id="w1", orders_count=1, items_count=1)

    # The failing write only ever touched a temp file — the previously-good
    # record must survive intact, and no temp file is left behind.
    preserved = json.loads(manager.stats_file.read_text(encoding="utf-8"))
    assert preserved["total_orders_packed"] == 5
    assert not list(manager.stats_file.parent.glob(".*_tmp_*"))
