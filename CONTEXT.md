# Packing Tool — domain glossary

**Packer Mode** — the full-screen packing flow: scan an order barcode, then scan each item until the order is complete.

**Order document** — the web-rendered part of Packer Mode: metadata banner, scan feedback, SKU list, extras, history, summary and session progress.

**Qt chrome** — the Qt part of Packer Mode around the order document: scanner capture, Skip order, Exit packing, dev scan simulator.

**Packer bridge** — the one `QWebChannel` object the order document talks to. State Python owns crosses as a notify property; what the page reports crosses as a slot.

**Feedback band** — the order document's outcome row: what the last scan did, in its status colour, with the raw scanned text beside it.

**Scan flash** — the brief colour pulse on the order document's column edge that makes a scan's outcome visible from across the floor.

**Item state** — an order item's packing state: *pending* (nothing packed), *partial* (some of the required quantity packed), *complete* (all of it).

**Unmatched scan** — a scan that matches no item in the order and no known barcode; it is not an item, so it has no item state.

**Scanner capture** — the Qt input that receives barcode-scanner keystrokes; it must hold keyboard focus whenever Packer Mode is open. It is the field in Packer Mode's command bar.

**Extras** — items scanned into an order that the order does not contain; the packer keeps or removes each one.

**Manual confirm** — marking one unit of an item packed from its row, without a scan (`confirmation_method` *manual*).

**Force confirm** — marking the rest of an item's quantity packed at once, without a scan (*force_confirmed*; shown as *forced*). The summary's `total_manual_confirms` counts both.

**Packing table view** — the Packing tab's order list (orders with their SKU rows) shown before Packer Mode starts.

**Command bar** — the 60px row above a screen, carrying what that screen is and what can be done to it. Above the pages it holds the sidebar toggle, the client selector, the open session's id, the page's actions and the ⋯ overflow menu (Server connection…, Exit); above Packer Mode it holds the order number, scanner capture, Skip order and Exit packing.

**Sidebar** — the Qt column left of the pages: the app mark, the three destinations (Packing, Statistics, Sessions) and a footer with SKU mapping, the worker, Light/Dark and the connection card. 200px, collapsing to a 56px rail. With no client chosen its destinations are disabled.

**Connection card** — the sidebar footer's statement of whether the file server answers: *Server connected*, *Reconnecting…* (while a check runs) or *Server unreachable* (with Retry). The server is checked on Retry and after a failed session action, never on a timer.

**Connection banner** — the banner above the page while the server is unreachable: which path, since when, and Retry. While it shows, sessions cannot be opened or ended.

**State panel** — the centred title, sentence and action a screen shows in place of its content when there is nothing to show or the work is done.

**Toast** — a transient, non-blocking message at the window's bottom right for an outcome that needs no decision; failures use a dialog instead.

**Floor density** — the density profile for warehouse use: 44px controls, 12pt body, 60px command bar.

**Artboard** — a static HTML drawing of a screen under `docs/design/`; once the owner approves it, it is the brief the implementation follows.

**Session Browser** — the screen listing a client's packing sessions, and the detail page behind a selected one. Its client picker is the command bar's; it has no picker of its own. Its destination in the sidebar is labelled "Sessions".

**Session status** — one of seven states a session is in: *not started*, *active*, *paused*, *stale*, *completed*, *incomplete*, *abandoned*. A packer declares *paused* and *incomplete*; the system infers the rest.

**Status chip** — the pill marking a status, carrying F5's three channels: colour is the role, a tinted ground means the thing is still live, and a solid dot means a person decided it where a hollow dot means the system did.

**Stat card** — a big number over a small label in a bordered box; the unit the Statistics screen is built from.

**SKU roll-up** — one order's lines consolidated to one row per distinct SKU, in the order document's side column. Not the same as the Statistics screen's **SKU summary**, which spans the whole session.

**Packing state** — one packing list's saved progress (`packing_state.json` in its work directory): completed, skipped and in-progress orders, with timing. The source of truth for a session's progress.

**Session lock** — the file in a packing list's work directory that says which PC is packing it. One PC at a time; it is renewed by a heartbeat, and a lock whose heartbeat stopped is *stale*.

**Session registry** — the per-client index the Session Browser reads: one entry per packing session with its status and counts. A summary of packing state for listing, never the source of truth.

**Packed-order signal** — the order numbers Packing Tool writes into a Shopify session's `session_info.json`, which Shopify Tool reads so an order already packed is flagged as a repeat.
