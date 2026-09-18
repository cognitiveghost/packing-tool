# ADR 0001 — Packer Mode's document renders on the web tier

- **Status:** accepted, 2026-09-17.
- **Deciders:** repo owner
- **Supersedes:** the scope line of shopify-fulfillment-tool ADR 0001
  ("Packing Tool stays entirely Qt").

## Decision

Packer Mode's order document (SKU list, scan feedback, history, extras,
summary, progress) renders in a `QWebEngineView`. The Qt shell keeps scanner
capture, Skip, Exit and the dev scan simulator. Session Browser, Statistics and
every other Packing Tool screen stay Qt.

## Context

Shopify ADR 0001 capped the web tier at Analysis Results because every screen
across the Qt↔JS seam costs maintenance twice. That cap assumed Packing Tool had
no screen worth the cost. Packer Mode now is: its layout is built from
`QTableWidget`s and feedback labels the owner calls ugly, and the same
reasoning that moved Analysis Results applies. Rebuilding it in Qt again
changes nothing about why it looks the way it does.

The owner accepted the build-size cost up front: Chromium already ships in
Shopify Tool (128 → 294 MiB zip, verified on Windows over RDP), on the same
warehouse machines.

## Consequences

- `PySide6-QtWebEngine` becomes a dependency; CI must guard that the frozen build
  contains `QtWebEngineProcess.exe`.
- **Scanner invariant.** Barcode scanners type into a hidden Qt `QLineEdit`.
  The web view must never hold keyboard focus, or scans are silently lost. It is
  `NoFocus`, and a regression test sends a scan after a click inside the view.
- Shopify ADR 0001's guardrails apply unchanged: colour only from
  `shared/theme.py` via `theme_css_vars()`, no hex in web assets, no
  shadows/gradients/transitions/transforms/px font sizes, one mono face.
- **Amended 2026-09-18 (owner):** animation is *not* among those guardrails.
  Shopify's ADR left it an open question rather than deciding it, and
  `shared/style_lint.py` accordingly bans `transition`, `transform`,
  `scale/rotate/translate` and `opacity` but not `animation`/`@keyframes`. A
  `@keyframes` rule over properties the lint allows is permitted on this
  repo's web tier — Bundle 4 uses one for the scan flash, the cue a packer
  reads from across the floor. The banned list above is unchanged: an
  animation may not reach for `transition`, `transform` or `opacity`.
- No third web screen without a new ADR.

## Alternatives considered

**Redesign Packer Mode in Qt.** Cheaper, keeps the build smaller. Rejected by
the owner for the same reason Shopify's third Qt rebuild was rejected.

**Move the whole Packer Mode page, scanner included, to the web.** Rejected:
scanner focus would have to be rebuilt in JS and proven on hardware, for no
layout gain the split does not already give.
