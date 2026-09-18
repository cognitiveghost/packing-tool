"""The bridge and the page, driven through a real Chromium (ADR 0001).

CI runs the suite on windows-latest, where QtWebEngine needs no extra runtime
packages. Never mark these skip -- a bridge nobody can run is a bridge nobody
guards.
"""

import time

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.packer_bridge import PAGE, THEME_MARKER, mount_packer_page
from gui.theme import apply_theme
from shared.theme import THEME_DARK, THEME_LIGHT


def _eval(qtbot, view, expr, timeout=5000):
    box = []
    view.page().runJavaScript(expr, 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return box[0]


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
