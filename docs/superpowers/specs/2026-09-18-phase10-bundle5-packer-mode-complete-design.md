# Phase 10 Bundle 5 — Packer Mode complete

**Status:** owner-approved on the four scope questions below, 2026-09-18.
**Parent spec:** `docs/superpowers/specs/2026-09-17-phase10-packer-v2-design.md`.
**Predecessor:** `docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md`
(its S1 rewrote what Bundle 5 is; read that section before this one).
**Roadmap:** `docs/superpowers/plans/2026-09-17-phase10-packer-v2-roadmap.md`, Bundle 5.
**ADR:** `docs/adr/0001-packer-mode-on-the-web-tier.md`.
**Mockup (the brief):** `docs/design/phase10/packer-mode.html` frames P1–P8, with
`docs/design/phase10/packer-document.css`, `artboard.css` and `HANDOFF.md`.

## Goal

Packer Mode becomes the screen the artboard draws. Bundle 4 moved the document
onto the web tier; what is left is the Qt chrome around it, the one drawn state
the document cannot yet reach, the unmatched-scan row Bundle 4's S3 deferred,
and the copy.

After this bundle: the scanner is a visible 44px field in a 60px command bar
with Skip and Exit beside it, a finished session says so in place instead of
through a modal, an unmatched scan gets a row and a way to map it, and every
string on the screen is the artboard's rather than a shouted capital.

## Scope decisions (owner, 2026-09-18)

### S1 — P1 "No session open" is dropped, not built

No code path reaches it. `packer_mode_button` is disabled until
`enable_packing_mode()` runs, and `end_session()` ends with
`setCurrentWidget(self.session_widget)` — commented "avoids leaving a blank
packer mode screen" (`main_window.py:1901`). So Packer Mode is never on screen
without a session, and P1's panel would be code nothing can show.

The roadmap's "every state drawn in Bundle 2 is reachable" does not hold for P1
and this is the recorded departure. The owner rejected making it reachable:
stopping on P1 when a session ends would add a click to every session end to
honour a drawing.

`.state-panel`'s CSS is already in `packer.css` (Bundle 4 lifted it) and P8
uses it. Nothing is wasted.

### S2 — P8 replaces the modal, and ends the session

Today `all_orders_complete` → `_on_all_orders_complete` → a deferred
`QMessageBox.question("All orders have been packed!\nEnd session now?")`, whose
Yes calls `end_session()` (`main_window.py:2223-2255`). That modal is how a
finished session gets ended from the floor.

The modal goes. P8's panel takes its decision:

| Button | Role | Does |
|---|---|---|
| End session | primary | `MainWindow.end_session()` — the modal's Yes, unchanged |
| Exit packing | ghost | `exit_packing_mode` — the modal's No, session left open |

This departs from the artboard, which draws one button labelled "Exit packing".
`HANDOFF.md`'s "P8 / T2 duplicate primary action" note invites exactly this
reconsideration ("Reject this together with S4's pattern if it doesn't hold up
in Bundle 5/6"). The drawing's single Exit would leave no way to end a session
from the screen that announces it is over — a state panel that explains a
situation without offering the fix, which is the dead end that note argues
against.

The command bar's own Exit stays where it is and keeps its own behaviour; that
duplication is the one `HANDOFF.md` sanctions.

### S3 — the unmatched-scan row maps by picking one of the order's SKUs

`PackerLogic.unknown_scans` holds the raw text of every scan in this order that
matched no item and no mapping (`packer_logic.py:1169`), cleared with the order
by `clear_current_order()`. Today only the feedback text mentions them.

They become `.sku-row--unknown` rows after the item rows: product "Unknown SKU",
the raw barcode in the SKU cell, `—` for quantity, chip "No match", one action,
**Map SKU**.

That action needs the reverse of today's dialog. `_on_map_sku_from_packer`
knows the SKU and asks for the barcode (`QInputDialog`); here the barcode is
known and the SKU has to be picked. So: a dialog listing this order's lines,
unpacked first, with the scanned barcode shown. Picking one saves the mapping
and **replays the scan**, so the item is packed in the same gesture — the scan
already happened, and making the packer scan again to use a mapping they just
made is a step with no purpose.

An unmatched scan in the order document is by construction a scan made while
packing this order, so its SKU is almost always one of these lines. If it is
not, the packer picks nothing and cancels.

### S4 — the amber quantity cue comes back, and fades when the line is done

The old table tinted the quantity cell with `status_warning_bg` /
`status_warning` on any line with `Quantity > 1` — feature `[C]`, at
`gui/packer_mode_widget.py:501-505` before Bundle 4. The web document dropped
it; the mockup sanctions the drop but it is a floor-visible cue and was not on
Bundle 4's deletion list.

It returns as `.sku-row__qty--multi` on rows where `required > 1` **and**
`packed < required`. The cue means "this line needs more than one scan", which
stops being news once the line is complete — so a finished 3 / 3 row is plain,
and the tint does not compete with the row's own completion colour.

## Also in scope

### A1 — the Qt chrome, per the artboard

`PackerModeWidget`'s layout today is an `QHBoxLayout` of a left column (the
document, a 1×1 hidden scanner) and a right column (sim group, Skip, a stretch,
Exit). It becomes a `QVBoxLayout`: a 60px command bar, then the document.

The bar, left to right: an order label, the scanner field, the sim group when
sim mode is on, a stretch, Skip order, Exit packing.

- **The scanner field is `scanner_input`, grown up.** The same `QLineEdit`, now
  ~280px wide at `control_height`, placeholder "Ready to scan". It already
  holds keyboard focus and already gets disabled after an order completes
  (`main_window.py:2083`), so it draws the artboard's `field--placeholder
  field--focus` and `field--disabled` states with no second widget and no new
  state to keep in sync. D3's invariant is unchanged: the field the scanner
  types into is still the one with focus, and it is now visible enough for a
  packer to see that.
- **No fourth `CommandBar` page.** `gui/command_bar.py` carries a client combo,
  a session label, a filter input, four buttons and an overflow menu, all
  aliased by `MainWindow`; Packer Mode wants none of them. A fifth page mode
  would hide six widgets to show three. Packer Mode builds its own bar and
  shares only what is actually common: `BAR_HEIGHT` and a module-level
  `bar_css(tokens)` in `command_bar.py` that both bars' stylesheets use, so the
  60px row, its `surface_raised` ground and its bottom border have one
  definition. Two callers, one rule set — the seam is real, not hypothetical.
- **The order label** shows `#<order>` while an order is open, "No order"
  between orders, and "Session complete" at P8. It is the only new widget the
  bar needs.
- **The sim group** keeps its `QGroupBox`, restyled to the artboard's
  `.sim-group`: dashed `status_warning` border, the label "DEV", the input, and
  a "Simulate scan" button. It sits inline in the bar rather than in a right-hand
  column. The artboard draws it only at 1920; at 1366 it simply makes the bar
  tight, which is a dev-only concern.

### A2 — the copy

Every string the artboard draws is sentence case and says what to do next. The
app sends eight shouted capitals into the same band. The artboard is the brief,
so they change:

| Today (`main_window.py`) | Becomes |
|---|---|
| `ITEM OK` | `<sku> confirmed — <packed> of <required> packed` |
| `INCORRECT ITEM!\n<detail>` | `Unknown SKU <scan> — scan again or map it` |
| `ORDER <n> COMPLETE!` | `Order #<n> packed. Scan the next order.` |
| `Scan the next order's barcode` | `Scan an order barcode` |
| `EXTRA ITEM!` | `Extra item scanned — keep it or remove it` |
| `REVIEW EXTRA ITEMS!` | `Review the extra items before this order can close` |
| `ORDER <n> ALREADY COMPLETED` | `Order #<n> is already packed` |
| `ORDER NOT FOUND` | `No order matches <scan>` |
| `Already at 0!` | `Nothing packed on that line yet` |

The first four are the artboard's own words. The rest follow its voice: what
happened, then what to do, in the same sentence case. The two strings already
in that voice ("Extra cleared — continue scanning", "Mapped: … → …") stay.

The `\n` in the old danger string goes with it: the band is one row, and the
unknown-scan count it carried is now visible as rows in the list.

**P8's sentence**: `<packed> of <total> orders packed`, then `, <n> skipped`
only when any were, then `, <items> items`, then `, in <duration>`. Every
number is already in `MainWindow`'s reach —
`session_packing_state["completed_orders"]` and `["skipped_orders"]`,
`len(logic.orders_data)`, `sum(o["items_count"] for o in
logic.completed_orders_metadata)` and `logic.started_at`. No new `PackerLogic`
API.

### A3 — retiring what is left

Bundle 4 deleted the tables and labels. What remains is the layout that held
them: the left/right `QWidget` split, `scan_row`, and the right column's
stretch. `QGroupBox` stays (the sim group), `QVBoxLayout`/`QHBoxLayout` stay.

`main_window.py` loses `_show_all_complete_dialog` and the `QMessageBox` import
if nothing else uses it.

## Architecture

The seam is Bundle 4's, extended by one property and one slot:

```
main_window.py ── public methods ──► PackerModeWidget (Qt bar + model)
      ▲                                        │ properties
      └──────── signals ◄── PackerBridge ◄──────┘
                                 │  slots
                          packer.js (QWebChannel)
```

### `gui/packer_bridge.py`

- **New property `sessionEnd`** (`QVariantMap`): `{}` while packing, and
  `{title, body}` when the session is over. The page shows the state panel when
  it is non-empty and the item list when it is not — one fact, one place. This
  is the eighth property Bundle 4 declined to add speculatively; it is added now
  because a state the document cannot otherwise distinguish needs it (S2 of
  Bundle 4's spec said exactly this).
- **New slots `endSession()` and `exitPacking()`**, emitting
  `endSessionRequested` and `exitPackingRequested`. P8's two buttons are the
  document's first actions that are not about one row.
- **`item_rows` gains `multi`** — `required > 1 and packed < required` (S4) —
  and prefers `order_state`'s own `required` over the packing list's
  `Quantity` when the state entry carries one. `PackerLogic` decides completion
  from `order_state['required']` (`packer_logic.py:1027, 1038, 1096`), so on a
  resumed session whose saved state and packing list disagree, the document
  must agree with the logic or it lies about which lines are done. Fallback
  stays `max(_int(item["Quantity"]), 1)`.
- **New payload function `unknown_rows(scans) -> list[dict]`** — one row per
  unmatched scan, in scan order, de-duplicated (the same wrong barcode scanned
  three times is one row to map). It emits **the same dict shape `item_rows`
  does**, with `state: "unknown"`, `row: -1` and `mapBarcode: True`, and the
  widget concatenates the two lists into the existing `items` property. So
  there is no ninth property, the list stays one list in one scroll container,
  and the page needs no branch beyond the quantity cell's `—`. Pure,
  module-level, tested without Qt.
- **New payload function `session_end_payload(...) -> dict`** — S2's sentence
  from counts, so the plural rules and the omitted-when-zero clause are
  testable without a browser or a session.

### `gui/packer_mode_widget.py`

One new public method, in the shape the existing ones already have:
`show_session_complete(payload: dict)` — pushes `sessionEnd`, disables the
scanner field and Skip, and sets the order label to "Session complete". The
order label needs no setter of its own: `display_order` and `clear_screen`
already know when the order changes.

`clear_screen()` clears `sessionEnd` too, so a restored or restarted session
comes back to a document that is packing rather than finished.

Two new signals, for the actions the document gained: `end_session_requested`
and a **`map_barcode_requested(str barcode)`** for the unknown row. The
existing `map_sku_requested(str sku)` stays for the per-item button — the two
dialogs ask opposite questions, and one signal carrying whichever half the
caller happens to have would leave the receiver guessing which it got.

Both `Map SKU` dialogs are opened by `MainWindow`, not the widget: the picker
needs `profile_manager`, `current_client_id` and the order's items to save a
mapping, and `_on_map_sku_from_packer` already lives there. The widget forwards
the barcode and nothing else, as it forwards a row index today. (The
force-confirm `ConfirmDialog` stays in the widget; it needs no application
state.)

### `gui/web/packer.js`, `packer.css`

- `renderItems` appends `unknown` rows after the item rows, and
  `renderSessionEnd` toggles `.doc-state` on `.doc-main` with the panel's two
  buttons.
- **The duplication Bundle 4's handoff flagged gets collapsed here**, because
  this is the bundle that adds the third caller: one `rowEl(cells, actions)`
  helper behind `renderItems`, `renderExtras` and the unknown rows, and one
  `dataset.action` → slot table instead of the `if/else` cascade repeated in
  two listeners. Three callers, so the helper is not speculative.
- CSS additions: `.doc-state` (the one rule `packer-document.css:230` has that
  `packer.css` does not), and `.sku-row__qty--multi`. Nothing else: the
  `.state-panel`, `.sku-row--unknown` and `chip--tint` rules are already there.

### Scrolling with the panel

Bundle 4's review found the SKU list needed `overflow-y: auto`. The state panel
replaces the list rather than joining it, so it adds no scroll case of its own —
but the unknown rows extend the list, so **the 20-item check runs with unknown
rows present**, not only with item rows.

## Test seams

| Seam | Test | Needs |
|---|---|---|
| `unknown_rows`, `session_end_payload`, `item_rows`' `multi` flag and `required` precedence | `tests/test_packer_payload.py` (existing) | nothing |
| The panel shows, the list hides, its two buttons reach the widget's signals | `tests/test_packer_bridge.py` (existing) | QtWebEngine |
| Unknown rows render with Map SKU; the mapped pick reaches `map_barcode_requested` | `tests/test_packer_bridge.py` | QtWebEngine |
| The scanner still gets the scan after a click in the view, now that the field is visible and in a different parent | `tests/test_packer_scanner_focus.py` (existing) | QtWebEngine |
| `bar_css` used by both bars; the bar is 60px | `tests/test_packing_density.py` (existing) | nothing |
| No hardcoded colour or size in the new assets | `tests/test_style_literals_guard.py`, `tests/test_style_lint.py` (existing) | nothing |

The `_eval()` helper in `test_packer_bridge.py` routes results through
`JSON.stringify` — this build's `runJavaScript` returns `''` for a JS array.
New array assertions must use it.

## D7 — bugs in the touched code

- The `required` precedence above is one (S2 of the PR #180 review's owner
  list).
- `_on_cancel_item`'s "Already at 0!" branch is unreachable from the UI now that
  Undo only renders when `packed > 0`, but it stays as a guard: a stale row
  index from a page that has not re-rendered can still reach the slot. Only its
  string changes.
- Anything else this bundle's code reveals, with a regression test. Bugs outside
  it become GitHub issues.

## Non-goals

- P1's panel (S1).
- Session-wide item totals in the side column. The block is titled "Session
  progress" and its item numbers are the current order's, as the Qt summary
  table's were before Bundle 4; the artboard's sample numbers imply session
  totals but no session item accounting exists to feed them. If the owner wants
  it, it is its own item — it needs a running total `PackerLogic` does not keep.
- Session Browser, Statistics, the Packing table view — Bundle 6.
- Any change to `shared/` beyond none, to session file formats, or to the
  Shopify↔Packing contract.
- No third web screen (ADR 0001).

## Merge gate

The owner checks on Windows that a real scanner still scans with the visible
field in the bar, and that a finished session shows P8 and ends from it.
