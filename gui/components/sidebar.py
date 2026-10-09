"""The shell's left column: header, destinations, footer.

UI refresh phase 1, spec docs/superpowers/specs/2026-10-08-ui-refresh-phase1-shell-design.md
section 6.2, following docs/design/ui-refresh/mockups/Packer App.html frames
2a-2e. The same shape as shopify-fulfillment-tool's gui/components/sidebar.py,
at floor sizes and with this app's footer: SKU mapping, the worker, the theme
and the connection.

It holds widgets and no application state. MainWindow tells it the worker,
the theme, the connection state and whether a client is chosen.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.command_bar import BAR_HEIGHT
from gui.setup_payload import initials
from shared.icons import icon
from shared.navrail import RAIL_WIDTH, NavRail
from shared.theme import current_tokens, font_css, on_theme_changed

SIDEBAR_WIDTH = 200
ITEM_HEIGHT = 44
# state -> (label, the status role whose colours it wears)
_CONNECTION = {
    "ok": ("Server connected", "success"),
    "checking": ("Reconnecting…", "warning"),
    "down": ("Server unreachable", "danger"),
}
# 200 - footer margins 16 - card padding 20 - dot 10 - gap 8 = 146, less a few
# px so the ellipsis never touches the card's edge.
_PATH_WIDTH = 140
# 200 - footer margins 16 - card padding 16 - avatar 32 - gap 10 = 126.
_NAME_WIDTH = 122


class FloorNavRail(NavRail):
    """NavRail's sidebar mode at floor density.

    shared/ cannot be edited from this repo, and its sidebar items are 32px
    tall with a 16px icon. Both overrides are of private methods, so
    tests/test_sidebar.py pins the 44px height: a sync that renames either
    fails there instead of quietly shrinking the items. Listed under
    "For shared/" in the phase 1 spec, section 8.
    """

    def _shape(self, button: QToolButton) -> None:
        super()._shape(button)
        button.setFixedHeight(ITEM_HEIGHT)
        button.setIconSize(QSize(20, 20))

    def _apply_theme(self, _name: str | None = None) -> None:
        super()._apply_theme(_name)
        # With no client chosen every destination is disabled, and the mockup
        # (frame 2a) draws none of them as current.
        tokens = current_tokens()
        self.setStyleSheet(
            self.styleSheet()
            + "NavRail QToolButton:checked:disabled { background-color: transparent;"
            f" border: 1px solid transparent; color: {tokens.text_disabled};"
            " font-weight: normal; }"
        )


class Sidebar(QWidget):
    """Header, destinations, footer. Collapses to a 56px rail."""

    skuMappingRequested = Signal()
    switchWorkerRequested = Signal()
    themeRequested = Signal(str)
    retryRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A QWidget subclass paints no QSS background without this.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._expanded = True
        self._state = "ok"
        self._theme_name = current_tokens().name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header: the mark and the app's name. The collapse button is the
        # command bar's first control, as the mockup draws it.
        self.header = QFrame(self)
        self.header.setObjectName("SidebarHeader")
        # The bar's height, so the two rules under them are one line.
        self.header.setFixedHeight(BAR_HEIGHT)
        self._header_row = QHBoxLayout(self.header)
        self._header_row.setSpacing(10)
        self.mark = QLabel(self.header)
        self.mark.setObjectName("SidebarMark")
        self.mark.setFixedSize(32, 32)
        self.mark.setAlignment(Qt.AlignCenter)
        self.title = QLabel("Packer Assistant", self.header)
        self.title.setMinimumWidth(0)
        self._header_row.addWidget(self.mark)
        self._header_row.addWidget(self.title, 1)
        layout.addWidget(self.header)

        self.rail = FloorNavRail(self, expanded_width=SIDEBAR_WIDTH)
        self.rail.layout().setSpacing(4)
        layout.addWidget(self.rail, 1)

        self.footer = QFrame(self)
        self.footer.setObjectName("SidebarFooter")
        footer = QVBoxLayout(self.footer)
        footer.setContentsMargins(8, 8, 8, 8)
        footer.setSpacing(6)

        self.sku_button = QToolButton(self.footer)
        self.sku_button.setObjectName("FooterItem")
        self.sku_button.setText("SKU mapping")
        self.sku_button.setToolTip("SKU mapping…")
        self.sku_button.setAutoRaise(True)
        self.sku_button.setIconSize(QSize(20, 20))
        self.sku_button.clicked.connect(self.skuMappingRequested.emit)
        footer.addWidget(self.sku_button)

        # Worker, expanded: avatar, name, Switch worker… link.
        self.worker_card = QFrame(self.footer)
        self.worker_card.setObjectName("WorkerCard")
        self.worker_card.setMinimumHeight(56)
        self.worker_card.setToolTip("Signed-in worker")
        card = QHBoxLayout(self.worker_card)
        card.setContentsMargins(8, 6, 8, 6)
        card.setSpacing(10)
        self.worker_avatar = QLabel(self.worker_card)
        self.worker_avatar.setObjectName("WorkerAvatar")
        self.worker_avatar.setFixedSize(32, 32)
        self.worker_avatar.setAlignment(Qt.AlignCenter)
        names = QVBoxLayout()
        names.setSpacing(0)
        self.worker_name = QLabel(self.worker_card)
        self.worker_name.setObjectName("WorkerName")
        self.worker_name.setFixedWidth(_NAME_WIDTH)
        self.worker_link = QPushButton("Switch worker…", self.worker_card)
        self.worker_link.setObjectName("WorkerLink")
        self.worker_link.setFlat(True)
        self.worker_link.setCursor(Qt.PointingHandCursor)
        self.worker_link.clicked.connect(self.switchWorkerRequested.emit)
        names.addWidget(self.worker_name)
        names.addWidget(self.worker_link, 0, Qt.AlignLeft)
        card.addWidget(self.worker_avatar)
        card.addLayout(names, 1)
        footer.addWidget(self.worker_card)

        # Worker, collapsed: the avatar is the button.
        self.worker_rail_button = QToolButton(self.footer)
        self.worker_rail_button.setObjectName("WorkerRailButton")
        # A 44px target; the sheet's 6px margin draws the 32px avatar in it.
        self.worker_rail_button.setFixedSize(ITEM_HEIGHT, ITEM_HEIGHT)
        self.worker_rail_button.clicked.connect(self.switchWorkerRequested.emit)
        footer.addWidget(self.worker_rail_button, 0, Qt.AlignHCenter)

        self.theme_segment = QFrame(self.footer)
        self.theme_segment.setObjectName("ThemeSegment")
        self.theme_segment.setFixedHeight(ITEM_HEIGHT)
        segment = QHBoxLayout(self.theme_segment)
        segment.setContentsMargins(2, 2, 2, 2)
        segment.setSpacing(2)
        self.light_button = self._segment_button("Light")
        self.dark_button = self._segment_button("Dark")
        group = QButtonGroup(self.theme_segment)
        group.setExclusive(True)
        for button, name in ((self.light_button, "light"), (self.dark_button, "dark")):
            group.addButton(button)
            segment.addWidget(button)
            button.clicked.connect(lambda _c=False, n=name: self.themeRequested.emit(n))
        footer.addWidget(self.theme_segment)

        self.theme_toggle = QToolButton(self.footer)
        self.theme_toggle.setObjectName("FooterItem")
        self.theme_toggle.setAutoRaise(True)
        self.theme_toggle.setIconSize(QSize(20, 20))
        self.theme_toggle.setFixedSize(RAIL_WIDTH - 16, ITEM_HEIGHT)
        self.theme_toggle.clicked.connect(
            lambda: self.themeRequested.emit(
                "light" if self._theme_name == "dark" else "dark"
            )
        )
        footer.addWidget(self.theme_toggle)

        # Connection, expanded: dot, state, path, Retry.
        self.connection_box = QFrame(self.footer)
        self.connection_box.setObjectName("ConnectionBox")
        self.connection_box.setMinimumHeight(52)
        box = QHBoxLayout(self.connection_box)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(8)
        self.connection_dot = QLabel(self.connection_box)
        self.connection_dot.setFixedSize(10, 10)
        dot_column = QVBoxLayout()
        dot_column.setContentsMargins(0, 4, 0, 0)
        dot_column.addWidget(self.connection_dot)
        dot_column.addStretch()
        box.addLayout(dot_column)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.connection_label = QLabel(self.connection_box)
        self.path_label = QLabel(self.connection_box)
        self.path_label.setFixedWidth(_PATH_WIDTH)
        self.retry_button = QPushButton("Retry", self.connection_box)
        self.retry_button.setObjectName("RetryButton")
        self.retry_button.setFixedHeight(ITEM_HEIGHT)
        self.retry_button.clicked.connect(self.retryRequested.emit)
        self.retry_button.hide()
        text.addWidget(self.connection_label)
        text.addWidget(self.path_label)
        text.addSpacing(4)
        text.addWidget(self.retry_button)
        box.addLayout(text, 1)
        footer.addWidget(self.connection_box)

        # Connection, collapsed: a server glyph with the same dot.
        self.connection_icon = QToolButton(self.footer)
        self.connection_icon.setObjectName("ConnectionIcon")
        self.connection_icon.setIconSize(QSize(20, 20))
        self.connection_icon.setFixedSize(RAIL_WIDTH - 16, ITEM_HEIGHT)
        self.connection_icon.clicked.connect(self._retry_if_down)
        self.connection_icon_dot = QLabel(self.connection_icon)
        self.connection_icon_dot.setFixedSize(10, 10)
        self.connection_icon_dot.move(24, 26)
        self.connection_icon_dot.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        footer.addWidget(self.connection_icon)

        layout.addWidget(self.footer)

        self._server_path = ""
        self._worker = ""
        on_theme_changed(self, self._apply_theme)
        self.set_expanded(True)

    # -- construction helpers -------------------------------------------------

    def _segment_button(self, text: str) -> QToolButton:
        button = QToolButton(self.theme_segment)
        button.setText(text)
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setFixedHeight(ITEM_HEIGHT - 6)
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    def _retry_if_down(self) -> None:
        if self._state == "down":
            self.retryRequested.emit()

    # -- public API -------------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.setFixedWidth(SIDEBAR_WIDTH if expanded else RAIL_WIDTH)
        self.rail.set_expanded(expanded)
        if expanded:
            self._header_row.setContentsMargins(14, 0, 14, 0)
        else:
            # (56 - 32) / 2: the mark centred in the rail.
            self._header_row.setContentsMargins(12, 0, 12, 0)
        for widget in (self.title, self.worker_card, self.theme_segment,
                       self.connection_box):
            widget.setVisible(expanded)
        for widget in (self.worker_rail_button, self.theme_toggle,
                       self.connection_icon):
            widget.setVisible(not expanded)
        self.sku_button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon if expanded else Qt.ToolButtonIconOnly
        )
        self.sku_button.setFixedSize(
            (SIDEBAR_WIDTH if expanded else RAIL_WIDTH) - 16, ITEM_HEIGHT
        )
        self._apply_theme(current_tokens())

    def is_expanded(self) -> bool:
        return self._expanded

    def set_worker(self, name: str) -> None:
        self._worker = name or ""
        letters = initials(self._worker)
        self.worker_avatar.setText(letters)
        self.worker_rail_button.setText(letters)
        metrics = QFontMetrics(self.worker_name.font())
        self.worker_name.setText(
            metrics.elidedText(self._worker, Qt.ElideRight, _NAME_WIDTH)
        )
        self.worker_name.setToolTip(self._worker)
        self.worker_rail_button.setToolTip(f"{self._worker} · Switch worker…")

    def set_theme_name(self, name: str) -> None:
        self._theme_name = name
        (self.dark_button if name == "dark" else self.light_button).setChecked(True)
        self.theme_toggle.setToolTip(
            "Switch to Light" if name == "dark" else "Switch to Dark"
        )
        self.theme_toggle.setIcon(icon("sun" if name == "dark" else "moon"))

    def set_connection(self, state: str, server_path: str) -> None:
        label, _role = _CONNECTION[state]  # KeyError on an unknown state
        self._state = state
        self._server_path = server_path
        self.connection_label.setText(label)
        metrics = QFontMetrics(self.path_label.font())
        self.path_label.setText(
            metrics.elidedText(server_path, Qt.ElideMiddle, _PATH_WIDTH)
        )
        self.path_label.setToolTip(server_path)
        self.connection_box.setToolTip(f"{label} · {server_path}")
        self.connection_icon.setToolTip(f"{label} · {server_path}")
        self.retry_button.setVisible(state == "down")
        self._style_connection(current_tokens())

    def set_client_chosen(self, chosen: bool) -> None:
        for index in range(len(self.rail._buttons)):
            self.rail.button(index).setEnabled(chosen)
        self.sku_button.setEnabled(chosen)

    # -- internals --------------------------------------------------------------

    def _apply_theme(self, t) -> None:
        """Re-run on every theme change: this widget's own sheet outranks the
        app's, and a QIcon is a snapshot (ADR 0003)."""
        pad = 9 if self._expanded else 0
        self.setStyleSheet(
            f"Sidebar {{ background-color: {t.surface_sunken};"
            f" border-right: 1px solid {t.border_subtle}; }}"
            # The app sheet's `QWidget` rule would paint these on `surface`.
            f"#SidebarHeader, #SidebarFooter {{ background-color: {t.surface_sunken}; }}"
            f"#SidebarHeader {{ border-bottom: 1px solid {t.border_subtle}; }}"
            f"#SidebarFooter {{ border-top: 1px solid {t.border_subtle}; }}"
            # Id-on-id: `#SidebarHeader QLabel` below would otherwise win and clear it.
            f"#SidebarHeader #SidebarMark {{ background-color: {t.accent_fill};"
            f" border-radius: 8px; }}"
            f"#SidebarHeader QLabel {{ background: transparent; color: {t.text};"
            f" {font_css('body', bold=True)} }}"
            f"#FooterItem {{ background-color: transparent;"
            f" border: 1px solid transparent; border-radius: 8px;"
            f" padding-left: {pad}px; color: {t.text_secondary}; {font_css('body')} }}"
            f"#FooterItem:hover {{ background-color: {t.hover}; }}"
            f"#FooterItem:disabled {{ color: {t.text_disabled}; }}"
            f"#WorkerCard {{ background-color: {t.surface};"
            f" border: 1px solid {t.border}; border-radius: 8px; }}"
            f"#WorkerCard QLabel {{ background: transparent; }}"
            f"#WorkerAvatar {{ background-color: {t.surface_raised};"
            f" border: 1px solid {t.border_strong}; border-radius: 16px;"
            f" margin: 6px; color: {t.text}; {font_css('caption', bold=True)} }}"
            f"#WorkerName {{ color: {t.text}; {font_css('body', bold=True)} }}"
            f"#WorkerLink {{ background: transparent; border: none; padding: 0;"
            f" min-height: 0; text-align: left; text-decoration: underline;"
            f" color: {t.text_secondary}; {font_css('caption')} }}"
            f"#WorkerLink:hover {{ color: {t.text}; }}"
            f"#WorkerRailButton {{ background-color: {t.surface};"
            f" border: 1px solid {t.border_strong}; border-radius: 16px;"
            f" margin: 6px; color: {t.text}; {font_css('caption', bold=True)} }}"
            f"#ThemeSegment {{ background-color: {t.surface_sunken};"
            f" border: 1px solid {t.border}; border-radius: 8px; }}"
            f"#ThemeSegment QToolButton {{ background-color: transparent;"
            f" border: 1px solid transparent; border-radius: 6px;"
            f" color: {t.text_secondary}; {font_css('caption')} }}"
            f"#ThemeSegment QToolButton:checked {{ background-color: {t.surface};"
            f" border: 1px solid {t.border_subtle}; color: {t.text};"
            f" font-weight: bold; }}"
        )
        self.mark.setPixmap(icon("package", color=t.on_accent).pixmap(18, 18))
        self.sku_button.setIcon(icon("tag"))
        self.light_button.setIcon(icon("sun"))
        self.dark_button.setIcon(icon("moon"))
        self.connection_icon.setIcon(icon("server"))
        self.set_theme_name(t.name)
        self._style_connection(t)

    def _style_connection(self, t) -> None:
        _label, role = _CONNECTION[self._state]
        # No status_warning_dot token: the mockup's amber is under the 3:1
        # floor on this plane (spec section 7, departure 3).
        dot = getattr(t, f"status_{role}_dot", None) or getattr(t, f"status_{role}")
        colour = getattr(t, f"status_{role}")
        fill = "transparent" if self._state == "ok" else getattr(t, f"status_{role}_bg")
        edge = t.status_danger_border if self._state == "down" else "transparent"
        for d in (self.connection_dot, self.connection_icon_dot):
            d.setStyleSheet(f"background-color: {dot}; border-radius: 5px;")
        self.connection_box.setStyleSheet(
            f"#ConnectionBox {{ background-color: {fill}; border: 1px solid {edge};"
            f" border-radius: 8px; }}"
            f"#ConnectionBox QLabel {{ background: transparent; }}"
        )
        self.connection_icon.setStyleSheet(
            f"#ConnectionIcon {{ background-color: {fill}; border: none;"
            f" border-radius: 8px; }}"
        )
        self.connection_label.setStyleSheet(
            f"color: {colour}; {font_css('caption', bold=True)}"
        )
        self.path_label.setStyleSheet(
            f"color: {t.text_secondary}; font-family: {t.font_family_mono};"
            f" {font_css('caption')}"
        )
        self.retry_button.setStyleSheet(
            f"#RetryButton {{ background-color: {t.surface}; color: {t.text};"
            f" border: 1px solid {t.status_danger_border}; border-radius: 8px;"
            f" padding: 0 12px; {font_css('body', bold=True)} }}"
        )
