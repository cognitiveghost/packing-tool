"""Theme manager for Packing Tool — thin wrapper over shared.theme.

Kept as its own module (rather than importing shared.theme directly at
every call site) so packing-tool/main.py's existing
`from gui.theme import load_saved_theme, toggle_theme` keeps working unchanged.
"""
from dataclasses import replace
from functools import lru_cache

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gui.fonts import load_bundled_fonts
from shared.theme import (
    THEME_DARK,
    THEME_LIGHT,
    ThemeTokens,
    build_palette,
    build_stylesheet,
    get_theme,
)

__all__ = [
    "THEME_DARK", "THEME_LIGHT", "apply_theme", "current_tokens",
    "load_saved_theme", "toggle_theme",
]


# The live theme name. apply_theme is the only write path -- toggle_theme and
# load_saved_theme both route through it -- so this cannot go stale, and it
# spares current_tokens() a QSettings read per table row on the scan path.
_current: str | None = None


def _tokens(theme_name: str) -> ThemeTokens:
    """shared.theme's tokens with the bundled family layered on, when available.

    Memoized because current_tokens() runs twice per table row on the scan
    path and replace() re-runs __init__ over all 50 fields every call.

    Only the success path is memoized: load_bundled_fonts() returns None
    before a QApplication exists, and caching that would leave the app on the
    fallback font for the rest of the process over one early call.
    """
    family = load_bundled_fonts()
    if family is None:          # no QApplication yet, or the TTF is missing
        return get_theme(theme_name)
    return _tokens_with_font(theme_name, family)


@lru_cache(maxsize=2)
def _tokens_with_font(theme_name: str, family: str) -> ThemeTokens:
    theme = get_theme(theme_name)
    return replace(theme, font_family=f"'{family}', {theme.font_family}")


def apply_theme(app: QApplication, theme: str = THEME_DARK) -> None:
    global _current
    tokens = _tokens(theme)
    app.setStyleSheet(build_stylesheet(tokens))
    app.setPalette(build_palette(tokens))
    QSettings("PackingTool", "Theme").setValue("current_theme", theme)
    _current = theme


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

    ponytail: returns the live tokens, but a widget already styled at
    construction keeps its old colours until the window is rebuilt. That is
    the same staleness the hardcoded literals had, minus being wrong in one
    theme outright. Upgrade path when it bites: a themeChanged signal plus a
    restyle pass, which is 8.9's problem, not this task's.
    """
    if _current is None:
        # Nothing applied yet (a dialog constructed before load_saved_theme,
        # or a test importing the module standalone).
        return _tokens(QSettings("PackingTool", "Theme")
                       .value("current_theme", THEME_DARK))
    return _tokens(_current)
