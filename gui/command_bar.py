"""The 60px bar above Packer Assistant's pages.

UI refresh phase 1, spec docs/superpowers/specs/2026-10-08-ui-refresh-phase1-shell-design.md
section 6.3, following docs/design/ui-refresh/mockups/Packer App.html frames
2a-2e.

Packer Assistant's own, not Fulfilment's CommandBar: that one carries client
groups, recent sessions and a stock chip this app has no use for. It holds
widgets and no application state -- MainWindow connects them and tells the bar
which page and session it is showing, whether a client is chosen and whether
the server answers.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QWidget,
)

from shared.components.overflow import OverflowMenu, overflow_button
from shared.icons import icon
from shared.theme import font_css, on_theme_changed, set_button_role

BAR_HEIGHT = 60
PAGES = ("packing", "statistics", "browser")
_CLIENT_WIDTH = 250
_FILTER_MIN, _FILTER_MAX = 170, 300
_END_TIP = "End the current packing session"


def bar_css(tokens, selector: str = "CommandBar") -> str:
    """The 60px bar's ground, its bottom border and its session label.

    Packer Mode builds its own bar rather than becoming a fourth page of this
    one -- it wants none of the client combo, filter or buttons above. What
    the two bars share is this rule set, so it has one definition and takes
    the selector it paints. Type-scoped: a bare rule would repaint every
    child button.
    """
    return (
        f"{selector} {{ background-color: {tokens.surface_sunken};"
        f" border-bottom: 1px solid {tokens.border_subtle}; }}"
        f" QLabel#cmdbarSession {{ {font_css('body')} background: transparent;"
        f" font-family: {tokens.font_family_mono}; color: {tokens.text}; }}"
    )


class CommandBar(QWidget):
    sidebarToggled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A plain QWidget subclass ignores a background rule without this.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(BAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self.sidebar_button = QToolButton(self)
        self.sidebar_button.setObjectName("cmdbarSidebarToggle")
        self.sidebar_button.setAutoRaise(True)
        self.sidebar_button.setFixedSize(44, 44)
        self.sidebar_button.clicked.connect(self.sidebarToggled.emit)
        layout.addWidget(self.sidebar_button)

        self.client_combo = QComboBox(self)
        self.client_combo.setFixedWidth(_CLIENT_WIDTH)
        self.client_combo.setPlaceholderText("Choose a client")
        self.client_combo.setToolTip("Client")
        layout.addWidget(self.client_combo)

        self.session_label = QLabel("", self)
        self.session_label.setObjectName("cmdbarSession")
        layout.addWidget(self.session_label)

        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText("Filter orders")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setMinimumWidth(_FILTER_MIN)
        self.filter_input.setMaximumWidth(_FILTER_MAX)
        # 100 against the spacer's 1: the filter takes the room up to its
        # maximum before the spacer gets any.
        layout.addWidget(self.filter_input, 100)

        layout.addStretch(1)

        self.open_session_button = QPushButton("Open session", self)
        set_button_role(self.open_session_button, "primary")
        self.start_packing_button = QPushButton("Start packing", self)
        set_button_role(self.start_packing_button, "primary")
        self.start_packing_button.setToolTip("Start packing · opens Packer Mode")
        self.end_session_button = QPushButton("End session", self)
        set_button_role(self.end_session_button, "secondary")
        for button in (
            self.open_session_button,
            self.start_packing_button,
            self.end_session_button,
        ):
            layout.addWidget(button)

        # The shortcut, drawn inside End session at its right edge. A child
        # label, because a QPushButton's text has one font.
        self.end_shortcut_label = QLabel("Ctrl+E", self.end_session_button)
        self.end_shortcut_label.setObjectName("cmdbarKbd")
        self.end_shortcut_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        hint_row = QHBoxLayout(self.end_session_button)
        hint_row.setContentsMargins(0, 0, 14, 0)
        hint_row.addStretch(1)
        hint_row.addWidget(self.end_shortcut_label)

        self.overflow = OverflowMenu(self)
        self.overflow_button = overflow_button(self.overflow, self)
        self.overflow_button.setToolTip("More")
        self.overflow_button.setFixedSize(44, 44)
        layout.addWidget(self.overflow_button)

        self._page = "packing"
        self._has_session = False
        self._client_chosen = False
        self._reachable = True
        self._sidebar_expanded = True
        on_theme_changed(self, self._apply_theme)
        self._refresh()

    def _apply_theme(self, tokens) -> None:
        self._tokens = tokens
        hint_width = QFontMetrics(self.end_shortcut_label.font()).horizontalAdvance(
            "Ctrl+E"
        )
        self.setStyleSheet(
            bar_css(tokens)
            + f" QToolButton#cmdbarSidebarToggle {{ background-color: transparent;"
            f" border: none; border-radius: 8px; }}"
            f" QToolButton#cmdbarSidebarToggle:hover {{"
            f" background-color: {tokens.surface_raised}; }}"
            f" QLabel#cmdbarKbd {{ background: transparent;"
            f" font-family: {tokens.font_family_mono}; {font_css('caption')} }}"
        )
        # Room for the hint: the button's own text stays left of it.
        # Scoped to QPushButton: a bare declaration would reach the child label.
        self.end_session_button.setStyleSheet(
            f"QPushButton {{ text-align: left; padding-right: {hint_width + 28}px; }}"
        )
        self._paint_sidebar_button()
        self._paint_hint()

    def _paint_sidebar_button(self) -> None:
        expanded = self._sidebar_expanded
        self.sidebar_button.setIcon(
            icon("panel-left-close" if expanded else "panel-left-open")
        )
        self.sidebar_button.setToolTip(
            "Collapse sidebar" if expanded else "Expand sidebar"
        )

    def _paint_hint(self) -> None:
        tokens = self._tokens
        colour = (
            tokens.text_secondary
            if self.end_session_button.isEnabled()
            else tokens.text_disabled
        )
        self.end_shortcut_label.setStyleSheet(f"color: {colour};")

    def set_page(self, name: str) -> None:
        if name not in PAGES:
            raise KeyError(f"Unknown page {name!r}; expected one of {PAGES}")
        self._page = name
        self._refresh()

    def set_session(self, session_id: str | None) -> None:
        self._has_session = bool(session_id)
        self.session_label.setText(session_id or "")
        self._refresh()

    def set_client_chosen(self, chosen: bool) -> None:
        self._client_chosen = chosen
        self._refresh()

    def set_server_reachable(self, reachable: bool) -> None:
        self._reachable = reachable
        self._refresh()

    def set_sidebar_expanded(self, expanded: bool) -> None:
        self._sidebar_expanded = expanded
        self._paint_sidebar_button()

    def _refresh(self) -> None:
        packing = self._page == "packing"
        self.session_label.setHidden(not self._has_session)
        self.filter_input.setHidden(not packing)
        self.filter_input.setEnabled(self._has_session)

        self.open_session_button.setHidden(not (packing and not self._has_session))
        self.open_session_button.setEnabled(self._client_chosen and self._reachable)
        if not self._reachable:
            open_tip = "Open session · server unreachable"
        elif not self._client_chosen:
            open_tip = "Open session · choose a client first"
        else:
            open_tip = "Open session"
        self.open_session_button.setToolTip(open_tip)

        for button in (self.start_packing_button, self.end_session_button):
            button.setHidden(not (packing and self._has_session))
        self.end_session_button.setEnabled(self._has_session and self._reachable)
        self.end_session_button.setToolTip(
            _END_TIP if self._reachable else "End session · server unreachable"
        )
        if hasattr(self, "_tokens"):
            self._paint_hint()
