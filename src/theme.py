"""Theme manager for Packing Tool — thin wrapper over shared.theme.

Kept as its own module (rather than importing shared.theme directly at
every call site) so packing-tool/src/main.py's existing
`from theme import load_saved_theme, toggle_theme` keeps working unchanged.
"""

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from shared.theme import THEME_DARK, THEME_LIGHT, ThemeTokens, get_theme
from shared.theme import apply_theme as _apply_theme

__all__ = [
    "THEME_DARK", "THEME_LIGHT", "apply_theme", "current_tokens",
    "load_saved_theme", "toggle_theme",
]


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


def current_tokens() -> ThemeTokens:
    """The tokens for the theme currently applied.

    ponytail: read from QSettings on each call and never cached, so a widget
    styled at construction keeps its old colours until the window is rebuilt.
    That is the same staleness the hardcoded literals had, minus being wrong
    in one theme outright. Upgrade path when it bites: a themeChanged signal
    plus a restyle pass, which is 8.9's problem, not this task's.
    """
    settings = QSettings("PackingTool", "Theme")
    return get_theme(settings.value("current_theme", THEME_DARK))
