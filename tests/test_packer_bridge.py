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

from gui.packer_bridge import (
    PAGE,
    THEME_MARKER,
    item_rows,
    mount_packer_page,
    unknown_rows,
)
from gui.theme import apply_theme
from shared.theme import THEME_DARK, THEME_LIGHT

ITEMS_FOR_PAGE = [{"SKU": "TS-4409-B", "Product_Name": "Wireless Mouse", "Quantity": 3}]


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


def test_the_view_never_takes_keyboard_focus(page, qtbot):
    from PySide6.QtCore import Qt

    view, _ = page
    assert view.focusPolicy() == Qt.FocusPolicy.NoFocus

    # The proxy is the widget that actually takes a click, and it is created
    # lazily -- so require it here rather than tolerating None, which is the one
    # case mount_packer_page's loadFinished re-assertion exists to cover.
    qtbot.waitUntil(lambda: view.focusProxy() is not None, timeout=5000)
    assert view.focusProxy().focusPolicy() == Qt.FocusPolicy.NoFocus


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

    view, bridge = page
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.chip').length === 2")
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.chip')).map(c => c.textContent)",
    ) == ["Complete", "Partial"]


def test_the_row_a_scan_landed_on_is_tinted(page, qtbot):

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

    view, bridge = page
    calls = []
    bridge.confirmRequested.connect(calls.append)
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 2")
    view.page().runJavaScript(
        "document.querySelector('[data-action=\"confirm\"]').click()"
    )
    qtbot.waitUntil(lambda: calls == [1], timeout=5000)


def test_the_side_column_shows_orders_items_and_unique_skus(page, qtbot):
    view, bridge = page
    bridge.set_progress(
        {
            "orders_done": 8,
            "orders_total": 13,
            "items_packed": 41,
            "items_total": 66,
            "skus_packed": 19,
            "skus_total": 34,
        }
    )
    _until_js(
        qtbot,
        view,
        "document.getElementById('progress-numbers').textContent.includes('8 / 13')",
    )
    assert (
        _eval(qtbot, view, "document.getElementById('progress-numbers').textContent")
        == "8 / 13 orders · 41 / 66 items"
    )
    assert (
        _eval(qtbot, view, "document.getElementById('summary-skus').textContent")
        == "19 / 34"
    )
    assert (
        _eval(qtbot, view, "document.getElementById('progress-fill').style.width")
        == "61.5385%"
    )


def test_no_orders_yet_leaves_the_bar_empty_and_says_so(page, qtbot):
    view, bridge = page
    bridge.set_progress({"orders_done": 0, "orders_total": 0})
    _until_js(
        qtbot, view, "document.getElementById('progress-fill').style.width === '0%'"
    )
    assert (
        _eval(
            qtbot, view, "document.getElementById('history-rows').textContent"
        ).strip()
        == "No orders yet"
    )


def test_history_lists_newest_first_with_a_status_chip(page, qtbot):
    view, bridge = page
    bridge.set_history(
        [
            {"order": "10429", "status": "complete"},
            {"order": "10428", "status": "skipped"},
        ]
    )
    _until_js(qtbot, view, "document.querySelectorAll('.history-row').length === 2")
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.history-row__order'))"
        ".map(e => e.textContent)",
    ) == ["#10429", "#10428"]
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelectorAll('.history-row .chip')[1].textContent",
        )
        == "Skipped"
    )


def test_the_widget_pushes_orders_and_item_numbers_together(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    widget.update_session_progress(8, 13)
    progress = widget.bridge.progress
    assert (progress["orders_done"], progress["orders_total"]) == (8, 13)
    assert (progress["items_packed"], progress["items_total"]) == (4, 11)
    assert (progress["skus_packed"], progress["skus_total"]) == (1, 2)


def test_a_skipped_order_is_marked_as_such_in_history(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.add_order_to_history("10428")
    widget.add_order_to_history("10429", "[SKIPPED]")
    assert widget.bridge.history == [
        {"order": "10429", "status": "skipped"},
        {"order": "10428", "status": "complete"},
    ]


def test_extras_appear_above_the_list_with_keep_and_remove(page, qtbot):
    view, bridge = page
    bridge.set_extras(
        [{"sku": "BX-9910-Z", "count": 1}, {"sku": "TS-1200-A", "count": 2}]
    )
    _until_js(qtbot, view, "document.querySelectorAll('.extras-row').length === 2")
    assert _eval(qtbot, view, "document.getElementById('extras').hidden") is False
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.extras-row .sku-row__qty'))"
        ".map(e => e.textContent)",
    ) == ["× 1", "× 2"]
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.extras-row .btn'))"
        ".map(b => b.textContent)",
    ) == ["Keep", "Remove", "Keep", "Remove"]


def test_no_extras_hides_the_section(page, qtbot):
    view, bridge = page
    bridge.set_extras([{"sku": "X", "count": 1}])
    _until_js(qtbot, view, "document.getElementById('extras').hidden === false")
    bridge.set_extras([])
    _until_js(qtbot, view, "document.getElementById('extras').hidden === true")


def test_keep_and_remove_carry_the_normalised_sku(page, qtbot):
    view, bridge = page
    kept, removed = [], []
    bridge.keepExtraRequested.connect(kept.append)
    bridge.removeExtraRequested.connect(removed.append)
    bridge.set_extras([{"sku": "BX9910Z", "count": 1}])
    _until_js(qtbot, view, "document.querySelectorAll('.extras-row').length === 1")
    view.page().runJavaScript(
        "document.querySelector('[data-action=\"keep\"]').click()"
    )
    qtbot.waitUntil(lambda: kept == ["BX9910Z"], timeout=5000)
    view.page().runJavaScript(
        "document.querySelector('[data-action=\"remove\"]').click()"
    )
    qtbot.waitUntil(lambda: removed == ["BX9910Z"], timeout=5000)


def test_the_widget_turns_the_extras_dict_into_rows(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.show_extras_panel({"BX9910Z": 1, "TS1200A": 2})
    assert widget.bridge.extras == [
        {"sku": "BX9910Z", "count": 1},
        {"sku": "TS1200A", "count": 2},
    ]


def test_clearing_the_screen_returns_to_waiting_and_keeps_the_session(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.update_session_progress(8, 13)
    widget.add_order_to_history("10428")
    widget.display_order(ITEMS, STATE, metadata={"shipping_provider": "DPD"})
    widget.show_extras_panel({"X": 1})

    widget.clear_screen()

    assert widget.bridge.items == []
    assert widget.bridge.extras == []
    assert widget.bridge.banner == {"order": "", "chips": [], "notes": ""}
    assert widget.bridge.feedback["text"] == "Scan the next order's barcode"
    assert widget.bridge.history == [{"order": "10428", "status": "complete"}]
    assert widget.bridge.progress["orders_done"] == 8


def test_clearing_the_screen_re_enables_the_scanner_and_disables_skip(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    widget.scanner_input.setEnabled(False)
    widget.clear_screen()
    assert widget.scanner_input.isEnabled() is True
    assert widget.skip_order_button.isEnabled() is False


def test_the_waiting_document_shows_no_list_and_no_banner(page, qtbot):
    view, bridge = page
    bridge.set_items([])
    bridge.set_banner({"order": "", "chips": [], "notes": ""})
    _until_js(qtbot, view, "document.getElementById('sku-list').hidden === true")
    assert _eval(qtbot, view, "document.getElementById('banner').hidden") is True


# The Qt -> web translation layer. Every other feedback test drives
# bridge.set_feedback(...) directly, i.e. post-translation, so a typo in the
# prefix strip or in the colour mapping would leave the band uncoloured on
# every scan with the suite still green.


def test_a_notification_role_loses_its_status_prefix_on_the_way_out(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)

    widget.show_notification("ITEM OK", "status_success")
    assert widget.bridge.feedback["role"] == "success"

    widget.show_notification("", "transparent")
    assert widget.bridge.feedback["role"] == ""


def test_flash_border_s_colour_words_reach_the_bridge_as_roles(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)

    seen = []
    widget.bridge.scanFlashed.connect(seen.append)
    for color in ("green", "orange", "red"):
        widget.flash_scan(color)
    assert seen == ["success", "warning", "danger"]


def test_the_page_reads_the_session_end_payload(qtbot, page):
    view, bridge = page
    assert _eval(qtbot, view, "window.packerBridge.sessionEnd") == {}
    bridge.set_session_end(
        {"title": "Session complete", "body": "2 of 2 orders packed."}
    )
    _until_js(
        qtbot, view, "window.packerBridge.sessionEnd.title === 'Session complete'"
    )


def test_an_unmatched_scan_draws_a_no_match_row_that_only_maps(qtbot, page):
    view, bridge = page
    bridge.set_items(unknown_rows(["4006381333931"]))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    assert _eval(qtbot, view, "document.querySelector('.sku-row').className") == (
        "sku-row sku-row--unknown"
    )
    cells = _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.sku-row > span'))"
        ".map(function (e) { return e.textContent; })",
    )
    assert cells[:3] == ["Unknown SKU", "4006381333931", "—"]
    assert "No match" in cells[3]
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.sku-row .btn'))"
        ".map(function (e) { return e.textContent; })",
    ) == ["Map SKU"]


def test_mapping_an_unmatched_scan_reaches_python_with_the_barcode(qtbot, page):
    view, bridge = page
    bridge.set_items(unknown_rows(["4006381333931"]))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row .btn').length === 1")
    with qtbot.waitSignal(bridge.mapBarcodeRequested, timeout=5000) as caught:
        view.page().runJavaScript("document.querySelector('.sku-row .btn').click()")
    assert caught.args == ["4006381333931"]


def test_the_quantity_cell_warns_while_a_multi_unit_line_is_unfinished(qtbot, page):
    view, bridge = page
    bridge.set_items(
        item_rows(ITEMS_FOR_PAGE, [{"row": 0, "packed": 1, "required": 3}], {})
    )
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    assert _eval(qtbot, view, "document.querySelector('.sku-row__qty').className") == (
        "sku-row__qty sku-row__qty--multi"
    )


def test_a_finished_multi_unit_line_drops_the_warning(qtbot, page):
    view, bridge = page
    bridge.set_items(
        item_rows(ITEMS_FOR_PAGE, [{"row": 0, "packed": 3, "required": 3}], {})
    )
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    assert _eval(qtbot, view, "document.querySelector('.sku-row__qty').className") == (
        "sku-row__qty"
    )


def test_a_finished_session_replaces_the_document_with_its_panel(qtbot, page):
    view, bridge = page
    bridge.set_items(item_rows(ITEMS_FOR_PAGE, [], {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    bridge.set_session_end(
        {"title": "Session complete", "body": "2 of 2 orders packed."}
    )
    _until_js(
        qtbot,
        view,
        "document.getElementById('doc-main').classList.contains('doc-state')",
    )
    # The list is still in the DOM -- the bridge keeps filling it -- but the
    # panel has the column.
    assert (
        _eval(
            qtbot, view, "getComputedStyle(document.getElementById('sku-list')).display"
        )
        == "none"
    )
    assert _eval(
        qtbot, view, "document.querySelector('.state-panel-title').textContent"
    ) == ("Session complete")
    assert _eval(
        qtbot, view, "document.querySelector('.state-panel-body').textContent"
    ) == ("2 of 2 orders packed.")


def test_clearing_the_session_end_gives_the_document_back(qtbot, page):
    view, bridge = page
    bridge.set_session_end({"title": "Session complete", "body": "done."})
    _until_js(
        qtbot,
        view,
        "document.getElementById('doc-main').classList.contains('doc-state')",
    )
    bridge.set_session_end({})
    _until_js(
        qtbot,
        view,
        "!document.getElementById('doc-main').classList.contains('doc-state')",
    )
    assert (
        _eval(
            qtbot,
            view,
            "getComputedStyle(document.querySelector('.state-panel')).display",
        )
        == "none"
    )


def test_the_panels_buttons_reach_python(qtbot, page):
    view, bridge = page
    bridge.set_session_end({"title": "Session complete", "body": "done."})
    _until_js(
        qtbot,
        view,
        "document.querySelectorAll('.state-panel-actions .btn').length === 2",
    )
    labels = _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.state-panel-actions .btn'))"
        ".map(function (e) { return e.textContent; })",
    )
    assert labels == ["End session", "Exit packing"]
    with qtbot.waitSignal(bridge.endSessionRequested, timeout=5000):
        view.page().runJavaScript(
            "document.querySelector('[data-action=\"endSession\"]').click()"
        )
    with qtbot.waitSignal(bridge.exitPackingRequested, timeout=5000):
        view.page().runJavaScript(
            "document.querySelector('[data-action=\"exitPacking\"]').click()"
        )
