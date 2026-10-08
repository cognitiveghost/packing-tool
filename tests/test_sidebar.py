"""The shell's left column (spec 2026-10-08 section 6.2, mockup frames 2a-2e).

Never shown in these tests, so visibility is read with isHidden().
"""

import pytest

from gui.components.sidebar import ITEM_HEIGHT, SIDEBAR_WIDTH, Sidebar, initials
from shared import theme as shared_theme
from shared.icons import icon
from shared.navrail import RAIL_WIDTH
from shared.theme import current_theme_name, current_tokens, set_current


@pytest.fixture
def sidebar(qapp):
    widget = Sidebar()
    for name, label in (("clipboard-list", "Packing"), ("table", "Statistics"),
                        ("folder-open", "Sessions")):
        widget.rail.add_item(icon(name), label)
    yield widget
    widget.deleteLater()


@pytest.mark.parametrize("name, expected", [
    ("Desislava Ilieva", "DI"),
    ("Maria", "M"),
    ("ana maria de souza", "AM"),
    ("  ", ""),
    ("", ""),
])
def test_initials(name, expected):
    assert initials(name) == expected


def test_it_starts_expanded_at_200(sidebar):
    assert sidebar.is_expanded()
    assert sidebar.width() == SIDEBAR_WIDTH == 200
    assert not sidebar.title.isHidden()
    assert not sidebar.worker_card.isHidden()
    assert not sidebar.theme_segment.isHidden()
    assert not sidebar.connection_box.isHidden()
    assert sidebar.worker_rail_button.isHidden()
    assert sidebar.theme_toggle.isHidden()
    assert sidebar.connection_icon.isHidden()


def test_collapsed_is_the_56px_rail(sidebar):
    sidebar.set_expanded(False)
    assert not sidebar.is_expanded()
    assert sidebar.width() == RAIL_WIDTH == 56
    assert sidebar.title.isHidden()
    assert sidebar.worker_card.isHidden()
    assert sidebar.theme_segment.isHidden()
    assert sidebar.connection_box.isHidden()
    assert not sidebar.worker_rail_button.isHidden()
    assert not sidebar.theme_toggle.isHidden()
    assert not sidebar.connection_icon.isHidden()


@pytest.mark.parametrize("expanded", [True, False])
def test_every_destination_and_sku_mapping_is_44px_tall(sidebar, expanded):
    """Floor density. shared's NavRail ships 32px items; FloorNavRail overrides
    its private _shape, so this is the test that fails if a sync renames it."""
    sidebar.set_expanded(expanded)
    for index in range(3):
        assert sidebar.rail.button(index).height() == ITEM_HEIGHT == 44
    assert sidebar.sku_button.height() == 44


def test_the_worker_shows_initials_and_name(sidebar):
    sidebar.set_worker("Desislava Ilieva")
    assert sidebar.worker_avatar.text() == "DI"
    assert sidebar.worker_rail_button.text() == "DI"
    assert sidebar.worker_name.toolTip() == "Desislava Ilieva"
    assert sidebar.worker_rail_button.toolTip() == "Desislava Ilieva · Switch worker…"


def test_a_long_worker_name_does_not_widen_the_sidebar(sidebar):
    sidebar.set_worker("Maximiliana Konstantinopolska-Wolfeschlegelstein")
    assert sidebar.width() == SIDEBAR_WIDTH
    assert sidebar.worker_name.text().endswith("…")
    assert sidebar.worker_name.toolTip().startswith("Maximiliana")


@pytest.mark.parametrize("state, label, retry_hidden", [
    ("ok", "Server connected", True),
    ("checking", "Reconnecting…", True),
    ("down", "Server unreachable", False),
])
def test_each_connection_state(sidebar, state, label, retry_hidden):
    sidebar.set_connection(state, r"\\fs01\packer")
    assert sidebar.connection_label.text() == label
    assert sidebar.retry_button.isHidden() is retry_hidden
    assert sidebar.connection_icon.toolTip() == rf"{label} · \\fs01\packer"


def test_an_unknown_connection_state_fails_loudly(sidebar):
    with pytest.raises(KeyError):
        sidebar.set_connection("offline", "x")


def test_a_long_path_is_elided_and_kept_in_the_tooltip(sidebar):
    path = r"\\warehouse-fileserver-01.corp.example\fulfilment\packer-assistant\production"
    sidebar.set_connection("ok", path)
    assert sidebar.path_label.text() != path
    assert "…" in sidebar.path_label.text()
    assert sidebar.path_label.toolTip() == path
    assert sidebar.width() == SIDEBAR_WIDTH


def test_no_client_disables_the_destinations_and_sku_mapping(sidebar):
    sidebar.set_client_chosen(False)
    assert not any(sidebar.rail.button(i).isEnabled() for i in range(3))
    assert not sidebar.sku_button.isEnabled()
    sidebar.set_client_chosen(True)
    assert all(sidebar.rail.button(i).isEnabled() for i in range(3))
    assert sidebar.sku_button.isEnabled()


def test_the_footer_controls_emit(sidebar, qtbot):
    with qtbot.waitSignal(sidebar.skuMappingRequested, timeout=500):
        sidebar.sku_button.click()
    with qtbot.waitSignal(sidebar.switchWorkerRequested, timeout=500):
        sidebar.worker_link.click()
    with qtbot.waitSignal(sidebar.switchWorkerRequested, timeout=500):
        sidebar.worker_rail_button.click()
    with qtbot.waitSignal(sidebar.themeRequested, timeout=500) as dark:
        sidebar.dark_button.click()
    assert dark.args == ["dark"]
    sidebar.set_connection("down", "x")
    with qtbot.waitSignal(sidebar.retryRequested, timeout=500):
        sidebar.retry_button.click()
    with qtbot.waitSignal(sidebar.retryRequested, timeout=500):
        sidebar.connection_icon.click()


def test_the_collapsed_connection_glyph_only_retries_when_down(sidebar, qtbot):
    sidebar.set_connection("ok", "x")
    with qtbot.assertNotEmitted(sidebar.retryRequested):
        sidebar.connection_icon.click()


def test_the_theme_toggle_asks_for_the_other_theme(sidebar, qtbot):
    sidebar.set_theme_name("dark")
    assert sidebar.dark_button.isChecked()
    with qtbot.waitSignal(sidebar.themeRequested, timeout=500) as blocker:
        sidebar.theme_toggle.click()
    assert blocker.args == ["light"]


def test_it_restyles_on_a_theme_switch_and_keeps_its_state(sidebar):
    sidebar.set_connection("down", "x")
    before = current_theme_name()
    set_current("dark" if before == "light" else "light")
    try:
        assert current_tokens().surface_sunken in sidebar.styleSheet()
        assert current_tokens().status_danger_bg in sidebar.connection_box.styleSheet()
        assert not sidebar.retry_button.isHidden()
    finally:
        shared_theme._current = before
