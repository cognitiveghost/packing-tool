# Unified UI/UX Design System (Packing Tool + Shopify Fulfillment Tool) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace both apps' independent, drifted theme systems with one shared `shared/theme.py`, apply a unified VS Code–inspired high-contrast palette, clean up the concrete inconsistencies the audit found (hardcoded colors, no spacing scale, no window-geometry persistence, leftover info banners, excess emoji), and rebuild four specific screens (Packer Mode, Session Browser, Shopify main window, Shopify settings window) per the approved mockups.

**Architecture:** `packing-tool/shared/theme.py` becomes the single source of truth for colors, spacing, fonts, a `StatusDot` widget, and window-geometry helpers — following the exact same canonical-source pattern already established for `stats_manager.py` (see `docs/superpowers/specs/2026-07-25-shared-unification-design.md`). It's synced into `shopify-fulfillment-tool/shared/` via the existing `scripts/sync_shared.py`. Both apps' existing `theme_manager.py`/`theme.py` keep their current public APIs but delegate internally to `shared.theme`, so the ~180 call sites across `shopify-fulfillment-tool/gui/*.py` that read `theme.text`, `theme.accent_blue`, etc. need zero changes.

**Tech Stack:** Python 3.11+, PySide6, pytest (packing-tool only — shopify-fulfillment-tool has no test suite; verified via `ruff check .` + its existing headless smoke test).

**Related spec:** `docs/superpowers/specs/2026-07-26-unified-ui-design-system-design.md`

## Global Constraints

- Canonical `shared/theme.py` lives in `packing-tool/shared/`; shopify-fulfillment-tool's copy is produced only by running `python scripts/sync_shared.py`, never hand-edited.
- `ThemeTokens` field names for colors (`background`, `background_elevated`, `text`, `text_secondary`, `border`, `border_subtle`, `hover`, `active_background`, `active_border`, `accent_blue`, `accent_green`, `accent_orange`, `accent_red`, `button_hover_light`, `button_hover_dark`) are kept **identical** to shopify-fulfillment-tool's pre-existing `ThemeColors` dataclass field names — verified via `grep -rohE "theme\.[a-z_]+" gui/*.py` to be read at ~180 call sites across 18 files. Do not rename these fields.
- Accent color is `#007ACC` everywhere (was `#1565C0`/similar in both apps). Border radius is `4` (int, px) everywhere (was 6-8px in shopify-tool). Semantic colors (`accent_green`/`accent_orange`/`accent_red`) keep their existing values — both apps already agree on these.
- Light theme borders (`border`, `text`) go from the old soft gray (`#CCCCCC`)/mid-gray to near-black (`#1A1A1A`) — this is the single biggest visible palette change, approved via mockup.
- No new pip dependencies. No `pytest-qt` — Qt-dependent code (stylesheet/palette builders, `StatusDot`, `apply_theme`) is verified with an `if __name__ == "__main__":` self-check block (offscreen `QApplication`), not pytest, per this codebase's existing convention (no PySide6 code anywhere is currently pytest-covered). Pure-Python logic (`ThemeTokens` validation, geometry clamping) gets real pytest tests in `packing-tool/tests/`.
- Out of scope (do not touch): backend/business logic, a mechanical rewrite of every `setSpacing`/`setContentsMargins` call in both apps, IA changes to Shopify tool's Information/Tools/Reports tabs, any Packing Tool dialog other than Packer Mode and Session Browser.
- `shopify-fulfillment-tool` has no `tests/` directory (per its `CLAUDE.md`: "Tests are being rewritten"). Verification there is `ruff check .` plus `CI=1 python run_dev.py` (existing headless smoke test).

---

### Task 1: `shared/theme.py` — ThemeTokens dataclass and the two theme instances

**Files:**
- Create: `packing-tool/shared/theme.py`
- Test: `packing-tool/tests/test_theme.py`

**Interfaces:**
- Produces: `ThemeTokens` (frozen dataclass), `LIGHT_THEME`, `DARK_THEME` (module-level `ThemeTokens` instances), `THEMES: dict[str, ThemeTokens]`, `get_theme(name: str) -> ThemeTokens`, `validate_theme(theme: ThemeTokens) -> None` (raises `ValueError`) — consumed by Task 2 (geometry), Task 3 (stylesheet/palette), Task 6/7 (both apps' theme modules).

- [ ] **Step 1: Write the failing test**

```python
# packing-tool/tests/test_theme.py
import pytest
from shared.theme import ThemeTokens, LIGHT_THEME, DARK_THEME, THEMES, get_theme, validate_theme


def test_light_and_dark_themes_have_distinct_backgrounds():
    assert LIGHT_THEME.background == "#FFFFFF"
    assert DARK_THEME.background == "#000000"


def test_light_theme_border_is_near_black_not_soft_gray():
    # The approved design change: light theme borders mirror dark theme's
    # crisp borders instead of the old #CCCCCC soft gray.
    assert LIGHT_THEME.border == "#1A1A1A"


def test_both_themes_share_the_same_accent_and_radius():
    assert LIGHT_THEME.accent_blue == DARK_THEME.accent_blue == "#007ACC"
    assert LIGHT_THEME.radius == DARK_THEME.radius == 4


def test_get_theme_returns_correct_instance():
    assert get_theme("dark") is DARK_THEME
    assert get_theme("light") is LIGHT_THEME


def test_get_theme_falls_back_to_light_for_unknown_name():
    assert get_theme("nonsense") is LIGHT_THEME


def test_validate_theme_passes_for_both_builtin_themes():
    validate_theme(LIGHT_THEME)
    validate_theme(DARK_THEME)


def test_validate_theme_rejects_bad_hex():
    bad = ThemeTokens(
        name="bad", background="not-a-color", background_elevated="#FFFFFF",
        text="#000000", text_secondary="#000000", text_disabled="#000000",
        text_placeholder="#000000", border="#000000", border_subtle="#000000",
        hover="#000000", active_background="#000000", active_border="#000000",
        button_hover_light="#000000", button_hover_dark="#000000",
    )
    with pytest.raises(ValueError):
        validate_theme(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packing-tool && python -m pytest tests/test_theme.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shared.theme'`

- [ ] **Step 3: Write the implementation**

```python
# packing-tool/shared/theme.py
"""Shared theme system for Packing Tool and Shopify Fulfillment Tool.

Canonical source — see
docs/superpowers/specs/2026-07-26-unified-ui-design-system-design.md.
Never hand-edit shopify-fulfillment-tool/shared/theme.py; run
shopify-fulfillment-tool/scripts/sync_shared.py after changing this file.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeTokens:
    """Color/spacing/font tokens for one theme (light or dark).

    Color field names are kept identical to shopify-fulfillment-tool's
    pre-unification `ThemeColors` dataclass on purpose — ~180 call sites
    across gui/*.py read these by exact attribute name (e.g.
    `theme.text_secondary`, `theme.accent_blue`) and renaming them would
    mean touching every one of those call sites for no functional gain.
    """
    name: str
    background: str
    background_elevated: str
    text: str
    text_secondary: str
    text_disabled: str
    text_placeholder: str
    border: str
    border_subtle: str
    hover: str
    active_background: str
    active_border: str
    button_hover_light: str
    button_hover_dark: str
    accent_blue: str = "#007ACC"
    accent_green: str = "#4CAF50"
    accent_orange: str = "#FF9800"
    accent_red: str = "#F44336"
    radius: int = 4
    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 12
    spacing_lg: int = 16
    spacing_xl: int = 24
    font_family: str = "Segoe UI, sans-serif"
    font_family_mono: str = "Consolas, monospace"


LIGHT_THEME = ThemeTokens(
    name="light",
    background="#FFFFFF",
    background_elevated="#FAFAFA",
    text="#1A1A1A",
    text_secondary="#5A5A5A",
    text_disabled="#AAAAAA",
    text_placeholder="#888888",
    border="#1A1A1A",
    border_subtle="#CCCCCC",
    hover="#EEEEEE",
    active_background="#F0F8F0",
    active_border="#4CAF50",
    button_hover_light="#005A9E",
    button_hover_dark="#005A9E",
)

DARK_THEME = ThemeTokens(
    name="dark",
    background="#000000",
    background_elevated="#0F0F0F",
    text="#FFFFFF",
    text_secondary="#B0B0B0",
    text_disabled="#444444",
    text_placeholder="#888888",
    border="#FFFFFF",
    border_subtle="#404040",
    hover="#1A1A1A",
    active_background="#1A3D1A",
    active_border="#4CAF50",
    button_hover_light="#2D9FE8",
    button_hover_dark="#2D9FE8",
)

THEMES: dict = {"light": LIGHT_THEME, "dark": DARK_THEME}


def get_theme(name: str) -> ThemeTokens:
    """Look up a theme by name, falling back to light for an unknown name."""
    return THEMES.get(name, LIGHT_THEME)


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_COLOR_FIELDS = (
    "background", "background_elevated", "text", "text_secondary",
    "text_disabled", "text_placeholder", "border", "border_subtle",
    "hover", "active_background", "active_border", "button_hover_light",
    "button_hover_dark", "accent_blue", "accent_green", "accent_orange",
    "accent_red",
)


def validate_theme(theme: ThemeTokens) -> None:
    """Raise ValueError if any color field isn't a valid #RRGGBB string."""
    for field_name in _COLOR_FIELDS:
        value = getattr(theme, field_name)
        if not _HEX_RE.match(value):
            raise ValueError(
                f"{theme.name}.{field_name} = {value!r} is not a valid #RRGGBB color"
            )


if __name__ == "__main__":
    validate_theme(LIGHT_THEME)
    validate_theme(DARK_THEME)
    assert get_theme("dark") is DARK_THEME
    assert get_theme("light") is LIGHT_THEME
    assert get_theme("missing") is LIGHT_THEME
    print("shared/theme.py tokens self-check OK")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packing-tool && python -m pytest tests/test_theme.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the self-check**

Run: `cd packing-tool && python shared/theme.py`
Expected: `shared/theme.py tokens self-check OK`

- [ ] **Step 6: Commit**

```bash
cd packing-tool
git add shared/theme.py tests/test_theme.py
git commit -m "feat: add shared ThemeTokens and light/dark theme instances"
```

---

### Task 2: `shared/theme.py` — window-geometry clamping (pure function)

**Files:**
- Modify: `packing-tool/shared/theme.py`
- Test: `packing-tool/tests/test_theme.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `clamp_geometry(x, y, w, h, avail_x, avail_y, avail_w, avail_h) -> tuple[int, int, int, int]` — consumed by Task 4's `restore_window_geometry`.

- [ ] **Step 1: Write the failing test**

```python
# append to packing-tool/tests/test_theme.py
from shared.theme import clamp_geometry


def test_clamp_geometry_leaves_window_untouched_when_it_fits():
    result = clamp_geometry(100, 100, 800, 600, 0, 0, 1920, 1080)
    assert result == (100, 100, 800, 600)


def test_clamp_geometry_shrinks_window_larger_than_screen():
    result = clamp_geometry(0, 0, 3000, 2000, 0, 0, 1920, 1080)
    assert result == (0, 0, 1920, 1080)


def test_clamp_geometry_pulls_window_back_onto_screen():
    # Saved on a monitor to the right that no longer exists; available
    # screen is now just the primary 1920x1080 at origin (0,0).
    result = clamp_geometry(2500, 100, 800, 600, 0, 0, 1920, 1080)
    assert result == (1120, 100, 800, 600)  # 1920 - 800 = 1120


def test_clamp_geometry_pulls_window_up_from_negative_position():
    result = clamp_geometry(-500, -500, 800, 600, 0, 0, 1920, 1080)
    assert result == (0, 0, 800, 600)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packing-tool && python -m pytest tests/test_theme.py -v -k clamp_geometry`
Expected: FAIL with `ImportError: cannot import name 'clamp_geometry'`

- [ ] **Step 3: Add the implementation**

```python
# add to packing-tool/shared/theme.py, after validate_theme()

def clamp_geometry(
    x: int, y: int, w: int, h: int,
    avail_x: int, avail_y: int, avail_w: int, avail_h: int,
) -> tuple:
    """Clamp a saved window rect to fit inside the available screen rect.

    Shrinks w/h to fit if larger than the screen, then clamps x/y so the
    whole window is on-screen. Pure function — no Qt dependency — so a
    saved-on-a-different-monitor geometry can never restore off-screen.
    """
    w = min(w, avail_w)
    h = min(h, avail_h)
    x = max(avail_x, min(x, avail_x + avail_w - w))
    y = max(avail_y, min(y, avail_y + avail_h - h))
    return (x, y, w, h)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packing-tool && python -m pytest tests/test_theme.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
cd packing-tool
git add shared/theme.py tests/test_theme.py
git commit -m "feat: add pure clamp_geometry helper for window-geometry restore"
```

---

### Task 3: `shared/theme.py` — stylesheet and palette builders

**Files:**
- Modify: `packing-tool/shared/theme.py`

**Interfaces:**
- Consumes: `ThemeTokens` (Task 1).
- Produces: `build_stylesheet(theme: ThemeTokens) -> str`, `build_palette(theme: ThemeTokens) -> QPalette`, `apply_theme(app: QApplication, theme_name: str) -> None` — consumed by Task 6 (packing-tool theme.py) and Task 7 (shopify-tool theme_manager.py).

- [ ] **Step 1: Add the stylesheet builder**

This ports shopify-fulfillment-tool's existing (already comprehensive, already-working) `_build_global_stylesheet` template, parameterized with the new token names and the `radius` token instead of hardcoded 6-8px corners.

```python
# add to packing-tool/shared/theme.py

def build_stylesheet(theme: ThemeTokens) -> str:
    """Build the global Qt stylesheet (QSS) for one theme."""
    hover = theme.button_hover_dark if theme.name == "dark" else theme.button_hover_light
    r = theme.radius
    return f"""
        QWidget {{
            background-color: {theme.background};
            color: {theme.text};
            font-family: {theme.font_family};
        }}

        QPushButton {{
            background-color: {theme.accent_blue};
            color: white;
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 6px 12px;
            font-size: 10pt;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {theme.button_hover_dark}; }}
        QPushButton:disabled {{
            background-color: {theme.background};
            color: {theme.text_disabled};
            border: 1px solid {theme.border_subtle};
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 4px 8px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 2px solid {theme.accent_blue};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            background-color: {theme.background};
            color: {theme.text_disabled};
            border-color: {theme.border_subtle};
        }}

        QComboBox {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 4px 8px;
        }}
        QComboBox:hover {{ border: 1px solid {theme.accent_blue}; }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            selection-background-color: {theme.accent_blue};
            selection-color: white;
        }}

        QSpinBox, QDoubleSpinBox, QDateEdit {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 4px 8px;
        }}

        QCheckBox, QRadioButton {{
            color: {theme.text};
            spacing: {theme.spacing_sm}px;
            background-color: transparent;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 18px; height: 18px;
            border: 2px solid {theme.border};
            border-radius: {r}px;
            background-color: {theme.background};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 2px solid {theme.accent_blue};
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background-color: {theme.accent_blue};
            border: 2px solid {theme.accent_blue};
        }}

        QGroupBox {{
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r + 4}px;
            padding-top: 24px; padding-bottom: 8px;
            padding-left: 8px; padding-right: 8px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: padding;
            subcontrol-position: top left;
            padding: 4px 8px; left: 8px; top: 4px;
        }}

        QLabel {{ color: {theme.text}; background-color: transparent; }}

        QTableView {{
            background-color: {theme.background};
            color: {theme.text};
            gridline-color: {theme.border_subtle};
            border: 1px solid {theme.border};
            border-radius: {r + 4}px;
        }}
        QTableView::item:selected {{ background-color: {theme.accent_blue}; color: white; }}
        QTableView::item:hover {{ background-color: {theme.hover}; }}
        QHeaderView::section {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            padding: 4px; font-weight: bold;
        }}
        QTableCornerButton::section {{
            background-color: {theme.background_elevated};
            border: 1px solid {theme.border};
        }}

        QListWidget {{
            background-color: {theme.background};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r + 4}px;
        }}
        QListWidget::item:selected {{ background-color: {theme.accent_blue}; color: white; }}
        QListWidget::item:hover {{ background-color: {theme.hover}; }}

        QScrollBar:vertical {{ background-color: {theme.background}; width: 12px; border: none; }}
        QScrollBar::handle:vertical {{
            background-color: {theme.border}; min-height: 20px; border-radius: 6px;
        }}
        QScrollBar::handle:vertical:hover {{ background-color: {theme.text_secondary}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar:horizontal {{ background-color: {theme.background}; height: 12px; border: none; }}
        QScrollBar::handle:horizontal {{
            background-color: {theme.border}; min-width: 20px; border-radius: 6px;
        }}
        QScrollBar::handle:horizontal:hover {{ background-color: {theme.text_secondary}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

        QTabWidget::pane {{ border: 1px solid {theme.border}; background-color: {theme.background}; }}
        QTabBar::tab {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            padding: 8px 16px; margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {theme.background};
            border-bottom-color: {theme.background};
            font-weight: bold;
        }}
        QTabBar::tab:hover {{ background-color: {theme.hover}; }}

        QStatusBar {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border-top: 1px solid {theme.border};
        }}

        QMenuBar {{ background-color: {theme.background}; color: {theme.text}; }}
        QMenuBar::item:selected {{ background-color: {theme.hover}; }}
        QMenu {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
        }}
        QMenu::item:selected {{ background-color: {theme.accent_blue}; color: white; }}

        QToolBar {{
            background-color: {theme.background_elevated};
            border: 1px solid {theme.border};
            spacing: {theme.spacing_xs}px;
        }}

        QDialog {{ background-color: {theme.background}; color: {theme.text}; }}
    """
```

- [ ] **Step 2: Add the palette builder and apply_theme**

```python
# add to packing-tool/shared/theme.py

def build_palette(theme: ThemeTokens):
    """Build a QPalette for one theme. Import is local so this module stays
    importable in a pure-Python (no Qt) context, e.g. under plain pytest."""
    from PySide6.QtGui import QPalette, QColor

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(theme.background))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(theme.background_elevated))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.hover))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.background_elevated))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Text, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(theme.background_elevated))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(theme.accent_red))
    palette.setColor(QPalette.ColorRole.Link, QColor(theme.accent_blue))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor("#9C27B0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.accent_blue))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.text_placeholder))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(theme.background_elevated))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(theme.background_elevated))
    return palette


def apply_theme(app, theme_name: str) -> None:
    """Apply a theme's stylesheet and palette to a running QApplication."""
    theme = get_theme(theme_name)
    app.setStyleSheet(build_stylesheet(theme))
    app.setPalette(build_palette(theme))
```

- [ ] **Step 3: Write and run the Qt self-check**

```python
# replace the `if __name__ == "__main__":` block at the bottom of
# packing-tool/shared/theme.py with:

if __name__ == "__main__":
    validate_theme(LIGHT_THEME)
    validate_theme(DARK_THEME)
    assert get_theme("dark") is DARK_THEME
    assert get_theme("light") is LIGHT_THEME
    assert get_theme("missing") is LIGHT_THEME

    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    for theme in (LIGHT_THEME, DARK_THEME):
        sheet = build_stylesheet(theme)
        assert "QPushButton" in sheet and theme.accent_blue in sheet
        palette = build_palette(theme)
        assert palette.color(palette.ColorRole.Window).name().upper() == theme.background.upper()
    apply_theme(app, "dark")
    assert theme_app_stylesheet := app.styleSheet()
    print("shared/theme.py full self-check OK")
```

Run: `cd packing-tool && python shared/theme.py`
Expected: `shared/theme.py full self-check OK`

- [ ] **Step 4: Commit**

```bash
cd packing-tool
git add shared/theme.py
git commit -m "feat: add shared stylesheet and QPalette builders"
```

---

### Task 4: `shared/theme.py` — StatusDot widget and window-geometry save/restore

**Files:**
- Modify: `packing-tool/shared/theme.py`

**Interfaces:**
- Consumes: `clamp_geometry` (Task 2).
- Produces: `StatusDot(QWidget)` with `__init__(self, color: str, diameter: int = 10, parent=None)` and `set_color(self, color: str) -> None` — consumed by Task 11 (Session Browser). `save_window_geometry(window, settings) -> None`, `restore_window_geometry(window, settings) -> bool` — consumed by Task 10 (both main windows).

- [ ] **Step 1: Add StatusDot**

```python
# add to packing-tool/shared/theme.py, near the top-level imports add:
#   from PySide6.QtCore import Qt
#   from PySide6.QtGui import QColor, QPainter
#   from PySide6.QtWidgets import QWidget
# (module-level import is fine here — unlike build_palette/apply_theme,
#  StatusDot IS a Qt class and this module already has Qt as a runtime
#  dependency once any of these are used; only the pure functions above
#  need to stay importable without Qt installed.)

class StatusDot(QWidget):
    """Small colored circle for status indicators in tables/lists.

    Replaces emoji glyphs (previously concatenated into table-cell text,
    e.g. packing-tool's sessions_list_widget.py STATUS_CONFIG icons) with a
    theme-independent painted widget — consistent rendering across OS/fonts.
    """

    def __init__(self, color: str, diameter: int = 10, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self._diameter, self._diameter)
```

- [ ] **Step 2: Add window-geometry save/restore**

```python
# add to packing-tool/shared/theme.py

def save_window_geometry(window, settings, key: str = "window_geometry") -> None:
    """Save a QMainWindow/QWidget's geometry to QSettings."""
    settings.setValue(key, window.saveGeometry())


def restore_window_geometry(window, settings, key: str = "window_geometry") -> bool:
    """Restore previously-saved geometry, clamped to the available screen.

    Returns True if geometry was restored, False if there was nothing saved
    (caller should fall back to its own default size in that case).
    """
    from PySide6.QtGui import QGuiApplication

    raw = settings.value(key)
    if raw is None:
        return False
    if not window.restoreGeometry(raw):
        return False

    screen = window.screen() or QGuiApplication.primaryScreen()
    avail = screen.availableGeometry()
    geo = window.geometry()
    x, y, w, h = clamp_geometry(
        geo.x(), geo.y(), geo.width(), geo.height(),
        avail.x(), avail.y(), avail.width(), avail.height(),
    )
    window.setGeometry(x, y, w, h)
    return True
```

- [ ] **Step 3: Extend the Qt self-check**

```python
# extend the Qt section of the `if __name__ == "__main__":` block from Task 3:

    dot = StatusDot(DARK_THEME.accent_green)
    assert dot.width() == 10 and dot.height() == 10
    dot.set_color(DARK_THEME.accent_red)

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMainWindow
    test_settings = QSettings("SharedThemeSelfCheck", "GeometryTest")
    test_settings.remove("window_geometry")
    win = QMainWindow()
    win.setGeometry(100, 100, 800, 600)
    save_window_geometry(win, test_settings)
    win2 = QMainWindow()
    assert restore_window_geometry(win2, test_settings) is True
    assert win2.geometry().width() == 800
    test_settings.remove("window_geometry")

    print("shared/theme.py full self-check OK")
```

Run: `cd packing-tool && python shared/theme.py`
Expected: `shared/theme.py full self-check OK`

- [ ] **Step 4: Commit**

```bash
cd packing-tool
git add shared/theme.py
git commit -m "feat: add StatusDot widget and window-geometry save/restore helpers"
```

---

### Task 5: Sync `shared/` into shopify-fulfillment-tool

**Files:**
- No manual edits — runs the existing sync script.
- Modify (generated): `shopify-fulfillment-tool/shared/theme.py` (new file, copied)

**Interfaces:**
- Consumes: `packing-tool/scripts/... ` — actually the sync script lives in shopify-fulfillment-tool (`shopify-fulfillment-tool/scripts/sync_shared.py`), copying FROM `packing-tool/shared/` TO `shopify-fulfillment-tool/shared/`.
- Produces: `shopify-fulfillment-tool/shared/theme.py`, identical to `packing-tool/shared/theme.py` — consumed by Task 7.

- [ ] **Step 1: Run the existing sync script**

Run: `cd shopify-fulfillment-tool && python scripts/sync_shared.py`
Expected: prints a list of copied files including `theme.py`, e.g. `Synced N file(s) from .../packing-tool/shared to .../shared:` followed by a file list containing `theme.py`.

- [ ] **Step 2: Verify the copy is byte-identical**

Run: `diff packing-tool/shared/theme.py shopify-fulfillment-tool/shared/theme.py`
Expected: no output (files identical)

- [ ] **Step 3: Commit the synced file in shopify-fulfillment-tool**

```bash
cd shopify-fulfillment-tool
git add shared/theme.py
git commit -m "chore: sync shared/theme.py from packing-tool"
```

---

### Task 6: `packing-tool/src/theme.py` delegates to `shared.theme`

**Files:**
- Modify: `packing-tool/src/theme.py` (full rewrite — file shrinks from 124 lines to a thin wrapper)
- Delete: `packing-tool/src/styles_dark.qss`, `packing-tool/src/styles_light.qss`, `packing-tool/src/styles.qss`

**Interfaces:**
- Consumes: `shared.theme.apply_theme`, `shared.theme.THEME_DARK`/`THEME_LIGHT` names (new constants — see Step 1).
- Produces: `apply_theme(app, theme=THEME_DARK)`, `load_saved_theme(app) -> str`, `toggle_theme(app) -> str`, `THEME_DARK`, `THEME_LIGHT` — **unchanged signatures**, so `packing-tool/src/main.py:52`'s `from theme import load_saved_theme, toggle_theme` needs no change.

- [ ] **Step 1: Add THEME_DARK/THEME_LIGHT constants to shared/theme.py**

The two apps' current modules both define `THEME_DARK = "dark"` / `THEME_LIGHT = "light"` (or the shopify-tool equivalent string literals) — hoist these into `shared.theme` too so both apps import the same constants instead of each redefining them.

```python
# add near the top of packing-tool/shared/theme.py, after the imports:
THEME_DARK = "dark"
THEME_LIGHT = "light"
```

Run: `cd packing-tool && python shared/theme.py` (re-run self-check, still passes — pure addition)

- [ ] **Step 2: Rewrite packing-tool/src/theme.py**

```python
# packing-tool/src/theme.py
"""Theme manager for Packing Tool — thin wrapper over shared.theme.

Kept as its own module (rather than importing shared.theme directly at
every call site) so packing-tool/src/main.py's existing
`from theme import load_saved_theme, toggle_theme` keeps working unchanged.
"""

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from shared.theme import apply_theme as _apply_theme, THEME_DARK, THEME_LIGHT

__all__ = ["THEME_DARK", "THEME_LIGHT", "apply_theme", "load_saved_theme", "toggle_theme"]


def apply_theme(app: QApplication, theme: str = THEME_DARK) -> None:
    _apply_theme(app, theme)
    settings = QSettings("PackingTool", "Theme")
    settings.setValue("current_theme", theme)


def load_saved_theme(app: QApplication) -> str:
    settings = QSettings("PackingTool", "Theme")
    theme = settings.value("current_theme", THEME_DARK)
    apply_theme(app, theme)
    return theme


def toggle_theme(app: QApplication) -> str:
    settings = QSettings("PackingTool", "Theme")
    current = settings.value("current_theme", THEME_DARK)
    new_theme = THEME_LIGHT if current == THEME_DARK else THEME_DARK
    apply_theme(app, new_theme)
    return new_theme
```

- [ ] **Step 3: Delete the now-unused qss files**

Run: `cd packing-tool && git rm src/styles_dark.qss src/styles_light.qss src/styles.qss`
Expected: three files staged for deletion

- [ ] **Step 4: Run the existing test suite**

Run: `cd packing-tool && python -m pytest tests/ -v`
Expected: PASS, same test count as before this task (theme.py has no existing tests to break)

- [ ] **Step 5: Manual smoke check**

Run: `cd packing-tool && python src/main.py`
Expected: app launches, window shows the dark theme (black background, white borders) matching what `styles_dark.qss` used to produce; toggling theme (if there's a UI control) switches to light without errors in the console.

- [ ] **Step 6: Commit**

```bash
cd packing-tool
git add src/theme.py shared/theme.py
git commit -m "refactor: delegate packing-tool theme.py to shared.theme, drop qss files"
```

---

### Task 7: `shopify-fulfillment-tool/gui/theme_manager.py` delegates to `shared.theme`

**Files:**
- Modify: `shopify-fulfillment-tool/gui/theme_manager.py` (rewritten internals — public class/API unchanged)

**Interfaces:**
- Consumes: `shared.theme.get_theme`, `build_stylesheet`, `build_palette`, `ThemeTokens` (as the return type of `get_current_theme()`).
- Produces: **unchanged public API** — `get_theme_manager() -> ThemeManager`, `ThemeManager.get_current_theme() -> ThemeTokens` (was `ThemeColors` — field-compatible, see Global Constraints), `.is_dark_theme()`, `.get_current_theme_name()`, `.toggle_theme()`, `.set_theme(name)`, `.apply_theme()`, signal `theme_changed`. Verified against all 18 files importing `get_theme_manager` (Task 8's file list) — none of them import `ThemeColors`/`LightTheme`/`DarkTheme` directly, only `get_theme_manager`.

- [ ] **Step 1: Rewrite theme_manager.py**

```python
# shopify-fulfillment-tool/gui/theme_manager.py
"""Theme Manager - thin wrapper over shared.theme.

Public API (get_theme_manager(), ThemeManager.get_current_theme(), etc.)
is unchanged from before unification — see shared.theme for the actual
token definitions and stylesheet/palette builders.
"""

import logging
from typing import Optional
from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtWidgets import QApplication

from shared.theme import ThemeTokens, get_theme, build_stylesheet, build_palette

logger = logging.getLogger(__name__)


class ThemeManager(QObject):
    """Manages application themes (singleton). See shared.theme for tokens."""

    theme_changed = Signal()
    _instance: Optional["ThemeManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True
        self._current_theme_name = "light"
        self._load_theme_preference()
        logger.info(f"ThemeManager initialized with theme: {self._current_theme_name}")

    def get_current_theme(self) -> ThemeTokens:
        return get_theme(self._current_theme_name)

    def is_dark_theme(self) -> bool:
        return self._current_theme_name == "dark"

    def get_current_theme_name(self) -> str:
        return self._current_theme_name

    def toggle_theme(self):
        self.set_theme("dark" if self._current_theme_name == "light" else "light")

    def set_theme(self, theme_name: str):
        if theme_name not in ("light", "dark"):
            logger.warning(f"Unknown theme: {theme_name}, using light theme")
            theme_name = "light"
        if theme_name == self._current_theme_name:
            return
        self._current_theme_name = theme_name
        self._save_theme_preference()
        self.apply_theme()
        self.theme_changed.emit()
        logger.info(f"Theme changed to: {theme_name}")

    def apply_theme(self):
        app = QApplication.instance()
        if app is None:
            logger.warning("QApplication not found, cannot apply theme")
            return
        theme = self.get_current_theme()
        app.setStyleSheet(build_stylesheet(theme))
        app.setPalette(build_palette(theme))
        logger.debug(f"Applied {self._current_theme_name} theme globally")

    def _save_theme_preference(self):
        try:
            settings = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
            settings.setValue("theme", self._current_theme_name)
            settings.sync()
        except Exception as e:
            logger.error(f"Failed to save theme preference: {e}")

    def _load_theme_preference(self):
        try:
            settings = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
            saved_theme = settings.value("theme", "light")
            self._current_theme_name = saved_theme if saved_theme in ("light", "dark") else "light"
        except Exception as e:
            logger.error(f"Failed to load theme preference: {e}")
            self._current_theme_name = "light"


_theme_manager_instance: Optional[ThemeManager] = None


def get_theme_manager() -> ThemeManager:
    global _theme_manager_instance
    if _theme_manager_instance is None:
        _theme_manager_instance = ThemeManager()
    return _theme_manager_instance
```

- [ ] **Step 2: Run lint**

Run: `cd shopify-fulfillment-tool && ruff check gui/theme_manager.py`
Expected: no errors

- [ ] **Step 3: Run the existing headless smoke test**

Run: `cd shopify-fulfillment-tool && CI=1 python run_dev.py`
Expected: exits cleanly (same as before this change — confirms every one of the ~180 `theme.xxx` call sites still resolves, since `ThemeTokens` field names match the old `ThemeColors` exactly)

- [ ] **Step 4: Manual visual check**

Run: `cd shopify-fulfillment-tool && python gui_main.py`
Expected: app launches; toggle theme (if exposed in UI, or via Settings) between light/dark — light now shows near-black borders/text instead of the old soft gray, dark looks the same as before.

- [ ] **Step 5: Commit**

```bash
cd shopify-fulfillment-tool
git add gui/theme_manager.py
git commit -m "refactor: delegate theme_manager.py to shared.theme"
```

---

### Task 8: Remove the two flagged info banners

**Files:**
- Modify: `shopify-fulfillment-tool/gui/column_mapping_widget.py:98-106`
- Modify: `shopify-fulfillment-tool/gui/settings_window_pyside.py:451-463`

**Interfaces:** none (pure deletions).

- [ ] **Step 1: Remove the CSV-mapping example banner**

In `gui/column_mapping_widget.py`, delete lines 98-106 entirely (the `help_text` QLabel block, including its hardcoded-color `setStyleSheet` call — this also removes one of the 75 hardcoded-color instances tracked in Task 9, so skip this file when doing that pass):

```python
# DELETE this whole block (was directly after `layout.addWidget(scroll)`):
#
#         # Help text at bottom
#         help_text = QLabel(
#             "ℹ️ Enter the exact column names as they appear in your CSV file.\n"
#             "Example: 'Name' → 'Order_Number' means your CSV has a 'Name' column "
#             "that will be used for order numbers."
#         )
#         help_text.setWordWrap(True)
#         help_text.setStyleSheet("background-color: #e8f4f8; padding: 10px; border-radius: 5px; font-size: 9pt;")
#         layout.addWidget(help_text)
```

Because `ColumnMappingWidget` is instantiated twice on the same dialog (once for Orders mapping, once for Stock mapping — confirmed via `grep -c` showing only one definition in source but two renders on screen per the original screenshots), this single deletion removes both banners the user saw.

- [ ] **Step 2: Remove the "templates no longer used" note**

In `gui/settings_window_pyside.py`, delete lines 451-463 (the `info_box` QGroupBox block inside `create_general_tab()`):

```python
# DELETE this whole block (was directly after `main_layout.addWidget(settings_box)`):
#
#         # Info about removed fields
#         info_box = QGroupBox("Note")
#         info_layout = QVBoxLayout(info_box)
#         info_label = QLabel(
#             "Templates and custom output directories are no longer used.\n"
#             "All reports are now generated in session-specific folders automatically."
#         )
#         info_label.setWordWrap(True)
#         from gui.theme_manager import get_theme_manager
#         theme = get_theme_manager().get_current_theme()
#         info_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
#         info_layout.addWidget(info_label)
#         main_layout.addWidget(info_box)
```

- [ ] **Step 3: Grep both apps for similar leftover banners**

Run:
```bash
grep -rn "ℹ️\|QGroupBox(\"Note\")\|no longer used\|Example:" shopify-fulfillment-tool/gui/*.py packing-tool/src/*.py packing-tool/src/**/*.py 2>/dev/null
```
Expected: review each hit manually. Remove any that are clearly the same pattern (a static instructional/deprecation banner with no other function). Do not remove tooltips (`setToolTip`) or inline validation feedback — those are functional, not leftover instructional clutter.

- [ ] **Step 4: Run lint and smoke test**

Run: `cd shopify-fulfillment-tool && ruff check gui/column_mapping_widget.py gui/settings_window_pyside.py && CI=1 python run_dev.py`
Expected: no lint errors, smoke test exits cleanly

- [ ] **Step 5: Commit**

```bash
cd shopify-fulfillment-tool
git add gui/column_mapping_widget.py gui/settings_window_pyside.py
git commit -m "fix: remove leftover instructional/deprecation info banners"
```

---

### Task 9: Remove hardcoded colors in shopify-fulfillment-tool

**Files:**
- Modify: `gui/settings_window_pyside.py`, `gui/pandas_model.py`, `gui/add_product_dialog.py`, `gui/client_sidebar.py`, `gui/client_settings_dialog.py`, `gui/tag_categories_dialog.py`, `gui/rule_test_dialog.py`, `gui/background_worker.py`, `gui/ui_manager.py`, `gui/log_viewer.py`, `gui/groups_management_dialog.py`, `gui/report_selection_dialog.py`, `gui/barcode_generator_widget.py`, `gui/tag_management_panel.py`, `gui/session_browser_widget.py`

**Interfaces:** none new — every call site already has `from gui.theme_manager import get_theme_manager` available or one import away.

- [ ] **Step 1: Get the current full list of offending lines**

Run:
```bash
cd shopify-fulfillment-tool
grep -rnE "#[0-9A-Fa-f]{3,6}" gui/*.py | grep -v theme_manager.py
```
Expected: ~74 lines (75 minus the one removed in Task 8, Step 1). Save this output — it's your worklist.

- [ ] **Step 2: Fix each hit using the semantic mapping**

For each hit, replace the hardcoded hex with the matching theme token, adding `theme = get_theme_manager().get_current_theme()` at the top of the enclosing method if not already present. Use this color→token mapping (derived from the actual semantic meaning of each hardcoded value found in the codebase):

| Hardcoded hex | Token |
|---|---|
| `#4CAF50`, `#45a049` | `theme.accent_green` |
| `#f44336`, `#F44336` | `theme.accent_red` |
| `#FF9800`, `#ff9800` | `theme.accent_orange` |
| `#2196F3` | `theme.accent_blue` |
| `#666`, `#999`, `#888` | `theme.text_secondary` |
| `#ccc`, `#ddd` | `theme.border_subtle` |
| `#ffebee` (light-red background) | leave as a literal *tint* — background tints for validation states aren't in `ThemeTokens` (out of scope per the spec's "no new fields beyond what's needed" — flag with a `# ponytail:` comment instead of inventing a new token for a handful of call sites) |

Example fix (from `settings_window_pyside.py:583`):

```python
# before
delete_rule_btn.setStyleSheet("background-color: #f44336; color: white;")

# after
theme = get_theme_manager().get_current_theme()
delete_rule_btn.setStyleSheet(f"background-color: {theme.accent_red}; color: white;")
```

Work through the worklist file by file. For validation-state background tints (like `#ffebee`/`#fff3e0` found around line 1099-1112 of `settings_window_pyside.py`), leave the literal but add a comment:

```python
# ponytail: literal validation-tint color, not worth a new ThemeTokens field
# for ~4 call sites; revisit if more validation states are added.
value_widget.setStyleSheet(f"border: 1px solid {theme.accent_red}; background-color: #ffebee;")
```

- [ ] **Step 3: Re-run the grep to confirm the sweep is complete**

Run: `cd shopify-fulfillment-tool && grep -rnE "#[0-9A-Fa-f]{3,6}" gui/*.py | grep -v theme_manager.py`
Expected: only the `# ponytail:`-flagged validation-tint lines remain (a handful, all explicitly justified), nothing else.

- [ ] **Step 4: Lint and smoke test**

Run: `cd shopify-fulfillment-tool && ruff check gui/ && CI=1 python run_dev.py`
Expected: no errors, clean exit

- [ ] **Step 5: Manual visual check in both themes**

Run: `cd shopify-fulfillment-tool && python gui_main.py`
Expected: open Settings window, Add Product dialog, Tag Categories dialog, Session Browser — toggle light/dark — no color looks out of place or fails to switch with the theme.

- [ ] **Step 6: Commit**

```bash
cd shopify-fulfillment-tool
git add gui/
git commit -m "fix: route hardcoded colors through theme tokens"
```

---

### Task 10: Window-geometry persistence in both main windows

**Files:**
- Modify: `packing-tool/src/main.py:168` (constructor), `:1232` (`closeEvent`)
- Modify: `shopify-fulfillment-tool/gui/main_window_pyside.py:74` (constructor), `:1485` (`closeEvent`)

**Interfaces:**
- Consumes: `shared.theme.save_window_geometry`, `restore_window_geometry` (Task 4).

- [ ] **Step 1: Wire it into packing-tool's MainWindow**

In `packing-tool/src/main.py`, replace the fixed `self.resize(1024, 768)` at line 168 with a restore-or-default:

```python
# before (line 168)
self.resize(1024, 768)

# after
from shared.theme import save_window_geometry, restore_window_geometry
self._geometry_settings = QSettings("PackingTool", "MainWindowGeometry")
if not restore_window_geometry(self, self._geometry_settings):
    self.resize(1024, 768)
```

(`QSettings` is already imported at the top of `main.py` — see line 30 — so only the `shared.theme` import is new.)

In `closeEvent` (starts at line 1232), add the save call as the first step, before the existing numbered cleanup steps:

```python
# add at the top of closeEvent's try block, before "# 1. Stop heartbeat timer"
try:
    save_window_geometry(self, self._geometry_settings)
except Exception as e:
    logger.warning(f"Failed to save window geometry: {e}")
```

- [ ] **Step 2: Wire it into shopify-tool's MainWindow**

In `shopify-fulfillment-tool/gui/main_window_pyside.py`, replace the fixed `self.setGeometry(100, 100, 1100, 900)` at line 74:

```python
# before (line 74)
self.setGeometry(100, 100, 1100, 900)

# after
from shared.theme import save_window_geometry, restore_window_geometry
from PySide6.QtCore import QSettings
self._geometry_settings = QSettings("ShopifyFulfillmentTool", "MainWindowGeometry")
if not restore_window_geometry(self, self._geometry_settings):
    self.setGeometry(100, 100, 1100, 900)
```

In `closeEvent` (line 1485), add the save call before `event.accept()`:

```python
def closeEvent(self, event):
    """Handles the application window being closed.
    ...
    """
    from shared.theme import save_window_geometry
    try:
        save_window_geometry(self, self._geometry_settings)
    except Exception as e:
        logger.warning(f"Failed to save window geometry: {e}")
    # Session data is now managed by SessionManager on the server
    # No need to save local session files
    event.accept()
```

- [ ] **Step 3: Manual verification (both apps)**

Run each app, resize/move the window, close it, relaunch:
```bash
cd packing-tool && python src/main.py
cd shopify-fulfillment-tool && python gui_main.py
```
Expected: window reopens at the size/position it was closed at, in both apps.

- [ ] **Step 4: Run existing test suites**

Run: `cd packing-tool && python -m pytest tests/ -v`
Expected: PASS (no existing test touches `MainWindow.__init__`'s geometry line — confirm none newly fail)

Run: `cd shopify-fulfillment-tool && ruff check gui/main_window_pyside.py && CI=1 python run_dev.py`
Expected: no errors, clean exit

- [ ] **Step 5: Commit**

```bash
cd packing-tool && git add src/main.py && git commit -m "feat: persist and restore main window geometry"
cd ../shopify-fulfillment-tool && git add gui/main_window_pyside.py && git commit -m "feat: persist and restore main window geometry"
```

---

### Task 11: Packing Tool — Session Browser redesign (StatusDot + consolidated action bar)

**Files:**
- Modify: `packing-tool/src/session_browser/sessions_list_widget.py`

**Interfaces:**
- Consumes: `shared.theme.StatusDot` (Task 4).
- Produces: no external API change — `SessionsListWidget`'s public signals (`resume_session_requested`, `start_packing_requested`) and its constructor signature are unchanged.

- [ ] **Step 1: Drop icon from STATUS_CONFIG, keep color**

```python
# in sessions_list_widget.py, replace STATUS_CONFIG (lines 38-46):

STATUS_CONFIG = {
    "not_started":  {"label": "Not Started",  "color": "#4A90D9"},
    "in_progress":  {"label": "Active",        "color": "#27AE60"},
    "stale":        {"label": "Stale",         "color": "#E67E22"},
    "paused":       {"label": "Paused",        "color": "#F1C40F"},
    "completed":    {"label": "Completed",     "color": "#2ECC71"},
    "incomplete":   {"label": "Incomplete",    "color": "#E74C3C"},
    "abandoned":    {"label": "Abandoned",     "color": "#C0392B"},
}
```

Update `_status_display()` (line 138-140) to drop the icon:

```python
def _status_display(status: str) -> str:
    cfg = STATUS_CONFIG.get(status, {"label": status.replace("_", " ").title()})
    return cfg["label"]
```

- [ ] **Step 2: Use StatusDot in the table's status cell**

The table currently sets a plain `QTableWidgetItem(f"{cfg['icon']} {cfg['label']}")` for the status column (around line 412). `QTableWidget` cells can't embed a widget directly in a `QTableWidgetItem`, so use `setCellWidget` for the status column instead — pairing a `StatusDot` with a `QLabel` in a small container:

```python
# add import at the top of sessions_list_widget.py
from shared.theme import StatusDot

# add this helper method to SessionsListWidget
def _make_status_cell(self, status: str) -> QWidget:
    cfg = STATUS_CONFIG.get(status, {"label": status.replace("_", " ").title(), "color": "#888888"})
    cell = QWidget()
    layout = QHBoxLayout(cell)
    layout.setContentsMargins(8, 0, 4, 0)
    layout.setSpacing(6)
    layout.addWidget(StatusDot(cfg["color"]))
    layout.addWidget(QLabel(cfg["label"]))
    layout.addStretch()
    return cell
```

Find the line that currently does (around line 412):
```python
status_item = QTableWidgetItem(f"{cfg['icon']} {cfg['label']}")
```
and the surrounding code that does `self._table.setItem(row, COL_STATUS, status_item)`. Replace that assignment with:
```python
self._table.setCellWidget(row, COL_STATUS, self._make_status_cell(entry.get("status", "")))
```
Keep sorting working by also setting a hidden sort-key item — `QTableWidgetItem` still needs to exist for the sort role even though the visible widget is the cell widget:
```python
sort_item = QTableWidgetItem()
sort_item.setData(Qt.ItemDataRole.DisplayRole, STATUS_CONFIG.get(entry.get("status", ""), {}).get("label", ""))
self._table.setItem(row, COL_STATUS, sort_item)
self._table.setCellWidget(row, COL_STATUS, self._make_status_cell(entry.get("status", "")))
```

Also update the status filter combo (around line 205-207), which currently builds its items with the icon:
```python
# before
for key, cfg in STATUS_CONFIG.items():
    self._status_combo.addItem(f"{cfg['icon']} {cfg['label']}", key)

# after
for key, cfg in STATUS_CONFIG.items():
    self._status_combo.addItem(cfg["label"], key)
```

- [ ] **Step 3: Consolidate the two button rows into one action bar**

Replace the `_preview_box` (QGroupBox, lines 271-288) and the separate `action_layout` (lines 290-302) with a single toolbar row. Delete both blocks and replace with:

```python
# Consolidated action bar (replaces the old preview QGroupBox + separate
# action_layout — see 2026-07-26-unified-ui-design-system-design.md)
action_bar = QHBoxLayout()
action_bar.setSpacing(8)

self._preview_label = QLabel("Select a row for quick info")
self._preview_label.setWordWrap(True)
action_bar.addWidget(self._preview_label, 1)

self._preview_action_btn = QPushButton()
self._preview_action_btn.setVisible(False)
self._preview_action_btn.clicked.connect(self._on_preview_action)
action_bar.addWidget(self._preview_action_btn)

self._preview_details_btn = QPushButton("View Details")
self._preview_details_btn.setVisible(False)
self._preview_details_btn.clicked.connect(self._on_preview_details)
action_bar.addWidget(self._preview_details_btn)

divider = QFrame()
divider.setFrameShape(QFrame.Shape.VLine)
divider.setFrameShadow(QFrame.Shadow.Sunken)
action_bar.addWidget(divider)

self._export_csv_btn = QPushButton("Export CSV")
self._export_csv_btn.clicked.connect(self._export_csv)
action_bar.addWidget(self._export_csv_btn)

self._export_excel_btn = QPushButton("Export Excel")
self._export_excel_btn.clicked.connect(self._export_excel)
action_bar.addWidget(self._export_excel_btn)

self._refresh_btn = QPushButton("Refresh")
self._refresh_btn.clicked.connect(self.refresh)
action_bar.addWidget(self._refresh_btn)

main_layout.addLayout(action_bar)
```

Remove the now-dead `self._preview_box.setMaximumHeight(120)` line and the `QGroupBox`/`preview_layout` construction that preceded it — they're fully replaced by `action_bar` above. `self._preview_label`, `self._preview_action_btn`, `self._preview_details_btn` keep the same names so `_on_row_selected`, `_on_preview_action`, `_on_preview_details` (which reference `self._preview_label.setText(...)` etc. elsewhere in the file) need no changes.

- [ ] **Step 4: Tidy the filter row's search placeholder (drop the emoji)**

```python
# line 228, before
self._search_input.setPlaceholderText("🔍  Search list, session, worker…")

# after
self._search_input.setPlaceholderText("Search list, session, worker…")
```

- [ ] **Step 5: Run the existing test suite**

Run: `cd packing-tool && python -m pytest tests/ -v`
Expected: PASS (no existing test targets `SessionsListWidget`'s internals directly per the current `tests/` listing — confirm no new failures)

- [ ] **Step 6: Manual visual check**

Run: `cd packing-tool && python src/main.py`, open Session Browser for a client with sessions.
Expected: status column shows a colored dot + text (no emoji), one action bar under the table (not two), search box has no magnifying-glass emoji, sorting by status column still works.

- [ ] **Step 7: Commit**

```bash
cd packing-tool
git add src/session_browser/sessions_list_widget.py
git commit -m "refactor: consolidate Session Browser action bar, StatusDot instead of emoji"
```

---

### Task 12: Packing Tool — Packer Mode restructure

**Files:**
- Modify: `packing-tool/src/packer_mode_widget.py`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: no external API change — signals and public methods referenced by `main.py` (e.g. whatever connects to this widget) keep their names; only internal layout changes.

- [ ] **Step 1: Confirm the current public surface before touching layout**

Run: `cd packing-tool && grep -n "^    [a-z_]* = Signal\|def [a-z_]*(self" src/packer_mode_widget.py | head -30`
Note every public method/signal name here — Steps 2-4 must not rename any of them, only move where their widgets sit in the layout.

- [ ] **Step 2: Move the scanner input to the top of the left (main) panel**

In `_init_ui` (starts at line 70), the current order builds, in the left panel: `session_progress_bar`, `metadata_banner`, `table_frame` (order items table), then the bottom row (history + extras). The scanner input (`self.scanner_input`) currently lives in `_right_bottom` on the right column (around line 340).

Move the scanner-input construction (and its immediately-surrounding feedback label, if any — check the code between `self.scanner_input = ...` and its `addWidget` call) to right after `metadata_banner` is added to `left_layout` (currently line 117: `left_layout.addWidget(self.metadata_banner)`), and before `table_frame` is added (line 144: `left_layout.addWidget(self.table_frame)`):

```python
# after: left_layout.addWidget(self.metadata_banner)   (was line 117)
# insert a prominent scan row here, using the same self.scanner_input widget
# that used to live in the right column:
scan_row = QHBoxLayout()
scan_row.setSpacing(8)
scan_row.addWidget(self.scanner_input, 1)
left_layout.addLayout(scan_row)
# ... then continue with the existing table_frame construction/addWidget
```

Remove the old `right_layout.addWidget(_right_bottom)` block (around line 348) that previously placed `scanner_input` + `exit_button` at the bottom of the right column — `scanner_input` now lives in `scan_row` above. Keep `exit_button` on the right column (Step 4 covers where it ends up).

- [ ] **Step 3: Turn the right column into glance-only stat tiles + short lists**

Replace the right column's `scan_info_frame` internals (order status + feed) with compact stat tiles, and drop the `summary_frame`/`summary_table` from the right column entirely (it moves to a tab in Step 4). Also remove the dev-only `sim_group` scan simulator from the production layout (guard it behind a debug flag instead of always constructing it):

```python
# find the block that builds `sim_group` (around lines 240-256) and wrap its
# construction so it's opt-in for development only:
import os
if os.environ.get("PACKER_DEV_SIM"):
    sim_group = QGroupBox("Scan Simulator (dev)")
    sim_layout = QHBoxLayout(sim_group)
    # ... existing sim_input / sim_btn construction unchanged ...
    right_layout.addWidget(sim_group)
```

Add stat tiles above the existing `history`/`extras` short lists in the right column (these read from whatever attributes the widget already tracks for packed/total counts — check `_on_generation_complete`/scan-handling methods for the exact attribute names before wiring `setText`, since the plan can't know PackerModeWidget's internal counters without reading them at implementation time):

```python
# add near the top of right_layout construction, before scan_info_frame:
stats_row = QHBoxLayout()
self.packed_stat_label = QLabel("Packed: 0 / 0")
self.items_stat_label = QLabel("Items: 0 / 0")
for lbl in (self.packed_stat_label, self.items_stat_label):
    lbl.setStyleSheet("font-weight: bold;")
    stats_row.addWidget(lbl)
right_layout.addLayout(stats_row)
```
Wire `self.packed_stat_label.setText(...)`/`self.items_stat_label.setText(...)` wherever the widget currently updates order/item progress (find via `grep -n "setText\|progress" src/packer_mode_widget.py` and update the same call sites that currently update `session_progress_bar` — add a sibling `setText` call there).

- [ ] **Step 4: Move the summary table into a tab next to the order-items table**

Wrap the existing `table_frame` (order items) and the existing `summary_frame` (summary table) in a `QTabWidget` instead of stacking `summary_frame` in the right column:

```python
# replace:
#   frame_layout.addWidget(self.table)
#   left_layout.addWidget(self.table_frame)
#   ... (bottom_row with history/extras) ...
# with a tab container that holds table_frame as one tab and summary_frame as another:

self.main_tabs = QTabWidget()
self.main_tabs.addTab(self.table_frame, "Order Items")
self.main_tabs.addTab(self.summary_frame, "Session Summary")
left_layout.addWidget(self.main_tabs, 1)
left_layout.addWidget(_bottom_row)  # history/extras stay under the tabs, in the left column
```
`self.summary_frame` and `self.summary_table` keep their existing construction code (the `_sfl`/`summary_table` block, lines ~213-232) — only where the finished `summary_frame` is *added* changes, from `right_layout.addWidget(self.summary_frame)` to the tab above.

- [ ] **Step 5: Manual visual verification**

Run: `cd packing-tool && python src/main.py`, enter Packer Mode with a test session.
Expected: scanner input is the first thing visible under the metadata banner in the main pane; right column shows two stat numbers + history + extras, no summary table, no scan simulator (unless `PACKER_DEV_SIM=1` is set); "Order Items" / "Session Summary" tabs both show their respective tables at full width.

- [ ] **Step 6: Run the existing test suite**

Run: `cd packing-tool && python -m pytest tests/ -v`
Expected: PASS — `test_packer_logic_scanning.py`/`test_packer_logic_dataframe_integrity.py` etc. test `PackerLogic`, not the widget layout, so none should be affected by this UI-only change; confirm no new failures.

- [ ] **Step 7: Commit**

```bash
cd packing-tool
git add src/packer_mode_widget.py
git commit -m "refactor: restructure Packer Mode — scanner input to top, glance-only right rail, summary as tab"
```

---

### Task 13: Shopify Tool — de-duplicate Session Browser in the main window

**Files:**
- Modify: `shopify-fulfillment-tool/gui/ui_manager.py:307-338` (`_create_session_browser_panel`)

**Interfaces:**
- Consumes: `shopify_tool.session_manager.SessionManager.list_client_sessions(client_id, status_filter=None) -> List[Dict]` (existing method, each dict has `session_name`, `status`, `created_at`, `session_path` per `get_session_info`).
- Produces: no signal/API change — `self.mw.on_session_selected(session_path: str)` (existing handler, `main_window_pyside.py:891`) is still the thing clicking a recent session calls into.

- [ ] **Step 1: Replace `_create_session_browser_panel`'s body**

The current method (lines 307-338) builds a full `SessionBrowserWidget` inside a 40%-width splitter panel. Replace it with a compact "Recent Sessions" list showing the 5 most recent sessions for whichever client is currently selected, plus a link to the full browser on Tab 3:

```python
def _create_session_browser_panel(self):
    """Create right panel with a compact 'Recent Sessions' quick-pick.

    The full SessionBrowserWidget lives exclusively on Tab 3 ("Session
    Browser") — this panel used to embed a second full copy of it squeezed
    into 40% width, which was too narrow to be useful. See
    2026-07-26-unified-ui-design-system-design.md.
    """
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setSpacing(5)
    layout.setContentsMargins(10, 10, 10, 10)

    title = QLabel("Recent Sessions")
    title.setStyleSheet("font-size: 11pt; font-weight: bold;")
    layout.addWidget(title)

    self.mw.recent_sessions_list = QListWidget()
    self.mw.recent_sessions_list.itemDoubleClicked.connect(self._on_recent_session_double_clicked)
    layout.addWidget(self.mw.recent_sessions_list, 1)

    open_full_link = QPushButton("Open full Session Browser →")
    open_full_link.setFlat(True)
    open_full_link.clicked.connect(lambda: self.mw.main_tabs.setCurrentIndex(2))
    layout.addWidget(open_full_link)

    return panel


def _on_recent_session_double_clicked(self, item):
    session_path = item.data(Qt.ItemDataRole.UserRole)
    if session_path:
        self.mw.on_session_selected(session_path)


def refresh_recent_sessions(self, client_id: str):
    """Populate the Tab 1 quick-pick list — call this whenever the current
    client changes (wire into wherever current_client_id is set)."""
    self.mw.recent_sessions_list.clear()
    if not client_id:
        return
    sessions = self.mw.session_manager.list_client_sessions(client_id)[:5]
    for info in sessions:
        label = f"{info.get('session_name', '?')} — {info.get('status', '?')}"
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, info.get("session_path"))
        self.mw.recent_sessions_list.addItem(item)
```

Add the required imports at the top of `ui_manager.py` if not already present: `QListWidget`, `QListWidgetItem` from `PySide6.QtWidgets`, `Qt` from `PySide6.QtCore` (check existing import block first — `ui_manager.py` already imports heavily from `PySide6.QtWidgets`, likely just needs these two classes added to that import line).

- [ ] **Step 2: Wire `refresh_recent_sessions` into the client-selection flow**

Run: `cd shopify-fulfillment-tool && grep -n "current_client_id = \|def on_client_changed\|def _on_client_selected" gui/main_window_pyside.py gui/ui_manager.py`
Find the method that runs when the user picks a client (sets `self.current_client_id`), and add a call to `self.ui_manager.refresh_recent_sessions(client_id)` at the end of it, alongside whatever already refreshes the Tab 3 full browser for the new client.

- [ ] **Step 3: Manual visual verification**

Run: `cd shopify-fulfillment-tool && python gui_main.py`
Expected: Tab 1 ("Session Setup") right side now shows a short list (≤5 rows) instead of a cramped full table; double-clicking a row opens that session the same way it did before; "Open full Session Browser →" switches to Tab 3, which still shows the complete, full-width browser.

- [ ] **Step 4: Lint and smoke test**

Run: `cd shopify-fulfillment-tool && ruff check gui/ui_manager.py gui/main_window_pyside.py && CI=1 python run_dev.py`
Expected: no errors, clean exit

- [ ] **Step 5: Commit**

```bash
cd shopify-fulfillment-tool
git add gui/ui_manager.py gui/main_window_pyside.py
git commit -m "refactor: replace duplicated Session Browser panel on Tab 1 with a Recent Sessions quick-pick"
```

---

### Task 14: Shopify Tool — Settings window: tabs → grouped left-nav

**Files:**
- Modify: `shopify-fulfillment-tool/gui/settings_window_pyside.py` (constructor around lines 180-200; the final `self.tab_widget.addTab(...)` line inside each of the 10 `create_*_tab` methods)

**Interfaces:**
- Consumes: nothing new.
- Produces: no change to any `create_*_tab()` method's *content* — only how the finished page gets registered. `self.tab_widget` changes type from `QTabWidget` to `QStackedWidget`; confirmed via `grep -n "self\.tab_widget\." settings_window_pyside.py` that `.addTab(...)` is the *only* way it's used elsewhere in the file (no `.setCurrentIndex`/`.currentChanged` call sites to update).

- [ ] **Step 1: Add the nav-group table and helper methods**

Add near the top of the `SettingsWindow` class (after `class SettingsWindow(...):` and before `__init__`):

```python
    # Grouped left-nav replacing the old 10-tab horizontal QTabWidget strip.
    # Group/order chosen to mirror VS Code's own Settings UI grouping.
    SETTINGS_NAV_GROUPS = [
        ("Data", ["General", "Mappings", "Column Config"]),
        ("Fulfillment Logic", ["Rules", "Sets", "Weight"]),
        ("Output", ["Packing Lists", "Stock Exports", "SKU Labels"]),
        ("Organization", ["Tag Categories"]),
    ]
```

Add these two methods anywhere in the class body (e.g. right after `__init__`):

```python
    def _add_settings_page(self, page: QWidget, name: str) -> None:
        """Register a settings page under `name`.

        Replaces the old `self.tab_widget.addTab(page, name)` calls — the
        10-tab horizontal strip is replaced by a grouped left-nav
        (_build_settings_nav) that looks up pages by this same name.
        """
        self.tab_widget.addWidget(page)
        self._page_index_by_name[name] = self.tab_widget.count() - 1

    def _build_settings_nav(self) -> None:
        """Populate the left-nav list from SETTINGS_NAV_GROUPS with
        non-selectable section headers, and wire selection to the stack."""
        for group_name, page_names in self.SETTINGS_NAV_GROUPS:
            header = QListWidgetItem(group_name.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setPointSize(max(font.pointSize() - 1, 7))
            font.setBold(True)
            header.setFont(font)
            self._settings_nav.addItem(header)
            for page_name in page_names:
                if page_name not in self._page_index_by_name:
                    continue
                item = QListWidgetItem(page_name)
                item.setData(Qt.ItemDataRole.UserRole, self._page_index_by_name[page_name])
                self._settings_nav.addItem(item)
        self._settings_nav.currentItemChanged.connect(self._on_settings_nav_changed)
        # Select the first real (non-header) entry
        for row in range(self._settings_nav.count()):
            if self._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable:
                self._settings_nav.setCurrentRow(row)
                break

    def _on_settings_nav_changed(self, current, _previous):
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.tab_widget.setCurrentIndex(index)
```

- [ ] **Step 2: Replace the QTabWidget construction in `__init__`**

```python
# before (around lines 185-200):
#         main_layout = QVBoxLayout(self)
#         self.tab_widget = QTabWidget()
#         main_layout.addWidget(self.tab_widget)
#
#         # Create all tabs
#         self.create_general_tab()
#         ... (10 calls) ...

# after:
main_layout = QVBoxLayout(self)
content_layout = QHBoxLayout()
main_layout.addLayout(content_layout)

self._settings_nav = QListWidget()
self._settings_nav.setFixedWidth(170)
self._settings_nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
content_layout.addWidget(self._settings_nav)

self.tab_widget = QStackedWidget()
content_layout.addWidget(self.tab_widget, 1)

self._page_index_by_name = {}

# Create all tabs (unchanged call order/method names)
self.create_general_tab()
self.create_rules_tab()
self.create_packing_lists_tab()
self.create_stock_exports_tab()
self.create_mappings_tab()
self.create_sets_tab()  # Sets/Bundles tab
self.create_weight_tab()  # Volumetric Weight tab
self.create_tag_categories_tab()  # Tag Categories tab
self.create_column_config_tab()  # Column Configuration tab
self.create_sku_labels_tab()     # SKU Label Printing tab

self._build_settings_nav()
```

- [ ] **Step 3: Update the 10 `addTab` call sites**

In each of the 10 `create_*_tab` methods, change the final line from `self.tab_widget.addTab(tab, "Name")` to `self._add_settings_page(tab, "Name")`. Exact lines to change (from the pre-change file):

```
line 467:  self.tab_widget.addTab(tab, "General")           -> self._add_settings_page(tab, "General")
line 494:  self.tab_widget.addTab(tab, "Rules")              -> self._add_settings_page(tab, "Rules")
line 1471: self.tab_widget.addTab(tab, "Packing Lists")      -> self._add_settings_page(tab, "Packing Lists")
line 1631: self.tab_widget.addTab(tab, "Stock Exports")      -> self._add_settings_page(tab, "Stock Exports")
line 1770: self.tab_widget.addTab(tab, "Mappings")           -> self._add_settings_page(tab, "Mappings")
line 1918: self.tab_widget.addTab(tab, "Sets")               -> self._add_settings_page(tab, "Sets")
line 2293: self.tab_widget.addTab(tab, "Weight")             -> self._add_settings_page(tab, "Weight")
line 3245: self.tab_widget.addTab(tab, "Tag Categories")     -> self._add_settings_page(tab, "Tag Categories")
line 3286: self.tab_widget.addTab(tab, "Column Config")      -> self._add_settings_page(tab, "Column Config")
line 3357: self.tab_widget.addTab(tab, "SKU Labels")         -> self._add_settings_page(tab, "SKU Labels")
```

(Line numbers may have shifted slightly from Task 8/9's edits to this same file — use `grep -n 'self.tab_widget.addTab'` to re-locate each one before editing rather than trusting these numbers blindly.)

Note: `create_weight_tab()` internally builds its own small `QTabWidget` for "Products"/"Boxes" (2 sub-tabs) — leave that inner QTabWidget as-is. It's a reasonable 2-tab strip, not the 10-tab problem this task fixes; only its own final `addTab` call into the *outer* `self.tab_widget` changes per the table above.

- [ ] **Step 4: Add missing imports**

At the top of `settings_window_pyside.py`, ensure `QListWidget`, `QListWidgetItem`, `QStackedWidget` are imported from `PySide6.QtWidgets` (add to the existing import block if not already present — the file already imports `QTabWidget` from the same module, so this is a same-line addition).

- [ ] **Step 5: Manual visual verification**

Run: `cd shopify-fulfillment-tool && python gui_main.py`, open Settings.
Expected: left side shows a grouped nav list (Data / Fulfillment Logic / Output / Organization headers, 10 clickable items total); clicking each one shows the same content the corresponding tab used to show; "Weight" still has its internal Products/Boxes sub-tabs; window resizes without the nav or content clipping.

- [ ] **Step 6: Lint and smoke test**

Run: `cd shopify-fulfillment-tool && ruff check gui/settings_window_pyside.py && CI=1 python run_dev.py`
Expected: no errors, clean exit

- [ ] **Step 7: Commit**

```bash
cd shopify-fulfillment-tool
git add gui/settings_window_pyside.py
git commit -m "refactor: replace Settings window's 10-tab strip with a grouped left-nav"
```

---

### Task 15: Emoji sweep and end-to-end manual verification

**Files:**
- Modify: `packing-tool/src/main.py`, `packing-tool/src/exceptions.py`, `packing-tool/src/session_lock_manager.py`, `packing-tool/src/session_browser/orders_tab.py`, `packing-tool/src/restore_session_dialog.py`, `packing-tool/src/packer_mode_widget.py`, `shopify-fulfillment-tool/gui/ui_manager.py`, `shopify-fulfillment-tool/gui/file_handler.py`
- No new files.

**Interfaces:** none — text/glyph changes only.

- [ ] **Step 1: Re-run the emoji audit to get the current worklist**

Run:
```bash
cd /home/cognitiveghost/Desktop/Projects
grep -rnoP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]" packing-tool/src/*.py packing-tool/src/**/*.py shopify-fulfillment-tool/gui/*.py shopify-fulfillment-tool/gui_main.py 2>/dev/null | sort
```
Expected: the ✅⚡🕐💻👤📋📦🌙☀️🔒 etc. hits from the original audit, minus whatever Tasks 11/12 already removed (search box 🔍, status dots 🟢🟡🟠🔵🔴, `📋  View Details` button).

- [ ] **Step 2: Remove decorative/colorful emoji, keep functional monochrome glyphs**

For each remaining hit, apply this rule: full-color/decorative emoji (✅⚡🕐💻👤📋📦🌙☀️🔒🟢🟡🟠🔵🔴) get deleted from the string (keep the surrounding text, just drop the glyph and any now-redundant leading space); plain monochrome symbols already in use elsewhere in the unified design (✓ ✕ ⚠ ☰ ⚙) can stay if they're load-bearing (e.g. a checkmark indicating success inline in a log message) — judge each one against its actual context, don't blanket-delete.

Example fix pattern (`packing-tool/src/exceptions.py`, error messages using 🕐💻👤 to label time/computer/user context):
```python
# before
message = f"🕐 Locked at: {locked_at}\n💻 PC: {pc_name}\n👤 User: {user}"

# after
message = f"Locked at: {locked_at}\nPC: {pc_name}\nUser: {user}"
```

Work through `main.py` (5×✅), `exceptions.py` (🕐💻👤❌), `session_lock_manager.py` (💻👤), `orders_tab.py` (⚡✓), `restore_session_dialog.py` (🔒📦⚠), `packer_mode_widget.py` (✓, if any remain after Task 12), and shopify-tool's `ui_manager.py` (🌙⚙☰☀ — these are the theme-toggle/sidebar/settings header icons; per the design spec these are borderline-acceptable structural glyphs, so leave them unless they visually clash with the new palette once you see it running) and `file_handler.py` (✓✗ — status glyphs, keep, they're monochrome and functional).

- [ ] **Step 3: Re-run the audit to confirm the sweep**

Run the same command from Step 1.
Expected: only the deliberately-kept monochrome glyphs (✓ ✕ ⚠ ☰ ⚙) remain, each one load-bearing (verify by reading its context one more time).

- [ ] **Step 4: Lint both apps**

Run: `cd packing-tool && python -m pytest tests/ -v` (confirm no string-matching test broke on the removed emoji — check `test_session_lock_manager.py` in particular, since it may assert on lock-conflict message content)
Run: `cd shopify-fulfillment-tool && ruff check gui/`

- [ ] **Step 5: End-to-end manual verification (both apps, both themes, multiple window sizes)**

This is the final checkpoint for the whole plan — walk through both apps checking everything built in Tasks 1-15 together:

```bash
cd packing-tool && python src/main.py
```
- Toggle light/dark — both themes show the new palette (light: near-black borders; dark: unchanged from before).
- Resize the window small, close, relaunch — reopens at the same size (Task 10).
- Open Session Browser — one action bar, status dots, no emoji in the status column (Task 11).
- Enter Packer Mode — scanner input at top, right rail is glance-only, Session Summary is a tab (Task 12).

```bash
cd shopify-fulfillment-tool && python gui_main.py
```
- Toggle light/dark — same palette check as above.
- Resize, close, relaunch — geometry restored (Task 10).
- Tab 1 shows "Recent Sessions" (≤5 rows), Tab 3 shows the full browser (Task 13).
- Open Settings — grouped left-nav, no 10-tab strip (Task 14).
- Open Column Mapping and General settings — no leftover example/note banners (Task 8).
- No colors visibly fail to switch between light/dark anywhere you clicked (Task 9).

Expected: every item above holds. If something doesn't, note which task's change is responsible and fix it before considering the plan complete — do not move on with a known-broken item.

- [ ] **Step 6: Commit**

```bash
cd packing-tool && git add -A && git commit -m "fix: remove decorative emoji, keep functional monochrome glyphs"
cd ../shopify-fulfillment-tool && git add -A && git commit -m "fix: remove decorative emoji, keep functional monochrome glyphs"
```

---

## Self-Review Notes

- **Spec coverage:** Shared theme module + sync (Tasks 1-7), hardcoded-color cleanup (Task 9), spacing scale (documented as `ThemeTokens.spacing_*` fields in Task 1, applied within the screens touched by Tasks 11-14 per the spec's explicit "no blanket rewrite" scope), window-geometry persistence (Tasks 4, 10), emoji policy (Tasks 11, 15), info banners (Task 8), and all four screen redesigns (Tasks 11-14) each map to a task. The spec's "out of scope" list (backend logic, full spacing rewrite, other tabs/dialogs) has no corresponding task, as intended.
- **Placeholder scan:** none found — every step has literal code, exact file/line references, and runnable verification commands. Task 12 and 13 note where an implementer must `grep` for the current attribute names (packed/item counters, client-change hook) rather than guessing them, because those are pre-existing internals this plan didn't invent — that's a pointer to a concrete command, not a "TBD".
- **Type consistency:** `ThemeTokens` field names (Task 1) are used identically in `build_stylesheet`/`build_palette` (Task 3), `theme_manager.py`'s `get_current_theme() -> ThemeTokens` (Task 7), and Task 9's color→token table. `StatusDot(color: str, diameter: int = 10, parent=None)` (Task 4) is called identically in Task 11 (`StatusDot(cfg["color"])`). `save_window_geometry(window, settings, key=...)`/`restore_window_geometry(window, settings, key=...) -> bool` (Task 4) are called identically in Task 10 for both apps. `_add_settings_page(page: QWidget, name: str)` (Task 14) is called with the same two-positional-argument shape at all 10 call sites listed in that task's Step 3.
