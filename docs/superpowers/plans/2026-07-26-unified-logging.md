# Unified Logging (Packing Tool ↔ Shopify Fulfillment Tool) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace packing-tool's `src/logger.py` and shopify-fulfillment-tool's `shopify_tool/logger_config.py` — two independent, hand-rolled logging setups — with one canonical `shared/logger.py`, fix the concrete bugs found while designing it (shopify-fulfillment-tool's centralized logging never actually reaching the file server; packing-tool's logger resolving its own server path independently of `ProfileManager`; `extra=` context fields being silently dropped), and make logging safe when multiple PCs run either app against the same network file server — without needing any file locking.

**Architecture:** `packing-tool/shared/logger.py` becomes the single source of truth, copied into shopify-fulfillment-tool by the existing `shopify-fulfillment-tool/scripts/sync_shared.py`. Each process writes its own log file (`Logs/<tool_name>/<tool_name>_<hostname>_<pid>.log`), so concurrent writers never share a file and no locking is needed. `setup_logging()` is called from each app's own `ProfileManager` right after `base_path` is resolved, configuring the root logger so every existing `logging.getLogger(__name__)` / `logging.getLogger("ShopifyToolLogger")` call site keeps working unchanged.

**Tech Stack:** Python 3.11+, pytest (packing-tool only — shopify-fulfillment-tool has no test suite yet, verified via `ruff check .` + its existing headless smoke test `CI=1 python run_dev.py`).

**Related spec:** `docs/superpowers/specs/2026-07-26-unified-logging-design.md`. One correction found while detailing this plan — see Global Constraints.

## Global Constraints

- Canonical `shared/logger.py` lives in `packing-tool/shared/`; shopify-fulfillment-tool's copy is produced only by running `scripts/sync_shared.py`, never hand-edited.
- Per-process log files: `Logs/<tool_name>/<tool_name>_<hostname>_<pid>.log` (`hostname` = `socket.gethostname()`, `pid` = `os.getpid()`). `TimedRotatingFileHandler(when="midnight", backupCount=retention_days)` — daily rotation because either app can stay open across multiple days.
- No file locking anywhere in this module — a per-process filename has exactly one writer for its whole lifetime, unlike `shared.stats_manager`'s genuinely-shared `Stats/global_stats.json`, which needs `shared.file_lock`.
- `setup_logging()` must be **idempotent within a process**: a second call (e.g. the Server Connection recovery-retry flow reconstructing `ProfileManager` after the user fixes an unreachable path) must close and replace its own previously-added handlers, not stack duplicates that would each re-emit every subsequent log line. This was not called out in the spec — found while tracing `ProfileManager`'s recovery-retry flow (`docs/superpowers/specs/2026-07-26-server-connection-settings-design.md`) during planning, and confirmed necessary for the packing-tool test suite too: `tests/conftest.py`'s `profile_manager` fixture constructs a fresh `ProfileManager` (and therefore triggers `setup_logging()`) in nearly every test, all within one `pytest` process.
- `_sweep_old_logs` (mtime-based, best-effort, `retention_days` old) replaces `backupCount`'s cleanup role, since a per-process file has no long-lived owner left to prune its own old rotations once its process exits.
- Console handler (`StreamHandler`) is added only when `sys.stderr is not None` — both apps build with `pyinstaller --onefile --windowed` (`packing-tool/main.spec:46`, `shopify-fulfillment-tool/.github/workflows/build_release.yml:64`), which makes `sys.stderr` `None`, so a `StreamHandler` in the packaged EXE currently silently no-ops on every call.
- `UnifiedJSONFormatter` captures `extra=` fields generically (any `LogRecord` attribute not in a precomputed standard-attribute set), not via a hardcoded `extra_data` key — this is a real fix, not a style choice: `packing-tool/src/session_lock_manager.py` already calls loggers with `extra={"client_id": ..., "session_dir": ...}`, which the old formatter silently dropped.
- `base_path` and `level` resolution stay per-app (same pattern as `StatsManager`/`server_connection`): packing-tool reads `config.ini [Logging] LogLevel`/`LogRetentionDays` (unchanged keys/fallbacks); shopify-fulfillment-tool gets a new env var `FULFILLMENT_LOG_LEVEL` (mirrors the existing `FULFILLMENT_SERVER_PATH` precedent), fallback `INFO`.
- **Correction to the spec's scope item 8:** the spec says "1 місце" (one location) of a bare `logging.<level>()` call in shopify-fulfillment-tool needing fixed to a module logger. Re-checking while planning: `grep -rl` (file-count, not occurrence-count) was misread during spec-writing — `gui/main_window_pyside.py` alone has ~38 such call sites, not 1. These are **not** a functional bug: `UnifiedJSONFormatter` keys off `record.module`/`record.funcName`/`record.lineno`, never `record.name`, so a bare `logging.info(...)` (root logger) and `logging.getLogger("ShopifyToolLogger").info(...)` produce identical JSON output once the root logger is configured. Normalizing all 38 call sites to a module logger would be a same-behavior style change with no diagnostic value — descoped from this plan (Task 8 covers only the `exc_info` fixes, which do change what's diagnosable from the log file).
- Tests use real file I/O under `tmp_path`, no mocks, per this suite's stated philosophy (`tests/conftest.py`).
- shopify-fulfillment-tool has no `tests/` directory (per its `CLAUDE.md`: "Tests are being rewritten"). Verification there is `ruff check .` plus its existing CI smoke test: `CI=1 python run_dev.py`.

---

### Task 1: Create the canonical `shared/logger.py`

**Files:**
- Create: `packing-tool/shared/logger.py`
- Create: `packing-tool/tests/test_logger.py`

**Interfaces:**
- Produces: `shared.logger.setup_logging(tool_name: str, base_path: str, level: int = logging.INFO, retention_days: int = 30) -> None`, `shared.logger.UnifiedJSONFormatter(tool_name: str)`. Used by Task 2 (packing-tool) and Task 6 (shopify-fulfillment-tool, after Task 5's sync).

- [ ] **Step 1: Write the failing tests**

Create `packing-tool/tests/test_logger.py`:

```python
"""Unified logger (shared/logger.py) - per-process log files (no locking:
each filename has exactly one writer for its whole lifetime), a JSON
formatter that generically captures extra= fields, a console handler
gated on sys.stderr being available, and a best-effort mtime-based
retention sweep (per-process files have no long-lived owner left to
prune their own old rotations, unlike a TimedRotatingFileHandler
rotating a single long-lived shared file)."""
import json
import logging
import os
import time

import pytest

from shared.logger import setup_logging, _sweep_old_logs, _active_handlers


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Hermetic tests: each test's setup_logging() call configures the
    real root logger (there is only one). Handlers and level must not
    leak between tests, or a later test's assertions about handler count
    would depend on test execution order."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    for handler in root.handlers[:]:
        if handler not in original_handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(original_level)
    _active_handlers.clear()


def _read_json_lines(log_file):
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_setup_logging_creates_one_file_per_process(tmp_path):
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)

    log_dir = tmp_path / "Logs" / "TestTool"
    files = list(log_dir.glob("TestTool_*.log"))
    assert len(files) == 1
    assert f"_{os.getpid()}.log" in files[0].name


def test_log_message_is_captured_as_json(tmp_path):
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)
    logging.getLogger("test_module").info("hello world")

    log_file = next((tmp_path / "Logs" / "TestTool").glob("TestTool_*.log"))
    records = _read_json_lines(log_file)
    assert any(r["message"] == "hello world" and r["level"] == "INFO" for r in records)


def test_extra_fields_are_captured_generically(tmp_path):
    """Regression: packing-tool's old StructuredJSONFormatter looked for a
    record.extra_data attribute that logging never actually sets - each
    extra={...} key becomes its own attribute directly on the record, so
    session_lock_manager.py's extra={"client_id": ...} calls were
    silently dropped from the JSON output. UnifiedJSONFormatter must not
    repeat that bug."""
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)
    logging.getLogger("test_module").warning(
        "lock conflict", extra={"client_id": "M", "session_dir": "S1"}
    )

    log_file = next((tmp_path / "Logs" / "TestTool").glob("TestTool_*.log"))
    records = _read_json_lines(log_file)
    match = next(r for r in records if r["message"] == "lock conflict")
    assert match["extra"] == {"client_id": "M", "session_dir": "S1"}


def test_setup_logging_is_idempotent(tmp_path):
    """Regression: the Server Connection recovery-retry flow can
    reconstruct ProfileManager (and therefore call setup_logging again)
    within the same process. A second call must replace, not stack, its
    handlers - otherwise every subsequent log line gets emitted once per
    accumulated handler."""
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)
    handler_count_after_first = len(_active_handlers)

    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)
    assert len(_active_handlers) == handler_count_after_first

    logging.getLogger("test_module").info("only once")
    log_file = next((tmp_path / "Logs" / "TestTool").glob("TestTool_*.log"))
    records = _read_json_lines(log_file)
    assert sum(1 for r in records if r["message"] == "only once") == 1


def test_console_handler_skipped_when_stderr_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stderr", None)
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)

    assert not any(isinstance(h, logging.StreamHandler) for h in _active_handlers)


def test_sweep_deletes_old_files_but_keeps_recent(tmp_path):
    log_dir = tmp_path / "Logs" / "TestTool"
    log_dir.mkdir(parents=True)

    old_file = log_dir / "old.log"
    old_file.write_text("stale")
    old_time = time.time() - 40 * 86400
    os.utime(old_file, (old_time, old_time))

    recent_file = log_dir / "recent.log"
    recent_file.write_text("fresh")

    _sweep_old_logs(log_dir, retention_days=30)

    assert not old_file.exists()
    assert recent_file.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd packing-tool && python -m pytest tests/test_logger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.logger'` (module doesn't exist yet).

- [ ] **Step 3: Create `shared/logger.py`**

```python
"""
Unified logging for Shopify Tool and Packing Tool.

Canonical version. This module lives in packing-tool/shared/ and is copied
into shopify-fulfillment-tool/shared/ by
shopify-fulfillment-tool/scripts/sync_shared.py - the two copies must stay
byte-identical. See shared/README.md.

Each process writes its own log file (Logs/<tool_name>/<tool_name>_
<hostname>_<pid>.log), so multiple PCs/processes sharing one network file
server never contend for the same file - no locking needed, since a given
filename only ever has exactly one writer for its whole lifetime. Contrast
with shared.stats_manager, where every process genuinely shares one file
and needs shared.file_lock.
"""
import json
import logging
import os
import socket
import sys
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime"}

# Handlers this module added to the root logger, so a second setup_logging()
# call in the same process (e.g. a Server Connection recovery retry
# reconstructing ProfileManager after the user fixes an unreachable path)
# replaces them instead of stacking duplicates that would each re-emit
# every subsequent log line.
_active_handlers: list = []


class UnifiedJSONFormatter(logging.Formatter):
    """JSON formatter shared by both tools.

    Any attribute a log call sets via extra={...} that isn't one of the
    standard LogRecord attributes is captured under log_data["extra"] -
    generic, not a hardcoded field-name allowlist. This is what packing-
    tool's old StructuredJSONFormatter got wrong: it looked for a single
    record.extra_data attribute that logging never actually sets (each
    extra= key becomes its own attribute directly on the record).
    """

    def __init__(self, tool_name: str):
        super().__init__()
        self.tool_name = tool_name

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "tool": self.tool_name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)

        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS
        }
        if extra:
            log_data["extra"] = extra

        return json.dumps(log_data, ensure_ascii=False, default=str)


def _sweep_old_logs(log_dir: Path, retention_days: int) -> None:
    """Best-effort delete of files in log_dir older than retention_days.

    Per-process log files have no single long-lived owner left to prune
    their own old rotations once their process exits -
    TimedRotatingFileHandler's backupCount only prunes rotations created
    by that same handler instance. A file that can't be deleted (e.g.
    still open by another live process - Windows refuses to remove it)
    is silently skipped and retried on the next startup.
    """
    cutoff = time.time() - retention_days * 86400
    try:
        entries = list(log_dir.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def setup_logging(
    tool_name: str,
    base_path: str,
    level: int = logging.INFO,
    retention_days: int = 30,
) -> None:
    """Configure the root logger for `tool_name`.

    Every existing logging.getLogger(__name__) /
    logging.getLogger("ShopifyToolLogger") call in either app keeps
    working unchanged - this only configures handlers on the root logger.

    Call once base_path is known (from ProfileManager.base_path), not at
    import time with an unresolved path.

    Safe to call again later in the same process - previously-added
    handlers are closed and removed first, so retries never stack
    duplicate handlers.
    """
    global _active_handlers

    root_logger = logging.getLogger()
    for handler in _active_handlers:
        root_logger.removeHandler(handler)
        handler.close()
    _active_handlers = []

    log_dir = Path(base_path) / "Logs" / tool_name
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log_dir = Path.home() / f".{tool_name.lower()}" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"Warning: could not access server logs directory. Using local: {log_dir}. Error: {e}")

    log_file = log_dir / f"{tool_name}_{socket.gethostname()}_{os.getpid()}.log"

    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=retention_days, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(UnifiedJSONFormatter(tool_name))
    root_logger.addHandler(file_handler)
    _active_handlers.append(file_handler)

    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root_logger.addHandler(console_handler)
        _active_handlers.append(console_handler)

    root_logger.setLevel(level)

    _sweep_old_logs(log_dir, retention_days)

    startup_logger = logging.getLogger(tool_name)
    startup_logger.info("=" * 80)
    startup_logger.info(f"{tool_name} started")
    startup_logger.info(f"Log level: {logging.getLevelName(level)}")
    startup_logger.info(f"Log file: {log_file}")
    startup_logger.info("=" * 80)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        setup_logging("SelfCheckTool", tmp, level=logging.DEBUG)
        logging.getLogger(__name__).info("hello", extra={"client_id": "M"})

        log_dir = Path(tmp) / "Logs" / "SelfCheckTool"
        files = list(log_dir.glob("SelfCheckTool_*.log"))
        assert len(files) == 1, f"expected 1 log file, found {files}"

        lines = [line for line in files[0].read_text(encoding="utf-8").splitlines() if '"hello"' in line]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["extra"]["client_id"] == "M"

        handlers_before = len(_active_handlers)
        setup_logging("SelfCheckTool", tmp, level=logging.DEBUG)
        assert len(_active_handlers) == handlers_before, "setup_logging() must not stack duplicate handlers"

        old_file = log_dir / "old.log"
        old_file.write_text("stale")
        old_time = time.time() - 40 * 86400
        os.utime(old_file, (old_time, old_time))
        _sweep_old_logs(log_dir, retention_days=30)
        assert not old_file.exists(), "sweep should delete files older than retention_days"

    print("shared/logger.py self-check OK")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd packing-tool && python -m pytest tests/test_logger.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the module's own self-check**

Run: `cd packing-tool && python shared/logger.py`
Expected: prints `shared/logger.py self-check OK`

- [ ] **Step 6: Commit**

```bash
cd packing-tool
git add shared/logger.py tests/test_logger.py
git commit -m "$(cat <<'EOF'
Add canonical shared/logger.py

One setup_logging(tool_name, base_path, level, retention_days) entry
point for both apps, configuring the root logger so existing
logging.getLogger(__name__) / logging.getLogger("ShopifyToolLogger")
call sites keep working unchanged. Each process gets its own log file
(Logs/<tool_name>/<tool_name>_<hostname>_<pid>.log) so multiple
warehouse PCs writing to the same network file server never contend
for one file - no locking needed. UnifiedJSONFormatter generically
captures extra= fields instead of packing-tool's old formatter's
nonexistent extra_data attribute check.
EOF
)"
```

---

### Task 2: Wire `packing-tool/src/profile_manager.py` to call `setup_logging`

**Files:**
- Modify: `packing-tool/src/profile_manager.py:20-22,100-101`
- Modify: `packing-tool/tests/test_profile_manager.py`

**Interfaces:**
- Consumes: `shared.logger.setup_logging` (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `packing-tool/tests/test_profile_manager.py`:

```python
# ---------------------------------------------------------------------------
# Logging wiring: ProfileManager now calls shared.logger.setup_logging with
# its own resolved base_path, instead of the old logger.py independently
# re-reading config.ini - so a per-process log file always lands under the
# same server the rest of ProfileManager's data uses.
# ---------------------------------------------------------------------------
import logging as _logging


def test_profile_manager_creates_a_per_process_log_file(config_ini, server_root):
    ProfileManager(config_path=str(config_ini))

    log_dir = server_root / "Logs" / "PackingTool"
    files = list(log_dir.glob("PackingTool_*.log"))
    assert len(files) == 1

    for handler in _logging.getLogger().handlers[:]:
        _logging.getLogger().removeHandler(handler)
        handler.close()
```

(The teardown loop at the end avoids leaking this test's handlers into whatever test runs next in the same `pytest` process — the full cleanup fixture is added properly in Task 3 once `AppLogger`'s old neutering is removed from `conftest.py`; this test stands on its own until then.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd packing-tool && python -m pytest tests/test_profile_manager.py -k per_process_log_file -v`
Expected: FAIL — no `Logs/PackingTool/` directory is created (nothing calls `setup_logging` yet).

- [ ] **Step 3: Wire the call into `ProfileManager.__init__`**

In `packing-tool/src/profile_manager.py`, add the import near the top (after line 20's `from logger import get_logger`, which Task 3 removes later):

```python
from shared.logger import setup_logging
```

Then, immediately after `self.logs_dir = self.base_path / "Logs"` (line 100), insert:

```python

        # Per-process log file on the same server ProfileManager itself
        # resolved (base_path) - previously logger.py re-read config.ini
        # independently, so a saved Server Connection path or
        # FULFILLMENT_SERVER_PATH override could silently point data at
        # one server and logs at another.
        log_level_str = self.config.get('Logging', 'LogLevel', fallback='INFO')
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
        retention_days = self.config.getint('Logging', 'LogRetentionDays', fallback=30)
        setup_logging("PackingTool", str(self.base_path), level=log_level, retention_days=retention_days)
```

This also needs `import logging` added near the top of the file (it currently only imports `get_logger` from the private `logger` module, not stdlib `logging` directly) — add `import logging` as its own line, next to the existing `import os` (Task 3 will later remove the now-redundant `from logger import get_logger` line without touching this new `import logging`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd packing-tool && python -m pytest tests/test_profile_manager.py -k per_process_log_file -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `cd packing-tool && python -m pytest -v`
Expected: PASS (every test — `setup_logging` now runs once per `ProfileManager` construction across the whole suite; Task 1's idempotency guarantee is what keeps this from stacking handlers test after test)

- [ ] **Step 6: Commit**

```bash
cd packing-tool
git add src/profile_manager.py tests/test_profile_manager.py
git commit -m "$(cat <<'EOF'
Call shared.logger.setup_logging from ProfileManager

Logging now uses the same base_path ProfileManager itself resolved
(env var / Server Connection UI / config.ini), instead of the old
logger.py independently re-reading config.ini - the two could
previously disagree if the server path was changed via env var or the
Server Connection dialog without also updating config.ini.
EOF
)"
```

---

### Task 3: Delete `packing-tool/src/logger.py`, update the 16 call sites

**Files:**
- Delete: `packing-tool/src/logger.py`
- Modify: `packing-tool/src/main.py:35,54`
- Modify: `packing-tool/src/profile_manager.py:20` (remove now-dead import only — `import logging` already added in Task 2)
- Modify: `packing-tool/src/packer_logic.py:19,25`
- Modify: `packing-tool/src/session_lock_manager.py:18,44`
- Modify: `packing-tool/src/session_manager.py:32,36`
- Modify: `packing-tool/src/session_selector.py:27,32`
- Modify: `packing-tool/src/session_history_manager.py:13,16`
- Modify: `packing-tool/src/session_registry_manager.py:33,37`
- Modify: `packing-tool/src/restore_session_dialog.py:13,15`
- Modify: `packing-tool/src/async_state_writer.py:12,14`
- Modify: `packing-tool/src/sku_mapping_dialog.py:15,17`
- Modify: `packing-tool/src/session_browser/session_browser_widget.py:31,35`
- Modify: `packing-tool/src/session_browser/client_selector_widget.py:15,17`
- Modify: `packing-tool/src/session_browser/orders_tab.py:11,13`
- Modify: `packing-tool/src/session_browser/sessions_list_widget.py:28,32`
- Modify: `packing-tool/src/session_browser/session_details_dialog.py:14,18`
- Modify: `packing-tool/tests/conftest.py:28-29`

**Interfaces:** none (pure mechanical import swap — `logging.getLogger(name)` returns the exact same kind of object `get_logger(name)` used to return, since `get_logger` was always just `AppLogger.get_logger` which itself returned `logging.getLogger(name)`).

- [ ] **Step 1: Replace `from logger import get_logger` / `logger = get_logger(__name__)` in 15 of the 16 files**

For each of these files, replace `from logger import get_logger` with `import logging`, and replace `logger = get_logger(__name__)` with `logger = logging.getLogger(__name__)`:

- `packing-tool/src/main.py` (lines 35, 54)
- `packing-tool/src/packer_logic.py` (lines 19, 25)
- `packing-tool/src/session_manager.py` (lines 32, 36)
- `packing-tool/src/session_selector.py` (lines 27, 32)
- `packing-tool/src/session_history_manager.py` (lines 13, 16)
- `packing-tool/src/session_registry_manager.py` (lines 33, 37)
- `packing-tool/src/restore_session_dialog.py` (lines 13, 15)
- `packing-tool/src/async_state_writer.py` (lines 12, 14)
- `packing-tool/src/sku_mapping_dialog.py` (lines 15, 17)
- `packing-tool/src/session_browser/session_browser_widget.py` (lines 31, 35)
- `packing-tool/src/session_browser/client_selector_widget.py` (lines 15, 17)
- `packing-tool/src/session_browser/orders_tab.py` (lines 11, 13)
- `packing-tool/src/session_browser/sessions_list_widget.py` (lines 28, 32)
- `packing-tool/src/session_browser/session_details_dialog.py` (lines 14, 18)

Worked example (`packing-tool/src/main.py`):

```python
# Before (line 35):
from logger import get_logger
# ...
# Before (line 54):
logger = get_logger(__name__)
```

```python
# After (line 35):
import logging
# ...
# After (line 54):
logger = logging.getLogger(__name__)
```

- [ ] **Step 2: `packing-tool/src/profile_manager.py` — remove the dead import only**

Task 2 already added `import logging` here. Just delete line 20 (`from logger import get_logger`) — do not add a second `import logging`.

- [ ] **Step 3: `packing-tool/src/session_lock_manager.py` — different pattern, uses `AppLogger` directly**

Change:

```python
from logger import AppLogger
```

to:

```python
import logging
```

And change (line 44):

```python
        self.logger = AppLogger.get_logger(self.__class__.__name__)
```

to:

```python
        self.logger = logging.getLogger(self.__class__.__name__)
```

- [ ] **Step 4: Delete `src/logger.py`**

```bash
cd packing-tool
git rm src/logger.py
```

- [ ] **Step 5: Fix `tests/conftest.py`'s now-dead `AppLogger` neutering**

Remove these two lines (28-29):

```python
from logger import AppLogger
AppLogger._initialized = True  # skip real _setup_logging(); avoid UNC-path side effects
```

They neutered the old singleton so tests wouldn't trigger its hardcoded-UNC-path fallback. That class no longer exists — the new `setup_logging()` is called by `ProfileManager` with the test's own `tmp_path`-based `server_root`, which is already hermetic (Task 2's test proved this). Also remove the now-stale comment about `AppLogger` in the module docstring (lines 8-12):

```python
- AppLogger is neutralized before any app module is imported: its default
  config falls back to a hardcoded Windows UNC path
  (\\\\192.168.88.101\\_Fulfilment_\\0UFulfilment) which, on POSIX, is
  treated as a single literal directory name and gets created in the repo
  root the first time any module calls get_logger().
```

Replace it with:

```python
- Each ProfileManager construction calls shared.logger.setup_logging,
  which adds handlers to the real root logger. tests/test_logger.py's
  _reset_root_logger fixture is autouse there; this file doesn't need
  its own equivalent since no test here asserts on handler counts.
```

Also add the autouse root-logger cleanup fixture (so accumulated handlers from many `ProfileManager` constructions across the suite don't pile up), right after `_isolate_qsettings`:

```python
@pytest.fixture(autouse=True)
def _reset_root_logger_handlers():
    """Every ProfileManager construction calls shared.logger.setup_logging,
    which adds handlers to the process-wide root logger. setup_logging
    itself replaces its own previous handlers on each call (see
    shared/logger.py's _active_handlers), so this doesn't strictly leak -
    but closing them between tests avoids holding open file handles to
    dozens of per-test tmp_path directories for the whole suite run.
    """
    yield
    from shared.logger import _active_handlers
    root = logging.getLogger()
    for handler in _active_handlers:
        root.removeHandler(handler)
        handler.close()
    _active_handlers.clear()
```

This needs `import logging` added to `conftest.py`'s existing top-of-file imports (it currently imports `os, sys, json, configparser, Path` but not bare `logging`).

- [ ] **Step 6: Remove the now-redundant per-test cleanup from Task 2's test**

In `packing-tool/tests/test_profile_manager.py`, simplify the test added in Task 2 (the manual handler-cleanup loop is now handled by `conftest.py`'s new autouse fixture):

```python
def test_profile_manager_creates_a_per_process_log_file(config_ini, server_root):
    ProfileManager(config_path=str(config_ini))

    log_dir = server_root / "Logs" / "PackingTool"
    files = list(log_dir.glob("PackingTool_*.log"))
    assert len(files) == 1
```

- [ ] **Step 7: Run the full test suite**

Run: `cd packing-tool && python -m pytest -v`
Expected: PASS (every test)

- [ ] **Step 8: Verify no reference to the old logger module remains**

Run: `cd packing-tool && grep -rn "from logger import\|^import logger$" src/ tests/`
Expected: no output

- [ ] **Step 9: Verify the app imports cleanly**

Run:
```bash
cd packing-tool
QT_QPA_PLATFORM=offscreen python -c "
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
import main
print('main import OK')
"
```
Expected: prints `main import OK`

- [ ] **Step 10: Commit**

```bash
cd packing-tool
git add -A
git commit -m "$(cat <<'EOF'
Delete src/logger.py, use shared.logger everywhere

AppLogger/get_logger() were only ever a lazy-init trigger around a
plain logging.getLogger(name) call - now that setup_logging() is
called explicitly once from ProfileManager (previous commit), every
call site can use bare logging.getLogger(__name__)/
logging.getLogger(self.__class__.__name__) directly. Also removes
tests/conftest.py's AppLogger neutering, which no longer applies -
replaced with a handler-cleanup fixture for shared.logger's root-logger
handlers instead.
EOF
)"
```

---

### Task 4: Content audit in packing-tool — add `exc_info` to error logs that lack a traceback

**Files:**
- Modify: `packing-tool/src/json_cache.py`, `main.py`, `packer_logic.py`, `profile_manager.py`, `session_history_manager.py`, `session_manager.py`, `session_registry_manager.py`, `sku_mapping_dialog.py`, `session_browser/client_selector_widget.py`
- Modify: `packing-tool/shared/metadata_utils.py`

**Interfaces:** none — behavior-preserving (adds `exc_info=True` to existing `logger.error(...)` calls; message text and log level unchanged).

- [ ] **Step 1: Run the detector script to get the current list**

```bash
cd /home/cognitiveghost/Desktop/Projects
cat > /tmp/find_missing_exc_info.py <<'PYEOF'
"""Find logger.error()/logging.error() calls inside an except block that
don't already capture a traceback (no exc_info=..., not .exception())."""
import ast
import sys
from pathlib import Path


def find_in_file(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = []

    class Visitor(ast.NodeVisitor):
        def visit_ExceptHandler(self, node):
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                    if child.func.attr == "error":
                        has_exc_info = any(kw.arg == "exc_info" for kw in child.keywords)
                        if not has_exc_info:
                            hits.append(child.lineno)
            self.generic_visit(node)

    Visitor().visit(tree)
    return hits


total = 0
for root_dir in sys.argv[1:]:
    for py_file in sorted(Path(root_dir).rglob("*.py")):
        if "__pycache__" in py_file.parts or ".venv" in py_file.parts or "venv" in py_file.parts:
            continue
        hits = find_in_file(py_file)
        if hits:
            total += len(hits)
            print(f"{py_file}: {hits}")
print(f"TOTAL: {total}")
PYEOF
python3 /tmp/find_missing_exc_info.py packing-tool/src packing-tool/shared
```

Expected output (36 total, exact line numbers as of this plan being written — re-running may shift numbers slightly if earlier tasks touched these files, but the file list and approximate count should match):

```
packing-tool/src/json_cache.py: [166]
packing-tool/src/main.py: [187, 1172, 1197, 1787, 1799, 2077]
packing-tool/src/packer_logic.py: [292, 319, 537, 1416, 1420, 1614, 1618]
packing-tool/src/profile_manager.py: [149, 163, 236, 389, 426, 489, 499, 581, 637]
packing-tool/src/session_browser/client_selector_widget.py: [76]
packing-tool/src/session_history_manager.py: [470]
packing-tool/src/session_manager.py: [282, 394, 457, 483, 527, 594]
packing-tool/src/session_registry_manager.py: [131, 706]
packing-tool/src/sku_mapping_dialog.py: [53, 284]
packing-tool/shared/metadata_utils.py: [128]
TOTAL: 36
```

- [ ] **Step 2: Fix each flagged call site**

For every `(file, line)` pair reported above, add `exc_info=True` as a keyword argument to that `logger.error(...)` call. Worked example (`packing-tool/src/json_cache.py:166`):

```python
# Before:
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return default
```

```python
# After:
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}", exc_info=True)
            return default
```

Apply the identical transformation (add `, exc_info=True` before the closing `)` of the flagged `.error(...)` call) to every line reported in Step 1 across all 10 files listed there.

- [ ] **Step 3: Re-run the detector to confirm zero remaining**

Run: `python3 /tmp/find_missing_exc_info.py packing-tool/src packing-tool/shared`
Expected: `TOTAL: 0`

- [ ] **Step 4: Run the full test suite**

Run: `cd packing-tool && python -m pytest -v`
Expected: PASS (every test — `exc_info=True` only changes what's written to the log file, not control flow or return values)

- [ ] **Step 5: Commit**

```bash
cd packing-tool
git add -A
git commit -m "$(cat <<'EOF'
Add exc_info=True to error logs missing a traceback

36 logger.error() calls inside except blocks logged only the exception's
str() with no traceback - found via a small AST-based detector (any
Call to .error() inside an ExceptHandler with no exc_info keyword).
With per-process log files now reaching the server unconditionally
(previous commits), these are worth being actually diagnosable from the
log file alone instead of requiring the failure to be reproduced live.
EOF
)"
```

---

### Task 5: Sync `shared/` into shopify-fulfillment-tool

**Files:**
- Replace (via running the script): `shopify-fulfillment-tool/shared/logger.py` (new)

**Interfaces:**
- Produces: `shopify-fulfillment-tool/shared/logger.py`, byte-identical to `packing-tool/shared/logger.py`.

- [ ] **Step 1: Run the existing sync script**

Run: `cd shopify-fulfillment-tool && python scripts/sync_shared.py`
Expected: prints `Synced 8 file(s) from .../packing-tool/shared to .../shopify-fulfillment-tool/shared:` including `logger.py` in the list (alongside the 7 files already synced by the previous shared-unification project).

- [ ] **Step 2: Confirm the two directories are identical**

Run: `diff -rq packing-tool/shared shopify-fulfillment-tool/shared --exclude=__pycache__`
Expected: no output

- [ ] **Step 3: Run the merged module's self-check from inside shopify-fulfillment-tool**

Run: `cd shopify-fulfillment-tool && python shared/logger.py`
Expected: prints `shared/logger.py self-check OK`

- [ ] **Step 4: Commit**

```bash
cd shopify-fulfillment-tool
git add shared/logger.py
git commit -m "$(cat <<'EOF'
Sync shared/logger.py from packing-tool

Canonical unified logging module (per-process log files, no locking,
generic extra= field capture) - wired into shopify_tool/profile_manager.py
in the next commit.
EOF
)"
```

---

### Task 6: Wire `shopify_tool/profile_manager.py` to call `setup_logging`, remove the eager import-time call

**Files:**
- Modify: `shopify-fulfillment-tool/shopify_tool/profile_manager.py:25,97-98`
- Modify: `shopify-fulfillment-tool/shopify_tool/__init__.py:9,12`
- Delete: `shopify-fulfillment-tool/shopify_tool/logger_config.py`

**Interfaces:**
- Consumes: `shared.logger.setup_logging` (Task 5's sync).

- [ ] **Step 1: Add the import**

In `shopify-fulfillment-tool/shopify_tool/profile_manager.py`, change line 25:

```python
from shared.server_connection import resolve_server_path, test_path_reachable
```

to:

```python
from shared.logger import setup_logging
from shared.server_connection import resolve_server_path, test_path_reachable
```

- [ ] **Step 2: Call `setup_logging` right after `base_path` is resolved**

Change (lines 93-97):

```python
        # Auto-detect base path if not provided
        if base_path is None:
            base_path = self._get_base_path()

        self.base_path = Path(base_path)
```

to:

```python
        # Auto-detect base path if not provided
        if base_path is None:
            base_path = self._get_base_path()

        self.base_path = Path(base_path)

        # Per-process log file on the same server base_path resolved to -
        # previously this never happened at all: shopify_tool/__init__.py
        # called the old setup_logging() at package-import time with no
        # base_path, so centralized JSON logging silently wrote to a
        # local ./logs/ folder instead of the network share.
        log_level_str = os.environ.get("FULFILLMENT_LOG_LEVEL", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
        setup_logging("ShopifyTool", str(self.base_path), level=log_level, retention_days=30)
```

(`os` and `logging` are already imported at the top of this file — lines 16-17.)

- [ ] **Step 3: Remove the eager setup at package import time**

Replace the entire contents of `shopify-fulfillment-tool/shopify_tool/__init__.py`:

```python
"""
Shopify Fulfillment Tool

Version: 1.9.9.1
"""

__version__ = "1.9.9.1"
```

(Drops the `from .logger_config import setup_logging` import and the eager `setup_logging()` call — logging is now configured by `ProfileManager` once `base_path` is actually known, not blindly at package-import time.)

- [ ] **Step 4: Delete `logger_config.py`**

```bash
cd shopify-fulfillment-tool
git rm shopify_tool/logger_config.py
```

(`log_with_context()`, defined only in this file, has zero call sites anywhere else in the codebase — confirmed via `grep -rn "log_with_context" --include="*.py" .` returning only its own definition. No replacement needed.)

- [ ] **Step 5: Verify no reference to the deleted module remains**

Run: `cd shopify-fulfillment-tool && grep -rn "logger_config" --include="*.py" .`
Expected: no output

- [ ] **Step 6: Lint**

Run: `cd shopify-fulfillment-tool && ruff check shopify_tool/profile_manager.py shopify_tool/__init__.py`
Expected: no new errors

- [ ] **Step 7: Headless smoke test**

Run: `cd shopify-fulfillment-tool && CI=1 python run_dev.py`
Expected: exits cleanly

- [ ] **Step 8: Verify a per-process log file actually appears on the dev server**

Run:
```bash
cd shopify-fulfillment-tool
rm -rf dev-server/Logs/ShopifyTool
CI=1 python run_dev.py
find dev-server/Logs/ShopifyTool -name "ShopifyTool_*.log"
```
Expected: prints exactly one file path — this is the concrete proof that the original bug (logs never reaching the server) is fixed.

- [ ] **Step 9: Commit**

```bash
cd shopify-fulfillment-tool
git add -A
git commit -m "$(cat <<'EOF'
Call shared.logger.setup_logging from ProfileManager, delete logger_config.py

Fixes centralized logging never actually reaching the file server:
shopify_tool/__init__.py used to call the old setup_logging() at
package-import time with no base_path, so JSON logs silently wrote to
a local ./logs/ folder instead of Logs/shopify_tool/ on the network
share. Now called from ProfileManager.__init__ right after base_path
is resolved, same as packing-tool. Also adds FULFILLMENT_LOG_LEVEL env
var support (shopify-fulfillment-tool had no way to configure log
level before this).
EOF
)"
```

---

### Task 7: Fix `main_window_pyside.py`'s `setup_logging` clobbering the configured level

**Files:**
- Modify: `shopify-fulfillment-tool/gui/main_window_pyside.py:271-272`

**Interfaces:** none.

- [ ] **Step 1: Remove the unconditional `setLevel(INFO)`**

Change (lines 267-274):

```python
        self.log_handler = QtLogHandler()
        self.log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)
        self.log_handler.log_message_received.connect(
            self.execution_log_edit.appendPlainText
        )
```

to:

```python
        self.log_handler = QtLogHandler()
        self.log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        # Root logger level is owned by shared.logger.setup_logging
        # (called from ProfileManager, before this runs) - don't
        # override it back to INFO here, or FULFILLMENT_LOG_LEVEL=DEBUG
        # would silently have no effect.
        logging.getLogger().addHandler(self.log_handler)
        self.log_handler.log_message_received.connect(
            self.execution_log_edit.appendPlainText
        )
```

- [ ] **Step 2: Lint**

Run: `cd shopify-fulfillment-tool && ruff check gui/main_window_pyside.py`
Expected: no new errors

- [ ] **Step 3: Headless smoke test**

Run: `cd shopify-fulfillment-tool && CI=1 python run_dev.py`
Expected: exits cleanly

- [ ] **Step 4: Manual verification of the fix**

Run:
```bash
cd shopify-fulfillment-tool
FULFILLMENT_LOG_LEVEL=DEBUG python run_dev.py
```
Action: perform any action that logs a `logger.debug(...)` call (e.g. trigger a client load).
Expected: DEBUG-level lines now appear in the "Execution Log" panel — before this fix, `main_window_pyside.py`'s own `setup_logging()` always forced the root logger back to `INFO` after `ProfileManager` had already set it to `DEBUG`, so `FULFILLMENT_LOG_LEVEL=DEBUG` had no visible effect.

- [ ] **Step 5: Commit**

```bash
cd shopify-fulfillment-tool
git add gui/main_window_pyside.py
git commit -m "$(cat <<'EOF'
Stop main_window_pyside.py's setup_logging from resetting the root level

logging.getLogger().setLevel(logging.INFO) ran unconditionally after
ProfileManager had already configured the root logger via
shared.logger.setup_logging (previous commit) - silently discarding
FULFILLMENT_LOG_LEVEL=DEBUG every time. Root logger level is now owned
by ProfileManager's call alone.
EOF
)"
```

---

### Task 8: Content audit in shopify-fulfillment-tool — add `exc_info` to error logs that lack a traceback

**Files:**
- Modify: `shopify-fulfillment-tool/shopify_tool/analysis.py`, `barcode_history.py`, `barcode_processor.py`, `core.py`, `csv_utils.py`, `groups_manager.py`, `packing_lists.py`, `pdf_processor.py`, `profile_manager.py`, `reference_labels_history.py`, `sequential_order.py`, `session_manager.py`, `stock_export.py`, `utils.py`
- Modify: `shopify-fulfillment-tool/gui/actions_handler.py`, `barcode_generator_widget.py`, `column_config_dialog.py`, `file_handler.py`, `main_window_pyside.py`, `reference_labels_widget.py`, `session_browser_widget.py`, `table_config_manager.py`, `theme_manager.py`

**Interfaces:** none — behavior-preserving (adds `exc_info=True`; message text and log level unchanged).

- [ ] **Step 1: Run the detector script**

```bash
cd /home/cognitiveghost/Desktop/Projects
cat > /tmp/find_missing_exc_info.py <<'PYEOF'
"""Find logger.error()/logging.error() calls inside an except block that
don't already capture a traceback (no exc_info=..., not .exception())."""
import ast
import sys
from pathlib import Path


def find_in_file(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = []

    class Visitor(ast.NodeVisitor):
        def visit_ExceptHandler(self, node):
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                    if child.func.attr == "error":
                        has_exc_info = any(kw.arg == "exc_info" for kw in child.keywords)
                        if not has_exc_info:
                            hits.append(child.lineno)
            self.generic_visit(node)

    Visitor().visit(tree)
    return hits


total = 0
for root_dir in sys.argv[1:]:
    for py_file in sorted(Path(root_dir).rglob("*.py")):
        if "__pycache__" in py_file.parts or ".venv" in py_file.parts or "venv" in py_file.parts:
            continue
        hits = find_in_file(py_file)
        if hits:
            total += len(hits)
            print(f"{py_file}: {hits}")
print(f"TOTAL: {total}")
PYEOF
python3 /tmp/find_missing_exc_info.py shopify-fulfillment-tool/shopify_tool shopify-fulfillment-tool/gui
```

Expected output (83 total, exact line numbers as of this plan being written):

```
shopify-fulfillment-tool/shopify_tool/analysis.py: [1471, 1474]
shopify-fulfillment-tool/shopify_tool/barcode_history.py: [48, 63]
shopify-fulfillment-tool/shopify_tool/barcode_processor.py: [458]
shopify-fulfillment-tool/shopify_tool/core.py: [205, 215, 225, 459, 463, 539, 543, 547, 555, 561, 588, 592, 596, 604, 610, 986, 989, 1034, 1037, 1088]
shopify-fulfillment-tool/shopify_tool/csv_utils.py: [355, 390]
shopify-fulfillment-tool/shopify_tool/groups_manager.py: [128, 188, 496]
shopify-fulfillment-tool/shopify_tool/packing_lists.py: [308]
shopify-fulfillment-tool/shopify_tool/pdf_processor.py: [192]
shopify-fulfillment-tool/shopify_tool/profile_manager.py: [167, 170, 259, 262, 333, 907, 912, 995, 1090, 1375, 1550]
shopify-fulfillment-tool/shopify_tool/reference_labels_history.py: [59, 69, 87]
shopify-fulfillment-tool/shopify_tool/sequential_order.py: [159]
shopify-fulfillment-tool/shopify_tool/session_manager.py: [147, 315, 361, 402, 445, 601]
shopify-fulfillment-tool/shopify_tool/stock_export.py: [294]
shopify-fulfillment-tool/shopify_tool/utils.py: [36]
shopify-fulfillment-tool/gui/actions_handler.py: [123, 385, 441, 1419, 1441]
shopify-fulfillment-tool/gui/barcode_generator_widget.py: [534, 552]
shopify-fulfillment-tool/gui/column_config_dialog.py: [485, 525, 632]
shopify-fulfillment-tool/gui/file_handler.py: [67, 70, 73, 171, 174, 177, 248, 837]
shopify-fulfillment-tool/gui/main_window_pyside.py: [894]
shopify-fulfillment-tool/gui/reference_labels_widget.py: [340]
shopify-fulfillment-tool/gui/session_browser_widget.py: [507, 528]
shopify-fulfillment-tool/gui/table_config_manager.py: [209, 732, 1025, 1116]
shopify-fulfillment-tool/gui/theme_manager.py: [79, 87]
TOTAL: 83
```

- [ ] **Step 2: Fix each flagged call site**

For every `(file, line)` pair reported above, add `exc_info=True` as a keyword argument to that `logger.error(...)` call. Worked example (`shopify-fulfillment-tool/shopify_tool/core.py:205`):

```python
# Before:
    except KeyError as e:
        logger.error(f"Missing required column in DataFrame for packing analysis: {e}")
```

```python
# After:
    except KeyError as e:
        logger.error(f"Missing required column in DataFrame for packing analysis: {e}", exc_info=True)
```

Apply the identical transformation to every line reported in Step 1, across all 23 files listed there.

- [ ] **Step 3: Re-run the detector to confirm zero remaining**

Run: `python3 /tmp/find_missing_exc_info.py shopify-fulfillment-tool/shopify_tool shopify-fulfillment-tool/gui`
Expected: `TOTAL: 0`

- [ ] **Step 4: Lint**

Run: `cd shopify-fulfillment-tool && ruff check shopify_tool/ gui/`
Expected: no new errors

- [ ] **Step 5: Headless smoke test**

Run: `cd shopify-fulfillment-tool && CI=1 python run_dev.py`
Expected: exits cleanly

- [ ] **Step 6: Commit**

```bash
cd shopify-fulfillment-tool
git add -A
git commit -m "$(cat <<'EOF'
Add exc_info=True to error logs missing a traceback

83 logger.error()/logging.error() calls inside except blocks logged
only the exception's str() with no traceback - found via a small
AST-based detector (any Call to .error() inside an ExceptHandler with
no exc_info keyword). With per-process log files now actually reaching
the server (previous commits), these are worth being diagnosable from
the log file alone.
EOF
)"
```

---

### Task 9: End-to-end sanity check on the shared dev-server

**Files:** none (manual verification only, no code changes)

- [ ] **Step 1: Clear old dev-server logs**

Run: `rm -rf shopify-fulfillment-tool/dev-server/Logs`

- [ ] **Step 2: Launch both apps against the same dev-server at once**

Run in two separate terminals:
```bash
# Terminal 1
cd shopify-fulfillment-tool && python run_dev.py
# Terminal 2
cd packing-tool && python run_dev.py
```
Action: use each app briefly (load a client, open a session).

- [ ] **Step 3: Confirm each process wrote its own file, no errors**

Run: `find shopify-fulfillment-tool/dev-server/Logs -type f`
Expected: two files, e.g. `Logs/ShopifyTool/ShopifyTool_<hostname>_<pid1>.log` and `Logs/PackingTool/PackingTool_<hostname>_<pid2>.log` (different `pid`s) — no `PermissionError` in either app's console output, no `Logging error` messages from Python's own error-handling.

- [ ] **Step 4: Confirm `extra=` fields survive in the JSON output**

Run:
```bash
python3 -c "
import json, glob
for path in glob.glob('shopify-fulfillment-tool/dev-server/Logs/PackingTool/*.log'):
    for line in open(path, encoding='utf-8'):
        record = json.loads(line)
        if 'extra' in record:
            print(record)
            break
"
```
Expected: at least one printed record with a non-empty `"extra"` dict (from `session_lock_manager.py`'s `extra={"client_id": ..., "session_dir": ...}` calls, if a session was opened during Step 2) — confirms the generic `extra=` capture works against a real run, not just the unit test.

- [ ] **Step 5: Confirm the retention sweep doesn't touch an in-use file**

Run:
```bash
find shopify-fulfillment-tool/dev-server/Logs -name "*.log" -newermt "-1 minute"
```
Expected: both files from Step 3 are listed (freshly written, not swept) — this task has no dedicated automated test for "doesn't delete a live file," since `_sweep_old_logs` in Task 1 already covers the pure mtime logic; this step is the live confirmation that a genuinely active file (mtime seconds old) is never a sweep candidate regardless of `retention_days`.

This task has no commit — it's a verification-only checkpoint confirming Tasks 1-8 actually solve the original problem end to end.

---

## Self-Review Notes

- **Spec coverage:** scope items 1-9 from the design doc are all covered — canonical `shared/logger.py` with `setup_logging` (Task 1), per-process files + rotation (Task 1), retention sweep (Task 1), console-handler guard (Task 1), shopify-tool's setup-call-site fix (Task 6), `UnifiedJSONFormatter`'s generic `extra=` capture (Task 1), `setup_logging` called from each `ProfileManager` (Tasks 2, 6), the content audit (Tasks 4, 8), and deletion of `src/logger.py`/`logger_config.py` with the 16 call-site swap (Task 3, Task 6).
- **Correction found while planning:** the spec's content-audit item for "1 bare `logging.<level>()` call site" in shopify-fulfillment-tool undercounted — actual count is ~38, all in `gui/main_window_pyside.py`. Documented in Global Constraints and descoped: these already work correctly (the shared formatter doesn't key off logger name), so normalizing them would be a no-op style change, not a fix.
- **Second correction found while planning:** `setup_logging`'s idempotency requirement (Global Constraints) wasn't in the spec — found by tracing the Server Connection recovery-retry flow (a prior project's feature) and by noticing `tests/conftest.py`'s `profile_manager` fixture constructs a fresh `ProfileManager` in nearly every test within one `pytest` process. Task 1's `_active_handlers` tracking and its dedicated idempotency test are the fix.
- **Placeholder scan:** none — every step has literal code, exact file paths and line numbers, and runnable verification commands. The two "apply this transformation to every line in the list" steps (Task 4 Step 2, Task 8 Step 2) are a uniform, fully-specified mechanical edit (add one keyword argument) with a worked example and an automated zero-remaining verification gate, not an open-ended instruction.
- **Type consistency:** `setup_logging(tool_name: str, base_path: str, level: int = logging.INFO, retention_days: int = 30) -> None` (Task 1) is called identically in Task 2 (`"PackingTool"`) and Task 6 (`"ShopifyTool"`) — same parameter names, same positional/keyword usage. `_active_handlers` and `_sweep_old_logs` (Task 1) are referenced with matching names in Task 1's own tests and in `tests/conftest.py`'s new fixture (Task 3).
