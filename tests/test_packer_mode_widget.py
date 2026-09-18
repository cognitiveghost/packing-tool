"""Packer Mode's Qt side: the bar, and the state the widget pushes.

The document itself is covered by tests/test_packer_bridge.py.
"""

import pytest

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


def test_clearing_the_screen_gives_the_document_back(widget):
    widget.show_session_complete({"title": "Session complete", "body": "done."})
    widget.clear_screen()
    assert widget.bridge.sessionEnd == {}
    assert widget.scanner_input.isEnabled() is True


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
