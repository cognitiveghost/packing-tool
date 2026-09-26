# Audit 02 — Several PCs, the file server, and the whole-app sweep

Scope: `packing_tool/session_lock_manager.py`, `session_registry_manager.py`,
`profile_manager.py` (SKU mapping), `worker_manager.py`,
`progress_publisher.py`, `shared/atomic_write.py`, `shared/file_lock.py`,
`shared/stats_manager.py`, and the Packer Mode, browser and session paths
of `gui/`. Proof tests: `tests/audit/test_02_concurrency_sweep.py`. Audited
against `origin/main` at `78c3a41`.

## 1. Verdict

**The Phase 12 lock and registry fixes hold, but four shared files are still
written without coordination, and two guards have holes.** Two PCs racing
for a free list get exactly one lock, and registry writers no longer drop each
other's entries (both pinned by passing tests). What remains:

- the **stale-lock prompt** can delete a live lock (AUDIT-02-1), and a
  **second list** can be opened on top of a running one (AUDIT-02-2): both let
  two writers share one packing state;
- **SKU mappings** are saved as a full replacement built from a stale view,
  so one PC erases what another just mapped (AUDIT-02-3);
- **worker stats** and a **failed registry read** lose data under
  concurrency or a network blip (AUDIT-02-4, -5).

On speed: every file write is atomic and small (a 117-order state is 105 KB).
The UI thread, however, rebuilds the whole order tree on every scan, which
takes 128 ms on the largest real list (AUDIT-02-7).

## 2. Findings

| id | severity | summary | where | proof test | status |
|---|---|---|---|---|---|
| AUDIT-02-1 | high | "Force-release stale lock?" deletes whatever lock exists when the user answers, even a fresh one | `gui/main_window.py:2481`, `session_lock_manager.py:408` | `test_force_release_after_the_prompt_does_not_steal_a_fresh_lock` | confirmed |
| AUDIT-02-2 | high | A second list can be opened while one is packing; the first lock is orphaned and its writer leaks | `gui/main_window.py:2330` | `test_opening_a_second_list_is_refused_while_one_is_packing` | confirmed |
| AUDIT-02-3 | high | SKU mapping saves replace the whole table from a view up to 60 s old (or from when the dialog opened); a torn read saves an empty table | `gui/main_window.py:2096`, `profile_manager.py:464`, `:516`; `gui/sku_mapping_dialog.py:307` | `test_a_mapping_saved_on_one_pc_survives_a_save_on_another`, `test_an_unreadable_mapping_file_is_not_saved_over` | confirmed |
| AUDIT-02-4 | medium | `workers.json` is an unlocked read-modify-write; two End sessions together lose one's counts, two new workers can get one id | `worker_manager.py:195`, `:270` | `test_two_pcs_ending_sessions_together_both_count` | confirmed |
| AUDIT-02-5 | medium | `read_registry` returns an empty registry on any read error, and the locked writers save it | `session_registry_manager.py:110` | `test_a_failed_registry_read_does_not_wipe_it` | confirmed |
| AUDIT-02-6 | medium | The client picker stays live during a session; stats, registry and SKU mappings then go to the other client | `gui/main_window.py:815` | `test_the_client_cannot_change_under_a_running_list` | confirmed |
| AUDIT-02-7 | medium | Every order open and SKU scan rebuilds the whole order tree (hidden while packing): 128 ms at 117 orders, 375 ms at 400 | `gui/main_window.py:1969`, `:1988` | `test_a_scan_does_not_rebuild_the_order_tree` | confirmed |
| AUDIT-02-8 | medium | Heartbeat (every 60 s) and the order-complete checkpoint do share I/O on the UI thread; a share outage freezes the packing screen | `gui/main_window.py:1047`, `packer_logic.py:668` | — (design) | observed |
| AUDIT-02-9 | medium | The row's **Confirm** button packs a unit without a scan and records it as `scanned` | `gui/packer_mode_widget.py:242`, `packer_bridge.py:76` | `test_a_confirm_click_is_not_recorded_as_a_scan` | confirmed |
| AUDIT-02-10 | medium | History shows an order "Complete" the moment it is opened; a skip then adds a second entry | `gui/main_window.py:1886`, `packer_mode_widget.py:505` | `test_an_opened_order_is_not_shown_as_complete`, `test_a_skipped_order_appears_once_in_history` | confirmed |
| AUDIT-02-11 | low | Scanning the next order's barcode mid-order reads "Unknown SKU", counts as an unknown scan and offers Map SKU | `packer_logic.py:1194` | `test_scanning_the_next_orders_barcode_is_not_an_unknown_sku` | confirmed |
| AUDIT-02-12 | low | The state "snapshot" handed to the writer thread aliases live lists; a write can serialise mid-change | `packer_logic.py:555` | `test_the_state_snapshot_does_not_change_after_it_is_taken` | confirmed |
| AUDIT-02-13 | low | "Order ##11019922 is already packed" | `gui/main_window.py:1906` | `test_already_packed_message_has_one_hash` | confirmed |
| AUDIT-02-14 | cleanup | The legacy Excel path is unreachable: `start_session`, `_handle_stale_lock_error`, `_handle_session_locked_error`, `restore_session_dialog.py`, `ProfileManager.get_incomplete_sessions` | `gui/main_window.py:853-980`, `:2490-2611` | — | observed |

## 3. Findings in detail

### AUDIT-02-1 — The stale-lock prompt can delete a live lock (high)

`_acquire_lock_with_stale_prompt` shows a modal question, then calls
`force_release_lock`, which unlinks the lock file unconditionally. While the
question is open, the original PC can come back and renew its heartbeat, or
a third PC can take the lock. Answering **Yes** then deletes that live lock
and creates ours. Two PCs now write one `packing_state.json` until the other
PC's next heartbeat (≤ 60 s) tears it down. Orders it finishes in that window
are overwritten by our next write.

**Fix direction.** `force_release_lock(session_dir, expected)` re-reads the
lock and deletes it only if it is still the same stale lock (same owner, pid
and heartbeat).

### AUDIT-02-2 — A second list on top of a running one (high)

`_start_or_resume_from_browser` refuses only when
`session_manager.is_active()`, which is true only on the legacy Excel path.
With a Shopify list open, the browser starts another one. The new start
overwrites `current_work_dir`, `logic` and the publisher without releasing
the first lock, closing the first logic's writer thread, or publishing its
progress. The first list turns *stale* in the browser, and its
`packing_state.json` is written by an orphaned thread.

### AUDIT-02-3 — SKU mappings lost across PCs (high)

`save_sku_mapping` replaces the table ("callers pass the full desired
mapping"). Callers build that mapping from `load_sku_mapping`, which serves a
per-PC cache for 60 s. The SKU mapping dialog uses the table it loaded when
it opened. So a mapping another PC saved in that window is erased.

Worse, on Windows the save rewrites `packer_config.json` in place
(truncate, then write), and `load_sku_mapping` reads without the lock. A
read that lands mid-rewrite gets an empty table, caches it for 60 s, and
the next map on that PC saves a table containing one entry. The test shows
50 mappings reduced to 1.

**Fix direction.** An `update_sku_mapping(client, add=…, remove=…)` applied to
the fresh file under the lock; the dialog sends its diff; the writer uses
temp-file + rename; a read error is an error, not `{}`.

### AUDIT-02-4 — workers.json (medium)

`update_worker_stats` and `create_worker` read, change and atomically write
`Workers/workers.json` with no lock. Two End sessions at the same moment keep
only the last writer's counts. Two PCs adding a worker at once both compute
`worker_00N`. **Fix:** the registry's sidecar-lock pattern.

### AUDIT-02-5 — Failed registry read saved as empty (medium)

`read_registry` returns `_empty_registry()` on *any* exception, including an
SMB sharing violation. The mutators (`register_session_start`, `…_complete`,
`update_session_progress`) run under the lock and write back what they read.
One failed read therefore wipes every entry. `refresh_available_lists`
re-derives most of them from disk on the next browser refresh, but not their
worker names or metrics. **Fix:** mutators read strictly (raise on error);
listing keeps the lenient read.

### AUDIT-02-6 — Client picker live during a session (medium)

Nothing disables the command bar's client picker while a list is open.
Switching it changes `current_client_id`, which End session uses for
`record_packing` and the registry, and which Map SKU uses for
`packer_config.json`.

### AUDIT-02-7 — The order tree is rebuilt on every scan (medium, speed)

`_on_item_packed` (every non-completing scan) and `update_order_status`
(every order open and completion) call `_populate_order_tree`, which clears
and rebuilds every order and line with a `StatusChip` widget per order. It
does this while the tree sits on a page the packer can't see. Measured on
the VM (offscreen Qt), best of 3:

| list | tree rebuild | stats refresh | state size | state write (local disk) |
|---|---|---|---|---|
| 117 orders / 240 lines (largest production list) | 128 ms | 11 ms | 105 KB | 3 ms |
| 400 orders (synthetic, same mix) | 375 ms | 10 ms | 360 KB | 9 ms |

A scanner fires keystrokes faster than that, so scans queue behind the
rebuild. **Fix:** mark the tree dirty; rebuild when the Packing page is shown.

### AUDIT-02-8 — Share I/O on the UI thread (medium, observed)

The heartbeat timer's `update_heartbeat` (read + atomic write, up to 3
tries 0.5 s apart), and `_save_session_state_sync` at every order completion,
run on the UI thread. When the share is unreachable, Windows SMB calls can
block for tens of seconds, and the packing screen freezes with them.
Phase 12 already moved the other writes off the UI thread.
**Fix direction:** the heartbeat on a worker thread; the order-complete
checkpoint to use the async writer plus a flush at End session.

### AUDIT-02-9 — Confirm is recorded as a scan (medium)

Every unfinished row shows **Confirm**. `_on_manual_confirm` emits the row's
SKU through `barcode_scanned`, exactly as the scanner would, so the record
says `confirmation_method: "scanned"` and the feedback band shows the SKU
as the raw scan. A list packed entirely with clicks is indistinguishable from
one scanned item by item. Force confirm, by contrast, is recorded. This is
the one gap in "can we prove the packer verified the list?"

### AUDIT-02-10 — History column (medium, UI)

`on_scanner_input` calls `add_order_to_history(order)` on **ORDER_LOADED**,
and the default status is "complete". The column therefore lists an order as
Complete while it is still being packed, and never updates it. Skip adds a
second entry for the same order ("Skipped"), and returning to it adds a
third ("Complete").

### AUDIT-02-11 — Next order's barcode mid-order (low)

With an order open, every scan is treated as a SKU. Scanning the next order's
barcode (a common slip) reads "Unknown SKU #10430 — scan again or map it",
offers **Map SKU** for an order number, and adds to the order's unknown-scan
metric. **Fix:** if the text matches an order in the list, say "#10430 is an
order — finish or skip #10429 first" and don't count it.

### AUDIT-02-12 — Live "snapshot" (low)

`_build_state_dict` promises "a plain serialisable dict — safe to hand off to
a background thread", but puts the live `completed_orders_metadata`, the
in-progress item lists and the scan-record list into it. `atomic_write_json`
uses `indent=2`, which selects json's pure-Python encoder. The writer thread
can therefore run while the UI thread appends. Rare (scans are seconds
apart); the fix is a `copy.deepcopy` (≈1 ms at 117 orders).

### AUDIT-02-13 — "##" (low)

Order numbers carry their `#`; the message adds another.

### AUDIT-02-14 — Dead legacy path (cleanup)

`start_session` has one caller, its own stale-lock retry. Nothing in the UI
reaches it, so it, its two error dialogs, `RestoreSessionDialog` and
`get_incomplete_sessions` are dead: about 500 lines that every future
change to session start has to reason around.

## 4. Verified correct

- Lock creation is exclusive (`O_EXCL`): two PCs get one lock
  (`test_two_pcs_racing_for_a_free_list_get_one_lock`).
- An unreadable lock counts as held; heartbeat rewrites are atomic; losing
  the lock stops writes and tears the session down (Phase 12 B1–B3).
- Registry read-modify-writes are serialised by the sidecar lock
  (`test_registry_writers_do_not_drop_each_others_entries`).
- `global_stats.json` is updated under a lock on the file itself.
- `session_info.json` packed-order signal: written per order through the
  publisher, under Shopify's own `.lock` sidecar.
- Session browser refresh runs on a worker thread and skips while hidden.

## 5. Observations, no change proposed

- Staleness compares the lock's heartbeat (writer's clock) with the reader's
  clock; PCs more than 2 minutes apart would see a live lock as stale. Keep
  warehouse PCs on NTP.
- `refresh_available_lists` lists every session folder each refresh; the
  cost grows with history (≈3 share round-trips per session). Fine at today's
  volume.

## 6. Owner decisions needed

- **AUDIT-02-9:** keep the Confirm button, recorded as `manual` and counted
  in the summary (recommended), or remove it so only scans and Force pack?
