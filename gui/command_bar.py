"""The 60px bar above Packing Tool's pages (artboard T1/T2).

Packing Tool's own, not Shopify's CommandBar: that one carries client groups,
recent sessions and a stock chip this app has no use for (Bundle 3 spec E4,
owner answer Q1). It holds widgets and no application state -- MainWindow
connects them and tells the bar which page and session it is showing.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from shared.components.overflow import OverflowMenu, overflow_button
from shared.theme import font_css, on_theme_changed, set_button_role

BAR_HEIGHT = 60
PAGES = ("packing", "statistics", "browser")
_CLIENT_WIDTH = 240
_FILTER_WIDTH = 220


class CommandBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A plain QWidget subclass ignores a background rule without this.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(BAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self.client_combo = QComboBox(self)
        self.client_combo.setFixedWidth(_CLIENT_WIDTH)
        layout.addWidget(self.client_combo)

        self.session_label = QLabel("No session", self)
        self.session_label.setObjectName("cmdbarSession")
        layout.addWidget(self.session_label)

        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText("Filter orders")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setFixedWidth(_FILTER_WIDTH)
        layout.addWidget(self.filter_input)

        layout.addStretch(1)

        self.open_session_button = QPushButton("Open session", self)
        set_button_role(self.open_session_button, "primary")
        self.start_packing_button = QPushButton("Start packing", self)
        set_button_role(self.start_packing_button, "primary")
        self.sku_mapping_button = QPushButton("SKU mapping", self)
        self.end_session_button = QPushButton("End session", self)
        for button in (
            self.open_session_button,
            self.start_packing_button,
            self.sku_mapping_button,
            self.end_session_button,
        ):
            layout.addWidget(button)

        self.overflow = OverflowMenu(self)
        self.overflow_button = overflow_button(self.overflow, self)
        self.overflow_button.setToolTip("More")
        layout.addWidget(self.overflow_button)

        self._page = "packing"
        self._has_session = False
        on_theme_changed(self, self._apply_theme)
        self._refresh()

    def _apply_theme(self, tokens) -> None:
        # Type-scoped selectors: a bare rule would repaint every child button.
        self.setStyleSheet(
            f"CommandBar {{ background-color: {tokens.surface_raised};"
            f" border-bottom: 1px solid {tokens.border_subtle}; }}"
            f" QLabel#cmdbarSession {{ {font_css('body')}"
            f" font-family: {tokens.font_family_mono}; color: {tokens.text_secondary}; }}"
        )

    def set_page(self, name: str) -> None:
        if name not in PAGES:
            raise KeyError(f"Unknown page {name!r}; expected one of {PAGES}")
        self._page = name
        self._refresh()

    def set_session(self, session_id: str | None) -> None:
        self._has_session = bool(session_id)
        self.session_label.setText(session_id or "No session")
        self._refresh()

    def _refresh(self) -> None:
        packing = self._page == "packing"
        self.session_label.setHidden(self._page == "browser")
        self.filter_input.setHidden(not packing)
        self.filter_input.setEnabled(self._has_session)
        self.open_session_button.setHidden(not (packing and not self._has_session))
        for button in (
            self.start_packing_button,
            self.sku_mapping_button,
            self.end_session_button,
        ):
            button.setHidden(not (packing and self._has_session))
