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
