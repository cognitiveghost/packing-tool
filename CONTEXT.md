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

**Force confirm** — marking an item packed without a matching scan.

**Packing table view** — the Packing tab's order list (orders with their SKU rows) shown before Packer Mode starts.

**Command bar** — the 60px row above a screen, carrying what that screen is and what can be done to it. Above the pages it holds the client picker, session id, the page's actions and the ⋯ overflow menu; above Packer Mode it holds the order number, scanner capture, Skip order and Exit packing.

**State panel** — the centred title, sentence and action a screen shows in place of its content when there is nothing to show or the work is done.

**Toast** — a transient, non-blocking message at the window's bottom right for an outcome that needs no decision; failures use a dialog instead.

**Floor density** — the density profile for warehouse use: 44px controls, 12pt body, 60px command bar.

**Artboard** — a static HTML drawing of a screen under `docs/design/`; once the owner approves it, it is the brief the implementation follows.

**Session Browser** — the screen listing a client's packing sessions, and the detail page behind a selected one. Its client picker is the command bar's; it has no picker of its own.

**Session status** — one of seven states a session is in: *not started*, *active*, *paused*, *stale*, *completed*, *incomplete*, *abandoned*. A packer declares *paused* and *incomplete*; the system infers the rest.

**Status chip** — the pill marking a status, carrying F5's three channels: colour is the role, a tinted ground means the thing is still live, and a solid dot means a person decided it where a hollow dot means the system did.

**Stat card** — a big number over a small label in a bordered box; the unit the Statistics screen is built from.

**SKU roll-up** — one order's lines consolidated to one row per distinct SKU, in the order document's side column. Not the same as the Statistics screen's **SKU summary**, which spans the whole session.
