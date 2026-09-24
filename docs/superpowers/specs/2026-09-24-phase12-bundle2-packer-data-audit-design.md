# Phase 12 Bundle 2 — Packer Mode reset, data-layer audit, cross-app sync

**Todoist:** `6hcMGGQRrgcPgGXV` (parent Phase 12 `6hcCR5qQFWGcgGxV`).
**Repos:** `packing-tool` only. No `shared/` change, so no sync and no Shopify PR.
**Branch/worktree:** `worktree-phase12-bundle2`.

The bundle has three items: a bug (item 1) and two audits (items 2 and 3) that read the same
data, so they are reported together. The audit's rule came from the owner: fix defects that
are clear and small, and ask before any larger rework. Every finding below is marked
**fix** (this bundle), **decided** (the owner chose it, see *Owner decisions*) or
**follow-up** (a new Todoist task, not this bundle).

## Vocabulary

Terms added to `CONTEXT.md` in this bundle: **Packing state**, **Session registry**,
**Session lock**, **Packed-order signal**.

## Item 1 — the end-of-session message leaks into the next session

**Reproduced.** Session 1 packs orders 1001 and 1002 and ends. `reset_for_new_session()`
runs, and the order document still shows:

- the history column: `1002 complete`, `1001 complete`;
- the progress block: `2 / 2 orders`, bar at 100%.

The session-complete panel itself does clear (`sessionEnd == {}`, and `packer.js`'s
`renderSessionEnd` treats `{}` as "not over"). What leaks is the session-level state the
panel sat over.

**Root cause.** `PackerModeWidget` keeps two kinds of state: *order* state (items, rows,
extras, banner, feedback), which `clear_screen()` resets, and *session* state
(`_history`, `_orders_done`, `_orders_total`), which only `__init__` sets. The widget is
built once per app run and reused for every session, so session state carries over.
`reset_for_new_session()` (`gui/packer_mode_widget.py:438`) lowers the panel and calls
`clear_screen()`, and neither touches session state.

A second gap: nothing resets the document when a session *starts*. The one reset runs at the
end of `MainWindow.end_session()` (`gui/main_window.py:1738`), after
`self.logic.end_session_cleanup()` and `self.session_manager.end_session()`. Neither call
is guarded, so an exception in either one skips the reset.

**Fix.**
1. `reset_for_new_session()` also clears `_history`, sets `_orders_done` and
   `_orders_total` to 0, and pushes both (`bridge.set_history([])`, `_push_progress()`).
2. Both session-start paths call `reset_for_new_session()` and then
   `update_session_progress(done, total)` after the logic has loaded:
   `start_session()` (Excel) and `start_shopify_packing_session()`. `done` is
   `len(logic.session_packing_state["completed_orders"])`, so a resumed session opens on
   its real count rather than `0 / N`.

   Decided here: a resumed session's history column starts empty ("No orders yet"). The
   progress block carries the resumed count. Seeding the history from the packing state is
   possible but has no request behind it.

**Tests.** Widget level: after a finished session and `reset_for_new_session()`, `history`
is `[]` and `progress` shows `0 / 0`. Seam level (`tests/test_packer_mainwindow_seam.py`
style): after a session start, the bridge's history is empty and `orders_total` equals the
loaded order count.

## Items 2 and 3 — the audit

### A. Crash and corruption safety of the packing state

**A1. An unreadable packing state is replaced by an empty one.** — *decided (Q1)*
`PackerLogic._load_session_state()` (`packing_tool/packer_logic.py:357-366`) reads
`packing_state.json` through `get_cached_json(..., default=None)`. `JSONCache.get` returns
the default on *any* exception (`packing_tool/json_cache.py`, the `except Exception` branch),
including a transient SMB `OSError`. The loader then treats `None` as "starting fresh", and
the first scan's write replaces the file on disk. One network hiccup while a session opens
destroys that packing list's recorded progress. This is the most severe finding.

**A2. A failed state write is only logged.** — *decided (Q2)*
`_do_atomic_write()` (`packer_logic.py:607-629`) catches every exception and logs
"CRITICAL: Failed to save session state". `AsyncStateWriter` has no failure channel, and
`flush()` returns normally after a failed write. The packer keeps scanning with nothing on
disk, and nothing on screen tells them.

**A3. Writes are atomic.** Packing state, the session summary, the registry and
`session_info.json` all go through `shared.atomic_write.atomic_write_json` (temp file,
then rename, with 3 retries). No torn state file is possible from our own writes. The one
gap: there is no `fsync` before the rename. On an SMB share the client's `close()` has
already pushed the data, so a leftover risk exists only if the file *server* loses power.
**Not fixed**: it would be a `shared/` change for a server-side failure mode.

**A4. Crash recovery restores the order in progress.** The state carries `_timing` and
`_current_extras`, and the loader validates `in_progress` item by item. Nothing to fix.

### B. Session lock (two PCs, one packing list)

**B1. An unreadable lock counts as no lock.** — *decided (Q3)*
`SessionLockManager.is_locked()` (`packing_tool/session_lock_manager.py:218-261`) returns
`(False, None)` on `OSError` or `JSONDecodeError`. `update_heartbeat()` rewrites the lock
file *in place* (truncate, then dump) every 60 s, so another PC reading at that moment can
see an empty file. On Windows it can also see a sharing violation. Either way it concludes
"not locked", and `acquire_lock()` overwrites the live lock.

**B2. Acquisition is check-then-write.** — *decided (Q3)*
`acquire_lock()` checks `lock_path.exists()` and then writes with
`atomic_write_json` (rename, which overwrites). Two PCs opening the same list at once both
see no lock and both proceed. The last write wins the file, and both PCs pack.

**B3. Losing the lock goes unnoticed.** — *decided (Q3)*
When `update_heartbeat()` finds another PC's lock, it returns `False`.
`MainWindow._update_session_heartbeat()` (`gui/main_window.py:1020-1027`) ignores the return value.
After B1 or B2, both PCs keep writing the same `packing_state.json`, each overwriting the
other's progress.

### C. Metrics

**C1. Packing duration is never recorded for Shopify sessions.** — *fix*
`end_session()` takes `_start_time` from `self.session_manager.get_session_info()`
(`gui/main_window.py:1441-1463`). That reads `session_info.json` from
`session_manager.output_dir`, which only the Excel path sets. The Shopify path (the main
workflow) never starts `session_manager`, so `_start_time` is `None`. `record_packing`
then gets `duration_seconds: None` and `started_at: None`, and `update_worker_stats` gets
`duration_seconds=0`. Every worker's accumulated packing time is zero for Shopify sessions.
**Fix:** fall back to `self.logic.started_at` (the packing state's own start stamp, already
used by `generate_session_summary`) when session_info gives none.

**C2. Duration includes paused time.** — *follow-up*
`generate_session_summary()` measures `completed_at - started_at` with `started_at` taken
from the packing state. A list paused at 18:00 and resumed at 08:00 reports 14+ hours, and
orders/hour and items/hour fall with it. Measuring active time needs a per-run interval log
in the packing state. That is a format change, so it becomes a follow-up task.

**C3. "Items packed" is computed three ways.** Live progress sums scan-record units,
`end_session` sums DataFrame `Quantity` of completed orders, and the summary sums
`items_count`. They agree whenever an order completes with `packed == required`, which is
the only way an order completes. **Not a defect**: noted so the next reader doesn't
re-audit it.

### D. Session Browser vs. live packing

**D1. A live session shows as *paused*.** — *fix*
`SessionRegistryManager._resolve_status()` (`packing_tool/session_registry_manager.py:604-613`)
looks for `.session.lock` in `entry["session_path"]`, the Shopify session root. The Shopify
path locks `work_dir` (`packing/<list>/`) instead (`main_window.py:1191`). No lock ever
exists at the root, so every `in_progress` entry resolves to `paused`. *In progress* and
*stale* never appear. **Fix:** check `entry["work_dir"]` first, then fall back to
`session_path` for Excel entries.

**D2. Resuming a session erases its registry progress.** — *fix*
`register_session_start()` (`session_registry_manager.py:387-433`) replaces the whole entry,
setting `completed_orders: 0`, `skipped_orders: 0` and `started_at: now`.
`start_shopify_packing_session()` calls it on every start, including a resume from the
browser. A list that was 9/14 when it was paused reads `0 / 14 orders` once resumed, and its
Age restarts. **Fix:** when the entry exists, keep its `started_at`. Take `completed_orders`
and `skipped_orders` from the loaded packing state, passed in by the caller.

**D3. The registry has no lock.** — *fix*
`read_registry()` and `write_registry()` are an unlocked read-modify-write of one per-client
file that every PC writes. Two PCs starting or ending sessions at once can drop each other's
entry. A dropped entry is dangerous: `refresh_available_lists()` then lists that packing list
as *not started* again, so a finished list can be offered for packing a second time.
**Fix:** hold an exclusive lock on a `.lock` sidecar next to the registry file around each
read-modify-write. Use `shared.file_lock.locked_file`, the same pattern
`SessionManager.update_session_metadata()` already uses for `session_info.json`.

**D4. Live progress stays `0 / N` in the browser until the session ends.** — *decided (Q5)*
The registry's `completed_orders` and `last_updated` are written at start, pause and end
only. A live list reads `0 / 14 orders` throughout. Since `last_updated` never moves, a
session open longer than 24 h resolves as *abandoned*, because the abandoned check runs
before the lock check.

### E. Sync with Shopify Tool

**E1. Shopify learns which orders were packed only at End session.** — *decided (Q4)*
Shopify's repeat detection (`shopify_tool/packed_orders.py`) reads
`packing_progress[<list>].completed_orders` from each session's `session_info.json`.
Packing writes that list in exactly one place: the background writes inside `end_session()`
(`main_window.py:1628`). The start-time call at line 1252 passes none. So these packed orders
are invisible to Shopify:

- orders in a list that is paused or still open, e.g. overnight;
- orders in a session that crashed and was never resumed.

If Shopify runs its next analysis in that window, those orders are not flagged *Repeat* and
can ship twice. This is the gap item 3 asked about.

**E2. Shopify's reading side is correct.** It reads through
`SessionManager.list_client_sessions()`, so an index rebuild fires when a session directory's
mtime is newer than the index. Packing's `atomic_write_json` rename bumps that mtime. Both
sides take the same `session_info.json.lock` sidecar. The date comes from `started_at`, not
`updated_at` (see the comment in `packed_orders.py`). No change is needed on the Shopify side.

## Owner decisions

Asked 2026-09-24. The owner took the recommended option on all five.

**Q1 → A1: retry, then refuse.** When `packing_state.json` exists, read it directly (not
through `JSONCache`, which hides the error): 3 attempts, 0.5 s apart. If every attempt
raises, or the root is not a JSON object, raise `PackingStateUnreadableError` (new, in
`packing_tool/exceptions.py`, subclass of `PackingToolError`) from `PackerLogic.__init__`.
Raise it *before* the `AsyncStateWriter` thread is created. The file stays untouched. The
session does not open. `start_shopify_packing_session()` catches the error in its own
`except` clause, runs `_cleanup_failed_session_start()` (which releases the lock) and shows:

> **Could not read saved progress**
> The saved progress for {list} could not be read, so the list was not opened. Nothing
> was changed. Check the connection to the server and open it again.

A *missing* file still means "new session, start fresh", as it does today.

**Q2 → A2: warn and keep going.** `PackerLogic` gains a `save_failed = Signal(bool)`. It
emits on transitions only: `True` on the first failed write after a success, `False` on the
first success after a failure. `_do_atomic_write()` emits it from the writer thread. Qt
queues a cross-thread signal to the receiver's thread, so the UI slot runs on the main thread
(CLAUDE.md: no UI calls from background threads). `MainWindow` forwards it to
`PackerModeWidget.set_unsaved(bool)`. While the flag is set, `_push_feedback()` sends
role `danger` and prefixes the text with `Progress not saved — check the network`. When
there is an outcome, it is kept after ` · `, so the scan result stays readable. There is no
retry timer: every scan, cancel or extra schedules a full snapshot, so the next action is the
retry. The first success clears the flag.

**Q3 → B1, B2, B3: fix all three.**
- *B1.* `update_heartbeat()` writes with `atomic_write_json` after verifying ownership,
  instead of truncating in place, so readers never see a half-written lock.
  `is_locked()` retries an unreadable read 3 times, 0.2 s apart. If it is still unreadable,
  it returns `(True, {"unreadable": True, ...})`. `acquire_lock()` answers that with
  `(False, "The session lock could not be read. Try again in a moment.", None)`. That is
  neither the stale-lock path nor a takeover.
- *B2.* A new lock is created with `os.open(path, O_CREAT | O_EXCL | O_WRONLY)` and the
  JSON is written into that handle. `FileExistsError` means another PC won the race, and it
  is reported like an active lock. Reacquiring our own lock and the force-release path keep
  their current behaviour.
- *B3.* New `SessionLockManager.owns_lock(session_dir) -> bool | None`: `True` for our lock,
  `False` for another owner's lock or a missing file, `None` for an unreadable one. When
  `update_heartbeat()` returns `False`, `MainWindow._update_session_heartbeat()` asks
  `owns_lock()`. `False` means the lock is lost:
  `PackerLogic.stop_writing()` (a flag `_do_atomic_write()` checks first, so neither a
  pending nor a later write reaches disk), stop the heartbeat, show a critical dialog, and
  tear the session down *without* `end_session()`'s writes. Those writes would stamp
  another PC's live session as ended. The teardown is `end_session()`'s existing cleanup
  tail (lines 1697–1742), extracted into `_teardown_session()` so both callers share it.
  Dialog copy:

  > **This list is open on another PC**
  > {locked_by} has taken over {list}. This PC has stopped packing it so the two don't
  > overwrite each other's progress. Orders packed here up to now are saved.

  The legacy Excel path runs its own heartbeat in `SessionManager` and is not changed.

**Q4 → E1: publish after every order.** New module `packing_tool/progress_publisher.py`
with class `ProgressPublisher`. Its interface is `publish(completed_orders: list[str],
skipped_count: int)` and `close()`. It is built at session start from the session manager,
the registry manager, client id, session path and packing list name, and it owns an
`AsyncStateWriter`, so publishing is non-blocking and the latest snapshot wins. Its write
calls `SessionManager.update_session_metadata(path, list, "in_progress",
completed_orders=...)`, which already takes Shopify's `session_info.json.lock` and merges,
and the new registry method from Q5. Failures are logged; this signal is best-effort, as it
is on Shopify's side. `MainWindow` publishes from `_handle_order_completion()` and
`_on_skip_order()`. `end_session()` calls `close()` (which flushes) *before* its own final
`"completed"` write, so the final write lands last. `_teardown_session()` also closes it.
Shopify sessions only: the Excel path has no `session_info.json` packing block.

**Q5 → D4: registry progress on each order.** New
`SessionRegistryManager.update_session_progress(client_id, session_id, list_name,
completed_orders: int, skipped_orders: int)`. It sets both counts and `last_updated` when
the entry exists and is not `completed`/`incomplete`, and does nothing otherwise. It is
called from `ProgressPublisher`'s write. A moving `last_updated` also stops a live session
from resolving as *abandoned* after 24 h.

## Out of scope

- `fsync` in `shared/atomic_write.py` (A3).
- Active-time duration (C2): follow-up task.
- Seeding the Packer Mode history column on resume.
- Lock-loss detection on the legacy Excel path (its heartbeat lives in `SessionManager`).
