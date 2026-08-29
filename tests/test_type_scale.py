"""The type scale is shared, so packing-tool can size a shared widget.

Ported from shopify-fulfillment-tool/tests/test_type_scale.py, which asserted
the same contract against gui/theme_manager.py before 8.6 moved it here.
"""
import pytest

from shared.theme import (
    DEFAULT_DENSITY,
    DENSITY_PROFILES,
    TYPE_SCALE,
    font_css,
    get_density,
    set_density,
    type_style,
)


@pytest.fixture(autouse=True)
def _restore_density():
    """Density is process-global; no test may leak floor into the next one."""
    before = get_density()
    yield
    set_density(before)


def test_packing_tool_ships_at_the_desk_default():
    assert DEFAULT_DENSITY == "desk"
    assert get_density() == "desk"


def test_font_css_is_a_qss_fragment():
    assert font_css("caption") == "font-size: 9pt; font-weight: normal;"
    assert font_css("heading") == "font-size: 14pt; font-weight: bold;"


def test_bold_can_be_overridden_per_call():
    assert font_css("caption", bold=True) == "font-size: 9pt; font-weight: bold;"


def test_floor_density_raises_body_and_caption_only():
    set_density("floor")
    assert type_style("caption").size_pt == 10
    assert type_style("body").size_pt == 12
    assert type_style("heading").size_pt == TYPE_SCALE["heading"].size_pt


def test_an_unknown_role_fails_loudly():
    with pytest.raises(KeyError):
        font_css("headline")


def test_an_unknown_density_fails_loudly():
    with pytest.raises(KeyError):
        set_density("aisle")


def test_density_padding_matches_the_spacing_tokens():
    """The profiles spell the spacing scale as literals; they must not drift."""
    for profile in DENSITY_PROFILES.values():
        assert profile.padding_v in (4, 8, 12)
        assert profile.padding_h in (4, 8, 12)
