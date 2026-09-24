# Phase 12 Bundle 2 — Packer Mode reset + data-layer fixes: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, in this session (the runner forbids fan-out). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new Packer Mode session opens on a clean document, and the packing data layer stops
losing or hiding progress: unreadable state, silent save failures, the two-PC lock, the Session
Browser's status and progress, the packed-order signal to Shopify, and the worker duration.

**Architecture:** All changes are in `packing-tool`, with no `shared/` edits. Most tasks harden one
existing module at its current interface. One new module, `packing_tool/progress_publisher.py`,
publishes per-order progress in the background through the existing `AsyncStateWriter`.
`MainWindow` changes are wiring, plus one extraction: `_teardown_session()` out of `end_session()`.

**Tech Stack:** Python 3, PySide6 (signals across threads), pytest + pytest-qt, JSON files on an SMB share.

**Spec:** `docs/superpowers/specs/2026-09-24-phase12-bundle2-packer-data-audit-design.md`. Read its
**Owner decisions** section first. Every choice below argues from it.

## Global Constraints

- Work in worktree `packing-tool/.claude/worktrees/phase12-bundle2`, branch `worktree-phase12-bundle2`. Never commit to `main`.
- **Do not edit `shared/`.** This bundle needs no shared change and no Shopify PR.
- Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q` (the `.venv` is a symlink to the main checkout's). Lint: `ruff check .`
- **Ruff hook gotcha:** an editor hook runs `ruff format` over every file touched by the Edit/Write tools. These files are NOT ruff-formatted today, and an Edit would reformat them whole and bury the change (PR #182 had to revert exactly that): `packing_tool/packer_logic.py`, `packing_tool/session_lock_manager.py`, `packing_tool/session_registry_manager.py`, `packing_tool/exceptions.py`, `tests/test_session_lock_manager.py`, `tests/test_packer_logic_state_persistence.py`, `tests/test_packer_mode_widget.py`, `tests/test_packer_mainwindow_seam.py`. **Edit these with a small Python script run through Bash** (`pathlib` read → `str.replace(old, new, 1)` with an `assert old in text` → write), or append tests with `cat >> file <<'EOF'`. `gui/main_window.py` and `gui/packer_mode_widget.py` are already formatted, so Edit is fine on them. New files may be created with Write.
- No UI calls from background threads. A writer-thread event reaches the UI only through a Qt `Signal`.
- User-facing copy is verbatim from the spec. The em dash in `Progress not saved — check the network` is U+2014.
- One commit per task, message `Phase 12 Bundle 2: <task>`, ending with the two trailer lines the session's attribution reminder gives. Commit with `git commit -F <file>`, message file in `$CLAUDE_JOB_DIR/tmp`. Run one plain git command per Bash call (a worktree guard refuses compound ones).

## Review Focus

1. **A share outage while a session opens.** A packing list whose `packing_state.json` exists but can't be read must refuse to open with the file untouched. It must never open empty (Task 2).
2. **A save that fails, then recovers.** The band must stay red on every scan while saves fail and clear on the first success, without hiding the scan outcome (Task 3).
3. **Reading a lock while the owner rewrites it.** An unreadable lock must read as *held*. Taking over a live lock must never be offered (Task 4).
4. **A PC that lost its lock.** It must not write the summary, the registry "incomplete" status or `packing_state.json` over the new owner's session (Task 5).
5. **Resuming a half-packed list.** The Session Browser count, its Age and Packer Mode's progress must all show the resumed state, not `0` (Tasks 1 and 6).

---

### Task 1: Packer Mode opens every session on a clean document (spec item 1)

**Files:**
- Modify: `gui/packer_mode_widget.py` (`reset_for_new_session`, ~line 438)
- Modify: `gui/main_window.py` (new `_open_packer_document`; call sites in `start_session` ~line 928 and `start_shopify_packing_session` ~line 1287)
- Test: `tests/test_packer_mode_widget.py`, `tests/test_packer_mainwindow_seam.py` (append with `cat >>`)

**Interfaces:**
- Produces: `MainWindow._open_packer_document() -> None` (uses `self.logic.session_packing_state` and `self.logic.orders_data`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_mode_widget.py`:

```python
def test_a_new_session_does_not_inherit_the_last_ones_history_or_counts(widget):
    """Phase 12 Bundle 2 item 1: the panel cleared, but the side column
    still showed the finished session's orders and its 2 / 2."""
    widget.add_order_to_history("1001")
    widget.add_order_to_history("1002")
    widget.update_session_progress(2, 2)
    widget.show_session_complete({"title": "Session complete", "body": "done."})

    widget.reset_for_new_session()

    assert widget.bridge.history == []
    assert widget.bridge.progress["orders_done"] == 0
    assert widget.bridge.progress["orders_total"] == 0
```

Append to `tests/test_packer_mainwindow_seam.py`:

```python
def test_starting_a_session_clears_the_document_and_shows_the_resumed_count(window):
    widget = window.packer_mode_widget
    widget.add_order_to_history("0999")
    widget.update_session_progress(5, 5)
    logic = StubLogic("SKU_OK")
    logic.orders_data = {"1001": {}, "1002": {}, "1003": {}}
    logic.session_packing_state = {"completed_orders": ["1001"], "skipped_orders": []}
    window.logic = logic

    window._open_packer_document()

    assert widget.bridge.history == []
    assert widget.bridge.progress["orders_done"] == 1
    assert widget.bridge.progress["orders_total"] == 3
```

- [ ] **Step 2: Run to verify both fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_packer_mode_widget.py tests/test_packer_mainwindow_seam.py`
Expected: the widget test fails because `history` still holds two rows. The seam test fails with `AttributeError: ... '_open_packer_document'`.

- [ ] **Step 3: Implement**

In `gui/packer_mode_widget.py`, replace `reset_for_new_session` with:

```python
    def reset_for_new_session(self):
        """Take the session-complete panel down and clear the whole document.

        clear_screen() resets the *order*; this also resets what belongs to
        the *session* -- its history and order counts -- because the widget
        outlives every session the app runs.
        """
        self._session_over = False
        self.bridge.set_session_end({})
        self.scanner_input.setPlaceholderText("Ready to scan")
        self._history = []
        self.bridge.set_history([])
        self._orders_done = 0
        self._orders_total = 0
        self.clear_screen()  # pushes progress through _push_rows()
```

In `gui/main_window.py`, add next to `switch_to_packer_mode`:

```python
    def _open_packer_document(self):
        """Give Packer Mode a clean document for the session just loaded.

        Runs at session start, so a session always opens clean however the
        last one ended. A resumed list opens on its real count.
        """
        state = self.logic.session_packing_state
        self.packer_mode_widget.reset_for_new_session()
        self.packer_mode_widget.update_session_progress(
            len(state.get("completed_orders", [])), len(self.logic.orders_data)
        )
```

Call `self._open_packer_document()` in `start_session` right after `self.setup_order_table()` (the `# Setup order table` block, ~line 925), and in `start_shopify_packing_session` right after `self.setup_order_table()` at step 10 (~line 1287).

- [ ] **Step 4: Run tests to verify they pass**

Same command as Step 2. Expected: PASS.

- [ ] **Step 5: Commit** — `Phase 12 Bundle 2: a new session opens Packer Mode on a clean document`

---

### Task 2: An unreadable packing state refuses to open (spec A1 / Q1)

**Files:**
- Modify: `packing_tool/exceptions.py` (script edit)
- Modify: `packing_tool/packer_logic.py` `_load_session_state` (~lines 339-366) (script edit)
- Modify: `gui/main_window.py` `start_shopify_packing_session` except clauses (~line 1297)
- Test: `tests/test_packer_logic_state_persistence.py` (script edit: replace one test, append one)

**Interfaces:**
- Produces: `packing_tool.exceptions.PackingStateUnreadableError(PackingToolError)`; module constants `STATE_READ_ATTEMPTS = 3`, `STATE_READ_RETRY_SECONDS = 0.5` in `packer_logic.py`; `PackerLogic._read_state_file(state_file: str) -> dict`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_packer_logic_state_persistence.py`, replace
`test_corrupted_json_state_file_starts_fresh_instead_of_crashing` (the whole function) with:

```python
def test_an_unreadable_state_file_refuses_to_open_and_is_left_alone(
    packer_logic_factory, session_factory, monkeypatch
):
    """Spec A1: starting fresh here meant the first scan overwrote every
    order packed so far. The session must not open, and the file must not
    change."""
    import packing_tool.packer_logic as pl
    from packing_tool.exceptions import PackingStateUnreadableError

    monkeypatch.setattr(pl, "STATE_READ_RETRY_SECONDS", 0)
    orders = [("ORDER-001", "DHL", [{"sku": "SKU-1", "quantity": 1, "product_name": "A"}])]
    _session_dir, work_dir, _list_path = session_factory(client_id="M", orders=orders)
    state_path = work_dir / "packing_state.json"
    state_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(PackingStateUnreadableError):
        packer_logic_factory("M", work_dir)
    assert state_path.read_text(encoding="utf-8") == "{not valid json"


def test_a_transient_read_error_is_retried(packer_logic_factory, session_factory, monkeypatch):
    import builtins

    import packing_tool.packer_logic as pl

    monkeypatch.setattr(pl, "STATE_READ_RETRY_SECONDS", 0)
    orders = [("ORDER-001", "DHL", [{"sku": "SKU-1", "quantity": 1, "product_name": "A"}])]
    _session_dir, work_dir, _list_path = session_factory(client_id="M", orders=orders)
    state_path = work_dir / "packing_state.json"
    state_path.write_text(json.dumps({"completed_orders": ["ORDER-001"]}), encoding="utf-8")

    real_open, calls = builtins.open, {"n": 0}

    def flaky_open(path, *args, **kwargs):
        if str(path) == str(state_path):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("The network name is no longer available")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)
    logic = packer_logic_factory("M", work_dir)
    assert logic.session_packing_state["completed_orders"] == ["ORDER-001"]
```

Add `import pytest` to the file's imports if it is missing.

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_packer_logic_state_persistence.py`
Expected: FAIL. `PackingStateUnreadableError` can't be imported, and the retry test reads `[]` because the cache path swallowed the `OSError`.

- [ ] **Step 3: Implement**

Append to `packing_tool/exceptions.py`:

```python
class PackingStateUnreadableError(PackingToolError):
    """
    Raised when a packing list's packing_state.json exists but cannot be
    read. The session must not open: starting fresh would let the first
    scan overwrite every order already packed (Phase 12 Bundle 2, A1).
    """
```

In `packing_tool/packer_logic.py`:
- Add module constants near the other module-level constants: `STATE_READ_ATTEMPTS = 3` and `STATE_READ_RETRY_SECONDS = 0.5`. Import `time` if it isn't already imported, and `PackingStateUnreadableError` from `packing_tool.exceptions`.
- Add the method:

```python
    def _read_state_file(self, state_file: str) -> dict:
        """Read packing_state.json straight from disk, retrying transient errors.

        Not through JSONCache: its get() returns the default on any error,
        which is exactly what hid a network hiccup as "no saved progress".
        """
        last_error = None
        for attempt in range(STATE_READ_ATTEMPTS):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError) as exc:  # JSONDecodeError is a ValueError
                last_error = exc
                if attempt < STATE_READ_ATTEMPTS - 1:
                    time.sleep(STATE_READ_RETRY_SECONDS)
                continue
            if not isinstance(data, dict):
                raise PackingStateUnreadableError(
                    f"{state_file}: root is {type(data).__name__}, not an object"
                )
            return data
        raise PackingStateUnreadableError(f"{state_file}: {last_error}")
```

- In `_load_session_state`, replace the block that reads through `get_cached_json` down to the end of the `not isinstance(state_data, dict)` fresh-start branch. Every "starting fresh" branch *after* `os.path.exists` must go. Use:

```python
        data = self._read_state_file(state_file)
        # Legacy format wrapped the state in {"data": {...}}
        state_data = data["data"] if isinstance(data.get("data"), dict) else data
```

  Keep the `if not os.path.exists(state_file)` fresh-start branch: a missing file is a new session. `_read_state_file` is called outside the existing `try`, so `PackingStateUnreadableError` propagates. If `get_cached_json` is no longer used in the module, remove its import (`ruff check` flags it).

In `gui/main_window.py` `start_shopify_packing_session`, add an `except` clause *before* `except FileNotFoundError`:

```python
        except PackingStateUnreadableError:
            logger.exception("Packing state unreadable; session not opened")
            self._cleanup_failed_session_start()
            QMessageBox.critical(
                self,
                "Could not read saved progress",
                f"The saved progress for {packing_list_name} could not be read, "
                "so the list was not opened. Nothing was changed. Check the "
                "connection to the server and open it again.",
            )
            return False
```

(import `PackingStateUnreadableError` alongside the existing `packing_tool.exceptions` imports.)
It reaches this clause through `start_worker.error` (`raise start_worker.error`, ~line 1230).

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_packer_logic_state_persistence.py tests/test_json_cache.py`
Expected: PASS. That includes `test_missing_state_file_starts_fresh` and `test_json_cache_is_not_mutated_by_in_memory_migration`, both unchanged.

- [ ] **Step 5: Commit** — `Phase 12 Bundle 2: an unreadable packing state refuses to open`

---

### Task 3: A failed save is on screen until the next success (spec A2 / Q2)

**Files:**
- Modify: `packing_tool/packer_logic.py` (script edit): signal, `_do_atomic_write`
- Modify: `gui/packer_mode_widget.py`: `set_unsaved`, `_push_feedback`, `reset_for_new_session`
- Modify: `gui/main_window.py`: connect the signal at both `all_orders_complete.connect` sites (~lines 913 and 1237)
- Test: `tests/test_packer_logic_state_persistence.py`, `tests/test_packer_mode_widget.py` (append)

**Interfaces:**
- Produces: `PackerLogic.save_failed = Signal(bool)`, where `True` means saving started failing and `False` means it recovered, emitted on transitions only. `PackerModeWidget.set_unsaved(unsaved: bool) -> None`. Module constant `UNSAVED_TEXT = "Progress not saved — check the network"` in `gui/packer_mode_widget.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_logic_state_persistence.py`:

```python
def test_a_failed_save_is_signalled_once_and_its_recovery_once(loaded_logic, monkeypatch):
    import packing_tool.packer_logic as pl

    seen = []
    loaded_logic.save_failed.connect(seen.append)
    real_write = pl.atomic_write_json

    def failing_write(*args, **kwargs):
        raise OSError("share unavailable")

    monkeypatch.setattr(pl, "atomic_write_json", failing_write)
    loaded_logic._do_atomic_write(loaded_logic._build_state_dict())
    loaded_logic._do_atomic_write(loaded_logic._build_state_dict())
    monkeypatch.setattr(pl, "atomic_write_json", real_write)
    loaded_logic._do_atomic_write(loaded_logic._build_state_dict())

    assert seen == [True, False]
```

Append to `tests/test_packer_mode_widget.py`:

```python
def test_unsaved_progress_keeps_the_band_red_and_the_outcome_readable(widget):
    widget.set_unsaved(True)
    widget.show_notification("Order #1001 packed. Scan the next order.", "status_success")
    assert widget.bridge.feedback["role"] == "danger"
    assert widget.bridge.feedback["text"] == (
        "Progress not saved — check the network · Order #1001 packed. Scan the next order."
    )

    widget.set_unsaved(False)
    assert widget.bridge.feedback["role"] == "success"
    assert widget.bridge.feedback["text"] == "Order #1001 packed. Scan the next order."


def test_a_new_session_starts_saved(widget):
    widget.set_unsaved(True)
    widget.reset_for_new_session()
    assert widget.bridge.feedback["role"] == "info"
```


- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_packer_logic_state_persistence.py tests/test_packer_mode_widget.py`
Expected: FAIL with `AttributeError` (`save_failed`, `set_unsaved`).

- [ ] **Step 3: Implement**

`packing_tool/packer_logic.py`, next to `all_orders_complete = Signal()`:

```python
    save_failed = Signal(bool)  # True: state writes started failing; False: they recovered
```

In `__init__`, before `self._state_writer = AsyncStateWriter(...)`, add `self._last_save_ok = True`. Replace `_do_atomic_write`'s `try/except` with:

```python
        try:
            atomic_write_json(state_file, state_data)
            invalidate_json_cache(state_file)
        except Exception:
            logger.exception("CRITICAL: Failed to save session state")
            self._set_save_ok(False)
            return
        self._set_save_ok(True)
        logger.debug(f"Session state saved: {completed_orders_count}/{total_orders} orders, {packed_items}/{total_items} items")
```

and add:

```python
    def _set_save_ok(self, ok: bool) -> None:
        """Emit save_failed on a change only. Runs on the writer thread; Qt
        queues the signal to the receiver's (UI) thread."""
        if ok != self._last_save_ok:
            self._last_save_ok = ok
            self.save_failed.emit(not ok)
```

`gui/packer_mode_widget.py`: add the module constant `UNSAVED_TEXT = "Progress not saved — check the network"`, set `self._unsaved = False` in `__init__` next to `self._history = []`, and:

```python
    def set_unsaved(self, unsaved: bool):
        """Show, or clear, that the packing state is not reaching disk.

        Sticky across scans: every scan rewrites the band, and the warning
        must survive that until a save succeeds (spec Q2).
        """
        self._unsaved = bool(unsaved)
        self._push_feedback()

    def _push_feedback(self):
        text, role = self._feedback_text, self._feedback_role
        if self._unsaved:
            text = f"{UNSAVED_TEXT} · {text}" if text else UNSAVED_TEXT
            role = "danger"
        self.bridge.set_feedback(text, role, self._raw_scan)
```

In `reset_for_new_session`, add `self._unsaved = False` before `self.clear_screen()`.

`gui/main_window.py`: after each `self.logic.all_orders_complete.connect(self._on_all_orders_complete)` (two sites), add
`self.logic.save_failed.connect(self.packer_mode_widget.set_unsaved)`.

- [ ] **Step 4: Run tests.** Same command. Expected: PASS.
- [ ] **Step 5: Commit** — `Phase 12 Bundle 2: a failed save stays on screen until the next success`

---

### Task 4: The lock fails closed and is created exclusively (spec B1, B2 / Q3)

**Files:**
- Modify: `packing_tool/session_lock_manager.py` (script edit): `is_locked`, `acquire_lock`, `update_heartbeat`, new `owns_lock`
- Test: `tests/test_session_lock_manager.py` (append)

**Interfaces:**
- Produces: module constants `LOCK_READ_ATTEMPTS = 3`, `LOCK_READ_RETRY_SECONDS = 0.2`. `is_locked()` may now return `(True, info)` with `info["unreadable"] is True`. `SessionLockManager.owns_lock(session_dir: Path) -> bool | None` returns `True` for our lock, `False` for another owner's lock or no lock, and `None` if the lock is unreadable. Acquire messages `LOCK_UNREADABLE_MSG = "The session lock could not be read. Try again in a moment."` and `LOCK_RACE_MSG = "Another PC opened this session a moment ago. Try again in a moment."`. Neither contains the word "stale", which matters because `MainWindow._acquire_lock_with_stale_prompt` branches on that word.

- [ ] **Step 1: Write the failing tests** (append; `lock_manager`, `session_dir` and `_write_foreign_lock` already exist in the file):

```python
@pytest.fixture
def no_retry_delay(monkeypatch):
    import packing_tool.session_lock_manager as slm

    monkeypatch.setattr(slm, "LOCK_READ_RETRY_SECONDS", 0)


def test_an_unreadable_lock_counts_as_held_and_is_left_alone(lock_manager, session_dir, no_retry_delay):
    lock_path = session_dir / SessionLockManager.LOCK_FILENAME
    lock_path.write_text("", encoding="utf-8")  # what a reader saw mid-rewrite

    success, message, _info = lock_manager.acquire_lock("M", session_dir)

    assert success is False
    assert message == "The session lock could not be read. Try again in a moment."
    assert "stale" not in message.lower()
    assert lock_path.read_text(encoding="utf-8") == ""


def test_losing_the_creation_race_is_refused_not_overwritten(lock_manager, session_dir, monkeypatch):
    import packing_tool.session_lock_manager as slm

    def other_pc_won(*args, **kwargs):
        raise FileExistsError

    monkeypatch.setattr(slm.os, "open", other_pc_won)
    success, message, _info = lock_manager.acquire_lock("M", session_dir)
    assert success is False
    assert message == "Another PC opened this session a moment ago. Try again in a moment."


def test_the_heartbeat_rewrites_the_lock_atomically(lock_manager, session_dir, monkeypatch):
    import packing_tool.session_lock_manager as slm

    assert lock_manager.acquire_lock("M", session_dir)[0]
    writes = []
    real = slm.atomic_write_json
    monkeypatch.setattr(slm, "atomic_write_json", lambda p, d, **kw: (writes.append(p), real(p, d, **kw)))

    assert lock_manager.update_heartbeat(session_dir) is True
    assert writes == [session_dir / SessionLockManager.LOCK_FILENAME]


def test_owns_lock_tells_ours_from_theirs_from_unreadable(lock_manager, session_dir, no_retry_delay):
    assert lock_manager.owns_lock(session_dir) is False  # no lock at all
    assert lock_manager.acquire_lock("M", session_dir)[0]
    assert lock_manager.owns_lock(session_dir) is True
    _write_foreign_lock(session_dir)
    assert lock_manager.owns_lock(session_dir) is False
    (session_dir / SessionLockManager.LOCK_FILENAME).write_text("{", encoding="utf-8")
    assert lock_manager.owns_lock(session_dir) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_session_lock_manager.py`
Expected: FAIL. The unreadable lock currently reads as free and is overwritten. `os.open` is never called. The heartbeat writes in place. `owns_lock` doesn't exist.

- [ ] **Step 3: Implement** (script edits to `packing_tool/session_lock_manager.py`)

1. Constants and imports: `LOCK_READ_ATTEMPTS = 3`, `LOCK_READ_RETRY_SECONDS = 0.2`, `LOCK_UNREADABLE_MSG`, `LOCK_RACE_MSG` (text in *Interfaces*). Make sure `os` and `time` are imported.
2. `is_locked`: replace the single `open`/`json.load` with a retry loop. `FileNotFoundError` returns `(False, None)`, since the lock was just released. Any other `OSError` or `json.JSONDecodeError`, after `LOCK_READ_ATTEMPTS` tries `LOCK_READ_RETRY_SECONDS` apart, logs a warning and returns:

```python
            now = datetime.now().astimezone().isoformat()
            return True, {
                "unreadable": True,
                "locked_by": "unknown PC",
                "user_name": "unknown",
                "lock_time": now,
                "heartbeat": now,  # never stale: an unreadable lock is not abandoned
                "process_id": None,
                "worker_id": None,
                "worker_name": None,
            }
```

   Keep the missing-required-fields branch as it is.
3. `acquire_lock`: at the top of the `if is_locked:` branch, before the own-lock check:

```python
                if lock_info.get("unreadable"):
                    return False, LOCK_UNREADABLE_MSG, None
```

   Replace `atomic_write_json(lock_path, lock_data, indent=2)` in the create path with an exclusive create:

```python
            # Exclusive create: two PCs past the check above cannot both win (spec B2).
            if lock_path.exists():
                lock_path.unlink()  # present but invalid -- is_locked() said free
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2)
```

   and add, *before* the existing `except Exception as e:` of that `try`:

```python
        except FileExistsError:
            self.logger.warning("Lost the lock-creation race", extra={"session_dir": str(session_dir)})
            return False, LOCK_RACE_MSG, None
```

4. `update_heartbeat`: inside the retry loop, drop the `open(..., 'r+')`/`locked_file` in-place rewrite. Read with a plain `open(lock_path, "r")` + `json.load`, keep the ownership check (`return False` if not ours), set `data["heartbeat"]`, then `atomic_write_json(lock_path, data, indent=2)` and `return True`. Keep the `except (OSError, FileLockError, json.JSONDecodeError)` retry handling. Drop `FileLockError` and `locked_file` from the imports if nothing else uses them (`ruff check`).
5. Add:

```python
    def owns_lock(self, session_dir: Path) -> bool | None:
        """Whether this process holds the session's lock.

        True: ours. False: another PC's, or no lock at all -- either way this
        PC must stop writing. None: unreadable right now; decide nothing.
        """
        is_locked, info = self.is_locked(session_dir)
        if not is_locked:
            return False
        if info.get("unreadable"):
            return None
        return info.get("locked_by") == self.hostname and info.get("process_id") == self.process_id
```

- [ ] **Step 4: Run the whole lock file** (the old tests must still pass). Same command. Expected: PASS.
- [ ] **Step 5: Commit** — `Phase 12 Bundle 2: the session lock fails closed and is created exclusively`

---

### Task 5: A PC that loses its lock stops packing (spec B3 / Q3)

**Files:**
- Modify: `packing_tool/packer_logic.py` (script edit): `stop_writing`, guard in `_do_atomic_write`
- Modify: `gui/main_window.py`: extract `_teardown_session()`, rewrite `_update_session_heartbeat()` (~line 1020), add `_on_lock_lost()`
- Test: `tests/test_packer_logic_state_persistence.py` (append), new `tests/test_session_lock_loss.py`

**Interfaces:**
- Consumes: `SessionLockManager.owns_lock` (Task 4).
- Produces: `PackerLogic.stop_writing() -> None`. `MainWindow._teardown_session() -> None` is the shared tail of `end_session()` and the lock-loss path. Task 7 adds a publisher close into it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_logic_state_persistence.py`:

```python
def test_after_stop_writing_no_state_reaches_disk(loaded_logic):
    loaded_logic.save_state()
    state_path = loaded_logic.work_dir / "packing_state.json"
    before = state_path.read_text(encoding="utf-8")

    loaded_logic.stop_writing()
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.save_state()

    assert state_path.read_text(encoding="utf-8") == before
```

Create `tests/test_session_lock_loss.py`:

```python
"""Spec B3: a PC whose lock another PC took must stop writing and leave the
session without end_session()'s writes, which would stamp the other PC's
live session as ended."""

import json
from datetime import datetime

from packing_tool.session_lock_manager import SessionLockManager


class LockLossLogic:
    def __init__(self):
        self.stopped = False
        self.cleaned = False

    def stop_writing(self):
        self.stopped = True

    def end_session_cleanup(self):
        self.cleaned = True


def test_a_lost_lock_stops_writing_and_tears_down_without_ending(main_window, tmp_path, monkeypatch):
    work_dir = tmp_path / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    now = datetime.now().astimezone().isoformat()
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": "PC-2", "user_name": "x", "lock_time": now,
                    "heartbeat": now, "process_id": 1}),
        encoding="utf-8",
    )
    logic = LockLossLogic()
    main_window.logic = logic
    main_window.current_work_dir = str(work_dir)
    main_window.current_packing_list = "DHL_Orders"

    ended, shown = [], []
    monkeypatch.setattr(main_window, "end_session", lambda: ended.append(True))
    monkeypatch.setattr(
        "gui.main_window.QMessageBox.critical",
        lambda _parent, title, text: shown.append((title, text)),
    )

    main_window._update_session_heartbeat()

    assert logic.stopped and logic.cleaned
    assert main_window.logic is None
    assert ended == []
    assert shown[0][0] == "This list is open on another PC"
    assert "PC-2 has taken over DHL_Orders." in shown[0][1]
    assert (work_dir / SessionLockManager.LOCK_FILENAME).exists()  # not ours to delete
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_packer_logic_state_persistence.py tests/test_session_lock_loss.py`
Expected: FAIL (`stop_writing` missing; heartbeat ignores the loss).

- [ ] **Step 3: Implement**

`packing_tool/packer_logic.py`: in `__init__` before the writer, add `self._writing_stopped = False`. At the top of `_do_atomic_write`:

```python
        if self._writing_stopped:
            logger.warning("State write dropped: this PC no longer holds the session lock")
            return
```

and add:

```python
    def stop_writing(self) -> None:
        """Drop every state write from now on, pending ones included.

        For a PC that lost its session lock: the new owner's packing state
        is the live one, and ours must not overwrite it (spec B3).
        """
        self._writing_stopped = True
```

`gui/main_window.py`:
1. Move everything in `end_session()` from `# CRITICAL: Stop heartbeat timer and release lock` to the final `logger.info("Session ended and all variables cleared")` into a new method `_teardown_session(self)` (docstring: "Stop the heartbeat, release the lock, drop the logic and return the UI to the session view. The tail of end_session(), and the whole of leaving a session whose lock was lost."). `end_session()` ends with `self._teardown_session()`. No behaviour change for `end_session`.
2. Replace `_update_session_heartbeat` with:

```python
    def _update_session_heartbeat(self):
        """Renew the session lock; notice if another PC has taken it (spec B3)."""
        if not (self.logic and getattr(self, "current_work_dir", None)):
            return
        work_dir = Path(self.current_work_dir)
        try:
            if self.lock_manager.update_heartbeat(work_dir):
                logger.debug("Lock heartbeat updated")
                return
            if self.lock_manager.owns_lock(work_dir) is False:
                self._on_lock_lost(work_dir)
        except Exception:
            logger.exception("Failed to update heartbeat")

    def _on_lock_lost(self, work_dir: Path):
        """Another PC holds this list's lock: stop writing, then leave it."""
        _locked, info = self.lock_manager.is_locked(work_dir)
        holder = (info or {}).get("locked_by") or "Another PC"
        list_name = getattr(self, "current_packing_list", None) or work_dir.name
        logger.error(f"Session lock lost to {holder}: {work_dir}")
        self.logic.stop_writing()
        self._teardown_session()
        QMessageBox.critical(
            self,
            "This list is open on another PC",
            f"{holder} has taken over {list_name}. This PC has stopped packing it "
            "so the two don't overwrite each other's progress. Orders packed here "
            "up to now are saved.",
        )
```

   The dialog comes *after* the teardown, so no live scanner sits under it. `_teardown_session` calls `release_lock`, which already refuses to delete a lock it doesn't own.

- [ ] **Step 4: Run tests**, then the existing end-session coverage: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_packer_logic_state_persistence.py tests/test_session_lock_loss.py tests/test_packer_mainwindow_seam.py tests/test_shell.py`. Expected: PASS.
- [ ] **Step 5: Commit** — `Phase 12 Bundle 2: a PC that loses its lock stops packing`

---

### Task 6: The Session Browser tells the truth about a session (spec D1, D2, D3 / Q5)

**Files:**
- Modify: `packing_tool/session_registry_manager.py` (script edit)
- Modify: `gui/main_window.py`: `register_session_start` call (~line 1271)
- Test: new `tests/test_session_registry.py`

**Interfaces:**
- Produces: `SessionRegistryManager.register_session_start(..., completed_orders: int = 0, skipped_orders: int = 0)` (new keyword params, keeps `started_at` of an existing entry). `SessionRegistryManager.update_session_progress(client_id: str, session_id: str, packing_list_name: str, completed_orders: int, skipped_orders: int) -> bool`. `SessionRegistryManager._locked(client_id)`, a context manager.

- [ ] **Step 1: Write the failing tests** — create `tests/test_session_registry.py`:

```python
import json
import threading
from datetime import datetime, timedelta

import pytest

from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_registry_manager import SessionRegistryManager
from shared.metadata_utils import get_current_timestamp


@pytest.fixture
def registry(profile_manager):
    return SessionRegistryManager(profile_manager)


def _entry(tmp_path, **over):
    session_path = tmp_path / "2026-09-24_1"
    work_dir = session_path / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True, exist_ok=True)
    entry = {"status": "in_progress", "last_updated": get_current_timestamp(),
             "session_path": str(session_path), "work_dir": str(work_dir)}
    entry.update(over)
    return entry, work_dir


def _lock(work_dir, age_seconds):
    beat = (datetime.now().astimezone() - timedelta(seconds=age_seconds)).isoformat()
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": "PC-1", "heartbeat": beat}), encoding="utf-8")


def test_a_live_session_reads_in_progress_from_its_work_dir_lock(registry, tmp_path):
    entry, work_dir = _entry(tmp_path)
    _lock(work_dir, age_seconds=10)
    assert registry._resolve_status(entry) == "in_progress"


def test_a_silent_lock_reads_stale(registry, tmp_path):
    entry, work_dir = _entry(tmp_path)
    _lock(work_dir, age_seconds=600)
    assert registry._resolve_status(entry) == "stale"


def test_no_lock_reads_paused(registry, tmp_path):
    entry, _work_dir = _entry(tmp_path)
    assert registry._resolve_status(entry) == "paused"


def _start(registry, **over):
    args = dict(client_id="M", session_id="2026-09-24_1", packing_list_name="DHL_Orders",
                worker_id=None, worker_name=None, pc_name="PC-1", total_orders=14,
                total_items=30, work_dir="w", session_path="s")
    args.update(over)
    return registry.register_session_start(**args)


def test_resuming_keeps_the_start_and_carries_the_progress(registry):
    _start(registry)
    first = registry.get_sessions("M")[0]["started_at"]
    _start(registry, completed_orders=9, skipped_orders=1)
    entry = registry.get_sessions("M")[0]
    assert entry["started_at"] == first
    assert (entry["completed_orders"], entry["skipped_orders"]) == (9, 1)


def test_progress_moves_a_live_entry_and_leaves_a_finished_one(registry):
    _start(registry)
    assert registry.update_session_progress("M", "2026-09-24_1", "DHL_Orders", 3, 0) is True
    assert registry.get_sessions("M")[0]["completed_orders"] == 3
    registry.register_session_complete("M", "2026-09-24_1", "DHL_Orders",
                                       {"total_orders": 14, "completed_orders": 14})
    assert registry.update_session_progress("M", "2026-09-24_1", "DHL_Orders", 1, 0) is False
    assert registry.get_sessions("M")[0]["completed_orders"] == 14


def test_concurrent_writers_do_not_drop_each_others_entries(registry):
    """Spec D3. Without the lock this loses entries often but not always;
    with it, it never does."""
    def add(prefix):
        for i in range(15):
            registry.register_available_list("M", f"{prefix}-{i}", "DHL_Orders", "list.json", "s", {})

    threads = [threading.Thread(target=add, args=(p,)) for p in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(registry.get_available_lists("M")) == 30
```

`register_available_list(client_id, session_id, packing_list_name, packing_list_path, session_path, metadata)` is the real signature. `get_sessions` / `get_available_lists` return lists of entry dicts. The conftest `profile_manager` points at a tmp server root.

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_session_registry.py`
Expected: FAIL. The status tests read `paused` for all three, because the lock is looked up in `session_path`. Resume resets `started_at` and the counts. `update_session_progress` doesn't exist. The concurrency test is likely short of 30.

- [ ] **Step 3: Implement** (script edits)

1. `_resolve_status`: `lock_dir = entry.get("work_dir") or entry.get("session_path", "")`, then `lock_file = Path(lock_dir) / ".session.lock"`. The Shopify path locks the work directory; Excel entries have no `work_dir` and fall back.
2. Add, with `from contextlib import contextmanager` and `from shared.file_lock import locked_file`:

```python
    @contextmanager
    def _locked(self, client_id: str):
        """Hold the registry's sidecar lock for one read-modify-write (spec D3).

        Every PC writes this one file; without the lock two writers each
        drop the other's change, and a dropped entry re-lists a finished
        packing list as not started.
        """
        path = self._get_registry_path(client_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_name(path.name + ".lock"), "a+") as handle, locked_file(handle):
            yield
```

3. Wrap the read-through-write body of every method that calls `write_registry` in `with self._locked(client_id):`. Those are `ensure_registry`, `register_session_start`, `register_session_complete`, `register_session_paused`, `register_available_list`, `refresh_available_lists` and the new `update_session_progress`. `write_registry` itself stays unlocked, because callers hold the lock. Check that no method holding the lock calls another method that takes it: `locked_file` is not re-entrant across two handles.
4. `register_session_start`: add `completed_orders: int = 0, skipped_orders: int = 0` keyword params. Read `existing = registry["sessions"].get(key, {})` before overwriting. Set `"started_at": existing.get("started_at") or now`, `"completed_orders": completed_orders`, `"skipped_orders": skipped_orders`.
5. Add:

```python
    def update_session_progress(
        self,
        client_id: str,
        session_id: str,
        packing_list_name: str,
        completed_orders: int,
        skipped_orders: int,
    ) -> bool:
        """Move a live entry's counts and last_updated as orders finish (spec Q5).

        A finished entry (completed/incomplete) is left alone: its counts
        came from the session summary and are final.
        """
        with self._locked(client_id):
            registry = self.read_registry(client_id)
            entry = registry["sessions"].get(self._session_key(session_id, packing_list_name))
            if entry is None or entry.get("status") in ("completed", "incomplete"):
                return False
            entry.update(
                {
                    "completed_orders": completed_orders,
                    "skipped_orders": skipped_orders,
                    "last_updated": get_current_timestamp(),
                }
            )
            return self.write_registry(client_id, registry)
```

`gui/main_window.py`: in the `register_session_start(...)` call, add
`completed_orders=len(self.logic.session_packing_state.get("completed_orders", [])),`
`skipped_orders=len(self.logic.session_packing_state.get("skipped_orders", [])),`.

- [ ] **Step 4: Run** `tests/test_session_registry.py` plus `tests/test_sessions_list_status.py tests/test_sessions_list_columns.py tests/test_session_browser_client.py`. Expected: PASS.
- [ ] **Step 5: Commit** — `Phase 12 Bundle 2: the Session Browser shows live status and resumed progress`

---

### Task 7: Packed orders reach Shopify and the browser after every order (spec E1 / Q4, D4 / Q5)

**Files:**
- Create: `packing_tool/progress_publisher.py`
- Modify: `gui/main_window.py`: create, publish and close the publisher
- Test: new `tests/test_progress_publisher.py`, append to `tests/test_packer_mainwindow_seam.py`

**Interfaces:**
- Consumes: `SessionManager.update_session_metadata(session_path, packing_list_name, status, completed_orders=None)` (exists, `packing_tool/session_manager.py:677`) and `SessionRegistryManager.update_session_progress` (Task 6).
- Produces: `ProgressPublisher(session_manager, registry_manager, client_id: str, session_path: str, packing_list_name: str, *, sync_mode: bool = False)` with `publish(completed_orders: list[str], skipped_count: int) -> None` and `close() -> None`. Also `MainWindow._progress_publisher` (init `None`), `MainWindow._publish_progress()` and `MainWindow._close_progress_publisher()`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_progress_publisher.py`:

```python
from packing_tool.progress_publisher import ProgressPublisher


class FakeSessionManager:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def update_session_metadata(self, session_path, packing_list_name, status, completed_orders=None):
        if self.fail:
            raise OSError("share unavailable")
        self.calls.append((session_path, packing_list_name, status, completed_orders))


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def update_session_progress(self, client_id, session_id, packing_list_name, completed_orders, skipped_orders):
        self.calls.append((client_id, session_id, packing_list_name, completed_orders, skipped_orders))
        return True


def _publisher(sm, reg):
    return ProgressPublisher(sm, reg, "M", "/srv/Sessions/CLIENT_M/2026-09-24_1", "DHL_Orders", sync_mode=True)


def test_publishing_tells_shopify_and_the_registry():
    sm, reg = FakeSessionManager(), FakeRegistry()
    _publisher(sm, reg).publish(["1001", "1002"], 1)
    assert sm.calls == [("/srv/Sessions/CLIENT_M/2026-09-24_1", "DHL_Orders", "in_progress", ["1001", "1002"])]
    assert reg.calls == [("M", "2026-09-24_1", "DHL_Orders", 2, 1)]


def test_a_failing_session_info_write_still_reaches_the_registry():
    sm, reg = FakeSessionManager(fail=True), FakeRegistry()
    _publisher(sm, reg).publish(["1001"], 0)
    assert reg.calls == [("M", "2026-09-24_1", "DHL_Orders", 1, 0)]


def test_close_flushes_the_last_publish_before_returning():
    sm, reg = FakeSessionManager(), FakeRegistry()
    publisher = ProgressPublisher(sm, reg, "M", "/s/2026-09-24_1", "DHL_Orders")  # real thread
    publisher.publish(["1001"], 0)
    publisher.close()
    assert sm.calls[-1][3] == ["1001"]
```

Append to `tests/test_packer_mainwindow_seam.py`:

```python
class RecordingPublisher:
    def __init__(self):
        self.published = []

    def publish(self, completed_orders, skipped_count):
        self.published.append((list(completed_orders), skipped_count))


def test_a_completed_order_is_published(window, monkeypatch):
    window.logic = StubLogic("SKU_OK")
    window._progress_publisher = RecordingPublisher()
    monkeypatch.setattr(window, "update_order_status", lambda *_: None)
    window._handle_order_completion("1001")
    assert window._progress_publisher.published == [(["1001"], 0)]


def test_a_skipped_order_is_published(window):
    logic = StubLogic("SKU_OK")
    logic.session_packing_state = {"completed_orders": [], "skipped_orders": []}
    logic.skip_order = lambda: logic.session_packing_state["skipped_orders"].append("1001")
    window.logic = logic
    window._progress_publisher = RecordingPublisher()
    window._on_skip_order()
    assert window._progress_publisher.published == [([], 1)]
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_progress_publisher.py tests/test_packer_mainwindow_seam.py`
Expected: FAIL (`ModuleNotFoundError: packing_tool.progress_publisher`; `_progress_publisher` unused).

- [ ] **Step 3: Implement** — create `packing_tool/progress_publisher.py`:

```python
"""Tell Shopify Tool and the Session Browser what a session has packed so far.

Shopify's repeat detection reads the packed-order signal from the session's
session_info.json; the Session Browser reads counts from the session
registry. Both used to hear only at End session, so a paused, overnight or
crashed list stayed invisible (Phase 12 Bundle 2, E1 / D4).

Each publish is a locked read-modify-write on the share, so it runs on
AsyncStateWriter's background thread; a later publish replaces one not yet
written, and both files take cumulative values, so the latest is enough.
Best-effort by contract, as on Shopify's side: a failure is logged, never
raised into packing.
"""

import logging
from pathlib import Path

from packing_tool.async_state_writer import AsyncStateWriter

logger = logging.getLogger(__name__)


class ProgressPublisher:
    def __init__(
        self,
        session_manager,
        registry_manager,
        client_id: str,
        session_path: str,
        packing_list_name: str,
        *,
        sync_mode: bool = False,
    ):
        self._session_manager = session_manager
        self._registry_manager = registry_manager
        self._client_id = client_id
        self._session_path = str(session_path)
        self._list_name = packing_list_name
        self._writer = AsyncStateWriter(self._write, sync_mode=sync_mode)

    def publish(self, completed_orders: list[str], skipped_count: int) -> None:
        self._writer.schedule(
            {"completed_orders": list(completed_orders), "skipped_count": int(skipped_count)}
        )

    def close(self) -> None:
        """Write whatever is pending, then stop. Call before the final End-session write."""
        self._writer.shutdown()

    def _write(self, snapshot: dict) -> None:
        completed = snapshot["completed_orders"]
        try:
            self._session_manager.update_session_metadata(
                self._session_path, self._list_name, "in_progress", completed_orders=completed
            )
        except Exception:
            logger.exception("Could not publish packed orders to session_info.json")
        try:
            if self._registry_manager is not None:
                self._registry_manager.update_session_progress(
                    self._client_id,
                    Path(self._session_path).name,
                    self._list_name,
                    len(completed),
                    snapshot["skipped_count"],
                )
        except Exception:
            logger.exception("Could not publish progress to the session registry")
```

`gui/main_window.py`:
1. `__init__`: `self._progress_publisher = None` next to `self.current_packing_list = None` (~line 259).
2. `start_shopify_packing_session`: after the `register_session_start` `try/except` block (step 9b), add:

```python
            self._progress_publisher = ProgressPublisher(
                self.session_manager,
                getattr(self, "registry_manager", None),
                client_id,
                str(session_path),
                packing_list_name,
            )
```

3. Add:

```python
    def _publish_progress(self):
        """Hand the session's packed and skipped orders to the publisher."""
        if self._progress_publisher is None or not self.logic:
            return
        state = self.logic.session_packing_state
        self._progress_publisher.publish(
            state.get("completed_orders", []), len(state.get("skipped_orders", []))
        )

    def _close_progress_publisher(self):
        if self._progress_publisher is not None:
            self._progress_publisher.close()
            self._progress_publisher = None
```

4. Call `self._publish_progress()` at the end of `_handle_order_completion` and after `self.logic.skip_order()` in `_on_skip_order`.
5. Call `self._close_progress_publisher()`:
   - in `end_session()`, immediately before `_logic_ref._state_writer.flush()`, so the publisher's last `"in_progress"` write lands before `_do_slow_writes`' final `"completed"` one;
   - at the top of `_teardown_session()` (it's idempotent, so a second close is a no-op);
   - in `_cleanup_failed_session_start()`.

- [ ] **Step 4: Run** the two test files plus `tests/test_session_metadata_orders.py`. Expected: PASS.
- [ ] **Step 5: Commit** — `Phase 12 Bundle 2: packed orders reach Shopify and the browser after every order`

---

### Task 8: Worker packing time is recorded for Shopify sessions (spec C1)

**Files:**
- Modify: `gui/main_window.py`: new module-level `_packing_start_time`, used in `end_session()` (~lines 1441-1463)
- Test: `tests/test_packer_mode_widget.py` already imports `_session_seconds` from `gui.main_window`; put this in a new `tests/test_packing_start_time.py`

**Interfaces:**
- Produces: `_packing_start_time(session_info: dict | None, logic_started_at: str | None) -> datetime | None`.

- [ ] **Step 1: Write the failing test** — `tests/test_packing_start_time.py`:

```python
from datetime import datetime

from gui.main_window import _packing_start_time


def test_session_info_wins_when_it_has_a_start():
    got = _packing_start_time({"started_at": "2026-09-24T08:00:00+03:00"}, "2026-09-24T09:00:00+03:00")
    assert got == datetime.fromisoformat("2026-09-24T08:00:00+03:00")


def test_a_shopify_session_falls_back_to_the_packing_state():
    """Spec C1: the Shopify path never writes session_info's start, so the
    duration was None and worker time accrued 0."""
    got = _packing_start_time(None, "2026-09-24T09:00:00+03:00")
    assert got == datetime.fromisoformat("2026-09-24T09:00:00+03:00")


def test_a_naive_stamp_is_read_as_local_time():
    assert _packing_start_time(None, "2026-09-24T09:00:00").tzinfo is not None


def test_nothing_usable_gives_none():
    assert _packing_start_time({"started_at": "garbage"}, None) is None
```

- [ ] **Step 2: Run** — `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_packing_start_time.py`. Expected: ImportError.
- [ ] **Step 3: Implement** — module level in `gui/main_window.py`, next to `_session_seconds`:

```python
def _packing_start_time(session_info, logic_started_at):
    """When packing started, for the duration End session records.

    session_info.json carries it on the Excel path only; the Shopify path
    never starts SessionManager, so fall back to the packing state's own
    stamp. Naive legacy stamps are read as local time.
    """
    for raw in ((session_info or {}).get("started_at"), logic_started_at):
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse packing start time: {raw!r}")
            continue
        return parsed if parsed.tzinfo else parsed.astimezone()
    return None
```

In `end_session()`, replace the `_start_time` parsing inside the `try` (the `if _session_info and "started_at" in _session_info:` block) with `_start_time = _packing_start_time(_session_info, self.logic.started_at)`. Keep the surrounding `try/except` so a `get_session_info()` failure still falls through. In that `except`, set `_start_time = _packing_start_time(None, self.logic.started_at)` instead of `None`.

- [ ] **Step 4: Run** — same command. Expected: PASS.
- [ ] **Step 5: Commit** — `Phase 12 Bundle 2: worker packing time is recorded for Shopify sessions`

---

### Task 9: Gate

- [ ] `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q`: all pass (baseline on `origin/main` is 725+).
- [ ] `ruff check .`: clean.
- [ ] `git diff origin/main --stat`: the 8 script-edited files show only this bundle's lines. If one shows hundreds of changed lines, the ruff hook reformatted it. Restore that file from `origin/main` and redo the edit by script.
- [ ] `graphify update .`
- [ ] Update `state.md` and set `next_stage: C`.
