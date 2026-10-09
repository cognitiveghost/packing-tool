# ADR 0003 — The shell's pages are one web document

- **Status:** accepted, 2026-10-08.
- **Deciders:** repo owner
- **Builds on:** ADR 0002 (every screen moves to the web tier; the shell stays Qt).

## Decision

Packing, Statistics, Sessions and Session details are drawn by one page, `gui/web/app.html`, in one
`QWebEngineView`, talking to one bridge, `gui/app_bridge.AppBridge`. The bridge's `page` property says
which of them is showing. A screen joins the document in its own phase: Packing and Statistics in phase 3,
Sessions and Session details in phase 4. Until then a screen stays a Qt page beside the view.

Packer Mode keeps its own view and its own bridge (ADR 0001): it replaces the whole shell, has Qt chrome of
its own, and its view must never take the keyboard.

Before Packer Mode covers the shell, the document is told to draw nothing and the switch waits for that
paint, 150 ms at most. Leaving Packer Mode already waits the same way for its cleared page (phase 2).

## Context

A hidden `QWebEngineView` stops painting and shows its last frame when it comes back, until a new one is
ready. Fulfilment Tool, with a view per screen, fixed that by stacking every page as visible and measured
about 31 MB per view. That fix is not available here: a Qt page cannot be drawn over a live web view, and
it hands keyboard focus to a web view on a switch, which Packer Mode forbids.

The mockup draws the pages as one app with one frame around them.

## Consequences

- Switching between pages of the document is a redraw inside a visible view. It cannot show an old frame.
- One view is hidden only under Packer Mode. (Until phase 4 it was also hidden under the Qt Sessions page;
  Sessions and Session details are pages of the document since.)
- One document means one script and one sheet that grow with each phase. `app.js` keeps a section per
  page, and the bridge keeps one named property per page's state, so a page's payload and its tests stay
  separable.
- State is pushed to the document only while the shell is showing. A scan in Packer Mode pushes nothing,
  and leaving pushes once.
- SKU mapping and Worker selection are dialogs, not pages of the shell. Phase 5 decides where they live.

## Alternatives considered

**A view per screen.** What `shared/web_page.py` was first built for. Rejected: more memory, and every
hidden view is another frame that can go stale, with no stack-all fix to lean on here.

**Packer Mode in the same document.** Rejected: its scanner invariant is a property of its view, and one
view cannot both refuse the keyboard and take it for the pages' buttons.
