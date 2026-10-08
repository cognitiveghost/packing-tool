"""The shell's pages: one web view, and the Qt Sessions page beside it (ADR 0003).

Packing and Statistics are two pages of one document in one QWebEngineView;
Sessions joins it in phase 4 and is the Qt SessionBrowserWidget until then.
This widget speaks the part of QTabWidget MainWindow's call sites already
use, so they kept `session_tabs` and did not change.
"""

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from gui.app_bridge import mount_app_page

PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER = range(3)
# The bridge's name for each page the document draws.
_WEB_PAGES = {PAGE_PACKING: "packing", PAGE_STATISTICS: "statistics"}


class AppPages(QWidget):
    currentChanged = Signal(int)

    def __init__(self, session_browser: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.view = QWebEngineView(self)
        self.bridge = mount_app_page(self.view)
        self.browser = session_browser

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self.view)
        self._stack.addWidget(session_browser)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self._index = PAGE_PACKING

    def count(self) -> int:
        return 3

    def currentIndex(self) -> int:
        return self._index

    def widget(self, index: int) -> QWidget:
        return self.browser if index == PAGE_BROWSER else self.view

    def web_is_current(self) -> bool:
        return self._stack.currentWidget() is self.view

    def setCurrentIndex(self, index: int) -> None:
        if index == self._index or index not in (PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER):
            return
        self._index = index
        if index in _WEB_PAGES:
            self.bridge.set_page(_WEB_PAGES[index])
        self._stack.setCurrentWidget(self.widget(index))
        self.currentChanged.emit(index)
