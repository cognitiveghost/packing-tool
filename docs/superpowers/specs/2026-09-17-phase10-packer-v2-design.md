# Phase 10 — Packer Tool v2

**Status:** approved by the repo owner, 2026-09-17.
**Roadmap:** `docs/superpowers/plans/2026-09-17-phase10-packer-v2-roadmap.md`
**Design references:** Claude Design artbook `75385f2c-4be2-446c-8e9d-bf90ee063ff7`
(Shopify Tool's Fulfilment System v2 — F0 tokens, F5 status, S shell, D destinations, W results).
The artbook has **no Packing Tool artboards**; Bundle 2 draws them.

## Goal

Bring Packing Tool up to the design system Shopify Tool finished in Phase 9, and
use the refresh to catch backend bugs along the way. Three screens matter:

1. **Packer Mode** — rebuilt around a web-rendered order document (Chromium via
   `QWebEngineView`), so the layout stops fighting `QTableWidget`.
2. **Session Browser** — redesigned in Qt, following Shopify Bundle 6.
3. **Statistics** — kept as a destination, redesigned in Qt.

Everything else gets the general repaint through the shared shell and components.

## Where Packing Tool stands

Already merged from Phase 9: 9.0 asset library (#171), Phase 9 Bundle 1 foundations —
tokens, borders, controls (#172), 9.3 status chip (#173), rail cleanup (#174).
Not ported: command bar / shell, the component library (`Card`, `StatePanel`,
`Toast`, `ConfirmDialog`, …, which live only in Shopify's `gui/components/`),
the session browser pattern, and the web tier.

## Decisions

### D1 — Packer Mode crosses to the web tier; this overrides Shopify ADR 0001's scope line

Shopify ADR 0001 says "Packing Tool stays entirely Qt" and caps the web tier at
one screen, because every screen across the seam is a permanent tax. The repo
owner accepts a second screen for Packer Mode, and the build-size cost up front
(Chromium already ships and works in Shopify Tool on the same machines).
Recorded in packing-tool **ADR 0001**; Bundle 3 adds a pointer note to
Shopify's ADR 0001 when it next touches that repo. The
guardrails from Shopify's ADR carry over unchanged: `shared/theme.py` is the only
source of colour, `theme_css_vars()` feeds the page, no hex in web assets
(`style_lint` covers `.css`/`.html`), no shadows/gradients/transitions/transforms/px
font sizes, one mono face (`font_family_mono`).

### D2 — The split: Qt keeps the scanner, Skip and Exit; the web page gets everything else

| Qt (`PackerModeWidget` chrome) | Web (the packer document) |
|---|---|
| Scanner capture (`scanner_input`) — may be resized and repositioned | Order SKU list with per-item states |
| Skip order, Exit — placed neatly, not where they are today | Scan feedback: notifications, raw scan, match / wrong SKU / order complete |
| Dev-mode scan simulator | History, extras, summary, session progress, metadata banner |

Scan *results* are shown on the web page, not in Qt labels — the owner's
explicit call ("right now it looks ugly").

### D3 — The scanner invariant (non-negotiable)

Barcode scanners are keyboard wedges. Today a hidden 1×1 `QLineEdit` receives
them and `set_focus_to_scanner()` reclaims focus after every action. A
`QWebEngineView` takes keyboard focus when clicked, which would silently swallow
scans. Therefore:

- The web view never holds keyboard focus (`Qt.NoFocus` on the view and its
  focus proxy; clicks on web actions return focus to the scanner through the
  bridge).
- A test proves a keystroke sequence + Enter reaches `barcode_scanned` after a
  click inside the web view. Bundle 4 adds it as a regression test, and the
  owner confirms it with a real scanner on a Windows build before Bundle 4
  merges.

### D4 — `shared/` is already in sync

`theme_css_vars()` and the `.css`/`.html` lint already reached packing-tool via
#175 and #176; both repos' `shared/` trees are byte-identical (44 files,
checked 2026-09-17). No foundations bundle is needed. The original Bundle 1
(drift repair + build gate) was dropped.

### D5 — Mockups are drafted by the runner, approved by the owner

Bundle 2 draws the artboards as HTML under `docs/design/phase10/` using the
artbook's tokens and floor density (44px controls, 12pt body, 60px command bar —
artbook S). The owner approves them on the PR; Bundles 3–6 treat them as the
brief (runner stage A, rule A4).

### D6 — Shared components move into `shared/`, not copied

The components Packing Tool needs from Shopify's `gui/components/` move to
`shared/` (as 9.0 did for icons) so both apps import one copy rather than two
that drift. Bundle 3's Stage A may leave a component in Shopify if it
carries Shopify-only behaviour, and says why.

### D7 — Bug hunt is opportunistic, per bundle

No dedicated audit. Each bundle fixes backend bugs it finds in the code it
touches (`packing_tool/` — `packer_logic`, session / lock / registry managers),
root cause plus a regression test. The Stage C reviewer brief asks for them
explicitly. Bugs outside the bundle's code become GitHub issues, not scope.

### D8 — Statistics stays and is redesigned in Qt

Unlike Shopify (which deleted its Statistics tab), Packing Tool keeps it, built
from `Card`/stat-card components. It does not go on the web tier.

## Non-goals

- No third web screen. Session Browser and Statistics stay Qt.
- No change to session file formats or the Shopify↔Packing contract unless a
  bug fix requires it (then called out in that bundle's spec).
- No new dependency other than `PySide6-QtWebEngine`.

## Risks

- **Scanner over RDP.** Chromium rendering is proven by Shopify Tool; scanner
  focus next to a web view is not. The owner checks it on Windows in Bundle 4.
- **Bundle 5 size.** If its plan exceeds ~15 tasks it splits into 5a (scan
  feedback + panels) and 5b (Qt chrome + retire old widgets).
