# Phase 15 — Packing-tool audit and its fixes (plan, already implemented)

**Repo:** `packing-tool` only. No `shared/` change, so no sync and no Shopify PR.
**Worktree / branch:** `packing-tool/.claude/worktrees/audit-packing` on `audit/packing-tool`,
from `origin/main` at `78c3a41`.
**Spec:** the two audit reports. Each finding, its root cause and its fix direction are there:

- `docs/audit/01-data-metrics.md`: packing list → scan matching → packing state → metrics.
- `docs/audit/02-concurrency-sweep.md`: several PCs, the file server, and the whole-app sweep.

This cycle was run by hand (owner session, 2026-09-26): the audit and both fix bundles are
committed. **The runner enters at Stage C** (review, fix findings, open one PR).

## Commits

| commit | content |
|---|---|
| `14cc94c` | audit: reports + proof tests (`tests/audit/`), no product code |
| `6ea4c96` | Fix Bundle A: data, metrics, Packer Mode sweep (AUDIT-01-1..6, 02-9..13) |
| `a0161bc` | Fix Bundle B: several PCs, file server, dead code (AUDIT-02-1..8, 02-14) |

## Owner decisions (2026-09-26)

- **AUDIT-01-3, a list rewritten after packing started: reconcile and tell.** Follow the list as
  it is now. Packed orders it dropped move to `completed_off_list`, out of every count but still
  published to Shopify as packed. Open orders it dropped are forgotten. An open order whose lines
  changed takes the new lines and keeps what was packed. An info toast names the changes.
- **AUDIT-02-9, the row's Confirm button: keep it, record it as manual.** `confirmation_method:
  "manual"`, summed as `metrics.total_manual_confirms` in the session summary.

## What the review should check hardest

1. **State format** (`packer_logic.py`). New keys: `in_progress._timing_by_order`,
   `completed_off_list`, `stats_recorded_orders`. The legacy `_timing` / `_current_extras` are
   still written for older app versions on other PCs, and still read (mapped to
   `progress.in_progress_order`). Mixed-version floors must not lose progress.
2. **End session stats** (`main_window.end_session`). Only orders new since the last End count,
   with this run's duration (`PackerLogic.run_started_at`). `stats_recorded_orders` is saved
   only after `record_packing` succeeds.
3. **SKU mapping** (`profile_manager`). Every write goes through `_change_sku_mapping`: a sidecar
   lock, then a fresh read, then temp file + rename. The dialog sends a diff
   (`update_sku_mapping`), and `PackerLogic.set_sku_map` no longer saves. A failed read raises
   and is never cached.
4. **Heartbeat thread** (`main_window._heartbeat_tick`). Renewal runs on a daemon thread.
   `_lock_io` serialises it with every `release_lock`, so a late renewal cannot recreate a
   released lock. Loss is signalled back to the UI thread.
5. **Dead-code removal (AUDIT-02-14).** `MainWindow.start_session`, its two lock dialogs,
   `RestoreSessionDialog`, `get_incomplete_sessions` and `load_from_shopify_analysis` are gone.
   `SessionManager`'s Excel lifecycle remains (left for a later refactor, flag it, don't do it).

## Gate

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q --color=no
.venv/bin/ruff check .
```

At `a0161bc`: 780 passed, ruff clean. Every AUDIT-k test in `tests/audit/` failed before its fix
(strict xfail at `14cc94c`) and is now a plain regression test. All 29 production packing states
under `~/Desktop/production info/` load with the new code with no packed order lost. Only herbar
2026-07-17_2 reports a list change (2 skipped orders no longer on the list), which is correct.

## By hand after merge

- A packing run on a warehouse PC before a floor release: the state format and the SKU-mapping
  write path changed.
- Other PCs should update together: an old build reading a new state ignores
  `_timing_by_order` and falls back to the single `_timing` block (the pre-fix behaviour).
