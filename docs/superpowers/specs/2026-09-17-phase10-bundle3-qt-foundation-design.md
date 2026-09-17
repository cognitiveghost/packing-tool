# Phase 10 Bundle 3 — Qt foundation (design)

**Roadmap:** `docs/superpowers/plans/2026-09-17-phase10-packer-v2-roadmap.md` → Bundle 3.
**Parent spec:** `docs/superpowers/specs/2026-09-17-phase10-packer-v2-design.md` (D6, D7).
**Brief (mockup):** `docs/design/phase10/packing-table.html` (T1, T2),
`statistics.html` and `session-browser.html` for the per-page command-bar
contents, `HANDOFF.md` for the widget mapping.
**Classification:** architectural. Modules move across two repos, and one
interface (the command bar) is deliberately *not* shared.

Owner answers, 2026-09-17 (Stage A):

| # | Question | Answer |
|---|---|---|
| Q1 | How to share Shopify's `CommandBar` | **Leave it in Shopify.** Packing Tool builds its own bar |
| Q2 | Where the menu bar's actions go | **Overflow ⋯ button in the bar** |
| Q3 | Which components move | **The set Packing Tool needs** (below) |
| Q4 | Rail width (the 56px artboard rail elides labels in Qt) | **Keep 76px, full labels** |
| Q5 | Where the message line's texts go | **Toast** |

## E1 — What moves into `shared/components/`

From Shopify `gui/components/` to packing-tool `shared/components/` (canonical),
then synced into Shopify:

| Module | Why Packing Tool needs it |
|---|---|
| `card.py` (`Card`) | StatePanel's plane; Bundle 6 stat cards |
| `state_panel.py` (`StatePanel`) | T2/S2/B3 empty states (Bundle 6) |
| `toast.py` (`Toast`, `toast`) | E5: replaces the message line |
| `confirm_dialog.py` (`ConfirmDialog`) | roadmap-named; Bundle 5/6 confirmations |
| `filterbar.py` (`FilterBar`) | Session Browser B1 (Bundle 6) |
| `overflow.py` (`OverflowMenu`, `overflow_button`) | E4: the ⋯ menu |

Their tests move with them into packing-tool `tests/`.

**Decoupling.** Four of them import Shopify's `gui.theme_manager`. The
replacements are already in `shared.theme`:

- `get_theme_manager().get_current_theme()` → `current_tokens()`. These
  widgets read colours only, never `font_family`, so the family-less tokens are
  correct. See `current_tokens`' docstring.
- `get_theme_manager().theme_changed.connect(self._apply_theme)` →
  `on_theme_changed(self, lambda _t: self._apply_theme())`.
- `from gui.theme_manager import font_css, set_button_role` → `shared.theme`.
- `apply_dialog_button_roles` (Shopify `gui/theme_manager.py`) moves into
  `shared/theme.py` beside `set_button_role`. Shopify's `gui/theme_manager.py`
  re-imports it, so its call sites keep working.

**Stays in Shopify** (Shopify-only behaviour, or unused by Packing Tool):
`CommandBar` (Q1: client groups, New client, recent sessions, stock chip,
`BarState`), `PrintOptions`, `FileSlot`, `RadioCard`, `FormSection`,
`ErrorBanner`, `InlineMessage`, `ElidedLabel`, `ContextualSelectionBar`.

**Shopify import surface.** `gui/components/__init__.py` keeps exporting every
name. The moved ones are re-exported from `shared.components`, the same way it
already re-exports `shared.navrail.NavRail`. Deep imports
(`from gui.components.card import Card`) switch to `shared.components.card`.
The moved modules are deleted from Shopify.

## E2 — Floor density

Packing Tool runs at `floor` (44px controls, 12pt body). `gui/theme.py`
`load_saved_theme` calls `set_density("floor")` before it builds the
stylesheet. `shared/theme.py`'s `DEFAULT_DENSITY` stays `desk`, because that is
Shopify's default.

## E3 — Rail (Q4: departure from the artboard)

The rail stays at `RAIL_WIDTH = 76` with labels **Packing / Statistics /
Browse**, which are the shipped labels. Measured with the bundled Inter at
10pt bold: "Packing" 51px, "Browse" 47px, "Statistics" 60px. A 56px
`QToolButton` leaves about 48px for text, so the artboard's width would elide
two of its own labels. `tests/test_navrail_labels_fit.py` keeps guarding it.
No code change: the shipped rail already matches the answer.

## E4 — Packing command bar (`gui/command_bar.py`, `CommandBar`)

A packing-tool-only widget, 60px tall (floor), full width above the pages
(right of the rail). It holds only widgets, emits nothing of its own, and owns
no application state. `MainWindow` connects the widgets it exposes.

Left to right, per artboard T1:

| Widget | Attribute | Visible when |
|---|---|---|
| client picker, 240px | `client_combo` (`QComboBox`) | always |
| session id, mono, `text_secondary` | `session_label` | page ≠ browser |
| "Filter orders", 220px, clear button | `filter_input` (`QLineEdit`) | page = packing; enabled only with a session |
| stretch | | |
| **Open session** (primary) | `open_session_button` | page = packing, no session |
| **Start packing** (primary) | `start_packing_button` | page = packing, session |
| SKU mapping | `sku_mapping_button` | page = packing, session |
| End session | `end_session_button` | page = packing, session |
| ⋯ | `overflow_button` / `overflow` | always |

- `set_page(name)` takes `"packing" | "statistics" | "browser"`.
  `set_session(session_id: str | None)` sets the label to the id or
  "No session".
- Exactly one primary is visible at a time.
- End session is secondary (the artboard draws a plain `.btn`), not today's
  `danger`.
- **Open session** navigates to the Browse page (`open_session_browser`).

**Overflow ⋯ (Q2).** The artboards draw none, so this is a departure. Items:
"Select worker…", "Server connection…", "Toggle dark/light theme", a separator,
then "Exit". SKU mappings is not listed, because the bar already has that
button. The menu bar and the toolbar are deleted. Ctrl+E stays as a window
`QShortcut` that calls `end_session_button.click()`. `click()` does nothing on
a disabled button, so the shortcut still respects "no session".

**Session id text.** The session directory name (`current_session_path.name`,
e.g. `2026-09-01_1042`), with the packing-list name as the tooltip. Today the
toolbar shows "Session: <packing list>". The artboard shows the id.

**Search.** Today's `search_input` on the Packing page becomes the bar's
`filter_input`. `MainWindow.search_input` stays as an alias, so
`_filter_orders` and its callers are untouched.

## E5 — Status bar and toasts (Q5)

The message line (`status_label`, above the status bar) is deleted. The
`QStatusBar` becomes the artboard's 40px strip: session id (mono) and worker
name on the left, order summary on the right ("5 orders · 2 packed ·
1 in progress").

- Its colours come from the existing `QStatusBar` rule in
  `build_stylesheet`. Only the mono label restyles itself, through
  `on_theme_changed`.
- The summary is computed in `_populate_order_tree` from
  `logic.session_packing_state` and cleared on session end.
- The worker label shows the name only. The artboard shows a placeholder id
  ("W-007"); a name is what a packer recognises.

Every `status_label.setText` call site is sorted into a toast, a dialog, or
nothing (the table in the plan, Task 5). Two rules decide it:

1. An outcome the user should see becomes a `toast(self, …)` (roles `success`
   or `info`).
2. A failure becomes `QMessageBox.critical`, Packing Tool's existing error
   route. `Toast` has no error role by design.

**D7 bug found.** `end_session` shows "Session ended. Report saved to <path>".
The session teardown then immediately overwrites it with "Session ended. Start
a new session to begin.", so the report path was never readable. The toast
keeps the path; the teardown text is dropped.

## E6 — Shopify side

1. Run `python scripts/sync_shared.py <packing-tool worktree>`.
2. Delete the six moved modules and their six moved tests.
3. Switch deep imports and re-export from `shared.components` in
   `gui/components/__init__.py`.
4. Remove the `apply_dialog_button_roles` definition from
   `gui/theme_manager.py` (it becomes a re-import).
5. `docs/adr/0001-analysis-results-on-the-web-tier.md` gets a note: its
   "Packing Tool stays entirely Qt" line is superseded by packing-tool
   `docs/adr/0001-packer-mode-on-the-web-tier.md`.

## Departures from the artboards (summary)

- **Rail:** 76px, not 56px; labels Packing/Statistics/Browse, not
  Stats/Browse (E3, Q4).
- **Overflow ⋯ button** added at the bar's right end (E4, Q2).
- **Worker name** in the status bar instead of an id (E5).
- **The status bar spans the full window width**, running under the rail, because it is the
  `QMainWindow` status bar. The artboard draws it inside the column right of the rail. Keeping
  `QStatusBar` means Packer Mode (the other page of the stacked widget) keeps its strip for free.
- **T2's state panel** on the Packing page and the order-tree restyle are
  Bundle 6 (HANDOFF). Bundle 3 only puts T2's command bar in place.

## Not in this bundle

Packer Mode chrome (Bundle 5), web order document (Bundle 4), order table /
Statistics / Session Browser page bodies (Bundle 6).
