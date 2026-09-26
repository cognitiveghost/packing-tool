# Audit 01 — Packing list → scan matching → packing state → metrics and history

Scope: `packing_tool/packer_logic.py` (list loading, order lookup, scan
matching, force confirm, extras, skip, state save/load, session summary),
`packing_tool/session_stats.py`, the End-session path in `gui/main_window.py`
(report, `record_packing`, `update_worker_stats`, registry completion),
`shared/stats_manager.py`, `packing_tool/worker_manager.py`. Proof tests:
`tests/audit/test_01_data_metrics.py`. Audited against `origin/main` at
`78c3a41`, after Phase 12 Bundle 2 (#184).

## 1. Verdict

**Reading and matching are reliable. The numbers produced after the list has
been packed in more than one run are not.** I replayed all 29 production
packing states against the packing lists they were packed from: 613 completed
orders, and for every one the packed units equal the list's required units,
every scan is timestamped after its order started, and no order is both
completed and skipped. The ten production orders that list one SKU on two
lines are handled correctly: each line needs its own units.

The weak points are around the edges of a single, straight run:

- a list **ended, resumed and ended again** is counted twice in global and
  worker statistics (AUDIT-01-2);
- an order **left and returned to** (Skip, or leaving Packer Mode) takes over
  the previous order's timing and scan records (AUDIT-01-1);
- a packing list **rewritten by Shopify after packing started** is trusted
  blindly: stale quantities, and orders no longer on the list still count
  toward "done" (AUDIT-01-3). Production shows this happens.

## 2. Findings

| id | severity | summary | where | proof test | status |
|---|---|---|---|---|---|
| AUDIT-01-1 | high | Returning to a skipped or left order reuses the previous order's start time and scan records | `packer_logic.py:951`, `:1201`, `:1208` | `test_returning_to_a_skipped_order_keeps_its_own_scan_records`, `test_cancel_on_a_returned_order_does_not_edit_a_finished_order` | fixed |
| AUDIT-01-2 | high | Ending a list twice (incomplete → Resume → End) records its cumulative orders, items and time again | `gui/main_window.py:1537-1697` | `test_a_list_ended_twice_counts_each_order_once_in_global_stats`, `…_in_worker_stats` | fixed |
| AUDIT-01-3 | high | A packing list rewritten after packing started: resumed orders keep the old quantities; orders dropped from the list still count as done, so "all orders packed" can fire with orders unpacked | `packer_logic.py:923`, `:1337` | `test_a_resumed_order_follows_the_quantity_now_on_the_list`, `test_an_order_dropped_from_the_list_does_not_count_toward_done` | fixed |
| AUDIT-01-4 | low | Statistics SKU table gives a SKU's packed units to every product name it appears under | `session_stats.py:66`, `:79` | `test_sku_summary_counts_a_sku_once_across_product_names` | fixed |
| AUDIT-01-5 | low | The packing report stamps every completed order with the End-session time | `gui/main_window.py:1482` | `test_report_completed_at_is_when_the_order_was_packed` | fixed |
| AUDIT-01-6 | low | The Statistics "Items" card counts lines; every other "items" figure counts units | `session_stats.py:35` | `test_items_card_counts_units_like_every_other_items_figure` | fixed |

## 3. Findings in detail

### AUDIT-01-1 — A returned order inherits another order's timing (high)

**What goes wrong.** `PackerLogic` keeps one set of per-order timing fields
(`current_order_start_time`, `current_order_items_scanned`, the correction /
extra / unknown counters). `start_order_packing` resets them only for a
*new* order. For an order already in `in_progress` it assumes they were
restored from disk for that order. They weren't: they still hold whatever
order was open last.

**Scenario.** Open #1, scan one unit, Skip. Open #2, pack it. Open #1 again
and finish it. #1's completed record carries #2's scan, not #1's first scan,
and #2's start time. Its `items_count`, duration, first-scan latency and
correction count are all wrong. Undo on #1 can decrement a record that belongs
to #2's completed metadata, because `_complete_current_order` stores a
shallow copy of the same record dicts.

**Root cause.** Timing is per-PC-process, not per-order. `_build_state_dict`
also writes a single `_timing` block with no order number, so after a
restart it is applied to whichever in-progress order is opened first.

**Production evidence.** None visible: the two production skips were never
returned to. Every Skip that is returned to hits it, as does every exit from
Packer Mode in the middle of an order.

### AUDIT-01-2 — Ending a list twice counts it twice (high)

**What goes wrong.** End session on an unfinished list marks it
*incomplete*; the browser offers **Resume** on it. At every End session,
`record_packing` and `update_worker_stats` receive the list's *cumulative*
completed orders and items, `sessions=1`, and a duration measured from the
list's first start. They add, never replace.

**Scenario.** 1 of 2 orders packed, End (stats +1). Resume, pack the other,
End (stats +2). Global stats say 3 orders packed; the worker has 3 orders and
5 items for a list of 2 orders and 4 items. The duration counts the overnight
gap twice over.

**Root cause.** Stats are an append-only event log fed with running totals.

**Production evidence.** The production stats file is not in the snapshot.
The pre-fix record in the dev mirror shows the Phase 12 C1 bug
(`duration_seconds: null`) instead, fixed since.

### AUDIT-01-3 — A rewritten packing list (high)

**What goes wrong.** The packing state remembers orders and quantities, not
which version of the list they came from. On resume:

1. an order already in `in_progress` keeps its saved `required` counts, even
   if the list now asks for a different quantity;
2. `completed_orders` still counts orders the list no longer contains, so
   `_check_all_complete` (`done + skipped >= total`) can fire while orders on
   the current list are unpacked, and the progress reads e.g. 13/13.

**Production evidence.** `herbar 2026-07-17_2`: packing ended 11:05:40 with
13 packed and 2 skipped; at 11:06:28 Shopify re-ran the analysis and
overwrote `ALL_ORDERS_HERBAR.json` with 13 orders. Nothing links the saved
state to the list version, and nothing on either side warns.

### AUDIT-01-4 — SKU table double-counts across product names (low)

`sku_summary` groups by (SKU, Product_Name) but looks packed units up by SKU
alone. Production has `NO_SKU` under two names in one list; packing one gives
both rows "1 packed".

### AUDIT-01-5 — Report "Completed At" is the End-session time (low)

`end_session` writes `datetime.now()` for every completed order. The real
completion time is in `completed_orders_metadata`.

### AUDIT-01-6 — "Items" means lines on one card, units everywhere else (low)

The Statistics card counts rows (`len(df)`). The session summary, registry,
progress block and worker stats count units. A list with 3 × one SKU reads
"1 item" there and "3 items" everywhere else.

## 4. Production check

`production info/` snapshot, 35 packing lists, 29 packing states, 26
summaries (script kept out of the repo; it reads only JSON):

- 767 orders, 2265 lines; all order numbers are strings, all quantities
  positive integers, no empty SKUs.
- 613 completed orders: packed units == required units for 613/613;
  `items_count` == required for 613/613; 0 scans before their order's start.
- 80 force-confirmed units, all on one 3-SKU bundle (20 each) and two SKUs.
- 1 list rewritten after packing (AUDIT-01-3).
- Summaries: `completed_orders` matches the state in 26/26; `orders_per_hour`
  matches its own inputs in 26/26.

## 5. Verified correct

- Order lookup: `#`, `!` and spaces from the scanner are ignored; case is
  kept, as in Shopify's `sanitize_order_number`.
- SKU matching: normalised on both sides (case, spaces, dashes), mapping
  applied first, split lines matched by row
  (`test_split_lines_of_one_sku_each_need_their_own_units`).
- Restart in the middle of an order restores packed counts
  (`test_resume_after_restart_keeps_counts`) and extras.
- Phase 12 fixes hold: unreadable state refuses to open; failed writes are
  shown; Shopify-path duration is recorded; registry progress moves per order.

## 6. Owner decisions (2026-09-26)

- **AUDIT-01-3 → reconcile and tell.** On resume, packing follows the list as
  it is now. Packed orders the list dropped move to `completed_off_list`: out
  of every count, still published to Shopify as packed. Open orders the list
  dropped are forgotten. An open order whose lines changed takes the new
  lines and keeps what was packed. A toast names the changes.

## 7. Not covered

The legacy Excel path (unreachable, see AUDIT-02-14); the Shopify side of
list generation.
