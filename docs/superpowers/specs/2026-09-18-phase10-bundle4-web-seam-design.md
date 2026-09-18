# Phase 10 Bundle 4 — the web seam and the order document

**Status:** owner-approved on the four scope questions below, 2026-09-18.
**Parent spec:** `docs/superpowers/specs/2026-09-17-phase10-packer-v2-design.md` (D1–D3, D7).
**Roadmap:** `docs/superpowers/plans/2026-09-17-phase10-packer-v2-roadmap.md`, Bundle 4.
**ADR:** `docs/adr/0001-packer-mode-on-the-web-tier.md`.
**Mockup (the brief):** `docs/design/phase10/packer-mode.html` frames P2–P7, with
`docs/design/phase10/packer-document.css` and `docs/design/phase10/HANDOFF.md`.

## Goal

Packer Mode's order document moves onto the web tier. After this bundle the
document is whole — metadata banner, feedback band, extras, SKU list with
per-item states and actions, and the side column (progress, history, summary) —
and every Qt widget it replaces is gone. Qt keeps the scanner, Skip, Exit and
the dev simulator, still sitting where they sit today; Bundle 5 places them per
the artboard and adds the two state panels, P1 and P8.

## Scope decisions (owner, 2026-09-18)

### S1 — The whole document lands in Bundle 4, not half of it

The roadmap splits the document across Bundles 4 and 5 (SKU list here;
banner, feedback, extras, history, summary, progress there); `HANDOFF.md` tags
all of it Bundle 4. The owner chose whole-document.

Reason: every region is fed by data `PackerModeWidget` already receives through
an existing public method, so each one is a bridge property plus a render
function. The split's cost is the opposite of a saving — a hybrid screen (web
list, Qt feedback and history around it) has to be laid out, reviewed and
scanner-checked on Windows, then thrown away one bundle later.

Bundle 5 therefore becomes: Qt chrome placement (scanner field in the command
bar, Skip/Exit, sim group), the two state panels — P1 "No session open" and P8
"session complete" — and retiring what is left. Both panels need session state
the widget is never told about today: `clear_screen()` runs when Packer Mode is
*left*, not when a session opens, so nothing in Bundle 4 can honestly
distinguish "no session" from "waiting for an order". The panels' CSS still
lands here, with the rest of the lifted rule sets.

### S2 — Row actions keep today's rules, drawn in the artboard's style

The artboard draws action sets per state (Undo on complete; Confirm + Force
confirm on partial; Confirm on pending). Those sets, taken literally, drop the
`required_qty > 5` guard on Force confirm and leave a partially packed row with
no way to undo a mis-scan. The owner chose today's behaviour:

| Action | Shown when | Bridge slot |
|---|---|---|
| Confirm | `packed < required` | `confirmItem(row)` |
| Undo | `packed > 0` | `undoItem(row)` |
| Force confirm | `required > 5` and `packed < required` | `forceItem(row)` |
| Map SKU | normalised SKU is not a value in `sku_map` | `mapSku(sku)` |

Rendered with the artboard's `.btn.btn--ghost` at caption size. The label is
**Force** rather than "Force confirm" where three buttons share the 190px
actions slot; nothing else about the drawing changes.

One micro-change against today: Undo appears only once something is packed.
Today it is always present and answers a press at zero with a "Already at 0!"
warning — a button whose only outcome is a complaint.

### S3 — Map SKU stays per item

The artboard puts **Map SKU** on an unmatched-scan row ("Unknown SKU", the raw
barcode, chip "No match"). That row is a scan-feedback concept the current model
does not have, and it needs the *reverse* dialog: today
`map_sku_requested(sku)` prompts for the barcode, while that row knows the
barcode and needs the SKU picked.

Bundle 4 ships the existing per-item button on rows whose SKU has no mapping,
through the existing signal and dialog. The unmatched-scan row and its dialog
belong to Bundle 5's scan-feedback work.

### S4 — The scan flash becomes an animation on the document

Today a scan flashes `table_frame`'s border for 300ms
(`main_window.flash_border`). That frame is one of the widgets this bundle
deletes.

The owner's ruling: **animation on the web tier is allowed.** ADR 0001 carried
over Shopify's guardrail list, where animation was an open question rather than
a decision; `shared/style_lint.py` bans `transition`, `transform`,
`scale/rotate/translate`, `opacity`, gradients and `box-shadow` — and does not
mention `animation` or `@keyframes`.

So the flash is a `@keyframes` pulse over `border-color`, on the document
column (`.doc-main`) — today's cue is a border on the frame around the whole
table, and that is the element it becomes. The column carries a permanent
`2px solid transparent` border so a flash shifts no layout, and the feedback
band keeps its own static role colour, so the text stays readable the whole
time. No `transition`, no `transform`, no `opacity` — the lint stays as it is,
`shared/` is not touched, and the ADR's guardrail list stays true as written.

`flash_border`'s three call colours map onto a role name:
`green → success`, `orange → warning`, `red → danger`.

## Architecture

### The seam

```
main_window.py ── existing public methods ──► PackerModeWidget (Qt chrome + model)
      ▲                                                   │ properties
      └──────── existing signals ◄── PackerBridge ◄────────┘
                                          │  slots
                                   packer.js (QWebChannel)
```

**`PackerModeWidget` keeps the API it has today.** Every public method keeps its
name and signature — `display_order`, `update_item_row`, `show_notification`,
`update_raw_scan_display`, `add_order_to_history`, `update_session_progress`,
`show_extras_panel`, `clear_screen`, `set_focus_to_scanner` — and every signal
keeps its name and payload, `cancel_item_requested(int)` and
`force_confirm_requested(int)` included, row indices unchanged. `main_window.py`
therefore changes only where it reaches into a widget this bundle deletes:
`flash_border`'s `table_frame` and `scanner_input.setEnabled(False)`.

**The widget owns the document's model.** Today per-item state lives in the
`QTableWidget`'s cell text: `update_item_row` parses `"1 / 2"` back out of a
cell, and `_refresh_summary_from_table` rebuilds the summary by re-reading the
grid. A web view cannot be read back synchronously, so the widget holds the
model — items, extras, history, progress, feedback — mutates it in those same
public methods, and pushes it over the bridge. The text parsing goes away with
the table.

### `gui/packer_bridge.py`

Modelled on `gui/results_bridge.py` in shopify-fulfillment-tool: one channel
object, every message its own named member, state out as a notify `Property`
(so a page that connects late needs no handshake), reports in as a `Slot`.
Channel members are camelCase because JS calls them.

Python → JS properties: `themeCss`, `banner`, `feedback`, `items`, `extras`,
`history`, `progress` — seven, and no eighth for "which state is the document
in": an empty `items` list is already what tells the page to hide the list, so
a separate state name would be a second record of the same fact. The state
panels that would need one are Bundle 5's. JS → Python slots and the signals they
emit: `confirmItem`/`undoItem`/`forceItem` (row), `mapSku` (sku),
`keepExtra`/`removeExtra` (normalised sku) — six, matching the six actions the
document draws; nothing for Exit, which stays a Qt button until Bundle 5 gives
P8 its own. One JS-facing signal, `scanFlashed(str role)`, for S4.

`mount_packer_page(view) -> PackerBridge` mirrors `mount_results_page`: build
the bridge and channel parented to the view, write `theme_css_vars()` over the
page's `/* theme-vars */` marker before the first paint, then push it again on
every `on_theme_changed` so a theme or density switch repaints without a reload.

**No `shared/` extraction.** The roadmap allows lifting the generic part of the
mount into `shared/` "only if both bridges use it". After the theme push — which
is already shared — what is left is about six lines of `QWebChannel` wiring. A
shared helper for that would cost an edit to `shared/`, a `sync_shared.py` run,
and a second repo's PR to adopt it. Not worth it; the ADR forbids a third web
screen without a new ADR, so there is no third caller coming.

**Payload building is pure and module-level**, so the numbers are testable with
neither Qt nor Chromium running — the seam `gui/orders_view.order_payload`
occupies in Shopify:

- `item_rows(items, order_state, sku_map) -> list[dict]` — one row per order
  item: `{row, product, sku, required, packed, state, just_changed, confirm,
  undo, force, map}` — `state` is `"pending" | "partial" | "complete"`, and the
  last four are S2's action flags, flat rather than nested so the payload
  survives the QVariant round trip unchanged. JS renders what this decides and
  decides nothing itself.
- `banner_chips(metadata) -> dict` — `{order, chips: [...], notes}`, carrying
  over `_update_metadata_banner`'s `nan`-and-empty cleaning verbatim.
- `summary_lines(items, order_state) -> dict` — unique SKUs packed/total and
  items packed/total, replacing `_update_summary_panel` and
  `_refresh_summary_from_table` with one function over the model.

### `gui/web/packer.html`, `packer.css`, `packer.js`

- **HTML** is the artboard's `.doc` subtree: `.doc-main` holding `.doc-banner`,
  `.feedback`, `.extras`, `.sku-list`, and `.side` holding the three
  `.side-block`s. One `<style id="theme-vars">/* theme-vars */</style>`, one
  stylesheet link, `qrc:///qtwebchannel/qwebchannel.js`, then `packer.js`.
- **CSS** is `docs/design/phase10/packer-document.css` lifted as-is, plus the
  `.btn`, `.chip` and `.state-panel` rule sets `HANDOFF.md`'s A3 note asks for,
  lifted from `docs/design/phase10/artboard.css`. Plus the S4 keyframes. Every
  `var(--…)` it uses is already emitted by `theme_css_vars()` — checked, all 55
  names — so no theme token is added. `.frame--1920`'s `--side-width` override
  becomes a plain media query at 1600px.
- **JS** is one render function per region plus the `QWebChannel` bootstrap from
  `results.js`: read each property, connect its `…Changed` signal, set
  `document.documentElement.dataset.bridge = "ready"` when wired (the handle the
  tests wait on). No sort, no filter, no windowing — the list is one order.
  Row actions are delegated clicks that call a slot; the page holds no state
  beyond what it last rendered.

### The scanner invariant (D3)

- `view.setFocusPolicy(Qt.NoFocus)`, and the same on `view.focusProxy()` at
  mount time, since the proxy is the widget that actually takes a click.
- Every bridge slot ends in `set_focus_to_scanner()`, exactly as today's button
  handlers do.
- Regression test: click inside the view with `QTest`, then send a keystroke
  sequence and Enter, and assert `barcode_scanned` fired with the typed text.
  Never skipped — CI runs the suite on `windows-latest`, where Chromium needs no
  extra runtime packages.

### Confirmations

`_on_force_confirm` keeps a confirmation, through
`shared.components.confirm_dialog.ConfirmDialog` (verb "Force confirm") rather
than a raw `QMessageBox` — it is the component the rest of the app confirms
with, and a modal is a top-level popup, so it paints above the web view.

`_on_cancel_item` loses its confirmation. Undoing one scan is reversible by
scanning again, and `ConfirmDialog`'s own contract is that an undoable act never
confirms.

## What Bundle 4 deletes

From `packer_mode_widget.py`: `table`, `table_frame`, `FRAME_DEFAULT_STYLE`,
`_make_actions_widget`, `metadata_banner` and the `_meta_*_lbl` chips,
`history_table`, `extras_panel`/`extras_table`/`_extras_section_title`,
`summary_frame`/`summary_table`, `main_tabs`, `session_progress_bar`,
`packed_stat_label`, `items_stat_label`, `status_label`, `notification_label`,
`raw_scan_label`, `scan_info_frame`, `_refresh_summary_from_table`.

Kept, unplaced, for Bundle 5: `scanner_input`, `skip_order_button`,
`exit_button`, the sim `QGroupBox`.

In `main_window.py`: `flash_border`'s `table_frame` styling becomes
`bridge.scanFlashed`; `scanner_input.setEnabled(False)` stays (the widget still
owns the scanner).

## Packaging

- **No new dependency.** The roadmap's item 0 says to add
  `PySide6-QtWebEngine` to `requirements.txt`. It is not needed:
  `requirements.txt` installs the `PySide6` metapackage, which depends on
  PySide6-Addons, which ships QtWebEngine — `PySide6.QtWebEngineWidgets` imports
  today (verified, PySide6 6.11.2). shopify-fulfillment-tool made the same call
  and guards it with `tests/test_webengine_available.py` plus a comment on the
  requirement. Bundle 4 copies that guard and comment. Adding a line for a
  package nothing installs separately would be a second, silently drifting
  record of the same fact.
- **`main.spec` needs `('gui/web', 'gui/web')` in `datas`.** Shopify passes
  `--add-data "gui/web;gui/web"` on a CLI PyInstaller call; this repo builds from
  `main.spec`, so without this the page is simply absent from the frozen build
  and the view loads nothing.
- **`.github/workflows/build-release.yml`**: `QtWebEngineProcess.exe` and
  `packer.html` join `package.svg` and `Inter-Regular.ttf` in the
  "Verify bundled assets shipped" step. Same failure shape the step already
  guards — a missing helper process is invisible until someone opens the view
  over RDP after a full build and download.

## Test seams

| Seam | Test | Needs |
|---|---|---|
| Payload functions (`item_rows`, `banner_chips`, `summary_lines`) | `tests/test_packer_payload.py` | nothing |
| Bridge over a real Chromium — theme marker once, rows render, a slot reaches the widget's signal | `tests/test_packer_bridge.py` | QtWebEngine (pattern: Shopify `tests/test_results_bridge.py`) |
| Scanner keeps focus after a click in the view (D3) | `tests/test_packer_scanner_focus.py` | QtWebEngine |
| QtWebEngine stays installed | `tests/test_webengine_available.py` | nothing |
| No hardcoded colour or size in the new web assets | existing `tests/test_style_literals_guard.py` — `gui/` is already in its scope | nothing |

## D7 — bugs in the touched code

Fix what this bundle's own code reveals, with a regression test, per D7. Two
candidates already visible:

- `update_item_row` re-derives `required` by parsing the quantity cell's text
  and falls back to `1` when the parse fails, which silently completes a
  multi-quantity row. Moving state into the model removes the parse entirely.
- `_refresh_summary_from_table` recomputes the summary from displayed text on
  every scan; `summary_lines` over the model replaces it.

Bugs found outside this bundle's code become GitHub issues, not scope.

## Non-goals

- The P1 and P8 state panels and the unmatched-scan row — Bundle 5.
- Placing the scanner field, Skip, Exit and the sim group per the artboard —
  Bundle 5. They keep today's positions in this bundle.
- Any change to `shared/`, to session file formats, or to the
  Shopify↔Packing contract.
- No third web screen (ADR 0001).
