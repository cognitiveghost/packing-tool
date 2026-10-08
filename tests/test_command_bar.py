"""The 60px bar above the pages (spec 2026-10-08 section 6.3, frames 2a-2e).

Visibility is read with isHidden(): the bar is never shown in these tests, so
isVisible() is False for everything.
"""

import pytest

from gui.command_bar import BAR_HEIGHT, PAGES, CommandBar
from shared import theme as shared_theme
from shared.theme import current_theme_name, current_tokens, set_current


@pytest.fixture
def bar(qapp):
    widget = CommandBar()
    widget.set_client_chosen(True)
    yield widget
    widget.deleteLater()


def _shown_primaries(bar):
    buttons = (bar.open_session_button, bar.start_packing_button, bar.end_session_button)
    return [b.text() for b in buttons
            if not b.isHidden() and b.property("role") == "primary"]


def test_the_bar_is_floor_height(bar):
    assert bar.height() == BAR_HEIGHT == 60


def test_the_controls_run_in_the_mockups_order(bar):
    layout = bar.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    order = [w for w in order if w is not None]
    assert order == [
        bar.sidebar_button, bar.client_combo, bar.session_label, bar.filter_input,
        bar.open_session_button, bar.start_packing_button, bar.end_session_button,
        bar.overflow_button,
    ]


def test_there_is_no_sku_mapping_button(bar):
    """It moved to the sidebar footer."""
    assert not hasattr(bar, "sku_mapping_button")


def test_the_client_selector_is_250_wide_with_a_placeholder(bar):
    assert bar.client_combo.width() == 250
    assert bar.client_combo.placeholderText() == "Choose a client"


def test_no_session_offers_open_session_as_the_one_primary(bar):
    bar.set_page("packing")
    bar.set_session(None)
    assert _shown_primaries(bar) == ["Open session"]
    assert bar.session_label.isHidden()
    assert not bar.filter_input.isEnabled()
    assert bar.end_session_button.isHidden() and bar.start_packing_button.isHidden()


def test_a_session_offers_start_packing_as_the_one_primary(bar):
    bar.set_page("packing")
    bar.set_session("2026-09-01_1042")
    assert _shown_primaries(bar) == ["Start packing"]
    assert bar.session_label.text() == "2026-09-01_1042"
    assert not bar.session_label.isHidden()
    assert bar.filter_input.isEnabled()
    assert bar.open_session_button.isHidden()
    assert not bar.end_session_button.isHidden()
    assert bar.end_session_button.property("role") == "secondary"
    assert bar.end_shortcut_label.text() == "Ctrl+E"
    assert bar.start_packing_button.toolTip() == "Start packing · opens Packer Mode"


@pytest.mark.parametrize("page", ["statistics", "browser"])
def test_other_pages_carry_no_packing_actions(bar, page):
    bar.set_session("2026-09-01_1042")
    bar.set_page(page)
    assert _shown_primaries(bar) == []
    assert bar.filter_input.isHidden()
    assert bar.end_session_button.isHidden()


@pytest.mark.parametrize("page", PAGES)
def test_the_session_id_shows_on_every_page_while_a_session_is_open(bar, page):
    bar.set_session("2026-09-01_1042")
    bar.set_page(page)
    assert not bar.session_label.isHidden()
    bar.set_session(None)
    assert bar.session_label.isHidden()


@pytest.mark.parametrize("page", PAGES)
def test_toggle_client_picker_and_overflow_are_on_every_page(bar, page):
    bar.set_page(page)
    assert not bar.sidebar_button.isHidden()
    assert not bar.client_combo.isHidden()
    assert not bar.overflow_button.isHidden()


def test_the_filter_shrinks_before_it_is_cut_off(bar):
    assert bar.filter_input.minimumWidth() == 170
    assert bar.filter_input.maximumWidth() == 300


def test_open_session_is_disabled_without_a_client_and_says_why(bar):
    bar.set_client_chosen(False)
    assert not bar.open_session_button.isEnabled()
    assert bar.open_session_button.toolTip() == "Open session · choose a client first"
    bar.set_client_chosen(True)
    assert bar.open_session_button.isEnabled()
    assert bar.open_session_button.toolTip() == "Open session"


def test_an_unreachable_server_disables_open_and_end_and_says_why(bar):
    bar.set_server_reachable(False)
    assert not bar.open_session_button.isEnabled()
    assert bar.open_session_button.toolTip() == "Open session · server unreachable"
    bar.set_session("2026-09-01_1042")
    assert not bar.end_session_button.isEnabled()
    assert bar.end_session_button.toolTip() == "End session · server unreachable"
    bar.set_server_reachable(True)
    assert bar.end_session_button.isEnabled()
    assert bar.end_session_button.toolTip() == "End the current packing session"


def test_end_session_is_never_enabled_without_a_session(bar):
    bar.set_session(None)
    assert not bar.end_session_button.isEnabled()


def test_the_sidebar_button_emits_and_names_what_it_will_do(bar, qtbot):
    assert bar.sidebar_button.toolTip() == "Collapse sidebar"
    with qtbot.waitSignal(bar.sidebarToggled, timeout=500):
        bar.sidebar_button.click()
    bar.set_sidebar_expanded(False)
    assert bar.sidebar_button.toolTip() == "Expand sidebar"


def test_an_unknown_page_fails_loudly(bar):
    with pytest.raises(KeyError):
        bar.set_page("stats")


def test_the_bar_sits_on_the_frame_plane_and_repaints_on_a_theme_switch(bar):
    before = current_theme_name()
    set_current("dark" if before == "light" else "light")
    try:
        tokens = current_tokens()
        assert f"background-color: {tokens.surface_sunken}" in bar.styleSheet()
    finally:
        # Put back exactly what was there: set_current() cannot express "no
        # theme applied yet", and leaving "light" behind broke a later test.
        shared_theme._current = before
