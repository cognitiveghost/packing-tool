# Phase 10 Bundle 3 — Qt foundation Implementation Plan

> **For agentic workers:** Execute in this session with superpowers:executing-plans (the runner forbids subagent fan-out). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the components Packing Tool needs into `shared/components/`, then rebuild Packing Tool's window chrome to match artboard T1/T2: a 60px command bar with an overflow menu, a 40px status bar, and toasts in place of the menu bar, toolbar and message line.

**Architecture:**
- **packing-tool is canonical.** Six Shopify components move into `shared/components/` and lose their `gui.theme_manager` imports. Shopify then syncs `shared/` and deletes its copies.
- **The command bar is not shared** (owner, Q1). Packing Tool gets its own small `gui/command_bar.py` that owns widgets and no state. `MainWindow` aliases its widgets onto the attribute names the existing code already uses, so the 2,400-line window changes only at its edges.

**Tech Stack:** Python 3, PySide6, pytest (offscreen).

**Spec:** `docs/superpowers/specs/2026-09-17-phase10-bundle3-qt-foundation-design.md`. Read it first: E1–E6 and the owner answers Q1–Q5 are the "why" behind every task here.

## Global Constraints

- Two repos, two worktrees, same branch name `worktree-phase10-bundle3`:
  - packing-tool: `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/phase10-bundle3`
  - Shopify: `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/phase10-bundle3`
  - The Shopify branch was created tracking `origin/main`. **Push it with `/usr/bin/git -C <shopify worktree> push -u origin worktree-phase10-bundle3`**, never a bare `git push`.
- Git: call `/usr/bin/git` directly, one command per Bash call, and use `-C <worktree>` for the repo you are not `cd`'d in. Compound shell lines that mention git are refused by the worktree guard.
- Python: packing-tool uses `/home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python`; Shopify uses its worktree's `.venv/bin/python` (a symlink). `python` is not on PATH.
- Test command: `QT_QPA_PLATFORM=offscreen <python> -m pytest …`. Lint: `<python> -m ruff check . --exclude shared`.
- **Never hand-edit Shopify's `shared/`.** Change packing-tool `shared/`, then in the Shopify worktree run `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/phase10-bundle3`.
- No hardcoded colours anywhere. `tests/test_style_literals_guard.py` scans `gui/`, `packing_tool/` and `shared/`. Colours come from `shared.theme` tokens, restyled via `on_theme_changed(widget, apply)`, where `apply(tokens)` runs now and on every theme change.
- One visible primary button per screen (`set_button_role(button, "primary")`).
- Copy is sentence case, exactly as the artboard writes it: "Open session", "Start packing", "SKU mapping", "End session", "Filter orders", "No session".
- `RAIL_WIDTH` stays 76 and `RAIL_ITEMS` labels stay Packing / Statistics / Browse (Q4). Do not touch them.
- After code changes in either repo, run `graphify update .` in that repo.

## File map

packing-tool:
- Create `shared/components/__init__.py`, `card.py`, `state_panel.py`, `toast.py`, `confirm_dialog.py`, `filterbar.py`, `overflow.py` (Task 1)
- Modify `shared/theme.py`: add `apply_dialog_button_roles` (Task 1)
- Create tests `test_components_card.py`, `test_state_panel.py`, `test_components_toast.py`, `test_components_confirm_dialog.py`, `test_components_filterbar.py`, `test_components_overflow.py` (Task 1)
- Modify `gui/theme.py`: floor density; create `tests/test_packing_density.py` (Task 2)
- Create `gui/command_bar.py` and `tests/test_command_bar.py` (Task 3)
- Modify `gui/main_window.py`, `tests/test_shell.py` and `tests/test_screen_primaries.py` (Tasks 4–5)
- Modify `CONTEXT.md` (Task 6)

Shopify: `shared/**` (sync only), `gui/components/__init__.py`, deep-import call sites, `gui/theme_manager.py`, the six moved tests (deleted), `tests/test_components_render_roles.py`, `docs/adr/0001-analysis-results-on-the-web-tier.md` (Task 7).

**Test seams.**
- Component behaviour is tested on the widget alone (Task 1, Task 3).
- The window shell is tested through the module-scoped `window` fixture in `tests/test_shell.py`, which builds a real `MainWindow` against a temp config.
- Pure text logic (`order_summary`) is tested as a plain function.

Do not add tests that drive a full packing session. None exist, and the fixture cost is out of scope.

---

### Task 1: Components move into packing-tool `shared/components/`

**Files:**
- Create: `shared/components/{__init__,card,state_panel,toast,confirm_dialog,filterbar,overflow}.py`
- Modify: `shared/theme.py` (add one function after `set_button_role`, ~line 1065)
- Create: `tests/test_components_card.py`, `tests/test_state_panel.py`, `tests/test_components_toast.py`, `tests/test_components_confirm_dialog.py`, `tests/test_components_filterbar.py`, `tests/test_components_overflow.py`

**Interfaces:**
- Produces:
  - `shared.components` exports `Card`, `StatePanel`, `Toast`, `toast`, `ConfirmDialog`, `FilterBar`, `OverflowMenu`, `overflow_button`, each with the same signatures as Shopify's today.
  - `toast(source: QWidget, text: str, *, role="success"|"info", action_text="", on_action=None) -> Toast`.
  - `OverflowMenu.add_item(text: str, slot) -> QAction`.
  - `overflow_button(menu, parent=None) -> QToolButton`.
  - `shared.theme.apply_dialog_button_roles(box: QDialogButtonBox) -> None`.

- [ ] **Step 1: Copy the tests first (they fail: no module yet)**

Source: `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/phase10-bundle3/tests/`. Copy the six test files above into packing-tool `tests/`, then edit them:
- `from gui.components.<m> import …` → `from shared.components.<m> import …`
- `from gui.theme_manager import TYPE_SCALE` → `from shared.theme import TYPE_SCALE`
- Any `get_theme_manager().toggle_theme()` / `manager.set_theme(x)` (in the toast and filterbar tests) becomes a direct theme switch through `shared.theme.set_current`, restored in `finally`:

```python
from shared.theme import current_theme_name, set_current

before = current_theme_name() or "light"
set_current("dark" if before == "light" else "light")
try:
    ...  # the original assertions
finally:
    set_current(before)
```

If a test depends on a Shopify-only fixture that packing-tool's `tests/conftest.py` lacks (packing has `qapp`), inline the fixture into that test file.

- [ ] **Step 2: Run them to see the import failure**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_components_card.py tests/test_state_panel.py tests/test_components_toast.py tests/test_components_confirm_dialog.py tests/test_components_filterbar.py tests/test_components_overflow.py -q`
Expected: collection errors, `ModuleNotFoundError: No module named 'shared.components'`.

- [ ] **Step 3: Add `apply_dialog_button_roles` to `shared/theme.py`**

Put it directly after `set_button_role`, copied verbatim from Shopify `gui/theme_manager.py:41-53`:

```python
def apply_dialog_button_roles(box) -> None:
    """Mark a dialog's accept button primary. Everything else keeps the default.

    Since the default role became secondary, only the one button that commits the
    dialog needs marking. AcceptRole is Qt's own answer to "which button is that",
    so a Close-only box correctly comes out with no primary at all.
    """
    from PySide6.QtWidgets import QDialogButtonBox

    for button in box.buttons():
        if box.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole:
            set_button_role(button, "primary")
```

- [ ] **Step 4: Copy the six modules and decouple them**

Copy `card.py`, `state_panel.py`, `toast.py`, `confirm_dialog.py`, `filterbar.py` and `overflow.py` from the Shopify worktree's `gui/components/` into `shared/components/`. Then make exactly these edits and nothing else:

| File | Change |
|---|---|
| `card.py` | `from gui.theme_manager import font_css` → `from shared.theme import font_css` |
| `state_panel.py` | `from gui.components.card import Card` → `from shared.components.card import Card` |
| `confirm_dialog.py` | `from gui.theme_manager import apply_dialog_button_roles` + `from shared.theme import font_css` → `from shared.theme import apply_dialog_button_roles, font_css` |
| `filterbar.py` | import → `from shared.theme import current_tokens, font_css, on_theme_changed, set_button_role`; in `__init__` replace the two lines `self._apply_theme()` / `get_theme_manager().theme_changed.connect(self._apply_theme)` with `on_theme_changed(self, lambda _t: self._apply_theme())`; in `_apply_theme` use `theme = current_tokens()` |
| `overflow.py` | drop `from gui.theme_manager import get_theme_manager`; import `current_tokens` from `shared.theme`; both `get_theme_manager().get_current_theme()` → `current_tokens()`. In `overflow_button`'s docstring, delete the `ponytail:` paragraph about `ui_manager._style_results_overflow` (a Shopify file) |
| `toast.py` | none; it already imports only `shared.theme` |

Any docstring line that names a Shopify spec path (`docs/superpowers/specs/2026-09-…phase9…`) gets the prefix `shopify-fulfillment-tool ` so the path stays findable from packing-tool.

`shared/components/__init__.py`:

```python
"""Qt components both apps import.

Canonical here; shopify-fulfillment-tool receives them via scripts/sync_shared.py.
Phase 10 spec D6 / Bundle 3 spec E1.
"""

from shared.components.card import Card
from shared.components.confirm_dialog import ConfirmDialog
from shared.components.filterbar import FilterBar
from shared.components.overflow import OverflowMenu, overflow_button
from shared.components.state_panel import StatePanel
from shared.components.toast import Toast, toast

__all__ = [
    "Card", "ConfirmDialog", "FilterBar", "OverflowMenu", "StatePanel",
    "Toast", "overflow_button", "toast",
]
```

Verify no Shopify import is left: `grep -rn "gui\." shared/components/` must print nothing.

- [ ] **Step 5: Run the moved tests and the guards**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_components_card.py tests/test_state_panel.py tests/test_components_toast.py tests/test_components_confirm_dialog.py tests/test_components_filterbar.py tests/test_components_overflow.py tests/test_style_literals_guard.py -q`
Expected: all pass.

A theme-switch test can fail because a component still reads a stale colour. Fix the component (an `on_theme_changed` it missed); do not weaken the test.

- [ ] **Step 6: Commit**

```
/usr/bin/git add shared/components shared/theme.py tests/test_components_card.py tests/test_state_panel.py tests/test_components_toast.py tests/test_components_confirm_dialog.py tests/test_components_filterbar.py tests/test_components_overflow.py
/usr/bin/git commit -m "Phase 10 Bundle 3: shared components move from Shopify into shared/"
```

(End every commit message with the attribution trailer the session gives you.)

---

### Task 2: Packing Tool runs at floor density

**Files:**
- Modify: `gui/theme.py` (`load_saved_theme`)
- Create: `tests/test_packing_density.py`

**Interfaces:** Produces `gui.theme.PACKING_DENSITY = "floor"`. `load_saved_theme(app)` leaves `shared.theme.get_density() == "floor"`.

- [ ] **Step 1: Failing test**

```python
"""Packing Tool is a scan station: floor density, not Shopify's desk default."""
from gui import theme as packing_theme
from shared import theme as shared_theme


class _MemorySettings:
    def __init__(self, *_args):
        pass

    def value(self, _key, default=None):
        return default

    def setValue(self, _key, _value):
        pass


def test_loading_the_theme_switches_to_floor_density(qapp, monkeypatch):
    monkeypatch.setattr(packing_theme, "QSettings", _MemorySettings)
    before = shared_theme.get_density()
    sheet = qapp.styleSheet()
    shared_theme.set_density("desk")
    try:
        packing_theme.load_saved_theme(qapp)
        assert shared_theme.get_density() == "floor"
    finally:
        shared_theme.set_density(before)
        qapp.setStyleSheet(sheet)
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_packing_density.py -q`
Expected: FAIL, `assert 'desk' == 'floor'`.

- [ ] **Step 3: Implement**

In `gui/theme.py`: add `set_density` to the `shared.theme` import, add `"PACKING_DENSITY"` to `__all__`, and change `load_saved_theme`:

```python
# A station that has not been told otherwise is a scan station (spec E2).
PACKING_DENSITY = "floor"


def load_saved_theme(app: QApplication) -> str:
    # Before apply_theme: build_stylesheet reads the density when it runs.
    set_density(PACKING_DENSITY)
    settings = QSettings("PackingTool", "Theme")
    theme = settings.value("current_theme", THEME_DARK)
    apply_theme(app, theme)
    return theme
```

- [ ] **Step 4: Run it plus the density/type-scale tests**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_packing_density.py tests/test_type_scale.py tests/test_theme.py tests/test_navrail_labels_fit.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/theme.py tests/test_packing_density.py`, then `/usr/bin/git commit -m "Phase 10 Bundle 3: Packing Tool runs at floor density"`.

---

### Task 3: Packing command bar widget

**Files:**
- Create: `gui/command_bar.py`
- Create: `tests/test_command_bar.py`

**Interfaces:**
- Consumes: `shared.components.overflow.OverflowMenu`, `overflow_button` (Task 1).
- Produces: `gui.command_bar.CommandBar(parent=None)` with
  - attributes `client_combo: QComboBox`, `session_label: QLabel`, `filter_input: QLineEdit`, `open_session_button`, `start_packing_button`, `sku_mapping_button`, `end_session_button` (all `QPushButton`), `overflow: OverflowMenu`, `overflow_button: QToolButton`;
  - methods `set_page(name: str)` with `name in PAGES`, and `set_session(session_id: str | None)`;
  - constants `BAR_HEIGHT = 60` and `PAGES = ("packing", "statistics", "browser")`.

- [ ] **Step 1: Failing tests**

`tests/test_command_bar.py`:

```python
"""The Packing command bar: which controls a page shows, and one primary.

Visibility is read with isHidden(): the bar is never shown in these tests, so
isVisible() is False for everything.
"""
import pytest

from gui.command_bar import BAR_HEIGHT, PAGES, CommandBar
from shared.theme import current_theme_name, current_tokens, set_current


@pytest.fixture
def bar(qapp):
    widget = CommandBar()
    yield widget
    widget.deleteLater()


def _shown_primaries(bar):
    buttons = (bar.open_session_button, bar.start_packing_button,
               bar.sku_mapping_button, bar.end_session_button)
    return [b.text() for b in buttons
            if not b.isHidden() and b.property("role") == "primary"]


def test_the_bar_is_floor_height(bar):
    assert bar.height() == BAR_HEIGHT == 60


def test_no_session_offers_open_session_as_the_one_primary(bar):
    bar.set_page("packing")
    bar.set_session(None)
    assert _shown_primaries(bar) == ["Open session"]
    assert bar.session_label.text() == "No session"
    assert not bar.filter_input.isEnabled()
    assert bar.sku_mapping_button.isHidden() and bar.end_session_button.isHidden()


def test_a_session_offers_start_packing_as_the_one_primary(bar):
    bar.set_page("packing")
    bar.set_session("2026-09-01_1042")
    assert _shown_primaries(bar) == ["Start packing"]
    assert bar.session_label.text() == "2026-09-01_1042"
    assert bar.filter_input.isEnabled()
    assert not bar.sku_mapping_button.isHidden()
    assert not bar.end_session_button.isHidden()
    assert bar.end_session_button.property("role") != "danger"


@pytest.mark.parametrize("page", ["statistics", "browser"])
def test_other_pages_carry_no_packing_actions(bar, page):
    bar.set_session("2026-09-01_1042")
    bar.set_page(page)
    assert _shown_primaries(bar) == []
    assert bar.filter_input.isHidden()
    assert bar.sku_mapping_button.isHidden()


def test_the_browser_page_hides_the_session_id(bar):
    bar.set_session("2026-09-01_1042")
    bar.set_page("statistics")
    assert not bar.session_label.isHidden()
    bar.set_page("browser")
    assert bar.session_label.isHidden()


@pytest.mark.parametrize("page", PAGES)
def test_client_picker_and_overflow_are_on_every_page(bar, page):
    bar.set_page(page)
    assert not bar.client_combo.isHidden()
    assert not bar.overflow_button.isHidden()


def test_an_unknown_page_fails_loudly(bar):
    with pytest.raises(KeyError):
        bar.set_page("stats")


def test_the_bar_repaints_on_a_theme_switch(bar):
    before = current_theme_name() or "light"
    set_current("dark" if before == "light" else "light")
    try:
        assert current_tokens().surface_raised in bar.styleSheet()
    finally:
        set_current(before)
```

- [ ] **Step 2: Run them**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_command_bar.py -q`
Expected: collection error, `No module named 'gui.command_bar'`.

- [ ] **Step 3: Implement `gui/command_bar.py`**

```python
"""The 60px bar above Packing Tool's pages (artboard T1/T2).

Packing Tool's own, not Shopify's CommandBar: that one carries client groups,
recent sessions and a stock chip this app has no use for (Bundle 3 spec E4,
owner answer Q1). It holds widgets and no application state -- MainWindow
connects them and tells the bar which page and session it is showing.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from shared.components.overflow import OverflowMenu, overflow_button
from shared.theme import font_css, on_theme_changed, set_button_role

BAR_HEIGHT = 60
PAGES = ("packing", "statistics", "browser")
_CLIENT_WIDTH = 240
_FILTER_WIDTH = 220


class CommandBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A plain QWidget subclass ignores a background rule without this.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(BAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self.client_combo = QComboBox(self)
        self.client_combo.setFixedWidth(_CLIENT_WIDTH)
        layout.addWidget(self.client_combo)

        self.session_label = QLabel("No session", self)
        self.session_label.setObjectName("cmdbarSession")
        layout.addWidget(self.session_label)

        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText("Filter orders")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setFixedWidth(_FILTER_WIDTH)
        layout.addWidget(self.filter_input)

        layout.addStretch(1)

        self.open_session_button = QPushButton("Open session", self)
        set_button_role(self.open_session_button, "primary")
        self.start_packing_button = QPushButton("Start packing", self)
        set_button_role(self.start_packing_button, "primary")
        self.sku_mapping_button = QPushButton("SKU mapping", self)
        self.end_session_button = QPushButton("End session", self)
        for button in (self.open_session_button, self.start_packing_button,
                       self.sku_mapping_button, self.end_session_button):
            layout.addWidget(button)

        self.overflow = OverflowMenu(self)
        self.overflow_button = overflow_button(self.overflow, self)
        self.overflow_button.setToolTip("More")
        layout.addWidget(self.overflow_button)

        self._page = "packing"
        self._has_session = False
        on_theme_changed(self, self._apply_theme)
        self._refresh()

    def _apply_theme(self, tokens) -> None:
        # Type-scoped selectors: a bare rule would repaint every child button.
        self.setStyleSheet(
            f"CommandBar {{ background-color: {tokens.surface_raised};"
            f" border-bottom: 1px solid {tokens.border_subtle}; }}"
            f" QLabel#cmdbarSession {{ {font_css('body')}"
            f" font-family: {tokens.font_family_mono}; color: {tokens.text_secondary}; }}"
        )

    def set_page(self, name: str) -> None:
        if name not in PAGES:
            raise KeyError(f"Unknown page {name!r}; expected one of {PAGES}")
        self._page = name
        self._refresh()

    def set_session(self, session_id: str | None) -> None:
        self._has_session = bool(session_id)
        self.session_label.setText(session_id or "No session")
        self._refresh()

    def _refresh(self) -> None:
        packing = self._page == "packing"
        self.session_label.setHidden(self._page == "browser")
        self.filter_input.setHidden(not packing)
        self.filter_input.setEnabled(self._has_session)
        self.open_session_button.setHidden(not (packing and not self._has_session))
        for button in (self.start_packing_button, self.sku_mapping_button,
                       self.end_session_button):
            button.setHidden(not (packing and self._has_session))
```

- [ ] **Step 4: Run the tests plus the style guard**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_command_bar.py tests/test_style_literals_guard.py -q`
Expected: PASS.

`test_the_bar_is_floor_height` may fail because `height()` of a never-shown widget is its default rather than the fixed height. If so, assert `bar.minimumHeight() == bar.maximumHeight() == BAR_HEIGHT` instead. That is the same guarantee.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/command_bar.py tests/test_command_bar.py`, then `/usr/bin/git commit -m "Phase 10 Bundle 3: Packing command bar"`.

---

### Task 4: The window shell uses the bar; menu bar and toolbar go

**Files:**
- Modify: `gui/main_window.py` (`_init_ui` ~223-367, `_init_menu_bar` 374-412, `_init_toolbar` 414-457, `_toggle_theme` ~1112, `enable_packing_mode` ~2149, session teardown ~1810-1830). Line numbers are at commit `9a526d7`.
- Modify: `tests/test_shell.py`, `tests/test_screen_primaries.py`

**Interfaces:**
- Consumes: `CommandBar` (Task 3).
- Produces:
  - `MainWindow.command_bar: CommandBar`;
  - `PAGE_NAMES = ("packing", "statistics", "browser")` in `gui/main_window.py`, index-aligned with `RAIL_ITEMS`;
  - aliases kept for existing call sites: `client_combo`, `search_input`, `packer_mode_button`, `sku_mapping_button`, `toolbar_end_btn`.

- [ ] **Step 1: Rewrite the shell tests first**

In `tests/test_shell.py`:

1. Replace `test_the_search_field_lives_on_the_packing_page`:

```python
def test_the_order_filter_is_the_bars_and_only_shows_on_the_packing_page(window):
    """It filters the order tree, so it must not claim to filter other pages."""
    assert window.search_input is window.command_bar.filter_input
    window.session_tabs.setCurrentIndex(PAGE_BROWSER)
    assert window.search_input.isHidden()
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    assert not window.search_input.isHidden()
```

2. Replace `test_session_browser_is_not_also_a_button_and_a_menu_item` and `test_the_toolbar_still_carries_the_session_actions`:

```python
def test_there_is_no_toolbar_and_no_menu_bar(window):
    """Artboard T1: the command bar is the only chrome above the pages."""
    from PySide6.QtWidgets import QMenuBar, QToolBar

    assert window.findChildren(QToolBar) == []
    assert all(not bar.actions() for bar in window.findChildren(QMenuBar))


def test_the_bar_carries_the_session_actions(window):
    bar = window.command_bar
    assert window.packer_mode_button is bar.start_packing_button
    assert window.sku_mapping_button is bar.sku_mapping_button
    assert window.toolbar_end_btn is bar.end_session_button


def test_the_old_menu_actions_live_in_the_overflow(window):
    labels = [a.text() for a in window.command_bar.overflow.actions() if a.text()]
    assert labels == [
        "Select worker…", "Server connection…", "Toggle dark/light theme", "Exit",
    ]
    assert "Session Browser" not in labels  # a destination, reached by the rail


def test_ctrl_e_still_ends_the_session_through_the_bar_button(window, monkeypatch):
    from PySide6.QtGui import QKeySequence, QShortcut  # QtGui in Qt 6

    shortcuts = [s for s in window.findChildren(QShortcut)
                 if s.key() == QKeySequence("Ctrl+E")]
    assert len(shortcuts) == 1
    clicks = []
    monkeypatch.setattr(window.toolbar_end_btn, "click", lambda: clicks.append(1))
    shortcuts[0].activated.emit()
    assert clicks == [1]


def test_the_bar_follows_the_page(window):
    window.session_tabs.setCurrentIndex(PAGE_BROWSER)
    assert window.command_bar.session_label.isHidden()
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    assert not window.command_bar.session_label.isHidden()
```

The monkeypatch in the Ctrl+E test only works if the shortcut calls `self.toolbar_end_btn.click()` through a lambda, not a bound method captured at connect time. Step 3 wires it that way.

In `tests/test_screen_primaries.py`: delete `test_the_packer_mode_button_is_marked_primary`, the source-string check. Task 3's `test_a_session_offers_start_packing_as_the_one_primary` now covers it.

- [ ] **Step 2: Run them**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_shell.py -q`
Expected: the new tests FAIL (`AttributeError: 'MainWindow' object has no attribute 'command_bar'`); the old rail tests still pass.

- [ ] **Step 3: Implement in `gui/main_window.py`**

1. **Imports and page names.**
   - Add `from gui.command_bar import CommandBar`.
   - Add `QShortcut` to the `PySide6.QtGui` import (`QKeySequence` is already imported).
   - After `PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER = range(len(RAIL_ITEMS))`, add `PAGE_NAMES = ("packing", "statistics", "browser")`.

2. **`_init_ui`, top of the pages column.**
   - Set `main_layout.setContentsMargins(0, 0, 0, 0)` and `main_layout.setSpacing(0)`, so the bar runs edge to edge.
   - Delete the whole `CLIENT SELECTION` block: `client_selection_widget`, `client_label`, the `QComboBox` creation, the stretch.
   - Delete the `self.search_input = QLineEdit()` block and `packing_layout.addWidget(self.search_input)`.
   - Put this in their place, before the tab widget:

```python
        self.command_bar = CommandBar()
        main_layout.addWidget(self.command_bar)

        # Aliases: ~40 call sites already speak these names.
        self.client_combo = self.command_bar.client_combo
        self.client_combo.currentIndexChanged.connect(self.on_client_changed)
        self.search_input = self.command_bar.filter_input
        self.search_input.textChanged.connect(self._filter_orders)

        self.packer_mode_button = self.command_bar.start_packing_button
        self.packer_mode_button.setEnabled(False)
        self.packer_mode_button.setToolTip("Switch to barcode scanning / packer mode")
        self.packer_mode_button.clicked.connect(self.switch_to_packer_mode)

        self.sku_mapping_button = self.command_bar.sku_mapping_button
        self.sku_mapping_button.setToolTip("Manage barcode to SKU mappings")
        self.sku_mapping_button.clicked.connect(self.open_sku_mapping_dialog)

        self.toolbar_end_btn = self.command_bar.end_session_button
        self.toolbar_end_btn.setEnabled(False)
        self.toolbar_end_btn.setToolTip("End the current packing session")
        self.toolbar_end_btn.clicked.connect(self.end_session)

        self.command_bar.open_session_button.clicked.connect(self.open_session_browser)
```

3. **After the rail ↔ tabs connections**, add:

```python
        self.session_tabs.currentChanged.connect(
            lambda index: self.command_bar.set_page(PAGE_NAMES[index])
        )
```

4. **Replace `self._init_menu_bar()` and `self._init_toolbar()`** in `_init_ui` with `self._init_overflow()`. Delete both old methods and add:

```python
    def _init_overflow(self):
        """App-level actions behind the bar's ⋯ (spec E4, owner answer Q2)."""
        menu = self.command_bar.overflow
        menu.add_item("Select worker…", self._select_worker)
        menu.add_item("Server connection…", self._open_connection_settings)
        menu.add_item("Toggle dark/light theme", self._toggle_theme)
        menu.addSeparator()
        menu.add_item("Exit", self.close)

        # Through click(), which is a no-op on the disabled no-session button.
        end_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        end_shortcut.activated.connect(lambda: self.toolbar_end_btn.click())
```

5. **Remove the leftovers.**
   - Remove `from PySide6.QtWidgets import QToolBar` if nothing else uses it.
   - Remove `QFont` / `QSize` / `QAction` imports if ruff reports them unused.
   - In `_toggle_theme`, delete the `self.statusBar().showMessage(f"Theme switched to: …", 3000)` line. The repaint is the feedback.

6. **`enable_packing_mode`.** Replace the `session_info_label` block with:

```python
        session_id = (
            Path(self.current_session_path).name if self.current_session_path
            else (self.current_packing_list or "")
        )
        self.command_bar.set_session(session_id or None)
        self.command_bar.session_label.setToolTip(self.current_packing_list or "")
```

   (`Path` is already imported in `main_window.py`; check.)

7. **Session teardown** (~1818-1824). Replace the `session_info_label` lines with `self.command_bar.set_session(None)`. Leave the `hasattr(self, 'toolbar_end_btn')` guard alone.

8. **Check nothing still uses the removed names:** `grep -n "session_info_label\|_init_toolbar\|_init_menu_bar\|client_selection" gui/main_window.py` must print nothing.

- [ ] **Step 4: Run the shell tests and the full suite**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_shell.py tests/test_screen_primaries.py -q`, then the full suite `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest -q`.
Expected: PASS. `status_label` still exists at this point; Task 5 removes it.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/main_window.py tests/test_shell.py tests/test_screen_primaries.py`, then `/usr/bin/git commit -m "Phase 10 Bundle 3: shell command bar replaces menu bar and toolbar"`.

---

### Task 5: Status bar per artboard; the message line becomes toasts

**Files:**
- Modify: `gui/main_window.py` (`_init_ui` status_label block ~350-360, `_init_status_bar` ~459, worker label ~870, `_populate_order_tree` ~498, and every `status_label.setText` site)
- Modify: `tests/test_shell.py`

**Interfaces:**
- Consumes: `shared.components.toast.toast` (Task 1), `CommandBar.set_session` (Task 3).
- Produces:
  - `gui.main_window.order_summary(total: int, packed: int, in_progress: int) -> str`;
  - `MainWindow.sb_session_label`, `sb_worker_label`, `sb_summary_label` (`QLabel`);
  - `MainWindow.status_label` no longer exists.

- [ ] **Step 1: Failing tests** (append to `tests/test_shell.py`)

```python
from gui.main_window import order_summary


@pytest.mark.parametrize("args, text", [
    ((5, 2, 1), "5 orders · 2 packed · 1 in progress"),
    ((1, 1, 0), "1 order · 1 packed · 0 in progress"),
    ((0, 0, 0), ""),
])
def test_order_summary(args, text):
    assert order_summary(*args) == text


def test_the_message_line_is_gone(window):
    """Its texts became toasts (spec E5). It also hid a bug: session teardown
    overwrote "Report saved to <path>" before anyone could read it."""
    assert not hasattr(window, "status_label")


def test_the_status_bar_is_the_artboards_strip(window):
    bar = window.statusBar()
    assert bar.minimumHeight() == bar.maximumHeight() == 40
    assert window.sb_worker_label.text() == window.current_worker_name
    assert window.sb_session_label.text() == "—"
```

- [ ] **Step 2: Run them**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest tests/test_shell.py -q`
Expected: the three new tests FAIL (ImportError on `order_summary` fails the module; that counts).

- [ ] **Step 3: Implement**

1. **Imports and the summary function.**
   - Add `from shared.components.toast import toast`.
   - Add `font_css` and `on_theme_changed` to the `shared.theme` import if they are missing.
   - Put this module-level function above `class MainWindow`:

```python
def order_summary(total: int, packed: int, in_progress: int) -> str:
    """The status bar's right-hand text (artboard T1). Empty with no orders."""
    if not total:
        return ""
    noun = "order" if total == 1 else "orders"
    return f"{total} {noun} · {packed} packed · {in_progress} in progress"
```

2. **`_init_ui`.** Delete the `self.status_label = QLabel(...)` block and its `main_layout.addWidget(self.status_label)`.

3. **Rewrite `_init_status_bar`:**

```python
    def _init_status_bar(self):
        """Artboard T1's 40px strip: session id and worker left, order summary right.

        Colours come from build_stylesheet's QStatusBar rule; only the mono
        session id styles itself.
        """
        status_bar = self.statusBar()
        status_bar.setFixedHeight(40)
        status_bar.setSizeGripEnabled(False)

        self.sb_session_label = QLabel("—")
        on_theme_changed(
            self.sb_session_label,
            lambda tokens: self.sb_session_label.setStyleSheet(
                f"{font_css('caption')} font-family: {tokens.font_family_mono};"
                f" color: {tokens.text_secondary};"
            ),
        )
        self.sb_worker_label = QLabel(self.current_worker_name or "")
        self.sb_worker_label.setObjectName("worker_label")
        self.sb_summary_label = QLabel("")
        status_bar.addWidget(self.sb_session_label)
        status_bar.addWidget(self.sb_worker_label)
        status_bar.addPermanentWidget(self.sb_summary_label)
```

   `on_theme_changed` calls `apply` immediately, so the lambda must be connected after `self.sb_session_label` is assigned. It is.

4. **Worker label** (~870): `self.sb_worker_label.setText(self.current_worker_name)`, without the "Worker: " prefix.

5. **Where the command bar's session changes** (Task 4's `enable_packing_mode` edit and the teardown), set the status bar too:
   - in `enable_packing_mode`: `self.sb_session_label.setText(session_id or "—")`;
   - in the teardown: `self.sb_session_label.setText("—")` and `self.sb_summary_label.setText("")`.

6. **End of `_populate_order_tree`** (after the loop; also on its early `return` when there is no logic, set `""`):

```python
        in_progress = len(in_progress_orders)
        self.sb_summary_label.setText(
            order_summary(grouped.ngroups, len(completed_orders), in_progress)
        )
```

   On the early return: `self.sb_summary_label.setText("")` before `return`. `_populate_order_tree` can run before `_init_status_bar` during `_init_ui`, so guard with `if hasattr(self, "sb_summary_label")`.

7. **Replace every `status_label.setText`.** Find them with `grep -n "status_label" gui/main_window.py`; this table was taken at `9a526d7`. Anything still matching after this list is a site this table missed: apply the two rules in spec E5 to it.

| Line | Old text | New |
|---|---|---|
| ~905 | "No clients found. Click '+ New Client'…" | delete (the combo already shows "(No clients available)"; the button it names does not exist) |
| ~953 | "Please select or create a client." | delete |
| ~965 | "Selected client: …\nReady to start a session." | delete |
| ~1028 | "A session is already active. Please end it first." | `toast(self, "A session is already open. End it first.", role="info")` |
| ~1087 | "Successfully loaded {n} orders for session '{id}'." | `toast(self, f"Loaded {order_count} orders.")` |
| ~1155 | "SKU mapping updated and synchronized across all PCs." | `toast(self, "SKU mapping saved and shared with every PC.")` |
| ~1441 | "Session: …\nOrders: …\nReady for packing" | `toast(self, f"Loaded {order_count} orders from {packing_list_name}.")` |
| ~1569 | "Session ended. Report saved to {output_path}" | `toast(self, f"Session ended. Report saved to {output_path}")` |
| ~1784 | "Could not save the report. Error: {e}" | `QMessageBox.critical(self, "Report not saved", f"Could not save the report:\n\n{e}")`, unless that `except` block already shows a dialog for the same error, in which case just delete |
| ~1828 | "Session ended. Start a new session to begin." | delete (this is the D7 bug: it overwrote the ~1569 message) |
| ~2175 / ~2180 | "Ready to pack…" / "Ready to pack" | delete, with the whole `if/else` (the load toasts already said it) |
| ~2466 | "Session opening cancelled." | delete (the user just cancelled it themselves) |

   The toast at ~1155 runs after `SKUMappingDialog` closes. `toast(self, …)` uses the main window as its source, which is right: the dialog is gone by then.

8. **Check** that `grep -n "status_label" gui/main_window.py` prints nothing. `packer_mode_widget.py` has its own `status_label`; do not touch it.

- [ ] **Step 4: Run the full suite and lint**

Run: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest -q` and `/home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m ruff check . --exclude shared`
Expected: all pass, lint clean.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/main_window.py tests/test_shell.py`, then `/usr/bin/git commit -m "Phase 10 Bundle 3: artboard status bar; message line becomes toasts"`.

---

### Task 6: Render check in both themes, glossary, push packing-tool

**Files:**
- Modify: `CONTEXT.md`
- Throwaway (not committed): `$CLAUDE_JOB_DIR/tmp/render_shell.py`

- [ ] **Step 1: Render the shell**

Create `$CLAUDE_JOB_DIR/tmp/render_shell.py`:

```python
import sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication
from gui.theme import apply_theme
from shared.theme import set_density

app = QApplication([])
set_density("floor")
from gui.main_window import MainWindow

tmp = Path(tempfile.mkdtemp())
for d in ("server", "cache"):
    (tmp / d).mkdir()
cfg = tmp / "config.ini"
cfg.write_text(
    f"[Network]\nFileServerPath = {tmp/'server'}\nConnectionTimeout = 5\n"
    f"LocalCachePath = {tmp/'cache'}\n[Logging]\nLogLevel = INFO\n"
    "LogRetentionDays = 30\nMaxLogSizeMB = 10\n", encoding="utf-8")
out = Path(sys.argv[1])
for theme in ("dark", "light"):
    apply_theme(app, theme)
    w = MainWindow(config_path=str(cfg))
    w.resize(1366, 768)
    w.show()
    app.processEvents()
    w.command_bar.set_session("2026-09-01_1042")
    app.processEvents()
    w.grab().save(str(out / f"shell-{theme}.png"))
    w.command_bar.set_session(None)
    app.processEvents()
    w.grab().save(str(out / f"shell-{theme}-nosession.png"))
    w.close()
```

Run from the packing-tool worktree: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python $CLAUDE_JOB_DIR/tmp/render_shell.py $CLAUDE_JOB_DIR/tmp`. (`apply_theme` writes the real `QSettings` theme key; that is acceptable on the dev VM.)

Open the four PNGs with the Read tool and compare them against `docs/design/phase10/packing-table.html` T1/T2:
- 60px bar with client, session id, filter, spacer, buttons, ⋯;
- one primary;
- 40px status strip;
- readable in both themes;
- no leftover "Client:" strip or menu bar.

Fix anything off in `gui/command_bar.py` or `main_window.py` and re-run Task 5 Step 4. Record in the Agent Handoff task that the render check was done.

- [ ] **Step 2: Glossary**

Add to `CONTEXT.md` after **Packing table view**:

```markdown
**Command bar** — the 60px row above Packing Tool's pages: client picker, session id, the page's actions, and the ⋯ overflow menu.

**Toast** — a transient, non-blocking message at the window's bottom right for an outcome that needs no decision; failures use a dialog instead.
```

- [ ] **Step 3: Commit, graphify, push**

1. `/usr/bin/git add CONTEXT.md`
2. `/usr/bin/git commit -m "Phase 10 Bundle 3: glossary"`
3. `graphify update .`
4. `/usr/bin/git push -u origin worktree-phase10-bundle3`

---

### Task 7: Shopify adopts `shared/components`

Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/phase10-bundle3` (`cd` there for non-git commands; git calls use `/usr/bin/git -C <that path>`).

**Files:**
- Sync: `shared/**`
- Delete: `gui/components/{card,state_panel,toast,confirm_dialog,filterbar,overflow}.py`, `tests/test_components_card.py`, `tests/test_state_panel.py`, `tests/test_components_toast.py`, `tests/test_components_confirm_dialog.py`, `tests/test_components_filterbar.py`, `tests/test_components_overflow.py`
- Modify: `gui/components/__init__.py`, `gui/components/commandbar.py`, `gui/ui_manager.py`, `gui/settings/reports.py`, `gui/settings/window.py`, `gui/settings/sets.py`, `gui/theme_manager.py`, `tests/test_components_render_roles.py`, `docs/adr/0001-analysis-results-on-the-web-tier.md`

**Interfaces:** Consumes the `shared.components` exports from Task 1. Produces no new names: every `from gui.components import X` in Shopify keeps working.

- [ ] **Step 1: Sync**

Run: `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/phase10-bundle3`
Expected: the output lists `components/…` and `theme.py`.

- [ ] **Step 2: Delete the Shopify copies and switch imports**

1. Delete the six modules and six tests listed above (`/usr/bin/git -C <shopify wt> rm <paths>`).
2. In `gui/components/__init__.py`, replace the six `from gui.components.<moved> import …` lines with one block below `from shared.navrail import NavRail`:

```python
from shared.components import (
    Card,
    ConfirmDialog,
    FilterBar,
    OverflowMenu,
    StatePanel,
    Toast,
    overflow_button,
    toast,
)
```

   Check `__all__`, if the file has one, still lists every name.

3. Switch the deep imports:

| File | From | To |
|---|---|---|
| `gui/components/commandbar.py` | `from gui.components.overflow import …` | `from shared.components.overflow import …` |
| `gui/ui_manager.py` | `from gui.components.state_panel import StatePanel` | `from shared.components.state_panel import StatePanel` |
| `gui/settings/reports.py` | same | same |
| `gui/settings/window.py` | `from gui.components.toast import toast` | `from shared.components.toast import toast` |
| `gui/settings/sets.py` | same | same |
| `tests/test_components_render_roles.py` | `from gui.components.state_panel import StatePanel` | `from shared.components.state_panel import StatePanel` |

   Then `grep -rnE "gui\.components\.(card|state_panel|toast|confirm_dialog|filterbar|overflow)\b" gui tests` must print nothing.

4. In `gui/theme_manager.py`, delete the `def apply_dialog_button_roles` function and add `apply_dialog_button_roles,  # noqa: F401 -- re-exported` to its `from shared.theme import (…)` list.

- [ ] **Step 3: ADR note**

Append to `docs/adr/0001-analysis-results-on-the-web-tier.md`:

```markdown
## Note (2026-09-17)

The line saying Packing Tool stays entirely Qt is superseded: Packing Tool's
Packer Mode order document moves to the web tier too. See packing-tool
`docs/adr/0001-packer-mode-on-the-web-tier.md`.
```

- [ ] **Step 4: Full suite, lint, style lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `.venv/bin/python -m ruff check . --exclude shared`
Expected: all pass. A test that patched `gui.components.toast.…` or `gui.components.state_panel.…` by string path must patch `shared.components.…` instead. Search with `grep -rn "gui.components\." tests`.

- [ ] **Step 5: Commit, graphify, push**

1. `/usr/bin/git -C <shopify wt> add -A shared gui tests docs/adr`
2. `/usr/bin/git -C <shopify wt> commit -m "Phase 10 Bundle 3: components come from shared/"`
3. `graphify update .` (run in the Shopify worktree)
4. `/usr/bin/git -C <shopify wt> push -u origin worktree-phase10-bundle3`

**Merge order for Stage C's PRs:** packing-tool first, because it is the canonical `shared/`. The Shopify PR body must say "merge after packing-tool #<n>".
