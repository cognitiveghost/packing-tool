# Phase 10 Bundle 2 — artboard handoff

Maps every frame region to the widget or code it replaces, the bundle that
builds it, its tier, and the shared component it should use. See
`docs/superpowers/specs/2026-09-17-phase10-bundle2-artboards-design.md` for
the frame inventory and `docs/superpowers/plans/2026-09-17-phase10-packer-v2-roadmap.md`
for the bundle plan.

## Packer Mode (`packer-mode.html`, P1–P8)

Replaces every widget listed in `packer_mode_widget.py`'s docstring
(`metadata_banner`, `table`, `history_table`, `extras_table`,
`summary_table`, `session_progress_bar`, `packed_stat_label`,
`items_stat_label`, `status_label`, `notification_label`,
`raw_scan_label`, `skip_order_button`, `exit_button`, the sim `QGroupBox`).

| Frame region | Replaces (file:attribute) | Bundle | Tier | Component |
|---|---|---|---|---|
| `.cmdbar` order number + scanner field (`.field`) | `packer_mode_widget.py:scanner_input` (was a 1×1 hidden `QLineEdit`, moved and resized per spec A2) | 5 | Qt | `CommandBar` |
| `.cmdbar` "Skip order" / "Exit packing" | `packer_mode_widget.py:skip_order_button`, `:exit_button` | 5 | Qt | `CommandBar` button roles |
| `.cmdbar .sim-group` (1920 only) | the sim `QGroupBox` | 5 | Qt | new — dashed-outline group, no existing component |
| `.doc-banner` | `packer_mode_widget.py:metadata_banner` (`_meta_*_lbl` chips) | 4 | Web | new — `packer.css` banner row |
| `.feedback` | `status_label`, `notification_label`, `raw_scan_label` (three widgets collapsed into one band) | 4 | Web | new — `packer.css` feedback band |
| `.extras` | `extras_table` | 4 | Web | new — `packer.css` extras section |
| `.sku-list` / `.sku-row` | `table` (the 5-column `QTableWidget`) | 4 | Web | new — `packer.css` SKU list |
| `.side .side-block` (progress) | `session_progress_bar`, `packed_stat_label`, `items_stat_label` | 4 | Web | new — `packer.css` side column |
| `.side .history` | `history_table` | 4 | Web | new — `packer.css` side column |
| `.side` (summary) | `summary_table` | 4 | Web | new — `packer.css` side column |
| `.state-panel` (P1, P8) | new — no state-panel exists in `packer_mode_widget.py` today | 4 | Web | new — `packer.css` state panel inside the document; P8's "Exit packing" is a web→Qt bridge call to the same exit logic as the command-bar button |
| `.statusbar` | existing status bar (session ID, worker, client) | 3 | Qt | shell `QStatusBar` |
| `.rail` (hidden, A1) | `NavRail` — not shown while packing | 3 | Qt | `NavRail` |

**Lifting the web tier (A3).** `packer-document.css` holds the order
document's layout; the generic `.btn`, `.chip` and `.state-panel` rules it
uses inside `.doc` still live in `artboard.css`. Bundle 4 must carry those
three rule sets into `packer.css` along with `packer-document.css` — they
were not copied here, so the artboards keep one definition of each.

## Packing table view (`packing-table.html`, T1–T2)

| Frame region | Replaces (file:attribute) | Bundle | Tier | Component |
|---|---|---|---|---|
| `.rail`, `.cmdbar` | shell chrome (client selector, session ID) | 3 | Qt | `NavRail`, `CommandBar` |
| `.cmdbar` "Start packing" / "SKU mapping" / "End session" | `main_window.py:packer_mode_button`, `:sku_mapping_button`, `:toolbar_end_btn` | 6 | Qt | `CommandBar` button roles |
| `.otable` order/SKU rows | `main_window.py:order_tree` (`_setup_order_tree`, `QTreeWidget` with columns Order/Item, Product, Quantity, Status, Courier) | 6 | Qt | `Card` + delegate-painted tree, `StatusEdgeDelegate`-style status chip |
| `.state-panel` (T2) | new — `order_tree` today just shows empty, no state panel | 6 | Qt | `StatePanel` |

## Session Browser (`session-browser.html`, B1–B3)

| Frame region | Replaces (file:attribute) | Bundle | Tier | Component |
|---|---|---|---|---|
| `.otable` list rows (B1) | `sessions_list_widget.py:_table` (`QTableWidget`, columns Status/Packing List/Session/Worker/PC/Progress/Started/Duration/Items) | 6 | Qt | `Card` + `SessionStatusDelegate` (extended: three-channel status per F5) |
| `.filterbar` (B1) | `sessions_list_widget.py:_status_combo`, `_date_from`, `_date_to`, `_search_input` | 6 | Qt | `FilterBar` |
| `.otable-row--selected` | `_table`'s row selection | 6 | Qt | selection ring per artbook F4 |
| `.detail-header`, `.tabstrip`, `.card-grid` (B2) | `session_details_dialog.py` (`SessionDetailsDialog`, today a modal `QDialog` with Overview/Orders/Metrics tabs) | 6 | Qt | new — non-modal detail page (spec: "not a modal dialog unless D2 draws one"; D2 draws none) |
| `.card-grid .dl-row` (B2 Overview) | `overview_tab.py` (`OverviewTab`'s `addRow` fields) | 6 | Qt | `Card` + definition-list rows |
| `.state-panel` (B3) | new — no empty state exists today | 6 | Qt | `StatePanel` |

Only the Overview tab is drawn for B2; Orders and Metrics reuse the same
header + tab strip shell (F3's tab-strip convention — drawn once, not per
tab) and carry `orders_tab.py` / `metrics_tab.py`'s own fields into the
same `.card-grid` pattern.

## Statistics (`statistics.html`, S1–S2)

| Frame region | Replaces (file:attribute) | Bundle | Tier | Component |
|---|---|---|---|---|
| `.stat-grid` (Session totals) | `main_window.py:_setup_statistics_tab` stat cards (`stats_total_orders`, `stats_completed_orders`, `stats_total_items`, `stats_unique_skus`, `stats_progress_pct`) | 6 | Qt | new — `StatCard` grid (`statcard.py` pattern from Shopify, ADR reference) |
| `.courier-grid` (By courier) | `courier_stats_widget` / `courier_stats_layout` | 6 | Qt | `StatCard`, small variant |
| `.otable` (SKU summary) | `sku_table` (`QTableWidget`, columns SKU/Product/Total Qty/Status) | 6 | Qt | `Card` + status chip |
| `.state-panel` (S2) | new — `_update_statistics` today just leaves cards at 0 | 6 | Qt | `StatePanel` |

## Departures from the artbook

- **A1 (Packer Mode hides the rail).** Drawn as specified: `packer-mode.html`
  uses `.shell--bare` (no rail column), the 60px `.cmdbar` carries the order
  number, scanner field, Skip and Exit in place of the shell's normal
  command bar.
- **A2 (visible scanner field).** Drawn as a 44px `.field` showing
  "Ready to scan" with a focus ring (P2), rather than the shipped 1×1
  hidden `QLineEdit`.
- **Rail label overflow (found while rendering).** "Statistics" does not
  fit the floor-density 56px rail item at any legible size (measured: ~72px
  needed at 10pt body against 56px available, no wrap point in one word).
  The rail item shows **"Stats"**; the tab and page title stay
  "Statistics". Bundle 6 should either ship the shortened rail label or
  give `NavRail` a two-line label mode — the artboard doesn't decide which,
  it only proves the current 10-character label can't ship as drawn.
- **P8 / T2 duplicate primary action.** Both draw "Exit packing" /
  "Open session" in the command bar *and* as the state panel's primary
  action, deliberately — the same duplication the artbook's own S4 uses for
  "Server Connection…" ("an empty state that explains a problem without
  offering the fix is a dead end"). Reject this together with S4's pattern
  if it doesn't hold up in Bundle 5/6, not separately.
- **Session Browser columns (B1) trade D1/D2's proposed columns for what
  Packing Tool actually has.** D1/D2 proposes STATUS / SESSION / AGE /
  PACKING / **BLK** / LAST TOUCHED / **COMMENT**. Packing Tool's
  `session_info.json` has no blocked-orders concept (that's a Shopify
  fulfilment-analysis field) and no per-session comment feature exists here
  — both are dropped. LAST TOUCHED is kept and is *not* the cross-repo cost
  D1 flags: Packing Tool's own session index already stores Worker + PC per
  session, so `sessions_list_widget.py`'s existing Worker/PC/Started
  columns fold into one LAST TOUCHED column at no new cost. ITEMS (already
  shown today) is kept alongside it.
- **Packer Mode's document column pair is centred at 1920, not
  grid-tracked.** The spec says the main column stays at a readable measure
  while the side column widens; a straight two-column CSS grid leaves a
  ~600px dead gap between them at 1920 because the grid track keeps its
  width even when the content inside is capped. `.doc` uses flex with
  `justify-content: center` instead, so the capped main column and the
  widened side column stay adjacent and the pair sits centred in the extra
  width.
- **P4's "just changed" row** is a plain background tint
  (`.sku-row--just-changed`, `--status-success-bg`) per spec ("tint only,
  no animation") — Qt has no transitions in QSS and the web tier is banned
  from using them (ADR 0001), so there was never a second option here.

- **SKU row actions are 44px, so rows holding them outgrow the 40px rung.**
  The spec asks for both "SKU list rows (40px)" and "All action targets
  44px"; the two can't hold at once. The target size wins (`.sku-row` uses
  `min-height`), so a row with actions is 45px. Rows with no actions stay 40px.
- **Rail label "Browse"** stands in for "Session Browser" for the same reason
  as "Stats": the full name doesn't fit the 56px rail.
- **B1 drops today's Packing List and Duration columns.** They are not in
  D1/D2's column set either; AGE and LAST TOUCHED carry the time story.
  Restore them in Bundle 6 if supervisors miss them.

## Rendering note (not a design decision)

This VM has no Chrome/Chromium binary and `claude-in-chrome` cannot reach a
background job's local files or ports, so the plan's `chrome-devtools` MCP
render-check was done instead with `QWebEngineView` (offscreen platform,
scroll-into-view + crop per frame) — the same Chromium engine the app's own
web tier uses. All 25 frames were rendered and inspected this way; nothing
here was left unverified, but Stage C should re-render on a machine with a
real browser if it wants a second opinion.
