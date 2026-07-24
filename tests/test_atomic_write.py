"""File save/write correctness (target #7) and the inconsistencies between
save paths across the codebase (target #6).

shared/atomic_write.py::atomic_write_json is the "reference" implementation:
temp file in the same directory + atomic rename, with retries for transient
SMB errors. session_manager.py, session_lock_manager.py,
session_registry_manager.py and shared/worker_manager.py all use it. This
file verifies that reference implementation, then contrasts it against the
save paths that DON'T use it even though they write to the same kind of
network share: PackerLogic._do_atomic_write (packing_state.json — the
highest-frequency write in the app), PackerLogic.save_session_summary
(session_summary.json), and StatsManager._atomic_update (global_stats.json,
shared between Packing Tool and Shopify Tool).
"""
import json
from pathlib import Path

import pytest

import packer_logic
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
# PackerLogic._do_atomic_write — atomic (temp file + shutil.move), but with
# no retry, unlike atomic_write_json — despite writing the highest-frequency
# file in the whole app (packing_state.json, saved on every scan).
# ---------------------------------------------------------------------------

def test_packer_logic_state_write_has_no_retry_on_transient_failure(loaded_logic, monkeypatch):
    calls = {"n": 0}

    def always_fail(src, dst):
        calls["n"] += 1
        raise OSError("simulated transient SMB error")

    monkeypatch.setattr(packer_logic.shutil, "move", always_fail)

    state = loaded_logic._build_state_dict()
    loaded_logic._do_atomic_write(state)  # caught internally, never raises...

    assert calls["n"] == 1  # ...but also never retried, unlike atomic_write_json's default retries=3
    # The scan that produced this state is now unrecorded on disk with no
    # retry and no surfaced error — only a log line. If the very next write
    # attempt for a *different* state also transiently fails, this scan's
    # data is gone for good (AsyncStateWriter only keeps the latest pending
    # write, it does not queue every write).


# ---------------------------------------------------------------------------
# PackerLogic.save_session_summary — not atomic at all: plain open('w') +
# json.dump, no temp file. A failure partway through truncates the
# destination in place.
# ---------------------------------------------------------------------------

def test_save_session_summary_corrupts_file_in_place_on_write_failure(loaded_logic, monkeypatch):
    summary_path = loaded_logic.work_dir / "session_summary.json"
    summary_path.write_text('{"previous": "good summary"}', encoding="utf-8")

    def failing_dump(data, fp, **kwargs):
        fp.write('{"truncated')  # simulate a write that dies partway through
        raise OSError("disk full")

    monkeypatch.setattr(packer_logic.json, "dump", failing_dump)

    with pytest.raises(IOError):
        loaded_logic.save_session_summary()

    # Unlike atomic_write_json, this leaves a half-written, invalid JSON file
    # in place of the previously-good summary — there is no temp file to fall
    # back to.
    content = summary_path.read_text(encoding="utf-8")
    assert content != '{"previous": "good summary"}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(content)


# ---------------------------------------------------------------------------
# StatsManager._atomic_update — the name promises atomicity, but it only
# provides *concurrency* safety (advisory file lock held across read-modify-
# write); it truncates the file in place before writing, so it is not
# crash-safe. global_stats.json is shared by BOTH Shopify Tool and Packing
# Tool — a single corrupted write loses history recorded by every PC.
# ---------------------------------------------------------------------------

def test_stats_manager_atomic_update_is_not_actually_crash_safe(tmp_path, monkeypatch):
    manager = StatsManager(str(tmp_path), max_retries=2, retry_delay=0)
    manager.record_packing(client_id="M", session_id="s1", worker_id="w1", orders_count=5, items_count=10)
    assert json.loads(manager.stats_file.read_text(encoding="utf-8"))["total_orders_packed"] == 5

    def failing_dump(data, fp, **kwargs):
        fp.write('{"start of a new record but')  # simulate a write that dies partway through
        raise OSError("network share dropped")

    monkeypatch.setattr("shared.stats_manager.json.dump", failing_dump)

    with pytest.raises(StatsManagerError):
        manager.record_packing(client_id="M", session_id="s2", worker_id="w1", orders_count=1, items_count=1)

    # The file was truncated (f.seek(0); f.truncate()) before the failing
    # write, wiping the previously-good record with no way back.
    corrupted = manager.stats_file.read_text(encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(corrupted)
