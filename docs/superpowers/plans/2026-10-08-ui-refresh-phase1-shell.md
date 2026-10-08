# UI refresh phase 1 (floor shell) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the approved mockups in the repo, sync `shared/` to Fulfilment's `main`, and rebuild the Qt shell (sidebar, command bar, no status bar, connection card and banner) to mockup frames 2a to 2e.

**Architecture:** Two new app-side Qt components (`Sidebar`, `ConnectionBanner`) and a reworked `CommandBar` hold widgets and no application state. `MainWindow` owns the state (client chosen, connection `ok`/`checking`/`down`, sidebar expanded) and pushes it into them. The three pages stay the Qt pages of today.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QSS), pytest with pytest-qt. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-08-ui-refresh-phase1-shell-design.md`. Read it first. ADR: `docs/adr/0002-every-screen-on-the-web-tier.md`.

## Global Constraints

- **Never edit a file under `shared/`** except by running `scripts/sync_shared.py` (Task 2). A hook blocks hand edits and CI diffs the folder.
- **No colour literals.** Every colour is a token read from `shared.theme` (`on_theme_changed(widget, apply)` gives the tokens). `tests/test_style_literals_guard.py` fails on a hex string in `gui/`.
- **Icons** only through `shared.icons.icon("name")`, and only names that exist in `shared/assets/icons/`. This plan uses: `package`, `clipboard-list`, `table`, `folder-open`, `tag`, `sun`, `moon`, `server`, `circle-alert`, `panel-left-close`, `panel-left-open`.
- **A widget's own stylesheet is re-run on every theme change** (`on_theme_changed`), never set once. A `QWidget` subclass needs `setAttribute(Qt.WA_StyledBackground, True)` to paint a QSS background.
- **Floor sizes:** controls 44px, command bar and sidebar header 60px, sidebar 200px / 56px, body text `font_css('body')` (12pt), captions `font_css('caption')` (10pt).
- **Copy, verbatim:** "Packer Assistant", "Packing", "Statistics", "Sessions", "SKU mapping", "Switch worker…", "Light", "Dark", "Server connected", "Reconnecting…", "Server unreachable", "Retry", "Choose a client", "Filter orders", "Open session", "Start packing", "End session", "Server connection…", "Exit". The ellipsis is the single character `…`.
- **Git:** `/usr/bin/git`, one plain git command per Bash call (no `&&`, `;`, `$VAR` paths). Commit with `/usr/bin/git commit -F <absolute path to a message file>`; write the message file with the Write tool. Never commit to `main`. Each commit message ends with the attribution lines your session gives you.
- **Tests:** run with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <path>`. If a hook refuses that, run the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Write test files with Write/Edit, never with shell redirection. Read visibility in tests with `isHidden()`: widgets that were never shown report `isVisible() == False`.
- **Lint:** `.venv/bin/ruff check . --exclude shared` must pass before each commit.
- After the last code change, run `graphify update .` (CLAUDE.md).
- Departures from the mockup are the ten in spec section 7. If you make another, add it to the spec's table in the same commit.

## Review Focus

Failure modes the spec implies that are most likely to bite a packer. Each has a test in the task named.

1. **A worker name of one word, or a very long one.** One initial, not a crash; the name elides and the card keeps its width (Task 3, `test_initials`, `test_a_long_worker_name_does_not_widen_the_sidebar`).
2. **A long UNC server path.** Elided in the middle on the card, whole in the tooltip (Task 3, `test_a_long_path_is_elided_and_kept_in_the_tooltip`).
3. **Retry pressed several times while a check runs.** One check, not a pile of threads (Task 8, `test_a_second_check_while_one_runs_is_ignored`).
4. **The window closes while a check is in flight.** No exception from the worker thread (Task 8, the `RuntimeError` guard, covered by `test_a_check_that_outlives_the_window_does_not_raise`).
5. **The remembered client was deleted on the server.** With two or more clients left the app starts on "Choose a client"; it does not select a stale index or crash (Task 7, `test_a_remembered_client_that_no_longer_exists_is_not_restored`).

## File map

| File | Responsibility | Task |
|---|---|---|
| `docs/design/ui-refresh/**` | mockups, prompts, current renders, phase 1 renders | 1, 9 |
| `shared/**`, `scripts/shared_synced_from.txt` | mirror of Fulfilment's `shared/` at `main` | 2 |
| `tests/test_theme.py` | drops the old-palette pins | 2 |
| `gui/components/__init__.py`, `gui/components/sidebar.py` | `Sidebar`, `FloorNavRail`, `initials()` | 3 |
| `gui/components/connection_banner.py` | `ConnectionBanner` | 4 |
| `gui/command_bar.py` | the 60px bar, reworked | 5 |
| `gui/main_window.py` | mounts the shell, owns client, connection and sidebar state | 6, 7, 8 |
| `gui/session_browser/session_browser_widget.py` | interim "12 of 40 sessions" caption | 6 |
| `scripts/render_shell.py` | offscreen renders of 2a to 2e | 9 |
| `CONTEXT.md` | glossary | 9 |

---

### Task 1: Design inputs in the repo

**Files:**
- Create: `docs/design/ui-refresh/mockups/` (six `.html` files and `README.md`), `docs/design/ui-refresh/prompts.md`, `docs/design/ui-refresh/current/*.png`

**Interfaces:**
- Produces: `docs/design/ui-refresh/mockups/Packer App.html` and `Floor Components.html`, which every later task reads as the brief.

- [ ] **Step 1: Copy the files**

Run each as its own Bash call:

```bash
mkdir -p docs/design/ui-refresh/mockups docs/design/ui-refresh/current
cp "/home/gloopy/Obsidian/Claude/packer-ui-refresh/ready mockups/"*.html docs/design/ui-refresh/mockups/
cp /home/gloopy/Desktop/Projects/packing-tool/docs/design/ui-refresh/prompts.md docs/design/ui-refresh/prompts.md
cp /home/gloopy/Desktop/Projects/packing-tool/docs/design/ui-refresh/current/*.png docs/design/ui-refresh/current/
ls docs/design/ui-refresh/mockups docs/design/ui-refresh/current
```

Expected: six files in `mockups/` (`Floor Components.html`, `Packer App.html`, `Packer Mode.html`, `Packer Screens.html`, `SKU Mapping.html`, `Worker Selection.html`) and 23 PNGs in `current/`. Do not rename anything: `Packer Screens.html` imports the others by name. Do not copy `.~lock.prompts.md#`.

- [ ] **Step 2: Mark the prompts as approved**

In `docs/design/ui-refresh/prompts.md` replace the line

```markdown
**Draft, 2026-10-07. Not yet reviewed by the owner.**
```

with

```markdown
**The mockups made from these prompts were approved by the owner on 2026-10-08.** They are in
[`mockups/`](mockups/), under the names Claude Design gave them, not the names the table below proposes.
```

- [ ] **Step 3: Write `docs/design/ui-refresh/mockups/README.md`**

````markdown
# Approved mockups (2026-10-08)

Claude Design bundles, made from [`../prompts.md`](../prompts.md) and approved by the owner. They are the
brief for all five phases of the UI refresh (ADR 0002).

| File | Screens | Frames |
|---|---|---|
| `Packer Screens.html` | the index: every frame, importing the files below by name | 1a to 8f |
| `Floor Components.html` | floor-density type, buttons, badges, inputs, rows, banner, toast | 1a, 1b |
| `Packer App.html` | the shell, Packing, Statistics, Sessions, Session details | 2a to 5b, 7a to 8f |
| `Packer Mode.html` | Packer Mode | 6a to 6j |
| `SKU Mapping.html` | SKU mapping | addendum |
| `Worker Selection.html` | Worker selection | addendum |

Do not rename a file: `Packer Screens.html` imports the others by name, and specs cite its frame ids.

## Viewing

Open `Packer Screens.html` in Chrome from this folder. Each frame carries its id; the notes beside a group
are part of the brief.

## Reading exact values

Each file is a bundle: a gzip+base64 manifest of scripts plus a JSON-encoded template. Sizes, colours and
state logic are in the template. The `const T = {...}` table in it holds the tokens as `[light, dark]`
pairs. To unpack:

```python
import base64, gzip, json, re, sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
block = lambda t: re.search(rf'<script type="__bundler/{t}">(.*?)</script>', src, re.S).group(1)
for key, entry in json.loads(block("manifest")).items():
    data = base64.b64decode(entry["data"])
    (out / f"{key}.js").write_bytes(gzip.decompress(data) if entry.get("compressed") else data)
(out / "template.html").write_text(json.loads(block("template")))
```

Save it outside the repo and run it with `.venv/bin/python -I unpack.py "Packer App.html" /tmp/packer-app`,
then read `/tmp/packer-app/template.html`. The shell is the `<nav>` and `<header>` at the top of that
template; its state logic is `renderVals()` at the bottom.
````

- [ ] **Step 4: Commit**

```bash
/usr/bin/git add docs/design
/usr/bin/git commit -F <message file>
```

Message: `docs: approved UI refresh mockups, prompts and current renders`.

---

### Task 2: Sync `shared/` to Fulfilment's `main`

**Files:**
- Modify (by script only): `shared/**`, `scripts/shared_synced_from.txt`
- Modify: `tests/test_theme.py`

**Interfaces:**
- Produces: the new tokens (`status_success_dot`, `status_danger_dot`, `status_danger_border`, `control_disabled_bg`, …), `NavRail(expanded_width=...)` with `set_expanded(bool)`, and the icons `sun`, `moon`, `server`, `circle-alert`, `panel-left-close`, `panel-left-open`.

Background: the owner's Fulfilment checkout at `../shopify-fulfillment-tool` is behind `origin/main`. Do not pull, check out or otherwise touch it. The pin in `scripts/shared_synced_from.txt` (`ffec57b…`) is not on Fulfilment's `main` (it was a squash-merged PR branch head with an identical `shared/`), so the script's ancestor check refuses it and `--force` is needed this once.

- [ ] **Step 1: Clone Fulfilment's `main` to a temp folder**

```bash
gh repo clone cognitiveghost/shopify-fulfillment-tool /tmp/dr-24-fulfilment
```

Then, as its own call:

```bash
/usr/bin/git -C /tmp/dr-24-fulfilment log --oneline -1
```

Expected: `387efef Web tier freshness: …(#372)` or a later commit on `main`. A later commit is fine. If `shared/` changed again since `387efef`, read `/usr/bin/git -C /tmp/dr-24-fulfilment log --oneline 387efef..HEAD -- shared` and, if anything other than additions shows up, record it with `runner <run> note` before going on.

- [ ] **Step 2: Run the sync**

```bash
.venv/bin/python scripts/sync_shared.py /tmp/dr-24-fulfilment --force
```

Expected output starts with `Synced … file(s) from /tmp/dr-24-fulfilment/shared (main) at <sha>`. `scripts/shared_synced_from.txt` now holds that sha. Confirm the new files exist: `ls shared/web shared/web_page.py shared/assets/icons/server.svg`.

- [ ] **Step 3: Run the suite and confirm what breaks**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Expected: `18 failed, 536 passed`, every failure in `tests/test_theme.py`. If anything outside `tests/test_theme.py` fails, stop and `runner <run> note` it: the plan assumed otherwise.

- [ ] **Step 4: Delete the seven tests that pin old palette values**

In `tests/test_theme.py` delete these functions whole (decorators and docstrings included). Palette values are tested in Fulfilment, which owns `shared/`:

- `test_dark_base_is_not_pure_black`
- `test_border_is_the_missing_middle_and_the_old_value_survives`
- `test_dark_page_plane_lifted_off_the_frame`
- `test_light_planes_are_an_even_ramp`
- `test_hover_is_the_overlay_plane`
- `test_selection_border_folds_onto_status_info`
- `test_focus_ring_folds_onto_status_info_in_light_only`

- [ ] **Step 5: Cut four tests down to what holds for any palette**

Replace `test_the_frame_plane_exists_and_is_part_of_the_matrix` with:

```python
def test_the_frame_plane_is_part_of_the_matrix():
    """surface_sunken is the app frame and the sidebar. A plane that is not in
    _SURFACE_PLANES is not validated for contrast, which is the failure mode
    the matrix exists to end. surface_inverse is the toast's plane, not an
    elevation step, and stays out."""
    assert _SURFACE_PLANES == (
        "surface_sunken", "surface", "surface_raised", "surface_overlay"
    )
```

Replace `test_the_three_accent_fills_are_theme_independent` with:

```python
def test_the_three_accent_fills_are_the_matrix():
    """Derived from _COLOR_FIELDS by prefix: this fails if a fill is renamed
    out of the matrix or a non-fill token wanders into it."""
    assert _ACCENT_FILLS == ("accent_fill", "accent_fill_hover", "accent_fill_active")
```

In `test_validate_theme_rejects_a_fill_that_fails_only_on_hover`, replace the `dataclasses.replace(...)` call with one whose hover fill is the label's own colour, so it fails against whatever `on_accent` is:

```python
    regressed = dataclasses.replace(
        DARK_THEME, name="regressed",
        accent_fill_hover=DARK_THEME.on_accent,   # 1:1 behind its own label
    )
```

and change its docstring's first sentence to: `A theme that passes on accent_fill and fails on the hover fill must raise.`

In `test_selection_is_a_ring_and_not_an_accent_fill`, rename it to `test_selection_is_a_ring` and delete its last two assertions (`theme.accent_fill not in rule`, `theme.on_accent not in rule`): `accent_fill` now equals `text`, so they no longer say anything about the ring.

- [ ] **Step 6: Run the suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Expected: 0 failed. Then `.venv/bin/ruff check . --exclude shared` (an import in `tests/test_theme.py` may now be unused; remove it if ruff says so).

- [ ] **Step 7: Remove the clone and commit**

```bash
rm -rf /tmp/dr-24-fulfilment
/usr/bin/git add shared scripts/shared_synced_from.txt tests/test_theme.py
/usr/bin/git commit -F <message file>
```

Message: `chore(shared): sync to shopify-fulfillment-tool main (new palette, sidebar NavRail, web kit)`, with a body line: `--force once: the old pin was a squash-merged PR head, not on main; its shared/ equals the merge commit's.`

---

### Task 3: `Sidebar`

**Files:**
- Create: `gui/components/__init__.py`, `gui/components/sidebar.py`
- Test: `tests/test_sidebar.py`

**Interfaces:**
- Consumes: `shared.navrail.NavRail(parent, expanded_width=200)`, `NavRail.set_expanded(bool)`, `NavRail.add_item(QIcon, str) -> int`, `NavRail.button(int)`; `gui.command_bar.BAR_HEIGHT` (60).
- Produces, in `gui/components/sidebar.py`:
  - `SIDEBAR_WIDTH = 200`, `ITEM_HEIGHT = 44`, `CONNECTION_STATES = ("ok", "checking", "down")`
  - `initials(name: str) -> str`
  - `class FloorNavRail(NavRail)`
  - `class Sidebar(QWidget)` with attribute `rail: FloorNavRail`; signals `skuMappingRequested()`, `switchWorkerRequested()`, `themeRequested(str)`, `retryRequested()`; methods `set_expanded(bool)`, `is_expanded() -> bool`, `set_worker(name: str)`, `set_theme_name(name: str)`, `set_connection(state: str, server_path: str)`, `set_client_chosen(bool)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sidebar.py`:

```python
"""The shell's left column (spec 2026-10-08 section 6.2, mockup frames 2a-2e).

Never shown in these tests, so visibility is read with isHidden().
"""

import pytest

from gui.components.sidebar import ITEM_HEIGHT, SIDEBAR_WIDTH, Sidebar, initials
from shared import theme as shared_theme
from shared.icons import icon
from shared.navrail import RAIL_WIDTH
from shared.theme import current_theme_name, current_tokens, set_current


@pytest.fixture
def sidebar(qapp):
    widget = Sidebar()
    for name, label in (("clipboard-list", "Packing"), ("table", "Statistics"),
                        ("folder-open", "Sessions")):
        widget.rail.add_item(icon(name), label)
    yield widget
    widget.deleteLater()


@pytest.mark.parametrize("name, expected", [
    ("Desislava Ilieva", "DI"),
    ("Maria", "M"),
    ("ana maria de souza", "AM"),
    ("  ", ""),
    ("", ""),
])
def test_initials(name, expected):
    assert initials(name) == expected


def test_it_starts_expanded_at_200(sidebar):
    assert sidebar.is_expanded()
    assert sidebar.width() == SIDEBAR_WIDTH == 200
    assert not sidebar.title.isHidden()
    assert not sidebar.worker_card.isHidden()
    assert not sidebar.theme_segment.isHidden()
    assert not sidebar.connection_box.isHidden()
    assert sidebar.worker_rail_button.isHidden()
    assert sidebar.theme_toggle.isHidden()
    assert sidebar.connection_icon.isHidden()


def test_collapsed_is_the_56px_rail(sidebar):
    sidebar.set_expanded(False)
    assert not sidebar.is_expanded()
    assert sidebar.width() == RAIL_WIDTH == 56
    assert sidebar.title.isHidden()
    assert sidebar.worker_card.isHidden()
    assert sidebar.theme_segment.isHidden()
    assert sidebar.connection_box.isHidden()
    assert not sidebar.worker_rail_button.isHidden()
    assert not sidebar.theme_toggle.isHidden()
    assert not sidebar.connection_icon.isHidden()


@pytest.mark.parametrize("expanded", [True, False])
def test_every_destination_and_sku_mapping_is_44px_tall(sidebar, expanded):
    """Floor density. shared's NavRail ships 32px items; FloorNavRail overrides
    its private _shape, so this is the test that fails if a sync renames it."""
    sidebar.set_expanded(expanded)
    for index in range(3):
        assert sidebar.rail.button(index).height() == ITEM_HEIGHT == 44
    assert sidebar.sku_button.height() == 44


def test_the_worker_shows_initials_and_name(sidebar):
    sidebar.set_worker("Desislava Ilieva")
    assert sidebar.worker_avatar.text() == "DI"
    assert sidebar.worker_rail_button.text() == "DI"
    assert sidebar.worker_name.toolTip() == "Desislava Ilieva"
    assert sidebar.worker_rail_button.toolTip() == "Desislava Ilieva · Switch worker…"


def test_a_long_worker_name_does_not_widen_the_sidebar(sidebar):
    sidebar.set_worker("Maximiliana Konstantinopolska-Wolfeschlegelstein")
    assert sidebar.width() == SIDEBAR_WIDTH
    assert sidebar.worker_name.text().endswith("…")
    assert sidebar.worker_name.toolTip().startswith("Maximiliana")


@pytest.mark.parametrize("state, label, retry_hidden", [
    ("ok", "Server connected", True),
    ("checking", "Reconnecting…", True),
    ("down", "Server unreachable", False),
])
def test_each_connection_state(sidebar, state, label, retry_hidden):
    sidebar.set_connection(state, r"\\fs01\packer")
    assert sidebar.connection_label.text() == label
    assert sidebar.retry_button.isHidden() is retry_hidden
    assert sidebar.connection_icon.toolTip() == rf"{label} · \\fs01\packer"


def test_an_unknown_connection_state_fails_loudly(sidebar):
    with pytest.raises(KeyError):
        sidebar.set_connection("offline", "x")


def test_a_long_path_is_elided_and_kept_in_the_tooltip(sidebar):
    path = r"\\warehouse-fileserver-01.corp.example\fulfilment\packer-assistant\production"
    sidebar.set_connection("ok", path)
    assert sidebar.path_label.text() != path
    assert "…" in sidebar.path_label.text()
    assert sidebar.path_label.toolTip() == path
    assert sidebar.width() == SIDEBAR_WIDTH


def test_no_client_disables_the_destinations_and_sku_mapping(sidebar):
    sidebar.set_client_chosen(False)
    assert not any(sidebar.rail.button(i).isEnabled() for i in range(3))
    assert not sidebar.sku_button.isEnabled()
    sidebar.set_client_chosen(True)
    assert all(sidebar.rail.button(i).isEnabled() for i in range(3))
    assert sidebar.sku_button.isEnabled()


def test_the_footer_controls_emit(sidebar, qtbot):
    with qtbot.waitSignal(sidebar.skuMappingRequested, timeout=500):
        sidebar.sku_button.click()
    with qtbot.waitSignal(sidebar.switchWorkerRequested, timeout=500):
        sidebar.worker_link.click()
    with qtbot.waitSignal(sidebar.switchWorkerRequested, timeout=500):
        sidebar.worker_rail_button.click()
    with qtbot.waitSignal(sidebar.themeRequested, timeout=500) as dark:
        sidebar.dark_button.click()
    assert dark.args == ["dark"]
    sidebar.set_connection("down", "x")
    with qtbot.waitSignal(sidebar.retryRequested, timeout=500):
        sidebar.retry_button.click()
    with qtbot.waitSignal(sidebar.retryRequested, timeout=500):
        sidebar.connection_icon.click()


def test_the_collapsed_connection_glyph_only_retries_when_down(sidebar, qtbot):
    sidebar.set_connection("ok", "x")
    with qtbot.assertNotEmitted(sidebar.retryRequested):
        sidebar.connection_icon.click()


def test_the_theme_toggle_asks_for_the_other_theme(sidebar, qtbot):
    sidebar.set_theme_name("dark")
    assert sidebar.dark_button.isChecked()
    with qtbot.waitSignal(sidebar.themeRequested, timeout=500) as blocker:
        sidebar.theme_toggle.click()
    assert blocker.args == ["light"]


def test_it_restyles_on_a_theme_switch_and_keeps_its_state(sidebar):
    sidebar.set_connection("down", "x")
    before = current_theme_name()
    set_current("dark" if before == "light" else "light")
    try:
        assert current_tokens().surface_sunken in sidebar.styleSheet()
        assert current_tokens().status_danger_bg in sidebar.connection_box.styleSheet()
        assert not sidebar.retry_button.isHidden()
    finally:
        shared_theme._current = before
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sidebar.py`
Expected: collection error, `ModuleNotFoundError: No module named 'gui.components'`.

- [ ] **Step 3: Write the component**

Create `gui/components/__init__.py`:

```python
"""Packer Assistant's own shell widgets. What both apps share is in shared/components."""
```

Create `gui/components/sidebar.py`:

```python
"""The shell's left column: header, destinations, footer.

UI refresh phase 1, spec docs/superpowers/specs/2026-10-08-ui-refresh-phase1-shell-design.md
section 6.2, following docs/design/ui-refresh/mockups/Packer App.html frames
2a-2e. The same shape as shopify-fulfillment-tool's gui/components/sidebar.py,
at floor sizes and with this app's footer: SKU mapping, the worker, the theme
and the connection.

It holds widgets and no application state. MainWindow tells it the worker,
the theme, the connection state and whether a client is chosen.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.command_bar import BAR_HEIGHT
from shared.icons import icon
from shared.navrail import RAIL_WIDTH, NavRail
from shared.theme import current_tokens, font_css, on_theme_changed

SIDEBAR_WIDTH = 200
ITEM_HEIGHT = 44
CONNECTION_STATES = ("ok", "checking", "down")
# state -> (label, the status role whose colours it wears)
_CONNECTION = {
    "ok": ("Server connected", "success"),
    "checking": ("Reconnecting…", "warning"),
    "down": ("Server unreachable", "danger"),
}
# 200 - footer margins 16 - card padding 20 - dot 10 - gap 8 = 146, less a few
# px so the ellipsis never touches the card's edge.
_PATH_WIDTH = 140
# 200 - footer margins 16 - card padding 16 - avatar 32 - gap 10 = 126.
_NAME_WIDTH = 122


def initials(name: str) -> str:
    """The first letters of the first two words: "Desislava Ilieva" -> "DI"."""
    return "".join(word[0] for word in name.split()[:2]).upper()


class FloorNavRail(NavRail):
    """NavRail's sidebar mode at floor density.

    shared/ cannot be edited from this repo, and its sidebar items are 32px
    tall with a 16px icon. Both overrides are of private methods, so
    tests/test_sidebar.py pins the 44px height: a sync that renames either
    fails there instead of quietly shrinking the items. Listed under
    "For shared/" in the phase 1 spec, section 8.
    """

    def _shape(self, button: QToolButton) -> None:
        super()._shape(button)
        button.setFixedHeight(ITEM_HEIGHT)
        button.setIconSize(QSize(20, 20))

    def _apply_theme(self, _name: str | None = None) -> None:
        super()._apply_theme(_name)
        # With no client chosen every destination is disabled, and the mockup
        # (frame 2a) draws none of them as current.
        tokens = current_tokens()
        self.setStyleSheet(
            self.styleSheet()
            + "NavRail QToolButton:checked:disabled { background-color: transparent;"
            f" border: 1px solid transparent; color: {tokens.text_disabled};"
            " font-weight: normal; }"
        )


class Sidebar(QWidget):
    """Header, destinations, footer. Collapses to a 56px rail."""

    skuMappingRequested = Signal()
    switchWorkerRequested = Signal()
    themeRequested = Signal(str)
    retryRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A QWidget subclass paints no QSS background without this.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._expanded = True
        self._state = "ok"
        self._theme_name = current_tokens().name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header: the mark and the app's name. The collapse button is the
        # command bar's first control, as the mockup draws it.
        self.header = QFrame(self)
        self.header.setObjectName("SidebarHeader")
        # The bar's height, so the two rules under them are one line.
        self.header.setFixedHeight(BAR_HEIGHT)
        self._header_row = QHBoxLayout(self.header)
        self._header_row.setSpacing(10)
        self.mark = QLabel(self.header)
        self.mark.setObjectName("SidebarMark")
        self.mark.setFixedSize(32, 32)
        self.mark.setAlignment(Qt.AlignCenter)
        self.title = QLabel("Packer Assistant", self.header)
        self.title.setMinimumWidth(0)
        self._header_row.addWidget(self.mark)
        self._header_row.addWidget(self.title, 1)
        layout.addWidget(self.header)

        self.rail = FloorNavRail(self, expanded_width=SIDEBAR_WIDTH)
        self.rail.layout().setSpacing(4)
        layout.addWidget(self.rail, 1)

        self.footer = QFrame(self)
        self.footer.setObjectName("SidebarFooter")
        footer = QVBoxLayout(self.footer)
        footer.setContentsMargins(8, 8, 8, 8)
        footer.setSpacing(6)

        self.sku_button = QToolButton(self.footer)
        self.sku_button.setObjectName("FooterItem")
        self.sku_button.setText("SKU mapping")
        self.sku_button.setToolTip("SKU mapping…")
        self.sku_button.setAutoRaise(True)
        self.sku_button.setIconSize(QSize(20, 20))
        self.sku_button.clicked.connect(self.skuMappingRequested.emit)
        footer.addWidget(self.sku_button)

        # Worker, expanded: avatar, name, Switch worker… link.
        self.worker_card = QFrame(self.footer)
        self.worker_card.setObjectName("WorkerCard")
        self.worker_card.setMinimumHeight(56)
        self.worker_card.setToolTip("Signed-in worker")
        card = QHBoxLayout(self.worker_card)
        card.setContentsMargins(8, 6, 8, 6)
        card.setSpacing(10)
        self.worker_avatar = QLabel(self.worker_card)
        self.worker_avatar.setObjectName("WorkerAvatar")
        self.worker_avatar.setFixedSize(32, 32)
        self.worker_avatar.setAlignment(Qt.AlignCenter)
        names = QVBoxLayout()
        names.setSpacing(0)
        self.worker_name = QLabel(self.worker_card)
        self.worker_name.setObjectName("WorkerName")
        self.worker_name.setFixedWidth(_NAME_WIDTH)
        self.worker_link = QPushButton("Switch worker…", self.worker_card)
        self.worker_link.setObjectName("WorkerLink")
        self.worker_link.setFlat(True)
        self.worker_link.setCursor(Qt.PointingHandCursor)
        self.worker_link.clicked.connect(self.switchWorkerRequested.emit)
        names.addWidget(self.worker_name)
        names.addWidget(self.worker_link, 0, Qt.AlignLeft)
        card.addWidget(self.worker_avatar)
        card.addLayout(names, 1)
        footer.addWidget(self.worker_card)

        # Worker, collapsed: the avatar is the button.
        self.worker_rail_button = QToolButton(self.footer)
        self.worker_rail_button.setObjectName("WorkerRailButton")
        self.worker_rail_button.setFixedSize(32, 32)
        self.worker_rail_button.clicked.connect(self.switchWorkerRequested.emit)
        footer.addWidget(self.worker_rail_button, 0, Qt.AlignHCenter)

        self.theme_segment = QFrame(self.footer)
        self.theme_segment.setObjectName("ThemeSegment")
        self.theme_segment.setFixedHeight(ITEM_HEIGHT)
        segment = QHBoxLayout(self.theme_segment)
        segment.setContentsMargins(2, 2, 2, 2)
        segment.setSpacing(2)
        self.light_button = self._segment_button("Light")
        self.dark_button = self._segment_button("Dark")
        group = QButtonGroup(self.theme_segment)
        group.setExclusive(True)
        for button, name in ((self.light_button, "light"), (self.dark_button, "dark")):
            group.addButton(button)
            segment.addWidget(button)
            button.clicked.connect(lambda _c=False, n=name: self.themeRequested.emit(n))
        footer.addWidget(self.theme_segment)

        self.theme_toggle = QToolButton(self.footer)
        self.theme_toggle.setObjectName("FooterItem")
        self.theme_toggle.setAutoRaise(True)
        self.theme_toggle.setIconSize(QSize(20, 20))
        self.theme_toggle.setFixedSize(RAIL_WIDTH - 16, ITEM_HEIGHT)
        self.theme_toggle.clicked.connect(
            lambda: self.themeRequested.emit(
                "light" if self._theme_name == "dark" else "dark"
            )
        )
        footer.addWidget(self.theme_toggle)

        # Connection, expanded: dot, state, path, Retry.
        self.connection_box = QFrame(self.footer)
        self.connection_box.setObjectName("ConnectionBox")
        self.connection_box.setMinimumHeight(52)
        box = QHBoxLayout(self.connection_box)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(8)
        self.connection_dot = QLabel(self.connection_box)
        self.connection_dot.setFixedSize(10, 10)
        dot_column = QVBoxLayout()
        dot_column.setContentsMargins(0, 4, 0, 0)
        dot_column.addWidget(self.connection_dot)
        dot_column.addStretch()
        box.addLayout(dot_column)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.connection_label = QLabel(self.connection_box)
        self.path_label = QLabel(self.connection_box)
        self.path_label.setFixedWidth(_PATH_WIDTH)
        self.retry_button = QPushButton("Retry", self.connection_box)
        self.retry_button.setObjectName("RetryButton")
        self.retry_button.setFixedHeight(ITEM_HEIGHT)
        self.retry_button.clicked.connect(self.retryRequested.emit)
        self.retry_button.hide()
        text.addWidget(self.connection_label)
        text.addWidget(self.path_label)
        text.addSpacing(4)
        text.addWidget(self.retry_button)
        box.addLayout(text, 1)
        footer.addWidget(self.connection_box)

        # Connection, collapsed: a server glyph with the same dot.
        self.connection_icon = QToolButton(self.footer)
        self.connection_icon.setObjectName("ConnectionIcon")
        self.connection_icon.setIconSize(QSize(20, 20))
        self.connection_icon.setFixedSize(RAIL_WIDTH - 16, ITEM_HEIGHT)
        self.connection_icon.clicked.connect(self._retry_if_down)
        self.connection_icon_dot = QLabel(self.connection_icon)
        self.connection_icon_dot.setFixedSize(10, 10)
        self.connection_icon_dot.move(24, 26)
        self.connection_icon_dot.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        footer.addWidget(self.connection_icon)

        layout.addWidget(self.footer)

        self._server_path = ""
        self._worker = ""
        on_theme_changed(self, self._apply_theme)
        self.set_expanded(True)

    # -- construction helpers -------------------------------------------------

    def _segment_button(self, text: str) -> QToolButton:
        button = QToolButton(self.theme_segment)
        button.setText(text)
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setFixedHeight(ITEM_HEIGHT - 6)
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    def _retry_if_down(self) -> None:
        if self._state == "down":
            self.retryRequested.emit()

    # -- public API -------------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.setFixedWidth(SIDEBAR_WIDTH if expanded else RAIL_WIDTH)
        self.rail.set_expanded(expanded)
        if expanded:
            self._header_row.setContentsMargins(14, 0, 14, 0)
        else:
            # (56 - 32) / 2: the mark centred in the rail.
            self._header_row.setContentsMargins(12, 0, 12, 0)
        for widget in (self.title, self.worker_card, self.theme_segment,
                       self.connection_box):
            widget.setVisible(expanded)
        for widget in (self.worker_rail_button, self.theme_toggle,
                       self.connection_icon):
            widget.setVisible(not expanded)
        self.sku_button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon if expanded else Qt.ToolButtonIconOnly
        )
        self.sku_button.setFixedSize(
            (SIDEBAR_WIDTH if expanded else RAIL_WIDTH) - 16, ITEM_HEIGHT
        )
        self._apply_theme(current_tokens())

    def is_expanded(self) -> bool:
        return self._expanded

    def set_worker(self, name: str) -> None:
        self._worker = name or ""
        letters = initials(self._worker)
        self.worker_avatar.setText(letters)
        self.worker_rail_button.setText(letters)
        metrics = QFontMetrics(self.worker_name.font())
        self.worker_name.setText(
            metrics.elidedText(self._worker, Qt.ElideRight, _NAME_WIDTH)
        )
        self.worker_name.setToolTip(self._worker)
        self.worker_rail_button.setToolTip(f"{self._worker} · Switch worker…")

    def set_theme_name(self, name: str) -> None:
        self._theme_name = name
        (self.dark_button if name == "dark" else self.light_button).setChecked(True)
        self.theme_toggle.setToolTip(
            "Switch to Light" if name == "dark" else "Switch to Dark"
        )
        self.theme_toggle.setIcon(icon("sun" if name == "dark" else "moon"))

    def set_connection(self, state: str, server_path: str) -> None:
        label, _role = _CONNECTION[state]  # KeyError on an unknown state
        self._state = state
        self._server_path = server_path
        self.connection_label.setText(label)
        metrics = QFontMetrics(self.path_label.font())
        self.path_label.setText(
            metrics.elidedText(server_path, Qt.ElideMiddle, _PATH_WIDTH)
        )
        self.path_label.setToolTip(server_path)
        self.connection_box.setToolTip(f"{label} · {server_path}")
        self.connection_icon.setToolTip(f"{label} · {server_path}")
        self.retry_button.setVisible(state == "down")
        self._style_connection(current_tokens())

    def set_client_chosen(self, chosen: bool) -> None:
        for index in range(len(self.rail._buttons)):
            self.rail.button(index).setEnabled(chosen)
        self.sku_button.setEnabled(chosen)

    # -- internals --------------------------------------------------------------

    def _apply_theme(self, t) -> None:
        """Re-run on every theme change: this widget's own sheet outranks the
        app's, and a QIcon is a snapshot (ADR 0003)."""
        pad = 9 if self._expanded else 0
        self.setStyleSheet(
            f"Sidebar {{ background-color: {t.surface_sunken};"
            f" border-right: 1px solid {t.border_subtle}; }}"
            # The app sheet's `QWidget` rule would paint these on `surface`.
            f"#SidebarHeader, #SidebarFooter {{ background-color: {t.surface_sunken}; }}"
            f"#SidebarHeader {{ border-bottom: 1px solid {t.border_subtle}; }}"
            f"#SidebarFooter {{ border-top: 1px solid {t.border_subtle}; }}"
            f"#SidebarMark {{ background-color: {t.accent_fill}; border-radius: 8px; }}"
            f"#SidebarHeader QLabel {{ background: transparent; color: {t.text};"
            f" {font_css('body', bold=True)} }}"
            f"#FooterItem {{ background-color: transparent;"
            f" border: 1px solid transparent; border-radius: 8px;"
            f" padding-left: {pad}px; color: {t.text_secondary}; {font_css('body')} }}"
            f"#FooterItem:hover {{ background-color: {t.hover}; }}"
            f"#FooterItem:disabled {{ color: {t.text_disabled}; }}"
            f"#WorkerCard {{ background-color: {t.surface};"
            f" border: 1px solid {t.border}; border-radius: 8px; }}"
            f"#WorkerCard QLabel {{ background: transparent; }}"
            f"#WorkerAvatar {{ background-color: {t.surface_raised};"
            f" border: 1px solid {t.border_strong}; border-radius: 16px;"
            f" color: {t.text}; {font_css('caption', bold=True)} }}"
            f"#WorkerName {{ color: {t.text}; {font_css('body', bold=True)} }}"
            f"#WorkerLink {{ background: transparent; border: none; padding: 0;"
            f" min-height: 0; text-align: left; text-decoration: underline;"
            f" color: {t.text_secondary}; {font_css('caption')} }}"
            f"#WorkerLink:hover {{ color: {t.text}; }}"
            f"#WorkerRailButton {{ background-color: {t.surface};"
            f" border: 1px solid {t.border_strong}; border-radius: 16px;"
            f" color: {t.text}; {font_css('caption', bold=True)} }}"
            f"#ThemeSegment {{ background-color: {t.surface_sunken};"
            f" border: 1px solid {t.border}; border-radius: 8px; }}"
            f"#ThemeSegment QToolButton {{ background-color: transparent;"
            f" border: 1px solid transparent; border-radius: 6px;"
            f" color: {t.text_secondary}; {font_css('caption')} }}"
            f"#ThemeSegment QToolButton:checked {{ background-color: {t.surface};"
            f" border: 1px solid {t.border_subtle}; color: {t.text};"
            f" font-weight: bold; }}"
        )
        self.mark.setPixmap(icon("package", color=t.on_accent).pixmap(18, 18))
        self.sku_button.setIcon(icon("tag"))
        self.light_button.setIcon(icon("sun"))
        self.dark_button.setIcon(icon("moon"))
        self.connection_icon.setIcon(icon("server"))
        self.set_theme_name(t.name)
        self._style_connection(t)

    def _style_connection(self, t) -> None:
        _label, role = _CONNECTION[self._state]
        # No status_warning_dot token: the mockup's amber is under the 3:1
        # floor on this plane (spec section 7, departure 3).
        dot = getattr(t, f"status_{role}_dot", None) or getattr(t, f"status_{role}")
        colour = getattr(t, f"status_{role}")
        fill = "transparent" if self._state == "ok" else getattr(t, f"status_{role}_bg")
        edge = t.status_danger_border if self._state == "down" else "transparent"
        for d in (self.connection_dot, self.connection_icon_dot):
            d.setStyleSheet(f"background-color: {dot}; border-radius: 5px;")
        self.connection_box.setStyleSheet(
            f"#ConnectionBox {{ background-color: {fill}; border: 1px solid {edge};"
            f" border-radius: 8px; }}"
            f"#ConnectionBox QLabel {{ background: transparent; }}"
        )
        self.connection_icon.setStyleSheet(
            f"#ConnectionIcon {{ background-color: {fill}; border: none;"
            f" border-radius: 8px; }}"
        )
        self.connection_label.setStyleSheet(
            f"color: {colour}; {font_css('caption', bold=True)}"
        )
        self.path_label.setStyleSheet(
            f"color: {t.text_secondary}; font-family: {t.font_family_mono};"
            f" {font_css('caption')}"
        )
        self.retry_button.setStyleSheet(
            f"#RetryButton {{ background-color: {t.surface}; color: {t.text};"
            f" border: 1px solid {t.status_danger_border}; border-radius: 8px;"
            f" padding: 0 12px; {font_css('body', bold=True)} }}"
        )
```

Note on `set_client_chosen`: it reads `self.rail._buttons` for the count. That is a private attribute of `shared`'s `NavRail`; `NavRail` has no public count. Keep it, and the test `test_no_client_disables_the_destinations_and_sku_mapping` covers it.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sidebar.py`
Expected: all pass. Likely first-run failures and their fixes:
- item height not 44: `NavRail.set_expanded` calls `self._shape(button)` for each button, so the override must be reached; check the method name against `shared/navrail.py`.
- `t.font_family_mono` missing: `shared.theme.current_tokens()` returns tokens without the bundled family. If the attribute is absent, read tokens through `gui.theme.current_tokens()` in `set_expanded`/`set_connection` instead (it layers the family; `on_theme_changed` already passes full tokens).
- a tooltip assertion with `\\`: the test uses raw strings; compare with `repr()` if confused.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check . --exclude shared
/usr/bin/git add gui/components tests/test_sidebar.py
/usr/bin/git commit -F <message file>
```

Message: `feat(shell): Sidebar with floor-height destinations, worker, theme and connection card`.

---

### Task 4: `ConnectionBanner`

**Files:**
- Create: `gui/components/connection_banner.py`
- Test: `tests/test_connection_banner.py`

**Interfaces:**
- Produces: `class ConnectionBanner(QFrame)` with signal `retryRequested()`, method `set_outage(server_path: str, since: str)`, and attributes `title_label`, `message_label`, `retry_button`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_connection_banner.py`:

```python
"""The page banner an outage raises (spec 2026-10-08 section 6.5, frame 2e)."""

import pytest

from gui.components.connection_banner import ConnectionBanner
from shared import theme as shared_theme
from shared.theme import current_theme_name, current_tokens, set_current


@pytest.fixture
def banner(qapp):
    widget = ConnectionBanner()
    yield widget
    widget.deleteLater()


def test_it_says_which_server_since_when_and_what_is_blocked(banner):
    banner.set_outage(r"\\fs01\packer", "14:02")
    assert banner.title_label.text() == "Server unreachable"
    text = banner.message_label.text()
    assert r"\\fs01\packer" in text
    assert "stopped answering at" in text and "14:02" in text
    assert "Sessions cannot be opened or ended until it answers." in text


def test_a_path_with_markup_characters_is_shown_literally(banner):
    banner.set_outage(r"\\fs01\<share>&co", "09:00")
    assert "&lt;share&gt;&amp;co" in banner.message_label.text()


def test_retry_emits(banner, qtbot):
    with qtbot.waitSignal(banner.retryRequested, timeout=500):
        banner.retry_button.click()
    assert banner.retry_button.text() == "Retry"
    assert banner.retry_button.height() == 44


def test_it_wears_the_danger_plane_in_both_themes(banner):
    before = current_theme_name()
    set_current("dark" if before == "light" else "light")
    try:
        tokens = current_tokens()
        assert tokens.status_danger_bg in banner.styleSheet()
        assert tokens.status_danger_border in banner.styleSheet()
    finally:
        shared_theme._current = before
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_connection_banner.py`
Expected: `ModuleNotFoundError: No module named 'gui.components.connection_banner'`.

- [ ] **Step 3: Write the component**

Create `gui/components/connection_banner.py`:

```python
"""The banner above the page while the server is unreachable.

Spec docs/superpowers/specs/2026-10-08-ui-refresh-phase1-shell-design.md
section 6.5, mockup frame 2e. Qt for now: the pages under it are Qt until
phases 3-5, when each web page draws its own from the kit.
"""

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from shared.icons import icon
from shared.theme import font_css, on_theme_changed


class ConnectionBanner(QFrame):
    retryRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionBanner")

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(14)

        self.glyph = QLabel(self)
        self.glyph.setFixedSize(24, 24)
        row.addWidget(self.glyph, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = QLabel("Server unreachable", self)
        self.title_label.setObjectName("BannerTitle")
        self.message_label = QLabel(self)
        self.message_label.setObjectName("BannerMessage")
        self.message_label.setTextFormat(Qt.RichText)
        self.message_label.setWordWrap(True)
        text.addWidget(self.title_label)
        text.addWidget(self.message_label)
        row.addLayout(text, 1)

        self.retry_button = QPushButton("Retry", self)
        self.retry_button.setFixedHeight(44)
        self.retry_button.clicked.connect(self.retryRequested.emit)
        row.addWidget(self.retry_button, 0, Qt.AlignVCenter)

        self._path = ""
        self._since = ""
        on_theme_changed(self, self._apply_theme)

    def set_outage(self, server_path: str, since: str) -> None:
        self._path, self._since = server_path, since
        self._write_message()

    def _write_message(self) -> None:
        mono = self._mono
        self.message_label.setText(
            f'<span style="font-family: {mono};">{escape(self._path)}</span>'
            f" stopped answering at"
            f' <span style="font-family: {mono};">{escape(self._since)}</span>.'
            " Sessions cannot be opened or ended until it answers."
        )

    def _apply_theme(self, t) -> None:
        self._mono = t.font_family_mono
        self.setStyleSheet(
            f"#ConnectionBanner {{ background-color: {t.status_danger_bg};"
            f" border: 1px solid {t.status_danger_border}; border-radius: 12px; }}"
            f"#ConnectionBanner QLabel {{ background: transparent; }}"
            f"#BannerTitle {{ color: {t.status_danger}; {font_css('body', bold=True)} }}"
            f"#BannerMessage {{ color: {t.text}; {font_css('body')} }}"
        )
        self.glyph.setPixmap(icon("circle-alert", color=t.status_danger).pixmap(24, 24))
        self._write_message()
```

`_mono` is set by `_apply_theme`, which `on_theme_changed` calls at once in the constructor, before `set_outage` can run. `font-family` in the rich-text span is a font name, not a colour or a size, so the style lint allows it; if `tests/test_style_literals_guard.py` objects, wrap the two mono fragments in `<code>…</code>` instead and drop the inline style.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_connection_banner.py tests/test_style_literals_guard.py`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check . --exclude shared
/usr/bin/git add gui/components/connection_banner.py tests/test_connection_banner.py
/usr/bin/git commit -F <message file>
```

Message: `feat(shell): ConnectionBanner for an unreachable server`.

---

### Task 5: Command bar to the mockup

**Files:**
- Modify: `gui/command_bar.py` (whole file)
- Modify: `tests/test_command_bar.py` (whole file), `tests/test_packing_density.py`

**Interfaces:**
- Produces, on `CommandBar`: attributes `sidebar_button`, `client_combo`, `session_label`, `filter_input`, `open_session_button`, `start_packing_button`, `end_session_button`, `end_shortcut_label`, `overflow`, `overflow_button`; signal `sidebarToggled()`; methods `set_page(name)`, `set_session(session_id | None)`, `set_client_chosen(bool)`, `set_server_reachable(bool)`, `set_sidebar_expanded(bool)`. **No `sku_mapping_button`.** `bar_css(tokens, selector)` and `BAR_HEIGHT`, `PAGES` keep their names.
- `CommandBar` decides whether *Open session* and *End session* are enabled (client chosen, server reachable, session open). `MainWindow` keeps deciding *Start packing*.

- [ ] **Step 1: Rewrite the tests**

Replace `tests/test_command_bar.py` with:

```python
"""The 60px bar above the pages (spec 2026-10-08 section 6.3, frames 2a-2e).

Visibility is read with isHidden(): the bar is never shown in these tests, so
isVisible() is False for everything.
"""

import pytest

from gui.command_bar import BAR_HEIGHT, PAGES, CommandBar
from shared import theme as shared_theme
from shared.theme import current_theme_name, current_tokens, set_current


@pytest.fixture
def bar(qapp):
    widget = CommandBar()
    widget.set_client_chosen(True)
    yield widget
    widget.deleteLater()


def _shown_primaries(bar):
    buttons = (bar.open_session_button, bar.start_packing_button, bar.end_session_button)
    return [b.text() for b in buttons
            if not b.isHidden() and b.property("role") == "primary"]


def test_the_bar_is_floor_height(bar):
    assert bar.height() == BAR_HEIGHT == 60


def test_the_controls_run_in_the_mockups_order(bar):
    layout = bar.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    order = [w for w in order if w is not None]
    assert order == [
        bar.sidebar_button, bar.client_combo, bar.session_label, bar.filter_input,
        bar.open_session_button, bar.start_packing_button, bar.end_session_button,
        bar.overflow_button,
    ]


def test_there_is_no_sku_mapping_button(bar):
    """It moved to the sidebar footer."""
    assert not hasattr(bar, "sku_mapping_button")


def test_the_client_selector_is_250_wide_with_a_placeholder(bar):
    assert bar.client_combo.width() == 250
    assert bar.client_combo.placeholderText() == "Choose a client"


def test_no_session_offers_open_session_as_the_one_primary(bar):
    bar.set_page("packing")
    bar.set_session(None)
    assert _shown_primaries(bar) == ["Open session"]
    assert bar.session_label.isHidden()
    assert not bar.filter_input.isEnabled()
    assert bar.end_session_button.isHidden() and bar.start_packing_button.isHidden()


def test_a_session_offers_start_packing_as_the_one_primary(bar):
    bar.set_page("packing")
    bar.set_session("2026-09-01_1042")
    assert _shown_primaries(bar) == ["Start packing"]
    assert bar.session_label.text() == "2026-09-01_1042"
    assert not bar.session_label.isHidden()
    assert bar.filter_input.isEnabled()
    assert bar.open_session_button.isHidden()
    assert not bar.end_session_button.isHidden()
    assert bar.end_session_button.property("role") == "secondary"
    assert bar.end_shortcut_label.text() == "Ctrl+E"
    assert bar.start_packing_button.toolTip() == "Start packing · opens Packer Mode"


@pytest.mark.parametrize("page", ["statistics", "browser"])
def test_other_pages_carry_no_packing_actions(bar, page):
    bar.set_session("2026-09-01_1042")
    bar.set_page(page)
    assert _shown_primaries(bar) == []
    assert bar.filter_input.isHidden()
    assert bar.end_session_button.isHidden()


@pytest.mark.parametrize("page", PAGES)
def test_the_session_id_shows_on_every_page_while_a_session_is_open(bar, page):
    bar.set_session("2026-09-01_1042")
    bar.set_page(page)
    assert not bar.session_label.isHidden()
    bar.set_session(None)
    assert bar.session_label.isHidden()


@pytest.mark.parametrize("page", PAGES)
def test_toggle_client_picker_and_overflow_are_on_every_page(bar, page):
    bar.set_page(page)
    assert not bar.sidebar_button.isHidden()
    assert not bar.client_combo.isHidden()
    assert not bar.overflow_button.isHidden()


def test_the_filter_shrinks_before_it_is_cut_off(bar):
    assert bar.filter_input.minimumWidth() == 170
    assert bar.filter_input.maximumWidth() == 300


def test_open_session_is_disabled_without_a_client_and_says_why(bar):
    bar.set_client_chosen(False)
    assert not bar.open_session_button.isEnabled()
    assert bar.open_session_button.toolTip() == "Open session · choose a client first"
    bar.set_client_chosen(True)
    assert bar.open_session_button.isEnabled()
    assert bar.open_session_button.toolTip() == "Open session"


def test_an_unreachable_server_disables_open_and_end_and_says_why(bar):
    bar.set_server_reachable(False)
    assert not bar.open_session_button.isEnabled()
    assert bar.open_session_button.toolTip() == "Open session · server unreachable"
    bar.set_session("2026-09-01_1042")
    assert not bar.end_session_button.isEnabled()
    assert bar.end_session_button.toolTip() == "End session · server unreachable"
    bar.set_server_reachable(True)
    assert bar.end_session_button.isEnabled()
    assert bar.end_session_button.toolTip() == "End the current packing session"


def test_end_session_is_never_enabled_without_a_session(bar):
    bar.set_session(None)
    assert not bar.end_session_button.isEnabled()


def test_the_sidebar_button_emits_and_names_what_it_will_do(bar, qtbot):
    assert bar.sidebar_button.toolTip() == "Collapse sidebar"
    with qtbot.waitSignal(bar.sidebarToggled, timeout=500):
        bar.sidebar_button.click()
    bar.set_sidebar_expanded(False)
    assert bar.sidebar_button.toolTip() == "Expand sidebar"


def test_an_unknown_page_fails_loudly(bar):
    with pytest.raises(KeyError):
        bar.set_page("stats")


def test_the_bar_sits_on_the_frame_plane_and_repaints_on_a_theme_switch(bar):
    before = current_theme_name()
    set_current("dark" if before == "light" else "light")
    try:
        tokens = current_tokens()
        assert f"background-color: {tokens.surface_sunken}" in bar.styleSheet()
    finally:
        # Put back exactly what was there: set_current() cannot express "no
        # theme applied yet", and leaving "light" behind broke a later test.
        shared_theme._current = before
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_command_bar.py`
Expected: failures such as `AttributeError: 'CommandBar' object has no attribute 'set_client_chosen'`.

- [ ] **Step 3: Rewrite `gui/command_bar.py`**

```python
"""The 60px bar above Packer Assistant's pages.

UI refresh phase 1, spec docs/superpowers/specs/2026-10-08-ui-refresh-phase1-shell-design.md
section 6.3, following docs/design/ui-refresh/mockups/Packer App.html frames
2a-2e.

Packer Assistant's own, not Fulfilment's CommandBar: that one carries client
groups, recent sessions and a stock chip this app has no use for. It holds
widgets and no application state -- MainWindow connects them and tells the bar
which page and session it is showing, whether a client is chosen and whether
the server answers.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QWidget,
)

from shared.components.overflow import OverflowMenu, overflow_button
from shared.icons import icon
from shared.theme import font_css, on_theme_changed, set_button_role

BAR_HEIGHT = 60
PAGES = ("packing", "statistics", "browser")
_CLIENT_WIDTH = 250
_FILTER_MIN, _FILTER_MAX = 170, 300
_END_TIP = "End the current packing session"


def bar_css(tokens, selector: str = "CommandBar") -> str:
    """The 60px bar's ground, its bottom border and its session label.

    Packer Mode builds its own bar rather than becoming a fourth page of this
    one -- it wants none of the client combo, filter or buttons above. What
    the two bars share is this rule set, so it has one definition and takes
    the selector it paints. Type-scoped: a bare rule would repaint every
    child button.
    """
    return (
        f"{selector} {{ background-color: {tokens.surface_sunken};"
        f" border-bottom: 1px solid {tokens.border_subtle}; }}"
        f" QLabel#cmdbarSession {{ {font_css('body')} background: transparent;"
        f" font-family: {tokens.font_family_mono}; color: {tokens.text}; }}"
    )


class CommandBar(QWidget):
    sidebarToggled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A plain QWidget subclass ignores a background rule without this.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(BAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self.sidebar_button = QToolButton(self)
        self.sidebar_button.setObjectName("cmdbarSidebarToggle")
        self.sidebar_button.setAutoRaise(True)
        self.sidebar_button.setFixedSize(44, 44)
        self.sidebar_button.clicked.connect(self.sidebarToggled.emit)
        layout.addWidget(self.sidebar_button)

        self.client_combo = QComboBox(self)
        self.client_combo.setFixedWidth(_CLIENT_WIDTH)
        self.client_combo.setPlaceholderText("Choose a client")
        self.client_combo.setToolTip("Client")
        layout.addWidget(self.client_combo)

        self.session_label = QLabel("", self)
        self.session_label.setObjectName("cmdbarSession")
        layout.addWidget(self.session_label)

        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText("Filter orders")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setMinimumWidth(_FILTER_MIN)
        self.filter_input.setMaximumWidth(_FILTER_MAX)
        # 100 against the spacer's 1: the filter takes the room up to its
        # maximum before the spacer gets any.
        layout.addWidget(self.filter_input, 100)

        layout.addStretch(1)

        self.open_session_button = QPushButton("Open session", self)
        set_button_role(self.open_session_button, "primary")
        self.start_packing_button = QPushButton("Start packing", self)
        set_button_role(self.start_packing_button, "primary")
        self.start_packing_button.setToolTip("Start packing · opens Packer Mode")
        self.end_session_button = QPushButton("End session", self)
        set_button_role(self.end_session_button, "secondary")
        for button in (
            self.open_session_button,
            self.start_packing_button,
            self.end_session_button,
        ):
            layout.addWidget(button)

        # The shortcut, drawn inside End session at its right edge. A child
        # label, because a QPushButton's text has one font.
        self.end_shortcut_label = QLabel("Ctrl+E", self.end_session_button)
        self.end_shortcut_label.setObjectName("cmdbarKbd")
        self.end_shortcut_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        hint_row = QHBoxLayout(self.end_session_button)
        hint_row.setContentsMargins(0, 0, 14, 0)
        hint_row.addStretch(1)
        hint_row.addWidget(self.end_shortcut_label)

        self.overflow = OverflowMenu(self)
        self.overflow_button = overflow_button(self.overflow, self)
        self.overflow_button.setToolTip("More")
        self.overflow_button.setFixedSize(44, 44)
        layout.addWidget(self.overflow_button)

        self._page = "packing"
        self._has_session = False
        self._client_chosen = False
        self._reachable = True
        self._sidebar_expanded = True
        on_theme_changed(self, self._apply_theme)
        self._refresh()

    def _apply_theme(self, tokens) -> None:
        self._tokens = tokens
        hint_width = QFontMetrics(self.end_shortcut_label.font()).horizontalAdvance(
            "Ctrl+E"
        )
        self.setStyleSheet(
            bar_css(tokens)
            + f" QToolButton#cmdbarSidebarToggle {{ background-color: transparent;"
            f" border: none; border-radius: 8px; }}"
            f" QToolButton#cmdbarSidebarToggle:hover {{"
            f" background-color: {tokens.surface_raised}; }}"
            f" QLabel#cmdbarKbd {{ background: transparent;"
            f" font-family: {tokens.font_family_mono}; {font_css('caption')} }}"
        )
        # Room for the hint: the button's own text stays left of it.
        # Scoped to QPushButton: a bare declaration would reach the child label.
        self.end_session_button.setStyleSheet(
            f"QPushButton {{ text-align: left; padding-right: {hint_width + 28}px; }}"
        )
        self._paint_sidebar_button()
        self._paint_hint()

    def _paint_sidebar_button(self) -> None:
        expanded = self._sidebar_expanded
        self.sidebar_button.setIcon(
            icon("panel-left-close" if expanded else "panel-left-open")
        )
        self.sidebar_button.setToolTip(
            "Collapse sidebar" if expanded else "Expand sidebar"
        )

    def _paint_hint(self) -> None:
        tokens = self._tokens
        colour = (
            tokens.text_secondary
            if self.end_session_button.isEnabled()
            else tokens.text_disabled
        )
        self.end_shortcut_label.setStyleSheet(f"color: {colour};")

    def set_page(self, name: str) -> None:
        if name not in PAGES:
            raise KeyError(f"Unknown page {name!r}; expected one of {PAGES}")
        self._page = name
        self._refresh()

    def set_session(self, session_id: str | None) -> None:
        self._has_session = bool(session_id)
        self.session_label.setText(session_id or "")
        self._refresh()

    def set_client_chosen(self, chosen: bool) -> None:
        self._client_chosen = chosen
        self._refresh()

    def set_server_reachable(self, reachable: bool) -> None:
        self._reachable = reachable
        self._refresh()

    def set_sidebar_expanded(self, expanded: bool) -> None:
        self._sidebar_expanded = expanded
        self._paint_sidebar_button()

    def _refresh(self) -> None:
        packing = self._page == "packing"
        self.session_label.setHidden(not self._has_session)
        self.filter_input.setHidden(not packing)
        self.filter_input.setEnabled(self._has_session)

        self.open_session_button.setHidden(not (packing and not self._has_session))
        self.open_session_button.setEnabled(self._client_chosen and self._reachable)
        if not self._reachable:
            open_tip = "Open session · server unreachable"
        elif not self._client_chosen:
            open_tip = "Open session · choose a client first"
        else:
            open_tip = "Open session"
        self.open_session_button.setToolTip(open_tip)

        for button in (self.start_packing_button, self.end_session_button):
            button.setHidden(not (packing and self._has_session))
        self.end_session_button.setEnabled(self._has_session and self._reachable)
        self.end_session_button.setToolTip(
            _END_TIP if self._reachable else "End session · server unreachable"
        )
        if hasattr(self, "_tokens"):
            self._paint_hint()
```

- [ ] **Step 4: Update `tests/test_packing_density.py`**

`test_both_bars_share_one_definition_of_the_bar` still holds (the selector and the function are unchanged). Add one assertion at its end so the shared ground is pinned:

```python
    assert f"background-color: {tokens.surface_sunken}" in bar_css(tokens)
```

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_command_bar.py tests/test_packing_density.py tests/test_packer_mode_widget.py`
Expected: all pass. `tests/test_shell.py` now fails (it still reads `bar.sku_mapping_button`); Task 6 fixes it. Do not run the whole suite as the gate for this task.

If `test_the_controls_run_in_the_mockups_order` fails because `itemAt(i).widget()` returns the spacer as `None` in an unexpected place, the list comprehension already drops `None`; check the `addWidget` order instead.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check . --exclude shared
/usr/bin/git add gui/command_bar.py tests/test_command_bar.py tests/test_packing_density.py
/usr/bin/git commit -F <message file>
```

Message: `feat(shell): command bar to the mockup (sidebar toggle, 250px client selector, reasons on disabled actions)`. Say in the body that `tests/test_shell.py` is red until the next commit.

---

### Task 6: Mount the shell in `MainWindow`; delete the status bar

**Files:**
- Modify: `gui/main_window.py`, `gui/session_browser/session_browser_widget.py`
- Modify: `tests/test_shell.py`, `tests/test_packing_empty.py`, `tests/test_icon_usage_guard.py` (comment only if it names the 76px rail)
- Delete: `tests/test_rail_labels.py`, `tests/test_navrail_labels_fit.py`

**Interfaces:**
- Consumes: `Sidebar` (Task 3), `CommandBar` (Task 5).
- Produces, on `MainWindow`: `sidebar: Sidebar`; `nav_rail` (alias of `sidebar.rail`, kept so call sites and tests do not churn); `packing_summary_label: QLabel`; `_switch_theme(name: str)`; `_toggle_sidebar()`. On `SessionBrowserWidget`: `count_label: QLabel`. `RAIL_ITEMS` labels become `("Packing", "Statistics", "Sessions")`. Removed: `RAIL_WIDTH`, `sku_mapping_button`, `_init_status_bar`, `_sync_status_bar_to_page`, `sb_session_label`, `sb_worker_label`, `sb_summary_label`, `sb_browser_label`.

- [ ] **Step 1: Update the tests first**

Delete the two rail-label test files (their premise, a narrow rail that needs short labels, is gone):

```bash
/usr/bin/git rm tests/test_rail_labels.py tests/test_navrail_labels_fit.py
```

In `tests/test_shell.py`:

1. Add imports at the top: `from PySide6.QtCore import QSettings` and `from PySide6.QtWidgets import QStatusBar, QTabWidget` (replace the existing `QTabWidget` import line).

2. Replace `test_the_bar_carries_the_session_actions` with:

```python
def test_the_bar_carries_the_session_actions(window):
    bar = window.command_bar
    assert window.packer_mode_button is bar.start_packing_button
    assert window.toolbar_end_btn is bar.end_session_button
    assert not hasattr(window, "sku_mapping_button")
```

3. Replace `test_the_old_menu_actions_live_in_the_overflow` with:

```python
def test_the_overflow_keeps_only_server_connection_and_exit(window):
    """Worker, SKU mapping and the theme moved to the sidebar footer."""
    labels = [a.text() for a in window.command_bar.overflow.actions() if a.text()]
    assert labels == ["Server connection…", "Exit"]


def test_the_sidebar_footer_reaches_what_the_overflow_used_to(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "open_sku_mapping_dialog", lambda: calls.append("sku"))
    monkeypatch.setattr(window, "_select_worker", lambda: calls.append("worker"))
    monkeypatch.setattr(window, "_switch_theme", lambda name: calls.append(name))
    window.sidebar.skuMappingRequested.emit()
    window.sidebar.switchWorkerRequested.emit()
    window.sidebar.themeRequested.emit("dark")
    assert calls == ["sku", "worker", "dark"]
```

Note: Qt connects a signal to the bound method object at connect time, so `monkeypatch.setattr(window, ...)` after construction is only seen if the connection goes through a lambda. Step 3 below connects all three with lambdas for exactly this reason.

4. Replace `test_the_bar_follows_the_page` with:

```python
def test_the_bar_follows_the_page(window):
    window.session_tabs.setCurrentIndex(PAGE_BROWSER)
    assert window.command_bar.filter_input.isHidden()
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    assert not window.command_bar.filter_input.isHidden()
```

5. Replace `test_the_status_bar_is_the_artboards_strip` and `test_sku_mapping_is_reachable_without_a_session` with:

```python
def test_there_is_no_status_bar(window):
    """ADR 0002. findChild, not statusBar(): statusBar() creates one."""
    assert window.findChild(QStatusBar) is None
    for name in ("sb_session_label", "sb_worker_label", "sb_summary_label",
                 "sb_browser_label"):
        assert not hasattr(window, name)


def test_the_worker_is_in_the_sidebar_footer(window):
    assert window.sidebar.worker_name.toolTip() == window.current_worker_name


def test_the_destinations_are_the_mockups_three(window):
    assert [label for _i, label, _t in RAIL_ITEMS] == ["Packing", "Statistics", "Sessions"]
    tips = [window.nav_rail.button(i).toolTip() for i in range(3)]
    assert tips == ["Packing  Ctrl+1", "Statistics  Ctrl+2", "Sessions  Ctrl+3"]
    assert window.nav_rail is window.sidebar.rail


def test_the_collapse_button_collapses_and_the_choice_is_remembered(window):
    settings = QSettings("PackingTool", "Shell")
    assert window.sidebar.is_expanded()
    window.command_bar.sidebar_button.click()
    try:
        assert not window.sidebar.is_expanded()
        assert window.command_bar.sidebar_button.toolTip() == "Expand sidebar"
        assert settings.value("sidebar_expanded", True, type=bool) is False
    finally:
        window.command_bar.sidebar_button.click()
    assert window.sidebar.is_expanded()
    assert settings.value("sidebar_expanded", True, type=bool) is True


def test_the_window_is_designed_for_1366_by_768(window):
    assert (window.minimumWidth(), window.minimumHeight()) == (1280, 680)
```

6. In `test_ending_a_session_clears_the_session_tooltip`, replace its last three assertions with:

```python
    assert window.command_bar.session_label.text() == ""
    assert window.command_bar.session_label.toolTip() == ""
```

In `tests/test_packing_empty.py`, replace `test_each_page_shows_only_its_own_status_bar_sentence` with:

```python
def test_the_order_summary_sits_above_the_tree(main_window_with_list):
    """The status bar's sentence, on its own page until phase 3's totals strip."""
    window = main_window_with_list
    assert window.packing_summary_label.text() == "2 orders · 0 packed · 0 in progress"
    assert not window.packing_summary_label.isHidden()


def test_no_list_means_no_summary_line(main_window):
    assert main_window.packing_summary_label.isHidden()


def test_the_session_count_sits_in_the_sessions_top_row(main_window):
    browser = main_window.session_browser
    browser.sessions_shown.emit(12, 40)
    assert browser.count_label.text() == "12 of 40 sessions"
```

The Ctrl+1/2/3 shortcuts and the remembered-collapse-at-startup test need a client and go in Task 7.

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shell.py tests/test_packing_empty.py`
Expected: failures, the first being `AttributeError` on `window.command_bar.sku_mapping_button` inside `MainWindow._init_ui`.

- [ ] **Step 3: Edit `gui/main_window.py`**

**3a. Imports.** Add `from gui.components.sidebar import Sidebar`. Change `from gui.theme import current_tokens, toggle_theme` to `from gui.theme import apply_theme, current_tokens`. Remove `from shared.navrail import NavRail`. After the edits below, remove whatever `shared.theme` or Qt names ruff reports unused (`theme_notifier` is still used).

**3b. Module constants.** Replace the block from the comment `# Wider than Depot's 56px …` through the end of `RAIL_ITEMS` with:

```python
# (icon name, sidebar label, tooltip) per destination, in sidebar order. The
# tooltip names the shortcut, as the mockup's does.
RAIL_ITEMS = (
    ("clipboard-list", "Packing", "Packing  Ctrl+1"),
    ("table", "Statistics", "Statistics  Ctrl+2"),
    ("folder-open", "Sessions", "Sessions  Ctrl+3"),
)
```

Keep `PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER = range(len(RAIL_ITEMS))`. In `order_summary`'s docstring change "The status bar's right-hand text (artboard T1)." to "The Packing page's summary line."

**3c. First-run size.** In `__init__`, change `self.resize(1024, 768)` to `self.resize(1366, 768)`.

**3d. `_init_ui`, the shell.** Replace

```python
        self.nav_rail = NavRail(width=RAIL_WIDTH)
        shell.addWidget(self.nav_rail)
```

with

```python
        self.sidebar = Sidebar()
        shell.addWidget(self.sidebar)
        # Alias: the call sites and tests that drive the pages speak this name.
        self.nav_rail = self.sidebar.rail
```

Replace `self.setMinimumSize(900, 600)` and its comment with:

```python
        # Designed for 1366x768 (ADR 0002). The minimum is under that because a
        # maximised window on such a screen loses the taskbar and title bar.
        self.setMinimumSize(1280, 680)
```

Delete the four lines that alias and wire `self.sku_mapping_button` (`self.sku_mapping_button = …`, its `setToolTip`, its `clicked.connect`). Delete the two `setToolTip` calls on `packer_mode_button` and `toolbar_end_btn`: the bar owns those tooltips now.

**3e. `_init_ui`, the Packing page.** Replace

```python
        self._setup_order_tree()
        self.order_tree_card = Card(margins=(0, 0, 0, 0))
```

with

```python
        # The status bar's "38 of 120 orders complete", on its own page until
        # phase 3 draws the mockup's totals strip.
        self.packing_summary_label = QLabel("")
        self.packing_summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.packing_summary_label.setContentsMargins(0, 4, 12, 0)
        on_theme_changed(
            self.packing_summary_label,
            lambda tokens: self.packing_summary_label.setStyleSheet(
                f"{font_css('caption')} color: {tokens.text_secondary};"
            ),
        )
        self.packing_summary_label.setVisible(False)
        packing_layout.addWidget(self.packing_summary_label)

        self._setup_order_tree()
        self.order_tree_card = Card(margins=(0, 0, 0, 0))
```

**3f. `_init_ui`, the Sessions page.** Delete the `self.session_browser.sessions_shown.connect(lambda shown, total: self.sb_browser_label.setText(…))` statement (five lines). The browser draws its own count (step 4).

**3g. `_init_ui`, destinations and wiring.** Replace the `for icon_name, label, tip in RAIL_ITEMS:` loop and keep the two-way binding below it. The loop is unchanged in shape:

```python
        for icon_name, label, tip in RAIL_ITEMS:
            index = self.nav_rail.add_item(icon(icon_name), label)
            self.nav_rail.button(index).setToolTip(tip)
```

Delete the line `self.session_tabs.currentChanged.connect(self._sync_status_bar_to_page)`.

After `theme_notifier.changed.connect(self._refresh_rail_icons)` add:

```python
        # Lambdas, so a test (or a subclass) that replaces the handler is seen.
        self.sidebar.skuMappingRequested.connect(lambda: self.open_sku_mapping_dialog())
        self.sidebar.switchWorkerRequested.connect(lambda: self._select_worker())
        self.sidebar.themeRequested.connect(lambda name: self._switch_theme(name))
        self.sidebar.set_worker(self.current_worker_name or "")
        self.command_bar.sidebarToggled.connect(self._toggle_sidebar)
        self._shell_settings = QSettings("PackingTool", "Shell")
        self._set_sidebar_expanded(
            self._shell_settings.value("sidebar_expanded", True, type=bool)
        )
```

At the end of `_init_ui`, delete the call `self._init_status_bar()`.

**3h. New methods**, next to `_refresh_rail_icons`:

```python
    def _toggle_sidebar(self):
        expanded = not self.sidebar.is_expanded()
        self._set_sidebar_expanded(expanded)
        self._shell_settings.setValue("sidebar_expanded", expanded)

    def _set_sidebar_expanded(self, expanded: bool):
        self.sidebar.set_expanded(expanded)
        self.command_bar.set_sidebar_expanded(expanded)

    def _switch_theme(self, name: str):
        """Light or Dark, from the sidebar's segment or its collapsed toggle."""
        if name != current_tokens().name:
            apply_theme(QApplication.instance(), name)
```

Delete the old `_toggle_theme` method.

**3i. `_init_overflow`.** Replace its body with:

```python
        """What is left behind the bar's ⋯ once the sidebar footer has the
        worker, SKU mapping and the theme (spec 2026-10-08 section 6.3)."""
        menu = self.command_bar.overflow
        menu.add_item("Server connection…", self._open_connection_settings)
        menu.addSeparator()
        exit_item = menu.add_item("Exit", self.close)
        # Shown beside the label, as the mockup draws it. The OS closes the
        # window on Alt+F4 either way.
        exit_item.setShortcut(QKeySequence("Alt+F4"))
        exit_item.setShortcutVisibleInContextMenu(True)

        # Through click(), which is a no-op on the disabled no-session button.
        end_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        end_shortcut.activated.connect(lambda: self.toolbar_end_btn.click())
```

**3j. Delete `_init_status_bar` and `_sync_status_bar_to_page`** whole.

**3k. The summary line.** In `_populate_order_tree`, in the early-return branch replace `self.sb_summary_label.setText("")` with:

```python
            self.packing_summary_label.setText("")
            self.packing_summary_label.setVisible(False)
```

and at the method's end replace `self.sb_summary_label.setText(order_summary(…))` with:

```python
        self.packing_summary_label.setText(
            order_summary(
                grouped.ngroups, len(completed_orders), len(in_progress_orders)
            )
        )
        self.packing_summary_label.setVisible(True)
```

In `_teardown_session` replace `self.sb_summary_label.setText("")` with the same two lines as the early-return branch.

**3l. The worker.** In `_select_worker` replace

```python
                    if hasattr(self, "sb_worker_label"):
                        self.sb_worker_label.setText(self.current_worker_name)
```

with

```python
                    if hasattr(self, "sidebar"):
                        self.sidebar.set_worker(self.current_worker_name)
```

**3m. `_show_session`.** Delete its line `self.sb_session_label.setText(session_id or "—")` and change its docstring to `"""The session's id in the bar, and its tooltip, set together."""`. In `enable_packing_mode`'s docstring change "in the command bar and status bar" to "in the command bar".

**3n. End session enabling.** `CommandBar` now decides when *End session* is enabled (session open and server reachable). Delete `self.toolbar_end_btn.setEnabled(False)` in `_init_ui` and in `_teardown_session`, and `self.toolbar_end_btn.setEnabled(True)` in `enable_packing_mode`. Each of those places already calls `_show_session(...)` (or, in `_init_ui`, starts with no session), which reaches `CommandBar.set_session`.

Then search the file for any name this step removed and fix what is left:

```bash
grep -n -E 'sb_|sku_mapping_button|RAIL_WIDTH|_toggle_theme|toggle_theme|statusBar|NavRail' gui/main_window.py
```

Expected: no output except `self.nav_rail` lines.

- [ ] **Step 4: The session count in the Sessions page**

In `gui/session_browser/session_browser_widget.py`, add `QLabel` to the `PySide6.QtWidgets` import and `font_css, on_theme_changed` to an import from `shared.theme` (add the import if the module has none). In `_init_ui`, replace

```python
        top_bar.addWidget(self._auto_refresh_cb)
        top_bar.addStretch()
```

with

```python
        top_bar.addWidget(self._auto_refresh_cb)
        top_bar.addStretch()
        # The status bar's "12 of 40 sessions", here until phase 4 draws the
        # mockup's tab counts.
        self.count_label = QLabel("")
        on_theme_changed(
            self.count_label,
            lambda tokens: self.count_label.setStyleSheet(
                f"{font_css('caption')} color: {tokens.text_secondary};"
            ),
        )
        top_bar.addWidget(self.count_label)
```

In `_connect_signals`, after `self.sessions_list.sessions_shown.connect(self.sessions_shown)` add:

```python
        self.sessions_shown.connect(
            lambda shown, total: self.count_label.setText(f"{shown} of {total} sessions")
        )
```

Change the comment on the `sessions_shown` signal from "forwarded for the status bar" to "forwarded; also drawn in the top row".

- [ ] **Step 5: Run the whole suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Expected: 0 failed. If a test elsewhere reads a removed name, update that test to the new home (the table in spec section 6.4); do not put the name back.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check . --exclude shared
/usr/bin/git add -A gui tests
/usr/bin/git commit -F <message file>
```

Message: `feat(shell): mount the sidebar, cut the overflow, delete the status bar`.

---

### Task 7: No client chosen

**Files:**
- Modify: `gui/main_window.py`, `tests/conftest.py`
- Test: `tests/test_no_client.py` (new)

**Interfaces:**
- Consumes: `Sidebar.set_client_chosen`, `CommandBar.set_client_chosen`.
- Produces, on `MainWindow`: `no_client_panel: StatePanel`, `_sync_client_state()`, and three `QShortcut`s (Ctrl+1/2/3).

- [ ] **Step 1: Keep the `main_window` fixture on a chosen client**

Tests that use the `main_window` fixture create two clients and rely on one being selected at startup. With this task, two clients and nothing remembered means "Choose a client". In `tests/conftest.py`, in the `main_window` fixture, after the two `seed.create_client_profile(...)` lines add:

```python
    # Two clients and nothing remembered would start on "Choose a client"
    # (spec 2026-10-08 section 6.6). These tests want what a PC that has been
    # used before shows: the remembered client, which is the first listed.
    from PySide6.QtCore import QSettings

    QSettings("PackingTool", "ClientSelection").setValue(
        "last_client", seed.get_available_clients()[0]
    )
```

and update the fixture's docstring sentence "MainWindow auto-selects a client at startup (restoring last_client, or whichever get_available_clients() lists first)" to "MainWindow restores the remembered client at startup, and this fixture remembers the first one listed".

- [ ] **Step 2: Write the failing tests**

Create `tests/test_no_client.py`:

```python
"""Frame 2a: no client chosen (spec 2026-10-08 section 6.6)."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence, QShortcut

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS, MainWindow
from packing_tool.profile_manager import ProfileManager


@pytest.fixture
def remembered():
    settings = QSettings("PackingTool", "ClientSelection")
    settings.remove("last_client")
    yield settings
    settings.remove("last_client")


def _window(config_ini, clients):
    seed = ProfileManager(config_path=str(config_ini))
    for client_id in clients:
        seed.create_client_profile(client_id, f"{client_id} name")
    return MainWindow(config_path=str(config_ini))


def _assert_no_client(window):
    assert window.current_client_id is None
    assert window.client_combo.currentIndex() == -1
    assert not window.no_client_panel.isHidden()
    assert window.session_tabs.isHidden()
    assert not any(window.nav_rail.button(i).isEnabled() for i in range(3))
    assert not window.sidebar.sku_button.isEnabled()
    assert not window.command_bar.open_session_button.isEnabled()


def _assert_client(window, client_id):
    assert window.current_client_id == client_id
    assert window.no_client_panel.isHidden()
    assert not window.session_tabs.isHidden()
    assert all(window.nav_rail.button(i).isEnabled() for i in range(3))
    assert window.sidebar.sku_button.isEnabled()
    assert window.command_bar.open_session_button.isEnabled()


def test_two_clients_and_nothing_remembered_starts_on_choose_a_client(
    config_ini, qapp, remembered
):
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        _assert_no_client(window)
        panel = window.no_client_panel
        assert panel.button.text() == "Choose a client"
    finally:
        window.deleteLater()


def test_a_single_client_is_selected(config_ini, qapp, remembered):
    window = _window(config_ini, ["ALPHA"])
    try:
        _assert_client(window, "ALPHA")
    finally:
        window.deleteLater()


def test_a_remembered_client_is_restored(config_ini, qapp, remembered):
    remembered.setValue("last_client", "BETA")
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        _assert_client(window, "BETA")
    finally:
        window.deleteLater()


def test_a_remembered_client_that_no_longer_exists_is_not_restored(
    config_ini, qapp, remembered
):
    remembered.setValue("last_client", "GONE")
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        _assert_no_client(window)
    finally:
        window.deleteLater()


def test_no_clients_at_all_shows_the_panel_without_a_button(config_ini, qapp, remembered):
    window = _window(config_ini, [])
    try:
        assert window.current_client_id is None
        assert not window.no_client_panel.isHidden()
        assert window.no_client_panel.button.isHidden()
    finally:
        window.deleteLater()


def test_choosing_a_client_brings_the_pages_back(config_ini, qapp, remembered):
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        window.client_combo.setCurrentIndex(window.client_combo.findData("BETA"))
        _assert_client(window, "BETA")
    finally:
        window.deleteLater()


def test_the_panels_button_opens_the_selector(config_ini, qapp, remembered, monkeypatch):
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        opened = []
        monkeypatch.setattr(window.client_combo, "showPopup", lambda: opened.append(1))
        window.no_client_panel.button.click()
        assert opened == [1]
    finally:
        window.deleteLater()


def _shortcut(window, keys):
    found = [s for s in window.findChildren(QShortcut) if s.key() == QKeySequence(keys)]
    assert len(found) == 1, keys
    return found[0]


def test_ctrl_1_2_3_switch_pages(main_window):
    _shortcut(main_window, "Ctrl+3").activated.emit()
    assert main_window.session_tabs.currentIndex() == PAGE_BROWSER
    _shortcut(main_window, "Ctrl+2").activated.emit()
    assert main_window.session_tabs.currentIndex() == PAGE_STATISTICS
    _shortcut(main_window, "Ctrl+1").activated.emit()
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING


def test_the_shortcuts_do_nothing_without_a_client(config_ini, qapp, remembered):
    window = _window(config_ini, ["ALPHA", "BETA"])
    try:
        before = window.session_tabs.currentIndex()
        _shortcut(window, "Ctrl+3").activated.emit()
        assert window.session_tabs.currentIndex() == before
    finally:
        window.deleteLater()


def test_a_collapsed_sidebar_is_restored_at_startup(config_ini, qapp, remembered):
    shell = QSettings("PackingTool", "Shell")
    shell.setValue("sidebar_expanded", False)
    try:
        window = _window(config_ini, ["ALPHA"])
        try:
            assert not window.sidebar.is_expanded()
            assert window.command_bar.sidebar_button.toolTip() == "Expand sidebar"
        finally:
            window.deleteLater()
    finally:
        shell.remove("sidebar_expanded")
```

- [ ] **Step 3: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_no_client.py`
Expected: failures on `no_client_panel` (AttributeError) and on the two-client case selecting a client.

- [ ] **Step 4: Edit `gui/main_window.py`**

**4a. The panel.** In `_init_ui`, replace `main_layout.addWidget(self.session_tabs)` with:

```python
        # Frame 2a: with no client chosen the pages give way to this.
        self.no_client_panel = StatePanel(
            "Choose a client to begin",
            "Sessions, packing lists and SKU mapping all belong to one client.",
            action_text="Choose a client",
        )
        self.no_client_panel.button.clicked.connect(
            lambda: self.client_combo.showPopup()
        )
        main_layout.addWidget(self.no_client_panel, 1)
        main_layout.addWidget(self.session_tabs, 1)
```

**4b. The shortcuts.** In `_init_overflow`, after the Ctrl+E shortcut, add:

```python
        for page, _item in enumerate(RAIL_ITEMS):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{page + 1}"), self)
            shortcut.activated.connect(lambda p=page: self._go_to_page(p))
```

and add the method:

```python
    def _go_to_page(self, page: int):
        """Ctrl+1/2/3. Nothing to go to until a client is chosen."""
        if self.current_client_id:
            self.session_tabs.setCurrentIndex(page)
```

**4c. `_sync_client_state`**, next to `on_client_changed`:

```python
    def _sync_client_state(self):
        """Enable or disable what needs a client (spec 2026-10-08 section 6.6)."""
        chosen = bool(self.current_client_id)
        self.sidebar.set_client_chosen(chosen)
        self.command_bar.set_client_chosen(chosen)
        self.no_client_panel.setVisible(not chosen)
        # Nothing to choose from: the selector says "(No clients available)".
        self.no_client_panel.button.setVisible(self.client_combo.isEnabled())
        self.session_tabs.setVisible(chosen)
```

**4d. `load_available_clients`.** Replace the block

```python
            # Restore last selected client
            last_client = self.settings.value("last_client")
            if last_client:
                index = self.client_combo.findData(last_client)
                if index >= 0:
                    self.client_combo.setCurrentIndex(index)
                    logger.info(f"Restored last selected client: {last_client}")
```

with

```python
            # The remembered client; failing that the only one; failing that
            # none, and the packer chooses (spec 2026-10-08 section 6.6).
            last_client = self.settings.value("last_client")
            index = self.client_combo.findData(last_client) if last_client else -1
            if index < 0 and len(clients) == 1:
                index = 0
            self.client_combo.setCurrentIndex(index)
            logger.info(f"Client at startup: {self.client_combo.currentData()}")
```

Change the `finally:` block of that method from

```python
        finally:
            self.client_combo.blockSignals(False)
```

to

```python
        finally:
            self.client_combo.blockSignals(False)
            self._sync_client_state()
```

(`load_available_clients` runs after `_init_ui`, so the sidebar and the panel exist.)

**4e. `on_client_changed`.** In the `if not client_id:` branch add `self._sync_client_state()` before its `return`. At the very end of the method add `self._sync_client_state()`.

- [ ] **Step 5: Run the whole suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Expected: 0 failed. A test that built a `MainWindow` with two clients on its own (not through the `main_window` fixture) and expected a selected client needs the same `last_client` line as Step 1; fix it there.

`tests/test_shell.py`'s `window` fixture has no client at all, so its window shows the panel. Its tests drive `window.session_tabs.setCurrentIndex(...)` directly and read `isHidden()` on bar widgets, which still works with the tab widget hidden.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check . --exclude shared
/usr/bin/git add gui/main_window.py tests/conftest.py tests/test_no_client.py
/usr/bin/git commit -F <message file>
```

Message: `feat(shell): start on "Choose a client" when none is remembered and several exist; Ctrl+1/2/3`.

---

### Task 8: Connection state

**Files:**
- Modify: `gui/main_window.py`
- Test: `tests/test_connection_state.py` (new)

**Interfaces:**
- Consumes: `Sidebar.set_connection(state, path)`, `Sidebar.retryRequested`, `ConnectionBanner.set_outage(path, since)`, `ConnectionBanner.retryRequested`, `CommandBar.set_server_reachable(bool)`, `shared.server_connection.test_path_reachable(path: str, timeout: int) -> bool`.
- Produces, on `MainWindow`: `connection_banner: ConnectionBanner`, `check_connection()`, `_connection_state: str` (`"ok"`, `"checking"`, `"down"`), `_set_connection_state(state: str)`, `_connection_down_since: str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_connection_state.py`:

```python
"""The connection card, the banner and what an outage disables
(spec 2026-10-08 section 6.5, frames 2d and 2e).

The server is checked on Retry and after a failed session action, never on a
timer. test_path_reachable is replaced, so no test waits on a real share.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

import gui.main_window as mw
from shared.components.toast import Toast


@pytest.fixture
def reach(monkeypatch):
    """Whether the fake server answers; count of the checks made."""
    state = {"ok": True, "calls": 0}

    def fake(_path, _timeout=5):
        state["calls"] += 1
        return state["ok"]

    monkeypatch.setattr(mw, "test_path_reachable", fake)
    return state


def _check(window, qtbot):
    window.check_connection()
    qtbot.waitUntil(lambda: window._connection_state != "checking", timeout=3000)


def test_it_starts_connected_with_no_banner(main_window):
    assert main_window._connection_state == "ok"
    assert main_window.connection_banner.isHidden()
    assert main_window.sidebar.connection_label.text() == "Server connected"
    assert main_window.sidebar.path_label.toolTip() == str(
        main_window.profile_manager.base_path
    )


def test_a_check_shows_reconnecting_while_it_runs(main_window, qtbot, reach):
    main_window.check_connection()
    assert main_window._connection_state == "checking"
    assert main_window.sidebar.connection_label.text() == "Reconnecting…"
    assert main_window.connection_banner.isHidden()
    qtbot.waitUntil(lambda: main_window._connection_state == "ok", timeout=3000)


def test_a_failed_check_raises_the_banner_and_disables_session_actions(
    main_window, qtbot, reach
):
    reach["ok"] = False
    _check(main_window, qtbot)
    assert main_window._connection_state == "down"
    assert main_window.sidebar.connection_label.text() == "Server unreachable"
    assert not main_window.connection_banner.isHidden()
    text = main_window.connection_banner.message_label.text()
    assert main_window._connection_down_since in text
    assert len(main_window._connection_down_since) == 5  # HH:MM
    assert not main_window.command_bar.open_session_button.isEnabled()
    assert not main_window.packing_state_panel.button.isEnabled()


def test_retry_recovers_hides_the_banner_and_says_so(main_window, qtbot, reach):
    reach["ok"] = False
    _check(main_window, qtbot)
    reach["ok"] = True
    main_window.connection_banner.retry_button.click()
    qtbot.waitUntil(lambda: main_window._connection_state == "ok", timeout=3000)
    assert main_window.connection_banner.isHidden()
    assert main_window.command_bar.open_session_button.isEnabled()
    assert main_window.packing_state_panel.button.isEnabled()
    shown = Toast.for_window(main_window)
    assert shown is not None and shown.text().startswith("Server connected again · ")


def test_a_check_that_was_never_down_says_nothing(main_window, qtbot, reach):
    existing = Toast.for_window(main_window)
    if existing is not None:
        existing.dismiss()
    _check(main_window, qtbot)
    shown = Toast.for_window(main_window)
    assert shown is None or shown.isHidden()


def test_the_sidebars_retry_runs_a_check(main_window, qtbot, reach):
    reach["ok"] = False
    _check(main_window, qtbot)
    before = reach["calls"]
    main_window.sidebar.retry_button.click()
    qtbot.waitUntil(lambda: main_window._connection_state != "checking", timeout=3000)
    assert reach["calls"] == before + 1


def test_the_time_of_the_outage_is_kept_across_failed_retries(
    main_window, qtbot, reach
):
    reach["ok"] = False
    _check(main_window, qtbot)
    main_window._connection_down_since = "14:02"
    _check(main_window, qtbot)
    assert main_window._connection_down_since == "14:02"


def test_a_second_check_while_one_runs_is_ignored(main_window, qtbot, reach):
    main_window.check_connection()
    main_window.check_connection()
    main_window.check_connection()
    qtbot.waitUntil(lambda: main_window._connection_state != "checking", timeout=3000)
    assert reach["calls"] == 1


def test_a_failed_session_start_checks_the_server(main_window, qtbot, reach):
    reach["ok"] = False
    main_window._cleanup_failed_session_start()
    qtbot.waitUntil(lambda: main_window._connection_state == "down", timeout=3000)
    assert not main_window.connection_banner.isHidden()


def test_starting_from_sessions_is_refused_while_down(
    main_window, qtbot, reach, monkeypatch, tmp_path
):
    reach["ok"] = False
    _check(main_window, qtbot)
    started = []
    monkeypatch.setattr(
        main_window, "start_shopify_packing_session",
        lambda **kwargs: started.append(kwargs) or True,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    main_window._start_or_resume_from_browser(
        "TESTCL", "DHL_Orders", tmp_path, tmp_path / "DHL_Orders.json",
        work_dir=tmp_path,
    )
    assert started == []
    shown = Toast.for_window(main_window)
    assert shown is not None
    assert shown.text() == "Server unreachable. Sessions cannot be opened until it answers."


def test_end_session_is_disabled_while_down(main_window_with_list, qtbot, reach):
    window = main_window_with_list
    window.current_packing_list = "DHL_Orders"
    window.enable_packing_mode()
    assert window.toolbar_end_btn.isEnabled()
    reach["ok"] = False
    _check(window, qtbot)
    assert not window.toolbar_end_btn.isEnabled()
    assert window.packer_mode_button.isEnabled()  # Start packing stays live


def test_a_check_that_outlives_the_window_does_not_raise(config_ini, qapp, reach):
    """The worker thread emits on a QObject that may be gone."""
    import threading

    from packing_tool.profile_manager import ProfileManager

    ProfileManager(config_path=str(config_ini)).create_client_profile("ALPHA", "Alpha")
    window = mw.MainWindow(config_path=str(config_ini))
    errors = []
    monkeypatch_hook = threading.excepthook
    threading.excepthook = lambda args: errors.append(args.exc_value)
    try:
        window.check_connection()
        window.deleteLater()
        qapp.processEvents()
        for thread in threading.enumerate():
            if thread.name == "connection-check":
                thread.join(3)
    finally:
        threading.excepthook = monkeypatch_hook
    assert errors == []
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_connection_state.py`
Expected: `AttributeError: module 'gui.main_window' has no attribute 'test_path_reachable'`.

- [ ] **Step 3: Edit `gui/main_window.py`**

**3a. Imports.** Add `from datetime import datetime` if the module does not already import `datetime` that way (check: `grep -n '^from datetime\|^import datetime' gui/main_window.py`; if it has `import datetime`, use `datetime.datetime.now()` below instead). Add `from gui.components.connection_banner import ConnectionBanner`. Change the `shared.server_connection` import to:

```python
from shared.server_connection import (
    ConnectionSettingsDialog,
    prompt_for_recovery_path,
    test_path_reachable,
)
```

`test_path_reachable` is a production function despite its name; pytest only collects from `tests/`.

**3b. The signal.** Next to `_heartbeat_lost = Signal(str)` in the class body add:

```python
    # Emitted from the connection-check thread; queued to the UI thread.
    _connection_checked = Signal(bool)
```

**3c. State.** In `__init__`, next to `self._heartbeat_lost.connect(self._on_heartbeat_lost)`, add:

```python
        # ok / checking / down (spec 2026-10-08 section 6.5). Checked on Retry
        # and after a failed session action, never on a timer (owner decision).
        self._connection_state = "ok"
        self._connection_was_down = False
        self._connection_down_since = ""
        self._connection_checked.connect(self._on_connection_checked)
```

**3d. The banner.** In `_init_ui`, directly before the `# Frame 2a: with no client chosen …` block added in Task 7, add:

```python
        # Frame 2e. Inset like the page content it sits above. The margins are
        # on a container, so hiding it leaves no gap above the page.
        self.connection_banner = ConnectionBanner()
        self.connection_banner.retryRequested.connect(self.check_connection)
        self._banner_row = QWidget()
        banner_layout = QVBoxLayout(self._banner_row)
        banner_layout.setContentsMargins(24, 20, 24, 0)
        banner_layout.addWidget(self.connection_banner)
        main_layout.addWidget(self._banner_row)
```

At the very end of `_init_ui` (after `self._init_overflow()`; the banner, the Packing state panel and the
sidebar all exist by then) add:

```python
        self.sidebar.retryRequested.connect(self.check_connection)
        self._set_connection_state("ok")
```

**3e. The methods**, next to `_open_connection_settings`:

```python
    def check_connection(self):
        """Ask the server once, off the UI thread (a dead share can block for
        the whole timeout). One check at a time."""
        if self._connection_state == "checking":
            return
        self._connection_was_down = self._connection_state == "down"
        self._set_connection_state("checking")
        path = str(self.profile_manager.base_path)
        timeout = self.profile_manager.connection_timeout

        def run():
            reachable = test_path_reachable(path, timeout)
            try:
                self._connection_checked.emit(reachable)
            except RuntimeError:
                pass  # the window closed while the check ran

        threading.Thread(target=run, name="connection-check", daemon=True).start()

    def _on_connection_checked(self, reachable: bool):
        if reachable:
            self._set_connection_state("ok")
            if self._connection_was_down:
                toast(self, f"Server connected again · {self.profile_manager.base_path}")
            return
        if not self._connection_was_down:
            # The time we found out; when the server stopped is not knowable.
            self._connection_down_since = datetime.now().strftime("%H:%M")
        self._set_connection_state("down")

    def _set_connection_state(self, state: str):
        self._connection_state = state
        path = str(self.profile_manager.base_path)
        down = state == "down"
        self.sidebar.set_connection(state, path)
        if down:
            self.connection_banner.set_outage(path, self._connection_down_since)
        # Both: the tests and the render read the banner, the layout reads the row.
        self.connection_banner.setVisible(down)
        self._banner_row.setVisible(down)
        self.command_bar.set_server_reachable(not down)
        self.packing_state_panel.button.setEnabled(not down)
```

**3f. After a failed session action.** At the end of `_cleanup_failed_session_start` add:

```python
        # A failed start may be the server going away: find out, so the
        # sidebar and the banner say so (spec 2026-10-08 section 6.5).
        self.check_connection()
```

In `end_session`, in the final `except Exception as e:` branch, after `logger.exception("Error during end_session")` add `self.check_connection()`.

**3g. Refuse to open while down.** At the top of `_start_or_resume_from_browser`, before the "One list at a time" check, add:

```python
        if self._connection_state == "down":
            toast(
                self,
                "Server unreachable. Sessions cannot be opened until it answers.",
                role="info",
            )
            return
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_connection_state.py`
Expected: all pass. Notes for likely failures:
- `test_end_session_is_disabled_while_down`: `enable_packing_mode` needs `current_session_path` or `current_packing_list` to produce a session id; the test sets `current_packing_list`. If `toolbar_end_btn` is still disabled after it, read `enable_packing_mode` and set what it reads.
- `test_starting_from_sessions_is_refused_while_down`: the method must return before touching `session_manager`.
- `Toast.for_window(window)` returns the window's one toast or `None`; `Toast.text()` is its message.

Then the whole suite:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Expected: 0 failed. Existing tests that drive a failing session start now also start a check thread; it finds the tmp server reachable and changes nothing.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check . --exclude shared
/usr/bin/git add gui/main_window.py tests/test_connection_state.py
/usr/bin/git commit -F <message file>
```

Message: `feat(shell): connection card and banner; an unreachable server disables Open and End session`.

---

### Task 9: Renders, glossary, final check

**Files:**
- Create: `scripts/render_shell.py`, `docs/design/ui-refresh/renders/phase1/*.png` (12 files)
- Modify: `CONTEXT.md`; `README.md` and `CLAUDE.md` only if they mention the status bar or the 76px rail (`grep -n -i 'status bar\|76px\|rail' README.md CLAUDE.md`)

**Interfaces:**
- Consumes: everything above. Uses `MainWindow._set_connection_state` and `_connection_down_since` to stage frames 2d and 2e.

- [ ] **Step 1: Write the render script**

Create `scripts/render_shell.py`:

```python
"""Offscreen renders of the shell, mockup frames 2a-2e, in both themes.

    .venv/bin/python scripts/render_shell.py [output dir]

Writes <frame>-<theme>.png at 1366x768 and 2b-<theme>-1920.png at 1920x1080,
by default into docs/design/ui-refresh/renders/phase1/. Runs against a
throwaway server with synthetic data and its own QSettings, so it touches
neither the file server nor this PC's saved theme or client.

Offscreen Qt uses a fallback font, not Segoe UI: glyph widths differ a little
from Windows.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

DEFAULT_OUT = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "phase1"
SERVER_LABEL = r"\\fs01\packer"

ORDERS = [
    (f"#104{n:02d}", courier, [
        {"sku": sku, "quantity": qty, "product_name": name},
        {"sku": "LIP-RED", "quantity": 1, "product_name": "Lip balm, red"},
    ])
    for n, (courier, sku, qty, name) in enumerate([
        ("DHL", "CRM-50ML", 2, "Day cream 50 ml"),
        ("DHL", "SER-30ML", 1, "Vitamin C serum 30 ml"),
        ("DPD", "SPF-50", 3, "Sunscreen SPF 50"),
        ("DPD", "LST-07", 2, "Lipstick, shade 07"),
        ("Speedy", "MSK-5PK", 1, "Sheet mask, 5 pack"),
        ("Speedy", "CLN-200", 1, "Gel cleanser 200 ml"),
    ], start=1)
]


def build(tmp: Path):
    from gui.main_window import MainWindow
    from packing_tool.packer_logic import PackerLogic
    from packing_tool.profile_manager import ProfileManager

    server = tmp / "server"
    server.mkdir()
    config = tmp / "config.ini"
    config.write_text(
        "[Network]\n"
        f"FileServerPath = {server}\n"
        "ConnectionTimeout = 5\n"
        f"LocalCachePath = {tmp / 'cache'}\n"
        "[Logging]\nLogLevel = WARNING\nLogRetentionDays = 30\nMaxLogSizeMB = 10\n",
        encoding="utf-8",
    )
    seed = ProfileManager(config_path=str(config))
    seed.create_client_profile("ACME", "Acme Cosmetics")
    seed.create_client_profile("BOREAL", "Boreal Outdoor")

    session_dir = server / "Sessions" / "CLIENT_ACME" / "2026-10-07_1"
    (session_dir / "packing_lists").mkdir(parents=True)
    work_dir = session_dir / "packing" / "Morning_wave"
    work_dir.mkdir(parents=True)
    list_path = session_dir / "packing_lists" / "Morning_wave.json"
    list_path.write_text(json.dumps({
        "list_name": "Morning_wave",
        "created_at": "2026-10-07T08:00:00+00:00",
        "orders": [
            {"order_number": number, "courier": courier, "items": items}
            for number, courier, items in ORDERS
        ],
    }), encoding="utf-8")

    window = MainWindow(skip_worker_selection=True, config_path=str(config))
    window.current_worker_name = "Desislava Ilieva"
    window.sidebar.set_worker(window.current_worker_name)

    def open_session():
        window.client_combo.setCurrentIndex(window.client_combo.findData("ACME"))
        logic = PackerLogic(
            client_id="ACME", profile_manager=window.profile_manager,
            work_dir=str(work_dir),
        )
        logic.load_packing_list_json(list_path)
        window.logic = logic
        window.current_session_path = session_dir
        window.current_packing_list = "Morning_wave"
        window._populate_order_tree()
        window.enable_packing_mode()
        return logic

    return window, open_session


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        # Before any QSettings is made: keep this PC's saved theme and client.
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp / "settings"))

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.theme import apply_theme, load_saved_theme

        load_saved_theme(app)
        window, open_session = build(tmp)
        window.show()
        # The card and the banner show the mockup's path, not the temp folder.
        real_set = window.sidebar.set_connection
        window.sidebar.set_connection = lambda state, _path: real_set(state, SERVER_LABEL)
        real_outage = window.connection_banner.set_outage
        window.connection_banner.set_outage = (
            lambda _path, since: real_outage(SERVER_LABEL, since)
        )

        def shoot(name: str, width: int = 1366, height: int = 768) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                window.resize(width, height)
                app.processEvents()
                app.processEvents()
                target = out / f"{name.format(theme=theme)}.png"
                if not window.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        # 2a: no client.
        window.client_combo.setCurrentIndex(-1)
        window._set_connection_state("ok")
        shoot("2a-{theme}")

        # 2b: session open.
        logic = open_session()
        shoot("2b-{theme}")
        shoot("2b-{theme}-1920", 1920, 1080)

        # 2c: collapsed rail.
        window._set_sidebar_expanded(False)
        shoot("2c-{theme}")
        window._set_sidebar_expanded(True)

        # 2d: reconnecting (in the app this shows only while a check runs).
        window._set_connection_state("checking")
        shoot("2d-{theme}")

        # 2e: server unreachable.
        window._connection_down_since = "14:02"
        window._set_connection_state("down")
        shoot("2e-{theme}")

        logic.close()
        window.logic = None
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

`on_client_changed` refuses a change while `window.logic` is set, so 2a is shot before the session is opened; keep that order. If `PackerLogic`'s constructor or `load_packing_list_json` take other arguments, copy the calls from the `packer_logic_factory` and `main_window_with_list` fixtures in `tests/conftest.py`.

- [ ] **Step 2: Run it**

```bash
.venv/bin/python scripts/render_shell.py
```

Expected: 12 paths printed, 12 PNGs in `docs/design/ui-refresh/renders/phase1/`.

- [ ] **Step 3: Look at every render beside its mockup frame**

Open each PNG with the Read tool. Open the mockup for comparison: render `Packer Screens.html`'s frames with headless Chrome if it is installed (`google-chrome --headless=new --hide-scrollbars --virtual-time-budget=8000 --window-size=1500,6000 --screenshot=/tmp/packer-screens.png "file://$PWD/docs/design/ui-refresh/mockups/Packer Screens.html"`), or unpack `Packer App.html` (the README in `mockups/` has the script) and read the `<nav>` and `<header>` blocks.

Check, in both themes:

| Frame | Must be true |
|---|---|
| all | sidebar 200px (56px in 2c) on the frame plane with a right hairline; header and command bar both 60px, their bottom rules one line; no status bar at the bottom |
| all | sidebar footer, top to bottom: SKU mapping, worker card ("DI", "Desislava Ilieva", *Switch worker…*), Light/Dark segment with the current theme raised, connection card |
| 2a | selector reads "Choose a client"; the three destinations and SKU mapping are greyed and none has the white plane; *Open session* is dashed-disabled; the page is the "Choose a client to begin" panel |
| 2b | Packing has the white plane and a bold label; selector reads "Acme Cosmetics (ACME)"; `2026-10-07_1` in mono; *Filter orders*; *Start packing* filled, *End session* outlined with `Ctrl+E` at its right in mono; `…` button; the summary line above the tree |
| 2b-1920 | nothing stretches oddly: the sidebar is still 200px, the filter stops at 300px |
| 2c | icons centred in the 56px rail; avatar, theme toggle and server glyph with its dot in the footer; the bar's first button shows the "open" glyph |
| 2d | card on the warning tint, "Reconnecting…", no Retry, no banner |
| 2e | card on the danger tint with its edge and a full-width Retry; banner above the page with the path in mono, "stopped answering at 14:02", and Retry; *End session* disabled; *Start packing* still enabled |

Fix what is wrong in the component that draws it, re-run the script, and look again. Typical fixes: a label that paints a `surface` background over a tinted card needs `background: transparent` in that card's sheet; the `Ctrl+E` hint overlapping the button text means `padding-right` on `end_session_button` is too small; a 20px gap above the page in every frame but 2e means `_banner_row` is not being hidden with the banner.

Anything you cannot make match and that is not already in spec section 7: add a row to that table, with the reason.

- [ ] **Step 4: Update `CONTEXT.md`**

Replace the **Command bar** entry with:

```markdown
**Command bar** — the 60px row above a screen, carrying what that screen is and what can be done to it. Above the pages it holds the sidebar toggle, the client selector, the open session's id, the page's actions and the ⋯ overflow menu (Server connection…, Exit); above Packer Mode it holds the order number, scanner capture, Skip order and Exit packing.
```

Add after it:

```markdown
**Sidebar** — the Qt column left of the pages: the app mark, the three destinations (Packing, Statistics, Sessions) and a footer with SKU mapping, the worker, Light/Dark and the connection card. 200px, collapsing to a 56px rail. With no client chosen its destinations are disabled.

**Connection card** — the sidebar footer's statement of whether the file server answers: *Server connected*, *Reconnecting…* (while a check runs) or *Server unreachable* (with Retry). The server is checked on Retry and after a failed session action, never on a timer.

**Connection banner** — the banner above the page while the server is unreachable: which path, since when, and Retry. While it shows, sessions cannot be opened or ended.
```

In the **Session Browser** entry append: ` Its destination in the sidebar is labelled "Sessions".` In the **Toast** entry nothing changes.

- [ ] **Step 5: Final verification**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
.venv/bin/python -c "import main"
graphify update .
/usr/bin/git status --short
```

Expected: 0 failed; ruff clean; the import prints nothing; `git status` shows only the files of this task (and nothing under `shared/`).

- [ ] **Step 6: Commit and push**

```bash
/usr/bin/git add scripts/render_shell.py docs/design/ui-refresh/renders CONTEXT.md
/usr/bin/git commit -F <message file>
/usr/bin/git push
```

Message: `docs(shell): phase 1 renders of frames 2a-2e, render script, glossary`.

The PR (Stage C) must carry: the 12 renders, the departures table from spec section 7 (with any row added in Step 3), and the "For shared/" list from spec section 8.

---

## Self-review notes (for the implementer)

- Spec sections 4, 5, 6.1 to 6.7, 9 and 11 map to Tasks 1, 2, 3 to 8, each task's tests, and Task 9.
- The names used across tasks: `Sidebar.set_connection(state, server_path)` with states `"ok"`, `"checking"`, `"down"`; `CommandBar.set_server_reachable(bool)`, `set_client_chosen(bool)`, `set_sidebar_expanded(bool)`, `sidebarToggled`; `MainWindow.check_connection()`, `_set_connection_state(state)`, `_connection_down_since`, `_sync_client_state()`, `_set_sidebar_expanded(bool)`, `_switch_theme(name)`, `no_client_panel`, `connection_banner`, `packing_summary_label`; `SessionBrowserWidget.count_label`.
- The code in this plan was written against the repo at `f913261` plus Fulfilment `387efef`, and was not run. Where a test and the code here disagree, the spec decides which is right.
