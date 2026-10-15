# Coverage gate and the snapshot bug fixes (Packer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End Session records `incomplete` for a run that ended with orders unpacked. The dead Excel session path goes. The tests reach and keep 85% of the Python app code and 80% of each page script, enforced in CI.

**Architecture:** One rule, `PackerLogic.all_orders_packed()`, decides the status End Session writes. Python coverage is coverage.py with a `.coveragerc` that leaves out `shared/`. JS coverage is a pytest plugin, `tests/js_coverage.py`. It reads precise V8 coverage from QtWebEngine over its DevTools socket, using `QWebSocket`, so no new dependency. `scripts/coverage_check.py` runs both, and CI calls it.

**Tech Stack:** Python 3.14, PySide6 6.11 (QtWebEngine, QtWebSockets), pytest 9 with pytest-qt, coverage.py 7.16 (the one new dev dependency).

**Spec:** `docs/superpowers/specs/2026-10-15-coverage-and-snapshot-fixes-design.md`. Read the whole spec first: the plan argues from it.

## Global Constraints

- **Never edit a file under `shared/`.** A hook blocks it and CI diffs the folder.
- **Python coverage gate:** `fail_under = 85` on `source = packing_tool, gui`; `shared/` is not measured.
- **JS coverage gate:** 80, applied to each of `gui/web/app.js`, `gui/web/packer.js` and `gui/web/setup.js`, and to their total.
- **Status words** End Session writes into `session_info.json` → `packing_progress[<list>]["status"]`: `completed` when every on-list order is packed, `incomplete` otherwise. Skipped orders are not packed. Packed orders the list dropped (`completed_off_list`) are out of the count.
- **No value from `~/Desktop/Server./` or `~/Desktop/production info/` goes into git.** Fixtures copy shapes only (counts, quantities), with made-up order numbers and SKUs.
- **Git:** `/usr/bin/git`, one plain git command per Bash call (no `&&`, `;`, `$VAR` paths). Commit with `/usr/bin/git commit -F <absolute path to a message file>`. Write the message file with the Write tool, outside the repo (`$CLAUDE_JOB_DIR/tmp`). Never commit to `main`. Each commit message ends with the attribution lines your session gives you.
- **Tests:** run with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <path>`. If a hook refuses that, run the whole suite with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Write test files with Write/Edit, never with shell redirection. If `.venv` is missing: `ln -s /home/gloopy/Desktop/Projects/packing-tool/.venv .venv`. Coverage from Task 3 on: `QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/coverage_check.py` (Task 10 creates it). Before Task 10, run the JS plugin with `JS_COVERAGE=1` in front of the pytest command.
- **coverage.py is not in `.venv` until Task 10** adds it to `requirements-dev.txt`. Then install it with `.venv/bin/python -m pip install coverage~=7.16`. That `.venv` is the main checkout's, shared by symlink, and this is the only package you install.
- **Lint:** `.venv/bin/ruff check . --exclude shared` must pass before each commit.
- **QtWebEngine tests:** `runJavaScript` cannot return a JS array. Wrap every result in `JSON.stringify`; `tests/setup_web.py`'s `eval_js` does. Never mark a Chromium test skip.
- **After the last code change of each task, run `graphify update .`** (CLAUDE.md).
- **The code in this plan was written without running it.** When a test you were told to expect passing fails, find out why. Then fix the code or the test so the behaviour the spec states holds. Never weaken an assertion to get green.
- **Bugs the new tests find** (spec §7): keep the failing test, fix the code, and note it for the PR body's "Bugs found" section. Keep a running list in `$CLAUDE_JOB_DIR/tmp/bugs-found.md`: what, where, the test. If the fix would change what a packer sees or what lands on the server, and the spec does not say what is right, stop and ask the owner.
- **Dead code a coverage gap reveals:** if `rg` finds no caller outside the file and its tests, delete it instead of testing it, and list it in the bugs-found file under "Deleted, no caller".

## Review Focus

1. **A list finished across two runs** (End after order 1, resume, pack order 2, End) must be `completed`. Task 1 tests the rule over restored state.
2. **End Session with nothing packed** must write `incomplete`, not `completed`, and not crash on an empty `completed_orders`. Task 1.
3. **A packed order the list later dropped** must not count toward "every order packed". Task 1, unit test.
4. **A DevTools session that stops answering** (renderer crashed, view destroyed) must not hang the suite: `take()` gives up after 5 s and drops it. Task 3.
5. **`JS_COVERAGE=1` with DevTools unreachable** must fail the run loudly, never report 0% or pass silently. Task 3.

---

### Task 1: B1, End Session records `incomplete` for a run with orders unpacked

**Files:**
- Modify: `packing_tool/packer_logic.py`: add `all_orders_packed()` next to `packed_order_numbers()` (line ~1643); use it in `_build_state_dict` (line ~621, the `"status": ...` entry)
- Modify: `gui/main_window.py` `end_session`: compute `_list_status` next to `_packed_orders` (line ~1447); pass it at step 4 of `_do_slow_writes` (line ~1592-1603)
- Modify: `packing_tool/session_manager.py`: the `update_session_metadata` docstring's `status` line
- Create: `tests/test_end_session_status.py`
- Modify: `tests/test_packer_logic_scanning.py` (append)

**Interfaces:**
- Produces: `PackerLogic.all_orders_packed(self) -> bool`. Task 7 uses it, and so does the `ended` fixture helper `_end_in_window(...)` defined in this task's test file.

- [ ] **Step 1: Write the failing unit tests.** Append to `tests/test_packer_logic_scanning.py`:

```python
# ---------------------------------------------------------------------------
# all_orders_packed -- the one rule End Session and the state file share
# (snapshot finding 2.1)
# ---------------------------------------------------------------------------

def _pack(logic, order, skus):
    logic.start_order_packing(order)
    for sku in skus:
        logic.process_sku_scan(sku)
    logic.clear_current_order()


def test_all_orders_packed_is_false_with_none_packed(loaded_logic):
    assert loaded_logic.all_orders_packed() is False


def test_all_orders_packed_is_false_with_one_left(loaded_logic):
    _pack(loaded_logic, "ORDER-002", ["SKU-CCC"])
    assert loaded_logic.all_orders_packed() is False


def test_all_orders_packed_is_true_once_every_order_is_packed(loaded_logic):
    _pack(loaded_logic, "ORDER-001", ["SKU-AAA", "SKU-AAA", "SKU-BBB"])
    _pack(loaded_logic, "ORDER-002", ["SKU-CCC"])
    assert loaded_logic.all_orders_packed() is True


def test_a_skipped_order_is_not_packed(loaded_logic):
    _pack(loaded_logic, "ORDER-002", ["SKU-CCC"])
    loaded_logic.start_order_packing("ORDER-001")
    loaded_logic.skip_order()
    assert loaded_logic.all_orders_packed() is False


def test_an_empty_list_is_never_all_packed(packer_logic_factory, session_factory):
    _session_dir, work_dir, _list_path = session_factory(client_id="M", orders=[])
    logic = packer_logic_factory("M", work_dir)
    assert logic.all_orders_packed() is False


def test_an_order_packed_then_dropped_from_the_list_is_out_of_the_count(loaded_logic):
    """AUDIT-01-3: completed_off_list orders are out of every count."""
    _pack(loaded_logic, "ORDER-002", ["SKU-CCC"])
    state = loaded_logic.session_packing_state
    state.setdefault("completed_off_list", []).append("ORDER-OLD")
    assert loaded_logic.all_orders_packed() is False
    _pack(loaded_logic, "ORDER-001", ["SKU-AAA", "SKU-AAA", "SKU-BBB"])
    assert loaded_logic.all_orders_packed() is True


def test_a_list_finished_on_a_second_run_is_all_packed(packer_logic_factory, session_factory):
    """Review focus 1: the rule reads the restored state, not only this run's scans."""
    orders = [
        ("ORD-1", "DHL", [{"sku": "SKU-1", "quantity": 1, "product_name": "One"}]),
        ("ORD-2", "DHL", [{"sku": "SKU-2", "quantity": 1, "product_name": "Two"}]),
    ]
    _session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)
    first = packer_logic_factory("M", work_dir)
    first.load_packing_list_json(list_path)
    _pack(first, "ORD-1", ["SKU-1"])
    first.save_state()
    first.close()

    second = packer_logic_factory("M", work_dir)
    second.load_packing_list_json(list_path)
    assert second.all_orders_packed() is False
    _pack(second, "ORD-2", ["SKU-2"])
    assert second.all_orders_packed() is True
```

- [ ] **Step 2: Write the failing End Session tests.** Create `tests/test_end_session_status.py`:

```python
"""End Session records what the run reached (snapshot finding 2.1).

A run ended with orders unpacked was written `completed` into session_info.json's
packing_progress, while packing_state.json and the registry said otherwise, and
the Shopify tool showed the session as done.
"""

import json

import pytest

from packing_tool.session_manager import SessionManager

ORDERS = [
    ("ORD-1", "DHL", [{"sku": "SKU-1", "quantity": 1, "product_name": "One"}]),
    ("ORD-2", "DHL", [{"sku": "SKU-2", "quantity": 1, "product_name": "Two"}]),
]


def _end_in_window(window, session_dir, work_dir, logic, monkeypatch):
    """Point a real MainWindow at a real list, End Session, return session_info.json."""
    (session_dir / "session_info.json").write_text(
        json.dumps({"session_id": session_dir.name}), encoding="utf-8"
    )
    window.logic = logic
    window.current_client_id = "TESTCL"
    window.current_work_dir = str(work_dir)
    window.current_session_path = str(session_dir)
    window.current_packing_list = "DHL_Orders"
    window.session_manager = SessionManager(
        client_id="TESTCL",
        profile_manager=window.profile_manager,
        lock_manager=window.lock_manager,
    )
    failures = []
    monkeypatch.setattr(
        "gui.main_window.QMessageBox.critical", lambda *a, **k: failures.append(a)
    )
    window.end_session()
    assert failures == []
    return json.loads((session_dir / "session_info.json").read_text(encoding="utf-8"))


@pytest.fixture
def ended(main_window, session_factory, packer_logic_factory, monkeypatch):
    """End a two-order list after packing `packed`; return its packing_progress block."""

    def _run(packed):
        session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
        logic = packer_logic_factory("TESTCL", work_dir)
        logic.load_packing_list_json(list_path)
        for order, _courier, items in ORDERS:
            if order in packed:
                logic.start_order_packing(order)
                for item in items:
                    logic.process_sku_scan(item["sku"])
                logic.clear_current_order()
        info = _end_in_window(main_window, session_dir, work_dir, logic, monkeypatch)
        return info["packing_progress"]["DHL_Orders"]

    return _run


def test_a_run_ended_with_an_order_unpacked_is_incomplete(ended):
    block = ended(packed={"ORD-1"})
    assert block["status"] == "incomplete"
    assert block["completed_orders"] == ["ORD-1"]


def test_a_run_ended_with_nothing_packed_is_incomplete(ended):
    block = ended(packed=set())
    assert block["status"] == "incomplete"
    assert "completed_orders" not in block


def test_a_run_ended_with_every_order_packed_is_completed(ended):
    block = ended(packed={"ORD-1", "ORD-2"})
    assert block["status"] == "completed"
    assert sorted(block["completed_orders"]) == ["ORD-1", "ORD-2"]
```

- [ ] **Step 3: Run both files and confirm they fail.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_end_session_status.py tests/test_packer_logic_scanning.py`
Expected: the `all_orders_packed` tests fail with `AttributeError: 'PackerLogic' object has no attribute 'all_orders_packed'`. The two `incomplete` End tests fail with `'completed' == 'incomplete'`. The `completed` End test passes already.

- [ ] **Step 4: Implement the rule.** In `packing_tool/packer_logic.py`, directly after `packed_order_numbers`:

```python
    def all_orders_packed(self) -> bool:
        """True when the list has orders and every one of them is packed.

        Skipped orders are not packed, and an order packed and then dropped from
        the list (completed_off_list) is out of every count (AUDIT-01-3). The
        state file, End Session and the registry all mean this by "completed"
        (snapshot finding 2.1).
        """
        total = len(self.orders_data) if self.orders_data else 0
        return total > 0 and len(self.session_packing_state.get('completed_orders', [])) == total
```

In `_build_state_dict`, replace

```python
            "status": "completed" if completed_orders_count == total_orders and total_orders > 0 else "in_progress",
```

with

```python
            "status": "completed" if self.all_orders_packed() else "in_progress",
```

If `total_orders` or `completed_orders_count` is then unused in `_build_state_dict`, leave them: both still feed `"progress"`.

- [ ] **Step 5: Use it in End Session.** In `gui/main_window.py` `end_session`, directly after `_packed_orders = self.logic.packed_order_numbers()`, add:

```python
                # What session_info.json records for this list: the same rule as
                # packing_state.json and the registry (snapshot finding 2.1).
                _list_status = "completed" if self.logic.all_orders_packed() else "incomplete"
```

Replace step 4 of `_do_slow_writes`:

```python
                    # 4. Update session metadata
                    try:
                        if _cur_sess_path and _cur_pack_list:
                            _sess_mgr.update_session_metadata(
                                _cur_sess_path,
                                _cur_pack_list,
                                _list_status,
                                completed_orders=_packed_orders,
                            )
                            logger.info(f"Updated session metadata to '{_list_status}'")
                    except Exception as exc:
                        logger.warning(f"update_session_metadata failed: {exc}")
```

In `packing_tool/session_manager.py` `update_session_metadata`, change the docstring line `status: Status ('in_progress', 'completed', 'paused')` to `status: Status ('in_progress', 'paused', 'completed', 'incomplete')`.

- [ ] **Step 6: Run the two files and confirm they pass.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_end_session_status.py tests/test_packer_logic_scanning.py`
Expected: all pass. If `end_session` raises before step 4 (a missing `stats_manager` or `worker_manager` on the fixture window, or `logic.close()` called twice at teardown), fix the fixture, not `end_session`. `main_window` builds every manager in `MainWindow.__init__`.

- [ ] **Step 7: Run the whole suite.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass (1082 before this task, plus the new ones).

- [ ] **Step 8: Lint, graphify, commit.** Message: `fix: End Session records incomplete when orders are left unpacked (snapshot 2.1)`.

---

### Task 2: Delete the dead Excel session path

**Files:**
- Modify: `packing_tool/session_manager.py` (delete most of it, see spec §4)
- Modify: `packing_tool/exceptions.py` (delete three classes)
- Modify: `packing_tool/profile_manager.py` (delete `get_session_dir`, `list_clients`, `client_exists`)
- Modify: `gui/main_window.py` (`end_session`, `closeEvent`, `_teardown_session`, `_start_or_resume_from_browser`)
- Modify: `tests/test_profile_manager.py` (delete `test_get_available_clients_and_list_clients_agree` and the comment block above it, lines ~188-203)

**Interfaces:**
- Produces: `SessionManager` keeps `__init__(client_id, profile_manager, lock_manager, worker_id=None, worker_name=None)`, `get_packing_work_dir(session_path, packing_list_name) -> Path` and `update_session_metadata(session_path, packing_list_name, status, completed_orders=None)`. Nothing else.

- [ ] **Step 1: Confirm nothing calls what goes.** Run each, one per Bash call:
  - `rg -n "\.(start_session|_cleanup_session_files|is_active|get_output_dir|get_barcodes_dir|get_session_info|_start_heartbeat|_stop_heartbeat|_update_heartbeat|load_packing_list|get_session_dir|list_clients|client_exists)\(" gui packing_tool scripts main.py tests`
  - `rg -n "SessionAlreadyActiveError|SessionLockedError|StaleLockError" gui packing_tool scripts main.py tests`
  - `rg -n "session_manager\.(session_id|output_dir|packing_list_path|session_active|heartbeat_timer|end_session)" gui packing_tool tests`

  Expected hits: only inside `packing_tool/session_manager.py` and `packing_tool/exceptions.py`, plus these:
  - `gui/main_window.py`: the `is_active()` calls at ~1130, ~1353, ~1690, ~2220; `get_output_dir` ~1371; `get_barcodes_dir` ~1438; `session_manager.session_id` ~1483; `session_manager.end_session()` ~1691;
  - `tests/test_profile_manager.py:203`.

  Any other hit means stop and ask the owner (runner `ask`).

- [ ] **Step 2: Cut `SessionManager` down.** Keep the `SESSION_INFO_FILE` constant, the `json`, `logging`, `Path`, `atomic_write_json`, `locked_file` and `get_current_timestamp` imports (drop `os` if nothing left uses it), `__init__`, `get_packing_work_dir` and `update_session_metadata`. `__init__` sets only `client_id`, `profile_manager`, `lock_manager`, `worker_id` and `worker_name`, plus the log line. Rewrite the module docstring:

```python
"""
Session Manager - the Packer's writes into a Shopify session folder.

Two jobs: make the work directory a packing list is packed in
(Sessions/CLIENT_X/<session>/packing/<list>/), and record each list's packing
progress in the session's session_info.json, which the Shopify tool reads.
"""
```

The class docstring becomes `"""Work directories and packing progress for one client's Shopify sessions."""`. Keep the comment above `SESSION_INFO_FILE` true: the Shopify tool writes this file and the Packer adds `packing_progress` to it.

- [ ] **Step 3: Delete the three exceptions.** In `packing_tool/exceptions.py` delete `SessionAlreadyActiveError`, `SessionLockedError` (with `get_display_message`) and `StaleLockError` (with its methods). Keep `PackingToolError`, `PackingStateUnreadableError` and `PackingListInvalidError`. Fix the module docstring if it lists the deleted classes.

- [ ] **Step 4: Delete the three ProfileManager methods** (`get_session_dir`, `list_clients`, `client_exists`), any import only they used (`datetime` if nothing else uses it: check with `rg -n "datetime" packing_tool/profile_manager.py`), and the `list_clients` test with its comment block.

- [ ] **Step 5: `MainWindow.end_session`.** Replace the start of the method body up to and including the output-path `if/else`:

```python
        if not getattr(self, "current_work_dir", None):
            logger.warning("end_session called but no active session found")
            return

        try:
            report_dir = Path(self.current_work_dir) / "reports"
            report_dir.mkdir(exist_ok=True, parents=True)
            output_path = str(report_dir / "packing_completed.xlsx")
            logger.info(f"Saving session report to: {output_path}")
```

Replace the summary-path block:

```python
            if self.logic:
                _summary_path = os.path.join(self.current_work_dir, "session_summary.json")
                _session_type = "shopify"
```

Replace the session-id block:

```python
                _session_id = derive_session_id(getattr(self, "current_session_path", ""))
                _pl_path_str = getattr(self, "current_packing_list", "Unknown") or "Unknown"
```

Delete `_is_shopify` if nothing else reads it. The docstring becomes:

```python
        """End the open list: save its report, summary, stats and progress, then tear down.

        Report: current_work_dir/reports/packing_completed.xlsx.
        """
```

- [ ] **Step 6: The other three branches.** In `closeEvent`, delete step 4 ("End Excel session if active", the whole `if hasattr(self, "session_manager") ...` block) and renumber "5. Stop the Sessions timer" to 4. In `_teardown_session`, delete the "End Excel session if active" `if` and its comment. In `_start_or_resume_from_browser`, the check becomes:

```python
        # One list at a time: an open list is self.logic (AUDIT-02-2). The row's
        # action is disabled while one is open, so this is for a start that
        # still arrives.
        if self.logic is not None:
```

- [ ] **Step 7: Check nothing is left.**
Run: `rg -n "is_active\(|start_session|SessionLockedError|StaleLockError|SessionAlreadyActiveError|get_session_dir|list_clients|client_exists|is_excel_session|_completed\.xlsx" gui packing_tool tests`
Expected: no output. Then `.venv/bin/ruff check . --exclude shared` (catches unused imports).

- [ ] **Step 8: Run the whole suite.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass, one fewer test than after Task 1 (the deleted `list_clients` test).

- [ ] **Step 9: graphify, commit.** Message: `chore: delete the Excel session path, dead since #187`.

---

### Task 3: The JS coverage plugin

**Files:**
- Create: `tests/js_coverage.py`
- Modify: `tests/conftest.py` (top of file, plus one fixture and three hooks)
- Create: `tests/test_js_coverage.py`

**Interfaces:**
- Produces, in `tests/js_coverage.py`:
  - `ENABLED: bool`
  - `enable_remote_debugging() -> None`
  - `utf16_len(text: str) -> int`
  - `executed_units(length: int, functions: list[dict]) -> list[bool]`
  - `line_report(source: str, executed: list[bool]) -> tuple[int, list[int]]`
  - `ranges_text(numbers: list[int]) -> str`
  - `class Collector`, with `start(app)`, `take()`, `report() -> tuple[list[tuple[str, int, int, str]], float]` and `failures(threshold: float) -> list[str]`
- Environment: `JS_COVERAGE=1` turns it on; `JS_COVERAGE_FAIL_UNDER=<number>` turns on the gate. Task 10 sets both.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_js_coverage.py`:

```python
"""The pure parts of tests/js_coverage.py, on hand-written V8 results.

V8's Profiler.takePreciseCoverage gives, per script, functions with ranges
{startOffset, endOffset, count}; offsets are UTF-16 code units, and a range
nested in another is more specific than it.
"""

import pytest

import js_coverage
from js_coverage import Collector, executed_units, line_report, ranges_text, utf16_len


def _r(start, end, count):
    return {"startOffset": start, "endOffset": end, "count": count}


def test_a_nested_range_paints_over_its_parent():
    ran = executed_units(10, [{"ranges": [_r(0, 10, 1), _r(4, 6, 0)]}])
    assert ran == [True] * 4 + [False] * 2 + [True] * 4


def test_a_nested_function_listed_before_its_parent_still_nests():
    ran = executed_units(10, [{"ranges": [_r(4, 6, 0)]}, {"ranges": [_r(0, 10, 1)]}])
    assert ran == [True] * 4 + [False] * 2 + [True] * 4


def test_a_never_called_function_misses_every_line_it_spans():
    source = "x = 1;\n\nfunction f() {\n  y();\n}\n"
    start, end = source.index("function"), source.index("}") + 1
    ran = executed_units(utf16_len(source), [
        {"ranges": [_r(0, len(source), 1)]},
        {"ranges": [_r(start, end, 0)]},
    ])
    assert line_report(source, ran) == (4, [3, 4, 5])


def test_a_line_partly_run_counts_as_covered():
    source = "a(); function g() { b(); }\n"
    start = source.index("function")
    ran = executed_units(utf16_len(source), [
        {"ranges": [_r(0, len(source), 1)]},
        {"ranges": [_r(start, len(source) - 1, 0)]},
    ])
    assert line_report(source, ran) == (1, [])


def test_offsets_after_a_character_above_the_bmp_are_utf16_units():
    # The emoji is one Python character and two UTF-16 units, so ";" is at
    # unit 2. Indexing by Python characters would miss line 1.
    source = "\U0001F600;\nz();\n"
    ran = [False] * utf16_len(source)
    ran[2] = True
    assert line_report(source, ran) == (2, [2])


def test_ranges_text_compresses_runs():
    assert ranges_text([1, 2, 3, 7, 9, 10]) == "1-3, 7, 9-10"
    assert ranges_text([]) == ""


def test_two_takes_are_ored_into_one_map():
    collector = Collector()
    url = (js_coverage.WEB_DIR / "setup.js").as_uri()
    collector._fold({"url": url, "functions": [{"ranges": [_r(0, 1, 1)]}]})
    collector._fold({"url": url, "functions": [{"ranges": [_r(5, 6, 1)]}]})
    ran = collector.executed["setup.js"]
    assert ran[0] and ran[5] and not ran[3]


def test_a_script_outside_gui_web_is_not_counted():
    collector = Collector()
    url = (js_coverage.WEB_DIR.parent.parent / "shared" / "web" / "page.js").as_uri()
    collector._fold({"url": url, "functions": [{"ranges": [_r(0, 1, 1)]}]})
    collector._fold({"url": "qrc:///qtwebchannel/qwebchannel.js", "functions": []})
    assert collector.executed == {}


def test_a_file_never_loaded_reports_zero():
    rows, cover = Collector().report()
    assert {name for name, *_ in rows} == {"app.js", "packer.js", "setup.js"}
    assert cover == 0.0
    assert all(missed == lines for _name, lines, missed, _text in rows)


def test_failures_name_each_file_and_the_total_below_the_threshold():
    failures = Collector().failures(80)
    assert len(failures) == 4  # three files and the total, all at 0%


class _SilentSocket:
    def sendTextMessage(self, _text):
        pass


def test_a_page_that_never_answers_is_dropped_after_the_timeout(monkeypatch):
    """Review focus 4: a dead renderer must not hang the suite."""
    monkeypatch.setattr(js_coverage, "TAKE_TIMEOUT_S", 0.2)
    collector = Collector()
    collector._ws = _SilentSocket()
    collector._sessions = {"S1"}
    collector.take()
    assert collector._sessions == set()


def test_devtools_that_never_answers_fails_loudly(qapp):
    """Review focus 5: measuring nothing must not look like passing."""
    with pytest.raises(RuntimeError, match="never answered"):
        Collector._browser_url(qapp, "http://127.0.0.1:9/json/version", timeout_s=0.5)
```

- [ ] **Step 2: Confirm they fail.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_js_coverage.py`
Expected: collection error, `ModuleNotFoundError: No module named 'js_coverage'`.

- [ ] **Step 3: Write the plugin.** Create `tests/js_coverage.py`:

```python
"""V8 coverage of the page scripts (gui/web/*.js), read from QtWebEngine.

Inert unless JS_COVERAGE=1 (scripts/coverage_check.py sets it). Spec:
docs/superpowers/specs/2026-10-15-coverage-and-snapshot-fixes-design.md section 6.

QtWebEngine serves Chrome DevTools on QTWEBENGINE_REMOTE_DEBUGGING. The
Collector auto-attaches to every page before its scripts run, starts precise
coverage, and after each test body takes what ran and ORs it into one map per
file. The DevTools endpoint is served on the Qt main thread, so nothing here
may block it: the one HTTP read runs on a thread, and the socket traffic is
QWebSocket inside the Qt event loop.
"""

import json
import os
import socket
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

ENABLED = os.environ.get("JS_COVERAGE") == "1"
WEB_DIR = (Path(__file__).resolve().parent.parent / "gui" / "web").resolve()
TAKE_TIMEOUT_S = 5.0


def enable_remote_debugging() -> None:
    """Give QtWebEngine a free DevTools port. Must run before QtWebEngine starts."""
    if not ENABLED or os.environ.get("QTWEBENGINE_REMOTE_DEBUGGING"):
        return
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = f"127.0.0.1:{port}"


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def executed_units(length: int, functions: list[dict]) -> list[bool]:
    """Which UTF-16 units of a script ran, from one take's `functions`.

    Ranges nest, and a nested range is more specific than its parent: paint
    outer ranges first (start ascending, longest first), inner ones over them.
    """
    counts = [0] * length
    ranges = sorted(
        (r for f in functions for r in f["ranges"]),
        key=lambda r: (r["startOffset"], -r["endOffset"]),
    )
    for r in ranges:
        start, end = max(r["startOffset"], 0), min(r["endOffset"], length)
        if end > start:
            counts[start:end] = [r["count"]] * (end - start)
    return [count > 0 for count in counts]


def line_report(source: str, executed: list[bool]) -> tuple[int, list[int]]:
    """(executable lines, missed line numbers).

    A line is executable when it holds a non-whitespace character, covered
    when any of those ran. `executed` is indexed in UTF-16 units.
    """
    executable, missed, offset = 0, [], 0
    for number, line in enumerate(source.split("\n"), start=1):
        has_code = ran = False
        for ch in line:
            width = 2 if ord(ch) > 0xFFFF else 1
            if not ch.isspace():
                has_code = True
                ran = ran or any(executed[offset:offset + width])
            offset += width
        offset += 1  # the "\n"
        if has_code:
            executable += 1
            if not ran:
                missed.append(number)
    return executable, missed


def ranges_text(numbers: list[int]) -> str:
    """[1, 2, 3, 7] -> "1-3, 7", as coverage report -m prints them."""
    parts, start = [], None
    for i, n in enumerate(numbers):
        if start is None:
            start = n
        if i + 1 == len(numbers) or numbers[i + 1] != n + 1:
            parts.append(str(n) if n == start else f"{start}-{n}")
            start = None
    return ", ".join(parts)


def _spin(done, seconds: float) -> bool:
    """Run the Qt event loop until done() or the time is up; True if done."""
    from PySide6.QtWidgets import QApplication

    deadline = time.monotonic() + seconds
    while not done():
        if time.monotonic() > deadline:
            return False
        QApplication.processEvents()
        time.sleep(0.005)
    return True


class Collector:
    """The DevTools socket, the attached pages, and what ran in each page script."""

    def __init__(self):
        self._sources = {p.name: p.read_text(encoding="utf-8") for p in sorted(WEB_DIR.glob("*.js"))}
        self.executed: dict[str, list[bool]] = {}
        self._sessions: set[str] = set()
        self._wanted: set[int] = set()  # request ids whose reply is read
        self._replies: dict[int, dict] = {}
        self._next_id = 0
        self._ws = None
        self._boot_page = None

    # -- DevTools -------------------------------------------------------- #

    def start(self, app) -> None:
        """Attach to every page from now on. Raises RuntimeError when DevTools is unreachable."""
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebSockets import QWebSocket

        # The DevTools server starts only once QtWebEngine is initialised.
        self._boot_page = QWebEnginePage()
        port = os.environ["QTWEBENGINE_REMOTE_DEBUGGING"].rsplit(":", 1)[-1]
        url = self._browser_url(app, f"http://127.0.0.1:{port}/json/version")
        self._ws = QWebSocket()
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.open(QUrl(url))
        if not _spin(self._ws.isValid, 10):
            raise RuntimeError(f"the DevTools socket never opened: {url}")
        reply = self._send(
            "Target.setAutoAttach",
            {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True},
            want=True,
        )
        if not _spin(lambda: reply in self._replies, 10):
            raise RuntimeError("DevTools never answered Target.setAutoAttach")

    @staticmethod
    def _browser_url(app, url: str, timeout_s: float = 20.0) -> str:
        """The browser target's socket URL, read without blocking the Qt main thread."""
        box = []

        def fetch():
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(url, timeout=2) as response:
                        box.append(json.load(response)["webSocketDebuggerUrl"])
                    return
                except (OSError, ValueError, KeyError):
                    time.sleep(0.05)

        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()
        while thread.is_alive():
            app.processEvents()
            time.sleep(0.01)
        if not box:
            raise RuntimeError(f"QtWebEngine DevTools never answered at {url}")
        return box[0]

    def _send(
        self, method: str, params: dict | None = None, session: str | None = None, want: bool = False
    ) -> int:
        """Send one DevTools command; with want=True its reply is kept for the caller."""
        self._next_id += 1
        message = {"id": self._next_id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        if want:
            self._wanted.add(self._next_id)
        self._ws.sendTextMessage(json.dumps(message))
        return self._next_id

    def _on_message(self, text: str) -> None:
        message = json.loads(text)
        if "id" in message:
            if message["id"] in self._wanted:
                self._wanted.discard(message["id"])
                self._replies[message["id"]] = message
            return
        method, params = message.get("method"), message.get("params", {})
        if method == "Target.attachedToTarget":
            session = params["sessionId"]
            if params.get("targetInfo", {}).get("type") == "page":
                self._sessions.add(session)
                self._send("Profiler.enable", session=session)
                self._send(
                    "Profiler.startPreciseCoverage",
                    {"callCount": True, "detailed": True},
                    session,
                )
            # Paused by waitForDebuggerOnStart: without this the page never loads.
            self._send("Runtime.runIfWaitingForDebugger", session=session)
        elif method == "Target.detachedFromTarget":
            self._sessions.discard(params.get("sessionId"))

    def take(self) -> None:
        """Fold what ran since the last take, in every live page, into the file maps.

        ponytail: a view destroyed mid-test loses what ran since the last take
        (an undercount, never an overcount); take on destroy if that matters.
        """
        asked = {
            self._send("Profiler.takePreciseCoverage", session=s, want=True): s
            for s in list(self._sessions)
        }
        _spin(lambda: all(i in self._replies for i in asked), TAKE_TIMEOUT_S)
        for request_id, session in asked.items():
            self._wanted.discard(request_id)
            reply = self._replies.pop(request_id, None)
            if reply is None:
                self._sessions.discard(session)  # gone or hung: stop asking it
                continue
            for script in reply.get("result", {}).get("result", []):
                self._fold(script)

    def _fold(self, script: dict) -> None:
        url = script.get("url", "")
        if not url.startswith("file:"):
            return
        path = Path(urllib.request.url2pathname(urllib.parse.urlparse(url).path)).resolve()
        if path.parent != WEB_DIR or path.name not in self._sources:
            return
        source = self._sources[path.name]
        ran = executed_units(utf16_len(source), script.get("functions", []))
        before = self.executed.get(path.name, [False] * len(ran))
        self.executed[path.name] = [a or b for a, b in zip(before, ran)]

    # -- Report ---------------------------------------------------------- #

    def report(self) -> tuple[list[tuple[str, int, int, str]], float]:
        """Rows of (file, lines, missed, missed ranges) for every gui/web/*.js, and the total %."""
        rows, lines_total, missed_total = [], 0, 0
        for name, source in self._sources.items():
            executed = self.executed.get(name, [False] * utf16_len(source))
            lines, missed = line_report(source, executed)
            rows.append((name, lines, len(missed), ranges_text(missed)))
            lines_total += lines
            missed_total += len(missed)
        cover = 100.0 * (lines_total - missed_total) / lines_total if lines_total else 100.0
        return rows, cover

    def failures(self, threshold: float) -> list[str]:
        """One sentence per file, and for the total, under `threshold` percent."""
        rows, cover = self.report()
        out = [
            f"{name} {100.0 * (lines - missed) / lines:.1f}% < {threshold:g}%"
            for name, lines, missed, _ in rows
            if lines and 100.0 * (lines - missed) / lines < threshold
        ]
        if cover < threshold:
            out.append(f"JS total {cover:.1f}% < {threshold:g}%")
        return out

    def summary_lines(self) -> list[str]:
        rows, cover = self.report()
        width = max(len(name) for name, *_ in rows) if rows else 5
        lines = [f"{'Name':<{width}}  Lines  Miss  Cover  Missing"]
        for name, total, missed, text in rows:
            pct = 100.0 * (total - missed) / total if total else 100.0
            lines.append(f"{name:<{width}}  {total:>5}  {missed:>4}  {pct:>4.0f}%  {text}")
        lines.append(f"{'TOTAL':<{width}}  {'':>5}  {'':>4}  {cover:>4.0f}%")
        return lines
```

- [ ] **Step 4: Wire it from `tests/conftest.py`.** Directly after `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` (before `import pytest`), add:

```python
import js_coverage  # noqa: E402  (tests/ is on sys.path: conftest's own folder)

# Before anything starts QtWebEngine: the port is read once, at its start.
js_coverage.enable_remote_debugging()
```

After the `qapp` fixture, add:

```python
@pytest.fixture(scope="session", autouse=True)
def _js_coverage(qapp, request):
    """JS_COVERAGE=1: attach to every page this run opens (tests/js_coverage.py)."""
    if js_coverage.ENABLED:
        collector = js_coverage.Collector()
        collector.start(qapp)
        request.config._js_coverage = collector
    yield


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    # After the body, before fixture teardown destroys the test's views.
    try:
        return (yield)
    finally:
        collector = getattr(item.config, "_js_coverage", None)
        if collector is not None:
            collector.take()


def pytest_sessionfinish(session, exitstatus):
    collector = getattr(session.config, "_js_coverage", None)
    threshold = os.environ.get("JS_COVERAGE_FAIL_UNDER")
    if collector is None or not threshold:
        return
    session.config._js_coverage_failures = collector.failures(float(threshold))
    if session.config._js_coverage_failures and session.exitstatus == 0:
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter, config):
    collector = getattr(config, "_js_coverage", None)
    if collector is None:
        return
    terminalreporter.section("JS coverage (gui/web)")
    for line in collector.summary_lines():
        terminalreporter.write_line(line)
    for failure in getattr(config, "_js_coverage_failures", []):
        terminalreporter.write_line(f"FAIL: {failure}", red=True)
```

`pytest_sessionfinish` in conftest runs inside the terminal reporter's wrapper, so before `pytest_terminal_summary`. That is why the failures are stored on `config`.

- [ ] **Step 5: Run the unit tests.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_js_coverage.py`
Expected: all pass.

- [ ] **Step 6: Measure the baseline.**
Run: `JS_COVERAGE=1 QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: the whole suite passes and the "JS coverage (gui/web)" table prints with three rows, none at 0%. Write the three per-file numbers and the total into `$CLAUDE_JOB_DIR/tmp/bugs-found.md` under "JS baseline". If any Chromium test now times out, that's a plugin bug (most likely a page left paused because `runIfWaitingForDebugger` was never sent); fix it in the plugin. If the run is more than 50% slower than without `JS_COVERAGE`, note the two times there too.

- [ ] **Step 7: Confirm the plain run is untouched.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: passes, no JS table, about as fast as before.

- [ ] **Step 8: Lint, graphify, commit.** Message: `test: measure page-script coverage from V8 through QtWebEngine DevTools`.

---

### Task 4: MainWindow scan routing, extras and Force confirm

**Files:**
- Create: `tests/test_packer_scan_routing.py`

**Interfaces:**
- Consumes: the `main_window`, `session_factory` and `packer_logic_factory` fixtures (`tests/conftest.py`); `packing_tool.packer_logic.normalize_sku`; `PackerModeWidget.bridge.feedback` (`{"text", "role", "raw"}`, role without the `status_` prefix), `.bridge.extras` (`[{"sku", "count"}]`), `.bridge.history` (`[{"order", "status"}]`), `.bridge.sessionEnd` (dict, empty until the session ends).

- [ ] **Step 1: Write the tests.** Create `tests/test_packer_scan_routing.py`:

```python
"""MainWindow's answer to each scan outcome, over a real PackerLogic.

tests/test_packer_mainwindow_seam.py stubs the logic to pin the widget calls;
these drive a real list so the outcome and the screen are checked together.
"""

import pytest

from packing_tool.packer_logic import normalize_sku

ORDERS = [
    ("ORD-1", "DHL", [
        {"sku": "SKU-A", "quantity": 1, "product_name": "A"},
        {"sku": "SKU-B", "quantity": 1, "product_name": "B"},
    ]),
    ("ORD-2", "DHL", [{"sku": "SKU-C", "quantity": 6, "product_name": "C"}]),
    ("ORD-3", "DHL", [
        {"sku": "SKU-D", "quantity": 1, "product_name": "D"},
        {"sku": "SKU-E", "quantity": 6, "product_name": "E"},
    ]),
]


@pytest.fixture
def packing(main_window, session_factory, packer_logic_factory, monkeypatch):
    monkeypatch.setattr("gui.main_window.ORDER_CLEAR_MS", 40)
    _session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    logic.item_packed.connect(main_window._on_item_packed)
    logic.all_orders_complete.connect(main_window._on_all_orders_complete)
    main_window.logic = logic
    main_window.current_packing_list = "DHL_Orders"
    return main_window, logic


def _scan(window, *texts):
    for text in texts:
        window.on_scanner_input(text)


def _feedback(window):
    fb = window.packer_mode_widget.bridge.feedback
    return fb["text"], fb["role"]


def test_an_order_already_packed_is_named(packing):
    window, _logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-B", "ORD-1")
    assert _feedback(window) == ("Order ORD-1 is already packed", "warning")


def test_an_unknown_order_is_named(packing):
    window, _logic = packing
    _scan(window, "NOPE-9")
    assert _feedback(window) == ("No order matches NOPE-9", "danger")


def test_another_orders_barcode_mid_order_is_named_as_an_order(packing):
    window, logic = packing
    _scan(window, "ORD-1", "ORD-2")
    assert _feedback(window) == ("ORD-2 is an order. Finish or skip ORD-1 first.", "warning")
    assert logic.current_order_number == "ORD-1"


def test_an_extra_item_shows_in_the_extras_panel(packing):
    window, _logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-A")
    assert window.packer_mode_widget.bridge.extras == [{"sku": normalize_sku("SKU-A"), "count": 1}]
    assert _feedback(window) == ("Extra item scanned — keep it or remove it", "warning")


def test_the_last_item_with_an_extra_pending_holds_the_order_open(packing):
    window, logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-A", "SKU-B")
    assert logic.current_order_number == "ORD-1"
    assert "ORD-1" not in logic.session_packing_state["completed_orders"]
    assert _feedback(window) == ("Review the extra items before this order can close", "warning")


@pytest.mark.parametrize("answer", ["_on_extra_confirmed", "_on_extra_removed"])
def test_resolving_the_last_extra_completes_the_order(packing, answer):
    window, logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-A", "SKU-B")
    getattr(window, answer)(normalize_sku("SKU-A"))
    assert logic.current_order_number is None
    assert "ORD-1" in logic.session_packing_state["completed_orders"]
    assert window.packer_mode_widget.bridge.history[0] == {"order": "ORD-1", "status": "complete"}


def test_removing_an_extra_before_the_order_is_done_says_so(packing):
    window, logic = packing
    _scan(window, "ORD-1", "SKU-A", "SKU-A")
    window._on_extra_removed(normalize_sku("SKU-A"))
    assert _feedback(window) == ("Extra cleared — continue scanning", "success")
    assert logic.current_order_number == "ORD-1"


def test_force_confirm_on_the_last_line_completes_the_order(packing):
    window, logic = packing
    _scan(window, "ORD-2")
    window._on_force_confirm(0)
    assert logic.current_order_number is None
    assert "ORD-2" in logic.session_packing_state["completed_orders"]
    assert window.packer_mode_widget.bridge.history[0]["order"] == "ORD-2"


def test_force_confirm_with_an_extra_pending_asks_for_the_extras(packing):
    """Force confirm packs the last line, but an extra still waits: the order stays open."""
    window, logic = packing
    _scan(window, "ORD-3", "SKU-D", "SKU-D")  # SKU-D done, then one extra; SKU-E pending
    row_e = next(s["row"] for s in logic.current_order_state if s["normalized_sku"] == normalize_sku("SKU-E"))
    window._on_force_confirm(row_e)
    assert logic.current_order_number == "ORD-3"
    assert "ORD-3" not in logic.session_packing_state["completed_orders"]
    assert _feedback(window) == ("Review the extra items before this order can close", "warning")
    assert window.packer_mode_widget.bridge.extras == [{"sku": normalize_sku("SKU-D"), "count": 1}]


def test_the_last_order_shows_session_complete_and_the_held_reset_keeps_it(packing, qtbot):
    window, logic = packing
    widget = window.packer_mode_widget
    _scan(window, "ORD-1", "SKU-A", "SKU-B", "ORD-2")
    window._on_force_confirm(0)
    _scan(window, "ORD-3", "SKU-D")
    row_e = next(s["row"] for s in logic.current_order_state if s["normalized_sku"] == normalize_sku("SKU-E"))
    window._on_force_confirm(row_e)
    qtbot.waitUntil(lambda: bool(widget.bridge.sessionEnd), timeout=2000)
    qtbot.wait(150)  # past ORDER_CLEAR_MS: the order's reset must not wipe the panel
    assert widget.bridge.sessionEnd
```

`current_order_state` rows carry `row` and `normalized_sku` (`process_sku_scan` matches on `s['normalized_sku']`). Check `row` with `rg -n "'row':" packing_tool/packer_logic.py`.

- [ ] **Step 2: Run them.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_packer_scan_routing.py`
Expected: pass. A failure is a bug or a wrong guess in this plan. Read the code path (`MainWindow.on_scanner_input`, `_on_force_confirm`, `_on_extra_confirmed`, `_on_extra_removed`) before changing anything. Copy the exact sentence from the code when the test's sentence is wrong. When the behaviour is wrong, follow the "Bugs the new tests find" rule.

- [ ] **Step 3: Lint, graphify, commit.** Message: `test: MainWindow's answer to each scan outcome over a real list`.

---

### Task 5: `closeEvent` cleanup and `end_session` fallbacks

**Files:**
- Create: `tests/test_window_close_and_end.py`

**Interfaces:**
- Consumes: `_end_in_window` from `tests/test_end_session_status.py` (Task 1). Import it: `from test_end_session_status import ORDERS, _end_in_window`; `tests/` is on `sys.path`, as `setup_web` shows. `SessionLockManager.LOCK_FILENAME` (`".session.lock"`), `lock_manager.acquire_lock(client_id, session_dir) -> (ok, msg, info)`.

- [ ] **Step 1: Write the tests.** Create `tests/test_window_close_and_end.py`:

```python
"""What closing the window and ending a list leave on disk, including when a step fails."""

import json

from PySide6.QtGui import QCloseEvent

from packing_tool.session_lock_manager import SessionLockManager
from test_end_session_status import ORDERS, _end_in_window


def _open(window, session_factory, packer_logic_factory):
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    ok, msg, _info = window.lock_manager.acquire_lock("TESTCL", work_dir)
    assert ok, msg
    window.logic = logic
    window.current_client_id = "TESTCL"
    window.current_work_dir = str(work_dir)
    window.current_session_path = str(session_dir)
    window.current_packing_list = "DHL_Orders"
    window._start_heartbeat_timer()
    return session_dir, work_dir, logic


def test_closing_with_a_list_open_saves_it_and_frees_the_lock(
    main_window, session_factory, packer_logic_factory
):
    _session_dir, work_dir, logic = _open(main_window, session_factory, packer_logic_factory)
    logic.start_order_packing("ORD-1")
    logic.process_sku_scan("SKU-1")
    logic.clear_current_order()

    event = QCloseEvent()
    main_window.closeEvent(event)

    assert event.isAccepted()
    assert not (work_dir / SessionLockManager.LOCK_FILENAME).exists()
    assert not main_window.heartbeat_timer.isActive()
    state = json.loads((work_dir / "packing_state.json").read_text(encoding="utf-8"))
    assert [o["order_number"] for o in state["completed"]] == ["ORD-1"]


def test_a_failed_save_does_not_stop_the_lock_release_or_the_close(
    main_window, session_factory, packer_logic_factory, monkeypatch
):
    _session_dir, work_dir, logic = _open(main_window, session_factory, packer_logic_factory)

    def boom():
        raise OSError("share gone")

    monkeypatch.setattr(logic, "save_state", boom)
    event = QCloseEvent()
    main_window.closeEvent(event)

    assert event.isAccepted()
    assert not (work_dir / SessionLockManager.LOCK_FILENAME).exists()


def test_a_summary_that_cannot_be_built_still_leaves_a_minimal_one(
    main_window, session_factory, packer_logic_factory, monkeypatch
):
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)

    def boom(**_kwargs):
        raise ValueError("bad metadata")

    monkeypatch.setattr(logic, "save_session_summary", boom)
    _end_in_window(main_window, session_dir, work_dir, logic, monkeypatch)

    summary = json.loads((work_dir / "session_summary.json").read_text(encoding="utf-8"))
    assert summary["error"] == "bad metadata"
    assert summary["session_type"] == "shopify"


def test_ending_a_list_marks_its_registry_entry_from_the_summary(
    main_window, session_factory, packer_logic_factory, monkeypatch
):
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    main_window.registry_manager.register_session_start(
        client_id="TESTCL", session_id=session_dir.name, packing_list_name="DHL_Orders",
        worker_id=None, worker_name=None, pc_name="PC-1", total_orders=2, total_items=2,
        work_dir=str(work_dir), session_path=str(session_dir),
    )
    logic.start_order_packing("ORD-1")
    logic.process_sku_scan("SKU-1")
    logic.clear_current_order()

    _end_in_window(main_window, session_dir, work_dir, logic, monkeypatch)

    entries = main_window.registry_manager.get_sessions("TESTCL")
    entry = next(e for e in entries if e.get("packing_list_name") == "DHL_Orders")
    assert entry["status"] == "incomplete"
    assert entry["completed_orders"] == 1
```

Check these against the code before running:
- `_start_heartbeat_timer`'s name (`rg -n "def _start_heartbeat_timer" gui/main_window.py`).
- The key `packing_state.json` stores packed orders under (`rg -n "\"completed\"|'completed':" packing_tool/packer_logic.py`). The state's `completed` list holds dicts with `order_number`.

Fix the test to match what is there; these are facts, not behaviour.

- [ ] **Step 2: Run them.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_window_close_and_end.py`
Expected: pass. If closing leaves the lock behind after a failed save, that is a bug: `closeEvent` must release the lock whatever came before. Fix it under the bugs rule.

- [ ] **Step 3: Lint, graphify, commit.** Message: `test: closing the window and ending a list, including a failing step`.

---

### Task 6: Registry rebuild from disk, and the lock it looks for

**Files:**
- Modify: `tests/test_session_registry.py` (append)
- Modify: `packing_tool/session_registry_manager.py` `_register_from_work_dir` (expected bug, Step 3)

**Interfaces:**
- Consumes: the `registry` fixture in `tests/test_session_registry.py` (`SessionRegistryManager(profile_manager)`), `profile_manager.get_sessions_root()`, `SessionLockManager.LOCK_FILENAME`.

- [ ] **Step 1: Write the tests.** Append to `tests/test_session_registry.py`:

```python
# ---------------------------------------------------------------------------
# build_from_scan / ensure_registry: the registry rebuilt from the Sessions tree
# ---------------------------------------------------------------------------

def _session_tree(profile_manager, session_id, lists, info=True):
    """Sessions/CLIENT_M/<session_id>/ with a packing list file per name in `lists`."""
    session_dir = profile_manager.get_sessions_root() / "CLIENT_M" / session_id
    (session_dir / "packing_lists").mkdir(parents=True, exist_ok=True)
    for name in lists:
        (session_dir / "packing_lists" / f"{name}.json").write_text(
            json.dumps({"list_name": name, "courier": "DHL", "orders": [{"order_number": "1"}]}),
            encoding="utf-8",
        )
    if info:
        (session_dir / "session_info.json").write_text(
            json.dumps({"pc_name": "PC-7"}), encoding="utf-8"
        )
    return session_dir


def _work_dir(session_dir, name, state=None, summary=None):
    work_dir = session_dir / "packing" / name
    work_dir.mkdir(parents=True, exist_ok=True)
    if state is not None:
        (work_dir / "packing_state.json").write_text(json.dumps(state), encoding="utf-8")
    if summary is not None:
        (work_dir / "session_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return work_dir


STATE = {"progress": {"total_orders": 2, "completed_orders": 1, "total_items": 2}}


def test_a_list_never_started_is_rebuilt_as_available(registry, profile_manager):
    _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    rebuilt = registry.build_from_scan("M")
    assert rebuilt["sessions"] == {}
    [available] = rebuilt["available_lists"].values()
    assert available["courier"] == "DHL"
    assert available["total_orders"] == 1


def test_a_finished_list_is_rebuilt_from_its_summary(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    _work_dir(session_dir, "DHL_Orders", summary={"total_orders": 2, "completed_orders": 2})
    [entry] = registry.build_from_scan("M")["sessions"].values()
    assert entry["status"] == "completed"


def test_a_list_ended_short_is_rebuilt_incomplete(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    _work_dir(session_dir, "DHL_Orders", summary={"total_orders": 2, "completed_orders": 1})
    [entry] = registry.build_from_scan("M")["sessions"].values()
    assert entry["status"] == "incomplete"


def test_a_list_left_open_without_a_lock_is_rebuilt_paused(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    _work_dir(session_dir, "DHL_Orders", state=STATE)
    [entry] = registry.build_from_scan("M")["sessions"].values()
    assert entry["status"] == "paused"
    assert entry["completed_orders"] == 1


def test_a_list_being_packed_is_rebuilt_in_progress(registry, profile_manager):
    """MainWindow locks the work folder (packing/<list>/.session.lock), not the session folder."""
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    work_dir = _work_dir(session_dir, "DHL_Orders", state=STATE)
    _lock(work_dir, age_seconds=10)
    [entry] = registry.build_from_scan("M")["sessions"].values()
    assert entry["status"] == "in_progress"


def test_a_corrupt_session_info_does_not_stop_the_rebuild(registry, profile_manager):
    session_dir = _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"], info=False)
    (session_dir / "session_info.json").write_text("{not json", encoding="utf-8")
    _work_dir(session_dir, "DHL_Orders", state=STATE)
    _session_tree(profile_manager, "2026-10-02_1", ["DPD_Orders"])
    rebuilt = registry.build_from_scan("M")
    assert len(rebuilt["sessions"]) == 1
    assert len(rebuilt["available_lists"]) == 1


def test_ensure_registry_writes_the_rebuild_once(registry, profile_manager):
    _session_tree(profile_manager, "2026-10-01_1", ["DHL_Orders"])
    assert registry.registry_exists("M") is False
    assert registry.ensure_registry("M") is True
    assert registry.registry_exists("M") is True
    assert len(registry.get_available_lists("M")) == 1


def test_a_client_with_no_sessions_folder_rebuilds_empty(registry):
    rebuilt = registry.build_from_scan("NOBODY")
    assert rebuilt["sessions"] == {} and rebuilt["available_lists"] == {}


def test_pausing_a_finished_entry_leaves_it_finished(registry, tmp_path):
    session_dir = tmp_path / "2026-10-01_1"
    work_dir = session_dir / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    registry.register_session_start(
        client_id="M", session_id="2026-10-01_1", packing_list_name="DHL_Orders",
        worker_id=None, worker_name=None, pc_name="PC-1", total_orders=1, total_items=1,
        work_dir=str(work_dir), session_path=str(session_dir),
    )
    registry.register_session_complete(
        "M", "2026-10-01_1", "DHL_Orders", {"total_orders": 1, "completed_orders": 1}
    )
    registry.register_session_paused("M", "2026-10-01_1", "DHL_Orders")
    [entry] = registry.get_sessions("M")
    assert entry["status"] == "completed"
```

The calls match the signatures on `origin/main` at `87959fd`. `get_sessions` returns a list of entry dicts.

- [ ] **Step 2: Run them.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_registry.py`
Expected: `test_a_list_being_packed_is_rebuilt_in_progress` fails with `'paused' == 'in_progress'`; the rest pass.

- [ ] **Step 3: Fix where the rebuild looks for the lock.** In `_register_from_work_dir`, replace

```python
        lock_file = session_dir / ".session.lock"
```

with

```python
        # MainWindow locks the work folder (packing/<list>/), not the session folder.
        lock_file = work_dir / SessionLockManager.LOCK_FILENAME
```

Import `SessionLockManager` at the top of the module unless that makes an import cycle (`rg -n "^from|^import" packing_tool/session_lock_manager.py`). If it does, use the literal `".session.lock"` with the same comment. The legacy `barcodes/` branch passes `barcodes_dir` as `work_dir`, which is where the Excel path kept its lock, so it stays right. Add the bug to the bugs-found file: "Registry rebuild read a live list as paused: it looked for the lock in the session folder. `_register_from_work_dir`; `test_a_list_being_packed_is_rebuilt_in_progress`."

- [ ] **Step 4: Run them again.** Same command. Expected: all pass.

- [ ] **Step 5: Lint, graphify, commit.** Message: `fix: registry rebuild reads the list's lock from its work folder`.

---

### Task 7: Real packing shapes

**Files:**
- Modify: `tests/test_end_session_status.py` (append)

**Interfaces:**
- Consumes: `_end_in_window`, `PackerLogic.all_orders_packed()` (Task 1), `PackerLogic.force_confirm_item(row) -> (dict, str)`, `PackerLogic.completed_orders_metadata` (list of dicts with `order_number` and `items_count`).

The shapes come from the production snapshot (spec §7). Every value below is made up.

- [ ] **Step 1: Write the tests.** Append to `tests/test_end_session_status.py`:

```python
# ---------------------------------------------------------------------------
# Real shapes (snapshot, 2026-10-11): lists up to 219 orders, an order of 70
# lines and 900 units, Force confirm of 56 units. Synthetic values only.
# ---------------------------------------------------------------------------

BIG_ORDER_LINES = (
    [{"sku": "BIG-00", "quantity": 56, "product_name": "Big 0"}]
    + [{"sku": f"BIG-{i:02d}", "quantity": 12, "product_name": f"Big {i}"} for i in range(1, 69)]
    + [{"sku": "BIG-69", "quantity": 28, "product_name": "Big 69"}]
)


def test_an_order_of_70_lines_and_900_units_packs_whole(packer_logic_factory, session_factory):
    assert sum(line["quantity"] for line in BIG_ORDER_LINES) == 900
    _session_dir, work_dir, list_path = session_factory(
        client_id="TESTCL", orders=[("BIG-1", "DHL", BIG_ORDER_LINES)]
    )
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    logic.start_order_packing("BIG-1")
    for _ in range(28):  # the last line is scanned unit by unit
        logic.process_sku_scan("BIG-69")
    rows = {s["normalized_sku"]: s["row"] for s in logic.current_order_state}
    for i in range(69):  # the rest by Force confirm, BIG-00's 56 units first
        _result, status = logic.force_confirm_item(rows[normalize_sku(f"BIG-{i:02d}")])
        assert status == "FORCE_CONFIRMED"
    assert logic.all_orders_packed() is True
    [meta] = logic.completed_orders_metadata
    assert meta["items_count"] == 900


def test_a_219_order_list_ended_two_short_is_incomplete(
    main_window, session_factory, packer_logic_factory, monkeypatch
):
    orders = [
        (f"L-{n:04d}", "DHL", [{"sku": f"S-{n % 23}", "quantity": 1 + n % 2, "product_name": "P"}])
        for n in range(219)
    ]
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=orders)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    for order, _courier, items in orders[:217]:
        logic.start_order_packing(order)
        for item in items:
            for _ in range(item["quantity"]):
                logic.process_sku_scan(item["sku"], "manual" if item["quantity"] == 1 else "scanned")
        logic.clear_current_order()

    info = _end_in_window(main_window, session_dir, work_dir, logic, monkeypatch)

    block = info["packing_progress"]["DHL_Orders"]
    assert block["status"] == "incomplete"
    assert len(block["completed_orders"]) == 217
    summary = json.loads((work_dir / "session_summary.json").read_text(encoding="utf-8"))
    assert (summary["completed_orders"], summary["total_orders"]) == (217, 219)
```

Add `from packing_tool.packer_logic import normalize_sku` to the file's imports. If `force_confirm_item` refuses BIG-69 after its scans, that is right: it's already complete, and the loop stops at row 68 (`range(69)` covers BIG-00 to BIG-68).

- [ ] **Step 2: Run them.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_end_session_status.py`
Expected: pass, the 219-order test in under 15 s. If it takes longer, note the time in the bugs-found file (a packer feels that slowness too). Do not shrink the list.

- [ ] **Step 3: Lint, graphify, commit.** Message: `test: the packing shapes the production snapshot holds`.

---

### Task 8: ProfileManager and SessionLockManager error paths

**Files:**
- Modify: `tests/test_profile_manager.py` (append)
- Modify: `tests/test_session_lock_manager.py` (append)

**Interfaces:**
- Consumes: the `profile_manager` and `config_ini` fixtures; `packing_tool.profile_manager.ProfileManager`, `NetworkError` and `ProfileManagerError` (check what `rg -n "^class|import.*Error" packing_tool/profile_manager.py` names); `SessionLockManager(profile_manager)`.

- [ ] **Step 1: Write the tests.** Append to `tests/test_profile_manager.py`:

```python
# ---------------------------------------------------------------------------
# Error paths: what the Packer meets when the file server misbehaves
# ---------------------------------------------------------------------------

def test_an_unreachable_server_fails_construction_with_what_to_check(tmp_path):
    config = tmp_path / "config.ini"
    config.write_text(
        "[Network]\n"
        f"FileServerPath = {tmp_path / 'no-such-share'}\n"
        "ConnectionTimeout = 1\n",
        encoding="utf-8",
    )
    with pytest.raises(NetworkError, match="Cannot connect to file server"):
        ProfileManager(config_path=str(config))


def test_a_missing_config_file_falls_back_to_defaults():
    assert ProfileManager._load_config("/no/such/config.ini").sections() == []


def test_a_corrupt_client_config_reads_as_none(profile_manager):
    profile_manager.create_client_profile("BAD", "Bad")
    config_path = profile_manager.clients_dir / "CLIENT_BAD" / "packer_config.json"
    config_path.write_text("{not json", encoding="utf-8")
    assert profile_manager.load_client_config("BAD") is None


def test_a_corrupt_packer_config_fails_the_sku_mapping_read_loudly(profile_manager):
    profile_manager.create_client_profile("BAD", "Bad")
    config_path = profile_manager.clients_dir / "CLIENT_BAD" / "packer_config.json"
    config_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProfileManagerError, match="Could not read the SKU mapping"):
        profile_manager.load_sku_mapping("BAD", fresh=True)


def test_a_clients_folder_that_vanished_lists_no_clients(profile_manager):
    import shutil

    shutil.rmtree(profile_manager.clients_dir)
    assert profile_manager.get_available_clients() == []
```

Append to `tests/test_session_lock_manager.py` (reuse its existing fixtures; read the top of the file first):

```python
# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_an_invalid_lock_file_is_released_as_safe(lock_manager, tmp_path):
    (tmp_path / SessionLockManager.LOCK_FILENAME).write_text("{not json", encoding="utf-8")
    assert lock_manager.release_lock(tmp_path) is True
    assert not (tmp_path / SessionLockManager.LOCK_FILENAME).exists()


def test_a_heartbeat_on_a_folder_that_vanished_reports_failure(lock_manager, tmp_path, monkeypatch):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    ok, msg, _ = lock_manager.acquire_lock("M", work_dir)
    assert ok, msg
    monkeypatch.setattr("packing_tool.session_lock_manager.time.sleep", lambda _s: None)
    (work_dir / SessionLockManager.LOCK_FILENAME).unlink()
    work_dir.rmdir()
    assert lock_manager.update_heartbeat(work_dir) is False


def test_force_releasing_an_invalid_lock_removes_it(lock_manager, tmp_path):
    (tmp_path / SessionLockManager.LOCK_FILENAME).write_text("{}", encoding="utf-8")
    assert lock_manager.force_release_lock(tmp_path) is True
    assert not (tmp_path / SessionLockManager.LOCK_FILENAME).exists()


def test_stale_minutes_of_an_unreadable_heartbeat_is_zero(lock_manager):
    assert lock_manager._get_stale_minutes({}) == 0
    assert lock_manager._get_stale_minutes({"heartbeat": "not a time"}) == 0
```

Names to check before running: the fixture `test_session_lock_manager.py` calls the manager (`lock_manager` above); the packer config file name and the clients folder attribute in `ProfileManager` (`rg -n "packer_config|clients_dir =" packing_tool/profile_manager.py`); whether `update_heartbeat` on a vanished lock returns False before retrying. Fit the tests to those facts.

- [ ] **Step 2: Run them.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_profile_manager.py tests/test_session_lock_manager.py`
Expected: pass. Watch one case: a corrupt `packer_config.json` that `load_client_config` turns into `None` while `load_sku_mapping` raises. That is today's behaviour, and both are right: the config read has a fallback, and the mapping read must not pretend there are no mappings.

- [ ] **Step 3: Lint, graphify, commit.** Message: `test: profile and lock managers on a misbehaving file server`.

---

### Task 9: Page-script behaviour tests to 80% per file

**Files:**
- Modify: `tests/test_packer_bridge.py`, `tests/test_app_bridge.py`, `tests/test_app_sessions_page.py`, `tests/test_setup_page_web.py` (append to whichever owns the page the gap is in: `packer.js` → `test_packer_bridge.py`; `app.js` → `test_app_bridge.py` or `test_app_sessions_page.py`; `setup.js` → `test_setup_page_web.py`)

**Interfaces:**
- Consumes: Task 3's plugin output: the "Missing" line ranges per file. `tests/setup_web.py`: `eval_js(qtbot, view, expr)`, `until_js(qtbot, view, expr)`, `run_js(qtbot, view, code)`, `shown(view, qtbot, element_id)`. Each test file's own page fixture and helpers (`_eval`, `_until_js` in `test_packer_bridge.py`).

- [ ] **Step 1: Get the list of gaps.**
Run: `JS_COVERAGE=1 QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Copy the "JS coverage (gui/web)" table into the bugs-found file under "JS before Task 9".

- [ ] **Step 2: Group the missed lines by behaviour.** Open each JS file at its missed ranges. Name the function each range is in, and what a packer or operator does to reach it: a click, a key, a bridge state such as an empty list, an error or a question. Write that list into the bugs-found file, one line per behaviour, with the file and line range.

- [ ] **Step 3: Write one test per behaviour,** in the file that owns the page, through the page the way a person uses it. Set the state through the bridge as the Python side does (`widget.display_order(...)`, `bridge.set_question(...)`, the page's own setters), act through `run_js` (dispatch the click or key on the real element), and assert what the page draws (`eval_js` on the element's text, hidden state or class) or what the bridge receives (a slot's recorded call). The pattern, from `tests/test_packer_bridge.py`:

```python
def test_<what_the_person_does>_<what_they_see>(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.show()
    view = widget.document_view
    _until_js(qtbot, view, "document.readyState === 'complete' && !!window.bridge")
    widget.display_order(ITEMS, STATE)  # the state the behaviour needs
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 2")
    _eval(qtbot, view, "(document.querySelector('<selector>').click(), true)")
    assert _eval(qtbot, view, "document.querySelector('<selector>').textContent") == "<copy>"
```

Copy each selector and sentence from the JS and HTML, never from memory. A test only calls a page function by name when no click or key reaches it. Say why in the test's docstring. A missed range no person can reach (dead JS) falls under the dead-code rule: delete it, and list it.

- [ ] **Step 4: Re-measure after each file's batch** with the Step 1 command. Stop when every row and the total read 80% or more.

- [ ] **Step 5: Lint, graphify, commit** after each file's batch reaches 80%. Message: `test: <file> behaviour the suite never drove`.

---

### Task 10: The gate, in CI and for people

**Files:**
- Create: `.coveragerc`
- Create: `scripts/coverage_check.py`
- Modify: `requirements-dev.txt`
- Modify: `.github/workflows/build-release.yml` (step "Run tests", lines ~53-56)
- Modify: `CLAUDE.md` ("Run & Test Commands")

**Interfaces:**
- Consumes: `JS_COVERAGE` and `JS_COVERAGE_FAIL_UNDER` (Task 3).
- Produces: `python scripts/coverage_check.py [pytest args]`, which exits non-zero when either gate fails.

- [ ] **Step 1: Add the dependency and config.** Append `coverage~=7.16` to `requirements-dev.txt`. Install it into the venv: `.venv/bin/python -m pip install coverage~=7.16`. Create `.coveragerc`:

```ini
[run]
source = packing_tool, gui
# shared/ is a mirror of shopify-fulfillment-tool's; it is tested there.

[report]
fail_under = 85
show_missing = True
skip_covered = True
sort = Cover
```

- [ ] **Step 2: Write the script.** Create `scripts/coverage_check.py`:

```python
"""Run the tests under both coverage gates: Python app code and the page scripts.

    python scripts/coverage_check.py [pytest args]

Python: coverage.py over packing_tool/ and gui/, gate in .coveragerc.
Page scripts: tests/js_coverage.py, V8 coverage read from QtWebEngine, each of
gui/web/*.js and their total at JS_FAIL_UNDER percent or more.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_FAIL_UNDER = "80"


def main(argv: list[str]) -> int:
    env = {**os.environ, "JS_COVERAGE": "1", "JS_COVERAGE_FAIL_UNDER": JS_FAIL_UNDER}
    tests = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "-m", "pytest", *argv], cwd=ROOT, env=env
    )
    report = subprocess.run([sys.executable, "-m", "coverage", "report"], cwd=ROOT)
    return tests.returncode or report.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 3: CI.** In `.github/workflows/build-release.yml`, change the "Run tests" step's `run: python -m pytest` to:

```yaml
        # Both coverage gates: Python app code (.coveragerc) and the page
        # scripts (tests/js_coverage.py). A plain `python -m pytest` measures nothing.
        run: python scripts/coverage_check.py
```

Keep its `env: QT_QPA_PLATFORM: offscreen`.

- [ ] **Step 4: Docs.** In `CLAUDE.md` "Run & Test Commands", after `python -m pytest`, add:

```bash
# Run the tests under both coverage gates (what CI runs): app code >= 85%,
# each gui/web/*.js >= 80%. Extra arguments go to pytest.
python scripts/coverage_check.py
```

- [ ] **Step 5: Run the gate.**
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/coverage_check.py`
Expected: exit 0. The coverage.py report lists no file under 85% in total (`skip_covered` hides the full ones), and the JS table shows every row at 80% or more. If Python is under 85%: take the files at the top of the report (sorted by cover), write behaviour tests for their missed lines the way Tasks 4 to 8 did, re-run, and commit each batch. A file under 85% is fine on its own while the total holds. Also write `TOTAL` and the three JS numbers into the bugs-found file under "Final".

- [ ] **Step 6: Lint, graphify, commit.** Message: `ci: gate on 85% app-code and 80% page-script coverage`.

- [ ] **Step 7: Prepare the PR body sections.** The PR is Stage C's, but write its sections now into `$CLAUDE_JOB_DIR/tmp/pr-body.md`:
  - **B1 (snapshot 2.1):** what changed and the tests.
  - **B2:** "Already fixed by #199: `PackerModeWidget.display_order` stops the pending clear; pinned by `tests/test_packer_mainwindow_seam.py::test_a_finished_orders_reset_does_not_close_the_order_opened_after_it`. No code change."
  - **Deleted:** the Excel path, and anything else deleted under the dead-code rule.
  - **Bugs found:** from the bugs-found file.
  - **Coverage:** before and after, Python and JS.
  - **For Fulfilment:** `packing_progress` blocks can now say `incomplete`; `session_lifecycle.py` reads them as not done (In progress, then Stale).
