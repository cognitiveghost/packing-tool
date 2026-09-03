"""Theme manager for Packing Tool — thin wrapper over shared.theme.

Kept as its own module (rather than importing shared.theme directly at
every call site) so packing-tool/main.py's existing
`from gui.theme import load_saved_theme, toggle_theme` keeps working unchanged.
"""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from shared.fonts import load_bundled_fonts
from shared.theme import (
    THEME_DARK,
    THEME_LIGHT,
    ThemeTokens,
    build_palette,
    build_stylesheet,
    current_theme_name,
    set_current,
    themed_tokens,
)

__all__ = [
    "THEME_DARK", "THEME_LIGHT", "apply_theme", "current_tokens",
    "load_saved_theme", "toggle_theme",
]


def apply_theme(app: QApplication, theme: str = THEME_DARK) -> None:
    tokens = themed_tokens(theme, load_bundled_fonts())
    app.setStyleSheet(build_stylesheet(tokens))
    app.setPalette(build_palette(tokens))
    QSettings("PackingTool", "Theme").setValue("current_theme", theme)
    # Last, and after the app sheet: shared.theme is now the single record of
    # which theme is live, and this emits theme_notifier.changed.
    set_current(theme)


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

    Not shared.theme.current_tokens(): that one deliberately omits the
    bundled family, and callers here read font_family off the tokens they
    get back.
    """
    name = current_theme_name()
    if name is None:
        # Nothing applied yet (a dialog constructed before load_saved_theme,
        # or a test importing the module standalone).
        name = QSettings("PackingTool", "Theme").value("current_theme", THEME_DARK)
    return themed_tokens(name, load_bundled_fonts())
