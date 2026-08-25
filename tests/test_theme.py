import pytest

import dataclasses

from shared.theme import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeTokens,
    _ALIAS_PAIRS,
    _COLOR_FIELDS,
    clamp_geometry,
    contrast_ratio,
    get_theme,
    validate_theme,
)


def test_dark_base_is_not_pure_black():
    # Pure black gives elevation nowhere to go: every raised plane can only
    # get lighter, and the first step reads as a smudge (spec 3.1).
    assert DARK_THEME.surface == "#0A0A0A"
    assert LIGHT_THEME.surface == "#FFFFFF"


def test_border_is_the_missing_middle_and_the_old_value_survives():
    # border was pure text contrast (17.4:1) used for every box outline,
    # which is what made both apps look harsh (spec 3.3).
    assert LIGHT_THEME.border == "#868686"
    assert DARK_THEME.border == "#6D6D6D"
    assert LIGHT_THEME.border_strong == "#1A1A1A"
    assert DARK_THEME.border_strong == "#F2F2F2"


def test_accent_blue_aliases_the_fill_not_the_info_foreground():
    # A fill token sits behind white; a foreground token sits on a surface.
    # One value cannot serve both -- aliasing accent_blue to status_info
    # would ship every dark-mode primary button below AA (spec 3.4a).
    for theme in (LIGHT_THEME, DARK_THEME):
        assert theme.accent_blue == theme.accent_fill
        assert theme.accent_blue != theme.status_info


def test_status_colours_now_differ_per_theme():
    # They were dataclass defaults, so both themes rendered identical status
    # colours on opposite backgrounds -- the root cause of the light-mode
    # failure (spec 1).
    assert LIGHT_THEME.status_warning != DARK_THEME.status_warning
    assert LIGHT_THEME.status_success != DARK_THEME.status_success


def test_selection_no_longer_shares_a_value_with_success():
    # active_border was #4CAF50, the same green as success. Selection and
    # success are unrelated meanings; neither could be retuned (spec 3.5).
    for theme in (LIGHT_THEME, DARK_THEME):
        assert theme.selection_border != theme.status_success


def test_radius_and_spacing_scales_exist():
    assert (LIGHT_THEME.radius_sm, LIGHT_THEME.radius_md, LIGHT_THEME.radius_lg) == (3, 6, 10)
    assert LIGHT_THEME.spacing_2xl == 32
    assert LIGHT_THEME.radius == 4  # unchanged, still read by build_stylesheet


def test_every_colour_field_is_declared_per_theme_not_defaulted():
    """Spec 1's root cause: accent_* were dataclass defaults neither theme
    overrode. A default on a colour field silently reintroduces that."""
    defaulted = [
        f.name for f in dataclasses.fields(ThemeTokens)
        if f.name in _COLOR_FIELDS and f.default is not dataclasses.MISSING
    ]
    assert not defaulted, f"colour fields must not carry defaults: {defaulted}"


def test_get_theme_returns_correct_instance():
    assert get_theme("dark") is DARK_THEME
    assert get_theme("light") is LIGHT_THEME


def test_get_theme_falls_back_to_light_for_unknown_name():
    assert get_theme("nonsense") is LIGHT_THEME


def test_validate_theme_passes_for_both_builtin_themes():
    validate_theme(LIGHT_THEME)
    validate_theme(DARK_THEME)


def test_validate_theme_rejects_bad_hex():
    bad = dataclasses.replace(LIGHT_THEME, name="bad", surface="not-a-color")
    with pytest.raises(ValueError, match="not a valid #RRGGBB"):
        validate_theme(bad)


def test_validate_theme_rejects_a_drifted_alias():
    drifted = dataclasses.replace(LIGHT_THEME, name="drifted", accent_blue="#123456")
    with pytest.raises(ValueError, match="drifted from its canonical token"):
        validate_theme(drifted)


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
