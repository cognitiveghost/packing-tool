"""D3, the scanner invariant: a click inside the web view must not eat scans.

Barcode scanners are keyboard wedges typing into a hidden QLineEdit. A
QWebEngineView takes keyboard focus when clicked, which would swallow every
scan after the packer touches the document once. This test is the gate; the
owner confirms the same with a real scanner on a Windows build.
"""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
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
