"""The bridge and the page, driven through a real Chromium (ADR 0001).

CI runs the suite on windows-latest, where QtWebEngine needs no extra runtime
packages. Never mark these skip -- a bridge nobody can run is a bridge nobody
guards.
"""

import json
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.packer_bridge import (
    PAGE,
    item_rows,
    mount_packer_page,
    unknown_rows,
)
from gui.theme import apply_theme
from shared.theme import THEME_DARK, THEME_LIGHT
from shared.web_page import THEME_MARKER, PageBridge

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
    assert _eval(qtbot, view, "document.querySelector('.sku-row__num').textContent") == "3"
    assert _eval(qtbot, view, "document.querySelector('.sku-row__of').textContent") == "of 3"


def test_each_state_carries_the_artboard_s_chip(page, qtbot):

    view, bridge = page
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row .badge').length === 2")
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.sku-row .badge')).map(c => c.textContent)",
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


def test_a_confirm_click_sends_the_row_s_sku_as_a_manual_confirm(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    manual, scanned = [], []
    widget.manual_confirm_requested.connect(manual.append)
    widget.barcode_scanned.connect(scanned.append)
    widget.bridge.confirmItem(1)
    assert (manual, scanned) == (["BX-3311-A"], [])  # a click is not a scan (AUDIT-02-9)


def test_an_undo_click_asks_nothing_and_reaches_the_cancel_signal(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.cancel_item_requested.connect(seen.append)
    widget.bridge.undoItem(1)
    assert seen == [1]


def test_a_force_click_opens_the_question_and_forces_only_on_yes(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.force_confirm_requested.connect(seen.append)

    widget.bridge.forceItem(1)
    assert seen == []
    widget.bridge.answerQuestion(False)
    assert seen == []

    widget.bridge.forceItem(1)
    widget.bridge.answerQuestion(True)
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
        "document.querySelector('[data-action=\"confirm\"]:not(:disabled)').click()"
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
            "document.querySelectorAll('.history-row__status')[1].textContent",
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


def test_extras_appear_in_the_list_with_keep_and_remove(page, qtbot):
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
    assert widget.bridge.banner == {"order": "", "chips": [], "repeat": False, "notes": ""}
    assert widget.bridge.feedback["text"] == "Scan an order barcode"
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


def test_a_repeat_only_banner_shows_the_warning_chip_and_no_notes(page, qtbot):
    view, bridge = page
    bridge.set_banner({"order": "10429", "chips": [], "repeat": True, "notes": ""})
    _until_js(qtbot, view, "document.getElementById('banner-repeat').hidden === false")
    assert _eval(qtbot, view, "document.getElementById('banner').hidden") is False
    assert _eval(qtbot, view, "document.getElementById('banner-repeat').textContent") == "Repeat"
    assert _eval(qtbot, view, "document.getElementById('banner-notes').hidden") is True


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


def test_the_bridge_is_a_page_bridge_and_counts_its_changes(page):
    _view, bridge = page
    assert isinstance(bridge, PageBridge)
    before = bridge.revision
    bridge.set_items([])
    bridge.set_unsaved(True)
    assert bridge.revision == before + 2


def test_the_three_new_states_start_empty_and_round_trip(page):
    _view, bridge = page
    assert (bridge.unsaved, bridge.question, bridge.takeover) == (False, {}, {})
    bridge.set_unsaved(True)
    bridge.set_question({"row": 1, "sku": "A"})
    bridge.set_takeover({"holder": "PC-2", "list": "DHL"})
    assert bridge.unsaved is True
    assert bridge.question == {"row": 1, "sku": "A"}
    assert bridge.takeover == {"holder": "PC-2", "list": "DHL"}


def test_an_answer_reaches_python(page, qtbot):
    _view, bridge = page
    with qtbot.waitSignal(bridge.questionAnswered, timeout=1000) as caught:
        bridge.answerQuestion(True)
    assert caught.args == [True]


def test_a_reloaded_page_still_refuses_the_keyboard(page, qtbot):
    """mount_page loads the page again when its render process dies. The new
    document gets a new focus proxy, and it must refuse focus like the first."""
    view, _bridge = page
    with qtbot.waitSignal(view.page().loadFinished, timeout=20000):
        view.page().renderProcessTerminated.emit(
            QWebEnginePage.RenderProcessTerminationStatus.CrashedTerminationStatus, 1
        )
    qtbot.waitUntil(
        lambda: view.focusProxy() is not None
        and view.focusProxy().focusPolicy() == Qt.FocusPolicy.NoFocus,
        timeout=5000,
    )
    assert view.focusPolicy() == Qt.FocusPolicy.NoFocus


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
            qtbot, view, "getComputedStyle(document.getElementById('list')).display"
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


def _row(**over):
    row = {
        "row": 0, "product": "Sunscreen SPF 50", "sku": "SPF-50", "required": 8, "packed": 3,
        "state": "partial", "just_changed": False, "confirm": True, "undo": True,
        "force": True, "force_slot": True, "map": True, "mapBarcode": False,
    }
    row.update(over)
    return row


def test_the_page_has_nothing_that_could_take_the_keyboard(page, qtbot):
    view, _bridge = page
    assert _eval(
        qtbot, view,
        "document.querySelectorAll('input, textarea, select, [contenteditable]').length",
    ) == 0


def test_the_page_reports_the_revision_it_painted(page, qtbot):
    _view, bridge = page
    bridge.set_items([_row()])
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


def test_the_kit_and_the_floor_sheet_are_loaded(page, qtbot):
    view, bridge = page
    bridge.set_items([_row()])
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    style = "getComputedStyle(document.querySelector('.sku-row %s')).%s"
    assert _eval(qtbot, view, style % (".badge", "height")) == "28px"   # floor.css
    assert _eval(qtbot, view, style % (".btn", "height")) == "40px"     # floor.css compact
    assert _eval(qtbot, view, style % (".btn", "alignItems")) == "center"  # kit.css
    assert _eval(qtbot, view, "getComputedStyle(document.querySelector('.sku-row')).minHeight") == "64px"


def test_6a_waiting_shows_the_info_band_and_an_empty_list(page, qtbot):
    view, bridge = page
    bridge.set_feedback("Scan an order barcode", "info", "")
    _until_js(qtbot, view, "document.getElementById('feedback').className === 'feedback feedback--info'")
    assert _eval(qtbot, view, "document.getElementById('list-empty').hidden") is False
    assert _eval(qtbot, view, "document.getElementById('list-empty').textContent") == "No order open"
    assert _eval(qtbot, view, "document.getElementById('list-head').hidden") is True
    assert _eval(qtbot, view, "document.getElementById('banner').hidden") is True
    assert _eval(qtbot, view, "document.getElementById('feedback-raw-box').hidden") is True


def test_6b_a_row_reads_sku_product_numeral_badge(page, qtbot):
    view, bridge = page
    bridge.set_items([_row()])
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    cell = "document.querySelector('.sku-row %s').textContent"
    assert _eval(qtbot, view, cell % ".sku-row__sku") == "SPF-50"
    assert _eval(qtbot, view, cell % ".sku-row__product") == "Sunscreen SPF 50"
    assert _eval(qtbot, view, cell % ".sku-row__num") == "3"
    assert _eval(qtbot, view, cell % ".sku-row__of") == "of 8"
    assert _eval(qtbot, view, "document.querySelector('.sku-row .badge').className") == "badge info"
    assert _eval(qtbot, view, "document.getElementById('list-head').hidden") is False
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('#list-head span')).map(e => e.textContent)",
    ) == ["SKU", "Product", "Packed", "Status", ""]


def test_6b_the_four_slots_are_always_there_in_the_same_order(page, qtbot):
    view, bridge = page
    bridge.set_items([
        _row(row=0),
        # complete: Confirm and Force are disabled, not gone
        _row(row=1, state="complete", packed=8, confirm=False, force=False),
        # a 2-unit, mapped line at zero: Force and Map SKU have no slot, Undo is disabled
        _row(row=2, state="pending", required=2, packed=0, undo=False,
             force=False, force_slot=False, map=False),
    ])
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 3")
    slots = _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('.sku-row')).map(r =>"
        " Array.from(r.querySelectorAll('.row-actions .btn')).map(b =>"
        " [b.textContent, b.disabled, 'absent' in b.dataset]))",
    )
    labels = ["Confirm", "Force confirm", "Undo", "Map SKU"]
    assert [[s[0] for s in row] for row in slots] == [labels, labels, labels]
    assert [(s[1], s[2]) for s in slots[0]] == [(False, False)] * 4
    assert [(s[1], s[2]) for s in slots[1]] == [(True, False), (True, False), (False, False), (False, False)]
    assert [(s[1], s[2]) for s in slots[2]] == [(False, False), (True, True), (True, False), (True, True)]
    assert _eval(
        qtbot, view,
        "getComputedStyle(document.querySelector('.btn[data-absent]')).visibility",
    ) == "hidden"


def test_6c_the_scanned_row_and_the_raw_scan(page, qtbot):
    view, bridge = page
    bridge.set_items([_row(just_changed=True)])
    bridge.set_feedback("SPF-50 confirmed — 3 of 8 packed", "success", "SPF-50")
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row--just-changed').length === 1")
    assert _eval(qtbot, view, "document.getElementById('feedback').className") == "feedback feedback--success"
    assert _eval(qtbot, view, "document.getElementById('feedback-raw-box').hidden") is False
    assert _eval(qtbot, view, "document.getElementById('feedback-raw').textContent") == "SPF-50"
    assert _eval(
        qtbot, view,
        "getComputedStyle(document.querySelector('.sku-row--just-changed')).borderLeftWidth",
    ) == "6px"


def test_the_flash_frame_is_ten_pixels_on_the_main_column(page, qtbot):
    view, _bridge = page
    assert _eval(
        qtbot, view, "document.getElementById('flash').parentElement.id"
    ) == "doc-main"
    assert _eval(
        qtbot, view, "getComputedStyle(document.getElementById('flash')).borderTopWidth"
    ) == "10px"


def test_6d_extras_sit_below_the_items_inside_the_list(page, qtbot):
    view, bridge = page
    bridge.set_items([_row()])
    bridge.set_extras([{"sku": "MSCBLK", "count": 2}])
    _until_js(qtbot, view, "document.querySelectorAll('.extras-row').length === 1")
    assert _eval(
        qtbot, view,
        "document.getElementById('sku-list').compareDocumentPosition("
        "document.getElementById('extras')) & Node.DOCUMENT_POSITION_FOLLOWING",
    ) != 0
    assert _eval(qtbot, view, "document.getElementById('list-scroll').contains(document.getElementById('extras'))") is True
    assert _eval(qtbot, view, "document.querySelector('.extras-row .badge').textContent") == "Extra"
    assert _eval(qtbot, view, "document.querySelector('.extras-row .sku-row__num').textContent") == "× 2"


def test_6e_an_unmatched_scan_is_a_no_match_row_that_only_maps(page, qtbot):
    view, bridge = page
    bridge.set_items([_row()] + unknown_rows(["4006381333931"]))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row--unknown').length === 1")
    row = "document.querySelector('.sku-row--unknown %s').textContent"
    assert _eval(qtbot, view, row % ".badge") == "No match"
    assert _eval(qtbot, view, row % ".sku-row__code") == "4006381333931"
    assert _eval(qtbot, view, row % ".sku-row__why") == "Not a SKU or barcode this client knows"
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('.sku-row--unknown .btn')).map(b => b.textContent)",
    ) == ["Map barcode…"]
    with qtbot.waitSignal(bridge.mapBarcodeRequested, timeout=5000) as caught:
        view.page().runJavaScript("document.querySelector('.sku-row--unknown .btn').click()")
    assert caught.args == ["4006381333931"]


def test_6f_the_question_shows_and_each_button_answers(page, qtbot):
    view, bridge = page
    assert _eval(qtbot, view, "document.getElementById('question').hidden") is True
    bridge.set_question(
        {"row": 0, "sku": "SPF-50", "product": "Sunscreen SPF 50", "remaining": 5, "required": 8}
    )
    _until_js(qtbot, view, "document.getElementById('question').hidden === false")
    assert _eval(qtbot, view, "document.querySelector('#question .dialog-title').textContent") == (
        "Force confirm SPF-50?"
    )
    assert _eval(qtbot, view, "document.querySelector('#question .dialog-text').textContent") == (
        "Marks the remaining 5 of 8 × Sunscreen SPF 50 as packed without scanning."
        " This cannot be undone."
    )
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('#question .btn')).map(b => b.textContent)",
    ) == ["Cancel", "Force confirm"]
    with qtbot.waitSignal(bridge.questionAnswered, timeout=5000) as caught:
        view.page().runJavaScript("document.querySelector('[data-action=\"answerYes\"]').click()")
    assert caught.args == [True]
    with qtbot.waitSignal(bridge.questionAnswered, timeout=5000) as caught:
        view.page().runJavaScript("document.querySelector('[data-action=\"answerNo\"]').click()")
    assert caught.args == [False]
    bridge.set_question({})
    _until_js(qtbot, view, "document.getElementById('question').hidden === true")


def test_6g_a_complete_row_goes_quiet(page, qtbot):
    view, bridge = page
    bridge.set_items([_row(state="complete", packed=8, confirm=False, force=False)])
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row--complete').length === 1")
    assert _eval(qtbot, view, "document.querySelector('.sku-row .badge').className") == "badge success"
    assert _eval(
        qtbot, view, "getComputedStyle(document.querySelector('.sku-row__num')).fontWeight"
    ) == "400"


def test_6i_the_unsaved_banner_follows_its_own_state(page, qtbot):
    view, bridge = page
    bridge.set_feedback("SPF-50 confirmed — 3 of 8 packed", "success", "SPF-50")
    assert _eval(qtbot, view, "document.getElementById('unsaved').hidden") is True
    bridge.set_unsaved(True)
    _until_js(qtbot, view, "document.getElementById('unsaved').hidden === false")
    assert "Progress not saved — check the network" in _eval(
        qtbot, view, "document.getElementById('unsaved').textContent"
    )
    assert _eval(qtbot, view, "document.getElementById('feedback').className") == "feedback feedback--success"
    bridge.set_unsaved(False)
    _until_js(qtbot, view, "document.getElementById('unsaved').hidden === true")


def test_6j_the_takeover_panel_names_the_holder_and_only_exits(page, qtbot):
    view, bridge = page
    assert _eval(qtbot, view, "document.getElementById('takeover').hidden") is True
    bridge.set_takeover({"holder": "Georgi Dimitrov", "list": "acme-packing-07-10"})
    _until_js(qtbot, view, "document.getElementById('takeover').hidden === false")
    assert _eval(qtbot, view, "document.querySelector('#takeover .dialog-title').textContent.trim()") == (
        "This list is open on another PC"
    )
    text = _eval(qtbot, view, "document.querySelector('#takeover .dialog-text').textContent")
    assert text.startswith("Georgi Dimitrov has taken over acme-packing-07-10. This PC has stopped packing it")
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('#takeover .btn')).map(b => b.textContent)",
    ) == ["Exit packing"]
    with qtbot.waitSignal(bridge.exitPackingRequested, timeout=5000):
        view.page().runJavaScript("document.querySelector('#takeover .btn').click()")


def test_a_long_sentence_stays_inside_the_band(page, qtbot):
    view, bridge = page
    bridge.set_feedback("Unknown SKU " + "9" * 90 + " — scan again or map it", "danger", "9" * 90)
    _until_js(qtbot, view, "document.getElementById('feedback-text').textContent.length > 90")
    assert _eval(
        qtbot, view,
        "document.getElementById('feedback').scrollWidth <= document.getElementById('feedback').clientWidth",
    ) is True
    assert _eval(
        qtbot, view,
        "document.getElementById('doc-main').scrollWidth <= document.getElementById('doc-main').clientWidth",
    ) is True


def test_the_side_column_is_248_pixels_and_lists_skus_with_a_dot(page, qtbot):
    view, bridge = page
    bridge.set_sku_rollup([
        {"sku": "CRM-50ML", "product": "", "packed": 1, "required": 3, "state": "partial"},
        {"sku": "LIP-RED", "product": "", "packed": 2, "required": 2, "state": "complete"},
    ])
    _until_js(qtbot, view, "document.querySelectorAll('.rollup-row').length === 2")
    assert _eval(qtbot, view, "document.querySelector('.side').getBoundingClientRect().width") == 248
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('.rollup-row .dot')).map(d => d.className)",
    ) == ["dot dot--partial", "dot dot--complete"]
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('.rollup-row__qty')).map(e => e.textContent)",
    ) == ["1 / 3", "2 / 2"]
