# Packing Tool — domain glossary

**Packer Mode** — the full-screen packing flow: scan an order barcode, then scan each item until the order is complete.

**Order document** — the web-rendered part of Packer Mode: the order card, the feedback band, the SKU list with its extras and unmatched scans, the side column (session progress, history, items by SKU, summary), the unsaved banner, and the two panels that take the page over (the Force confirm question, and "This list is open on another PC").

**Qt chrome** — the Qt part of Packer Mode around the order document: scanner capture, Skip order, Exit packing, dev scan simulator.

**Packer bridge** — the one `QWebChannel` object the order document talks to. State Python owns crosses as a notify property; what the page reports crosses as a slot.

**App document** — the web page that draws the shell's pages: Packing, Statistics, Sessions and Session details. One page in one web view (ADR 0003); Packer Mode's order document is a different page in its own view.

**App bridge** — the one `QWebChannel` object the app document talks to. It says which of the four pages shows, what the session is (none, opening, failed, open) and each page's data; the page reports clicks through slots.

**Feedback band** — the order document's outcome row: what the last scan did, as one large sentence on a solid fill in its status colour, with the raw scanned text beside it. The unsaved warning is a banner above it, not part of it.

**Scan flash** — the brief colour pulse on a 10px frame around the order document's main column that makes a scan's outcome visible from across the floor.

**Item state** — an order item's packing state: *pending* (nothing packed), *partial* (some of the required quantity packed), *complete* (all of it).

**Unmatched scan** — a scan that matches no item in the order and no known barcode; it is not an item, so it has no item state.

**Scanner capture** — the Qt input that receives barcode-scanner keystrokes; it must hold keyboard focus whenever Packer Mode is open. It is the field in Packer Mode's command bar.

**Extras** — items scanned into an order that the order does not contain; the packer keeps or removes each one.

**Manual confirm** — marking one unit of an item packed from its row, without a scan (`confirmation_method` *manual*).

**Force confirm** — marking the rest of an item's quantity packed at once, without a scan (*force_confirmed*; shown as *forced*). Offered only on lines over 5 units. The order document asks first, with the scanner off until the packer answers; it cannot be undone. The summary's `total_manual_confirms` counts both.

**Order index** — the Packing page's table: orders grouped In progress, Not started, Packed, each row opening to its items. *Filter orders* narrows it by order number, SKU or product name and marks the item that matched.

**Command bar** — the 60px row above a screen, carrying what that screen is and what can be done to it. Above the pages it holds the sidebar toggle, the client selector, the open session's id, the page's actions and the ⋯ overflow menu (Server connection…, Exit); above Packer Mode it holds the order number, scanner capture, Skip order and Exit packing.

**Sidebar** — the Qt column left of the pages: the app mark, the three destinations (Packing, Statistics, Sessions) and a footer with SKU mapping, the worker, Light/Dark and the connection card. 200px, collapsing to a 56px rail. With no client chosen its destinations are disabled.

**Connection card** — the sidebar footer's statement of whether the file server answers: *Server connected*, *Reconnecting…* (while a check runs) or *Server unreachable* (with Retry). The server is checked on Retry and after a failed session action, never on a timer.

**Connection banner** — the banner above the page while the server is unreachable: which path, since when, and Retry. While it shows, sessions cannot be opened or ended.

**State panel** — the centred title, sentence and action a screen shows in place of its content when there is nothing to show or the work is done. On a web page it is a centred card drawn by the page.

**Toast** — a transient, non-blocking message for an outcome that needs no decision; failures are shown in the page or in a dialog. While the app document is on screen it draws the toast itself, bottom centre; elsewhere it is the Qt toast at the window's bottom right.

**Floor density** — the density profile for warehouse use: 44px controls, 12pt body, 60px command bar.

**Floor web kit** — `gui/web/floor.css`: floor density for web pages, loaded between `shared/web/kit.css` and a page's own sheet. It holds sizes and shared parts (buttons, badges, the banner, the scrim and dialog), never a page's layout.

**Artboard** — a static HTML drawing of a screen under `docs/design/`; once the owner approves it, it is the brief the implementation follows.

**Session Browser** — the Sessions page and the Session details page behind a session: two pages of the app document. Its client picker is the command bar's; it has no picker of its own. Its destination in the sidebar is labelled "Sessions".

**Session status** — one of seven states a session is in: *not started*, *active*, *paused*, *stale*, *completed*, *incomplete*, *abandoned*. A packer declares *paused* and *incomplete*; the system infers the rest.

**Status chip** — the pill marking a session's status: its colour is the status's tone, and a solid dot means a person set the status where a hollow dot means the system inferred it.

**Session pane** — the 360px column beside the Sessions list while a row is selected: the session's facts and its one action (Start packing, Resume session, View details or Go to Packing). While it is open the list's Items and Last touched columns fold into it.

**Take over** — resuming a session whose lock is stale. The page asks first, saying which PC had it, since when and what comes along; only that lock is released, and only if it is still stale. A session that is live on another PC cannot be taken over.

**KPI strip** — one card split into cells, each a label over a large number: Packing's totals strip and Statistics' KPI strip.

**SKU roll-up** — one order's lines consolidated to one row per distinct SKU, in the order document's side column. Not the same as the Statistics screen's **SKU summary**, which spans the whole session.

**Packing state** — one packing list's saved progress (`packing_state.json` in its work directory): completed, skipped and in-progress orders, with timing. The source of truth for a session's progress.

**Session lock** — the file in a packing list's work directory that says which PC is packing it. One PC at a time; it is renewed by a heartbeat, and a lock with no heartbeat for 2 minutes is *stale*, and the Sessions list calls the session *stale* from the same moment.

**Session registry** — the per-client index the Session Browser reads: one entry per packing session with its status and counts. A summary of packing state for listing, never the source of truth.

**Packed-order signal** — the order numbers Packing Tool writes into a Shopify session's `session_info.json`, which Shopify Tool reads so an order already packed is flagged as a repeat.
