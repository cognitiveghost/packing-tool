"""The bridge and the page, driven through a real Chromium (ADR 0001).

CI runs the suite on windows-latest, where QtWebEngine needs no extra runtime
packages. Never mark these skip -- a bridge nobody can run is a bridge nobody
guards.
"""

import json
import time

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.packer_bridge import PAGE, THEME_MARKER, mount_packer_page
from gui.theme import apply_theme
from shared.theme import THEME_DARK, THEME_LIGHT


def _eval(qtbot, view, expr, timeout=5000):
    # This PySide6/QtWebEngine build's runJavaScript cannot marshal a JS array
    # back to Python (it silently comes back as ''), even though scalars and
    # JSON.stringify's own string result round-trip fine. Route every result
    # through JSON so array- and object-returning expressions work too.
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def _until_js(qtbot, view, expr, timeout_s=20):
    # A cold Chromium spin-up under CI load can outlast one round trip; keep
    # retrying against this function's own deadline.
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = max(int((deadline - time.monotonic()) * 1000), 50)
        try:
            if _eval(qtbot, view, expr, timeout=min(remaining, 5000)) is True:
                return
        except QtBotTimeoutError:
            continue
        qtbot.wait(50)
    pytest.fail(f"never became true in the page: {expr}")


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_packer_page(view)
    view.resize(1366, 700)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_first_paint_is_already_themed(page, qtbot):
    view, _ = page
    assert _eval(qtbot, view, "document.getElementById('theme-vars').textContent") != ""


def test_a_theme_switch_repaints_without_a_reload(page, qtbot, qapp):
    view, _ = page

    def css():
        return _eval(qtbot, view, "document.getElementById('theme-vars').textContent")

    before = css()
    assert "--surface" in before
    apply_theme(qapp, THEME_LIGHT)
    try:
        qtbot.waitUntil(lambda: css() != before, timeout=10000)
    finally:
        apply_theme(qapp, THEME_DARK)


def test_the_view_never_takes_keyboard_focus(page):
    from PySide6.QtCore import Qt

    view, _ = page
    assert view.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert view.focusProxy() is None or (
        view.focusProxy().focusPolicy() == Qt.FocusPolicy.NoFocus
    )


def test_a_notification_reaches_the_band_with_its_role(page, qtbot):
    view, bridge = page
    bridge.set_feedback("ITEM OK", "success", "TS-4409-B")
    _until_js(
        qtbot,
        view,
        "document.getElementById('feedback-text').textContent === 'ITEM OK'",
    )
    assert _eval(qtbot, view, "document.getElementById('feedback').className") == (
        "feedback feedback--success"
    )
    assert (
        _eval(qtbot, view, "document.getElementById('feedback-raw').textContent")
        == "TS-4409-B"
    )


def test_a_cleared_notification_leaves_the_band_neutral(page, qtbot):
    view, bridge = page
    bridge.set_feedback("ITEM OK", "success", "X")
    _until_js(
        qtbot, view, "document.getElementById('feedback').className.includes('success')"
    )
    bridge.set_feedback("", "", "X")
    _until_js(
        qtbot, view, "document.getElementById('feedback').className === 'feedback'"
    )


def test_a_flash_marks_the_document_column_and_clears_itself(page, qtbot):
    view, bridge = page
    bridge.flash("danger")
    _until_js(
        qtbot,
        view,
        "document.getElementById('doc-main').dataset.flash === 'danger'",
    )
    _until_js(
        qtbot,
        view,
        "document.getElementById('doc-main').dataset.flash === undefined",
    )


ITEMS = [
    {"SKU": "TS-4409-B", "Product_Name": "Wireless Mouse", "Quantity": 3},
    {"SKU": "BX-3311-A", "Product_Name": "Laptop Stand", "Quantity": 8},
]
STATE = [
    {
        "original_sku": "TS-4409-B",
        "normalized_sku": "TS4409B",
        "required": 3,
        "packed": 3,
        "row": 0,
    },
    {
        "original_sku": "BX-3311-A",
        "normalized_sku": "BX3311A",
        "required": 8,
        "packed": 1,
        "row": 1,
    },
]


def test_the_list_draws_one_row_per_item_with_its_state(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 2")
    assert _eval(
        qtbot, view, "document.querySelectorAll('.sku-row')[0].className"
    ).split() == ["sku-row", "sku-row--complete"]
    assert _eval(
        qtbot, view, "document.querySelectorAll('.sku-row')[1].className"
    ).split() == ["sku-row", "sku-row--partial"]


def test_a_row_shows_product_sku_and_the_packed_count(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 2")
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('.sku-row__product').textContent",
        )
        == "Wireless Mouse"
    )
    assert (
        _eval(qtbot, view, "document.querySelector('.sku-row__sku').textContent")
        == "TS-4409-B"
    )
    assert (
        _eval(qtbot, view, "document.querySelector('.sku-row__qty').textContent")
        == "3 / 3"
    )


def test_each_state_carries_the_artboard_s_chip(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.chip').length === 2")
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.chip')).map(c => c.textContent)",
    ) == ["Complete", "Partial"]


def test_the_row_a_scan_landed_on_is_tinted(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    rows = item_rows(ITEMS, STATE, {})
    rows[1]["just_changed"] = True
    bridge.set_items(rows)
    _until_js(
        qtbot,
        view,
        "document.querySelectorAll('.sku-row--just-changed').length === 1",
    )


def test_an_empty_list_hides_the_section(page, qtbot):
    view, bridge = page
    bridge.set_items([])
    _until_js(qtbot, view, "document.getElementById('sku-list').hidden === true")


def test_display_order_then_a_scan_updates_only_that_row(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE, metadata={"shipping_provider": "DPD"})
    widget.update_item_row(1, 2, False)

    rows = widget.bridge.items
    assert [(r["packed"], r["state"]) for r in rows] == [
        (3, "complete"),
        (2, "partial"),
    ]
    assert [r["just_changed"] for r in rows] == [False, True]
    assert widget.bridge.banner["chips"] == ["DPD"]


def test_a_confirm_click_re_emits_the_row_s_sku_as_a_scan(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.barcode_scanned.connect(seen.append)
    widget.bridge.confirmItem(1)
    assert seen == ["BX-3311-A"]


def test_an_undo_click_asks_nothing_and_reaches_the_cancel_signal(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.cancel_item_requested.connect(seen.append)
    widget.bridge.undoItem(1)
    assert seen == [1]


def test_a_force_click_confirms_first(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from gui import packer_mode_widget as module
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.force_confirm_requested.connect(seen.append)

    monkeypatch.setattr(
        module.ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )
    widget.bridge.forceItem(1)
    assert seen == []

    monkeypatch.setattr(
        module.ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )
    widget.bridge.forceItem(1)
    assert seen == [1]


def test_a_map_click_carries_the_original_sku(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.map_sku_requested.connect(seen.append)
    widget.bridge.mapSku("BX-3311-A")
    assert seen == ["BX-3311-A"]


def test_clicking_a_row_action_in_the_page_calls_its_slot(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    calls = []
    bridge.confirmRequested.connect(calls.append)
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 2")
    view.page().runJavaScript(
        "document.querySelector('[data-action=\"confirm\"]').click()"
    )
    qtbot.waitUntil(lambda: calls == [1], timeout=5000)
