import pytest

from shared.theme import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeTokens,
    clamp_geometry,
    contrast_ratio,
    get_theme,
    validate_theme,
)


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


def test_contrast_ratio_extremes():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)


def test_contrast_ratio_is_symmetric():
    assert contrast_ratio("#006DB7", "#FFFFFF") == pytest.approx(
        contrast_ratio("#FFFFFF", "#006DB7")
    )


def test_contrast_ratio_matches_published_wcag_value():
    # #767676 on #FFFFFF is the canonical 4.54:1 example in the WCAG 2.1
    # docs -- if the sRGB linearisation is wrong this lands near 4.0 or 5.1.
    assert contrast_ratio("#767676", "#FFFFFF") == pytest.approx(4.54, abs=0.01)
