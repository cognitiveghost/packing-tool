# UI refresh phase 5: Worker selection and SKU mapping on the web tier, and cleanup

- **Date:** 2026-10-09. dev-runner run 81, Todoist task "UI refresh phase 5" (5 of 5).
- **Mockups followed:** `docs/design/ui-refresh/mockups/Worker Selection.html` (six presets, two contexts)
  and `SKU Mapping.html` (eight presets). Neither is in `Packer Screens.html`: the README there calls them
  addenda. Every departure is in section 11.
- **Decisions it rests on:** ADR 0001 (the scanner invariant, web-asset guardrails), ADR 0002 (every screen
  on the web tier, floor density, `shared/` is never edited here), ADR 0003 (the shell's pages are one web
  document), and ADR 0004, written with this spec (SKU mapping takes the keyboard from Packer Mode).
- **Depends on:** phase 4 (merged, PR #201).

## 1. What this is for

Two screens are still Qt dialogs: Worker selection, shown before the window exists, and SKU mapping, a
table with four buttons whose "add" is two input boxes in a row. Packer Mode's *Map SKU* and *Map
barcode…* are a third and fourth dialog (`QInputDialog`). This phase redraws both screens to their
mockups as full-window web pages, routes the two Packer Mode flows through the new SKU mapping page
without losing a scan, deletes what is left over, and renders every screen of the refresh one last time.

**Done when:** no Qt page or dialog is left for these screens; the scanner tests of section 8 pass; every
frame of `Packer Screens.html` and every state of the two pages is rendered at 1366×768 and 1920×1080 in
both themes under `docs/design/ui-refresh/renders/final/`; section 11 lists every departure; `CONTEXT.md`
and `README.md` are current; the "For shared/" items of all five phases are one list; and the suite passes.

## 2. Owner decisions (2026-10-09, runner questions 70 and 71)

1. **SKU mapping is a full-window page.** The shell is hidden while it shows. Its own Close, Cancel and Save
   are the only ways out.
2. **From Packer Mode the page does one add.** The table is visible and searchable but read-only. The add
   writes that one mapping to the server at once and returns to Packer Mode.
3. ***Map barcode…* maps to the open order's SKUs only**, typed or picked with one click. The scan is
   replayed afterwards and packs the item, as today.
4. **A stray scan is replayed** into Packer Mode on return, not dropped.
5. The design in sections 4 to 10 was approved as presented, at floor density.

## 3. Facts the design rests on

- **Worker selection runs before the window is built.** `MainWindow.__init__` calls `_select_worker()`
  (a modal `WorkerSelectionDialog`) before `_init_ui()`, and `sys.exit(0)` on cancel. Under pytest, or with
  `skip_worker_selection=True`, it is skipped and a dummy worker is used.
- `WorkerManager.get_all_workers()` returns `WorkerProfile`s (`id`, `name`, `created_at`, `total_sessions`,
  `total_orders`, `last_active`, …) and raises on an unreadable `Workers/workers.json` (a corrupt one is
  renamed and read as empty). `create_worker(name)` raises `ValueError` for an empty name or one that
  exists already, compared without case. `last_active` changes only when a session ends.
- Switching worker with a session open is allowed today: the id is read when the session ends.
- **The task's premise is wrong for one of the two Packer Mode entries.** *Map barcode…* (on a *No match*
  row) knows the barcode and needs the SKU. *Map SKU* (on an item row whose SKU has no mapping) is the
  reverse: it knows the SKU and prompts for the barcode, which the packer scans.
- Today *Map barcode…* is a pick list (`_unmapped_choices`): the open order's lines, unfinished first. It
  saves, drops the barcode from `logic.unknown_scans`, and replays the scan with `on_scanner_input(barcode)`.
  *Map SKU* saves and replays nothing.
- Both flows write through `MainWindow._save_sku_mapping`, which asks before overwriting a barcode that
  maps to another SKU, calls `ProfileManager.update_sku_mapping(client, {barcode: sku})`, sets
  `logic.sku_map` and shows "Mapped: barcode → sku" in the feedback band.
- The mappings live in `Clients/CLIENT_<id>/packer_config.json` under `sku_mapping`, not in
  `sku_mapping.json` (a legacy fallback). `update_sku_mapping(client, add, remove)` applies one PC's edits
  under a file lock and returns the whole mapping; it raises `ProfileManagerError`.
- `load_sku_mapping` caches for 60 s. Today's "Reload from Server" reads that cache.
- A scan is matched by `normalize_sku` (letters and digits only, lower case) on both the barcode key and
  the SKU. Two barcodes that normalise alike are one key to `PackerLogic`, and SKU case does not matter.
- The largest client on the production share has under 200 mappings.
- The two mockups are drawn at office sizes (28 to 32px controls, 10pt body, 40px rows). ADR 0002 sets
  floor density for all five phases.
- Offscreen, `QTest` key events sent to a focused `QWebEngineView`'s focus proxy reach the focused DOM
  input, keys with no focused input reach a `document` keydown listener, and `setFocus()` on a Qt field
  takes effect in the same turn as the stack switch. (Probed for this spec; the probe is deleted.)
- A hidden `QWebEngineView` keeps its last frame and shows it when it comes back (ADR 0003).
- With a session open, a lost lock outside Packer Mode tears the session down and raises a message box.

## 4. Structure

### 4.1 Files

| File | Holds |
|---|---|
| `gui/setup_payload.py` (new) | Pure, no Qt, no I/O: `workers_payload`, `worker_name_problem`, `last_active_text`, `initials` (moved from `gui/components/sidebar.py`, which imports it back), `MappingEditor`, `mapping_payload`, `quick_payload`, `order_choices` (today's `_unmapped_choices`, moved). |
| `gui/setup_bridge.py` (new) | `SetupBridge(PageBridge)` and `mount_setup_page(view)`. |
| `gui/setup_pages.py` (new) | `SetupPages(QWidget)`: the view, and everything the two pages read from or write to the server. |
| `gui/web/setup.html`, `setup.css`, `setup.js` (new) | the **setup document**: both pages. |
| `gui/main_window.py` | the stack's third widget, the two ways in and the way back, the stray-scan queue. Loses `_select_worker`, `open_sku_mapping_dialog`, `_save_sku_mapping`, `_on_map_sku_from_packer`'s and `_on_map_barcode_from_packer`'s dialogs, `_unmapped_choices`. |
| `packing_tool/profile_manager.py` | `load_sku_mapping(client_id, fresh=False)`: `fresh=True` skips the cache. |
| `gui/sku_mapping_dialog.py`, `gui/worker_selection_dialog.py` | deleted. |
| `scripts/render_setup.py` (new), `scripts/render_all.py` (new) | section 9. |

The setup document is its own view, not two more pages of the app document. In the app document the Qt
sidebar and command bar would have to be hidden around it, and `MainWindow._shell_showing()` (which decides
whether a scan pushes pages, whether the Sessions timer refreshes, whether Ctrl+1 to 3 work) would be true
while a packer is mid-order on the mapping page. As a third widget of `stacked_widget` none of that changes.
One view for both pages, not one each: they are never on screen together (ADR 0003's reasoning).

### 4.2 `SetupBridge`

| Property | Type | Empty | Carries |
|---|---|---|---|
| `page` | str | `""` | `"workers"`, `"mapping"`, or `""`: draw nothing |
| `workers` | map | `{}` | section 5.2 |
| `mapping` | map | `{}` | section 6.2 |

JS-facing signal: `leaveAsked()`, which makes the mapping page raise its "Discard unsaved changes?"
question (section 6.6).

Slots that report, each emitting a Python-facing signal: `pickWorker(id)`, `retryWorkers()`,
`leaveWorkers()`, `deleteMapping(id)`, `reloadMappings()`, `saveMappings()`, `closeMapping()`,
`strayScan(text)`.

Slots that answer (`@Slot(..., result=str)`): `createWorker(name)`, `addMapping(barcode, sku)`,
`updateMapping(id, barcode, sku)`, `replaceMapping(id, barcode, sku)`. Each returns `""` when the thing
was done, else the sentence to show beside the field. They call `bridge.answer(name, *args)`, a callable
`SetupPages` sets; unset, they return `""` and do nothing. The page needs the answer to know whether to
clear what was typed.

### 4.3 `SetupPages`

`SetupPages(worker_manager, profile_manager, parent=None)`. Holds `view` and `bridge`.

- `show_workers(current_id, startup)`: reads the workers, pushes `workers`, sets `page` to `"workers"`.
- `show_mapping(client_id, client_label, quick=None)`: reads the client's mappings fresh, builds a
  `MappingEditor`, pushes `mapping`, sets `page` to `"mapping"`. `quick` is `None` from the sidebar, or
  `{"kind": "sku", "sku": …}` / `{"kind": "barcode", "barcode": …, "choices": […]}` from Packer Mode.
- `blank()`: sets `page` to `""` and empties both payloads.
- `dirty()`: whether the mapping page has unsaved changes. `ask_leave()`: emits `leaveAsked`.
- Signals: `workerChosen(str, str)` (id, name; emitted once the "Opening…" badge has painted),
  `quitRequested()`, `backRequested()` (leave with nothing to report), `mappingSaved(dict)` (the whole
  mapping, after a Save), `quickMapped(str, str, str, dict)` (kind, barcode, SKU, the whole mapping),
  `strayScanned(str)`.

All server reads and writes here are synchronous on the UI thread, as the dialogs' were: one small JSON
file each.

### 4.4 `MainWindow`

`stacked_widget` gains `self.setup_pages` as its third widget. Three methods replace the dialogs:

- **`_open_setup(show)`** records where it came from (`self._setup_return`: the shell or Packer Mode) and
  calls `show()`, one of the two `show_*` methods bound to its arguments.
  - From the shell: the app document is covered and painted first, exactly as `switch_to_packer_mode` does
    (`bridge.set_covered(True)`, `when_painted`), then the stack switches and the view takes the focus.
  - From Packer Mode: the stack switches at once and the view takes the focus. Packer Mode's document is
    left as it is.
- **`_leave_setup(after=None)`** calls `setup_pages.blank()`, waits for that paint (`when_painted`, 150 ms
  at most), then returns to `_setup_return`:
  - the shell: `_push_pages()`, `set_covered(False)`, switch;
  - Packer Mode: switch, `set_focus_to_scanner()`, then `after()` if given, then every queued stray scan
    through `on_scanner_input`, in order. The scanner was never paused, so there is nothing to resume.
- **Startup.** `__init__` no longer selects a worker before `_init_ui()`. After `load_available_clients()`,
  outside test mode, it calls `_open_setup` for Worker selection with `startup=True`; `_setup_return` is
  the shell. In test mode nothing changes: the dummy worker, and the shell on top.

While the setup page is on top: Ctrl+E does nothing (Ctrl+1 to 3 already check for the shell);
`closeEvent` with unsaved mapping changes ignores the close and calls `ask_leave()`.

A lock lost while the mapping page is open from Packer Mode: `_on_lock_lost` treats it as Packer Mode. It
shows the take-over panel on the packer widget and calls `_leave_setup()`, so the packer lands on frame 6j.
Opened from the shell, today's teardown and message box stand and the page stays open.

### 4.5 Who decides what

Python decides every card, row, count of changes and sentence that does not depend on what is being typed.
The page keeps: the text in its inputs, the search text, which row is being edited, and which question is
open. One check runs in the page as the packer types, because a round trip per key is not worth it, and Python
repeats it before it acts: **already mapped**, when the draft's barcode, normalised like `normalize_sku`,
equals another row's `key`. Everything else is answered by the slot the page calls.

### 4.6 Sheets

`setup.html` loads `shared/web/kit.css`, `floor.css`, then `setup.css`, as `app.html` does. Colour comes
only from `theme_css_vars()`; the two shadows are `--card-shadow` and `--overlay-shadow`. The pages reuse
from the kit and the floor kit: `.btn` (primary, secondary, ghost, danger, dashed, icon, compact), `.badge`,
`.banner.danger`, `.input`, `.field`, `.scrim` and `.dialog`, `.state-card`, `.tbl-head` and `.tbl-row`,
`.dot`, `.mono`. The kit's `.field` already takes the floor's control height, so `floor.css` does not change;
a rule that only these pages use stays in `setup.css`.

## 5. Worker selection

### 5.1 Layout

Full window on `--surface-sunken`. A 60px top row holds one secondary button on the right: **Quit** at
startup, **Back to *name*** from *Switch worker…*. Below it, centred and scrolling when it must: the app
mark (56px, the package glyph on `--accent-fill`), "Select your profile" at display size, "Choose your
worker profile to continue" in secondary text, then the grid.

The grid is `min(4, cards + 1)` columns of 240px with 16px gaps, centred. A card is a `<button>`, 240px
wide and at least 168px tall: a 44px circle with the initials, the badge opposite it, the name at heading
size (one line, ellipsis, the whole name in `title`), then two secondary lines. The last cell is **New
worker**: a dashed card with a plus in a dashed circle.

### 5.2 Payload

```
{"context": "startup" | "switch",
 "leave": "Quit" | "Back to Ivan",
 "mode": "ready" | "failed",
 "error": {} | {"title": "Couldn’t load the worker list.", "text": …, "path": …},
 "cards": [{"id", "name", "initials", "stats", "last", "badge", "picked": bool}]}
```

- **Order:** `last_active` newest first; workers never active after them, by name.
- **`stats`:** "31 sessions · 2,870 orders" (thousands separated by a comma, "1 session", "1 order"), or
  "No sessions yet" when both are zero.
- **`last`** (`last_active_text(when, now)`): "Last active Today, 07:40"; "Last active Yesterday"; two to
  six days ago the weekday, "Last active Monday"; seven to thirteen, "Last active Last week"; older, "Last
  active 12 Sep", with the year when it is not this one. Never active: "Just created" when `created_at` is
  under an hour old, else "Not active yet".
- **`badge`:** "Opening…" on the picked card; else "Current" on the signed-in worker's card in the switch
  context; else empty.

### 5.3 Picking

A click calls `pickWorker(id)`. `SetupPages` marks that card "Opening…" (a 1px `--text` ring, as the
mockup), and emits `workerChosen` once that has painted. `MainWindow` sets `current_worker_id` and
`current_worker_name`, tells the sidebar, and calls `_leave_setup()`. Picking the current worker in the
switch context does the same, which is "Back".

**Quit** emits `quitRequested`, and `MainWindow` closes the window. **Back to *name*** emits
`backRequested`.

### 5.4 New worker

A click turns the dashed card into a form in place: "New worker", a name field (`maxlength` 24, focused),
**Create** (primary) and **Cancel**. Enter creates, Esc cancels. Whether the form is open, and its text, are
the page's.

`createWorker(name)` runs `worker_name_problem(name, workers)` and returns its sentence, in this order:

| Case | Sentence |
|---|---|
| empty after trimming | "Enter a name." |
| a character other than a letter, a digit, a space, `.`, `'` or `-` | "Use letters, numbers, spaces, dots, hyphens or apostrophes." |
| the name exists, ignoring case | "There’s already a worker called Maria. Pick that card, or add a surname." |

With no problem it collapses inner runs of spaces, calls `create_worker`, and treats the new worker as
picked (section 5.3). A `ValueError` from `create_worker` (another PC took the name meanwhile) returns the
third sentence; any other error returns "Couldn’t create the worker: *cause*." A returned sentence shows
under the field in danger colour with a danger border on the field, and goes when the text changes.

### 5.5 States

| State | What shows |
|---|---|
| Six workers | 4 + 3 grid, *New worker* last |
| One | the card and *New worker*, two columns |
| None | "No workers yet" / "Create a worker profile to start packing." above the lone *New worker* card |
| Creating, duplicate | section 5.4 |
| Could not load | the danger banner: title, "*Cause*." and the path (`Workers` folder, mono), with **Retry**. No grid. Retry calls `retryWorkers()`, which reads again. The cause is `error_cause(error)` with its first letter raised |

## 6. SKU mapping

### 6.1 Layout

Full window on `--surface-sunken`. One card, 920px wide, centred, as tall as the window less 40px above
and below, with `--overlay-shadow`. Three rows:

- **Header (60px):** "SKU mapping", the client's label as a neutral badge with a success dot, and a ghost
  icon button, Close (Esc).
- **Body (`--surface-sunken`, 20px 24px padding):**
  - the line "Map product barcodes to internal SKUs. Changes are saved to the file server and reach every
    PC." with **Add mapping** (secondary, compact) at its right;
  - the error banner, when there is one;
  - the table card: a toolbar (the search `.input`, 280px, "Search barcode or SKU"; the count; **Reload from
    server**, secondary, compact), a head row ("Product barcode", "Internal SKU"), and the rows, which
    scroll. Columns: `8px 240px 16px 1fr 96px` (the unsaved dot, barcode, an arrow, SKU, the row's actions).
    A row is 44px, barcode in mono, SKU in bold mono, with ghost icon buttons Edit and Delete at its right.
- **Footer (68px):** on the left "Unsaved: 2 added, 1 edited" behind a 7px `--text` dot, or the saved line;
  on the right **Cancel** (secondary) and **Save** (primary, Ctrl+S, disabled with nothing unsaved).

### 6.2 `MappingEditor` and the payload

`MappingEditor(loaded)` holds the mapping as read and the working rows, each with an integer `id` that
lasts until the next load. Loaded rows are sorted by barcode; an added row goes on top.

- `add(barcode, sku)`, `update(id, barcode, sku)`, `replace(id, barcode, sku)`, `delete(id)`: the first
  three return a sentence or `""`. Barcode has all whitespace removed; SKU is trimmed and kept as typed.
- `replace` gives `sku` to the row that already has `barcode`, and removes row `id` if it is not `0` (the
  row being edited becomes the row it collided with).
- Problems, in order: "Enter a barcode.", "Enter a SKU.", "This barcode already maps to *SKU*." (another
  row's `key` equals this barcode's; `replace` is the way through).
- `counts()` → added, edited, deleted, by barcode against the mapping as read: a barcode that was not
  read is added, one whose SKU differs is edited, one that no row has now is deleted. So a row edited back
  to what was read is not a change, and a row whose barcode was edited counts as one added and one deleted,
  which is what the server gets. `summary()` → "2 added, 1 edited, 1 deleted", zero parts left out.
- `status(row)` → `"new"`, `"edited"` or `""`, by the same rule.
- `changes()` → `(add, remove)` for `update_sku_mapping`: every barcode whose SKU differs from what was
  read, and every barcode read that no row has now. An edited barcode is one remove and one add.
- `loaded(mapping)` starts over from a mapping (after a save or a reload).

```
{"client": "ACME",
 "mode": "ready" | "failed",
 "rows": [{"id", "barcode", "sku", "key", "status": "" | "new" | "edited"}],
 "dirty": bool, "changes": 3, "summary": "2 added, 1 edited",
 "lost": "Your 3 unsaved changes (2 added, 1 edited) will be lost." | "",
 "saved": bool,
 "error": {} | {"title", "text", "cause", "path", "action": "save" | "load" | ""},
 "quick": {} | section 7.1}
```

### 6.3 Search and count

In the page. A row shows when its barcode or its SKU contains the search text, ignoring case; the row
being edited always shows. The count reads "60 mappings", or "12 of 60 mappings" while searching. No
match: "No mappings match “*text*”." under the head row. All rows are drawn: the largest client has under
200, and a list past a few thousand would want windowing.

### 6.4 Adding and editing

**Add mapping** clears the search and opens the draft row above the rows, on `--surface-raised`: a barcode
`.field` ("Scan or type barcode", focused), the arrow, a SKU `.field` ("Internal SKU"), **Add** (primary,
compact, enabled with both filled and no collision) and a ghost ✕ (Esc).

- Enter in barcode moves to SKU, unless the barcode is empty or already mapped. A scanner's Enter does the
  same.
- Enter in SKU calls `addMapping`. On `""` the draft empties and the focus returns to barcode, ready for
  the next one. A sentence shows under the row in danger colour.
- **Already mapped.** While the draft's barcode collides, the barcode field takes a danger border, the row
  it collides with a `--status-danger-bg` plane, and a line under the draft reads "This barcode already
  maps to **CLN-200**. Replace it with CLN-250?" with **Replace** (danger, compact), or "… Enter a SKU to
  replace it." with Replace disabled while SKU is empty. Replace calls `replaceMapping`.
- **Edit** turns a row into the same two fields with **Update**, focus on SKU. Enter in either field calls
  `updateMapping`; the collision line and Replace work as above. One draft at a time: opening another
  closes the first without saving it.
- A row added or edited and not yet saved shows the 7px dot, with `title` "Added, not saved" or "Edited,
  not saved".

### 6.5 Delete and reload

**Delete** on a row that is on the server asks first, in a `.scrim` over the card: "Delete this mapping?",
the pair in a mono chip, "Once you save, scanning this barcode on any PC will no longer count as
*SKU*.", **Cancel** and **Delete** (danger). A row added and not yet saved is removed without the
question: nothing on the server changes.

**Reload from server** with nothing unsaved reads the server (`fresh=True`) and redraws. With unsaved
changes it asks: "Reload from server?", "Your 3 unsaved changes (2 added, 1 edited) will be lost. The list
is replaced with the copy on the file server.", **Cancel** and **Discard and reload** (danger).

Esc closes an open question; Enter does not answer one.

### 6.6 Save, and leaving

**Save** (or Ctrl+S) calls `saveMappings()`: `update_sku_mapping(client, add, remove)` with
`MappingEditor.changes()`. On success the editor starts over from the mapping the server returned, the
footer reads "Saved. Every PC now uses these mappings." with a check in `--status-success` until the next
change, the page stays open, and `mappingSaved` lets `MainWindow` call `logic.set_sku_map()` on an open
session.

**Save failed** (`ProfileManagerError`): the banner. Title "Couldn’t save to the file server.", text "Your
3 changes are still here and nothing on the server changed.", the cause as a caption, the path of
`packer_config.json` in mono, and **Try again**, which saves again. While it shows, the footer's "Unsaved"
line is hidden. The rows keep their dots.

**Could not load** (when the page opens, or on a reload): the same banner, "Couldn’t load the mappings.",
the cause and the path, with **Retry**. No table, and *Add mapping* is hidden. Today this case starts
from an empty table.

**Leaving.** Close, Cancel and Esc (with no draft and no question open) call `closeMapping()` when nothing
is unsaved. With unsaved changes they ask: "Discard unsaved changes?", "Your 3 unsaved changes (2 added, 1
edited) will be lost.", **Keep editing** and **Discard** (danger). Closing the window with unsaved changes
raises the same question through `leaveAsked` and does not close the window. `closeMapping` emits
`backRequested`.

### 6.7 States

| Mockup preset | What shows |
|---|---|
| 60 mappings | the table, "60 mappings", Save disabled |
| None | "No mappings yet" / "Scan or type a product barcode to map it to a SKU." with a primary **Add mapping**, in place of the table |
| Adding | the draft row, focus in barcode |
| Already mapped | section 6.4 |
| From Packer Mode | section 7 |
| Delete | section 6.5 |
| Reload, unsaved | section 6.5 |
| Save failed | section 6.6 |

## 7. SKU mapping from Packer Mode: the quick map

ADR 0004 holds the contract. This section is how the page and the window meet it.

### 7.1 Opening

`PackerModeWidget`'s `map_sku_requested(sku)` and `map_barcode_requested(barcode)` reach `MainWindow` as
today. With no client, or (for a barcode) no open order, they only refocus the scanner, as today. Otherwise
`_open_setup` shows the mapping page with `quick`:

```
{"kind": "sku", "sku": "SER-30ML", "barcode": "",
 "hint": "Scan or type the barcode for this SKU.", "choices": []}

{"kind": "barcode", "barcode": "5906000123456", "sku": "",
 "hint": "Scanned in Packer Mode. Enter the SKU it should count as.",
 "choices": [{"sku": "SER-30ML", "label": "SER-30ML — 0 / 2 packed", "key": "ser30ml"}, …]}
```

`choices` is `order_choices(logic.current_order_state)`: the open order's lines, unfinished first.

### 7.2 The page

- The draft row is open and cannot be closed. The known side is filled and disabled; the other field has
  the focus, and takes it back whenever the focus is left on nothing.
- `hint` shows under the row in caption size. For a barcode, the choices follow as secondary compact
  buttons, one per line of the order.
- The rows have no Edit and no Delete. *Add mapping* and *Reload from server* are hidden. The search works.
- The footer holds one button, **Back to packing** (secondary). It, Close and Esc call `closeMapping()`.
- *Map SKU*: Enter in barcode calls `addMapping`, unless the barcode is already mapped: then the collision
  line shows and only a click on **Replace** goes on.
- *Map barcode…*: Enter in SKU, or a click on a choice, calls `addMapping`. A SKU that is not a choice is
  refused with "Not on this order. Pick one of the lines below." and nothing is saved. The mapping is
  saved with the order's own spelling of the SKU.

### 7.3 The add

In a quick map `addMapping` and `replaceMapping` do not touch the editor. `SetupPages` calls
`update_sku_mapping(client, {barcode: sku})` at once.

- **Saved:** returns `""` and emits `quickMapped(kind, barcode, sku, mapping)`. `MainWindow` sets
  `logic.sku_map` from the mapping and calls `_leave_setup(after)`, where `after` shows "Mapped: *barcode*
  → *SKU*" in the feedback band and, for a barcode, removes it from `logic.unknown_scans`, redraws the
  unmatched rows and replays the scan with `on_scanner_input(barcode)`.
- **Failed:** returns "Not saved. Try again." and sets the banner of section 6.6 with no button. The draft
  keeps what was typed; Enter or Add tries again.

### 7.4 Stray scans

`setup.js` listens for `keydown` on `document`. A key whose target is an input, or that carries Ctrl, Alt
or Meta, is not its business. Otherwise a one-character key is appended to a buffer, and Enter sends a
non-empty buffer through `strayScan(text)` and empties it. The buffer is emptied whenever `page` changes.

`SetupPages` re-emits it as `strayScanned`. `MainWindow` queues it only when `_setup_return` is Packer
Mode, and `_leave_setup` replays the queue after the scanner field has the focus. Opened from the shell, or
on Worker selection, a stray scan is dropped: there is nothing to scan into.

### 7.5 What a test must prove

1. After a quick map is added, `QApplication.focusWidget()` is `packer_mode_widget.scanner_input`, and keys
   typed then reach `barcode_scanned`.
2. *Map barcode…*: a barcode typed into the SKU field and Enter calls `update_sku_mapping` zero times, and
   the page is still the top of the stack.
3. With the mapping page open from Packer Mode and the focus on no field, a barcode and Enter reach
   `on_scanner_input` exactly once, after Packer Mode is back on top.
4. *Map SKU*: a barcode typed into the barcode field and Enter saves `{barcode: sku}` and returns.
5. Back to packing returns with nothing saved, and the scanner field has the focus.

## 8. Testing

Seams, all through public surfaces:

- **Pure** (`tests/test_setup_payload.py`): `last_active_text` at each boundary; `stats` singular, plural,
  thousands, none; the card order; the three badges; the failed shape; each `worker_name_problem` sentence
  and a name that passes (with a Cyrillic one); `MappingEditor` add, update, replace (with and without an
  edited row), delete, each problem sentence, the collision by normalised key, `counts`, `summary`,
  `changes` for an added, an edited-SKU, an edited-barcode and a deleted row, an edit undone, `loaded`;
  `mapping_payload`'s `dirty`, `saved`, `status` and error shapes; `quick_payload` for both kinds;
  `order_choices` (the two `_unmapped_choices` tests, moved from `tests/test_packer_mode_widget.py`).
- **`ProfileManager`** (`tests/test_profile_manager.py`): `fresh=True` sees a file changed inside the cache
  window.
- **`SetupPages`** (`tests/test_setup_pages.py`), a real bridge and a real server folder, no assertions on
  Chromium: `show_workers` pushes the cards; an unreadable `workers.json` pushes the failed shape and
  `retryWorkers` recovers; `pickWorker` emits `workerChosen`; `createWorker` returns each sentence, and on
  success creates the worker and emits `workerChosen`; `leaveWorkers` emits `quitRequested` at startup and
  `backRequested` otherwise; `show_mapping` pushes the rows; add, update, replace and delete through the
  slots change the payload; `saveMappings` writes only the changes (a mapping another PC added meanwhile
  survives) and emits `mappingSaved`; a failing write pushes the banner and keeps the rows; `reloadMappings`
  reads fresh; a load that fails pushes the failed shape; in a quick map `addMapping` writes at once and
  emits `quickMapped`, refuses an off-order SKU, and a failing write returns the sentence; `strayScan`
  re-emits; `blank` empties everything.
- **The page in a real Chromium** (`tests/test_setup_page_web.py`), one test per state of sections 5.5 and
  6.7 at least: the texts and counts drawn; a card click reaching `pickWorker`; the form opening, Enter
  reaching `createWorker`, a returned sentence shown and then cleared by typing, Esc closing it; Retry;
  the leave button's label in both contexts; the search narrowing the rows and the count; the draft's
  Enter-to-SKU and Enter-to-add; the draft emptied and refocused after an add; the collision line and
  Replace; Edit and Update; both questions and both of their answers; Delete on a new row asking nothing;
  Ctrl+S; the saved line; the banner and Try again; the leave question on Close with unsaved changes and
  none without; `leaveAsked` raising it; the quick map's locked field, hidden controls, choices and
  footer; markup in a name or a SKU shown as text; `page` `""` leaving no text.
- **`MainWindow`** (`tests/test_setup_mainwindow_seam.py`): outside test mode the window starts on Worker
  selection (the flag is patched for one test); picking sets the worker, tells the sidebar and shows the
  shell; Quit closes; the sidebar's two requests open the two pages and each returns to the page it left;
  `mappingSaved` reaches an open session's `logic`; Ctrl+E does nothing on a setup page; a close with
  unsaved changes is refused; the five proofs of section 7.5 with real key events
  (`tests/test_setup_scanner.py`); the lock lost during a quick map lands on the take-over panel; a
  freshness test: after `_leave_setup` the setup document has painted `page` `""` before the stack moved.
- **Updated:** `tests/test_shell.py` (the sidebar test patches the new method names),
  `tests/test_screen_primaries.py` (the dialog's test goes; the server-connection one stays),
  `tests/audit/test_02_concurrency_sweep.py` (`_map_on` called `MainWindow._save_sku_mapping`; it calls
  `update_sku_mapping(client, {barcode: sku})`, which is what a quick map now runs).
- **Guards:** `tests/test_style_literals_guard.py` already scans `gui/web`.

## 9. Renders and the final pass

- `scripts/render_setup.py` drives a `SetupPages` alone against a throwaway server, with payloads built by
  the pure functions at a fixed "now": Worker selection's six presets (the first also in the switch
  context), SKU mapping's eight, and the quick map for *Map SKU*.
- The four existing scripts and the new one take `--size WIDTHxHEIGHT` (default `1366x768`) and render
  every one of their frames at that size. The few `-1920` extras they wrote go.
- `scripts/render_all.py` runs the five at both sizes into
  `docs/design/ui-refresh/renders/final/<size>/<frame>-<theme>.png`. `renders/phase1` to `phase4` are
  deleted: `final/` replaces them.
- The implementer opens every PNG beside its mockup frame, fixes what does not match, lists what cannot
  match in the PR under "Departures", and embeds the two new pages' renders in the PR.

## 10. Cleanup and documents

- **Deleted:** section 12.
- **`CONTEXT.md`:** new entries *Setup document*, *Setup bridge*, *Quick map*, *Stray scan*; *Sidebar* and
  *App bridge* checked against the code; *Toast* loses the Packer Mode "SKU mapping saved" case.
- **`README.md`:** the Layout section names the three web documents; "Settings → Server Connection"
  becomes the overflow menu's *Server connection…*.
- **ADR 0003:** its last consequence ("Phase 5 decides where they live") gains a pointer to this spec.
- **`docs/design/ui-refresh/for-shared.md`** (new): every "For shared/" item of phases 1 to 5 in one list,
  grouped by the `shared/` file it lands in, each with the app-side stand-in to delete once Fulfilment has
  it. The PR body carries the same list.
- **The PR names the owner's step before a release:** the frozen Windows build over RDP with a real
  scanner. *Map SKU* by scan; *Map barcode…* with a stray scan into the SKU field; a scan during each
  switch; the scanner field after every return; and Worker selection at startup with the server folder
  unreachable.

### For shared/, from this phase

- `.field.invalid` (a danger edge on a bare input); the kit has it only for `.input`.
- The stray-key listener and the toast script, as parts of `shared/web/page.js`.
- An initials helper: both apps draw a worker's initials.

## 11. Departures from the mockups

| Mockup | Built | Why |
|---|---|---|
| 28 to 32px controls, 10pt body, 40px rows, 48px header | 44px controls (40px compact), 12pt body, 44px rows, 60px header | ADR 0002: floor density in every phase |
| SKU mapping is a card over the dimmed shell | the card on the plain plane, the shell hidden | a web page cannot dim the Qt shell; owner decision 1 |
| Cancel puts the rows back and stays | Cancel leaves, asking first when there are unsaved changes | on a full-window page a Cancel that stays has no way out but Close |
| Close does nothing | Close leaves, as Cancel | the mockup left it free |
| SKU is upper-cased as it is typed | kept as typed | matching already ignores case, and saved SKUs would be rewritten |
| a barcode collides only when identical | when it normalises alike | that is one key to `PackerLogic` |
| Delete always asks | a row never saved is removed without asking | nothing on the server changes |
| the save-failed banner says "The file server didn’t respond" and names `sku_mapping.json` | the real cause, and `packer_config.json` | honest about the failure and the file |
| From Packer Mode everything is live, and the add waits for Save | the quick map of section 7 | owner decisions 2 and 3, ADR 0004 |
| the name is re-checked on every key after a failed Create | the sentence goes when the text changes and is checked again on Create | the rules live in Python only |
| "Just created" on a new card | also "Not active yet" for a worker made earlier who never packed | the mockup has no such worker |
| no state for mappings that cannot be read | the banner with Retry | today it starts from an empty table |

## 12. Deleted

- `gui/sku_mapping_dialog.py`, `gui/worker_selection_dialog.py`.
- From `gui/main_window.py`: `_select_worker`, `open_sku_mapping_dialog`, `_save_sku_mapping`,
  `_unmapped_choices`, the two `QInputDialog` flows, the "No Client Selected", "Overwrite Mapping?",
  "Reload Warning" and worker "Error" message boxes, and the imports left unused (`QInputDialog`, `QDialog`).
- `tests/test_screen_primaries.py`'s SKU mapping test.
- `docs/design/ui-refresh/renders/phase1` to `phase4`.
- Anything else in `gui/` that an audit finds unused once the dialogs are gone: a name defined in `gui/`
  and referenced nowhere outside `tests/`, and a QSS selector in `gui/` that no widget's class or object
  name matches. The audit run for this spec found none beyond the list above; the implementer runs it
  again at the end.

## 13. Out of scope

- The path-recovery prompt when the server folder is missing at startup: it is a `shared/` dialog.
- Mapping an unmatched scan to a SKU outside the open order from Packer Mode.
- Reading workers or mappings off the UI thread.
- Unused functions in `packing_tool/` (`client_exists`, `save_client_config`, `start_session`, …): not Qt,
  not this task's.
- The lock-lost message box outside Packer Mode, and the export failure boxes of phase 4.
- Any edit under `shared/`.
