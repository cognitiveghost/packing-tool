"""
Client Selector Widget — left-panel client picker for Session Browser.

Shows a list of all known clients and emits client_selected(str) when
the user picks one.  The selection is persisted in QSettings so the
last-used client is auto-restored on the next open.
"""

import logging

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class ClientSelectorWidget(QWidget):
    """
    Vertical list of client IDs with a Refresh button.

    Signals:
        client_selected(str): Emitted when the user clicks a client row,
                              carrying the raw client_id string (e.g. "M").
    """

    client_selected = Signal(str)

    def __init__(self, profile_manager, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self._settings = QSettings("PackingTool", "SessionBrowser")
        self._init_ui()

    # ------------------------------------------------------------------ #
    #  UI setup                                                            #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header = QLabel("Clients")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(100)
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget)

        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setToolTip("Reload client list from file server")
        self.refresh_btn.clicked.connect(self.load_clients)
        layout.addWidget(self.refresh_btn)

        self.setFixedWidth(175)

    # ------------------------------------------------------------------ #
    #  Data                                                                #
    # ------------------------------------------------------------------ #

    def load_clients(self):
        """Fetch client list from ProfileManager and populate the list."""
        try:
            clients = self.profile_manager.list_clients()
        except Exception:
            logger.exception("Failed to list clients")
            clients = []

        saved = self._settings.value("last_client_id", "", type=str)

        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for cid in sorted(clients):
            item = QListWidgetItem(f"  {cid}")
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)

        # Restore last selection or pick the first client
        if clients:
            target = saved if saved in clients else clients[0]
            self._select_client_id(target)

    def _select_client_id(self, client_id: str):
        """Programmatically select a client row without double-emitting."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == client_id:
                self.list_widget.blockSignals(True)
                self.list_widget.setCurrentItem(item)
                self.list_widget.blockSignals(False)
                self.client_selected.emit(client_id)
                return

    def selected_client_id(self) -> str | None:
        """Return the currently selected client_id or None."""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    # ------------------------------------------------------------------ #
    #  Slots                                                               #
    # ------------------------------------------------------------------ #

    def _on_item_changed(self, current, _previous):
        if current is None:
            return
        cid = current.data(Qt.ItemDataRole.UserRole)
        if cid:
            self._settings.setValue("last_client_id", cid)
            self.client_selected.emit(cid)
