# Phase 10 Bundle 2 — Packing Tool artboards

**Status:** Stage A, 2026-09-17. Owner answers recorded below; the artboards
themselves are approved on the PR.
**Parent spec:** `2026-09-17-phase10-packer-v2-design.md` (D2, D3, D5 apply unchanged).
**Roadmap:** `docs/superpowers/plans/2026-09-17-phase10-packer-v2-roadmap.md`, Bundle 2.
**Mockup source:** Claude Design artbook `75385f2c-4be2-446c-8e9d-bf90ee063ff7`
(read with the `DesignSync` tool, `get_file`). Canvases that matter:
`F0 Foundation Specimen Sheet.dc.html` (tokens, F5 status marks),
`S Shell and Placement.dc.html` (shell anatomy, floor density),
`D Supporting Destinations.dc.html` (Shopify session browser, D1/D2),
`W Setup and Results.dc.html` (the web results document).

## Goal

Draw the Packing Tool screens as static HTML so Bundles 3–6 have a brief to
follow exactly. No app code, no tests beyond the lint check below.

## Owner decisions (2026-09-17)

| # | Question | Answer |
|---|---|---|
| Q1 | Packing table view (order tree on the Packing tab) — who builds it | Drawn here; built in **Qt in Bundle 6** with Session Browser + Statistics. Roadmap updated. |
| Q2 | Where Packer Mode's Qt controls sit | **Top 60px bar** in the command-bar slot: order number + scanner field left, Skip + Exit right. Web document takes full width below. |
| Q3 | Coverage | **Every state once, key frames twice**: all Packer states at 1366 dark; scanning, wrong SKU and order complete also at 1366 light and 1920 dark. Every other screen in both themes at 1366. |
| Q4 | Review | Repo HTML under `docs/design/phase10/` **plus a private Artifact preview link** in the PR body. |

## Density and shell (from artbook S, floor)

- Command bar 60px, rail item 56×64, status bar 40px, row rung 40px,
  controls 44px, body 12pt, session ID mono 12pt, client selector 240px.
- Status marks follow F5: solid mark = a person did it, hollow = the system,
  tinted = live, untinted = resting or terminal.
- Windows sizes are client area (1366×768 means 1366×768 of app).

## Decisions made at Stage A (reversible at PR review)

- **A1. Packer Mode hides the rail.** Its 60px Qt bar replaces the shell
  command bar for the duration of packing; Exit is the only way out, so a rail
  click cannot bypass the exit/skip logic. The 40px status bar stays (session
  ID, worker, client).
- **A2. The scanner field is visible**, not a 1×1 hidden line edit: a 44px
  read-only-looking field showing "Ready to scan" with a focus ring, so a
  packer can see the scanner is live. Its behaviour (D3) is unchanged; Bundle 5
  sizes it.
- **A3. The order document's CSS is written to be lifted.** Everything inside
  the web tier of a Packer Mode frame is styled by `packer-document.css`, which
  obeys the web-tier rules (ADR 0001) so Bundle 4/5 can copy it into
  `gui/web/packer.css` rather than redraw it. Qt-tier parts use
  `artboard.css`, which only has to look right.
- **A4. Tier labels.** Every Packer Mode frame carries a thin `TIER QT` /
  `TIER WEB` annotation outside the frame edge (artbook S5b convention), so the
  D2 split is visible.
- **A5. Tokens are generated, not typed.** `tokens.css` is produced from
  `shared.theme.theme_css_vars()` for `LIGHT_THEME` and `DARK_THEME` at floor
  density, scoped under `[data-theme="light"]` / `[data-theme="dark"]` on each
  frame. It is the only file with hex in it.

## Frame inventory

`P` = Packer Mode, `T` = Packing table view, `B` = Session Browser,
`S` = Statistics. `D` = dark, `L` = light. Size 1366×768 unless stated.

| Frame | State | Variants |
|---|---|---|
| P1 | No session — web doc shows a state panel ("No session open. Start one from the Packing tab."), scanner field disabled, Skip disabled | D |
| P2 | Waiting for order — scanner ready, doc shows "Scan an order barcode", session progress and history visible | D |
| P3 | Scanning in progress — banner (order no., courier, country, box, tags, notes), SKU list with mixed item states, progress | D, L, D@1920 (1920 frame also shows the dev scan simulator in the bar) |
| P4 | Match — feedback band confirms the last SKU, raw scan in mono, row just ticked | D |
| P5 | Wrong / unknown SKU — danger feedback band with raw scan, row actions include Map SKU | D, L, D@1920 |
| P6 | Extras present — extras section above the SKU list with Keep / Remove per SKU | D |
| P7 | Order complete — success band, all rows complete, "Scan the next order" prompt | D, L, D@1920 |
| P8 | Session complete — state panel with session summary numbers, Exit is primary | D |
| T1 | Packing table view with orders, grouped order → SKU rows, status chips, filter | D, L |
| T2 | Packing table view, no session (empty state that invites starting one) | D |
| B1 | Session Browser — list + filters | D, L |
| B2 | Session Browser — session detail | D, L |
| B3 | Session Browser — no sessions / no filter matches | D |
| S1 | Statistics — stat cards | D, L |
| S2 | Statistics — no data yet | D |

25 frames.

### Packer Mode layout (web document)

Order document fills the area under the 60px bar and above the 40px status bar.

- **Main column:** metadata banner → scan feedback band → extras section (only
  when present) → SKU list.
- **SKU list rows** (40px): product name, SKU (mono), packed/required, F5
  status chip, row actions. Actions per D2 and today's signals: manual confirm,
  cancel (undo a packed unit), force confirm, map SKU. All action targets 44px.
- **Side column** (fixed width, drawer-free): session progress (orders and
  items packed x / y), history (recent orders, newest first, with outcome
  chip), summary (unique SKUs packed / total).
- **Scan feedback band:** the most prominent element on the page — readable
  from arm's length. Tinted by outcome (success / danger / info), with the raw
  scan in mono. Replaces `status_label`, `notification_label`, `raw_scan_label`.
- At 1920 the side column widens; the main column does not stretch its rows past
  a readable measure.

Current widgets it replaces are listed in `packer_mode_widget.py`
(`metadata_banner`, `table`, `history_table`, `extras_table`, `summary_table`,
`session_progress_bar`, `packed_stat_label`, `items_stat_label`,
`status_label`, `notification_label`, `raw_scan_label`, `skip_order_button`,
`exit_button`, the sim `QGroupBox`).

### Copy rules

Active voice, one name per action across all frames ("Skip order", "Exit
packing", "Map SKU", "Force confirm", "Keep", "Remove"). Errors say what to
do next ("Unknown SKU 4006381333931 — scan again or map it"). Empty states
invite the next action. Sample data is plausible warehouse data, never lorem
ipsum; reuse order/SKU shapes from `tests/` fixtures.

## Files

```
docs/design/phase10/
  index.html              frame index + links, both themes toggle-free (static)
  tokens.css              generated (A5); header comment says how
  artboard.css            canvas + Qt-tier look (shell, rail, bar, status bar)
  packer-document.css     web-tier styles (A3), lint-clean
  packer-mode.html        P1–P8
  packing-table.html      T1–T2
  session-browser.html    B1–B3
  statistics.html         S1–S2
  HANDOFF.md              artboard → widget / bundle map
```

`HANDOFF.md` has one table per screen: frame region → the widget or code it
replaces (file + attribute) → the bundle that builds it → Qt or web tier →
the shared component it should use (`Card`, `StatePanel`, `CommandBar`,
`Toast`, `ConfirmDialog`, status chip) or "new". It also lists every place
the artboards depart from the artbook and why (A1, A2 at least).

## Guardrails

- No hex, shadows, gradients, transitions, transforms or px font sizes in any
  file except `tokens.css`; one mono face via `--font-family-mono`.
  Check: `.venv/bin/python -m shared.style_lint docs/design/phase10/*.html
  docs/design/phase10/artboard.css docs/design/phase10/packer-document.css`
  prints nothing.
- Files open straight from disk (no server, no CDN, no JS required).
- No app code, no changes to `shared/`.

## Non-goals

- No interactive prototype, no JS state machine.
- No redesign of dialogs (SKU mapping, worker selection, restore session) —
  they get the general repaint in Bundle 3.
- No Shopify-side artboards.
