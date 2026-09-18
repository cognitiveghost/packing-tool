# Packing Tool — domain glossary

**Packer Mode** — the full-screen packing flow: scan an order barcode, then scan each item until the order is complete.

**Order document** — the web-rendered part of Packer Mode: metadata banner, scan feedback, SKU list, extras, history, summary and session progress.

**Qt chrome** — the Qt part of Packer Mode around the order document: scanner capture, Skip order, Exit packing, dev scan simulator.

**Packer bridge** — the one `QWebChannel` object the order document talks to. State Python owns crosses as a notify property; what the page reports crosses as a slot.

**Feedback band** — the order document's outcome row: what the last scan did, in its status colour, with the raw scanned text beside it.

**Scan flash** — the brief colour pulse on the order document's column edge that makes a scan's outcome visible from across the floor.

**Item state** — an order item's packing state: *pending* (nothing packed), *partial* (some of the required quantity packed), *complete* (all of it).

**Unmatched scan** — a scan that matches no item in the order and no known barcode; it is not an item, so it has no item state.

**Scanner capture** — the Qt input that receives barcode-scanner keystrokes; it must hold keyboard focus whenever Packer Mode is open.

**Extras** — items scanned into an order that the order does not contain; the packer keeps or removes each one.

**Force confirm** — marking an item packed without a matching scan.

**Packing table view** — the Packing tab's order list (orders with their SKU rows) shown before Packer Mode starts.

**Command bar** — the 60px row above Packing Tool's pages: client picker, session id, the page's actions, and the ⋯ overflow menu.

**Toast** — a transient, non-blocking message at the window's bottom right for an outcome that needs no decision; failures use a dialog instead.

**Floor density** — the density profile for warehouse use: 44px controls, 12pt body, 60px command bar.

**Artboard** — a static HTML drawing of a screen under `docs/design/`; once the owner approves it, it is the brief the implementation follows.
