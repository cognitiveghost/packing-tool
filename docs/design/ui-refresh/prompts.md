# Claude Design prompt pack — Packer Assistant UI refresh

**The mockups made from these prompts were approved by the owner on 2026-10-08.** They are in
[`mockups/`](mockups/), under the names Claude Design gave them, not the names the table below proposes.

Prompts for Claude Design, one per screen. Their output is a set of mockups the owner approves. After approval,
each mockup is the brief for its own implementation task (CLAUDE.md: "the mockup is the brief"). Same flow as
Fulfilment Tool's refresh (`../shopify-fulfillment-tool/docs/design/ui-refresh/`).

The look is already decided: it is Fulfilment Tool's, approved 2026-09-30 and now built. These prompts ask for
Packer Assistant's screens **in that look**, not for a new one.

## How to use

Four runs in one Claude Design project named **Packer Assistant — UI refresh**. A run is one message: paste
every block under its heading, in order, and attach the files it lists. Each run returns one HTML page per
screen. Ask for changes in the same thread. When a screen is right, export it and save it as
`docs/design/ui-refresh/mockups/<screen>.html`.

| Run | Screens | Mockup files |
|---|---|---|
| 1 | Style brief, Shell, Packing, Statistics | `component-sheet.html`, `app-shell.html`, `packing.html`, `statistics.html` |
| 2 | Packer Mode | `packer-mode.html` |
| 3 | Sessions, Session details | `sessions.html`, `session-details.html` |
| 4 | SKU mapping, Worker selection | `sku-mapping.html`, `worker-selection.html` |

Run 1 goes first: it sets the style and the shell the others sit in. Runs 2 to 4 can go in any order, and each
starts with one line: *"Same project, same style brief and shell as before."* To redo one screen, paste the style
brief and that screen's block alone.

**Style reference**, attached to run 1, from `shopify-fulfillment-tool/docs/design/ui-refresh/mockups/`:
`component-sheet.html`, `app-shell.html`, `renders/results.png`, `renders/browse.png`.

**Current screens** are in [`current/`](current/): offscreen renders at 1366×768, floor density, against a
throwaway server with synthetic data (one client, five packing lists, 24 orders packed in the open one).
Offscreen Qt uses a fallback font, not Segoe UI, so glyph widths differ a little from Windows.

---

## Run 1 — style brief, Shell, Packing, Statistics

Attach: the four style-reference files, and `current/packing.png`, `current/packing-expanded.png`,
`current/packing-no-session.png`, `current/packing-dark.png`, `current/stats.png`.

### Style brief

> You are designing the next version of **Packer Assistant**, a Windows desktop app used on the warehouse floor.
> A packer opens a packing list, scans an order's barcode, then scans every item that goes into the parcel; the
> app says at once whether each scan was right. It is the sibling of **Fulfilment Tool**, whose mockups are
> attached. A supervisor plans in Fulfilment Tool; a packer executes in this one.
>
> **The visual language is fixed: it is the attached Fulfilment Tool design.** Use its tokens, its type scale,
> its components (buttons, badges, card, index table, segmented control, input, state panel, toast, banner, page
> header) and its light and dark themes exactly as `component-sheet.html` defines them. Do not propose new token
> values. If a screen needs a component or a token the sheet does not have, name it, draw it once on a small
> addendum sheet, and say why.
>
> **What differs from Fulfilment Tool: this app is read standing up, at arm's length, with a scanner in one
> hand.** It runs in a **floor density**: 44px controls, 12pt body text, a 60px command bar. Keep the Polaris
> structure, but size for that density, and make state readable from two metres: status is carried by a large
> coloured surface and a word, never by colour alone and never by a small icon.
>
> **Hard constraints (the build depends on them):**
> - Two layers. The **shell** (left navigation, top command bar) is drawn by Qt widgets: flat only, borders and
>   background planes, **no shadows**. The **screen content** inside the shell is HTML/CSS in an embedded
>   Chromium: the two shadow tokens from the sheet are allowed there.
> - **The scanner types into one Qt field in the command bar, and that field must keep keyboard focus for the
>   whole of Packer Mode.** So the Packer Mode content (run 2) has **no text inputs, no dropdowns and nothing that
>   takes typing**: only buttons. Other screens may have a search field.
> - No gradients, no transitions, no transforms, no opacity fades. State changes are instant. One exception
>   already exists and stays: the **scan flash**, a brief colour pulse on Packer Mode's edge after each scan.
> - Fonts: **Segoe UI** for text and **Consolas** for SKUs, barcodes, order numbers, session ids and times. No
>   web fonts: the app runs offline.
> - Type sizes are points from the existing scale, never px: `caption` 9pt, `body` 10pt, `label` 12pt bold,
>   `heading` 14pt bold, `display` 17pt bold, `display_xl` 28pt bold. Floor density moves body text up to the
>   `label` size without the bold. If a design needs another size, name it as a new role and say why.
> - Deliver **light and dark** for every screen.
> - Disabled controls must look disabled at a glance.
> - Every screen shows its states: default with realistic data, empty, working (a named step, not a spinner or
>   shimmer), and failed.
>
> **Vocabulary (use these words exactly):** *client*, *session*, *packing list*, *order*, *item*, *SKU*,
> *barcode*, *worker* (the packer's profile), *Packer Mode*, *extras* (items scanned into an order that it does
> not contain), *unmatched scan*, *manual confirm*, *force confirm*, *skip order*. Item states: *Pending*,
> *Partial*, *Complete*. Session statuses: *Not started*, *Active*, *Paused*, *Stale*, *Completed*, *Incomplete*,
> *Abandoned*. Messages follow four routes: a **toast** for something that worked, an **inline message** next to
> what has a problem, a **confirm** only before something that cannot be undone, and an **error banner** for a
> failure. Empty states name the cause and offer the one action that fixes it. No apologies, no exclamation
> marks.
>
> Output: one HTML page per screen, each with a light/dark toggle and a state switcher, sized to **1366×768**
> first and checked at 1920×1080. In this first reply deliver four pages: a component sheet showing the
> Fulfilment Tool components at floor density (button, badge, card, table row, input, state panel, toast,
> banner), then the three screens described below: the shell, Packing and Statistics.

### Shell — navigation, command bar, status line

> Design the **shell** every screen sits in. Qt draws it, so it is flat (no shadows). Start from Fulfilment
> Tool's shell in `app-shell.html` and change only what this app needs.
>
> **Left navigation.** Three destinations, each with a Lucide icon: **Packing** (clipboard-list), **Statistics**
> (table), **Sessions** (folder-open). Today it is a 56px icon rail. Use Fulfilment Tool's sidebar: ~200px with
> icon + label, the app mark ("Packer Assistant") at the top, collapsing to the 56px rail. Pinned at the bottom:
> the **worker** who is signed in (name, with *Switch worker…*), **SKU mapping**, the Light/Dark choice and the
> server connection state (connected / reconnecting / unreachable, with Retry).
>
> **Top command bar**, one 60px row:
> - Left: the **client selector** (a combo; with no client it says "Choose a client"), then the open session's
>   id in Consolas, or nothing when no session is open.
> - On Packing only: a **Filter orders** field.
> - Right: the screen's actions. On Packing with no session: **Open session** (primary). On Packing with a
>   session: **Start packing** (primary), *End session* (Ctrl+E). Then a `…` overflow. Today the overflow holds
>   SKU mapping…, Select worker…, Server connection…, the theme toggle and Exit; say what is left in it once the
>   sidebar footer takes worker, SKU mapping and theme.
>
> **Status line.** Today a 40px bar at the bottom shows the session id and the worker on the left and one
> sentence on the right ("38 of 120 orders complete" on Packing, "12 of 40 sessions" on Sessions). Fulfilment
> Tool deleted its status bar. Do the same: give each fact a home in the sidebar footer, the command bar or the
> page, and say where each went.
>
> Show: no client chosen; client chosen with no session; session open; server unreachable; sidebar collapsed.

### Packing — the open session's orders

> Design **Packing**, the page a packer sees after opening a session and before starting to scan. It answers
> "what is in this packing list and how far along is it".
>
> Content today: a tree with one row per **order** and, under it, one row per **item**. Columns: *Order / Item*
> (order number in Consolas; SKU in Consolas on item rows), *Product*, *Quantity* (packed of required, e.g.
> "2 / 3"), *Status*, *Courier*. An order's status is one of *Not started*, *In progress*, *Packed*; an item's is
> *Pending*, *Partial*, *Complete*. The command bar's *Filter orders* narrows the tree by order number or SKU.
>
> Use the Polaris index-table pattern from Fulfilment Tool's Results: order rows that expand to their items,
> status badges, a page header with the packing list's name, and above the table a short strip of totals
> (orders complete of total, items packed of total, orders skipped) with one progress bar. The page's primary
> action is **Start packing**, mirrored in the command bar. No checkboxes: nothing is done to orders in bulk
> here.
>
> States: 120 orders, 38 complete, 2 in progress; filtered to one SKU; a filter that matches nothing ("No orders
> match — nothing in this packing list contains "CRM-50". Clear filter"); every order complete ("Packing list
> complete — 120 of 120 orders packed. End session"); no session ("No session open — Open a session to see its
> orders here." + *Open session*); no client; the packing list failed to load (error banner naming the file).

### Statistics

> Design **Statistics**, the open session's numbers, for a packer or supervisor glancing at progress mid-shift.
>
> Content today: **Session totals** as stat cards (Orders, Completed, Items, Unique SKUs, Progress %); **By
> courier** (per courier: orders and completed, e.g. "DHL 40 · 12 done"); **SKU summary**, a table with
> *SKU* (Consolas), *Product*, *Total qty*, *Status*; add a *Packed* count (*Pending*, *Partial*, *Packed*).
>
> Lay it out as Fulfilment Tool's Results is: a KPI strip, then cards. By courier wants bars, not a list. The
> SKU summary is the long part: keep it dense, sortable by what is left to pack.
>
> States: mid-session (120 orders, 38 complete, three couriers, 88 SKUs); session complete; no session ("No
> packing data yet — Start a session from the Packing tab to see numbers here." + *Go to Packing*).

---

## Run 2 — Packer Mode

Attach: `current/packer-mode.png`, `current/packer-mode-dark.png`, `current/packer-mode-waiting.png`,
`current/packer-mode-unmatched.png`, `current/packer-mode-complete.png`.

### Packer Mode

> Restyle **Packer Mode**, the full-screen scanning flow. It replaces the shell: no sidebar. It is already
> HTML and it works, so **keep its information and behaviour exactly** and move it onto the Fulfilment Tool look
> at floor density. This is the screen that is read from two metres.
>
> **Command bar** (Qt, flat, 60px): the current order number in Consolas (large), the **scanner field** (280px,
> shows what the scanner typed, placeholder "Order number or SKU", with the state "Ready to scan" or "Scanner
> disabled" beside it), then *Skip order* and *Exit packing* on the right.
>
> **Content** (HTML, no inputs of any kind):
> - **Order banner**: the order's metadata on one row (customer, courier, tags, internal notes, and a *Repeat*
>   chip when this customer's order was already packed).
> - **Feedback band**: the outcome of the last scan as one large sentence in its status colour ("Scan an order
>   barcode", "CRM-50ML — 2 of 3", "Order complete", "Not in this order"), with the raw scanned text in Consolas
>   beside it. With the **scan flash** on the content's edge, this is what the packer watches.
> - **SKU list**: one row per item: SKU (Consolas), product name, packed of required in large numerals, a
>   status chip (*Pending*, *Partial*, *Complete*), and row actions as buttons: *Confirm* (a manual confirm of one unit),
>   *Force confirm* (all remaining units; asks first, cannot be undone), *Undo* (take one back), *Map SKU*.
>   Complete rows go quiet; the row just scanned stands out.
> - **Extras**: "Extra items scanned", one row per extra with *Keep* and *Remove*.
> - **Unmatched scan**: a row with a *No match* chip, the barcode, and *Map barcode…*.
> - **Side column**: *Session progress* (a bar, "38 / 120 orders · 412 / 1,290 items"), *History* (the last
>   orders packed, newest first, with their time), *Items by SKU* (this order rolled up to one row per SKU) and
>   *Summary* ("Unique SKUs packed 31 / 88").
> - When every order is done, the content is a state panel: "Session complete", with *End session* (primary)
>   and *Exit packing*.
>
> Fix from today: the side column's four blocks have the same weight as the SKU list; the list must dominate.
> The feedback band and the flash should be legible in a bright warehouse and in dark theme.
>
> States: waiting for an order barcode; an order open with five items (one complete, one partial, three
> pending); a correct scan (success); a scan of an item not in the order (danger, with an extra row); an
> unmatched scan; the force-confirm confirm open; order complete; session complete; "Progress not saved — check
> the network" (error banner, scanning continues); "This list is open on another PC — <name> has taken over
> <packing list>. This PC has stopped packing it." (blocking, with *Exit packing*).

---

## Run 3 — Sessions and Session details

Attach: `current/browse.png`, `current/browse-row-selected.png`, `current/browse-detail-overview.png`,
`current/browse-detail-orders.png`, `current/browse-detail-metrics.png`, and Fulfilment Tool's `browse.html`.

### Sessions — the list

> Design **Sessions**, the list of this client's packing sessions. A packer comes here to start a packing list
> or resume one; a supervisor comes here to see what happened. Start from Fulfilment Tool's Browse in
> `browse.html`: same index table, same status tabs, same badges.
>
> Each row: **Status** (badge), **Session** (id like `2026-10-07_1`, Consolas), **Age** ("3 h"), **Packing**
> (the packing list's name), **Orders** (a small progress bar with "38 / 120"), **Items**, **Last touched**
> (worker, PC and time folded into one cell: "Maria · PACK-02 · 14:06"). Status is one of seven: *Not started*,
> *Active*, *Paused*, *Stale* (its PC stopped responding), *Completed*, *Incomplete*, *Abandoned*. A person
> declares *Paused* and *Incomplete*; the system infers the rest, and the badge shows which (solid dot = a
> person, hollow = the system), as on Fulfilment Tool.
>
> Toolbar, one row: status **tabs** with live counts in place of today's status combo, search sessions, a date
> range (From, To), *Refresh* with "Last refreshed 14:06:31" and the *Auto-refresh (2 min)* switch, and *Export* (CSV or Excel of the rows shown).
>
> Selecting a row opens a **detail pane** on the right (as Results has) in place of today's one-line preview:
> packing list, worker, PC, duration, orders done / total (skipped), items, scan corrections, unknown scans, and
> the row's **one primary action**: *Start packing* for Not started; *Resume session* for Active, Paused, Stale
> and Incomplete; *View details* for Completed and Abandoned. Resuming a session that another PC holds says so
> before it takes over. Double-click does the primary action.
>
> States: 40 sessions across statuses; one row selected with the pane; no client ("Choose a client — Pick a
> client in the bar above to see its sessions."); client with no sessions ("No sessions yet — Sessions appear
> here once someone starts packing for this client."); a filter that matches nothing; loading ("Reading sessions
> from the server…"); the refresh failed (error banner with the cause and Retry); resuming a session held by
> another PC (confirm).

### Session details

> Design **Session details**, the page behind a session in the list. Today it is three tabs (Overview, Orders,
> Metrics) of mostly label/value pairs. Argue for one scrolling page or for tabs, then draw it.
>
> Page header: a back link to Sessions, the session id (Consolas), its status badge, and *Export Excel* on the
> right.
>
> Content today (keep all of it):
> - **Overview**: Session ID, Client, Packing list, Worker; Started, Completed, Duration; Orders packed, Items
>   packed.
> - **Metrics**: *Order metrics* (average time per order, fastest order, slowest order), *Item metrics* (average
>   time per item, average time to first scan), *Performance rates* (orders per hour, items per hour), *Scan
>   quality* (total scan corrections, average corrections per order, total unknown scans, total extra scans),
>   and skipped orders. A note: "Only data from completed orders is shown."
> - **Orders**: a tree of orders and their items with *Duration*, *Count*, *Started / Scanned*, *Completed* and *Flags*
>   (skipped, manual or forced confirms, extras, corrections); a filter by order number; "Showing 38 of 120
>   orders"; Expand all / Collapse all.
>
> Use stat cards (a big number over a small label) for the numbers a supervisor compares between sessions, and
> the index table for orders. Flags become badges, not a text string.
>
> States: a completed session; an active session (timings still running, "so far" on the numbers); a session
> with no timing data ("Timing metrics are not available for this session."); an order row expanded; a filter
> that matches nothing; the session's files could not be read (error banner).

---

## Run 4 — SKU mapping and Worker selection

Attach: `current/sku-mapping.png`, `current/worker-select.png`, and Fulfilment Tool's `client-settings.html`.

### SKU mapping

> Design **SKU mapping**, where a client's product barcodes are mapped to its internal SKUs. It is per client,
> shared by every PC, and opened three ways: from the sidebar, and from Packer Mode's *Map SKU…* and *Map
> barcode…* (which arrive with the barcode already filled in).
>
> Today it is a modal with a two-column table (*Product barcode*, *Internal SKU*), four buttons (Add mapping,
> Edit selected, Delete selected, Reload from server) and Save / Cancel, and adding a mapping is two input
> boxes one after another. Make it a window in the style of Fulfilment Tool's Client settings pages
> (`client-settings.html`): a header with a one-line description ("Map product barcodes to internal SKUs.
> Changes are saved to the file server and reach every PC."), search, an index table with edit and delete on
> the row, and adding as one inline row with both fields. Save is live only with unsaved changes.
>
> States: 60 mappings; none ("No mappings yet — Scan or type a product barcode to map it to a SKU. Add
> mapping"); adding a row; a barcode that already exists (inline message naming the SKU it maps to, with
> *Replace*); opened from Packer Mode with the barcode filled in and the SKU field focused; delete (confirm);
> reload with unsaved changes (confirm); saving failed (error banner, nothing lost).

### Worker selection

> Design **Worker selection**, the first thing the app shows: "Select your profile — Choose your worker profile
> to continue". It is also reached later from *Switch worker…*.
>
> Today it is a modal with one card per worker (name, "Sessions 14 | Orders 1,204", "Last active Yesterday"),
> a *Create worker* button that opens a name prompt, and Cancel (which closes the app at startup). Draw it as a
> full window in the Fulfilment Tool look: large cards a packer can hit without aiming, most recently active
> first, the app mark above, and *New worker* as a card that turns into a name field in place.
>
> States: six workers; one worker; none ("No workers yet — Create a worker profile to start packing."); creating
> a worker; an invalid or duplicate name (inline message); the worker list could not be loaded (error banner
> with the server path and Retry).
