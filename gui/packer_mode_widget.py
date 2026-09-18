import logging
import os
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
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
        self.bridge.keepExtraRequested.connect(self._on_extra_confirmed)
        self.bridge.removeExtraRequested.connect(self._on_extra_removed)

        # Scanner input — hidden line edit that captures barcode scanner keystrokes.
        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedSize(1, 1)
        self.scanner_input.returnPressed.connect(self._on_scan)
        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        scan_row.addWidget(self.scanner_input, 1)
        left_layout.addLayout(scan_row)

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
        """Reset the document to waiting for the next order.

        The session's history and order counts stay: they belong to the
        session, not to the order that just ended.
        """
        self._items = []
        self._rows = []
        self._sku_map = {}
        self.bridge.set_banner(banner_payload("", None))
        self.bridge.set_extras([])
        self.scanner_input.clear()
        self.scanner_input.setEnabled(True)
        self.skip_order_button.setEnabled(False)
        self._raw_scan = ""
        self.show_notification("Scan the next order's barcode", "status_info")
        self._push_rows()
        self.set_focus_to_scanner()
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
        """Show the items scanned into this order that it does not contain.

        Args:
            extras: PackerLogic.current_extra_items -- normalised SKU to count.
        """
        self.bridge.set_extras(
            [{"sku": sku, "count": count} for sku, count in (extras or {}).items()]
        )
