# UI refresh phase 4: Sessions and Session details on the web tier

- **Date:** 2026-10-08. dev-runner run 77, Todoist task "UI refresh phase 4" (4 of 5).
- **Mockup followed:** `docs/design/ui-refresh/mockups/Packer App.html`, frames 7a to 7h (Sessions) and 8a to
  8f (Session details). Frame ids and the two group notes are in `Packer Screens.html`. Every departure is in
  section 12.
- **Decisions it rests on:** ADR 0001 (web-asset guardrails), ADR 0002 (every screen on the web tier;
  `shared/` is never edited here), ADR 0003 (the shell's pages are one web document).
- **Depends on:** phase 3 (merged, PR #200): `gui/web/app.html`, `AppBridge`, `AppPages`.

## 1. What this is for

Sessions is where a packer picks the list to pack and a lead sees what every PC is doing. Session details is
where the lead reads how a session went. Both are Qt widgets (`gui/session_browser/`, about 2,300 lines)
inside the new shell: a filter row, a sortable table, a caption line that doubles as a preview, and a detail
page of three tabs. This phase redraws them to the approved mockup as two more pages of the app document, and
deletes the Qt package.

**Done when:** start, resume, take over, both exports and refresh do what they do today, with their tests
ported; a freshness test covers Sessions and Session details; renders of 7a to 7h and 8a to 8f in both themes
are in the PR; section 12 lists every departure; `gui/session_browser/` and
`packing_tool/session_history_manager.py` are gone; and the suite passes.

## 2. Owner decisions (2026-10-08, runner question 69)

1. **Take over.** A stale lock only, as today. A session that is Active on another PC shows who has it, and
   its action is disabled. The confirm appears once that PC stops responding.
2. **Orders in Session details.** What the session recorded: packed, in-progress and skipped orders. The
   packing list is not read, so orders nobody started are not listed.
3. **Date range.** The last 30 days by default.
4. The design in sections 4 to 11 was approved as presented, and the owner approved the written spec in
   advance.

## 3. Facts the design rests on

- A registry entry (`SessionRegistryManager.get_all_entries`) carries `session_id`, `packing_list_name`,
  `status`, `worker_id`, `worker_name`, `pc_name`, `started_at`, `last_updated`, `completed_at`,
  `duration_seconds`, `total_orders`, `completed_orders`, `skipped_orders`, `total_items`, `work_dir`,
  `session_path` and `metrics` (a finished session's, else `None`). A list nobody started carries
  `packing_list_path`, `created_at`, `total_orders`, `total_items` and no `work_dir`. `total_items` is the
  units on the list, not the units packed.
- `SessionRegistryManager.read_registry` returns an empty registry when the file cannot be read. With the
  server away, today's list says "No sessions yet".
- A lock is stale after 120 s without a heartbeat (`SessionLockManager.STALE_TIMEOUT`); the heartbeat is
  every 60 s. The list calls a session *Stale* after 300 s (`STALE_HEARTBEAT_SECONDS`). Between the two a row
  reads *Active* while its lock can already be taken.
- `acquire_lock` refuses a live lock held by another process. A stale one is released by
  `force_release_lock(work_dir, expected=lock_info)`, which does nothing if the lock changed meanwhile
  (AUDIT-02-1). Today the question is a `QMessageBox` inside `MainWindow._acquire_lock_with_stale_prompt`.
- A started session's files, in its `work_dir`: `session_summary.json` once it has ended (counts, `metrics`,
  `orders`, `skipped_orders`), `packing_state.json` while it runs (`completed`, `in_progress`,
  `skipped_orders`, `skipped_orders_timing`, `progress`).
- A packed order's record: `order_number`, `started_at`, `completed_at`, `duration_seconds`, `items_count`
  (units), `corrections`, `extra_scans_count`, `unknown_scans_count`, `time_to_first_scan_seconds`, `items`.
  An item is one scan: `sku`, `title`, `quantity`, `row`, `scanned_at`, `time_from_order_start_seconds`,
  `confirmation_method` (`scanned`, `manual`, `force_confirmed`). Extra and unknown scans are counts: no SKU,
  no barcode, no time.
- `SessionDetailPage` reads those files on the UI thread and logs a file that fails to read; the page then
  shows empty tabs. Its "standardized data" loader and its `SessionHistoryManager` fallback are dead: no
  caller sends `orders_total`, and every started entry has a `work_dir`. `SessionHistoryManager` has no
  other user.
- The Qt list sorts by status priority and by any column header. Double-click opens the details of any row.
  The search matches list name, session id, worker name, worker id and PC.
- A successful start already raises the toast "Loaded N orders from LIST." and then a "Session Loaded" or
  "Session Resumed" message box that says the same.
- Phase 3 left the view hidden under the Qt Sessions page (its section 8, "known limits"). With Sessions in
  the document the view is hidden only under Packer Mode.

## 4. Structure

### 4.1 Files

| File | Holds |
|---|---|
| `packing_tool/session_details.py` (new) | `load_session_details(entry)`: reads a session's files, no Qt. `SessionFilesError(path, cause)`. |
| `gui/sessions_payload.py` (new) | Pure functions, no Qt, no I/O: `sessions_payload`, `details_payload`, `takeover_payload`, `session_export_rows`, `detail_export_rows`, and the status table. |
| `gui/sessions_page.py` (new) | `SessionsPage(QObject)`: the refresh and details workers, the 2-minute timer and its setting, the filter state, the exports and their file dialogs. Pushes `sessions`, `details` and `confirm` to the bridge. |
| `gui/workers.py` | gains `RegistryRefreshWorker` (moved) and `SessionDetailsWorker`. |
| `gui/app_bridge.py` | `AppBridge` gains three properties and twelve slots (section 4.2). |
| `gui/app_pages.py` | `AppPages` is the view alone. |
| `gui/web/app.html`, `app.css`, `app.js` | the two pages, the pane and the take-over dialog. |
| `gui/web/floor.css` | floor sizes for the segmented control, the input, the menu and the dotted badge. |

### 4.2 `AppBridge`

`page` gains `"sessions"` and `"details"`.

| Property | Type | Empty | Carries |
|---|---|---|---|
| `sessions` | map | `{}` | section 5 |
| `details` | map | `{}` | section 7; empty means no details are open |
| `confirm` | map | `{}` | section 6; empty means no question is open |

Slots the page calls, each emitting a Python-facing signal: `setSessionsFilter(tab, query, dateFrom,
dateTo)`, `clearSessionsFilter()`, `refreshSessions()`, `setAutoRefresh(bool)`, `sessionAction(key)`,
`sessionDetails(key)`, `exportSessions(format)`, `closeDetails()`, `setDetailsFilter(text)`,
`retryDetails()`, `exportDetails()`, `answerTakeOver(bool)`.

### 4.3 `AppPages`

The Qt stack and the `browser` argument go. `widget(index)` is the view for all three indices,
`web_is_current()` is deleted, and `PAGE_BROWSER` sets `page` to `"details"` when `bridge.details` is not
empty, else `"sessions"`. So leaving details for Packing and coming back returns to the details that were
open, and the sidebar's *Sessions* is lit for both.

### 4.4 Who decides what

Python decides the data: which sessions a tab, the dates and the search leave, each row's action and whether
it is enabled, every sentence, every number in details, which orders match the details filter. A row carries
its pane, so selecting one needs no round trip.

The page keeps three pieces of view state and nothing else: the selected row, whether the Export menu is
open, and the orders opened in details. The selected row is dropped when the tab changes or the row
leaves the list; the opened orders when another session's details open.

The three text inputs and two date inputs are in the page. The page sends their values through
`setSessionsFilter` and `setDetailsFilter` on every change; Python sends them back in the payload, and the
page writes a value into an input only when that input does not have the focus.

### 4.5 `SessionsPage`

`SessionsPage(bridge, registry_manager, lock_manager, *, window, is_showing, client_label, toast)`.

- `load_client(client_id)` clears the list, shows 7e and refreshes. `MainWindow.on_client_changed` calls it,
  as it called the widget.
- `refresh()` starts `RegistryRefreshWorker`. A result for another client than the current one is dropped,
  as today. While details of an Active session are open, a finished refresh also re-reads them.
- `page_shown()` refreshes. `MainWindow` calls it when the Sessions page becomes current.
- The timer is today's: 2 minutes, saved under `QSettings("PackingTool", "SessionBrowser")`
  (`auto_refresh_enabled`, `last_refresh_time`), and a tick refreshes only while `is_showing()` is true.
- `set_context(open_key, server_down)`: which session is open on this PC, and whether the server is
  unreachable. `MainWindow` calls it wherever it pushes the pages.
- `show_entries(entries)`: display these entries as a finished refresh would. The seam for tests and for the
  render script.
- Signals: `startRequested(dict)` and `resumeRequested(dict)` with today's payloads (`resumeRequested` adds
  `take_over`, the stale lock or `None`), and `showPackingRequested()`.

## 5. Sessions

Layout, top to bottom, in the document's column (20px 24px padding, 16px gap): the failed banner (7f), the
toolbar, then a row that takes the rest of the height: the list card, and the pane (360px) when a row is
selected.

### 5.1 Toolbar

One row, 8px gap, each control 44px high:

- **Tabs.** A segmented control: *All*, *Open*, *Finished*, *Abandoned*, each with its count in mono. *Open*
  is Not started, Active, Paused, Stale; *Finished* is Completed, Incomplete. A count is the sessions of that
  tab inside the date range, whatever the search says. While the first load runs the counts read "–".
- **Search.** A search glyph, "Search sessions", and a clear button when it holds text. It matches the list
  name, the session id, the worker's name and id, and the PC, ignoring case. It takes the row's spare width.
- **Date range.** Two native date inputs in one box, labelled *From* and *To*. By default *From* is 30 days
  ago and *To* is today, worked out at each push until the packer changes one, so a PC left on overnight
  still shows today's sessions. A session is dated by `started_at`, or `created_at` for a list nobody
  started, in local time. A session with no readable date is always listed. An emptied input is no bound.
- **Refresh.** An icon button, title "Refresh  F5", disabled while a refresh runs.
- **Stamp and switch.** Two lines at 10pt: "Last refreshed 14:06:31" (the time in mono; "Refreshing…" while
  one runs; red and bold after a failure), and the *Auto-refresh (2 min)* switch.
- **Export.** An icon button, title "Export the rows shown", opening a menu: a caption "Export the 40
  sessions shown", then *CSV* and *Excel* with `.csv` and `.xlsx` in mono at the right. Disabled with no
  rows.

### 5.2 The list card

- **Head,** 40px: Status, Session, Age, Packing, Orders, Items, Last touched, on the grid
  `150px 150px 64px minmax(0,1fr) 170px 76px 230px`. With the pane open the last two columns go and the grid
  is `150px 150px 64px minmax(0,1fr) 170px`.
- **Rows,** 44px, newest first by start date. No column sorting.
  - *Status*: the status chip (section 5.4).
  - *Session*: the id in bold mono.
  - *Age*: since the start, right-aligned mono, in the coarsest unit: "25m", "3h", "13d".
  - *Packing*: the packing list's name, cut with an ellipsis.
  - *Orders*: a 56px by 6px bar and "38 / 120" in mono. The bar's fill is `status_success_dot` for
    Completed, `status_danger_dot` for Incomplete, `text_secondary` otherwise. With no orders known, "—" and
    an empty bar.
  - *Items*: the units on the list, right-aligned mono; "—" in `text_disabled` at zero.
  - *Last touched*: "Maria · WH-PC-02 · 11:20" for today, "… · 13d ago" before that, "—" when nobody has.
- A row is a `button`. A click selects it: `selection_bg` with a 4px `selection_border` rule on its left.
  Its title is "Double-click: Resume session" (the row's action). A double-click runs the action when it is
  enabled.
- **Foot,** 40px, 10pt: a solid dot and "Set by a person", a hollow dot and "Inferred by the system", then at
  the right "Double-click a session for its action" and the count in mono: "40 sessions", or "12 of 40
  sessions" while the search holds text.

### 5.3 The pane

- **Head:** the status chip and a close button (title "Close  Esc"); the id at 17pt bold mono; the list's
  name at 14pt bold; then at 10pt "Set by a person · paused by Maria, 11:20".
- **Body,** scrolling: *Orders done* with "71 / 110" in bold mono, an 8px bar, and "2 skipped" or "None
  skipped"; then one row each for Worker, PC, Duration, Items, Scan corrections, Unknown scans, Last touched.
  - PC is followed by "(this PC)" for the session open here.
  - Duration is "3h 12m", with "so far" on an Active session, measured from its start; "—" when unknown.
  - Scan corrections and Unknown scans come from the entry's `metrics`; "—" when it has none.
- **Foot:** a note when there is one (section 5.5), the primary action at full width, a ghost *View details*
  under it when the session has files and the primary action is something else, and at 10pt "Or double-click
  the row".

The sentence after "Set by …":

| Status | Sentence |
|---|---|
| Not started | no orders packed yet |
| Active | scans arriving from WH-PC-02; for the session open here, "open on this PC" |
| Paused | paused by Maria, 11:20 |
| Stale | WH-PC-02 stopped responding, 11:20 |
| Completed | every order packed |
| Incomplete | closed by Maria with 39 orders unpacked |
| Abandoned | untouched for 5 days |

A time is "11:20" today and "6 Oct, 11:20" before that. A missing worker or PC drops its words ("paused,
11:20").

### 5.4 The status chip

A 28px badge with an 8px dot before the word. The dot is solid when a packer set the status (Paused,
Incomplete) and hollow when the system inferred it. The tone is the mockup's:

| Status | Word | Tone |
|---|---|---|
| `not_started` | Not started | neutral |
| `in_progress` | Active | info |
| `paused` | Paused | warning |
| `stale` | Stale | warning |
| `completed` | Completed | success |
| `incomplete` | Incomplete | danger |
| `abandoned` | Abandoned | neutral |

A status the registry invented is neutral, hollow, and reads as its own name with the underscores as spaces.

### 5.5 A row's action

| Status | Action | Enabled |
|---|---|---|
| Not started | *Start packing* | yes |
| Active, open on this PC | *Go to Packing* | yes |
| Active, elsewhere | *Resume session* | no. Note: "Open on WH-PC-02 right now. It can be taken over once that PC stops responding." |
| Paused, Incomplete | *Resume session* | yes |
| Stale | *Resume session* | yes. Warning note: "WH-PC-02 stopped responding. You will be asked before this PC takes over." |
| Completed, Abandoned | *View details* | yes |

Two things disable *Start packing* and *Resume session* on every row, each with its note:

- another session is open on this PC: "2026-10-07_1 is open on this PC. End it before opening another.";
- the server is unreachable: "Server unreachable. Sessions cannot be opened until it answers."

*Go to Packing* shows the Packing page. *View details* opens section 7. The list's *Stale* is aligned with
the lock: `STALE_HEARTBEAT_SECONDS` becomes 120, so a row reads Stale exactly when its lock can be taken.

### 5.6 States

| Frame | When | Drawn |
|---|---|---|
| 7h | no client | the centred card of phase 3 with "Choose a client" / "Pick a client in the bar above to see its sessions." / *Choose a client*. Nothing else. |
| 7e | a client's first load | counts "–"; in the list a 44px line with a refresh glyph and "Reading sessions from the server…", then 12 skeleton rows; the foot's count "–". |
| 7a | loaded | as above. |
| 7g | loaded, the client has no sessions | the toolbar with zero counts; in the list a centred glyph, "No sessions yet", "Sessions appear here once someone starts packing for this client." |
| 7d | loaded, nothing matches | a centred glyph, "No sessions match", the sentence below and *Clear filters* (secondary), which empties the search and puts the dates back. |
| 7f | a refresh failed | a danger banner above the toolbar: "Refresh failed", the sentence below and *Retry*. The list the page had stays and stays usable; the stamp turns red. |

7d's sentence: with a search, "Nothing in Open between 8 Sep and 7 Oct has “2025-12” in its id, packing list,
worker or PC."; without, "No open sessions between 8 Sep and 7 Oct." On *All* it reads "No sessions …" and
"Nothing between …". With one date emptied the range reads "since 8 Sep" or "up to 7 Oct", and with both it
is left out.

7f's sentence: "`\\fs01\packer\Sessions\CLIENT_ACME` could not be read at 14:08:31: the network path was not
found. The list below is from 14:06:31." The last sentence is left out when there is no earlier list. To
make it true, `RegistryRefreshWorker` lists the server's root folder before it reads the registry and lets the
`OSError` through; the cause is the error's own text.

A refresh with a list already on screen keeps the rows and the selection; only the stamp and the Refresh
button change.

## 6. Start, resume and take over

`SessionsPage` handles `sessionAction(key)`:

- *Start packing* emits `startRequested` with today's payload.
- *Go to Packing* emits `showPackingRequested`.
- *View details* opens section 7.
- *Resume session* reads the lock in the session's `work_dir`. If another process holds it and it is stale,
  the page shows the question (7c) and nothing starts. Otherwise it emits `resumeRequested`.

**7c,** a dialog over a scrim, drawn by the document (`floor.css` has both):

- title "Take over `2026-10-07_2`?" with a warning glyph;
- "WH-PC-02 stopped responding at 13:52 while Georgi was packing. If it comes back, it is told the session
  moved here." (The worker's words are dropped when the lock names none.)
- in `text_secondary`: "Everything saved so far comes with you: 52 of 96 orders packed."
- *Cancel* (secondary) and *Take over and resume* (primary). Esc cancels.

*Take over and resume* emits `resumeRequested` with `take_over` set to the lock that was read.
`MainWindow._start_or_resume_from_browser` and `start_shopify_packing_session` pass it on, and the lock step
becomes:

1. `acquire_lock`. Taken: go on.
2. Refused, the lock is stale and `take_over` is set: `force_release_lock(work_dir, expected=take_over)`,
   then `acquire_lock` again. A failure is frame 3c with the lock's message.
3. Refused, stale, no `take_over` (the list was behind, or this is a *Retry* of 3c): frame 3c, "Session
   could not be opened", "WH-PC-02 stopped responding while this list was open there. Resume it from
   Sessions to take it over."
4. Refused, live: frame 3c with the lock's message, as today.

Deleted with this: the "Stale Lock Detected" question, the "Session Loaded" and "Session Resumed" boxes (the
toast says it), and the "Session Active" warning (the row is disabled; if a start still arrives with a
session open, a toast says "2026-10-07_1 is open. End it before opening another."). After a take-over the
toast is "Took over 2026-10-07_2 from WH-PC-02."

## 7. Session details

One scrolling page. The scroller reaches the view's edges, so the scrollbar is at the window's edge.

### 7.1 Loading

`sessionDetails(key)` shows the page at once with what the list knows (the head and the facts row), and
`SessionDetailsWorker` runs `load_session_details(entry)`. Until it lands the page shows one line under the
facts: "Reading the session's files…". A result for another session than the one open is dropped.

`load_session_details` reads `session_summary.json`, `packing_state.json` and the session's
`session_info.json` with `json.load` (not the JSON cache: a refresh must see the file as it is now). It
builds what `SessionDetailPage._load_session_details` built, including the partial summary of a session with
no summary file. A summary or state file that exists and cannot be read raises `SessionFilesError` with the
file's path and the cause; a session with neither file raises it with the `work_dir` and "it holds no
session files". An unreadable `session_info.json` is logged and skipped, as today.

### 7.2 Layout

1. **Head:** *Sessions* with a left arrow (title "Back to Sessions  Alt+Left"), the id at 17pt bold mono,
   the status chip, "Set by … · …" at 10pt cut with an ellipsis, and *Export Excel* (secondary).
2. **8f banner** when the files could not be read.
3. **8b strip** on an Active session.
4. **Facts,** one card in seven cells (`minmax(0,1.4fr) repeat(6, minmax(0,1fr))`), a 10pt label over a bold
   value: Client, Packing list, Worker, PC, Started, Completed, Duration.
5. **Stat cards,** one card in five cells: a 28pt bold value with a 12pt "of N" beside it, the label at 12pt,
   a 10pt note.
6. **Timing and scan quality,** one card.
7. **Orders,** one card.

Items 5 to 7 are drawn once the files are read.

### 7.3 Facts

| Label | Value |
|---|---|
| Client | the command bar's text for the client: "Acme Cosmetics (ACME)" |
| Packing list | the summary's name, else the list entry's |
| Worker | "Maria (W-004)", the name alone, the id alone, or "—" |
| PC | the PC, or "—" |
| Started | "6 Oct, 08:02:11", or "—" |
| Completed | the same; "Still packing" on an Active session; "—" otherwise |
| Duration | "3h 12m"; with "so far" on an Active session, measured from its start; "—" when unknown |

When the files could not be read, Started and Duration come from the list entry and Completed is "—".

### 7.4 Stat cards

| Label | Value | "of" | Note |
|---|---|---|---|
| Orders packed | orders packed | "of 120" | "so far" when Active; else "39 not packed", or nothing |
| Items packed | units in the packed orders (`items_count` summed) | "of 402" when the list's total is known | "so far" when Active |
| Orders per hour | one decimal, or "—" | | "No timing data" without timing; "so far" when Active |
| Items per hour | a whole number, or "—" | | the same |
| Skipped orders | the count | | "not packed" when any |

### 7.5 Timing and scan quality

A title row: "Timing and scan quality" in bold and, at 10pt, "Only data from completed orders is shown."
(plus " Figures so far." when Active). Then three groups side by side, split by a rule, each a 10pt bold
label over tiles of a 17pt bold value and a 10pt label:

- **Order time** (3 tiles): Average per order; "Fastest · #10407"; "Slowest · #10422".
- **Item time** (2): Average per item; Average to first scan.
- **Scan quality** (4): Scan corrections; Corrections per order (two decimals, "—" with no packed order);
  Unknown scans; Extra scans.

Times read "45s", "4m 5s", "1h 2m". On an Active session the two time groups are titled "Order time so far"
and "Item time so far".

**8c, no timing.** A session has timing when its `metrics` is not empty. Without it the two time groups give
way to one block: an info glyph, "Timing metrics are not available for this session." in bold, and at 10pt
"Its files hold no scan times, so durations and rates cannot be worked out. Counts and flags are complete."
Scan quality stays, counted from the orders.

### 7.6 Orders

- **Bar:** "Orders" in bold; a 300px filter, "Filter by order number", with a clear button; "Showing 38 of
  38 recorded orders"; then at the right *Expand all* and *Collapse all* (secondary).
- **Head,** 40px, sticky at the top of the scroller: Order / Item, Duration, Count, Started / Scanned,
  Completed, Flags, on `minmax(0,1fr) 150px 140px 150px 120px minmax(0,1.25fr)`.
- **Order row,** 44px, a `button` with `aria-expanded`: a chevron, the number in bold mono (through
  `order_label`), then by kind:

| Kind | Duration | Count | Started | Completed | Flags |
|---|---|---|---|---|---|
| packed | "2m 14s", or "—" | "5 items" | 08:14:02 | 08:16:16 | below |
| in progress | "—" | "3 / 5 items" | "—" | "—" | *In progress* (info) |
| skipped | "—" | "—" | the time it was skipped, or "—" | "—" | *Skipped* (warning) |

  Packed orders come first in the order they were packed, then in-progress, then skipped. An order that is
  both in progress and skipped is listed once, as skipped.
- **Flags** on a packed order, as 24px badges at 10pt: *Forced confirm* (danger) when any item was forced,
  *Manual confirm* (neutral) when any was confirmed by hand, "2 extra" (warning), "1 correction" / "3
  corrections" (info), "1 unknown" (neutral).
- **Item rows** of an open order, 40px on `surface_raised`, the first cell indented 30px:
  - a packed order: one row per list line (its scans grouped by `row`, by SKU when a scan has none): the SKU
    in mono and the product's title in `text_secondary`; "+12s" (the first scan's time from the order's
    start); "×3"; the first scan's time; its flags (*Forced confirm*, *Manual confirm*). An order with no
    item records shows one row, "Item details not available".
  - then "2 extra scans · not in this order" with the *Extra* badge (warning), and "1 unknown scan · barcode
    not recognised" with "1 unknown" (neutral). No SKU and no time: the session's files hold counts.
  - an in-progress order: one row per line with the SKU and "2 / 3".
  - a skipped order has no rows and no chevron.
- The filter is trimmed and a leading `#` dropped; an order matches when its number contains it, ignoring
  case. *Expand all* opens the listed orders.
- **8e:** with nothing matching, under the head: a glyph, "No orders match", "No order number in this session
  contains “10999”." and *Clear filter*. The count reads "Showing 0 of 38 recorded orders".
- A session with no recorded orders shows, under the head, "No orders were recorded for this session."

### 7.7 States

| Frame | When | Drawn |
|---|---|---|
| 8a | a finished session | as above. |
| 8b | Active | an info strip under the head: "**Still packing on WH-PC-02.** Every number below is so far and refreshes with the list." and at the right "Last refreshed 14:06:31". "so far" as sections 7.3 to 7.5 say. Each finished list refresh re-reads the files. |
| 8c | no timing | section 7.5. |
| 8d | an order opened | section 7.6. |
| 8e | the filter matches nothing | section 7.6. |
| 8f | the files could not be read | a danger banner: "The session's files could not be read", "`<path>` could not be read: <cause>. Timings, metrics and orders appear once it can be read; the facts below come from the session list." and *Retry*. The facts row from the list entry; no cards, timing or orders; *Export Excel* disabled. |

*Export Excel* is also disabled, with the title "No order data to export", when the session recorded no
packed orders.

*Sessions* (and Alt+Left) closes the details and returns to the list with that session's row selected.

## 8. Exports

Both open a Qt save dialog from the bridge slot, in `SessionsPage`, with `window` as the parent.

- **Sessions:** the rows shown, in the order shown. Today's columns and file names:
  `sessions_<client>.csv` / `.xlsx`; Status, Packing List, Session ID, Worker, PC, Progress, Started,
  Duration (s), Total Items, Total Orders, Completed Orders, Skipped Orders. CSV writes the raw status,
  Excel its word, as today.
- **Session details:** `session_<id>.xlsx`, sheet "Session Details", one row per item scan of the packed
  orders, today's eight columns.
- Success is a toast: "Exported 40 sessions to sessions_ACME.csv", "Exported 2026-10-06_1 to
  session_2026-10-06_1.xlsx". A failure keeps the "Export Failed" message box. A cancelled dialog does
  nothing.

## 9. `MainWindow`

- Builds `SessionsPage` in place of `SessionBrowserWidget`, as `self.sessions`, and `AppPages()` with no
  argument. `startRequested` and `resumeRequested` go to today's `_handle_start_packing_from_browser` and
  `_handle_resume_session_from_browser`; `showPackingRequested` shows the Packing page.
- `session_tabs.currentChanged` calls `sessions.page_shown()` for `PAGE_BROWSER`.
- `_push_pages` and `_sync_shell` call `sessions.set_context(...)`; ending a session reaches it through
  `_push_pages`. The open key is the session id and the list name of the session open here.
- `_sync_client_state` no longer has a Qt page to leave; it still shows Packing when no client is chosen.
- `_toast` does not change: it asks whether the view is visible, and the view is now visible on Sessions too,
  so a toast raised there is the document's.
- After a take-over the start's toast is "Took over … from …" in place of "Loaded N orders from …".
- A *Retry* of frame 3c repeats the start with the same `take_over`. The lock is released only if it is
  still the lock that was asked about, so a retry can never take a lock nobody was asked about.
- `SessionHistoryManager` is no longer built.

The command bar on Sessions is unchanged: the sidebar toggle, the client, the open session's id and ⋯.

## 10. Freshness

The view is hidden only under Packer Mode, so phase 3's known limits are gone, and its freshness tests stop
hiding the view behind Sessions: they cover the shell with Packer Mode's widget, which is what hides it now.

**The freshness test,** once for Sessions and once for Session details, in a real Chromium on a shown
`MainWindow`: show A (client A's sessions; session A's details) and wait for its paint; cover the shell (the
stacked widget shows Packer Mode's widget, so the view is hidden); push B through `SessionsPage`
(`show_entries` with other sessions; details of another session); show the shell; wait until the painted
revision equals the bridge's; assert the DOM holds B's ids and none of A's.

## 11. What the mockup leaves free

- **Keyboard.** Every action is a `button`. A session row and an order row are buttons; the kit's focus ring
  shows. In the page: Esc closes the Export menu, then answers the take-over question with Cancel, then
  closes the pane; F5 refreshes on Sessions; Alt+Left goes back from details. These reach the page only
  while it has the focus, which a click in it gives. Ctrl+1/2/3 and Ctrl+E keep working after a click in the
  page (phase 3's test covers it).
- **1366×768.** Nothing scrolls the Sessions page: the list and the pane's body scroll inside themselves.
  The toolbar does not wrap; the search field gives up its width first. Session details scrolls as a whole.
- **Long data.** A list name, a product title and the "Set by" line are one line with an ellipsis and carry
  the full text as a `title`.
- **Motion.** None (ADR 0001). The skeleton rows are still.
- **Copy.** *Start packing*, *Resume session*, *View details*, *Go to Packing* and *Retry* are the words used
  elsewhere in the app. A disabled action always has a note saying why.
- **Markup in data.** A list name, worker, PC or SKU that is markup is shown as text (`textContent`).

## 12. Departures from the mockup

| # | Mockup | Built | Why |
|---|---|---|---|
| 1 | 7c takes over a session that is Active on another PC | only a stale lock is taken over; an Active one is disabled with a note | owner decision 1 |
| 2 | 7c's body for a live take-over | not built | follows from 1 |
| 3 | Details lists every order on the list, not-started ones too | packed, in-progress and skipped orders; "Showing N of N recorded orders" | owner decision 2 |
| 4 | Item rows show "scanned / qty" and a per-item duration | "×N" and "+Ns" from the order's start | the session's files hold scans, not the list's quantities |
| 5 | Extra and unknown rows name a SKU, a barcode and a time | a count and a sentence | the files hold counts only |
| 6 | An in-progress order shows a running duration | "—" | the page is not a clock; the list refresh carries the numbers |
| 7 | No way into details for a session whose action is Resume | a ghost *View details* under the action | 8b is the details of an Active session |
| 8 | Active on this PC: *Resume session* | *Go to Packing* | the session is already open; nothing is resumed |
| 9 | (not drawn) | with another session open, or the server down, the action is disabled with a note | replaces the "Session Active" message box; ADR 0002 says an outage disables the session actions |
| 10 | Refresh always swaps the list for skeleton rows | only a client's first load does; a refresh keeps the rows | a 2-minute auto-refresh must not blank a list someone is reading |
| 11 | Search matches the id and the packing list | worker and PC too | it does today; phase 3 kept its wider filter the same way |
| 12 | *Clear search* in 7d | *Clear filters*: the search and the dates | the dates can be what excludes everything |
| 13 | Dates read "8 Sep" and "7 Oct" in the toolbar | native date inputs in the PC's format | the platform's picker, no library; 7d's sentence still reads "8 Sep" |
| 14 | Items column: units packed | units on the list | the registry holds the list's total |
| 15 | Age "13 d", "3 h" | "13d", "3h" | today's format, with its tests |
| 16 | "Abandoned: untouched for 5 days" as a fixed sentence | the real number of days | data |
| 17 | 8f: "is in use by another program" | the real cause | data |
| 18 | 7f path `\\fs01\packer\ACME\sessions` | the client's real sessions folder | data |
| 19 | (not drawn) | details show "Reading the session's files…" while a worker reads them | the read is off the UI thread now |
| 20 | "Skipped orders: packed at the end" | "not packed" | a skipped order that is packed later leaves the skipped list |
| 21 | Export file names `ACME-sessions-2026-10-07.csv`, `session-<id>.xlsx` | today's `sessions_ACME.csv`, `session_<id>.xlsx` | "export behaves as today" |
| 22 | The connection banner is drawn in the page | the Qt banner above the view, as phases 1 and 3 built it | it works above the view; moving it is not this task |
| 23 | Hairlines in `border_subtle`, control edges in `border`, Segoe UI, Consolas | the kit's edges, the bundled Inter and the theme's mono | phases 1 to 3, rows 13 and 14 of phase 3 |
| 24 | F5's "tinted ground means still live" (CONTEXT.md) | the mockup's tones: Completed is tinted green, Abandoned is neutral | the mockup is the brief; CONTEXT.md is updated |
| 25 | *From* and *To* captions in the date box | hidden when the page is narrower than 1260px (1366px with the rail open); the box keeps its title, "Date range" | native date inputs are about 120px wider than "8 Sep"; the Export button went off the page at 1366px |
| 26 | Tabs padded 12px | 8px in this toolbar, and 2px between a date and its picker button | the same fit; Chromium leaves 24px there |

## 13. For shared/

To raise on Fulfilment's side. Nothing here blocks this phase.

- What `gui/web/floor.css` gains in section 4.1, as kit components at floor density.
- A badge with a leading dot (`.badge > .dot`, solid or hollow) as a kit component.
- `shared/components/card.py` has a comment naming `OverviewTab` and `MetricsTab`, which this phase deletes.

## 14. Testing

Seams, all through public surfaces:

- **`load_session_details`** (`tests/test_session_details.py`), ported from `tests/test_session_detail_page.py`:
  an entry loads its details from a summary; the list name comes from the summary, else the entry; an
  unfinished list loads from `packing_state.json` alone; a partial summary has timing metrics when the
  completed orders have durations and none when they do not; an unreadable summary raises `SessionFilesError`
  with its path; a `work_dir` with no files raises it; an unreadable `session_info.json` does not.
- **Pure payloads** (`tests/test_sessions_payload.py`), ported from `tests/test_sessions_list_columns.py`,
  `test_sessions_list_status.py`, `test_sessions_list_empty.py` and `test_confirmation_methods.py`:
  - age, last touched (today and older), "—" for an untouched session; orders "9 / 14" and "—";
  - only Paused and Incomplete are manual; the tone table; an unknown status still makes a chip;
  - the tabs and their counts; the date range, its defaults and an entry with no date; the search over all
    five fields; newest first;
  - `mode` is `empty` with no entries and `ready` otherwise; the no-match sentences for each range shape;
  - each row of section 5.5's table, with another session open, with the server down, and for the session
    open here;
  - the pane's facts and each sentence of section 5.3;
  - the failed block with and without an earlier list;
  - `takeover_payload` with and without a worker;
  - `details_payload`: the facts; "so far" on an Active session; each stat card; timing and no timing;
    fastest and slowest name their orders; scan quality counted from the orders without metrics; packed,
    in-progress and skipped rows in order; an order both in progress and skipped listed once; scans grouped
    by line; the flags for manual and forced items and for extras, corrections and unknowns; the filter with
    and without `#`; the loading and error shapes; `canExport`;
  - `session_export_rows` and `detail_export_rows` keep today's columns.
- **`RegistryRefreshWorker`** (`tests/test_session_selector_packing_lists.py`, kept and repointed at
  `SessionsPage`): a packing list uploaded after the registry was built appears. New: an unreachable server root
  emits `refresh_failed`.
- **`SessionRegistryManager`** (`tests/test_session_registry.py`): a heartbeat 130 s old resolves to stale.
- **`SessionsPage`** (`tests/test_sessions_page.py`), with a real bridge and no Chromium: `load_client`
  pushes the loading shape and then the rows; a result for another client is dropped; the filter slots
  change the rows; `clearSessionsFilter`; the timer refreshes only while showing and saves the switch;
  `page_shown` refreshes; `sessionAction` emits start and resume with today's payloads, and nothing for a
  row whose action is disabled; a stale lock held by
  another process raises `confirm` and emits nothing, *Cancel* clears it, *Take over* emits `resumeRequested`
  with the lock; a live lock held by another process emits `resumeRequested` (the start path refuses it);
  `sessionDetails` pushes loading then the details, and an unreadable file pushes the error; `closeDetails`;
  a refresh re-reads the details of an Active session; both exports write the file a patched dialog names
  and toast, and a cancelled dialog writes nothing; `set_context` re-pushes.
- **The page in a real Chromium** (`tests/test_app_sessions_page.py`), one test per frame at least: 7h; 7e's
  status line, skeleton rows and dashed counts; 7a's tabs, counts, rows and foot; a click selecting a row,
  opening the pane and folding the two columns; the pane's action reaching `sessionAction`; a double-click
  doing the same; a disabled action not reaching it; *View details* reaching `sessionDetails`; a tab, the
  search and a date reaching `setSessionsFilter`; a pushed query not overwriting the focused input; 7d and
  *Clear filters*; 7f and *Retry*; 7g; the switch reaching `setAutoRefresh`; the Export menu's two items
  reaching `exportSessions`; 7c's dialog and both answers; Esc; 8a's facts, cards and three groups; 8b's
  strip; 8c's sentence; 8d's item, extra and unknown rows after a click; *Expand all* and *Collapse all*; the
  filter reaching `setDetailsFilter`; 8e; 8f's banner, *Retry* and the disabled Export; the loading line;
  *Sessions* reaching `closeDetails`; markup in a list name shown as text; `covered` leaving no text.
- **`AppPages`** (`tests/test_app_pages.py`): three indices on one view; `PAGE_BROWSER` sets `sessions`, or
  `details` when details are open.
- **`MainWindow`** (`tests/test_sessions_mainwindow_seam.py`, and updates to `tests/test_shell.py`,
  `tests/test_session_browser_client.py`, `tests/test_app_mainwindow_seam.py`, `tests/test_app_freshness.py`):
  the two freshness tests of section 10; the client picker loads the client in `sessions`; the three signals
  reach their handlers; a resume with `take_over` force-releases that lock and opens; a stale lock with no
  `take_over` is 3c with the sentence of section 6 and no message box; a live lock is 3c; no message box
  after a start or a resume; `set_context` follows the open session and the connection; showing Sessions
  refreshes.
- **Deleted with what they tested:** `tests/test_session_detail_page.py`, `tests/test_sessions_list_columns.py`,
  `tests/test_sessions_list_status.py`, `tests/test_sessions_list_empty.py`. Every assertion in them about
  behaviour has a port above; the ones about Qt widgets (three tabs exist, a `QStackedWidget` swaps) do not.
- **Guards:** `tests/test_style_literals_guard.py` already scans `gui/web`.

**Renders.** `scripts/render_sessions.py` builds a `MainWindow` offscreen against a throwaway server (both
`QSettings` formats redirected, as `scripts/render_app_pages.py` does), sets payloads built by the pure
functions from 40 synthetic sessions at a fixed "now", and writes
`docs/design/ui-refresh/renders/phase4/<frame>-<theme>.png`: 7a to 7h and 8a to 8f at 1366×768 in Light and
Dark. The implementer looks at every PNG beside its mockup frame before the PR, and the PR embeds them.

## 15. Deleted

- `gui/session_browser/` (seven files).
- `packing_tool/session_history_manager.py`, and its construction in `MainWindow`.
- From `gui/main_window.py`: `_acquire_lock_with_stale_prompt`'s message box, the "Session Loaded",
  "Session Resumed" and "Session Active" boxes, and the imports left unused.
- From `gui/app_pages.py`: the `QStackedWidget`, `browser`, `web_is_current`.

## 16. Out of scope

- SKU mapping and Worker selection (phase 5).
- Taking over a live lock; recording which SKU or barcode an extra or unknown scan was; reading the packing
  list in Session details.
- Moving the connection banner into the document.
- The lock-lost message box outside Packer Mode.
- Any edit under `shared/`.

## 17. Docs touched

- `CONTEXT.md`: **Session Browser** says it is two pages of the app document; **Status chip** loses the
  tinted-ground channel; add **Session pane** and **Take over**; **App document** and **App bridge** name
  the four pages; **Session lock** says stale means 2 minutes without a heartbeat.
- `docs/adr/0003-the-shells-pages-are-one-web-document.md`: one line under Consequences, that since phase 4
  the view is hidden only under Packer Mode.
- `~/Obsidian/Claude/packing-tool.md`: the phase 4 entry.
