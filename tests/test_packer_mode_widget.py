"""Packer Mode's Qt side: the bar, and the state the widget pushes.

The document itself is covered by tests/test_packer_bridge.py.
"""

import pytest

from gui.main_window import _session_seconds, _unmapped_choices
from gui.packer_mode_widget import PackerModeWidget


@pytest.fixture
def widget(qtbot):
    w = PackerModeWidget()
    qtbot.addWidget(w)
    return w


def test_a_finished_session_stops_the_scanner_and_names_itself(widget):
    widget.show_session_complete({"title": "Session complete", "body": "done."})
    assert widget.bridge.sessionEnd["body"] == "done."
    assert widget.scanner_input.isEnabled() is False
    assert widget.skip_order_button.isEnabled() is False


def test_the_per_order_reset_leaves_a_finished_session_alone(widget):
    """The last order schedules clear_screen 3s out. It used to wipe the panel
    that is the only way to end the session from this screen."""
    widget.show_session_complete({"title": "Session complete", "body": "done."})
    widget.clear_screen()
    assert widget.bridge.sessionEnd["body"] == "done."
    assert widget.scanner_input.isEnabled() is False


def test_ending_the_session_gives_the_document_back(widget):
    widget.show_session_complete({"title": "Session complete", "body": "done."})
    widget.reset_for_new_session()
    assert widget.bridge.sessionEnd == {}
    assert widget.scanner_input.isEnabled() is True
    assert widget._order_label.text() == "No order"


def test_the_panels_end_session_button_reaches_the_widgets_signal(qtbot, widget):
    with qtbot.waitSignal(widget.end_session_requested, timeout=1000):
        widget.bridge.endSession()


def test_the_panels_exit_button_reaches_the_existing_exit_signal(qtbot, widget):
    with qtbot.waitSignal(widget.exit_packing_mode, timeout=1000):
        widget.bridge.exitPacking()


def test_mapping_an_unmatched_scan_forwards_the_barcode(qtbot, widget):
    with qtbot.waitSignal(widget.map_barcode_requested, timeout=1000) as caught:
        widget.bridge.mapBarcode("4006381333931")
    assert caught.args == ["4006381333931"]


from gui.command_bar import BAR_HEIGHT


def test_the_bar_is_the_same_sixty_pixels_the_pages_use(widget):
    assert widget.packer_bar.height() == BAR_HEIGHT


def test_the_scanner_is_visible_and_invites_a_scan(widget):
    # A2: the shipped 1x1 hidden QLineEdit becomes a field the packer can see.
    assert widget.scanner_input.placeholderText() == "Ready to scan"
    assert widget.scanner_input.width() > 100
    assert widget.scanner_input.parent() is widget.packer_bar


def test_the_scanner_still_owns_the_keyboard(qtbot, widget):
    # D3, restated for the bar: the field moved, the invariant did not.
    widget.show()
    qtbot.waitExposed(widget)
    widget.activateWindow()
    qtbot.wait(50)
    widget.set_focus_to_scanner()
    qtbot.wait(50)
    assert widget.scanner_input.hasFocus()


def test_skip_and_exit_sit_in_the_bar(widget):
    assert widget.skip_order_button.parent() is widget.packer_bar
    assert widget.exit_button.parent() is widget.packer_bar
    assert widget.exit_button.text() == "Exit packing"
    assert widget.skip_order_button.text() == "Skip order"


def test_showing_an_order_names_it_in_the_bar(widget):
    widget.display_order(
        [{"SKU": "A", "Product_Name": "A", "Quantity": 1, "Order_Number": "10429"}],
        [],
    )
    assert widget._order_label.text() == "#10429"
    widget.clear_screen()
    assert widget._order_label.text() == "No order"



def test_a_missing_or_unparseable_start_time_is_no_duration():
    assert _session_seconds(None) == 0
    assert _session_seconds("") == 0
    assert _session_seconds("not a timestamp") == 0


def test_a_start_time_an_hour_ago_is_an_hour():
    from datetime import datetime, timedelta

    started = (datetime.now().astimezone() - timedelta(hours=1)).isoformat()
    assert 3550 <= _session_seconds(started) <= 3650


def test_the_pick_list_puts_the_lines_that_still_need_scans_first():
    state = [
        {"original_sku": "A", "packed": 2, "required": 2},
        {"original_sku": "B", "packed": 0, "required": 1},
        {"original_sku": "C", "packed": 1, "required": 4},
    ]
    assert _unmapped_choices(state) == [
        ("B", "B — 0 / 1 packed"),
        ("C", "C — 1 / 4 packed"),
        ("A", "A — 2 / 2 packed"),
    ]


def test_the_pick_list_is_empty_when_there_is_no_order():
    assert _unmapped_choices(None) == []
    assert _unmapped_choices([]) == []


def test_a_scan_keeps_the_saved_states_required_not_the_packing_lists(widget):
    """Spec D7. PackerLogic decides completion from order_state["required"], so a
    resumed session whose saved state and packing list disagree must keep the
    state's number -- update_item_row rebuilding the rows used to drop it."""
    items = [{"Product": "P", "SKU": "A", "Quantity": 5}]
    widget.display_order(items, [{"row": 0, "packed": 1, "required": 2}])
    assert widget.row_at(0)["required"] == 2

    widget.update_item_row(0, 2, True)

    assert widget.row_at(0)["required"] == 2
    assert widget.row_at(0)["state"] == "complete"
