"""The wiring between MainWindow and PackerModeWidget, not either half alone.

Bundle 5 shipped two defects that lived exactly here: `unknown_rows` had no
production caller, and the last order's deferred `clear_screen` wiped the
session-complete panel three seconds after it rendered. Every other test in
this bundle sits on one side of the seam or the other, so neither showed up.

The logic is a stub: what is under test is which widget calls MainWindow makes
in response to a scan outcome, not how PackerLogic decides the outcome.
"""

import pytest

from gui.main_window import MainWindow


class StubLogic:
    """Just enough PackerLogic for on_scanner_input's product-scan branch."""

    def __init__(self, status, result=None):
        self._status = status
        self._result = result
        self.current_order_number = "1001"
        self.current_order_state = []
        self.unknown_scans = []
        self.orders_data = {"1001": {}}
        self.session_packing_state = {"completed_orders": ["1001"], "skipped_orders": []}
        self.completed_orders_metadata = []
        self.sku_map = {}
        self.started_at = None
        self.cleared = False

    def process_sku_scan(self, sku):
        if self._status == "SKU_NOT_FOUND":
            self.unknown_scans.append(sku)
        return self._result, self._status

    def clear_current_order(self):
        self.cleared = True


@pytest.fixture
def window(qapp, tmp_path):
    config = tmp_path / "config.ini"
    config.write_text(
        "[Network]\n"
        f"FileServerPath = {tmp_path}\n"
        "ConnectionTimeout = 5\n"
        f"LocalCachePath = {tmp_path}\n"
        "[Logging]\n"
        "LogLevel = INFO\nLogRetentionDays = 30\nMaxLogSizeMB = 10\n",
        encoding="utf-8",
    )
    mw = MainWindow(config_path=str(config))
    yield mw
    mw.deleteLater()


def test_an_unmatched_scan_becomes_a_row_in_the_document(window):
    """Spec S3. The feature was unreachable: no caller pushed unknown_scans."""
    window.logic = StubLogic("SKU_NOT_FOUND")
    window.packer_mode_widget.display_order([], [], metadata={}, sku_map={})

    window.on_scanner_input("9999999999")

    unknown = [r for r in window.packer_mode_widget.bridge.items if r["state"] == "unknown"]
    assert [r["sku"] for r in unknown] == ["9999999999"]
    assert unknown[0]["mapBarcode"] is True


def test_the_same_wrong_barcode_twice_is_one_row(window):
    window.logic = StubLogic("SKU_NOT_FOUND")
    window.packer_mode_widget.display_order([], [], metadata={}, sku_map={})

    window.on_scanner_input("9999999999")
    window.on_scanner_input("9999999999")

    unknown = [r for r in window.packer_mode_widget.bridge.items if r["state"] == "unknown"]
    assert len(unknown) == 1


def test_opening_an_order_drops_the_previous_order_s_unmatched_scans(window):
    window.logic = StubLogic("SKU_NOT_FOUND")
    window.packer_mode_widget.display_order([], [], metadata={}, sku_map={})
    window.on_scanner_input("9999999999")

    window.packer_mode_widget.display_order([], [], metadata={}, sku_map={})

    assert not [
        r for r in window.packer_mode_widget.bridge.items if r["state"] == "unknown"
    ]


def test_the_last_order_leaves_the_panel_up_after_its_deferred_reset(window):
    """Spec S2. _handle_order_completion schedules clear_screen 3s out while
    all_orders_complete renders the panel at once, so the panel has to outlive it."""
    window.logic = StubLogic("ORDER_COMPLETE")
    widget = window.packer_mode_widget

    window._handle_order_completion("1001")
    window._show_session_complete()
    widget.clear_screen()  # what the 3s timer fires

    assert widget.bridge.sessionEnd["title"]
    assert not widget.scanner_input.isEnabled()


def test_starting_a_session_clears_the_document_and_shows_the_resumed_count(window):
    widget = window.packer_mode_widget
    widget.add_order_to_history("0999")
    widget.update_session_progress(5, 5)
    logic = StubLogic("SKU_OK")
    logic.orders_data = {"1001": {}, "1002": {}, "1003": {}}
    logic.session_packing_state = {"completed_orders": ["1001"], "skipped_orders": []}
    window.logic = logic

    window._open_packer_document()

    assert widget.bridge.history == []
    assert widget.bridge.progress["orders_done"] == 1
    assert widget.bridge.progress["orders_total"] == 3


class RecordingPublisher:
    def __init__(self):
        self.published = []

    def publish(self, completed_orders, skipped_count):
        self.published.append((list(completed_orders), skipped_count))


def test_a_completed_order_is_published(window, monkeypatch):
    window.logic = StubLogic("SKU_OK")
    window._progress_publisher = RecordingPublisher()
    monkeypatch.setattr(window, "update_order_status", lambda *_: None)
    window._handle_order_completion("1001")
    assert window._progress_publisher.published == [(["1001"], 0)]


def test_a_skipped_order_is_published(window):
    logic = StubLogic("SKU_OK")
    logic.session_packing_state = {"completed_orders": [], "skipped_orders": []}
    logic.skip_order = lambda: logic.session_packing_state["skipped_orders"].append("1001")
    window.logic = logic
    window._progress_publisher = RecordingPublisher()
    window._on_skip_order()
    assert window._progress_publisher.published == [([], 1)]
