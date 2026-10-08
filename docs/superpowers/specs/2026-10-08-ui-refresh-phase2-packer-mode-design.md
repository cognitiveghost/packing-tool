# UI refresh phase 2: Packer Mode to the mockup, and the floor web kit

- **Date:** 2026-10-08
- **Mockup followed:** `docs/design/ui-refresh/mockups/Packer Mode.html`, frames 6a to 6j, and
  `Floor Components.html` (1a, 1b) for the floor sizes. Every departure is in section 9.
- **Decisions it rests on:** ADR 0001 (scanner invariant, web-asset guardrails), ADR 0002 (every screen on
  the web tier; `shared/` is never edited here).
- **Depends on:** phase 1 (merged, PR #198) and Fulfilment PR #372, which put `web_page.py`, `web/kit.css`
  and `web/page.js` into `shared/`. This repo's `shared/` is already pinned to that commit (`387efef`).

## 1. What this is for

Packer Mode is the screen a packer looks at all shift, from arm's length, with a scanner in one hand. It
already renders on the web tier, but on its own bridge plumbing and its own copy of the button, chip and
panel styles, drawn to an older artboard. This phase moves it onto the page base and kit both apps share,
restyles it to the approved mockup, and leaves behind the floor-density sheet phases 3 to 5 build on.

It is a restyle. What the screen says and what each action does stay as they are, with five exceptions: the
unsaved warning becomes a banner (6i), the Force confirm question and the lock-lost notice are drawn in the
page (6f, 6j), the band names the order when one opens (6b), and one bug is fixed first (section 3).

**Done when:** the page holds no input element of any kind; the view is still `NoFocus`; the
scan-after-click regression test passes; each of 6a to 6j has a test and a render in both themes; and
section 9 lists every departure from the mockup.

## 2. Owner decisions (2026-10-08, runner question 65)

1. **Old frame on re-entry.** A hidden web view keeps its last painted frame and shows it when it comes
   back. Packer Mode therefore leaves only after the cleared page has painted, 150 ms at most. Fulfilment's
   stack-all fix is not used here: a Qt page would sit over a live web view, and that fix hands focus to
   the web view on a switch.
2. **Force confirm** is asked in the page. While the question is open the scanner is off.
3. **Row actions** keep today's rules in four fixed slots: an act that never applies to a row leaves its
   slot empty, one that does not apply right now is drawn disabled.

## 3. Fixed first: a finished order's reset closes the order opened after it

`MainWindow._handle_order_completion` disables the scanner and schedules `clear_screen` 3 s out. Nothing
cancels that timer. If another order is on screen when it fires (the dev simulator, a replayed scan, or
leaving and re-entering Packer Mode inside the 3 s), the document is wiped while `PackerLogic` still holds
the order open. Fulfilment PR #372 reported it as "one unmatched scan closed the open order".

The fix puts the timer where the two things it races live. `PackerModeWidget.clear_screen_later(ms)` owns
one single-shot timer; `display_order()` and `clear_screen()` stop it. `MainWindow` calls
`clear_screen_later(ORDER_CLEAR_MS)` and no longer touches the scanner field. A failing test at the
`MainWindow` seam comes first.

## 4. The web base

### 4.1 Bridge

`PackerBridge` extends `shared.web_page.PageBridge`. It drops its own `themeCss` and inherits the revision
and the painted report. It keeps its named properties: QWebChannel sends one message per batch of changes,
so one snapshot property would buy nothing and cost every test its seam.

Three properties are added:

| Property | Type | Empty | Carries |
|---|---|---|---|
| `unsaved` | bool | `false` | state writes are failing (6i) |
| `question` | map | `{}` | the open Force confirm question: `row`, `sku`, `product`, `remaining`, `required` (6f) |
| `takeover` | map | `{}` | the lock was taken: `holder`, `list` (6j) |

One slot is added, `answerQuestion(bool)`, emitting `questionAnswered(bool)`. `forceItem(row)` stays: it
now asks Python to open the question instead of acting.

`item_rows()` gains `force_slot` (`required > FORCE_CONFIRM_MIN_QTY`), so the page can tell "never" from
"not now". It loses `multi` (section 9, row 9). A pure `force_question(row)` builds the question payload.

### 4.2 Mount

`mount_packer_page` calls `shared.web_page.mount_page(view, bridge, PAGE, "packer",
tokens=gui.theme.current_tokens)` and keeps `deny_focus` before the load and on every `loadFinished`. That
second call matters more now: a page whose render process died is loaded again by `mount_page`, and the
reloaded page gets a new focus proxy.

`packer.html` loads, in order, `../../shared/web/kit.css`, `floor.css`, `packer.css`, then
`qwebchannel.js`, `../../shared/web/page.js` and `packer.js`. `packer.js` calls `reportPaints(bridge)`.

Not adopted: `switch_theme` and the `themeApplied` acknowledgement. The sidebar is hidden in Packer Mode,
so the theme cannot change while this page is visible. `keep_pages_painted` is not adopted either
(decision 1). Both arrive with the first page that needs them.

### 4.3 Leaving after the page has painted

`MainWindow` gets one way out of Packer Mode, used by *Exit packing* and by session teardown. It pauses the
scanner, and if Packer Mode is the visible page it calls `when_painted(bridge, switch)`; otherwise it
switches at once. `switch_to_packer_mode` resumes the scanner. The scanner is paused during the wait so a
scan cannot open an order on a page that is about to be covered.

A session's state pushed while the page is hidden (a resumed session's counts) is painted when the page is
shown, so it can appear one frame late. It is never another session's data: the frame the view kept is the
cleared one.

### 4.4 Build

`main.spec` adds `('shared/web', 'shared/web')` to `datas`. The release workflow's bundle check adds
`kit.css` beside `packer.html`.

## 5. The sheets

**`gui/web/floor.css`** is the floor density over the kit, with no page in it. Control height (44px), body
(12pt) and caption (10pt) already reach the web tier through `theme_css_vars()` in the floor profile, so the
sheet holds only what the kit sizes for the office:

- buttons: 18px side padding; `.btn.compact` is the floor's smaller button, 40px with 12px padding; a ghost
  button is underlined;
- badges: 28px, 12pt, 14px radius; the neutral badge carries a strong border so it reads without colour;
- banner: centred, 14px gap, 12px by 16px padding, a 24px glyph, a 14pt danger title;
- the taking-over panel: `.scrim` (the theme's `scrim` over the whole page) and `.dialog` (overlay plane,
  12px radius, the theme's overlay shadow, 28px padding), with `.dialog-title` and `.dialog-actions`.

Phases 3 to 5 add table rows, inputs and the toast to this sheet when a page first uses them.

**`gui/web/packer.css`** keeps only Packer Mode's own: the two-column grid, the order card, the band, the
flash, the list and its rows, the side column, and the session-complete panel's sizes. Its copies of
`.btn`, `.chip`, `.card` and `.state-panel`'s base rules go. Sizes off the type scale (20, 26 and 30pt) are
custom properties at the top of the sheet.

## 6. The page, frame by frame

Layout: a grid of `minmax(0, 1fr)` and 248px. The main column has 16px 20px 20px padding and a 14px gap;
the side column 16px 16px 20px 4px. At 1920px the product column takes the extra width; nothing else moves.

**6a, waiting.** The band is solid `status_info` with "Scan an order barcode". The list card says "No order
open". The order card is hidden. *Skip order* is disabled.

**6b, order open.** The band says "Order #10407 · 5 items" in info; today it is left empty until the first
item scan, which the solid band would show as a blank block. The order card: today's chips as neutral badges, the notes behind a message glyph, and
*Repeat* as a warning badge at the right. It is hidden when an order has none of them. The list has a 36px
head (SKU, Product, Packed, Status) and 64px rows on the grid `150px minmax(0,1fr) 128px 116px 448px`:

- SKU in mono, bold; product in 14pt;
- the packed count as a 26pt bold numeral with "of N" at 14pt beside it;
- a badge: *Pending* neutral, *Partial* info, *Complete* success;
- four action slots, always in this order: *Confirm*, *Force confirm* (secondary, compact), *Undo*,
  *Map SKU* (ghost, compact). *Confirm* and *Force confirm* are disabled on a complete row, *Undo* at zero.
  *Force confirm* is absent under 6 units and *Map SKU* is absent on a mapped SKU; an absent slot keeps its
  width, so the columns line up down the list.
- A complete row goes quiet: raised ground, secondary text, normal weight.

**6c, correct scan.** The band turns solid `status_success` with today's sentence, and the raw scan sits at
the right under a 10pt "Scanned" label in 20pt mono. The scanned row takes `status_success_bg`, a 6px
`status_success_dot` bar on its left, and a success-coloured numeral. The flash is a 10px frame on the main
column's edge, pulsing twice over 900 ms and clearing, animated on `border-color` only.

**6d, not in this order.** Warning band and flash, as today's "Extra item scanned" is a warning. Below the
item rows: an "Extra items scanned" strip on `status_warning_bg`, then one row per extra with the SKU,
"× N" as a 26pt numeral, an *Extra* warning badge, and *Keep* / *Remove*.

**6e, unmatched scan.** Danger band and flash, as today. Below the extras: one row per unmatched barcode on
`status_danger_bg`, with a *No match* danger badge, the barcode in 17pt mono, "Not a SKU or barcode this
client knows", and *Map barcode…*, which opens today's Qt dialog.

**6f, Force confirm.** A scrim over the whole page and a 520px dialog: "Force confirm `SKU`?", "Marks the
remaining **N** of Q × Product as packed without scanning. This cannot be undone.", *Cancel* (secondary)
and *Force confirm* (the kit's critical button). The scanner field is disabled and its state reads
"Scanner disabled"; *Skip order* is disabled. Either answer closes the question and gives the scanner back.

**6g, order complete.** Every row quiet, the last one still carrying the scan's success fill. The band
keeps today's one sentence, "Order #N packed. Scan the next order."

**6h, session complete.** The main column is replaced by a centred card, 560px at most: a 48px check in
`status_success_dot`, "Session complete" at 28pt, today's sentence at 14pt, *End session* (primary) and
*Exit packing* (secondary). The side column stays. The scanner is disabled.

**6i, progress not saved.** A danger banner above the order card: the alert glyph, "Progress not saved —
check the network" and "Scanning continues". The band underneath keeps reporting scans in their own colour.
It clears when a write succeeds.

**6j, taken over.** A scrim and a 600px dialog edged in `status_danger_border`: "This list is open on
another PC", then today's sentence with the holder and the list name, and one button, *Exit packing*.
`MainWindow._on_lock_lost` stops writing and the progress publisher at once, as today. If Packer Mode is
the visible page it stops the heartbeat and shows this panel, and the session is torn down when the packer
exits, by either *Exit packing*. If another page is showing it behaves as today: teardown, then the message
box.

**Side column,** 248px, no cards, 10pt, sections divided by a `border` rule: *Session progress* (an 8px
track filled in `status_success_dot`, then "38 / 120 orders · 412 / 1,290 items"); *History* (order number
in mono and *Packed* or *Skipped*, newest first, scrolling inside 200px so it never pushes the next section
off the screen); *Items by SKU* (a state dot, the SKU in mono, "1 / 3"; "No order open" when empty);
*Summary* ("Unique SKUs packed", mono, bold).

## 7. The command bar (Qt)

The bar keeps its widgets and its 60px. Changes:

- the order number is 24pt bold mono; "No order" and "Session complete" are 17pt bold in `text_secondary`;
- the scanner field keeps its 280px and 44px, takes a 2px `selection_border` edge and 14pt mono text, and
  its placeholder becomes "Order number or SKU";
- beside it, a 12px dot and a bold label: "Ready to scan" (`status_success_dot`, `status_success`) or
  "Scanner disabled" (`text_disabled`, `text_secondary`);
- *Skip order* is disabled with no order, and while the scanner is off.

One method decides the scanner's state. It is off when the session is over, the list was taken over, a
question is open, or it is paused (the 3 s after an order completes, and while leaving). The dev simulator
refuses a scan while the scanner is off.

## 8. For shared/

To raise on Fulfilment's side. Nothing here blocks this phase.

- `band_fg` (text on a solid status fill) and `status_warning_dot`. Until then the band uses `on_accent`
  and the warning flash uses `status_warning`.
- The type scale has no rung between 17 and 28pt: Packer Mode uses 20, 24, 26 and 30pt.
- Icons `scan-barcode` and `triangle-alert`. The page draws its own inline glyphs.
- Everything in `gui/web/floor.css`, as the kit's floor density.
- `.scrim` and `.dialog` as kit components.

## 9. Departures from the mockup

| # | Mockup | Built | Why |
|---|---|---|---|
| 1 | The flash frame stays lit until the next scan | it pulses and clears | today's behaviour, and the band already holds the colour |
| 2 | The flash animates `opacity` | `border-color` | `opacity` is banned on the web tier (ADR 0001) |
| 3 | Band text in `band_fg`; warning flash in `status_warning_dot` | `on_accent`; `status_warning` | not in `shared/theme.py`. Light is identical for the text; Dark differs by a shade |
| 4 | Band sentence on one line, cut with an ellipsis | wraps, never cut | today's sentences are longer than the mockup's, and a packer acts on them |
| 5 | Band: a sentence and a hint line; "Order complete" | today's single sentences | information stays as today |
| 6 | 6d (extra) is danger and 6e (no match) is warning, in the band, the flash and the row | 6d warning, 6e danger, in all three | today's roles for those two outcomes: packers know red as "unknown barcode" |
| 7 | Every row offers all four actions | *Force confirm* only over 5 units, *Map SKU* only when unmapped, slots kept | owner decision 3 |
| 8 | Order card: customer name, courier, tags | today's chips, with no name | the packing list carries no customer name |
| 9 | (not drawn) | the warning tint on a multi-unit quantity is dropped | the 26pt "1 of 3" says it |
| 10 | Extra rows carry a product name | SKU only | an extra is a SKU and a count, nothing else is known |
| 11 | History shows the time each order was packed | *Packed* or *Skipped* | no time is recorded, and Skipped is information today |
| 12 | Secondary and disabled buttons edged in `border_strong`, no shadow | the kit's: `border`, card shadow | contrast floors and the kit win (phase 1, row 6) |
| 13 | A barcode glyph in the scanner field | none | not in `shared/assets/icons`, and the field is a Qt `QLineEdit` |
| 14 | 6j's sentence ends at "stopped packing it" | today's full sentence | it says the packed orders are saved |
| 15 | "Scanning continues · retrying" | "Scanning continues" | nothing retries on a timer; the next scan writes again |
| 16 | Segoe UI | the bundled Inter | the Qt tier's face, as in phase 1 |
| 17 | Force confirm dialog button: solid `status_danger` | the kit's `.btn.critical` | the shared destructive fill |
| 18 | Four row buttons fit a 404px column | the column is 448px, the buttons 4px apart | measured when rendering: Confirm, Force confirm, Undo and Map SKU need about 440px in Inter at 12pt bold |
| 19 | Product name on one line | up to two lines, then cut | at 1366px the narrowed column would cut most names to a few letters |

## 10. Testing

Seams, all through public surfaces:

- **Pure payloads** (`tests/test_packer_payload.py`): `force_slot`; `force_question`; `multi` is gone.
- **The page in a real Chromium** (`tests/test_packer_bridge.py`), one test per frame at least:
  6a the info band, the empty list and no order card; 6b the head, the row cells, the three badges and the
  slot rules (present, disabled, absent); 6c the band's role, the raw scan, the hot row and the flash
  setting and clearing itself; 6d extras below the items with *Keep* / *Remove*; 6e the *No match* row and
  *Map barcode…*; 6f the question showing and each button reaching `answerQuestion`; 6g a complete row's
  class; 6h the panel swap; 6i the banner following `unsaved` while the band keeps its own role; 6j the
  takeover panel with exactly one button. Plus: the page contains no `input`, `textarea`, `select` or
  `contenteditable`; the page reports the revision it painted.
- **`PackerModeWidget`** (`tests/test_packer_mode_widget.py`): the scanner's state label and enabled state
  for each of the four reasons; a Force click opens the question and emits nothing; *Force confirm* emits
  the row and *Cancel* emits nothing, and both give the scanner back; `set_unsaved` no longer rewrites the
  band; `show_takeover`; `clear_screen_later` is cancelled by `display_order`; the simulator refuses a scan
  while the scanner is off.
- **`MainWindow`** (`tests/test_packer_mainwindow_seam.py`, `tests/test_session_lock_loss.py`): the section
  3 regression; a lost lock in Packer Mode shows the panel and keeps the session until exit, then tears
  down; a lost lock elsewhere is unchanged; leaving Packer Mode switches only after the painted report.
- **Scanner invariant** (`tests/test_packer_scanner_focus.py`): unchanged, and repeated with the question
  open and after a page reload.
- **Guards:** `tests/test_style_literals_guard.py` already scans `gui/web`.

**Renders.** `scripts/render_packer_mode.py` drives a `PackerModeWidget` offscreen through its public
methods and writes `docs/design/ui-refresh/renders/phase2/<frame>-<theme>.png` for 6a to 6j in Light and
Dark at 1366×768, and `6b-<theme>-1920.png` at 1920×1080. The implementer looks at every PNG beside its
mockup frame before the PR, and the PR embeds them.

## 11. Out of scope

- *Map SKU* and *Map barcode…* dialogs (phase 5).
- The Packing, Statistics and Sessions pages, the toast on the web tier, `switch_theme`,
  `keep_pages_painted`.
- Any edit under `shared/`.
- New information on the screen: per-order times, customer names.

## 12. Docs touched

`CONTEXT.md`: **Feedback band** (solid fill; the unsaved warning is no longer part of it), **Scan flash**
(a frame on the main column), **Force confirm** (asked in the page, scanner off), **Order document** (adds
the unsaved banner and the taking-over panel), and a new **Floor web kit** entry for `gui/web/floor.css`.
