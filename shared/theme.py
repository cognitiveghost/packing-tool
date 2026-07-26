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


if __name__ == "__main__":
    validate_theme(LIGHT_THEME)
    validate_theme(DARK_THEME)
    assert get_theme("dark") is DARK_THEME
    assert get_theme("light") is LIGHT_THEME
    assert get_theme("missing") is LIGHT_THEME
    print("shared/theme.py tokens self-check OK")
