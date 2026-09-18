import logging
import os
from functools import partial
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.packer_bridge import banner_payload, item_rows, summary_lines
from gui.theme import current_tokens
from shared.components.confirm_dialog import ConfirmDialog

logger = logging.getLogger(__name__)


class PackerModeWidget(QWidget):
    """
    The user interface for the main "Packer Mode" screen.

    This widget displays the items for the currently active order, provides
    visual feedback on scanning actions, and captures input from a barcode
    scanner. It is designed to be a dedicated, focused view for the packing
    process.

    Attributes:
        barcode_scanned (Signal): Emitted when a barcode is scanned.
        exit_packing_mode (Signal): Emitted when the user clicks the exit button.
        skip_order_requested (Signal): Emitted when the skip order button is clicked.
        cancel_item_requested (Signal[int]): Emitted with row index on -1 button press.
        force_confirm_requested (Signal[int]): Emitted with row index on Force Confirm.
        map_sku_requested (Signal[str]): Emitted with original SKU on Map SKU press.
        extra_confirmed (Signal[str]): Emitted with normalized_sku on Keep extra.
        extra_removed (Signal[str]): Emitted with normalized_sku on Remove extra.
        document_view (QWebEngineView): The order document (bridge: PackerBridge).
        scanner_input (QLineEdit): Hidden line edit that captures barcode scanner input.
    """

    barcode_scanned = Signal(str)
    exit_packing_mode = Signal()
    skip_order_requested = Signal()
    cancel_item_requested = Signal(int)  # row index
    force_confirm_requested = Signal(int)  # row index
    map_sku_requested = Signal(str)  # original SKU string
    extra_confirmed = Signal(str)  # normalized_sku
    extra_removed = Signal(str)  # normalized_sku

    def __init__(self, parent: QWidget = None, sim_mode: bool = False):
        """
        Initializes the PackerModeWidget and its UI components.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
            sim_mode (bool): When True, show a visible scan simulator panel for
                development/testing without a physical barcode scanner. Defaults to False.
        """
        super().__init__(parent)
        self._sim_mode = sim_mode

        main_layout = QHBoxLayout(self)

        # ─── LEFT PANEL ──────────────────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(4)

        self._feedback_text = "Scan an order barcode"
        self._feedback_role = "info"
        self._raw_scan = ""
        self._items = []
        self._rows = []
        self._sku_map = {}
        self._orders_done = 0
        self._orders_total = 0
        self._history = []

        from gui.packer_bridge import mount_packer_page

        self.document_view = QWebEngineView(self)
        self.bridge = mount_packer_page(self.document_view)
        left_layout.addWidget(self.document_view, 1)
        self._push_feedback()
        self.bridge.confirmRequested.connect(self._on_manual_confirm)
        self.bridge.undoRequested.connect(self._on_cancel_item)
        self.bridge.forceRequested.connect(self._on_force_confirm)
        self.bridge.mapRequested.connect(self._on_map_sku_requested)

        # Scanner input — hidden line edit that captures barcode scanner keystrokes.
        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedSize(1, 1)
        self.scanner_input.returnPressed.connect(self._on_scan)
        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        scan_row.addWidget(self.scanner_input, 1)
        left_layout.addLayout(scan_row)

        # [J] Extra items panel (hidden by default) — Task 8 moves this into the document.
        _extras_container = QWidget()
        _ecvl = QVBoxLayout(_extras_container)
        _ecvl.setContentsMargins(0, 0, 0, 0)
        _ecvl.setSpacing(2)
        self._extras_section_title = QLabel(
            ""
        )  # shown as "EXTRA ITEMS DETECTED" when panel is active
        _etsf = self._extras_section_title.font()
        _etsf.setPointSize(9)
        _etsf.setBold(True)
        self._extras_section_title.setFont(_etsf)
        self._extras_section_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        _ecvl.addWidget(self._extras_section_title)

        self.extras_panel = QFrame()
        self.extras_panel.setObjectName("ExtrasPanel")
        self.extras_panel.setStyleSheet(
            f"QFrame#ExtrasPanel {{ border: 2px solid {current_tokens().status_warning}; border-radius: 3px; }}"
        )
        self.extras_panel.setVisible(False)
        _epl = QVBoxLayout(self.extras_panel)
        _epl.setContentsMargins(4, 4, 4, 4)
        _epl.setSpacing(3)
        self.extras_table = QTableWidget()
        self.extras_table.setColumnCount(3)
        self.extras_table.setHorizontalHeaderLabels(["SKU", "×", "Action"])
        self.extras_table.horizontalHeader().setStretchLastSection(True)
        self.extras_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.extras_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.extras_table.setFocusPolicy(Qt.NoFocus)
        _epl.addWidget(self.extras_table)
        _ecvl.addWidget(self.extras_panel)
        left_layout.addWidget(_extras_container)

        # ─── RIGHT PANEL ─────────────────────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Dev mode: visible scan simulator panel (replaces physical barcode scanner).
        # Opt-in only: via the ScanSimulatorMode config setting (self._sim_mode, wired
        # through main.py) or, for a quick one-off without touching config, PACKER_DEV_SIM=1.
        if self._sim_mode or os.environ.get("PACKER_DEV_SIM"):
            sim_group = QGroupBox("Scan Simulator (Dev Mode)")
            sim_group.setStyleSheet(
                f"QGroupBox {{ border: 2px dashed {current_tokens().status_warning}; border-radius: 6px; "
                f"margin-top: 6px; padding: 4px; color: {current_tokens().status_warning}; font-weight: bold; }}"
                "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
            )
            sim_layout = QHBoxLayout(sim_group)
            self.sim_input = QLineEdit()
            self.sim_input.setPlaceholderText(
                "Type order number or SKU, press Enter to scan..."
            )
            self.sim_input.returnPressed.connect(self._on_sim_scan)
            sim_btn = QPushButton("Scan")
            sim_btn.setFixedWidth(70)
            sim_btn.clicked.connect(self._on_sim_scan)
            sim_layout.addWidget(self.sim_input)
            sim_layout.addWidget(sim_btn)
            right_layout.addWidget(sim_group)

        # [E] Skip Order button — placed directly under the scan-info card
        self.skip_order_button = QPushButton("Skip Order →")
        self.skip_order_button.setFocusPolicy(Qt.NoFocus)
        self.skip_order_button.setEnabled(False)
        self.skip_order_button.clicked.connect(self.skip_order_requested.emit)
        right_layout.addWidget(self.skip_order_button)

        right_layout.addStretch()

        self.exit_button = QPushButton("<< Back to Menu")
        font = self.exit_button.font()
        font.setPointSize(14)
        self.exit_button.setFont(font)
        self.exit_button.clicked.connect(self.exit_packing_mode.emit)
        right_layout.addWidget(self.exit_button)

        main_layout.addWidget(left_widget, stretch=3)
        main_layout.addWidget(right_widget, stretch=1)

    def showEvent(self, event):
        """Re-assert the scanner's claim on the keyboard every time we appear."""
        super().showEvent(event)
        from gui.packer_bridge import deny_focus

        deny_focus(self.document_view)
        self.set_focus_to_scanner()

    # ─── Scanner input handlers ───────────────────────────────────────────────

    def _on_scan(self):
        """
        Private slot to handle the returnPressed signal from the scanner input.
        It emits the public barcode_scanned signal with the input text.
        """
        text = self.scanner_input.text()
        self.scanner_input.clear()
        self.barcode_scanned.emit(text)

    def _on_sim_scan(self):
        """
        Private slot for the scan simulator panel (dev mode only).

        Reads text from the visible simulator input field and emits
        the same ``barcode_scanned`` signal as a physical scanner would,
        so all normal packing logic handles it unchanged.
        """
        text = self.sim_input.text().strip()
        if text:
            self.sim_input.clear()
            self.barcode_scanned.emit(text)

    # ─── Action button slots ──────────────────────────────────────────────────

    def _on_manual_confirm(self, row: int):
        """Confirm one item by hand -- the same as scanning its SKU."""
        if 0 <= row < len(self._rows):
            self.barcode_scanned.emit(self._rows[row]["sku"])
        self.set_focus_to_scanner()

    def _on_cancel_item(self, row: int):
        """Undo the last scan for one item.

        No confirmation: undoing a scan is undone by scanning again, and a
        confirm is for acts Undo cannot reach (shared.components.ConfirmDialog).
        """
        self.cancel_item_requested.emit(row)
        self.set_focus_to_scanner()

    def _on_force_confirm(self, row: int):
        """Force-confirm every remaining unit of one item. Not undoable."""
        if not 0 <= row < len(self._rows):
            return
        item = self._rows[row]
        remaining = item["required"] - item["packed"]
        dialog = ConfirmDialog(
            self,
            title="Force confirm this item?",
            body=(
                f"{item['product']} ({item['sku']}): {remaining} of "
                f"{item['required']} still unscanned. Forcing marks them packed "
                "without a scan, and cannot be undone."
            ),
            verb="Force confirm",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.force_confirm_requested.emit(row)
        self.set_focus_to_scanner()

    def _on_map_sku_requested(self, sku: str):
        """Emit map_sku_requested with the original SKU string."""
        self.map_sku_requested.emit(sku)
        self.set_focus_to_scanner()

    def _on_extra_confirmed(self, norm_sku: str):
        """Emit extra_confirmed for the given normalized SKU."""
        self.extra_confirmed.emit(norm_sku)
        self.set_focus_to_scanner()

    def _on_extra_removed(self, norm_sku: str):
        """Emit extra_removed for the given normalized SKU."""
        self.extra_removed.emit(norm_sku)
        self.set_focus_to_scanner()

    # ─── Public display methods ───────────────────────────────────────────────

    def display_order(
        self,
        items: list[dict[str, Any]],
        order_state: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        sku_map: dict[str, str] | None = None,
    ):
        """Show one order in the document.

        Args:
            items: The order's product dicts, as PackerLogic returns them.
            order_state: PackerLogic.current_order_state for this order.
            metadata: Order-level metadata for the banner.
            sku_map: Normalised barcode -> SKU, for the Map SKU action.
        """
        self._items = list(items)
        self._sku_map = dict(sku_map or {})
        self._rows = item_rows(self._items, order_state, self._sku_map)
        order_number = (
            items[0].get("Order_Number", items[0].get("order_number", ""))
            if items
            else ""
        )
        self.bridge.set_banner(banner_payload(order_number, metadata))
        self._push_rows()
        self.skip_order_button.setEnabled(True)
        self.set_focus_to_scanner()

    def update_item_row(self, row: int, packed_count: int, is_complete: bool):
        """Update one item's packed count after a scan or a manual action.

        Args:
            row: The item's index, as PackerLogic reports it.
            packed_count: The item's new packed count.
            is_complete: Whether this item is now fully packed. Kept in the
                signature because every existing call site passes it; the row's
                state is derived from packed against required, so the two can
                never disagree.
        """
        if not 0 <= row < len(self._rows):
            logger.warning("Cannot update row %s: no such item in this order", row)
            return
        target = self._rows[row]
        target["packed"] = packed_count
        for candidate in self._rows:
            candidate["just_changed"] = candidate is target
        self._rows = item_rows(
            self._items,
            [{"row": r["row"], "packed": r["packed"]} for r in self._rows],
            self._sku_map,
        )
        self._rows[row]["just_changed"] = True
        self._push_rows()

    def _push_rows(self):
        """Send the item rows and the numbers derived from them."""
        self.bridge.set_items(self._rows)
        self._push_progress()

    def _push_progress(self):
        """The side column's numbers: orders from the session, items from the rows."""
        self.bridge.set_progress(
            {
                "orders_done": self._orders_done,
                "orders_total": self._orders_total,
                **summary_lines(self._rows),
            }
        )

    def show_notification(self, text: str, role: str):
        """Show the scan outcome in the document's feedback band.

        Args:
            text: The message. Empty clears the band.
            role: A shared.theme status role -- "status_success",
                "status_warning", "status_danger", "status_info" -- or
                "transparent" to clear. Both spellings are accepted because
                main_window has called it both ways since before the band
                existed.
        """
        self._feedback_text = text
        self._feedback_role = (
            "" if role == "transparent" or not text else role.removeprefix("status_")
        )
        self._push_feedback()

    def clear_screen(self):
        """
        Resets the widget to its initial state, ready for the next order.
        """
        self.table.clearContents()
        self.table.setRowCount(0)
        self.status_label.setText("Scan the next order's barcode")
        self.notification_label.setText("")
        self.scanner_input.clear()
        self.scanner_input.setEnabled(True)
        # [A] Hide metadata banner
        self.metadata_banner.setVisible(False)
        # [D] Clear summary panel (summary_frame is now a permanent tab page, not
        # a widget that's shown/hidden — the tab always exists, only its data changes)
        self.summary_table.setRowCount(0)
        self.items_stat_label.setText("Items: 0 / 0")
        # [E] Disable skip button
        self.skip_order_button.setEnabled(False)
        # [J] Hide extras panel and reset title
        self.extras_panel.setVisible(False)
        self.extras_table.setRowCount(0)
        self._extras_section_title.setText("")
        self._extras_section_title.setStyleSheet("")
        self.set_focus_to_scanner()

    def set_focus_to_scanner(self):
        """
        Sets the keyboard focus to the hidden scanner input field.
        This is crucial for ensuring the barcode scanner's output is captured.
        """
        self.scanner_input.setFocus()

    def update_raw_scan_display(self, text: str):
        """Show the raw text of the last scan beside the outcome."""
        self._raw_scan = text
        self._push_feedback()

    def _push_feedback(self):
        self.bridge.set_feedback(
            self._feedback_text, self._feedback_role, self._raw_scan
        )

    def add_order_to_history(self, order_number: str, status: str = ""):
        """Add an order to the top of the session's history.

        Args:
            order_number: The order that was just scanned.
            status: "[SKIPPED]" for a skipped order; empty for a completed one.
        """
        self._history.insert(
            0,
            {
                "order": str(order_number),
                "status": "skipped" if status == "[SKIPPED]" else "complete",
            },
        )
        self.bridge.set_history(self._history)

    # [B] Feature B ────────────────────────────────────────────────────────────

    def update_session_progress(self, completed: int, total: int):
        """Update the session's order counts in the side column.

        Args:
            completed: Orders finished in this session.
            total: Orders in the session.
        """
        self._orders_done = completed
        self._orders_total = total
        self._push_progress()

    # [J] Feature J ────────────────────────────────────────────────────────────

    def show_extras_panel(self, extras: dict[str, int]):
        """
        Populates and shows the extras panel with Keep/Remove buttons.

        Args:
            extras: Dict of {normalized_sku: extra_count}.
        """
        self.extras_table.setRowCount(len(extras))
        for i, (norm_sku, count) in enumerate(extras.items()):
            self.extras_table.setItem(i, 0, QTableWidgetItem(norm_sku))
            self.extras_table.setItem(i, 1, QTableWidgetItem(str(count)))

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 1, 2, 1)
            btn_layout.setSpacing(3)

            keep_btn = QPushButton("Keep")
            keep_btn.setFixedWidth(70)
            keep_btn.setFocusPolicy(Qt.NoFocus)
            keep_btn.clicked.connect(partial(self._on_extra_confirmed, norm_sku))

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(80)
            remove_btn.setFocusPolicy(Qt.NoFocus)
            remove_btn.clicked.connect(partial(self._on_extra_removed, norm_sku))

            btn_layout.addWidget(keep_btn)
            btn_layout.addWidget(remove_btn)
            self.extras_table.setCellWidget(i, 2, btn_widget)

        is_visible = len(extras) > 0
        self.extras_panel.setVisible(is_visible)
        if is_visible:
            self._extras_section_title.setText("EXTRA ITEMS DETECTED")
            self._extras_section_title.setStyleSheet(
                f"color: {current_tokens().status_warning};"
            )
        else:
            self._extras_section_title.setText("")
            self._extras_section_title.setStyleSheet("")
