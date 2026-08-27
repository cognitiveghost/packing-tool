"""JSONCache correctness (target #7) and the shared-mutable-object hazard
underlying the packer_logic persistence bugs in
test_packer_logic_state_persistence.py (target #2/#6).

Tests build their own JSONCache instances (not the module-level singleton
`_json_cache`) so they don't interfere with each other or with whatever the
app's global cache is doing elsewhere in the same process.
"""
import json

import pytest

from packing_tool import json_cache as json_cache_module
from packing_tool.json_cache import JSONCache


@pytest.fixture
def fake_clock(monkeypatch):
    state = {"now": 1_000_000.0}
    monkeypatch.setattr(json_cache_module.time, "time", lambda: state["now"])
    return state


def test_cache_hit_avoids_reading_the_file_again(tmp_path, fake_clock):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"v": 1}), encoding="utf-8")
    cache = JSONCache(ttl_seconds=60)

    first = cache.get(path)
    path.unlink()  # if the second get() re-reads from disk, this will surface as a miss
    second = cache.get(path)

    assert first == {"v": 1}
    assert second == {"v": 1}


def test_cache_expires_after_ttl(tmp_path, fake_clock):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"v": 1}), encoding="utf-8")
    cache = JSONCache(ttl_seconds=60)

    cache.get(path)
    path.write_text(json.dumps({"v": 2}), encoding="utf-8")

    fake_clock["now"] += 61  # advance past the TTL
    assert cache.get(path) == {"v": 2}


def test_cache_does_not_expire_before_ttl(tmp_path, fake_clock):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"v": 1}), encoding="utf-8")
    cache = JSONCache(ttl_seconds=60)

    cache.get(path)
    path.write_text(json.dumps({"v": 2}), encoding="utf-8")

    fake_clock["now"] += 59
    assert cache.get(path) == {"v": 1}  # still the stale cached value


def test_missing_file_returns_default(tmp_path):
    cache = JSONCache()
    assert cache.get(tmp_path / "nope.json", default="fallback") == "fallback"


def test_invalid_json_returns_default(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid", encoding="utf-8")
    cache = JSONCache()
    assert cache.get(path, default={}) == {}


def test_invalidate_forces_a_fresh_read(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"v": 1}), encoding="utf-8")
    cache = JSONCache(ttl_seconds=60)

    cache.get(path)
    path.write_text(json.dumps({"v": 2}), encoding="utf-8")
    cache.invalidate(path)

    assert cache.get(path) == {"v": 2}


def test_eviction_keeps_cache_at_or_under_max_size(tmp_path):
    cache = JSONCache(max_size=10, ttl_seconds=60)
    paths = []
    for i in range(11):
        p = tmp_path / f"file{i}.json"
        p.write_text(json.dumps({"i": i}), encoding="utf-8")
        paths.append(p)
        cache.get(p)  # each insert is a distinct cache_key -> triggers eviction once over max_size

    assert len(cache._cache) <= 10


# ---------------------------------------------------------------------------
# Regression test: get() used to hand back the live object stored in the
# cache, not a copy. Any caller that mutated what it got back corrupted the
# cache for every other reader of that same path — without ever writing to
# disk. This was the root cause behind PackerLogic silently poisoning
# cross-consumer reads of packing_state.json (see
# test_packer_logic_state_persistence.py).
# ---------------------------------------------------------------------------

def test_get_does_not_return_a_reference_callers_can_use_to_poison_the_cache(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"in_progress": {"ORDER-1": []}}), encoding="utf-8")
    cache = JSONCache(ttl_seconds=60)

    first_reader = cache.get(path)
    first_reader["in_progress"]["ORDER-1"].append({"tampered": True})  # a very ordinary-looking mutation

    second_reader = cache.get(path)  # cache hit, same TTL window
    assert second_reader["in_progress"]["ORDER-1"] == [], (
        "mutating one caller's result leaked into every other reader of the same "
        f"cached path: {second_reader}"
    )
