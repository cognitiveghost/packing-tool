"""The packer row's action buttons stay in their own cell (dr-37 item 3).

The action group is right-aligned in a fixed track. Bulgarian labels are
wider than the track, so the group used to spill left over the status chip.
"""

import json

from PySide6.QtWidgets import QWidget
from test_packer_scanner_focus import ITEMS, STATE, _showing

_ROW_EDGES_JS = """JSON.stringify((() => {
  const row = document.querySelector('.sku-row');
  const edge = (selector) => row.querySelector(selector).getBoundingClientRect();
  return {
    action: edge('.row-actions .btn').left,
    status: edge('.sku-row__status').right,
    badge: edge('.sku-row__status .badge').right,
  };
})())"""


def _row_edges(qtbot, view):
    # Through JSON: this build's runJavaScript cannot marshal a JS object.
    found = []
    view.page().runJavaScript(_ROW_EDGES_JS, found.append)
    qtbot.waitUntil(lambda: bool(found), timeout=5000)
    return json.loads(found[0])


def _assert_actions_clear_of_status(qtbot, widget: QWidget):
    widget.display_order(ITEMS, STATE)
    qtbot.waitUntil(lambda: widget.bridge.painted_revision >= widget.bridge.revision, timeout=5000)
    edges = _row_edges(qtbot, widget.document_view)
    assert edges["action"] >= edges["status"]
    assert edges["badge"] <= edges["status"]


def test_bg_action_buttons_stay_clear_of_the_status_chip(qtbot):
    from main import APP_ROOT
    from shared import i18n

    i18n.set_language("bg", i18n.catalogue_files(APP_ROOT, "bg"))
    widget = _showing(qtbot)
    _assert_actions_clear_of_status(qtbot, widget)


def test_en_action_buttons_stay_clear_of_the_status_chip(qtbot):
    widget = _showing(qtbot)
    _assert_actions_clear_of_status(qtbot, widget)
