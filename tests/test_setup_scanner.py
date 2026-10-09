"""ADR 0004: SKU mapping takes the keyboard from Packer Mode, and gives it back.

Real key events through a real Chromium, the way a barcode scanner (a
keyboard wedge) sends them. The owner confirms the same on a Windows build
with a real scanner. Never mark these skip.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from setup_web import eval_js, until_js

import gui.main_window as mw

UNKNOWN = "9999999999"


def in_packer_mode(window) -> bool:
    return window.stacked_widget.currentWidget() is window.packer_mode_widget


def on_setup(window) -> bool:
    return window.stacked_widget.currentWidget() is window.setup_pages


def scan(text):
    """What a scanner does: types into whatever has the focus, then Enter."""
    target = QApplication.focusWidget()
    QTest.keyClicks(target, text)
    QTest.keyClick(target, Qt.Key.Key_Return)


def saved(window) -> dict:
    return window.profile_manager.load_sku_mapping(window.current_client_id, fresh=True)


@pytest.fixture
def packing(main_window_with_list, qtbot):
    """A shown window in Packer Mode with order #10429 (one TS-4409-B) open."""
    window = main_window_with_list
    window.show()
    qtbot.waitExposed(window)
    window.activateWindow()
    for view in (
        window.session_tabs.view,
        window.setup_pages.view,
        window.packer_mode_widget.document_view,
    ):
        until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    window.stacked_widget.setCurrentWidget(window.packer_mode_widget)
    window.packer_mode_widget.set_focus_to_scanner()
    window.on_scanner_input("#10429")
    assert window.logic.current_order_number is not None
    yield window
    window.hide()


@pytest.fixture
def replayed(packing, monkeypatch):
    """Every text sent to on_scanner_input from here on, still acted on."""
    seen = []
    real = packing.on_scanner_input

    def spy(text, *args, **kwargs):
        seen.append(text)
        return real(text, *args, **kwargs)

    monkeypatch.setattr(packing, "on_scanner_input", spy)
    return seen


def open_quick(window, qtbot, *, sku=None, barcode=None):
    bridge = window.packer_mode_widget.bridge
    if sku is not None:
        bridge.mapSku(sku)
        field = "d-barcode"
    else:
        bridge.mapBarcode(barcode)
        field = "d-sku"
    qtbot.waitUntil(lambda: on_setup(window), timeout=3000)
    view = window.setup_pages.view
    until_js(qtbot, view, f"document.activeElement.id === '{field}'")
    qtbot.waitUntil(
        lambda: QApplication.focusWidget() in (view, view.focusProxy()), timeout=3000
    )
    return view


def test_map_sku_takes_the_scanned_barcode_and_gives_the_scanner_back(packing, qtbot):
    window = packing
    open_quick(window, qtbot, sku="TS-4409-B")
    assert window.setup_pages.bridge.mapping["quick"]["kind"] == "sku"

    scan("5906000123456")  # the packer scans the product

    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert saved(window)["5906000123456"] == "TS-4409-B"
    assert window.logic.sku_map["5906000123456"] == "TS-4409-B"
    # The scanner field has the focus again...
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input
    # ...and the next scan is Packer Mode's.
    seen = []
    window.packer_mode_widget.barcode_scanned.connect(seen.append)
    scan("5906000123456")
    assert seen == ["5906000123456"]


def test_a_scan_into_the_sku_field_saves_nothing(packing, qtbot, monkeypatch):
    """The dangerous one: Map barcode… has the focus on SKU, and a stray scan
    would type a barcode there and press Enter."""
    window = packing
    window.on_scanner_input(UNKNOWN)
    assert window.logic.unknown_scans == [UNKNOWN]
    writes = []
    real = window.profile_manager.update_sku_mapping
    monkeypatch.setattr(
        window.profile_manager, "update_sku_mapping",
        lambda *a, **k: (writes.append(a), real(*a, **k))[1],
    )
    view = open_quick(window, qtbot, barcode=UNKNOWN)

    scan("4006381333931")

    until_js(qtbot, view, "!document.getElementById('d-problem').hidden")
    assert eval_js(qtbot, view, "document.getElementById('d-problem').textContent") == (
        "Not on this order. Pick one of the lines below."
    )
    assert writes == []
    assert on_setup(window)
    assert UNKNOWN not in saved(window)


def test_map_barcode_saves_a_sku_of_the_order_and_replays_the_scan(packing, qtbot, replayed):
    window = packing
    window.on_scanner_input(UNKNOWN)
    replayed.clear()
    view = open_quick(window, qtbot, barcode=UNKNOWN)
    assert eval_js(
        qtbot, view, "document.querySelectorAll('#d-choices [data-choice]').length") == 1

    scan("ts 4409 b")  # typed loosely; a scanned SKU label works the same way

    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert saved(window)[UNKNOWN] == "TS-4409-B"  # the order's own spelling
    assert replayed == [UNKNOWN]  # the scan that had no match is acted on now
    assert UNKNOWN not in window.logic.unknown_scans
    # The replay finishes the order, which holds the scanner off until its
    # screen clears; the promise is that the field has the focus once enabled.
    qtbot.waitUntil(
        lambda: QApplication.focusWidget() is window.packer_mode_widget.scanner_input,
        timeout=5000,
    )


def test_a_scan_with_no_field_is_held_and_replayed_after_the_return(
    packing, qtbot, replayed, monkeypatch
):
    window = packing
    view = open_quick(window, qtbot, sku="TS-4409-B")
    # Hold the switch back, so the gap it leaves can be scanned into.
    held = []
    monkeypatch.setattr(mw, "when_painted", lambda bridge, callback, *a: held.append(callback))

    window.setup_pages.bridge.closeMapping()  # Back to packing
    assert len(held) == 1 and on_setup(window)
    until_js(qtbot, view, "document.getElementById('mapping').hidden")

    scan("4006381333931")  # no field has the focus: the page is blank

    qtbot.waitUntil(lambda: window._stray_scans == ["4006381333931"], timeout=3000)
    assert replayed == []  # not acted on yet

    held[0]()  # the paint arrives; the window switches

    assert in_packer_mode(window)
    assert replayed == ["4006381333931"]  # exactly once
    assert window._stray_scans == []
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input


def test_back_to_packing_saves_nothing_and_gives_the_scanner_back(packing, qtbot):
    window = packing
    before = saved(window)
    open_quick(window, qtbot, sku="TS-4409-B")
    window.setup_pages.bridge.closeMapping()
    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert saved(window) == before
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input
    seen = []
    window.packer_mode_widget.barcode_scanned.connect(seen.append)
    scan("TS-4409-B")
    assert seen == ["TS-4409-B"]


def test_a_stray_scan_reported_after_the_return_is_still_acted_on(packing, replayed):
    packing._on_stray_scan("4006381333931")  # Packer Mode is already back on top
    assert replayed == ["4006381333931"]


def test_a_stray_scan_on_a_page_opened_from_the_shell_is_dropped(main_window, monkeypatch):
    window = main_window
    seen = []
    monkeypatch.setattr(window, "on_scanner_input", lambda text, *a: seen.append(text))
    window.open_sku_mapping()
    window.setup_pages.bridge.strayScan("4006381333931")
    assert seen == [] and window._stray_scans == []


def test_map_barcode_with_no_open_order_only_refocuses_the_scanner(packing, qtbot):
    window = packing
    window.logic.current_order_state = []
    window.packer_mode_widget.bridge.mapBarcode(UNKNOWN)
    qtbot.wait(200)
    assert in_packer_mode(window)
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input


def test_a_lock_lost_during_a_quick_map_lands_on_the_take_over_panel(
    packing, qtbot, monkeypatch
):
    window = packing
    open_quick(window, qtbot, sku="TS-4409-B")
    monkeypatch.setattr(
        window.lock_manager, "is_locked", lambda work_dir: (True, {"locked_by": "WH-PC-02"})
    )
    window._on_lock_lost(Path("/sessions/2026-01-01_1/packing/DHL_Orders"))
    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert window.packer_mode_widget.taken_over
    assert window.logic is not None  # torn down when the packer exits, as on frame 6j


def test_a_held_stray_scan_is_not_replayed_onto_a_list_taken_over(
    packing, qtbot, monkeypatch, replayed
):
    window = packing
    open_quick(window, qtbot, sku="TS-4409-B")
    window.setup_pages.bridge.strayScan("4006381333931")
    assert window._stray_scans == ["4006381333931"]
    monkeypatch.setattr(
        window.lock_manager, "is_locked", lambda work_dir: (True, {"locked_by": "WH-PC-02"})
    )
    window._on_lock_lost(Path("/sessions/2026-01-01_1/packing/DHL_Orders"))
    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert replayed == [] and window._stray_scans == []
