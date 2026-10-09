"""The shell's pages: one web view (ADR 0003).

Packing, Statistics, Sessions and Session details are pages of one document
in one QWebEngineView. This widget speaks the part of QTabWidget MainWindow's
call sites already use, so they kept `session_tabs` and did not change.
"""

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.app_bridge import mount_app_page

PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER = range(3)


class AppPages(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.view = QWebEngineView(self)
        self.bridge = mount_app_page(self.view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self._index = PAGE_PACKING

    def count(self) -> int:
        return 3

    def currentIndex(self) -> int:
        return self._index

    def widget(self, index: int) -> QWidget:
        return self.view

    def _page_name(self, index: int) -> str:
        """The bridge's name for the page an index shows."""
        if index == PAGE_BROWSER:
            # Details left for another page are the details come back to.
            return "details" if self.bridge.details else "sessions"
        return "statistics" if index == PAGE_STATISTICS else "packing"

    def setCurrentIndex(self, index: int) -> None:
        if index == self._index or index not in (PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER):
            return
        self._index = index
        self.bridge.set_page(self._page_name(index))
        self.currentChanged.emit(index)
