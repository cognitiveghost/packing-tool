"""Packer Mode's Qt side: the bar, and the state the widget pushes.

The document itself is covered by tests/test_packer_bridge.py.
"""

import pytest

from gui.main_window import _session_seconds
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


def test_the_scanner_is_visible_and_says_it_is_ready(widget):
    assert widget.scanner_input.placeholderText() == "Order number or SKU"
    assert widget.scanner_input.width() == 280
    assert widget.scanner_input.height() == 44
    assert widget.scanner_input.parent() is widget.packer_bar
    assert widget._scanner_state.text() == "Ready to scan"


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


def test_a_new_session_does_not_inherit_the_last_ones_history_or_counts(widget):
    """Phase 12 Bundle 2 item 1: the panel cleared, but the side column
    still showed the finished session's orders and its 2 / 2."""
    widget.add_order_to_history("1001")
    widget.add_order_to_history("1002")
    widget.update_session_progress(2, 2)
    widget.show_session_complete({"title": "Session complete", "body": "done."})

    widget.reset_for_new_session()

    assert widget.bridge.history == []
    assert widget.bridge.progress["orders_done"] == 0
    assert widget.bridge.progress["orders_total"] == 0


def test_unsaved_progress_is_its_own_state_and_leaves_the_band_alone(widget):
    widget.show_notification("Order #1001 packed. Scan the next order.", "status_success")
    widget.set_unsaved(True)
    assert widget.bridge.unsaved is True
    assert widget.bridge.feedback["role"] == "success"
    assert widget.bridge.feedback["text"] == "Order #1001 packed. Scan the next order."
    assert widget.scanner_input.isEnabled()  # scanning continues

    widget.set_unsaved(False)
    assert widget.bridge.unsaved is False


def test_a_new_session_starts_saved(widget):
    widget.set_unsaved(True)
    widget.reset_for_new_session()
    assert widget.bridge.unsaved is False


ORDER = [
    {"SKU": "SPF-50", "Product_Name": "Sunscreen SPF 50", "Quantity": 8, "Order_Number": "10407"},
    {"SKU": "LIP-RED", "Product_Name": "Lip balm, red", "Quantity": 2, "Order_Number": "10407"},
]


def _off(widget):
    return (
        not widget.scanner_input.isEnabled()
        and widget._scanner_state.text() == "Scanner disabled"
        and not widget.skip_order_button.isEnabled()
    )


def test_an_open_order_turns_skip_on_and_no_order_turns_it_off(widget):
    assert not widget.skip_order_button.isEnabled()
    widget.display_order(ORDER, [])
    assert widget.skip_order_button.isEnabled()
    assert widget._scanner_state.text() == "Ready to scan"
    widget.clear_screen()
    assert not widget.skip_order_button.isEnabled()
    assert widget.scanner_input.isEnabled()


def test_a_force_click_asks_first_and_turns_the_scanner_off(qtbot, widget):
    widget.display_order(ORDER, [{"row": 0, "packed": 3, "required": 8}])
    forced = []
    widget.force_confirm_requested.connect(forced.append)

    widget.bridge.forceItem(0)

    assert forced == []
    assert widget.bridge.question == {
        "row": 0, "sku": "SPF-50", "product": "Sunscreen SPF 50", "remaining": 5, "required": 8,
    }
    assert _off(widget)


def test_force_confirm_sends_the_row_and_gives_the_scanner_back(widget):
    widget.display_order(ORDER, [])
    forced = []
    widget.force_confirm_requested.connect(forced.append)
    widget.bridge.forceItem(0)

    widget.bridge.answerQuestion(True)

    assert forced == [0]
    assert widget.bridge.question == {}
    assert widget.scanner_input.isEnabled()
    assert widget.skip_order_button.isEnabled()


def test_cancel_sends_nothing_and_gives_the_scanner_back(widget):
    widget.display_order(ORDER, [])
    forced = []
    widget.force_confirm_requested.connect(forced.append)
    widget.bridge.forceItem(0)

    widget.bridge.answerQuestion(False)

    assert forced == []
    assert widget.bridge.question == {}
    assert widget.scanner_input.isEnabled()


def test_a_force_click_on_a_row_that_is_not_there_asks_nothing(widget):
    widget.display_order(ORDER, [])
    widget.bridge.forceItem(7)
    assert widget.bridge.question == {}
    assert widget.scanner_input.isEnabled()


def test_an_answer_with_no_question_open_does_nothing(widget):
    widget.display_order(ORDER, [])
    forced = []
    widget.force_confirm_requested.connect(forced.append)
    widget.bridge.answerQuestion(True)
    assert forced == []


def test_leaving_with_a_question_open_drops_it(widget):
    widget.display_order(ORDER, [])
    widget.bridge.forceItem(0)
    widget.clear_screen()  # what Exit packing does
    assert widget.bridge.question == {}
    assert widget.scanner_input.isEnabled()


def test_a_takeover_turns_everything_off_until_a_new_session(widget):
    widget.display_order(ORDER, [])
    widget.show_takeover("PC-2", "DHL_Orders")
    assert widget.taken_over is True
    assert widget.bridge.takeover == {"holder": "PC-2", "list": "DHL_Orders"}
    assert _off(widget)

    widget.clear_screen()  # a per-order reset does not give the list back
    assert _off(widget)

    widget.reset_for_new_session()
    assert widget.taken_over is False
    assert widget.bridge.takeover == {}
    assert widget.scanner_input.isEnabled()


def test_a_takeover_closes_an_open_question(widget):
    widget.display_order(ORDER, [])
    widget.bridge.forceItem(0)
    widget.show_takeover("PC-2", "DHL_Orders")
    assert widget.bridge.question == {}
    widget.bridge.answerQuestion(True)  # a late click on the old question
    assert _off(widget)


def test_pause_and_resume(widget):
    widget.display_order(ORDER, [])
    widget.pause_scanner()
    assert _off(widget)
    widget.resume_scanner()
    assert widget.scanner_input.isEnabled()


def test_a_finished_session_stays_off_through_a_resume(widget):
    widget.show_session_complete({"title": "Session complete", "body": "done."})
    widget.resume_scanner()
    assert _off(widget)


def test_the_held_order_keeps_the_scanner_off_until_the_reset(qtbot, widget):
    widget.display_order(ORDER, [])
    widget.clear_screen_later(40)
    assert _off(widget)
    qtbot.wait(150)
    assert widget.scanner_input.isEnabled()
    assert widget.bridge.items == []


def test_the_simulator_refuses_a_scan_while_the_scanner_is_off(qtbot):
    w = PackerModeWidget(sim_mode=True)
    qtbot.addWidget(w)
    seen = []
    w.barcode_scanned.connect(seen.append)
    w.pause_scanner()
    w.sim_input.setText("10407")
    w._on_sim_scan()
    assert seen == []
    w.resume_scanner()
    w._on_sim_scan()
    assert seen == ["10407"]
