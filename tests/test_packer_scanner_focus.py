"""D3, the scanner invariant: a click inside the web view must not eat scans.

Barcode scanners are keyboard wedges typing into a hidden QLineEdit. A
QWebEngineView takes keyboard focus when clicked, which would swallow every
scan after the packer touches the document once. This test is the gate; the
owner confirms the same with a real scanner on a Windows build.
"""

import json

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from gui.packer_mode_widget import PackerModeWidget


def test_a_scan_still_reaches_the_widget_after_a_click_in_the_document(qtbot):
    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.resize(1366, 700)
    widget.show()
    qtbot.waitExposed(widget)

    seen = []
    widget.barcode_scanned.connect(seen.append)

    view = widget.document_view
    QTest.mouseClick(
        view.focusProxy() or view, Qt.MouseButton.LeftButton, pos=view.rect().center()
    )
    qtbot.wait(100)

    # The invariant itself: the click left focus on the scanner. Asserting this
    # before typing is what makes the test able to fail -- restoring focus here,
    # or typing into scanner_input directly, would pass with deny_focus deleted.
    assert QApplication.focusWidget() is widget.scanner_input

    QTest.keyClicks(QApplication.focusWidget(), "4006381333931")
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Return)

    assert seen == ["4006381333931"]


ITEMS = [{"SKU": "SPF-50", "Product_Name": "Sunscreen", "Quantity": 8, "Order_Number": "1002"}]
STATE = [{"row": 0, "packed": 3, "required": 8}]


def _showing(qtbot):
    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.resize(1366, 700)
    widget.show()
    qtbot.waitExposed(widget)
    bridge = widget.bridge
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)
    return widget


def _centre_of(qtbot, view, selector):
    # Through JSON: this build's runJavaScript cannot marshal a JS array.
    found = []
    view.page().runJavaScript(
        f"(() => {{ const r = document.querySelector('{selector}').getBoundingClientRect();"
        " return JSON.stringify([r.left + r.width / 2, r.top + r.height / 2]); })()",
        found.append,
    )
    qtbot.waitUntil(lambda: bool(found), timeout=5000)
    x, y = json.loads(found[0])
    return QPoint(int(x), int(y))


def _scan(widget, text):
    seen = []
    widget.barcode_scanned.connect(seen.append)
    QTest.keyClicks(QApplication.focusWidget(), text)
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Return)
    return seen


def test_a_scan_reaches_the_widget_after_the_question_is_cancelled_in_the_page(qtbot):
    """The question turns the scanner field off, so Qt moves focus off it. A
    click on Cancel, inside the view, must put it back."""
    widget = _showing(qtbot)
    widget.display_order(ITEMS, STATE)
    widget.bridge.forceItem(0)
    assert not widget.scanner_input.isEnabled()
    view = widget.document_view
    qtbot.waitUntil(lambda: widget.bridge.painted_revision >= widget.bridge.revision, timeout=5000)

    with qtbot.waitSignal(widget.bridge.questionAnswered, timeout=5000):
        QTest.mouseClick(
            view.focusProxy() or view,
            Qt.MouseButton.LeftButton,
            pos=_centre_of(qtbot, view, '[data-action="answerNo"]'),
        )

    assert QApplication.focusWidget() is widget.scanner_input
    assert _scan(widget, "4006381333931") == ["4006381333931"]


def test_a_scan_reaches_the_widget_after_the_page_is_loaded_again(qtbot):
    """A dead render process gets a new document and a new focus proxy."""
    widget = _showing(qtbot)
    view = widget.document_view
    with qtbot.waitSignal(view.page().loadFinished, timeout=20000):
        view.page().renderProcessTerminated.emit(
            QWebEnginePage.RenderProcessTerminationStatus.CrashedTerminationStatus, 1
        )
    qtbot.waitUntil(
        lambda: view.focusProxy() is not None
        and view.focusProxy().focusPolicy() == Qt.FocusPolicy.NoFocus,
        timeout=5000,
    )

    QTest.mouseClick(view.focusProxy(), Qt.MouseButton.LeftButton, pos=view.rect().center())
    qtbot.wait(100)

    assert QApplication.focusWidget() is widget.scanner_input
    assert _scan(widget, "4006381333931") == ["4006381333931"]
