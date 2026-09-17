"""The Packing command bar: which controls a page shows, and one primary.

Visibility is read with isHidden(): the bar is never shown in these tests, so
isVisible() is False for everything.
"""

import pytest

from gui.command_bar import BAR_HEIGHT, PAGES, CommandBar
from shared.theme import current_theme_name, current_tokens, set_current


@pytest.fixture
def bar(qapp):
    widget = CommandBar()
    yield widget
    widget.deleteLater()


def _shown_primaries(bar):
    buttons = (
        bar.open_session_button,
        bar.start_packing_button,
        bar.sku_mapping_button,
        bar.end_session_button,
    )
    return [
        b.text()
        for b in buttons
        if not b.isHidden() and b.property("role") == "primary"
    ]


def test_the_bar_is_floor_height(bar):
    assert bar.height() == BAR_HEIGHT == 60


def test_no_session_offers_open_session_as_the_one_primary(bar):
    bar.set_page("packing")
    bar.set_session(None)
    assert _shown_primaries(bar) == ["Open session"]
    assert bar.session_label.text() == "No session"
    assert not bar.filter_input.isEnabled()
    assert bar.sku_mapping_button.isHidden() and bar.end_session_button.isHidden()


def test_a_session_offers_start_packing_as_the_one_primary(bar):
    bar.set_page("packing")
    bar.set_session("2026-09-01_1042")
    assert _shown_primaries(bar) == ["Start packing"]
    assert bar.session_label.text() == "2026-09-01_1042"
    assert bar.filter_input.isEnabled()
    assert not bar.sku_mapping_button.isHidden()
    assert not bar.end_session_button.isHidden()
    assert bar.end_session_button.property("role") != "danger"


@pytest.mark.parametrize("page", ["statistics", "browser"])
def test_other_pages_carry_no_packing_actions(bar, page):
    bar.set_session("2026-09-01_1042")
    bar.set_page(page)
    assert _shown_primaries(bar) == []
    assert bar.filter_input.isHidden()
    assert bar.sku_mapping_button.isHidden()


def test_the_browser_page_hides_the_session_id(bar):
    bar.set_session("2026-09-01_1042")
    bar.set_page("statistics")
    assert not bar.session_label.isHidden()
    bar.set_page("browser")
    assert bar.session_label.isHidden()


@pytest.mark.parametrize("page", PAGES)
def test_client_picker_and_overflow_are_on_every_page(bar, page):
    bar.set_page(page)
    assert not bar.client_combo.isHidden()
    assert not bar.overflow_button.isHidden()


def test_an_unknown_page_fails_loudly(bar):
    with pytest.raises(KeyError):
        bar.set_page("stats")


def test_the_bar_repaints_on_a_theme_switch(bar):
    before = current_theme_name() or "light"
    set_current("dark" if before == "light" else "light")
    try:
        assert current_tokens().surface_raised in bar.styleSheet()
    finally:
        set_current(before)
