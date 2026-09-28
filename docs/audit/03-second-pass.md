# Audit 03 — Second pass: packing metrics and order data

Scope: the Phase 15 fixes in `packing_tool/packer_logic.py`
(`_reconcile_with_list`, `_fresh_order_state`, `generate_session_summary`,
`compute_order_timing_metrics`), `packing_tool/session_stats.py`,
`packing_tool/worker_manager.py` (averages), `shared/stats_manager.py`
(`record_packing`), the End-session stats path in `gui/main_window.py`, and the
partial summary in `gui/session_browser/session_detail_page.py`. Proof test:
`tests/audit/test_03_second_pass.py` (written by the fix plan, red first).
Audited against `origin/main` at `2dd6ab5`, after Phase 15 (#187). Checked
against the 26 production `session_summary.json` files.

The Shopify half of this pass is
`shopify-fulfillment-tool/docs/audit/06-second-pass.md`.

## 1. Verdict

**Order data and the counts are right. One time metric measures the wrong
thing.** "Avg time per item" is the mean of each scan's offset from its order's
start, not the time an item takes. That puts it near the time per order.

## 2. Findings

| id | severity | summary | where | proof test | status |
|---|---|---|---|---|---|
| AUDIT-03-1 | medium | `avg_time_per_item` averages `time_from_order_start_seconds`, so it reports roughly half an order's duration, not the time per unit packed | `packing_tool/packer_logic.py:103-111` | `test_avg_time_per_item_is_order_time_over_units` | open |

### AUDIT-03-1 — Avg time per item (medium)

**What goes wrong.** An order of 3 units scanned at 10 s, 20 s and 30 s after
its start takes 30 s, which is 10 s per item. The metric reports
(10 + 20 + 30) / 3 = 20 s. The more units an order has, the further off it is.

**Production evidence.** It is off in all 25 summaries with timed orders, reading
2 to 4 times too high. For example, 2026-07-22_1 shows 27.9 s per item where
order time over units is 8.4 s, and 2026-07-21_2 shows 81.1 s against 20.5 s.
It is shown on the session browser's Metrics tab
(`gui/session_browser/metrics_tab.py:105`) for complete and partial summaries,
because both use `compute_order_timing_metrics`.

**Fix direction.** Divide the summed durations of the timed orders by the summed
`items_count` of those same orders.

## 3. Verified correct

- `session_stats.session_totals` / `sku_summary` / `courier_totals`: units,
  distinct SKUs, per-SKU packed from in-progress plus closed orders.
- `_reconcile_with_list` carries packed units across a rewritten list
  line by line, capped at the new required quantity.
- End session records only orders not yet recorded (`stats_recorded_orders`),
  with this run's own duration. Worker averages are total time / orders and
  orders / sessions.
- `record_packing` adds the run's orders and items once. History is capped at
  1000 entries.

## 4. Observations, no change

- **A resumed list's summary counts the time between runs.**
  `generate_session_summary` measures `duration_seconds` from the list's first
  `started_at`, so `orders_per_hour` on a list resumed the next day includes the
  night. Worker and global stats already use each run's own time. Fixing this
  means deciding what a list's duration is (worked time vs elapsed). Recorded,
  not changed.
- Worker `avg_time_per_order` is run time / orders, idle time included.
- `total_sessions` counts End-session events, so a resumed list counts twice.
  This is consistent with the per-run stats since AUDIT-01-2.
- `_fresh_order_state` reads an unparsable quantity as 1. Shopify's payload
  always writes an integer (`core.build_packing_order_data`), so this doesn't
  arise.
