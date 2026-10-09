"""Helpers for driving the setup document in a real Chromium."""

import json
import time

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.setup_bridge import mount_setup_page


def eval_js(qtbot, view, expr, timeout=5000):
    # runJavaScript cannot marshal a JS array back; route everything through JSON.
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def until_js(qtbot, view, expr, timeout_s=20):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = max(int((deadline - time.monotonic()) * 1000), 50)
        try:
            if eval_js(qtbot, view, expr, timeout=min(remaining, 5000)) is True:
                return
        except (QtBotTimeoutError, ValueError):
            continue
        qtbot.wait(50)
    pytest.fail(f"never became true in the page: {expr}")


def run_js(qtbot, view, code):
    """Run statements in the page."""
    return eval_js(qtbot, view, f"(function () {{ {code}; return true; }})()")


def shown(view, qtbot, element_id):
    """Visible: neither it nor an ancestor is hidden."""
    return eval_js(
        qtbot, view,
        f"(function () {{ const n = document.getElementById('{element_id}');"
        " return !!n && !n.closest('[hidden]'); })()",
    )


def text(view, qtbot, element_id):
    return eval_js(qtbot, view, f"document.getElementById('{element_id}').textContent")


def click(view, qtbot, element_id):
    run_js(qtbot, view, f"document.getElementById('{element_id}').click()")


def set_value(view, qtbot, element_id, value):
    """Type into an input the way a person does: the value, then an input event."""
    run_js(
        qtbot, view,
        f"const n = document.getElementById('{element_id}'); n.focus();"
        f" n.value = {json.dumps(value)};"
        " n.dispatchEvent(new Event('input', {bubbles: true}))",
    )


def press(view, qtbot, element_id, key, ctrl=False):
    """A keydown on an element ('' for the document body)."""
    target = f"document.getElementById('{element_id}')" if element_id else "document.body"
    run_js(
        qtbot, view,
        f"{target}.dispatchEvent(new KeyboardEvent('keydown',"
        f" {{key: {json.dumps(key)}, ctrlKey: {str(bool(ctrl)).lower()},"
        " bubbles: true, cancelable: true}))",
    )


def settle(qtbot, bridge):
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


def mounted(qtbot):
    """A shown view with the setup document loaded: (view, bridge)."""
    view = QWebEngineView()
    qtbot.addWidget(view)
    view.resize(1366, 768)
    bridge = mount_setup_page(view)
    view.show()
    qtbot.waitExposed(view)
    until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge
