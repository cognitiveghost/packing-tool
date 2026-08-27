import dataclasses

import pytest

from shared.theme import (
    _ACCENT_FILLS,
    _COLOR_FIELDS,
    _SURFACE_PLANES,
    DARK_THEME,
    LIGHT_THEME,
    ThemeTokens,
    clamp_geometry,
    contrast_ratio,
    get_theme,
    validate_theme,
)


def test_dark_base_is_not_pure_black():
    # Pure black gives elevation nowhere to go: every raised plane can only
    # get lighter, and the first step reads as a smudge (spec 3.1). 8.1
    # lifted it again so the page sits above surface_sunken (spec 2/C1).
    assert DARK_THEME.surface == "#101014"
    assert LIGHT_THEME.surface == "#FFFFFF"


def test_border_is_the_missing_middle_and_the_old_value_survives():
    # border was pure text contrast (17.4:1) used for every box outline,
    # which is what made both apps look harsh (spec 3.3).
    assert LIGHT_THEME.border == "#858585"
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


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
@pytest.mark.parametrize("role", ["info", "success", "warning", "danger"])
def test_status_foregrounds_clear_aa_on_every_plane_and_their_own_tint(theme, role):
    """A badge has to be readable in a table, on a card and in a dialog
    alike. A test built from a single background per theme would pass green
    while every dialog failed AA -- which is what the spec's own first draft
    did (spec 3.4)."""
    fg = getattr(theme, f"status_{role}")
    backgrounds = [getattr(theme, plane) for plane in _SURFACE_PLANES]
    backgrounds.append(getattr(theme, f"status_{role}_bg"))
    for bg in backgrounds:
        assert contrast_ratio(fg, bg) >= 4.5, f"{theme.name} status_{role} on {bg}"


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
@pytest.mark.parametrize("token,floor", [
    ("text", 7.0),
    ("text_secondary", 4.5),
    ("text_disabled", 3.0),
    ("text_placeholder", 4.5),
    ("border", 3.0),
    ("focus_ring", 3.0),
    ("selection_border", 3.0),
])
def test_foreground_tokens_clear_their_floor_on_every_plane(theme, token, floor):
    value = getattr(theme, token)
    for plane in _SURFACE_PLANES:
        ratio = contrast_ratio(value, getattr(theme, plane))
        assert ratio >= floor, f"{theme.name}.{token} on {plane} = {ratio:.2f}"


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_on_accent_clears_aa_against_the_solid_fill(theme):
    # shared/theme.py paints white on accent_blue in five places and
    # build_palette pairs Highlight/HighlightedText the same way (spec 3.4a).
    assert contrast_ratio(theme.on_accent, theme.accent_fill) >= 4.5


def test_the_frame_plane_exists_and_is_part_of_the_matrix():
    """spec 2/C1: Depot's fourth plane. It is the app frame, the 56 px nav
    rail and the gutters -- regions separate by elevation instead of by a
    1 px border on every widget. Adding the token without adding it to
    _SURFACE_PLANES would leave it unvalidated, which is the whole failure
    mode 8.2 existed to end."""
    assert LIGHT_THEME.surface_sunken == "#E8E8EB"
    assert DARK_THEME.surface_sunken == "#08080B"
    assert _SURFACE_PLANES == (
        "surface_sunken", "surface", "surface_raised", "surface_overlay"
    )


def test_dark_page_plane_lifted_off_the_frame():
    """spec 2/C1: dark surface moves 0A0A0A -> 101014 so the page reads
    above surface_sunken without a border. Costs every foreground 0.2-0.4
    of ratio; the parametrized floor test below is what proves that is
    affordable."""
    assert DARK_THEME.surface == "#101014"
    assert DARK_THEME.background == "#101014"  # alias must move with it


def test_the_three_accent_fills_are_theme_independent():
    """spec 2/C4: a button fill sits on itself, not on a surface, so it
    needs no per-theme value."""
    for theme in (LIGHT_THEME, DARK_THEME):
        assert theme.accent_fill == "#006FBA"
        assert theme.accent_fill_hover == "#0A78C4"
        assert theme.accent_fill_active == "#005A9E"
    # Same tripwire the plane tuple gets above: both are derived from
    # _COLOR_FIELDS by prefix, so this fails if a fill is renamed out of the
    # matrix or a non-fill token wanders into it.
    assert _ACCENT_FILLS == ("accent_fill", "accent_fill_hover", "accent_fill_active")


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
@pytest.mark.parametrize("fill", ["accent_fill", "accent_fill_hover", "accent_fill_active"])
def test_on_accent_clears_aa_against_every_fill(theme, fill):
    """spec 7 test 2 -- the C4 class fix. #2D9FE8 shipped at 2.90:1 behind
    white because on_accent was proven against accent_fill alone while
    QPushButton:hover and :pressed swapped a different fill in behind the
    same label. Parametrizing over the fills is what closes the class."""
    assert contrast_ratio(theme.on_accent, getattr(theme, fill)) >= 4.5


def test_the_hover_aliases_now_resolve_to_the_active_fill():
    """spec 2/C4 + roadmap 8.1 Stage C: light was already #005A9E, so the
    re-point is a no-op there; dark is the 2.90:1 fix. Both aliases point
    at accent_fill_active because that is the value under which light does
    not move -- see D1 in the plan."""
    for theme in (LIGHT_THEME, DARK_THEME):
        assert theme.button_hover_light == theme.accent_fill_active
        assert theme.button_hover_dark == theme.accent_fill_active


def test_validate_theme_rejects_a_fill_that_fails_only_on_hover():
    """The exact shipped defect, as a regression test: a theme that passes
    on accent_fill and fails on the hover fill must raise.

    Only accent_fill_hover moves. Perturbing button_hover_* as well would
    trip the alias-drift check first -- it runs before the contrast loops --
    and the test would pass for the wrong reason.
    """
    regressed = dataclasses.replace(
        DARK_THEME, name="regressed",
        accent_fill_hover="#2D9FE8",           # 2.90:1 behind white
    )
    with pytest.raises(ValueError, match="accent_fill_hover"):
        validate_theme(regressed)


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_body_text_is_readable_on_a_selected_row(theme):
    assert contrast_ratio(theme.text, theme.selection_bg) >= 4.5


def test_validate_theme_rejects_a_status_colour_that_fails_on_a_dialog():
    """The exact silent failure 8.2 exists to end: a value that passes on
    the window background and fails on the overlay plane."""
    # #0075EE is 4.51:1 on dark surface -- a pass -- but 3.56:1 on
    # surface_overlay. A one-background check would call this fine.
    sunk = dataclasses.replace(DARK_THEME, name="sunk", status_info="#0075EE")
    with pytest.raises(ValueError, match="contrast"):
        validate_theme(sunk)


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


def test_built_stylesheet_names_no_css_colour():
    from shared.style_lint import _CSS_NAME
    from shared.theme import DARK_THEME, LIGHT_THEME, build_stylesheet
    for theme in (LIGHT_THEME, DARK_THEME):
        assert not _CSS_NAME.findall(build_stylesheet(theme))


def test_current_tokens_returns_the_applied_theme(qapp):
    from shared.theme import THEME_DARK, THEME_LIGHT, get_theme
    from theme import apply_theme, current_tokens
    apply_theme(qapp, THEME_LIGHT)
    assert current_tokens() is get_theme(THEME_LIGHT)
    apply_theme(qapp, THEME_DARK)
    assert current_tokens() is get_theme(THEME_DARK)
