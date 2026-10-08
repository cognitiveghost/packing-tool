# ADR 0002 — Every screen moves to the web tier; the shell stays Qt

- **Status:** accepted, 2026-10-08.
- **Deciders:** repo owner
- **Supersedes:** the last consequence of ADR 0001 ("No third web screen without a new ADR") and its
  decision line "Session Browser, Statistics and every other Packing Tool screen stay Qt". The rest of
  ADR 0001 stands, the scanner invariant first of all.

## Decision

Every screen of Packer Assistant renders on the web tier: Packing, Statistics, Sessions, Session details,
SKU mapping and Worker selection, next to Packer Mode, which already does. The **shell** (the sidebar and
the command bar) stays Qt and flat.

The approved Claude Design mockups in `docs/design/ui-refresh/mockups/` are the brief. `Packer Screens.html`
indexes every frame (1a to 8f), and each phase cites the frame ids it builds.

These hold for all five phases of the UI refresh:

- **Scanner invariant, unchanged from ADR 0001.** The scanner types into one Qt field. In Packer Mode the
  web view never takes keyboard focus, and the regression test that scans after a click inside the view
  stays.
- **Floor density.** 44px controls and 12pt body text. The window is designed for 1366×768 and checked at
  1920×1080. Both themes are built and rendered.
- **The status bar is deleted.** Connection state lives in the sidebar's connection card. A one-off
  confirmation is a toast. An outage is a page banner, and it disables the session actions.
- **Contrast floors outrank the mockup palette.** Where a mockup colour falls below the WCAG floors in
  `shared/theme.py`, the floor wins (shopify-fulfillment-tool ADR 0018).
- **`shared/` is never edited here.** It is a pinned mirror of shopify-fulfillment-tool's. What it lacks
  lives app-side in `gui/theme.py`, `gui/components/` or `gui/web/`, and each PR lists it under
  "For shared/" so it can be moved there from Fulfilment's side.

## Context

ADR 0001 let Packer Mode onto the web tier and capped it there, because every screen across the Qt↔JS seam
costs maintenance twice. Since then Fulfilment Tool moved all of its screens to the web tier in ten phases
and the seam's cost fell: one bridge base, one kit stylesheet and one page script now do the shared work,
and since Fulfilment PR #372 they live in `shared/` (`shared/web_page.py`, `shared/web/`). The two apps are
used side by side on the same floor, and the Qt screens here now look like a different product.

The owner approved the mockups on 2026-10-08. Chromium already ships in this app's build (ADR 0001), so
moving more screens adds no build-size cost.

## Consequences

- The refresh runs in five phases, one PR each: (1) design inputs, this ADR, the `shared/` sync and the
  shell; (2) Packer Mode and the floor web kit; (3) Packing and Statistics; (4) Sessions and Session
  details; (5) SKU mapping, Worker selection and cleanup.
- Until a screen's phase lands it stays Qt inside the new shell. A Qt widget cannot be drawn over a web
  view, so a screen moves whole, never in part.
- ADR 0001's guardrails for web assets stay: colour only from `shared/theme.py` through `theme_css_vars()`,
  no hex, no gradients, transitions, transforms or px font sizes, one mono face. `box-shadow` is allowed
  only as one of the theme's two shadow tokens (shopify-fulfillment-tool ADR 0016).
- SKU mapping and Worker selection have text inputs. They are never shown while Packer Mode is open, so
  they do not touch the scanner invariant. A phase that changes that needs its own ADR.
- Departures from a mockup are listed in the phase's spec and PR, never made silently.

## Alternatives considered

**Restyle the Qt screens to the new palette and stop.** The sync alone does most of it. Rejected by the
owner: the layouts the mockups draw (index tables with expanding rows, split panes, KPI strips) are the
ones Qt widgets fought in Fulfilment Tool, and a third Qt rebuild would end the same way.

**Move the shell to the web tier too.** Rejected: the scanner field has to be Qt, the shell would have to
be drawn over or around every page's web view, and Fulfilment's Qt shell already matches its mockup.
