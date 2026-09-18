import logging
import os
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.command_bar import BAR_HEIGHT, bar_css
from gui.packer_bridge import banner_payload, flash_role, item_rows, summary_lines
from shared.components.confirm_dialog import ConfirmDialog
from shared.theme import font_css, on_theme_changed

logger = logging.getLogger(__name__)

SCANNER_WIDTH = 280
SIM_INPUT_WIDTH = 160


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
        end_session_requested (Signal): Emitted when the session-complete panel's
            End session button is pressed.
        map_barcode_requested (Signal[str]): Emitted with the raw barcode of an
            unmatched scan the packer chose to map.
        document_view (QWebEngineView): The order document (bridge: PackerBridge).
        packer_bar (QWidget): The 60px command bar above the document.
        scanner_input (QLineEdit): Visible line edit that captures barcode scanner input.
    """

    barcode_scanned = Signal(str)
    exit_packing_mode = Signal()
    skip_order_requested = Signal()
    cancel_item_requested = Signal(int)  # row index
    force_confirm_requested = Signal(int)  # row index
    map_sku_requested = Signal(str)  # original SKU string
    extra_confirmed = Signal(str)  # normalized_sku
    extra_removed = Signal(str)  # normalized_sku
    end_session_requested = Signal()  # P8's primary action
    map_barcode_requested = Signal(str)  # raw barcode from an unmatched scan

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
        self._push_feedback()
        self.bridge.confirmRequested.connect(self._on_manual_confirm)
        self.bridge.undoRequested.connect(self._on_cancel_item)
        self.bridge.forceRequested.connect(self._on_force_confirm)
        self.bridge.mapRequested.connect(self._on_map_sku_requested)
        self.bridge.keepExtraRequested.connect(self._on_extra_confirmed)
        self.bridge.removeExtraRequested.connect(self._on_extra_removed)
        self.bridge.mapBarcodeRequested.connect(self._on_map_barcode)
        self.bridge.endSessionRequested.connect(self.end_session_requested.emit)
        self.bridge.exitPackingRequested.connect(self.exit_packing_mode.emit)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── COMMAND BAR (artboard A1: the rail is hidden while packing, and
        # this bar carries the order, the scanner, Skip and Exit) ────────────
        self.packer_bar = QWidget()
        self.packer_bar.setObjectName("PackerBar")
        # A plain QWidget subclass ignores a background rule without this.
        self.packer_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.packer_bar.setFixedHeight(BAR_HEIGHT)
        bar = QHBoxLayout(self.packer_bar)
        bar.setContentsMargins(12, 0, 12, 0)
        bar.setSpacing(8)

        self._order_label = QLabel("No order")
        self._order_label.setObjectName("cmdbarSession")
        bar.addWidget(self._order_label)

        # The scanner field, A2: the shipped 1x1 hidden QLineEdit, grown to a
        # field the packer can see. The global QSS already lands a QLineEdit on
        # control_height, so it needs a width and nothing else -- and because
        # it is still the widget the scanner types into, the visible focus ring
        # and the disabled state are the real thing rather than a copy of it.
        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedWidth(SCANNER_WIDTH)
        self.scanner_input.setPlaceholderText("Ready to scan")
        self.scanner_input.returnPressed.connect(self._on_scan)
        bar.addWidget(self.scanner_input)

        if self._sim_mode or os.environ.get("PACKER_DEV_SIM"):
            bar.addWidget(self._build_sim_group())

        bar.addStretch(1)

        self.skip_order_button = QPushButton("Skip order")
        self.skip_order_button.setFocusPolicy(Qt.NoFocus)
        self.skip_order_button.setEnabled(False)
        self.skip_order_button.clicked.connect(self.skip_order_requested.emit)
        bar.addWidget(self.skip_order_button)

        self.exit_button = QPushButton("Exit packing")
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.exit_button.clicked.connect(self.exit_packing_mode.emit)
        bar.addWidget(self.exit_button)

        root.addWidget(self.packer_bar)
        root.addWidget(self.document_view, 1)

        on_theme_changed(self, self._apply_bar_theme)

    def _build_sim_group(self) -> QGroupBox:
        """The dev scan simulator, inline in the bar (artboard P3-1920).

        Opt-in only: the ScanSimulatorMode config setting (wired through
        main.py) or PACKER_DEV_SIM=1 for a one-off.
        """
        group = QGroupBox("DEV")
        group.setObjectName("SimGroup")
        group.setFixedHeight(BAR_HEIGHT - 16)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)
        self.sim_input = QLineEdit()
        self.sim_input.setFixedWidth(SIM_INPUT_WIDTH)
        self.sim_input.setPlaceholderText("Order number or SKU")
        self.sim_input.returnPressed.connect(self._on_sim_scan)
        button = QPushButton("Simulate scan")
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(self._on_sim_scan)
        layout.addWidget(self.sim_input)
        layout.addWidget(button)
        return group

    def _apply_bar_theme(self, tokens) -> None:
        self.setStyleSheet(
            bar_css(tokens, "QWidget#PackerBar")
            + f" QGroupBox#SimGroup {{ border: 1px dashed {tokens.status_warning};"
            f" border-radius: {tokens.radius}px; color: {tokens.status_warning};"
            f" {font_css('caption', bold=True)} }}"
            " QGroupBox#SimGroup::title { subcontrol-origin: margin; left: 8px; }"
        )

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

    def _on_map_barcode(self, barcode: str):
        """Forward an unmatched scan's barcode; MainWindow owns the dialog."""
        self.map_barcode_requested.emit(barcode)
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
        self._order_label.setText(f"#{order_number}" if order_number else "No order")
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
        self._rows = item_rows(
            self._items,
            [{"row": r["row"], "packed": r["packed"]} for r in self._rows],
            self._sku_map,
        )
        self._rows[row]["just_changed"] = True
        self._push_rows()

    def row_at(self, row: int) -> dict[str, Any]:
        """One item row's payload, for a caller writing a message about it."""
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}

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
        self.bridge.set_session_end({})
        self._order_label.setText("No order")
        self.scanner_input.clear()
        self.scanner_input.setEnabled(True)
        self.skip_order_button.setEnabled(False)
        self._raw_scan = ""
        self.show_notification("Scan an order barcode", "status_info")
        self._push_rows()
        self.set_focus_to_scanner()

    def show_session_complete(self, payload: dict[str, str]):
        """Show the session's terminal state in place of the order document.

        Args:
            payload: gui.packer_bridge.session_end_payload()'s title and body.
        """
        self.bridge.set_session_end(payload)
        self._order_label.setText("Session complete")
        self.scanner_input.setEnabled(False)
        self.skip_order_button.setEnabled(False)

    def flash_scan(self, color: str):
        """Flash the document's edge with a scan's outcome.

        Args:
            color: "green", "red" or "orange", as main_window has named the
                cue since it was a border on the table frame. Anything else
                raises rather than emitting a role no CSS rule matches.
        """
        self.bridge.flash(flash_role(color))

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
