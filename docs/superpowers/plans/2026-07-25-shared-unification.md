# Shared/ Unification (Packing Tool ↔ Shopify Fulfillment Tool) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the two divergent `shared/` packages (packing-tool and shopify-fulfillment-tool) into one canonical version living in `packing-tool/shared/`, fix the four behavioral conflicts the ponytail-audit found (stats-file `version` field, tz-naive vs tz-aware timestamps, `session_id` mismatch, `base_path` config-source mismatch), and set up a one-way manual sync so shopify-fulfillment-tool's copy stops drifting.

**Architecture:** `packing-tool/shared/` becomes the single source of truth. Its `stats_manager.py` is rewritten to carry the full method set (merged from both forks) built on the infrastructure that already lives in packing-tool (`file_lock.py`, `atomic_write.py`, `metadata_utils.py`). A new `shopify-fulfillment-tool/scripts/sync_shared.py` copies that directory into shopify-fulfillment-tool on demand — no git submodule, no new repo.

**Tech Stack:** Python 3.11+, pytest (packing-tool only — shopify-fulfillment-tool has no test suite yet, verified via `ruff check .` + a headless smoke test per its existing CI).

**Related spec:** `docs/superpowers/specs/2026-07-25-shared-unification-design.md` (includes two corrections found while writing this plan — see Global Constraints below).

## Global Constraints

- Canonical `shared/` package lives in `packing-tool/shared/`; shopify-fulfillment-tool's copy is produced only by running the sync script, never hand-edited.
- `Stats/global_stats.json` format version bumps to `"2.0"` (was `"1.3.0"` in packing-tool, `"1.0"` in shopify-fulfillment-tool).
- No migration of existing production `Stats/global_stats.json` — the owner replaces it with a fresh file before rollout. Code only needs to handle the forward format.
- `StatsManager._atomic_update`'s temp-file-then-write-into-the-still-locked-handle pattern is carried over **unchanged** — it is not the same thing as `atomic_write.atomic_write_json`'s temp+`os.replace()`, and must not be "simplified" to that: replacing the file while holding an advisory lock on it would detach the lock from the new file. Already covered by `tests/test_atomic_write.py::test_stats_manager_atomic_update_is_actually_crash_safe`, which must keep passing.
- `shared/metadata_utils.py` must not import packing-tool's private `src/logger.py` module (`from logger import get_logger`) — shopify-fulfillment-tool has no such module and would raise `ModuleNotFoundError` the first time it called `get_current_timestamp()`. Use stdlib `logging.getLogger(__name__)` instead (behaviorally identical — `get_logger()` already just returns a plain `logging.Logger`).
- `session_id` passed to `record_analysis`/`record_packing` must be derived identically by both apps: `shared.session_id.derive_session_id(path)` (`Path(path).name`), not ad hoc per-app logic.
- `base_path` resolution in packing-tool must check the `FULFILLMENT_SERVER_PATH` env var first (same variable, same precedence shopify-fulfillment-tool already uses), falling back to `config.ini`'s `[Network] FileServerPath` — existing deployments that only set `config.ini` keep working unchanged.
- Tests use real collaborators (real file I/O under `tmp_path`, no mocks) per the existing suite's own stated philosophy in `tests/conftest.py`.
- shopify-fulfillment-tool has no `tests/` directory (per its `CLAUDE.md`: "Tests are being rewritten"). Verification there is `ruff check .` plus its existing CI smoke test: `CI=1 python run_dev.py`.

---

### Task 1: Remove `shared/metadata_utils.py`'s dependency on packing-tool's private `logger` module

**Files:**
- Modify: `packing-tool/shared/metadata_utils.py:1-16`
- Test: `packing-tool/tests/test_metadata_utils.py` (existing — no new test needed, this is a behavior-preserving import swap; the existing suite is the regression check)

**Interfaces:**
- Produces: `shared.metadata_utils.get_current_timestamp()`, `parse_timestamp()`, `calculate_duration()`, `load_session_summary()` — signatures unchanged, used by Task 2 and Task 4.

- [ ] **Step 1: Confirm the existing tests currently pass (baseline)**

Run: `cd packing-tool && python -m pytest tests/test_metadata_utils.py -v`
Expected: PASS (7 tests, establishes the pre-change baseline)

- [ ] **Step 2: Swap the logger import**

In `packing-tool/shared/metadata_utils.py`, change:

```python
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from logger import get_logger

logger = get_logger(__name__)
```

to:

```python
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
```

- [ ] **Step 3: Run the existing tests again to confirm no regression**

Run: `cd packing-tool && python -m pytest tests/test_metadata_utils.py -v`
Expected: PASS (same 7 tests, unchanged)

- [ ] **Step 4: Commit**

```bash
cd packing-tool
git add shared/metadata_utils.py
git commit -m "Drop metadata_utils.py's dependency on the private logger module

shopify-fulfillment-tool has no top-level logger.py (it has
shopify_tool/logger_config.py instead), so copying metadata_utils.py as-is
via the upcoming sync script would raise ModuleNotFoundError the first
time it called get_current_timestamp(). get_logger() already just returns
a plain logging.Logger, so this is behaviorally identical."
```

---

### Task 2: Merge `stats_manager.py` into the canonical superset

**Files:**
- Modify: `packing-tool/shared/stats_manager.py` (full rewrite)
- Modify: `packing-tool/tests/test_atomic_write.py:23` (import path check only — no content change expected, see Step 5)
- Create: `packing-tool/tests/test_stats_manager.py`

**Interfaces:**
- Consumes: `shared.file_lock.locked_file`, `shared.file_lock.FileLockError` (Task-independent, unchanged); `shared.metadata_utils.get_current_timestamp() -> str`, `shared.metadata_utils.parse_timestamp(str) -> Optional[datetime]` (from Task 1, signatures unchanged).
- Produces: `StatsManager` with `record_analysis`, `record_packing`, `record_label_print`, `get_global_stats`, `get_client_stats`, `get_all_clients_stats`, `get_analysis_history`, `get_packing_history`, `get_label_print_history`, `get_label_stats`, `reset_stats`. `StatsManagerError`. `FileLockError` (re-exported from `shared.file_lock`, not redefined). Used by Task 6 (packing-tool call sites, unchanged usage) and by shopify-fulfillment-tool after Task 7's sync.

- [ ] **Step 1: Write the failing tests**

Create `packing-tool/tests/test_stats_manager.py`:

```python
"""Merged StatsManager (shared/ unification) — record_analysis,
record_packing, record_label_print and the reporting/history methods all
live in one canonical file now. Previously packing-tool's copy only had
record_packing; shopify-fulfillment-tool's copy had the full set but
duplicated file-locking and timestamp logic inline instead of reusing
shared.file_lock / shared.metadata_utils. This file exercises the merged
surface end to end.
"""
from datetime import datetime, timedelta

from shared.stats_manager import StatsManager, FileLockError as StatsFileLockError
from shared.file_lock import FileLockError as SharedFileLockError


def test_default_stats_version_is_the_unified_value(tmp_path):
    manager = StatsManager(str(tmp_path))
    assert manager._get_default_stats()["version"] == "2.0"


def test_file_lock_error_is_the_one_shared_class():
    """Regression: shopify-fulfillment-tool's stats_manager.py used to
    define its own FileLockError(StatsManagerError) — a different class
    from packing-tool's shared.file_lock.FileLockError(Exception), despite
    both being exported from shared/__init__.py under the same name.
    """
    assert StatsFileLockError is SharedFileLockError


def test_record_analysis_updates_global_and_client_counters(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_analysis(
        client_id="M",
        session_id="2026-01-01_1",
        orders_count=150,
        metadata={"fulfillable_orders": 142},
    )

    global_stats = manager.get_global_stats()
    assert global_stats["total_orders_analyzed"] == 150

    client_stats = manager.get_client_stats("M")
    assert client_stats["orders_analyzed"] == 150
    assert client_stats["sessions"] == 0  # only record_packing increments sessions


def test_record_packing_updates_global_and_client_counters(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_packing(
        client_id="M",
        session_id="2026-01-01_1",
        worker_id="worker_001",
        orders_count=142,
        items_count=450,
    )

    global_stats = manager.get_global_stats()
    assert global_stats["total_orders_packed"] == 142
    assert global_stats["total_sessions"] == 1

    client_stats = manager.get_client_stats("M")
    assert client_stats["orders_packed"] == 142
    assert client_stats["sessions"] == 1


def test_record_analysis_and_record_packing_share_one_client_entry(tmp_path):
    """Both apps write the same by_client[client_id] entry in the same
    file — this is the whole point of the unified StatsManager."""
    manager = StatsManager(str(tmp_path))
    manager.record_analysis(client_id="M", session_id="s1", orders_count=150)
    manager.record_packing(
        client_id="M", session_id="s1", worker_id="w1",
        orders_count=142, items_count=450,
    )

    client_stats = manager.get_client_stats("M")
    assert client_stats["orders_analyzed"] == 150
    assert client_stats["orders_packed"] == 142
    assert client_stats["sessions"] == 1


def test_get_all_clients_stats_returns_every_client(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_analysis(client_id="M", session_id="s1", orders_count=10)
    manager.record_analysis(client_id="A", session_id="s2", orders_count=20)

    all_stats = manager.get_all_clients_stats()
    assert set(all_stats.keys()) == {"M", "A"}


def test_get_analysis_history_filters_by_client_and_limit(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_analysis(client_id="M", session_id="s1", orders_count=10)
    manager.record_analysis(client_id="A", session_id="s2", orders_count=20)
    manager.record_analysis(client_id="M", session_id="s3", orders_count=30)

    history = manager.get_analysis_history(client_id="M")
    assert len(history) == 2
    assert all(h["client_id"] == "M" for h in history)

    limited = manager.get_analysis_history(limit=1)
    assert len(limited) == 1


def test_get_packing_history_filters_by_worker(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_packing(client_id="M", session_id="s1", worker_id="w1", orders_count=1, items_count=1)
    manager.record_packing(client_id="M", session_id="s2", worker_id="w2", orders_count=1, items_count=1)

    history = manager.get_packing_history(worker_id="w1")
    assert len(history) == 1
    assert history[0]["worker_id"] == "w1"


def test_record_label_print_updates_counters_and_history(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_label_print(client_id="M", sku="SKU-1", copies=3)
    manager.record_label_print(client_id="M", sku="SKU-2", copies=2)

    stats = manager.get_label_stats(client_id="M")
    assert stats["total_labels_printed"] == 5
    assert stats["unique_skus"] == 2
    assert stats["top_sku"] == "SKU-1"


def test_get_label_print_history_accepts_naive_dates_from_the_gui(tmp_path):
    """Regression: the GUI (client_reports_widget.py) builds start_date/
    end_date from a QDate — a naive datetime, no timezone — while records
    are stored with timezone-aware timestamps (get_current_timestamp()).
    Comparing a naive and an aware datetime raises TypeError; this must
    not happen once every write path in the merged StatsManager produces
    timezone-aware timestamps.
    """
    manager = StatsManager(str(tmp_path))
    manager.record_label_print(client_id="M", sku="SKU-1", copies=1)

    naive_start = datetime.now() - timedelta(days=1)
    naive_end = datetime.now() + timedelta(days=1)

    history = manager.get_label_print_history(start_date=naive_start, end_date=naive_end)
    assert len(history) == 1


def test_get_label_print_history_filters_out_of_range_dates(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_label_print(client_id="M", sku="SKU-1", copies=1)

    far_future_start = datetime.now() + timedelta(days=30)
    history = manager.get_label_print_history(start_date=far_future_start)
    assert history == []


def test_reset_stats_clears_history_and_counters(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_packing(client_id="M", session_id="s1", worker_id="w1", orders_count=1, items_count=1)

    manager.reset_stats()

    assert manager.get_global_stats()["total_orders_packed"] == 0
    assert manager.get_packing_history() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd packing-tool && python -m pytest tests/test_stats_manager.py -v`
Expected: FAIL — most tests raise `AttributeError: 'StatsManager' object has no attribute 'record_analysis'` (and similarly for `get_global_stats`, `get_client_stats`, `get_all_clients_stats`, `get_analysis_history`, `get_packing_history`, `record_label_print`, `get_label_print_history`, `get_label_stats`, `reset_stats`), since the current `packing-tool/shared/stats_manager.py` only has `record_packing`.

- [ ] **Step 3: Rewrite `shared/stats_manager.py`**

Replace the entire contents of `packing-tool/shared/stats_manager.py` with:

```python
"""
Unified Statistics Manager for Shopify Tool and Packing Tool

Canonical version. This module lives in packing-tool/shared/ and is copied
into shopify-fulfillment-tool/shared/ by
shopify-fulfillment-tool/scripts/sync_shared.py — the two copies must stay
byte-identical. See shared/README.md.

Manages centralized statistics stored on the file server in
Stats/global_stats.json:
- Centralized storage on file server
- File locking for concurrent access from multiple PCs
- Separate tracking for analysis (Shopify Tool) and packing operations (Packing Tool)
- Per-client statistics breakdown
- Thread-safe and process-safe operations

Usage:
    # In Shopify Tool
    stats_manager = StatsManager(base_path)
    stats_manager.record_analysis(
        client_id="M",
        session_id="2025-11-05_1",
        orders_count=150,
        metadata={...}
    )

    # In Packing Tool
    stats_manager = StatsManager(base_path)
    stats_manager.record_packing(
        client_id="M",
        session_id="2025-11-05_1",
        worker_id="001",
        orders_count=142,
        items_count=450,
        metadata={...}
    )
"""

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from shared.file_lock import locked_file, FileLockError
from shared.metadata_utils import get_current_timestamp, parse_timestamp


class StatsManagerError(Exception):
    """Base exception for StatsManager errors."""
    pass


class StatsManager:
    """
    Unified statistics manager for both Shopify Tool and Packing Tool.

    Manages centralized statistics stored in Stats/global_stats.json on the
    file server. Provides thread-safe and process-safe operations using
    file locking.

    Structure of global_stats.json:
    {
        "total_orders_analyzed": 5420,      # From Shopify Tool
        "total_orders_packed": 4890,        # From Packing Tool
        "total_sessions": 312,
        "total_labels_printed": 88,
        "by_client": {
            "M": {
                "orders_analyzed": 2100,
                "orders_packed": 1950,
                "sessions": 145,
                "labels_printed": 12
            }
        },
        "analysis_history": [...],          # Shopify Tool records
        "packing_history": [...],           # Packing Tool records
        "label_print_history": [...],       # Shopify Tool label prints
        "last_updated": "2025-11-05T14:30:00+02:00",
        "version": "2.0"
    }

    Attributes:
        base_path (Path): Base path to 0UFulfilment directory
        stats_file (Path): Path to global_stats.json
        max_retries (int): Maximum number of retry attempts for file operations
        retry_delay (float): Delay in seconds between retries
    """

    def __init__(
        self,
        base_path: str,
        max_retries: int = 5,
        retry_delay: float = 0.1
    ):
        """
        Initialize the StatsManager.

        Args:
            base_path: Path to 0UFulfilment directory (e.g., \\\\server\\...\\0UFulfilment)
            max_retries: Maximum number of retry attempts for locked files
            retry_delay: Delay in seconds between retry attempts
        """
        self.base_path = Path(base_path)
        self.stats_file = self.base_path / "Stats" / "global_stats.json"
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_default_stats(self) -> Dict[str, Any]:
        """Get default statistics structure."""
        return {
            "total_orders_analyzed": 0,
            "total_orders_packed": 0,
            "total_sessions": 0,
            "total_labels_printed": 0,
            "by_client": {},
            "analysis_history": [],
            "packing_history": [],
            "label_print_history": [],
            "last_updated": get_current_timestamp(),
            "version": "2.0",
        }

    def _load_stats(self) -> Dict[str, Any]:
        """Load statistics from file with file locking."""
        if not self.stats_file.exists():
            return self._get_default_stats()

        for attempt in range(self.max_retries):
            try:
                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode, encoding='utf-8') as f:
                    with locked_file(f):
                        f.seek(0)
                        content = f.read()
                        if not content.strip():
                            return self._get_default_stats()

                        stats = json.loads(content)

                        if not isinstance(stats, dict):
                            return self._get_default_stats()

                        default = self._get_default_stats()
                        for key in default:
                            if key not in stats:
                                stats[key] = default[key]

                        return stats

            except json.JSONDecodeError:
                return self._get_default_stats()
            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to load stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

        return self._get_default_stats()

    def _save_stats(self, stats: Dict[str, Any]) -> None:
        """Save statistics to file with file locking."""
        stats["last_updated"] = get_current_timestamp()

        for attempt in range(self.max_retries):
            try:
                self.stats_file.parent.mkdir(parents=True, exist_ok=True)

                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode, encoding='utf-8') as f:
                    with locked_file(f):
                        f.seek(0)
                        f.truncate()
                        json.dump(stats, f, indent=4, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())

                return

            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to save stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

    def _atomic_update(self, update_func) -> None:
        """Perform an atomic update of statistics.

        NOTE: this deliberately does NOT delegate to
        shared.atomic_write.atomic_write_json's temp+os.replace() pattern.
        The advisory lock in locked_file() is held on this specific open
        file handle for the entire read-modify-write; replacing the file
        at this path with a new inode (what os.replace() does) would
        detach the lock from the file everyone else is waiting on. Instead,
        the new content is fully serialized to a throwaway temp file first
        (so a failure there never touches the locked original), and only
        written into the still-open, still-locked handle once it is known
        good. See tests/test_atomic_write.py::
        test_stats_manager_atomic_update_is_actually_crash_safe.
        """
        for attempt in range(self.max_retries):
            try:
                if not self.stats_file.exists():
                    self.stats_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.stats_file, 'w', encoding='utf-8') as f:
                        json.dump(self._get_default_stats(), f, indent=4)

                with open(self.stats_file, 'r+', encoding='utf-8') as f:
                    with locked_file(f):
                        f.seek(0)
                        content = f.read()
                        if content.strip():
                            try:
                                stats = json.loads(content)
                            except json.JSONDecodeError:
                                stats = self._get_default_stats()
                        else:
                            stats = self._get_default_stats()

                        if not isinstance(stats, dict):
                            stats = self._get_default_stats()

                        default = self._get_default_stats()
                        for key in default:
                            if key not in stats:
                                stats[key] = default[key]

                        update_func(stats)

                        stats["last_updated"] = get_current_timestamp()

                        tmp_fd, tmp_name = tempfile.mkstemp(
                            dir=self.stats_file.parent,
                            prefix=f".{self.stats_file.stem}_tmp_",
                            suffix=self.stats_file.suffix,
                        )
                        try:
                            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as tmp_f:
                                json.dump(stats, tmp_f, indent=4, ensure_ascii=False)
                            new_content = Path(tmp_name).read_text(encoding='utf-8')
                        finally:
                            try:
                                os.unlink(tmp_name)
                            except OSError:
                                pass

                        f.seek(0)
                        f.truncate()
                        f.write(new_content)
                        f.flush()
                        os.fsync(f.fileno())

                return  # Success

            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to update stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

    def record_analysis(
        self,
        client_id: str,
        session_id: str,
        orders_count: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record an analysis completion from Shopify Tool.

        Args:
            client_id: Client identifier (e.g., "M", "A", "B")
            session_id: Session identifier — derive with
                shared.session_id.derive_session_id(session_path)
            orders_count: Number of orders analyzed
            metadata: Optional additional metadata (e.g., fulfillable_orders,
                courier_breakdown)
        """
        def update(stats):
            stats["total_orders_analyzed"] += orders_count

            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0,
                }

            stats["by_client"][client_id]["orders_analyzed"] += orders_count

            record = {
                "timestamp": get_current_timestamp(),
                "client_id": client_id,
                "session_id": session_id,
                "orders_count": orders_count,
            }

            if metadata:
                record["metadata"] = metadata

            stats["analysis_history"].append(record)

            if len(stats["analysis_history"]) > 1000:
                stats["analysis_history"] = stats["analysis_history"][-1000:]

        self._atomic_update(update)

    def record_packing(
        self,
        client_id: str,
        session_id: str,
        worker_id: Optional[str],
        orders_count: int,
        items_count: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a packing session completion from Packing Tool.

        Args:
            client_id: Client identifier (e.g., "M", "A", "B")
            session_id: Session identifier — derive with
                shared.session_id.derive_session_id(session_path)
            worker_id: Worker identifier (e.g., "001", "002")
            orders_count: Number of orders packed
            items_count: Number of items packed
            metadata: Optional additional metadata (e.g., duration, start_time, end_time)
        """
        def update(stats):
            stats["total_orders_packed"] += orders_count
            stats["total_sessions"] += 1

            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0,
                }

            stats["by_client"][client_id]["orders_packed"] += orders_count
            stats["by_client"][client_id]["sessions"] += 1

            record = {
                "timestamp": get_current_timestamp(),
                "client_id": client_id,
                "session_id": session_id,
                "worker_id": worker_id,
                "orders_count": orders_count,
                "items_count": items_count,
            }

            if metadata:
                record["metadata"] = metadata

            stats["packing_history"].append(record)

            if len(stats["packing_history"]) > 1000:
                stats["packing_history"] = stats["packing_history"][-1000:]

        self._atomic_update(update)

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global statistics summary."""
        stats = self._load_stats()
        return {
            "total_orders_analyzed": stats.get("total_orders_analyzed", 0),
            "total_orders_packed": stats.get("total_orders_packed", 0),
            "total_sessions": stats.get("total_sessions", 0),
            "last_updated": stats.get("last_updated"),
        }

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get statistics for a specific client."""
        stats = self._load_stats()
        if client_id not in stats.get("by_client", {}):
            return {"orders_analyzed": 0, "orders_packed": 0, "sessions": 0}
        return stats["by_client"][client_id].copy()

    def get_all_clients_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all clients."""
        stats = self._load_stats()
        return stats.get("by_client", {}).copy()

    def get_analysis_history(
        self,
        client_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get analysis history with optional filtering (newest first)."""
        stats = self._load_stats()
        history = stats.get("analysis_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

        history.sort(key=lambda h: h.get("timestamp", ""), reverse=True)

        if limit:
            history = history[:limit]

        return history

    def get_packing_history(
        self,
        client_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get packing history with optional filtering (newest first)."""
        stats = self._load_stats()
        history = stats.get("packing_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

        if worker_id:
            history = [h for h in history if h.get("worker_id") == worker_id]

        history.sort(key=lambda h: h.get("timestamp", ""), reverse=True)

        if limit:
            history = history[:limit]

        return history

    def record_label_print(
        self,
        client_id: str,
        sku: str,
        copies: int,
    ) -> None:
        """Record a label print event from the SKU Label widget."""
        def update(stats):
            stats["total_labels_printed"] += copies

            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0,
                    "labels_printed": 0,
                }
            client = stats["by_client"][client_id]
            if "labels_printed" not in client:
                client["labels_printed"] = 0
            client["labels_printed"] += copies

            record = {
                "timestamp": get_current_timestamp(),
                "client_id": client_id,
                "sku": sku,
                "copies": copies,
            }
            stats["label_print_history"].append(record)

            if len(stats["label_print_history"]) > 1000:
                stats["label_print_history"] = stats["label_print_history"][-1000:]

        self._atomic_update(update)

    def get_label_print_history(
        self,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get label print history with optional filtering.

        start_date/end_date may be naive or timezone-aware (the GUI builds
        them from a QDate, which has no timezone concept). Naive values are
        assumed to be in the local timezone — the same convention
        get_current_timestamp() uses when writing records — so comparing
        them against the stored (timezone-aware) timestamps never raises
        "can't compare offset-naive and offset-aware datetimes".
        """
        stats = self._load_stats()
        history = stats.get("label_print_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

        if start_date:
            if start_date.tzinfo is None:
                start_date = start_date.astimezone()
            filtered = []
            for h in history:
                ts = parse_timestamp(h["timestamp"])
                if ts is not None and ts >= start_date:
                    filtered.append(h)
            history = filtered

        if end_date:
            end_dt = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            if end_dt.tzinfo is None:
                end_dt = end_dt.astimezone()
            filtered = []
            for h in history:
                ts = parse_timestamp(h["timestamp"])
                if ts is not None and ts <= end_dt:
                    filtered.append(h)
            history = filtered

        history.sort(key=lambda h: h.get("timestamp", ""), reverse=True)

        if limit:
            history = history[:limit]

        return history

    def get_label_stats(
        self,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get label printing summary statistics."""
        history = self.get_label_print_history(client_id=client_id)

        sku_counts: Dict[str, int] = {}
        for record in history:
            sku = record.get("sku", "Unknown")
            sku_counts[sku] = sku_counts.get(sku, 0) + record.get("copies", 1)

        total = sum(sku_counts.values())
        top_sku = max(sku_counts, key=sku_counts.get) if sku_counts else None

        return {
            "total_labels_printed": total,
            "unique_skus": len(sku_counts),
            "top_sku": top_sku,
            "sku_breakdown": sku_counts,
        }

    def reset_stats(self) -> None:
        """Reset all statistics to default values.

        WARNING: This will delete all historical data. Use with caution.
        """
        default_stats = self._get_default_stats()
        self._save_stats(default_stats)


if __name__ == "__main__":
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as tmp:
        manager = StatsManager(tmp)

        manager.record_analysis(
            client_id="M",
            session_id="2025-11-05_1",
            orders_count=150,
            metadata={"fulfillable_orders": 142, "courier_breakdown": {"DHL": 80, "DPD": 62}},
        )
        manager.record_packing(
            client_id="M",
            session_id="2025-11-05_1",
            worker_id="001",
            orders_count=142,
            items_count=450,
            metadata={"duration_seconds": 9000},
        )
        manager.record_label_print(client_id="M", sku="SKU-1", copies=3)

        stats = manager._load_stats()
        assert stats["total_orders_analyzed"] == 150
        assert stats["total_orders_packed"] == 142
        assert stats["total_labels_printed"] == 3
        assert stats["by_client"]["M"]["sessions"] == 1
        assert stats["version"] == "2.0"

        global_stats = manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == 150
        assert global_stats["total_orders_packed"] == 142

        print("stats_manager self-check OK")
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd packing-tool && python -m pytest tests/test_stats_manager.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Run the existing crash-safety regression test to confirm it still passes unchanged**

Run: `cd packing-tool && python -m pytest tests/test_atomic_write.py -v`
Expected: PASS (5 tests, including `test_stats_manager_atomic_update_is_actually_crash_safe`)

- [ ] **Step 6: Run the module's own self-check**

Run: `cd packing-tool && python shared/stats_manager.py`
Expected: prints `stats_manager self-check OK`

- [ ] **Step 7: Commit**

```bash
cd packing-tool
git add shared/stats_manager.py tests/test_stats_manager.py
git commit -m "Merge stats_manager.py into the canonical superset

Combines shopify-fulfillment-tool's fuller method set (record_analysis,
get_global_stats, get_client_stats, history/reporting, record_label_print)
with packing-tool's better infrastructure (shared.file_lock, tz-aware
shared.metadata_utils timestamps, the temp-file-into-locked-handle
_atomic_update). One FileLockError class instead of two. Stats-file
version bumped to 2.0. get_label_print_history now normalizes naive
start_date/end_date (as built from a QDate) against tz-aware stored
timestamps instead of raising on comparison."
```

---

### Task 3: Add `shared/session_id.py` and wire it into packing-tool

**Files:**
- Create: `packing-tool/shared/session_id.py`
- Modify: `packing-tool/src/main.py:44` (import), `packing-tool/src/main.py:1625-1627` (usage)

**Interfaces:**
- Produces: `shared.session_id.derive_session_id(session_path: str | Path) -> str`. Consumed here by `main.py`, and by Task 8 in shopify-fulfillment-tool's `actions_handler.py`.

- [ ] **Step 1: Create `shared/session_id.py`**

```python
"""Canonical session_id derivation shared between Packing Tool and Shopify
Tool, so a record written by one and a record written by the other for the
same real-world session carry the exact same session_id string.
"""
from pathlib import Path
from typing import Union


def derive_session_id(session_path: Union[str, Path]) -> str:
    """Derive a session_id from a session directory path.

    Both apps must call this instead of building their own session_id.
    Shopify Tool already used the folder name (Path(session_path).name);
    Packing Tool used to fall back, in one code path, to
    f"{current_session_path}_{current_packing_list}", which never matched
    Shopify Tool's value for the same real-world session.
    """
    return Path(session_path).name
```

(No dedicated test file: this is a one-line pass-through, exempt from the plan's test-every-task default per the approved spec — trivial one-liners don't carry independent failure modes worth a test file. It's exercised indirectly by Task 8's manual verification.)

- [ ] **Step 2: Wire the `derive_session_id` import into `main.py`**

`WorkerManager`'s import path (line 44) is left untouched here — it still moves from `shared.worker_manager` to bare `worker_manager` in Task 4, alongside the file move itself, so that edit and the move land in the same commit instead of leaving an intermediate broken import.

Add the `derive_session_id` import right after the `StatsManager` import at line 43:

```python
from shared.stats_manager import StatsManager
from shared.session_id import derive_session_id
from shared.worker_manager import WorkerManager
```

- [ ] **Step 3: Replace the broken session_id derivation**

In `packing-tool/src/main.py`, change:

```python
                if _is_shopify:
                    _session_id = f"{getattr(self, 'current_session_path', '')}_{getattr(self, 'current_packing_list', '')}"
                    _pl_path_str = getattr(self, 'current_packing_list', 'Unknown') or 'Unknown'
                else:
                    _session_id = self.session_manager.session_id
                    _pl_path_str = str(self.session_manager.packing_list_path or 'Unknown')
```

to:

```python
                if _is_shopify:
                    _session_id = derive_session_id(getattr(self, 'current_session_path', ''))
                    _pl_path_str = getattr(self, 'current_packing_list', 'Unknown') or 'Unknown'
                else:
                    _session_id = self.session_manager.session_id
                    _pl_path_str = str(self.session_manager.packing_list_path or 'Unknown')
```

Only the `_is_shopify` branch changes — that is the one whose `session_id` is meant to correlate with a session Shopify Tool wrote to `Stats/global_stats.json`. The `else` branch is a packing-tool-only session with no corresponding Shopify Tool record, and is untouched.

- [ ] **Step 4: Verify the app still imports cleanly**

Run: `cd packing-tool && python -c "import sys; sys.path.insert(0, 'src'); sys.path.insert(0, '.'); import ast; ast.parse(open('src/main.py').read())"`
Expected: no output (syntax parses; the full import check happens in Task 4's Step 5, since `from worker_manager import WorkerManager` doesn't resolve until that task's file move lands)

- [ ] **Step 5: Commit**

```bash
cd packing-tool
git add shared/session_id.py src/main.py
git commit -m "Add shared.session_id.derive_session_id and use it for Shopify-linked sessions

Packing Tool used to build session_id as
f'{current_session_path}_{current_packing_list}' for sessions opened from
a Shopify Tool analysis output — never matching the session_id Shopify
Tool itself recorded (Path(session_path).name) for the same session in
Stats/global_stats.json. Both apps now derive it the same way."
```

---

### Task 4: Move `shared/worker_manager.py` to `src/worker_manager.py`

**Files:**
- Move: `packing-tool/shared/worker_manager.py` → `packing-tool/src/worker_manager.py` (content unchanged)
- Modify: `packing-tool/src/main.py:44`
- Modify: `packing-tool/src/worker_selection_dialog.py:15`

**Interfaces:**
- Produces: `worker_manager.WorkerManager`, `worker_manager.WorkerProfile` (same classes, same public API — only the import path changes, from `shared.worker_manager` to bare `worker_manager`, matching how every other `src/*.py` sibling module is imported in this codebase).

- [ ] **Step 1: Move the file**

```bash
cd packing-tool
git mv shared/worker_manager.py src/worker_manager.py
```

No internal changes needed inside the file: it does `from shared.atomic_write import atomic_write_json` and (locally, inside two methods) `from shared.metadata_utils import get_current_timestamp` — both still resolve correctly from `src/`, since `packing-tool/src/main.py` already adds the project root to `sys.path` (`project_root = Path(__file__).parent.parent`), which is how every other `src/*.py` file already imports from `shared.*`.

- [ ] **Step 2: Update the import in `main.py`**

In `packing-tool/src/main.py`, change:

```python
from shared.stats_manager import StatsManager
from shared.session_id import derive_session_id
from shared.worker_manager import WorkerManager
```

to:

```python
from shared.stats_manager import StatsManager
from shared.session_id import derive_session_id
from worker_manager import WorkerManager
```

- [ ] **Step 3: Update the import in `worker_selection_dialog.py`**

In `packing-tool/src/worker_selection_dialog.py`, change line 15 from:

```python
from shared.worker_manager import WorkerManager, WorkerProfile
```

to:

```python
from worker_manager import WorkerManager, WorkerProfile
```

- [ ] **Step 4: Verify no other reference to `shared.worker_manager` remains**

Run: `cd packing-tool && grep -rn "shared\.worker_manager\|shared import.*Worker" src/ tests/ shared/`
Expected: no output

- [ ] **Step 5: Verify the app imports cleanly**

Run:
```bash
cd packing-tool
QT_QPA_PLATFORM=offscreen python -c "
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from worker_manager import WorkerManager, WorkerProfile
print('worker_manager import OK')
"
```
Expected: prints `worker_manager import OK`

- [ ] **Step 6: Run the full test suite**

Run: `cd packing-tool && python -m pytest -v`
Expected: PASS (all tests, including the pre-existing suite — moving the file doesn't touch its logic)

- [ ] **Step 7: Commit**

```bash
cd packing-tool
git add -A
git commit -m "Move worker_manager.py out of shared/ into src/

WorkerManager/WorkerProfile were never used by shopify-fulfillment-tool
(0 imports, not in its shared/__init__.py) — packing-tool's own worker
profile system doesn't belong in the package that's supposed to be
identical between both apps."
```

---

### Task 5: `FULFILLMENT_SERVER_PATH` env-var precedence in `profile_manager.py`

**Files:**
- Modify: `packing-tool/src/profile_manager.py:79-82`
- Modify: `packing-tool/tests/conftest.py` (add an autouse hermetic fixture)
- Modify: `packing-tool/tests/test_profile_manager.py` (add two tests)

**Interfaces:**
- Produces: `ProfileManager.__init__` now resolves `base_path` from `FULFILLMENT_SERVER_PATH` env var first, `config.ini`'s `[Network] FileServerPath` second — matching shopify-fulfillment-tool's `shopify_tool/profile_manager.py::_get_base_path()` precedence exactly (same env var name).

- [ ] **Step 1: Write the failing tests**

First, add a hermetic-test fixture to `packing-tool/tests/conftest.py` (append near the top, after the existing `qapp` fixture):

```python
@pytest.fixture(autouse=True)
def _clear_fulfillment_server_path_env(monkeypatch):
    """Hermetic tests: FULFILLMENT_SERVER_PATH must not leak in from the
    developer's shell (e.g. left set from working on the sibling
    shopify-fulfillment-tool repo), or every fixture that builds a
    ProfileManager from config_ini would silently redirect to whatever
    that variable points at instead of the tmp_path server_root.
    """
    monkeypatch.delenv("FULFILLMENT_SERVER_PATH", raising=False)
```

Then add to `packing-tool/tests/test_profile_manager.py`:

```python
# ---------------------------------------------------------------------------
# base_path resolution: FULFILLMENT_SERVER_PATH env var vs config.ini
# ---------------------------------------------------------------------------
# Regression/consistency test: Shopify Tool has always read its shared
# file-server path from the FULFILLMENT_SERVER_PATH env var first, falling
# back to a hardcoded default. Packing Tool used to read only config.ini,
# with no way to point both apps at the same server from one place. Now
# Packing Tool checks the same env var first too, falling back to
# config.ini for existing deployments that only set FileServerPath there.

def test_env_var_takes_precedence_over_config_ini(tmp_path, config_ini, server_root, monkeypatch):
    env_server = tmp_path / "env_server"
    env_server.mkdir()
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(env_server))

    manager = ProfileManager(config_path=str(config_ini))

    assert manager.base_path == env_server
    assert manager.base_path != server_root


def test_falls_back_to_config_ini_when_env_var_unset(config_ini, server_root):
    manager = ProfileManager(config_path=str(config_ini))

    assert manager.base_path == server_root
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd packing-tool && python -m pytest tests/test_profile_manager.py -k "env_var" -v`
Expected: FAIL on `test_env_var_takes_precedence_over_config_ini` — `manager.base_path` equals `server_root` (from `config.ini`), not `env_server`, because the env var is not read yet. `test_falls_back_to_config_ini_when_env_var_unset` passes already (nothing to change there yet), confirming the fallback path is not broken by the fixture addition.

- [ ] **Step 3: Add the env-var precedence**

In `packing-tool/src/profile_manager.py`, change:

```python
        # Get paths from config
        file_server_path = self.config.get('Network', 'FileServerPath', fallback=None)
        if not file_server_path:
            raise ProfileManagerError("FileServerPath not configured in config.ini")
```

to:

```python
        # Get paths from config — FULFILLMENT_SERVER_PATH env var takes
        # precedence when set (same variable, same precedence
        # shopify-fulfillment-tool's ProfileManager already uses), so both
        # apps can be pointed at the same file server from one place.
        # Falls back to config.ini for existing deployments.
        file_server_path = os.environ.get("FULFILLMENT_SERVER_PATH") or self.config.get(
            'Network', 'FileServerPath', fallback=None
        )
        if not file_server_path:
            raise ProfileManagerError(
                "FileServerPath not configured: set FULFILLMENT_SERVER_PATH "
                "or add FileServerPath to config.ini"
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd packing-tool && python -m pytest tests/test_profile_manager.py -v`
Expected: PASS (all tests in the file, including the two new ones)

- [ ] **Step 5: Run the full suite to confirm the new autouse fixture didn't break anything else**

Run: `cd packing-tool && python -m pytest -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
cd packing-tool
git add src/profile_manager.py tests/conftest.py tests/test_profile_manager.py
git commit -m "Add FULFILLMENT_SERVER_PATH env-var precedence to ProfileManager

Matches shopify-fulfillment-tool's existing precedence (env var first,
config fallback second) so both apps can be pointed at the same file
server from one place instead of two independently-configured sources.
Existing config.ini-only deployments are unaffected."
```

---

### Task 6: Update `shared/__init__.py` and run the full packing-tool suite

**Files:**
- Modify: `packing-tool/shared/__init__.py`

**Interfaces:**
- Produces: `shared.StatsManager`, `shared.StatsManagerError`, `shared.FileLockError` — `WorkerManager`/`WorkerProfile` no longer exported from `shared` (moved to `src/worker_manager.py` in Task 4).

- [ ] **Step 1: Rewrite `shared/__init__.py`**

Replace the entire contents of `packing-tool/shared/__init__.py` with:

```python
"""
Shared modules for Shopify Fulfillment Tool and Packing Tool.

This package contains unified components that work identically in both
tools. Canonical copy lives in packing-tool/shared/; synced into
shopify-fulfillment-tool/shared/ by
shopify-fulfillment-tool/scripts/sync_shared.py.
"""

from .file_lock import FileLockError
from .stats_manager import StatsManager, StatsManagerError

__all__ = [
    'StatsManager',
    'StatsManagerError',
    'FileLockError',
]

__version__ = '2.0.0'
```

- [ ] **Step 2: Run the full packing-tool test suite**

Run: `cd packing-tool && python -m pytest -v`
Expected: PASS (every test — this is the checkpoint before touching shopify-fulfillment-tool)

- [ ] **Step 3: Run ruff if configured**

Run: `cd packing-tool && ruff check shared/ src/ 2>&1 | head -50 || true`
Expected: no new errors introduced by this plan's changes (pre-existing warnings elsewhere are out of scope)

- [ ] **Step 4: Commit**

```bash
cd packing-tool
git add shared/__init__.py
git commit -m "Stop exporting WorkerManager from shared/, bump package version to 2.0.0

WorkerManager moved to src/worker_manager.py in the previous commit —
shared/ now only exports what's actually shared between both apps."
```

---

### Task 7: Create and run `shopify-fulfillment-tool/scripts/sync_shared.py`

**Files:**
- Create: `shopify-fulfillment-tool/scripts/sync_shared.py`
- Replace (via running the script): `shopify-fulfillment-tool/shared/__init__.py`, `stats_manager.py`, `README.md`
- Create (via running the script): `shopify-fulfillment-tool/shared/file_lock.py`, `atomic_write.py`, `metadata_utils.py`, `session_id.py`

**Interfaces:**
- Produces: `shopify-fulfillment-tool/shared/` becomes byte-identical to `packing-tool/shared/` (excluding `__pycache__`).

- [ ] **Step 1: Create the sync script**

```python
#!/usr/bin/env python3
"""One-way sync of the canonical shared/ package from packing-tool into this
repo. packing-tool/shared/ is the single source of truth (see
packing-tool/docs/superpowers/specs/2026-07-25-shared-unification-design.md)
— never hand-edit shopify-fulfillment-tool/shared/ directly.

Usage:
    python scripts/sync_shared.py
"""
import shutil
import sys
from pathlib import Path

THIS_REPO = Path(__file__).resolve().parent.parent
SOURCE = THIS_REPO.parent / "packing-tool" / "shared"
DEST = THIS_REPO / "shared"


def main() -> int:
    if not SOURCE.is_dir():
        print(f"Source not found: {SOURCE}", file=sys.stderr)
        print("Expected packing-tool as a sibling directory of this repo.", file=sys.stderr)
        return 1

    copied = []
    for src_file in sorted(SOURCE.rglob("*")):
        if "__pycache__" in src_file.parts:
            continue
        if not src_file.is_file():
            continue

        rel = src_file.relative_to(SOURCE)
        dest_file = DEST / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        copied.append(str(rel))

    print(f"Synced {len(copied)} file(s) from {SOURCE} to {DEST}:")
    for rel in copied:
        print(f"  {rel}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

Run: `cd shopify-fulfillment-tool && python scripts/sync_shared.py`
Expected: prints `Synced 7 file(s) from .../packing-tool/shared to .../shopify-fulfillment-tool/shared:` followed by `__init__.py`, `README.md`, `atomic_write.py`, `file_lock.py`, `metadata_utils.py`, `session_id.py`, `stats_manager.py`

- [ ] **Step 3: Confirm the two directories are now identical**

Run: `diff -rq packing-tool/shared shopify-fulfillment-tool/shared --exclude=__pycache__`
Expected: no output (no differences)

- [ ] **Step 4: Run the merged module's self-check from inside shopify-fulfillment-tool**

Run: `cd shopify-fulfillment-tool && python shared/stats_manager.py`
Expected: prints `stats_manager self-check OK` — this specifically proves `metadata_utils.py`'s dropped `logger` dependency (Task 1) actually resolves in this repo, which is the whole reason that fix was necessary before this sync could work.

- [ ] **Step 5: Commit**

```bash
cd shopify-fulfillment-tool
git add scripts/sync_shared.py shared/
git commit -m "Add scripts/sync_shared.py and sync shared/ from packing-tool

Replaces the divergent hand-maintained copy of shared/ with the canonical
version from packing-tool (superset StatsManager API, extracted file_lock/
atomic_write/metadata_utils, one FileLockError class, stats-file version
2.0). scripts/sync_shared.py is the one-way sync mechanism going forward —
shared/ here should never be hand-edited again."
```

---

### Task 8: Update `actions_handler.py` to use `derive_session_id`, verify shopify-fulfillment-tool

**Files:**
- Modify: `shopify-fulfillment-tool/gui/actions_handler.py:232-238`

**Interfaces:**
- Consumes: `shared.session_id.derive_session_id` (from Task 7's sync).

- [ ] **Step 1: Replace the session_name derivation**

In `shopify-fulfillment-tool/gui/actions_handler.py`, change:

```python
            try:
                from pathlib import Path
                from shared.stats_manager import StatsManager

                self.log.info("Recording analysis statistics to server...")

                stats_mgr = StatsManager(
                    base_path=str(self.mw.profile_manager.base_path)
                )

                # Get session info
                session_name = (
                    Path(self.mw.session_path).name
                    if self.mw.session_path
                    else "unknown"
                )
```

to:

```python
            try:
                from shared.stats_manager import StatsManager
                from shared.session_id import derive_session_id

                self.log.info("Recording analysis statistics to server...")

                stats_mgr = StatsManager(
                    base_path=str(self.mw.profile_manager.base_path)
                )

                # Get session info
                session_name = (
                    derive_session_id(self.mw.session_path)
                    if self.mw.session_path
                    else "unknown"
                )
```

(`derive_session_id` already does `Path(session_path).name` internally, so the `from pathlib import Path` local import is no longer needed here — dropped since nothing else in this block uses `Path` directly. Confirm with Step 2 before relying on this.)

- [ ] **Step 2: Confirm `Path` isn't used elsewhere in this method**

Run: `grep -n "Path(" shopify-fulfillment-tool/gui/actions_handler.py`
Expected: no remaining bare `Path(` calls in the `on_analysis_finished` method (if any other call sites of `Path` exist elsewhere in the file outside this method, they have their own imports already — this only removes the one local import inside this method's `try` block)

- [ ] **Step 3: Lint**

Run: `cd shopify-fulfillment-tool && ruff check gui/actions_handler.py`
Expected: no new errors (in particular, no unused-import warning for `Path` if it was fully removed correctly)

- [ ] **Step 4: Headless smoke test**

Run: `cd shopify-fulfillment-tool && CI=1 python run_dev.py`
Expected: exits cleanly (this is the same smoke test `.github/workflows/build-release.yml` runs — headless import + construct MainWindow); confirms `actions_handler.py` still imports without errors

- [ ] **Step 5: Commit**

```bash
cd shopify-fulfillment-tool
git add gui/actions_handler.py
git commit -m "Use shared.session_id.derive_session_id for analysis session_id

Was already equivalent to Path(session_path).name — switching to the
shared helper so this can never silently diverge from what Packing Tool
derives for the same session again."
```

---

### Task 9: End-to-end sanity check on the shared dev-server

**Files:** none (manual verification only, no code changes)

Both repos already share a local dev-server for exactly this kind of cross-repo check (`packing-tool/run_dev.py` points at `shopify-fulfillment-tool/dev-server`).

- [ ] **Step 1: Reset the dev-server's stats file (simulates the production replacement the user is doing manually)**

Run: `rm -f shopify-fulfillment-tool/dev-server/Stats/global_stats.json`
Expected: file removed (or no-op if it doesn't exist yet)

- [ ] **Step 2: Launch Shopify Tool against the dev-server and record an analysis**

Run: `cd shopify-fulfillment-tool && python run_dev.py`
Action: run an analysis for any client through the UI, let it complete.
Expected: log line `Statistics recorded: N orders, ...` in the app log; `shopify-fulfillment-tool/dev-server/Stats/global_stats.json` now exists.

- [ ] **Step 3: Inspect the recorded entry**

Run: `python -c "import json; d = json.load(open('shopify-fulfillment-tool/dev-server/Stats/global_stats.json')); print(d['version']); print(d['analysis_history'][-1])"`
Expected: `version` is `2.0`; the last `analysis_history` entry's `timestamp` has a UTC offset (e.g. ends in `+02:00` or `+00:00`, not bare); its `session_id` matches the session folder name under `dev-server/Sessions/CLIENT_.../`.

- [ ] **Step 4: Launch Packing Tool against the same dev-server and complete a packing session for that same client/session**

Run: `cd packing-tool && python run_dev.py` (this writes `config.dev.ini` pointed at the same `shopify-fulfillment-tool/dev-server`, per its own script)
Action: open the session Shopify Tool just produced, complete packing.
Expected: no errors in the log; `record_packing` logged as recorded.

- [ ] **Step 5: Confirm both records share one `by_client` entry and a matching `session_id`**

Run:
```bash
python -c "
import json
d = json.load(open('shopify-fulfillment-tool/dev-server/Stats/global_stats.json'))
a = d['analysis_history'][-1]
p = d['packing_history'][-1]
print('analysis session_id:', a['session_id'])
print('packing  session_id:', p['session_id'])
assert a['session_id'] == p['session_id'], 'session_id mismatch between the two apps'
print('by_client:', d['by_client'][a['client_id']])
print('OK — one shared record, matching session_id')
"
```
Expected: prints `OK — one shared record, matching session_id`; `by_client[<client>]` shows non-zero `orders_analyzed`, `orders_packed`, and `sessions`.

This task has no commit — it's a verification-only checkpoint confirming Tasks 1-8 actually solve the original problem end to end.

---

## Self-Review Notes

- **Spec coverage:** all four conflicts from the spec are covered — `version` field (Task 2, Step 3), tz-naive/aware timestamps (Task 2's use of `get_current_timestamp`/`parse_timestamp` everywhere, plus the naive-date regression test), `session_id` (Task 3, Task 8), `base_path` source (Task 5). The `shared/` merge and sync mechanism are covered (Tasks 2, 4, 6, 7). Two issues not in the original spec were found while detailing this plan and are captured as Task 1 (private `logger` dependency) and the naive/aware datetime comparison fix inside Task 2 — both documented as corrections in the spec file.
- **Placeholder scan:** none — every step has literal code, exact file paths, and runnable commands.
- **Type consistency:** `derive_session_id(session_path: Union[str, Path]) -> str` (Task 3) is called identically in Task 3 (packing-tool, `main.py`) and Task 8 (shopify-fulfillment-tool, `actions_handler.py`) with a single positional argument in both places. `StatsManager` method signatures in Task 2 match what Task 8's existing (unmodified) call sites in `sku_label_widget.py` and `client_reports_widget.py` already use (`record_label_print(client_id, sku, copies)`, `get_label_print_history(client_id=..., start_date=..., end_date=...)`) — verified against those files' current source during planning, no changes needed there.
