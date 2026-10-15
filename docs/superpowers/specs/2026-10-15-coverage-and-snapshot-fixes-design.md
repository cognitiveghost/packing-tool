# Coverage gate and the snapshot bug fixes (Packer)

Task: "Chore: Coverage tests + snapshot bug fixes (Packer)" (dev-runner run 85, branch
`dr/30-chore-coverage-tests-snapshot-bug-fixes`). No mockup: nothing on screen changes.

## 1. What the task asked, and what is true

**A. Coverage.** At least 80% of the project under test, UI and backend, and fix the bugs the new
tests find.

Measured on `origin/main` at `87959fd` (2026-10-15, statement coverage, 1082 tests passing):

| Scope | Statements | Missed | Cover |
|---|---|---|---|
| `packing_tool/` + `gui/` (app code) | 5927 | 659 | 89% |
| `shared/` (mirror; its tests live in shopify-fulfillment-tool) | 1799 | 648 | 64% |

Weakest app files: `packing_tool/session_manager.py` 33%, `packing_tool/exceptions.py` 48%,
`packing_tool/session_registry_manager.py` 72%, `packing_tool/profile_manager.py` 81%,
`packing_tool/session_lock_manager.py` 83%, `gui/main_window.py` 84%. Every other file is at 85%
or more. The page scripts `gui/web/app.js`, `packer.js` and `setup.js` (about 70 KB) run in a real
Chromium in about 140 tests but are not measured at all.

Most of `session_manager.py`'s miss is dead code (section 4).

**B1. Snapshot finding 2.1: an ended run with orders unpacked is recorded as `completed`.** Still
present. `MainWindow.end_session` calls `SessionManager.update_session_metadata(list, "completed",
…)` whatever the counts. `packing_state.json` and the registry already work the status out from the
counts, so the three files disagree (LIDA `2026-10-02_1`: state `in_progress`, registry
`incomplete`, `session_info.json` `completed`). In the snapshot, 110 of 677 packing runs ended with
orders unpacked.

**B2. Screen cleared under an open order.** Already fixed by UI refresh phase 2 (#199):
`PackerModeWidget.display_order` stops the clear timer that `clear_screen_later` (called by
`MainWindow._handle_order_completion`) started, and `clear_screen` stops it too.
`tests/test_packer_mainwindow_seam.py::test_a_finished_orders_reset_does_not_close_the_order_opened_after_it`
pins it. Phases 3 to 5 did not touch that path. **No code change**; the PR says so and the backlog
item closes.

## 2. Owner decisions (2026-10-15)

| Question | Answer |
|---|---|
| How is coverage kept? | A CI gate at **85%** on app code; `shared/` is left out. |
| The dead Excel session path | **Delete it.** |
| Measure the page JS? | **Yes, V8 coverage**, collected from QtWebEngine through DevTools. |
| B1: the status for a run ended with orders unpacked | **`incomplete`** |

## 3. B1: the status End Session records

One rule, in one place. New method on `PackerLogic`:

```python
def all_orders_packed(self) -> bool:
    """True when the list has orders and every one of them is packed.

    Skipped orders are not packed, and an order packed and then dropped from
    the list (completed_off_list) is out of every count (AUDIT-01-3).
    """
    total = len(self.orders_data) if self.orders_data else 0
    return total > 0 and len(self.session_packing_state.get('completed_orders', [])) == total
```

- `PackerLogic._build_state_dict` uses it for the `status` it writes into `packing_state.json`
  (`"completed" if self.all_orders_packed() else "in_progress"`). Same result as today; one
  rule, not two copies.
- `MainWindow.end_session` works the status out on the main thread, next to `_packed_orders`:
  `_list_status = "completed" if self.logic.all_orders_packed() else "incomplete"`. Step 4 of
  `_do_slow_writes` passes `_list_status` to `update_session_metadata` and logs it
  (`f"Updated session metadata to '{_list_status}'"`).
- The registry's rule in `register_session_complete` (summary `completed_orders ==
  total_orders`) gives the same answer, since the summary's `completed_orders` and `total_orders`
  are the same two counts. It is left as it is.
- `update_session_metadata`'s docstring lists `incomplete` as a status it can be given.

**What Shopify does with it today.** `shopify_tool/session_lifecycle.py` counts a list as packed
only when its block says `completed`, so an `incomplete` block shows the session as In progress,
then Stale after 7 days, until the Shopify coverage task teaches it the word. That is the true
state: the list is not done. `packed_orders.py` reads `completed_orders` whatever the status, so
repeat detection does not change. A list resumed after an `incomplete` End is written
`in_progress` again at open, as today.

**Tests (written first, both fail today):** a real `MainWindow` over a real session folder from
`session_factory`, with a `session_info.json` the test writes, with
`current_work_dir`/`current_session_path`/`current_packing_list` set. Pack one of two orders, call
`end_session()`, wait for the background writes, and read
`session_info.json["packing_progress"]["DHL_Orders"]["status"]`: `incomplete`. Pack both, End:
`completed`. Plus unit tests of `all_orders_packed()`: empty list, none packed, all packed, all
packed but one skipped, an off-list packed order not counted.

## 4. Delete the dead Excel session path

PR #187 removed `MainWindow.start_session`, the only caller of `SessionManager.start_session`.
Since then `SessionManager.session_id` is never set, `is_active()` is always False, and every
branch behind it is dead.

Delete from `packing_tool/session_manager.py`: `start_session`, `end_session`,
`_cleanup_session_files`, `is_active`, `get_output_dir`, `get_barcodes_dir`, `get_session_info`,
`_start_heartbeat`, `_stop_heartbeat`, `_update_heartbeat`, `load_packing_list`, the attributes
only they use (`session_id`, `session_active`, `output_dir`, `packing_list_path`,
`heartbeat_timer`), the imports only they use, and the module and class docstring text describing them.
`SessionManager` keeps `__init__`, `get_packing_work_dir` and `update_session_metadata`.

Delete from `packing_tool/profile_manager.py`: `get_session_dir` (only `start_session` called
it), `list_clients` and `client_exists` (no caller outside tests; `get_available_clients` is the
one in use). Delete the test of `list_clients` with it.

Delete from `packing_tool/exceptions.py`: `SessionAlreadyActiveError`, `SessionLockedError` and
`StaleLockError` (only `start_session` raised them). `PackingToolError` stays as the base of
`PackingStateUnreadableError`.

Delete from `gui/main_window.py`:
- `end_session`: the `is_excel_session` check (the guard becomes `if not self.current_work_dir`),
  the `else` branch that names the legacy `_completed.xlsx` report, the `_barcodes_dir` summary
  path and the `excel` `_session_type`, and `_session_id = self.session_manager.session_id`. Every
  End is a Shopify session: report `reports/packing_completed.xlsx`, summary
  `current_work_dir/session_summary.json`, `_session_type = "shopify"`.
- `closeEvent`: step 4, "End Excel session if active". Renumber the step comments.
- `_teardown_session`: "End Excel session if active".
- `_start_or_resume_from_browser`: the `is_active()` half of the `self.logic is not None or (...)`
  check, and the comment's mention of it.
- Any other `is_active()` call `rg "is_active\(" gui packing_tool` finds on `session_manager`.

Before deleting, `rg` each name across `gui/ packing_tool/ tests/ scripts/ main.py`; a caller this
spec did not list means stop and ask. The registry's stored `session_type` value `excel` stays
readable: old entries keep it.

## 5. Python coverage gate

- `requirements-dev.txt`: add `coverage~=7.16`.
- New `.coveragerc` at the repo root:

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

- New `scripts/coverage_check.py`: the one command that measures both, for CI and for people.
  It runs `python -m coverage run -m pytest` with `JS_COVERAGE=1` and `JS_COVERAGE_FAIL_UNDER=80`
  (section 6) in the environment, then `python -m coverage report`, and exits non-zero if either
  fails. Extra arguments go through to pytest.
- CI (`.github/workflows/build-release.yml`, step "Run tests"): `run: python scripts/coverage_check.py`
  in place of `python -m pytest`, same `QT_QPA_PLATFORM: offscreen`.
- A plain `python -m pytest` measures nothing and is as fast as today.

## 6. JS coverage from V8

Settled by a throwaway probe on 2026-10-15 (PySide6 6.11.2): with QtWebEngine remote debugging
on, a `QWebSocket` on the browser target can auto-attach to every page **before its scripts run**
and read precise per-function and per-block counts. On a bare Packer Mode page, `packer.js`
reported 42 functions, 19 never called. Two findings shape the design:

1. The DevTools server starts only once QtWebEngine is initialised, so the plugin creates a
   throwaway `QWebEnginePage` first.
2. The DevTools HTTP endpoint is served on the Qt main thread. A blocking `urllib` call from the
   main thread deadlocks; fetch `/json/version` on a worker thread while the main thread spins
   `processEvents()`. All later traffic goes over the `QWebSocket`, inside the Qt event loop.

New module `tests/js_coverage.py`, wired from `tests/conftest.py`. Inert unless `JS_COVERAGE=1`.

- **Before QtWebEngine starts** (top of `conftest.py`, next to `QT_QPA_PLATFORM`): if enabled,
  pick a free port (bind `127.0.0.1:0`, read it, close) and set
  `QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:<port>`.
- **Session fixture** (autouse, after `qapp`): create the throwaway page, read the browser
  `webSocketDebuggerUrl` from `http://127.0.0.1:<port>/json/version` (worker thread, 20 s cap),
  open the `QWebSocket`, send `Target.setAutoAttach {autoAttach: true, waitForDebuggerOnStart:
  true, flatten: true}` and wait for its reply. Any failure here fails the run with the reason.
  Do not skip: measuring nothing must not look like passing.
- **On `Target.attachedToTarget`:** for a `page` target, send `Profiler.enable` and
  `Profiler.startPreciseCoverage {callCount: true, detailed: true}` on its session. For every
  target, send `Runtime.runIfWaitingForDebugger`, or the page never loads. On
  `Target.detachedFromTarget`, forget the session.
- **After each test body** (`pytest_runtest_call` hookwrapper, after `yield`, so before fixture
  teardown destroys the views): send `Profiler.takePreciseCoverage` to every live session and spin
  the event loop until every reply is in (5 s cap; a session that does not answer is dropped).
  For each script whose URL is `file://…/gui/web/<name>.js`, fold the result into that file's
  executed-character map (below). `takePreciseCoverage` resets the counters, so each take holds
  only what ran since the last.
- **Folding one take into a file:** gather every range of every function, sort by
  `(startOffset, -endOffset)` so outer ranges come before the ranges nested in them, and paint
  them in that order onto a count array of the file's source (read from disk as UTF-8): later,
  more specific ranges overwrite. Then OR `count > 0` into the file's lifetime boolean map. V8
  offsets are **UTF-16 code units**, and `app.js` and `packer.js` hold non-ASCII text (typographic
  quotes, ellipses), so the arrays are indexed in UTF-16 units: the array length is
  `len(source.encode("utf-16-le")) // 2`, and the line count walks the source a character at a
  time, advancing the offset by 2 for a character above U+FFFF and by 1 otherwise.
- **Lines:** a line is *executable* when it holds a non-whitespace character, and *covered* when
  any of its non-whitespace characters ran. A file's cover is covered over executable lines.
- **Report** (`pytest_terminal_summary`): a table in the shape of `coverage report -m`, one row
  per `gui/web/*.js` file plus a total, with missed line ranges (`12-18, 40`). A file never loaded
  is reported at 0%, not left out: the file list is `gui/web/*.js` on disk.
- **Gate** (`pytest_sessionfinish`): when `JS_COVERAGE_FAIL_UNDER` is set and the total or any
  one file is below it, set `session.exitstatus = 1`; the summary says which. Without the variable the plugin only reports, so
  a partial local run with `JS_COVERAGE=1` does not fail on the number.
- `shared/web/page.js` and `qrc:///qtwebchannel/qwebchannel.js` are not counted: `page.js` is
  Fulfilment's to test, the other is Qt's.

Known ceilings, marked `ponytail:` in the code: a view destroyed in the middle of a test body
loses what ran since the last take (a slight undercount, never an overcount); line coverage over
characters, not branches.

The plugin itself gets one test file, `tests/test_js_coverage.py`, for the pure parts: the fold
(nested ranges, a later take ORed into an earlier one, a never-called function, offsets after a
non-ASCII character) and the line count (blank lines out, a line partly run counts as covered), on
hand-written V8 results.

## 7. The coverage tests

Targets come from the misses on `origin/main`. Each test drives real behaviour through the seam
the area already uses (`main_window` / `main_window_with_list` and `StubLogic` in
`tests/test_packer_mainwindow_seam.py`, real `PackerLogic` from `packer_logic_factory`, real
files under `tmp_path`, real Chromium through `tests/setup_web.py`'s helpers). No test asserts a
log line or a private counter where an outcome on screen or on disk can be read instead.

- **`MainWindow` scan routing** (`on_scanner_input`): an already-packed order barcode (`Order …
  is already packed`, orange); an unknown order (`No match…`, red); an order barcode while another
  order is open (`… is an order. Finish or skip … first.`); an extra item (`SKU_EXTRA`: the extras
  panel shows it); the last item while extras are pending (`ORDER_COMPLETE_WITH_EXTRAS`: the order
  stays open, the warning shows).
- **Extras and Force confirm completing an order:** Keep and Remove on the last pending extra
  complete the order (history gets it, the screen holds then clears); `EXTRA_CLEARED` shows its
  sentence; Force confirm on the last line completes the order.
- **Session complete:** packing the last order shows the session-complete panel, and a
  `clear_screen` scheduled by that order does not wipe it.
- **`closeEvent` cleanup:** with a list open, closing saves the state to disk, releases the lock
  file and stops the heartbeat; a failure in one step (monkeypatched to raise) does not stop the
  next steps or the close.
- **`end_session` fallbacks:** `save_session_summary` raising writes the minimal summary with its
  `error`; the registry entry is marked complete from the summary on disk.
- **`SessionRegistryManager`:** `build_from_scan` / `ensure_registry` rebuild the registry from a
  Sessions tree on disk (a finished list, an unfinished list, an available list, a corrupt
  `session_info.json`); `register_session_paused` leaves a finished entry alone. A list whose
  work folder holds a lock is rebuilt `in_progress`: today `_register_from_work_dir` looks for
  `.session.lock` in the session folder, but `MainWindow` locks the work folder
  (`packing/<list>/.session.lock`), so a live list is rebuilt `paused`. Expected to be the first
  bug the new tests find; the fix reads the lock from `work_dir`.
- **`ProfileManager` and `SessionLockManager`:** the missed error paths, e.g. an unreadable or
  corrupt config or lock file, a server path that has gone away.
- **The page JS:** behaviour tests through the existing real-Chromium tests
  (`test_packer_bridge.py`, `test_app_bridge.py`, `test_app_sessions_page.py`,
  `test_setup_page_web.py`), driving the page as a packer would (bridge state in, clicks and keys
  through `run_js`) and reading what it draws, until each of `app.js`, `packer.js` and `setup.js`
  is at 80% or more and the total is too.

**Real shapes, synthetic data.** The snapshot (`~/Desktop/Server./snapshot.duckdb`) gives the
shapes fixtures copy; no value from it goes into git. Lists run up to 219 orders (median 18); an
order has up to 70 lines and 900 units; Force confirm covers up to 56 units; 1896 lines were
manual confirms; 10 of 677 runs skipped orders. One fixture builds a list in each of those shapes
from made-up order numbers and SKUs.

**Bugs the new tests find.** A new test that fails on real behaviour is a bug: keep the failing
test, fix the code, and add a line to the PR body's "Bugs found" section (what, where, the test).
When the fix would change what a packer sees or what lands on the server, and this spec does not
say what is right, stop and ask the owner.

## 8. Done when

- `python scripts/coverage_check.py` passes locally and in CI: app code at 85% or more, every
  `gui/web/*.js` file and the JS total at 80% or more.
- B1's two tests pass; `session_info.json` says `incomplete` for a run ended with orders unpacked.
- The Excel path is gone and `rg "is_active\(|start_session|SessionLockedError|StaleLockError|SessionAlreadyActiveError|get_session_dir|list_clients|client_exists" gui packing_tool tests`
  finds nothing.
- The PR body states B2 was already fixed by #199, with the test that pins it, and lists the bugs
  found.
- `ruff check . --exclude shared` passes; `graphify update .` has been run.
