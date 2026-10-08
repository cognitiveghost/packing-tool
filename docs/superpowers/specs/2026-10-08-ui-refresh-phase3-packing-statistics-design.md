# UI refresh phase 3: Packing and Statistics on the web tier

- **Date:** 2026-10-08. dev-runner run 74, Todoist task "UI refresh phase 3" (3 of 5).
- **Mockup followed:** `docs/design/ui-refresh/mockups/Packer App.html`, frames 3a to 3g (Packing), 4a to 4c
  (Statistics), 5a and 5b (both at 1920×1080). Frame ids are defined in `Packer Screens.html`. Every
  departure is in section 11.
- **Decisions it rests on:** ADR 0001 (web-asset guardrails), ADR 0002 (every screen on the web tier;
  `shared/` is never edited here), and ADR 0003, written with this spec (the shell's pages are one web
  document).
- **Depends on:** phase 2 (merged, PR #199): `gui/web/floor.css`, `PackerBridge` on `shared.web_page`.

## 1. What this is for

Packing is where a packer checks what a list holds before starting, and Statistics is where a lead reads
how far it has got. Both are Qt widgets in the new shell, drawn to an older design: a tree, a caption line
and a row of stat cards. This phase redraws them to the approved mockup as one web document, and deletes
the Qt widgets they replace.

**Done when:** each page has a freshness test (state pushed while the view is hidden, the view shown, the
current revision painted, nothing of the previous session in the DOM); renders of 3a to 3g, 4a to 4c, 5a
and 5b in both themes are in the PR; section 11 lists every departure; the Qt order tree, its state panel
and `gui/statistics_widget.py` are gone; and the suite passes.

## 2. Owner decisions (2026-10-08, runner question 67)

1. **Failed start.** Every failed session start is shown in the page as frame 3c, with its own sentence,
   *Retry* and *Close*. The message boxes for it go.
2. **Filter.** *Filter orders* matches order number, SKU or product name, as today.
3. **Old frame.** *Start packing* blanks the document and waits for that paint (150 ms at most) before
   Packer Mode covers it, so the frame the hidden view keeps is empty.
4. The design in sections 3 to 9 was approved as presented.

## 3. Facts the design rests on

- A packing list is JSON written by Fulfilment Tool. A bad one fails in
  `PackerLogic.load_packing_list_json` on a missing order field (`order_number`, `courier`) or a missing
  column, as a `ValueError` whose text is the only carrier of what was missing.
- Opening a session is: take the lock (UI thread, and it can ask about a stale lock), then on
  `SessionStartWorker` build `PackerLogic` (reads the SKU mapping and the saved progress), then load the
  list. A modal `QProgressDialog` covers the two worker steps. The UI thread spins `processEvents` while
  the worker runs, so a page can repaint during them.
- A failed start runs `_cleanup_failed_session_start`, which releases the lock. After a failure no session
  exists.
- `PackerLogic.all_orders_complete` fires when every order is packed **or skipped**.
- A skipped order can also have an entry in `in_progress` (scanned, then skipped).
- A rebuild of the Qt tree is deferred while Packer Mode is open (AUDIT-02-7), and a test pins that a scan
  does not rebuild it. Statistics is recomputed with pandas on every scan.
- `shared/components/toast.py` is a child widget of the window. A web view paints over a Qt child
  (Fulfilment ADR 0007), so a toast raised while a web page is showing has to be drawn by that page.
  `PageBridge` already has `raise_toast`; no page in this app draws it yet.
- A hidden `QWebEngineView` does not paint. Its DOM follows the bridge, and the page's paint report comes
  only once it is visible again.
- `session_tabs` is a `QTabWidget` with a hidden tab bar. About ten call sites and four test modules drive
  it with `setCurrentIndex(PAGE_*)`, `currentIndex()` and `currentChanged`.

## 4. One document (ADR 0003)

`gui/web/app.html` is the **app document**: one page in one `QWebEngineView` that draws Packing and
Statistics now and takes Sessions and Session details in phase 4. Sessions stays the Qt
`SessionBrowserWidget` until then, on its own stack page beside the view.

A view per screen was the alternative. It costs about 31 MB each (measured in Fulfilment Tool), and every
hidden view is one more frame that can go stale. One document switches Packing to Statistics by redrawing
inside a visible view, which cannot show an old frame at all.

### 4.1 `gui/app_pages.py`: `AppPages`

A `QWidget` holding a two-page `QStackedWidget`: the web view, and the Session Browser. It speaks the part
of `QTabWidget` the call sites use, so `MainWindow.session_tabs` stays and they do not change:

- `setCurrentIndex(index)`, `currentIndex()`, `currentChanged(int)`, `count()` (3), `widget(index)`
  (the view for Packing and Statistics, the browser for Sessions).
- `PAGE_PACKING` and `PAGE_STATISTICS` show the view and set the bridge's `page`; `PAGE_BROWSER` shows the
  browser.
- `view`, `bridge`, and `web_is_current()` (the view is the stack's current page).

`AppPages(session_browser)` is built by `MainWindow`; the browser is passed in.

### 4.2 `gui/app_bridge.py`: `AppBridge(PageBridge)`

Named properties, as `PackerBridge` has (phase 2, section 4.1). Each is one coherent snapshot.

| Property | Type | Empty | Carries |
|---|---|---|---|
| `page` | str | `"packing"` | `"packing"` or `"statistics"` |
| `covered` | bool | `false` | draw nothing but the page's plane (section 8) |
| `shell` | map | `{client: false, clients: true, serverDown: false}` | a client is chosen; any client exists; the server is unreachable |
| `session` | map | `{state: "none"}` | section 4.3 |
| `packing` | map | `{}` | section 5 |
| `statistics` | map | `{}` | section 6 |

Slots the page calls, each emitting a Python-facing signal of the same meaning: `openSession()`,
`startPacking()`, `endSession()`, `retryStart()`, `closeFailure()`, `clearFilter()`, `chooseClient()`,
`showPage(str)`.

`mount_app_page(view)` calls `shared.web_page.mount_page(view, bridge, PAGE, "app",
tokens=gui.theme.current_tokens)` and returns the bridge. The view keeps its default focus policy
(section 9).

`app.html` loads, in order, `../../shared/web/kit.css`, `floor.css`, `app.css`, then `qwebchannel.js`,
`../../shared/web/page.js` and `app.js`. `app.js` calls `reportPaints(bridge)`, renders synchronously in
its signal handlers, and writes every string through `textContent`.

### 4.3 `session`

| `state` | Other keys | Drawn |
|---|---|---|
| `none` | | 3a on Packing, 4a on Statistics |
| `opening` | `list`, `id`, `step` (1 to 3) | the header and 3b, on both pages |
| `failed` | `list`, `title`, `text` | the header and 3c, on both pages |
| `open` | `list`, `id`, `meta`, `complete` | the header and the page's content |

`complete` is true when every order is **packed**. With skipped orders left it is false, so the packer can
still go and pack them.

### 4.4 Who decides what

Python decides the data: totals, grouping, which orders match the filter, which item is the hit, and
whether an order is open by default. The payload functions are pure (no Qt, no I/O) and live in
`gui/app_bridge.py` beside the bridge, as Packer Mode's do.

The page keeps two pieces of view state and nothing else: the orders the packer opened or closed by hand,
and the SKU table's sort. Both are dropped when `session.id` changes; the hand-toggled set is also dropped
when the filter text changes.

## 5. Packing

Layout, top to bottom, in a column with 20px 24px padding and a 16px gap: the page header, the totals
strip, the complete banner (3g), the filter line (3e), the index card, which takes the rest of the height
and scrolls inside.

**Page header.** The packing list's name at 17pt bold, cut with an ellipsis, and an *Active* info badge.
Under it in `text_secondary`: the session id in mono, a dot, then the meta "120 orders · DHL, DPD, Speedy"
(the first three couriers by name, then "+N"). At the right, *Start packing* (primary), the bar's button
mirrored. On Statistics the title is "Statistics", the meta is the list's name, and there is no button.

**Totals strip (3d).** One card in four cells, `repeat(3, minmax(0,1fr)) minmax(0,1.6fr)`:

- *Orders complete*: the count at 28pt bold, "of 120".
- *Items packed*: units packed, "of 402". Units, as every other "items" figure counts them.
- *Orders skipped*: the count, then "still Not started", or "none" at zero.
- *Progress*: the percent at 17pt bold, a 14px track filled in `status_success_dot`, and "82 orders left ·
  2 in progress", or "All orders packed" when complete.

**Index card.** A 40px head (Order / Item, Product, Quantity, Status, Courier) on the grid
`minmax(200px,1.1fr) minmax(0,2fr) 120px 170px 110px`, then the rows.

- **Groups** in this order, each a 40px `surface_sunken` row with its label, its count in mono and a note:
  *In progress*, *Not started* (note "3 skipped" when any), *Packed*. An empty group is not drawn.
  - *Packed*: in `completed_orders`.
  - *In progress*: in `in_progress` and not skipped.
  - *Not started*: everything else, skipped orders included.
- **Order row**, 52px: a chevron, the order number in bold mono (through `order_label`, so always with
  `#`), a *Skipped* warning badge when skipped; "3 items · Lip balm, red, Day cream 50 ml, …" in
  `text_secondary`, cut with an ellipsis; "2 / 5" in mono, right-aligned; the status badge (*Not started*
  neutral, *In progress* info, *Packed* success); the courier. A skipped order's badge reads *Not started*.
  An open row takes `surface_raised`.
- **Item row**, 44px, on `surface_raised`: the SKU in mono, indented 30px; the product; "1 / 2" in mono;
  the item's badge (*Pending* neutral, *Partial* info, *Complete* success); no courier.
- Clicking an order row opens or closes it. In-progress orders are open by default. No checkboxes.

**Filter (3e, 3f).** *Filter orders* stays the Qt field in the command bar. The query is trimmed and a
leading `#` dropped; matching ignores case. An order matches when its number, or any item's SKU or product
name, contains the query. With a query:

- only matching orders are listed, in their groups, and all of them are open;
- an item whose SKU or product contains the query is the **hit**: `selection_bg` with a 4px
  `selection_border` rule on its left;
- the filter line reads "**4** of 120 orders contain `LST-07`" (the query as typed), with *Clear filter*;
- with no match the index card shows, under its head, a centred glyph, "No orders match", "Nothing in this
  packing list contains “99999”." and *Clear filter* (secondary). The filter line is not drawn.

*Clear filter* calls `clearFilter()`, which clears the Qt field.

**States.**

| Frame | When | Drawn |
|---|---|---|
| no client | `shell.client` is false | a centred card: "Choose a client to begin" / "Sessions, packing lists and SKU mapping all belong to one client." / *Choose a client* (primary, absent when `shell.clients` is false). On either page. |
| 3a | `session.state` is `none` | a centred card: "No session open" / "Open a session to see its orders here." / *Open session* (primary, disabled while `shell.serverDown`). |
| 3b | `opening` | the header (title only, no badge, no button) and a card: "Working · step 2 of 3", the step's name at 17pt bold, the list and session id in `text_secondary`, and three 6px bars, filled up to the step in `accent_fill`. |
| 3c | `failed` | the header (title only) and a danger banner: the alert glyph, the title at 14pt bold in `status_danger`, the sentence, *Retry* (secondary) and *Close* (ghost). |
| 3d | `open` | the totals strip and the index card. |
| 3g | `open` and `complete` | 3d, plus a `status_success_bg` banner between the strip and the card: a 32px check, "Packing list complete" at 17pt bold in `status_success`, "120 of 120 orders packed." and *End session* (primary). The header's *Start packing* is disabled. |

The no-client and no-session cards are 520px at most, 32px padding, a 17pt bold title.

**The three steps of 3b** are the ones the code runs:

| Step | Name | What runs |
|---|---|---|
| 1 | Taking the packing list | the session lock, on the UI thread |
| 2 | Reading saved progress | `PackerLogic()` on the worker: SKU mapping and packing state |
| 3 | Reading the packing list | `load_packing_list_json` on the worker |

`SessionStartWorker` gains `step = Signal(int)` and emits 2 and 3 before each. `MainWindow` shows step 1
before it takes the lock. The modal `QProgressDialog` at session start is deleted; the one at session end
stays. On a fast server the steps pass in a blink, which is the point of naming them only when it is slow.

**The sentences of 3c.** `packing_tool/exceptions.py` gains `PackingListInvalidError(ValueError)` carrying
`missing` and `found` (lists of names). `load_packing_list_json` raises it, with today's message text, at
its two "missing" checks. It subclasses `ValueError` so nothing that catches or matches today's error
changes. A pure `start_failure(error, list_name)` in `gui/app_bridge.py` returns the title and the sentence:

| Error | Title | Sentence |
|---|---|---|
| `PackingListInvalidError` | Packing list could not be loaded | "`DHL_Orders` has an order with no courier. Found: order_number, items." For a column: "`DHL_Orders` has no Quantity column. Found: Order_Number, SKU, Courier." |
| other `ValueError`, `json.JSONDecodeError` | Packing list could not be loaded | "`DHL_Orders` could not be read: <the error>." |
| `FileNotFoundError` | Packing list could not be loaded | "`DHL_Orders` is no longer in the session's folder." |
| `PackingStateUnreadableError` | Saved progress could not be read | today's sentence: "The saved progress for DHL_Orders could not be read, so the list was not opened. Nothing was changed. Check the connection to the server and open it again." |
| `RuntimeError` (the lock is held) | Session could not be opened | the lock's own message |
| `OSError` making the work folder | Session could not be opened | "The work folder for DHL_Orders could not be made: <the error>." |
| anything else | Session could not be opened | the error's text |

`MainWindow` keeps the arguments of the failed start. *Retry* runs the same start again. *Close* returns to
3a. The failure also clears on a successful start and on a client change. Declining the stale-lock question
is not a failure: the page returns to 3a. A failed start still triggers `check_connection()`, as today.
While it shows, the bar is in its no-session state.

## 6. Statistics

Layout: the header, the KPI strip, then a row that takes the rest of the height, `minmax(300px, 0.75fr)
minmax(0, 2fr)` with a 16px gap: *By courier* and *SKU summary*.

**KPI strip (4b).** One card in five cells, `repeat(4, minmax(0,1fr)) minmax(0,1.5fr)`. Each of the first
four has a 12pt bold label, the value at 28pt bold and a 10pt note:

| Label | Value | Note |
|---|---|---|
| Orders | orders on the list | "3 couriers" |
| Completed | orders packed | "2 in progress", or "none in progress" |
| Items | units on the list | "148 packed" |
| Unique SKUs | distinct SKUs | "31 fully packed" |

The fifth is *Progress*: the percent at 28pt bold, the 14px track, "38 of 120 orders complete".

**By courier.** A card that scrolls inside. Per courier, by name: the name at 14pt bold, "**12** done" and
"of 40", a 24px track filled in `status_success_dot` to done over total, and "28 orders left" or "All
packed" in 10pt. `session_stats.courier_totals` gains the completed orders and returns `done` beside
`orders`.

**SKU summary.** A card: a 48px title row with "88 SKUs · sorted by Left, most first" at the right; a 44px
head of six sort buttons on the grid `130px minmax(0,1fr) 84px 84px 84px 120px` (SKU, Product, Total qty,
Packed, Left, Status); then 40px rows that scroll inside. SKU in mono; the three numbers in mono,
right-aligned; *Left* bold in `text`, or normal in `text_secondary` at zero; the badge (*Pending* neutral,
*Partial* info, *Packed* success).

Sorting is the page's. The default is *Left*, most first. A click on the sorted column reverses it; a click
on another sorts by it in its natural direction (text A to Z, numbers most first, status Pending, Partial,
Packed). Ties fall back to SKU. The sorted head is in `text` with an arrow and carries `aria-sort`.

**States.**

| Frame | When | Drawn |
|---|---|---|
| 4a | `none` | a centred card: "No packing data yet" / "Start a session from the Packing tab to see numbers here." / *Go to Packing* (primary), which calls `showPage("packing")`. |
| 4b | `open` | as above. |
| 4c | `open` and `complete` | every bar full, every *Left* zero and grey, *Completed*'s note "none in progress". No extra rule: it is what the numbers give. |

Opening, failed and no client draw as on Packing.

## 7. `MainWindow` and the bar

**One push.** `_push_pages()` builds `session`, `packing` and `statistics` from `self.logic` and the filter
text and sets them on the bridge. `_refresh_pages()` calls it when the shell is the visible page and marks
the pages stale otherwise; leaving Packer Mode pushes before it switches. It replaces
`_populate_order_tree`, `_refresh_order_tree`, `_rebuild_order_tree_if_stale`, `_update_statistics`,
`setup_order_table` and `update_order_status`. So a scan in Packer Mode costs the pages nothing, which is
better than today, where Statistics is recomputed on every scan.

The filter field's `textChanged` pushes `packing` alone.

**Slots.** `openSession` → `open_session_browser`; `startPacking` → `switch_to_packer_mode`; `endSession`
→ `end_session`; `retryStart` and `closeFailure` → section 5; `clearFilter` → `search_input.clear()`;
`chooseClient` → `client_combo.showPopup()`; `showPage` → `session_tabs.setCurrentIndex`.

**Shell.** `_sync_client_state` and `_set_connection_state` set `shell`. With no client the page is
Packing. The Qt `no_client_panel` is deleted. The connection banner stays the Qt widget above the pages:
it spans the Qt Sessions page too.

**Command bar.** `CommandBar.set_complete(bool)`: *End session* takes the primary role, and *Start
packing* is disabled with the tooltip "Every order is packed". `MainWindow` sets it from
`session.complete`.

**Toasts.** `MainWindow._toast(message, role="success")` replaces its direct `toast(self, …)` calls. When
the app document is the visible page it calls `bridge.raise_toast(message)`; otherwise it raises the Qt
toast as today. The page draws the mockup's toast: `surface_inverse`, bottom centre, 48px, 12pt, a
*Dismiss* button, gone after 4 s, the newest replacing the last. The sentences stay today's.

**Theme.** `_switch_theme` goes through `shared.web_page.switch_theme`, so the chrome and the visible page
turn over together.

## 8. Freshness

- The DOM is never behind the bridge: the page renders in its signal handlers, hidden or not.
- Nothing but the end of a session is pushed while Packer Mode covers the shell (section 7), and leaving
  Packer Mode pushes before the switch.
- **The kept frame.** `switch_to_packer_mode` sets `covered`, waits for the page to paint it
  (`when_painted`, 150 ms at most) and then switches. Leaving sets `covered` back, with the push, before
  the switch. So the frame the hidden view keeps is the empty plane. A window that is not visible (the
  tests' `MainWindow`) switches at once, as `_leave_packer_mode` already does.
- The view is also hidden while Sessions is showing. Nothing changes a session's state from there except
  starting one, and the page that comes back then shows 3a for a frame before 3b. One known limit: a theme
  changed on Sessions shows in the page area one frame late. Phase 4 ends it, when Sessions joins the
  document.

**The freshness test,** once for Packing and once for Statistics, in a real Chromium on a shown
`MainWindow`: open session A, wait for its paint; show Sessions (the view is hidden); end A and open B
through the same `MainWindow` methods the app uses; show the page; wait until the painted revision equals
the bridge's; assert the DOM holds B's order numbers (or SKUs) and none of A's.

## 9. What the mockup leaves free

- **Keyboard.** The view takes focus, as a page of buttons should. Every action in the page is a `button`.
  An order row is a `button` spanning the row with `aria-expanded`; Enter and Space toggle it. The kit's
  focus ring shows. A test clicks inside the page and then presses Ctrl+2 and Ctrl+E, and both still reach
  the window. If that test fails in implementation, the view is given `NoFocus` with `deny_focus`, as
  Packer Mode's is, and the row and sort buttons become mouse-only: say so in the PR.
- **1280×680.** Nothing scrolls the page. The index card, *By courier* and *SKU summary* scroll inside
  themselves; the strips and the header do not shrink below their content.
- **Long data.** The list's name, an order's item summary and a product name are one line with an
  ellipsis, and carry the full text as a `title`. A fourth courier and beyond is "+N" in the meta.
- **Motion.** None: no transitions (ADR 0001). A row opens at once.
- **Copy.** An action keeps one name: *Open session*, *Start packing*, *End session*, *Clear filter* are
  the bar's words. 3c says what is wrong and what was found, and its actions say what they do.

## 10. Sheets

**`gui/web/floor.css`** gains what phase 4's Sessions will use again, at floor sizes, with no page in it:

- the toast: bottom centre, 48px, 12pt, a 36px dismiss target;
- `.state-card`: the centred 520px card of 3a, 4a and no client, with a 17pt title;
- `.strip` and `.strip-cell`: a card split into cells by `border` rules, a 12pt bold label over a 28pt
  bold value;
- `.track` and `.track-fill`: the progress track (14px; `.track.tall` 24px), `surface_raised` with a
  `border_strong` edge, filled in `status_success_dot`;
- `.tbl-head`, `.tbl-group`, `.tbl-row`: the index table's 40px head, 40px group row and its rows, with
  `--tbl-cols` set by the page.

**`gui/web/app.css`** holds the two pages' layouts, grids and the 3b, 3c and 3g blocks. Sizes off the type
scale (14pt) are custom properties at its top.

## 11. Departures from the mockup

| # | Mockup | Built | Why |
|---|---|---|---|
| 1 | 3b's steps: Connecting to the server, Reading the packing list, Matching items to SKU mapping | Taking the packing list, Reading saved progress, Reading the packing list | the steps the code runs (section 3) |
| 2 | 3b's detail lines: the server path, "120 orders", "402 items · 88 SKUs" | the list's name and the session id | the counts are not known until the last step ends |
| 3 | 3c: "has no Quantity column. Found: SKU, Name, Qty ordered, Courier." | the missing field or column and the names found, from the JSON | a packing list is JSON, not a spreadsheet |
| 4 | 3c keeps the session: the bar shows its id and *End session*, the button is *Close session* | no session is open; the bar offers *Open session*; the button is *Close* | a failed start releases the lock, so there is nothing to close |
| 5 | 3c is one failure | seven, each with its sentence | owner decision 1 |
| 6 | Title "Morning wave, 7 October" over a mono file name | the list's name over the mono session id | a list has a name and no title; the session id is what the bar and Sessions call it |
| 7 | The filter matches order number or SKU, and echoes the query in capitals | product name too; the query as typed | owner decision 2; SKUs are not all capitals |
| 8 | Complete is one state | *complete* is every order packed; with skipped orders left the banner does not show and *Start packing* stays live | the session "completes" today with orders skipped, and they can still be packed |
| 9 | A skipped order is *Not started* with 0 packed | its real packed count, under *Not started* | an order can be scanned and then skipped |
| 10 | Toast copy: "Session 2026-10-07_1 opened · 120 orders", "Session … ended" | today's sentences | they carry the list's name and where the report was saved |
| 11 | The connection banner is drawn in the page | the Qt banner above the pages, as phase 1 built it | it spans the Qt Sessions page until phase 4 |
| 12 | A search glyph in the filter, a cross to clear it | the Qt field with its own clear button | phase 1, row 2: the field is a `QLineEdit` |
| 13 | Hairlines in `border_subtle`, control edges in `border`; secondary buttons without a shadow | the kit's | contrast floors and the kit win (phase 1 row 6, phase 2 row 12) |
| 14 | Segoe UI, Consolas | the bundled Inter and the theme's mono | the Qt tier's faces, as in phases 1 and 2 |
| 15 | The header's *Active* badge on a complete session | the same | kept: a session open on this PC is active until it is ended |
| 16 | *By courier* lists DHL, DPD, Speedy in that order | by name | there is no courier order in the data |
| 17 | (not drawn) | the item summary, product and list name carry a `title` | cut text must be readable somewhere |

## 12. For shared/

To raise on Fulfilment's side. Nothing here blocks this phase.

- Everything added to `gui/web/floor.css` in section 10, as kit components at floor density.
- A toast script in `shared/web/page.js`: every page of both apps draws the same toast from
  `toastRaised`, and here `app.js` carries its own.
- `shared/components/toast.py` cannot be seen over a web view. Packer Mode still raises it for "SKU mapping
  saved" (phase 5).

## 13. Testing

Seams, all through public surfaces:

- **Pure payloads** (`tests/test_app_payload.py`): `packing_payload` (totals; the three groups and their
  rules, a skipped in-progress order included; open by default; the filter by number, SKU and product,
  with and without `#`, any case; hits; the no-match shape), `statistics_payload` (KPIs and notes, courier
  `done`, SKU `left` and state, the complete case), `session_payload`, and `start_failure` for each row of
  section 5's table.
- **`session_stats`** (`tests/test_session_stats.py`): `courier_totals` returns `done`.
- **`PackerLogic`** (`tests/test_packer_logic_*`): a list with an order missing `courier` raises
  `PackingListInvalidError` with `missing` and `found`, and is still a `ValueError`.
- **The page in a real Chromium** (`tests/test_app_bridge.py`), one test per frame at least: no client
  (with and without the button); 3a and its button disabled while the server is down; 3b at each step; 3c
  with both buttons reaching their slots; 3d's strip, groups in order, default-open rows and a click
  toggling one; 3e's hit row and filter line; 3f; 3g's banner and disabled *Start packing*; 4a and its
  button; 4b's KPIs, bars and default sort; a header click re-sorting and a second click reversing; 4c;
  `covered` leaving no text in the body; the toast showing and dismissing; the page reporting the revision
  it painted; a theme switch repainting without a reload.
- **`AppPages`** (`tests/test_app_pages.py`): the three indices, `currentChanged`, `widget()`, `page`
  following the index, `web_is_current()`.
- **`CommandBar`** (`tests/test_command_bar.py`): `set_complete`.
- **`MainWindow`** (`tests/test_app_mainwindow_seam.py`, and updates to `tests/test_shell.py`,
  `tests/test_no_client.py`, `tests/test_connection_state.py`, `tests/audit/test_02_concurrency_sweep.py`):
  the two freshness tests of section 8; a scan in Packer Mode pushes nothing and leaving pushes once; each
  page slot reaches its handler; the filter field drives `packing`; a failed start shows 3c and no message
  box, *Retry* starts again with the same arguments, *Close* returns to 3a; the worker's steps reach
  `session.step`; `complete` reaches the bar; no client and server-down reach `shell`; a toast goes to the
  page when it is showing and to Qt otherwise; `switch_to_packer_mode` on a shown window switches only
  after the covered page has painted; the keyboard test of section 9.
- **Deleted with what they tested:** `tests/test_order_tree.py`, `tests/test_order_tree_filter.py`,
  `tests/test_statistics_widget.py`, `tests/test_packing_empty.py`.
- **Guards:** `tests/test_style_literals_guard.py` already scans `gui/web`.

**Renders.** `scripts/render_app_pages.py` builds a `MainWindow` offscreen against a throwaway server with
a synthetic 120-order list (both `QSettings` formats redirected, as `scripts/render_shell.py` does) and
writes `docs/design/ui-refresh/renders/phase3/<frame>-<theme>.png`: 3a to 3g and 4a to 4c at 1366×768, 5a
and 5b at 1920×1080, in Light and Dark. The implementer looks at every PNG beside its mockup frame before
the PR, and the PR embeds them. `scripts/render_shell.py` is updated to call `_push_pages()`.

## 14. Deleted

- From `gui/main_window.py`: the order tree and everything that only served it (`_setup_order_tree`,
  `_populate_order_tree`, `_refresh_order_tree`, `_rebuild_order_tree_if_stale`, `_order_status_chip`,
  `ORDER_STATUS_CHIP`, `order_summary`, `packing_summary_label`, `order_tree_card`,
  `packing_state_panel`, `no_client_panel`, `_update_statistics`, `setup_order_table`,
  `update_order_status`, `_order_tree_stale`), the session-start `QProgressDialog`, the six
  `QMessageBox.critical` calls of a failed start and the one for the work folder, the `QTabWidget`, and
  the imports left unused.
- `gui/statistics_widget.py`.

## 15. Out of scope

- Sessions and Session details (phase 4). SKU mapping and Worker selection (phase 5).
- The "Session Loaded" and "Session Resumed" message boxes after a start from Sessions, and the stale-lock
  question: they belong to the Sessions flow.
- A toast inside Packer Mode.
- Any edit under `shared/`.
- New information: per-order times, customer names.

## 16. Docs touched

- `docs/adr/0003-the-shells-pages-are-one-web-document.md` (new).
- `CONTEXT.md`: add **App document** and **App bridge**; replace **Packing table view** with **Order
  index**; replace **Stat card** with **KPI strip**; **State panel** and **Toast** say a web page draws
  its own; **SKU roll-up** keeps its pointer to the SKU summary.
- `.github/workflows/build-release.yml`: the bundle check adds `app.html`.
