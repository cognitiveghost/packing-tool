"""The app bridge and its page, driven through a real Chromium (ADR 0003).

Never mark these skip -- a bridge nobody can run is a bridge nobody guards.
"""

import json
import time

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.app_bridge import PAGE, mount_app_page, session_payload
from gui.theme import apply_theme
from shared.theme import THEME_DARK, THEME_LIGHT
from shared.web_page import THEME_MARKER


def _eval(qtbot, view, expr, timeout=5000):
    # runJavaScript cannot marshal a JS array back; route everything through JSON.
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def _until_js(qtbot, view, expr, timeout_s=20):
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


def _shown(view, qtbot, element_id):
    return _eval(qtbot, view, f"!document.getElementById('{element_id}').hidden")


def _text(view, qtbot, element_id):
    return _eval(qtbot, view, f"document.getElementById('{element_id}').textContent")


def _click(view, qtbot, element_id):
    _eval(qtbot, view, f"(document.getElementById('{element_id}').click(), true)")


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_app_page(view)
    view.resize(1166, 708)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _settle(qtbot, bridge):
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


OPEN = session_payload(
    "open", list_name="DHL_Orders", session_id="2026-10-07_1", orders=4, couriers=["DHL", "DPD"]
)


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_reports_the_revision_it_painted(page, qtbot):
    _view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    _settle(qtbot, bridge)
    assert bridge.painted_revision == bridge.revision


def test_a_theme_switch_repaints_without_a_reload(page, qtbot, qapp):
    view, _ = page
    before = _text(view, qtbot, "theme-vars")
    apply_theme(qapp, THEME_LIGHT)
    try:
        qtbot.waitUntil(lambda: _text(view, qtbot, "theme-vars") != before, timeout=10000)
    finally:
        apply_theme(qapp, THEME_DARK)


def test_with_no_client_the_page_asks_for_one(page, qtbot):
    view, bridge = page
    chosen = []
    bridge.chooseClientRequested.connect(lambda: chosen.append(1))
    bridge.set_shell(client=False, clients=True, server_down=False)
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "no-client")
    assert not _shown(view, qtbot, "no-session")
    assert _text(view, qtbot, "no-client-title") == "Choose a client to begin"
    _click(view, qtbot, "choose-client")
    qtbot.waitUntil(lambda: chosen == [1], timeout=5000)


def test_with_no_clients_at_all_there_is_no_button(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=False, clients=False, server_down=False)
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "no-client")
    assert not _shown(view, qtbot, "choose-client")


def test_3a_no_session_offers_open_session(page, qtbot):
    view, bridge = page
    opened = []
    bridge.openSessionRequested.connect(lambda: opened.append(1))
    bridge.set_shell(client=True, clients=True, server_down=False)
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "no-session")
    assert not _shown(view, qtbot, "head")
    _click(view, qtbot, "open-session")
    qtbot.waitUntil(lambda: opened == [1], timeout=5000)


def test_3a_open_session_is_disabled_while_the_server_is_down(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=True)
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.getElementById('open-session').disabled") is True


def test_4a_statistics_with_no_session_points_back_to_packing(page, qtbot):
    view, bridge = page
    asked = []
    bridge.pageRequested.connect(asked.append)
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_page("statistics")
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "stats-empty")
    assert not _shown(view, qtbot, "no-session")
    _click(view, qtbot, "go-packing")
    qtbot.waitUntil(lambda: asked == ["packing"], timeout=5000)


@pytest.mark.parametrize("step, name", [
    (1, "Taking the packing list"),
    (2, "Reading saved progress"),
    (3, "Reading the packing list"),
])
def test_3b_opening_names_the_step(page, qtbot, step, name):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(session_payload(
        "opening", list_name="DHL_Orders", session_id="2026-10-07_1", step=step))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "opening")
    assert _shown(view, qtbot, "head")
    assert _text(view, qtbot, "head-title") == "DHL_Orders"
    assert not _shown(view, qtbot, "head-badge")
    assert not _shown(view, qtbot, "head-start")
    assert _text(view, qtbot, "step-count") == f"Working · step {step} of 3"
    assert _text(view, qtbot, "step-name") == name
    assert _eval(qtbot, view, "document.querySelectorAll('.app-step-bar.done').length") == step


def test_3c_a_failed_start_says_why_and_offers_retry_and_close(page, qtbot):
    view, bridge = page
    said = []
    bridge.retryStartRequested.connect(lambda: said.append("retry"))
    bridge.closeFailureRequested.connect(lambda: said.append("close"))
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(session_payload(
        "failed", list_name="DHL_Orders", title="Packing list could not be loaded",
        text="DHL_Orders has an order with no courier. Found: items, order_number."))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "failed")
    assert not _shown(view, qtbot, "opening")
    assert _text(view, qtbot, "failed-title") == "Packing list could not be loaded"
    assert "no courier" in _text(view, qtbot, "failed-text")
    _click(view, qtbot, "failed-retry")
    _click(view, qtbot, "failed-close")
    qtbot.waitUntil(lambda: said == ["retry", "close"], timeout=5000)


def test_an_open_session_shows_the_header_with_its_meta(page, qtbot):
    view, bridge = page
    started = []
    bridge.startPackingRequested.connect(lambda: started.append(1))
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(OPEN)
    _settle(qtbot, bridge)
    assert _text(view, qtbot, "head-title") == "DHL_Orders"
    assert _text(view, qtbot, "head-id") == "2026-10-07_1"
    assert _text(view, qtbot, "head-meta") == "4 orders · DHL, DPD"
    assert _shown(view, qtbot, "head-badge")
    _click(view, qtbot, "head-start")
    qtbot.waitUntil(lambda: started == [1], timeout=5000)


def test_on_statistics_the_header_is_titled_statistics(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(OPEN)
    bridge.set_page("statistics")
    _settle(qtbot, bridge)
    assert _text(view, qtbot, "head-title") == "Statistics"
    assert _text(view, qtbot, "head-meta") == "DHL_Orders"
    assert not _shown(view, qtbot, "head-start")
    assert not _shown(view, qtbot, "head-id")


def test_covered_draws_nothing(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(OPEN)
    bridge.set_covered(True)
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.body.innerText.trim()") == ""
    bridge.set_covered(False)
    _settle(qtbot, bridge)
    assert "DHL_Orders" in _eval(qtbot, view, "document.body.innerText")


def test_the_page_draws_a_toast_and_dismisses_it(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    _settle(qtbot, bridge)
    bridge.raise_toast("Loaded 4 orders from DHL_Orders.")
    _until_js(qtbot, view, "!document.getElementById('toast').hidden")
    assert _text(view, qtbot, "toast-text") == "Loaded 4 orders from DHL_Orders."
    _click(view, qtbot, "toast-close")
    assert not _shown(view, qtbot, "toast")
