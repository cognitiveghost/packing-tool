# Phase 10 Bundle 6 — Session Browser, Packing table, Statistics, and the merge defects

**Date:** 2026-09-19
**Repo:** packing-tool (with one `shared/` change that syncs to shopify-fulfillment-tool)
**Roadmap:** `docs/superpowers/plans/2026-09-17-phase10-packer-v2-roadmap.md`, Bundle 6
**Artboards:** `docs/design/phase10/session-browser.html` (B1–B3),
`docs/design/phase10/packing-table.html` (T1–T2),
`docs/design/phase10/statistics.html` (S1–S2), and
`docs/design/phase10/HANDOFF.md` for the region→widget map.
**Todoist:** subtask `6hWmQ9h4H6pCh8r3` under `6hWmQ82ph3fwXm83`.

## Scope and its size

Bundle 6 rebuilds three Qt screens and fixes five defects the owner found after
merging Bundle 5 (PR #181). It is the largest bundle in Phase 10 — roughly
two to three times Bundle 5, which was thirteen tasks and filled one
implementation run.

The alternative was to ship the five defects first as a small PR and split the
three screens into 6a and 6b. **The owner chose one bundle, everything at
once (2026-09-19).** That is recorded here so a later reader knows the size was
deliberate rather than an oversight. The plan is ordered so the defect fixes
land first and each screen is independently reviewable.

## What the mockups already decided

Every visual question here was settled by the Bundle 2 artboards, which the
owner approved. Where this spec departs from them, it says so under
**Departures** and gives the reason. The four questions the artboards left open
went to the owner on 2026-09-19:

- **Per-SKU roll-up** — restore it as a side-column block in the order
  document, not under the SKU list. The room comes from bounding the history
  block.
- **Scan history** — bound the block's height and scroll inside it. No history
  is discarded.
- **Rail label** — ship `Stats`. The tab and page title stay `Statistics`.
- **Scope** — one bundle, as above.

---

## Part 1 — The five merge defects

These are defects in shipped code the owner is using on the floor, so they come
first in the plan and are independently testable.

### 1.1 Order numbers render as `##11019512`

Real order numbers already carry a leading `#` — `tests/test_session_metadata_orders.py`
uses `"#11019512"` — and three display sites prepend a second one:
`gui/web/packer.js:108` (the banner), `gui/web/packer.js:168` (a history row),
and `gui/packer_mode_widget.py:320` (the Qt command-bar order label).

**Fix:** one helper that prefixes `#` only when the value does not already
start with one, applied at all three sites. Both tiers need it, so there are
two one-line helpers — `orderLabel()` in `packer.js` and `_order_label()` in
`packer_mode_widget.py` — rather than one crossing the bridge. Stripping the
`#` at the data layer was rejected: a client whose order numbers carry no `#`
would then lose the marker entirely.

### 1.2 The per-SKU roll-up is gone

Not a regression against the brief. The old `summary_table` was a four-column
per-SKU consolidation (SKU / Product / packed-of-required / status) that merged
an order's repeated SKU lines into one row each. **The approved artboard
replaced it with a single `Unique SKUs packed 19 / 34` line**, on all twelve
Packer Mode frames, and Bundle 5 built the artboard faithfully.

**Owner decision (2026-09-19):** restore the roll-up as a block in the order
document's **side column**, below history — not as a full-width table under the
SKU list. The side column has the room once history is bounded (1.4).

**Fix:** a new `sku_rollup` bridge property carrying one entry per distinct SKU
(`sku`, `product`, `packed`, `required`, `state`), produced beside the existing
`summary_lines()` in `gui/packer_bridge.py` from the same `self._rows` the SKU
list uses, and rendered as a `.side-block` in `packer.css` with the item-state
chip the SKU list already uses. The single `Unique SKUs packed` line stays: it
is the roll-up's own total and the artboard's own copy.

This is a **departure from the artboard**, made on the owner's explicit
instruction after using the shipped screen.

### 1.3 Keeping an extra does not update the extras block

The wiring reads correctly end to end — `keepExtra` → `keepExtraRequested` →
`_on_extra_confirmed` → `confirm_keep_extra()` → `show_extras_panel()` →
`set_extras()` → `extrasChanged` → `renderExtras()` — so this one needs
reproduction before a fix, not a guess.

**The first hypothesis, and the one real asymmetry found:** `confirm_keep_extra`
(`packing_tool/packer_logic.py:1324`) does `pop()`, clearing **every** unit of
that SKU at once, while `remove_extra_item` (`:1334`) decrements by one. Scan
the same unexpected SKU twice and click *Keep* once and both disappear —
whereas *Remove* would need two clicks. If the owner expected the count to fall
2 → 1, "Keep did not update the extra" is exactly what that looks like.

**Fix:** reproduce first with a failing test at the `PackerLogic` seam (scan one
SKU as an extra twice, keep once, assert the remaining count). If the
hypothesis holds, make *Keep* decrement by one like *Remove*, so the two
actions are symmetric and a multi-unit extra can be resolved unit by unit. If
it does not hold, the reproduction has narrowed it to the bridge or the page
and the fix follows the evidence. **Do not change behaviour without a failing
test that shows the defect first.**

### 1.4 Scan history grows without bound

`_history.insert(0, …)` in `gui/packer_mode_widget.py:490` has no cap, and
`.history` in `gui/web/packer.css:242` sets `overflow-y: auto` with no bounded
height — so the block stretches the side column instead of scrolling. The old
Qt `history_table` had no cap either; it simply sat in a fixed-height layout,
which is the constraint the web tier lost.

**Fix (owner decision):** give `.history` a bounded height so it scrolls
internally, keeping the whole session's history reachable. Nothing is
discarded. The freed vertical space is where the 1.2 roll-up block goes.

### 1.5 A crash left nothing in the log

**Root cause: neither repo installs a `sys.excepthook`.** An unhandled exception
in a Qt slot is printed to stderr, and a frozen Windows GUI build has no
console to print to — so the traceback never reaches the log file. This is why
the owner saw a crash with no log information.

**Fix:** install the hook in `shared/logger.py`, beside `setup_logging`, so one
change covers both tools and every future crash. It must cover
`sys.excepthook` and `threading.excepthook` (a worker thread's crash is just as
invisible), log the full traceback at `CRITICAL` through the existing unified
logger, and then chain to the previous hook so nothing that works today stops
working. `shared/` is canonical in this repo, so this propagates to
shopify-fulfillment-tool on the next `sync_shared.py` run.

---

## Part 2 — The status chip, shared by all three screens

All three artboards use one chip, and `artboard.css:239` names it: **F5's three
channels — colour, fill, mark.**

- **Colour** — the status role: info, success, warning, danger, neutral.
- **Fill** — tinted means *live*, untinted means *resting or terminal*.
- **Mark** — the dot: solid means *a person did this*, hollow means *the system
  decided it*.

**`shared/theme.py` already implements all three channels, and nothing needs
building.** `StatusChip(role, text, theme, *, live=True, manual=False)` takes
`live` for the tint and `manual` for the mark, resolves them through
`status_style(role, theme, live=, manual=)`, and paints the 8px mark itself in
`paintEvent` (`shared/theme.py:702-1005`). Both keywords are keyword-only and
defaulted to the shipped appearance, so no existing call site in either repo
changes.

This spec's first draft proposed extending `StatusChip` with new `tint` and
`hollow` arguments. That was wrong — the channels were already there under the
names `live` and `manual`. **Bundle 6 writes no new chip code; it passes the two
keywords that already exist.**

Porting Shopify's `gui/session_row_delegates.py`, `status_edge_delegate.py` and
`selection_ring.py` into `shared/` — 418 lines — is likewise unnecessary.

**The session-status mapping**, read off B1's seven rows:

| `STATUS_CONFIG` key | Label | Role | Tint | Mark |
|---|---|---|---|---|
| `not_started` | Not started | `text_secondary` | `live=False` | `manual=False` |
| `in_progress` | Active | `status_info` | `live=True` | `manual=False` |
| `paused` | Paused | `status_warning` | `live=True` | `manual=True` |
| `stale` | Stale | `status_warning` | `live=True` | `manual=False` |
| `completed` | Completed | `status_success` | `live=False` | `manual=False` |
| `incomplete` | Incomplete | `status_danger` | `live=True` | `manual=True` |
| `abandoned` | Abandoned | `status_danger` | `live=False` | `manual=False` |

The rule behind it: **Paused and Incomplete are the two states a packer
declares; the system infers the other five** — so those two carry the solid
mark. **Tint marks a session that can still be worked** — Active, Paused, Stale
and Incomplete are resumable; Completed, Abandoned and Not started are not.
Stage B adds `live` and `manual` to each `STATUS_CONFIG` entry in
`gui/session_browser/sessions_list_widget.py:51`, so the mapping lives in one
table rather than being re-derived at each call site.

---

## Part 3 — Session Browser

### 3.1 One client selector, not two

The shell's command bar already owns a client picker
(`gui/command_bar.py:56`, aliased as `MainWindow.client_combo`). The Session
Browser carries a **second, independent** one: `ClientSelectorWidget` (127
lines) in a `QSplitter` down the left of the browser tab.

Artboard B1 draws no such sidebar — the client selector sits in the command bar,
where the shell's already is.

**Decision:** delete `client_selector_widget.py` and the splitter.
`MainWindow.on_client_changed` (`gui/main_window.py:1004`) gains a call to
`session_browser.load_client(client_id)`; today it notifies nothing. The
browser's per-client entry/active/stale counts, which the sidebar header
carried, move to the status bar as the artboard's `7 of 7 sessions`.

### 3.2 The list

`SessionsListWidget` keeps its `QTableWidget`. Rewriting it as model/view is not
what the artboard asks for, and the widget already sets a per-row status cell
widget (`:447`), which is the hook the chip needs.

- **Columns 9 → 6**, per B1: Status, Session, Age, Packing, Items, Last touched.
  Worker, PC and Started fold into one **Last touched** column
  (`W-004 · WH-PC-02 · 11:20`); **Age** is new and derived from the start
  timestamp already in the registry entry. Packing List and Duration are
  dropped, as the artboard specifies.
- **Status cell** — `_make_status_cell` swaps `StatusDot` + `QLabel` for one
  `StatusChip` carrying the Part 2 channels. The hidden sort-key item at
  `COL_STATUS` stays; it carries the row's entry and every filter reads it.
- **Filters** — the existing widgets (`_status_combo`, `_date_from`,
  `_date_to`, `_search_input`) stay and are re-laid per B1, with its `Status:`
  / `From:` / `To:` labels and the `Refresh` button moved into the row. Filter
  *behaviour* does not change.

  HANDOFF maps this region to the shared `FilterBar`, but that component is a
  row of toggle chips (`add_filter(key, text)` over `_FilterChip(QPushButton)`,
  `shared/components/filterbar.py:24`) — not a container for a combo, two date
  editors and a search field. Using it would mean re-specifying the filters,
  which this bundle does not do. The artboard draws labelled fields, and
  labelled fields are what it gets.
- **Card** — the table sits in a `shared.components.card.Card`.
- **Empty** — no sessions, or none matching the filters, shows a
  `shared.components.state_panel.StatePanel` (B3) in place of the table. The
  two cases get different copy: nothing to show yet versus nothing matched.

### 3.3 The detail page

`SessionDetailsDialog` is a modal `QDialog` today. B2 draws a page, not a
dialog, and the Phase 10 spec says detail is "not a modal dialog unless D2
draws one" — D2 draws none.

**Decision:** `SessionBrowserWidget` becomes a `QStackedWidget` of two pages,
list and detail. Selecting a session shows the detail page; the artboard's
`← Sessions` button returns. `OverviewTab`, `OrdersTab` and `MetricsTab` keep
their content and their files; what changes is that they are laid into the
artboard's `Card` + definition-list rows and hung under a shared header and tab
strip instead of a dialog's. `SessionDetailsDialog` is deleted once its header
and tab strip have moved.

The dialog's **Export Excel** action moves to the right of the detail header.
Its **Close** becomes the `← Sessions` button.

---

## Part 4 — Packing table view

`MainWindow._setup_order_tree` (`gui/main_window.py:458`) stays a `QTreeWidget`
— T1 draws parent order rows with child SKU rows, which is what a tree is.

- **Card** — the tree sits in a `Card`; the hardcoded
  `QTreeWidget::item { height: 30px; padding: 5px; }` stylesheet goes, replaced
  by the 40px floor-density row rung from the theme tokens.
- **Status chips** — the Status column uses `StatusChip`: *In progress*
  (warning, tinted, solid), *Packed* (success, untinted, hollow), *Not started*
  (neutral, untinted, hollow). Child SKU rows leave Status and Courier empty,
  as drawn.
- **Filter orders** — T1 puts a filter field in the command bar. This is new:
  the tree has no filter today. It hides orders whose number, SKU or product
  does not match, keeping matching children visible under their parent.
- **Empty** — no packing list loaded shows a `StatePanel` (T2) where the tree
  is. Today the tree simply renders empty.

**Deletion.** `gui/order_table_model.py` and `gui/custom_filter_proxy_model.py`
(≈9KB) are dead: nothing constructs `OrderTableModel` or
`CustomFilterProxyModel`, and the only references are two stale lines in
`MainWindow`'s class docstring (`:158-159`). Both files go, and the docstring
is corrected. They sit exactly in the code this part touches, and leaving them
invites a future reader to wire the new filter into a proxy model that was
never used.

---

## Part 5 — Statistics

### 5.1 The computation does not belong in `shared/stats_manager.py`

The roadmap says "logic that belongs in `shared/stats_manager.py` moves there".
**That premise is wrong and should not be followed.** `StatsManager` is a
persisted, cross-tool event log — `record_analysis`, `record_packing`,
`record_label_print`, `get_global_stats` — reading and writing a shared JSON
file under a lock. The Statistics tab computes something else entirely: live
per-session aggregates over the current `processed_df`, using Packing Tool's own
column names and its `session_packing_state`. Moving it into `shared/` would
push pandas and Packing-specific columns into a module Shopify also receives,
for no caller.

**Decision:** the computation moves to a new pure module,
`packing_tool/session_stats.py` — no Qt, no widgets, one function per block:

```
session_totals(df, completed_orders)  -> orders, completed, items, unique_skus, progress_pct
courier_totals(df)                    -> [(courier, orders, items), …]
sku_summary(df, session_packing_state) -> [(sku, product, qty, packed, state), …]
```

That is the seam the tests bind to. `_update_statistics` currently runs ~145
lines mixing three pandas aggregations with widget construction and is testable
only through a window; after the split each aggregation is a plain function over
a DataFrame.

The pandas work carried over — `itertuples` over `iterrows`, the vectorised
`groupby` for completed orders — is deliberate optimisation with comments saying
so. **Carry it across unchanged.** This is a move, not a rewrite.

### 5.2 The screen

- **`StatCard`** — a new `shared/components/statcard.py`: a big value over a
  small label in a bordered box, with a `--sm` variant for the courier grid.
  It replaces two hand-rolled copies of the same widget that exist in
  `main_window.py` today (`_make_stat_card` and the courier card built inside
  `_update_statistics`). Shopify has no `statcard.py` despite HANDOFF's note, so
  this is new code, not a port.
- **Session totals** — the same five cards as today, in the artboard's
  `stat-grid`.
- **By courier** — `StatCard` small variant, label `DPD · orders`, unchanged
  data.
- **SKU summary** — `Card` + table, with a **three-state chip** replacing
  today's text: **Packed** (success, hollow) when packed ≥ required,
  **Partial** (warning, tinted, hollow) when some is packed, **Pending**
  (neutral, hollow) when none is. Today this column reads `Complete` or a bare
  `3/5`, which the artboard replaces.
- **Empty** — no packing list loaded shows a `StatePanel` (S2). Today the cards
  sit at zero, which reads as a session with no work rather than no session.
- **`main_window.py` builds no Statistics widgets inline.** The tab moves to
  `gui/statistics_widget.py`, fed by `packing_tool/session_stats.py`. This is
  the roadmap's "done when" condition.

---

## Part 6 — The rail label

`RAIL_ITEMS` (`gui/main_window.py:86`) ships `Statistics`, which the artboard
measured at ~72px against 56px of rail and could not fit. `Session Browser` is
already shortened to `Browse` in the same tuple.

**Decision (owner, 2026-09-19):** the rail item reads **`Stats`**. The tab
label, the page title and the tooltip keep the full word.

---

## Departures from the artboards

1. **A per-SKU roll-up returns to the order document's side column** (1.2). The
   artboard drew a single summary line on all twelve frames. The owner asked
   for the roll-up back after using the shipped screen, and chose the side
   column over a full-width table.
2. **The scan-history block gains a bounded height** (1.4). The artboard drew
   history at one length and never showed it overflowing; the constraint is
   implied by the frame, not drawn in it.
3. **Export Excel sits in the detail header** (3.3). B2 leaves the header's
   right side empty and does not draw the action, but the dialog it replaces
   has it and no other surface offers it.

Everything else follows the artboards as approved, including the six B1 columns,
the dropped Packing List and Duration columns, the missing client sidebar, and
`Stats` on the rail.

## Non-goals

- No fourth screen and no new web-tier surface. All three screens stay Qt.
- No change to session file formats, the registry index, or the
  Shopify↔Packing contract.
- No new dependency.
- No rewrite of `SessionsListWidget` or the order tree to model/view.
- No rework of the filter *semantics* — the filter bar is re-laid, not
  re-specified.

## Testing

The seams Stage B binds tests to, so they do not end up bound to widgets:

- **`packing_tool/session_stats.py`** — the three functions, over DataFrames
  built in the test. The highest-value new seam in the bundle: today none of
  this is testable without a window.
- **`packing_tool/packer_logic.py`** — the 1.3 extras reproduction, as a
  failing test first.
- **`gui/packer_bridge.py`** — the `sku_rollup` payload (1.2) and the order
  label helper (1.1), as pure functions over rows.
- **`shared/logger.py`** — the excepthook logs a traceback and chains to the
  previous hook.
- **`STATUS_CONFIG`** — every one of the seven statuses maps to a chip; an
  unknown status still renders.
- **Widget level, kept thin:** each of the three screens shows its `StatePanel`
  when it has nothing to show, and `main_window.py` constructs no Statistics
  widgets.

Every payload function introduced here needs a named caller task in the plan.
Bundle 5's review found two functions that every test exercised and nothing in
`MainWindow` called; the feature shipped unreachable with a green suite.

## Done when

- All three screens match their artboards in both themes at floor density.
- `main_window.py` builds no Statistics widgets inline, and
  `order_table_model.py` / `custom_filter_proxy_model.py` are gone.
- The five defects each have a regression test that fails without the fix.
- `shared/` changes are synced to shopify-fulfillment-tool and that suite is
  still green.
- The suite and `ruff` pass, `style_lint` finds no hardcoded colour, and
  `graphify update .` has been run.
- The owner has checked all three screens on a Windows build.
