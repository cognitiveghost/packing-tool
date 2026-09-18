import logging
import os
from collections import defaultdict
from functools import partial
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.packer_bridge import banner_payload, item_rows
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
        session_progress_bar (QProgressBar): Shows completed/total orders for the session.
        document_view (QWebEngineView): The order document (bridge: PackerBridge).
        scanner_input (QLineEdit): Hidden line edit that captures barcode scanner input.
        history_table (QTableWidget): History of scanned orders in this session.
        packed_stat_label (QLabel): Glance-only tile — completed/total orders for the session.
        items_stat_label (QLabel): Glance-only tile — packed/total items for the current order.
    """

    barcode_scanned = Signal(str)
    exit_packing_mode = Signal()
    skip_order_requested = Signal()
    cancel_item_requested = Signal(int)  # row index
    force_confirm_requested = Signal(int)  # row index
    map_sku_requested = Signal(str)  # original SKU string
    extra_confirmed = Signal(str)  # normalized_sku
    extra_removed = Signal(str)  # normalized_sku

    # Shared max-height for the bottom info row (history/extras) and the matching
    # right-panel bottom section — keeps both panels' bottoms visually aligned.
    _BOTTOM_ROW_HEIGHT = 160

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

        from gui.packer_bridge import mount_packer_page

        self.document_view = QWebEngineView(self)
        self.bridge = mount_packer_page(self.document_view)
        left_layout.addWidget(self.document_view, 1)
        self._push_feedback()
        self.bridge.confirmRequested.connect(self._on_manual_confirm)
        self.bridge.undoRequested.connect(self._on_cancel_item)
        self.bridge.forceRequested.connect(self._on_force_confirm)
        self.bridge.mapRequested.connect(self._on_map_sku_requested)

        # [B] Session progress bar
        self.session_progress_bar = QProgressBar()
        self.session_progress_bar.setFixedHeight(18)
        self.session_progress_bar.setTextVisible(True)
        self.session_progress_bar.setFormat("0 / 0 orders")
        self.session_progress_bar.setValue(0)
        self.session_progress_bar.setMaximum(1)
        left_layout.addWidget(self.session_progress_bar)

        # Scanner input — hidden line edit that captures barcode scanner keystrokes.
        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedSize(1, 1)
        self.scanner_input.returnPressed.connect(self._on_scan)
        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        scan_row.addWidget(self.scanner_input, 1)
        left_layout.addLayout(scan_row)

        # Bottom row: history table (left half) + extras panel (right half, hidden until needed)
        _bottom_row = QWidget()
        _bottom_row.setMaximumHeight(self._BOTTOM_ROW_HEIGHT)
        _brl = QHBoxLayout(_bottom_row)
        _brl.setContentsMargins(0, 0, 0, 0)
        _brl.setSpacing(4)

        _hist_container = QWidget()
        _hist_vl = QVBoxLayout(_hist_container)
        _hist_vl.setContentsMargins(0, 0, 0, 0)
        _hist_vl.setSpacing(2)
        _hist_title = QLabel("Scanned Orders History:")
        _hist_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        _hf = _hist_title.font()
        _hf.setPointSize(9)
        _hist_title.setFont(_hf)
        _hist_vl.addWidget(_hist_title)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(1)
        self.history_table.setHorizontalHeaderLabels(["Order #"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.history_table.setFocusPolicy(Qt.NoFocus)
        _hist_vl.addWidget(self.history_table)
        _brl.addWidget(_hist_container, stretch=1)

        # [J] Extra items panel — right half of the bottom row (hidden by default)
        # Title label is always present (same 9pt height as history title) so that
        # extras_table top edge aligns with history_table top edge.
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
        _brl.addWidget(_extras_container, stretch=1)

        # [D] Summary panel — deduped SKUs with summed quantities
        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("SummaryFrame")
        self.summary_frame.setStyleSheet(
            "QFrame#SummaryFrame { border: 1px solid palette(mid); border-radius: 3px; }"
        )
        _sfl = QVBoxLayout(self.summary_frame)
        _sfl.setContentsMargins(4, 2, 4, 2)
        _sfl.setSpacing(2)
        _sh = QLabel("Summary (unique SKUs):")
        _shf = _sh.font()
        _shf.setPointSize(9)
        _sh.setFont(_shf)
        _sfl.addWidget(_sh)
        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(4)
        self.summary_table.setHorizontalHeaderLabels(
            ["SKU", "Product", "Packed/Total", "Status"]
        )
        _shdr = self.summary_table.horizontalHeader()
        _shdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        _shdr.setSectionResizeMode(1, QHeaderView.Stretch)
        _shdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        _shdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        _shdr.setStretchLastSection(False)
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.summary_table.setFocusPolicy(Qt.NoFocus)
        _sfl.addWidget(self.summary_table)

        left_layout.addWidget(self.summary_frame, 1)
        left_layout.addWidget(_bottom_row)  # history/extras stay under the tabs

        # ─── RIGHT PANEL ─────────────────────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Glance-only stat tiles: session order progress + current-order item progress.
        # Kept in sync via update_session_progress / _update_summary_panel /
        # _refresh_summary_from_table (same call sites that already update
        # session_progress_bar / summary_table).
        stats_row = QHBoxLayout()
        self.packed_stat_label = QLabel("Packed: 0 / 0")
        self.items_stat_label = QLabel("Items: 0 / 0")
        for lbl in (self.packed_stat_label, self.items_stat_label):
            lbl.setStyleSheet("font-weight: bold;")
            stats_row.addWidget(lbl)
        right_layout.addLayout(stats_row)

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

        # Bottom section — fixed height matching _bottom_row.maximumHeight() (160px) on
        # the left, so the exit button's bottom edge lines up with the history/extras row.
        _right_bottom = QWidget()
        _right_bottom.setMaximumHeight(self._BOTTOM_ROW_HEIGHT)
        _rbottom_layout = QVBoxLayout(_right_bottom)
        _rbottom_layout.setContentsMargins(0, 0, 0, 0)
        _rbottom_layout.setSpacing(0)
        _rbottom_layout.addStretch()

        self.exit_button = QPushButton("<< Back to Menu")
        font = self.exit_button.font()
        font.setPointSize(14)
        self.exit_button.setFont(font)
        self.exit_button.clicked.connect(self.exit_packing_mode.emit)
        _rbottom_layout.addWidget(self.exit_button)

        right_layout.addWidget(_right_bottom)

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
        """The side column's numbers. Task 7 fills this in."""

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
        """
        Adds an order number to the top of the scan history table.

        Args:
            order_number: The order number that was just scanned.
            status: Optional status suffix, e.g. "[SKIPPED]".
        """
        self.history_table.insertRow(0)
        display_text = f"{order_number} {status}".strip()
        item = QTableWidgetItem(display_text)
        if status == "[SKIPPED]":
            item.setForeground(QColor(current_tokens().status_warning))
        self.history_table.setItem(0, 0, item)

    # [B] Feature B ────────────────────────────────────────────────────────────

    def update_session_progress(self, completed: int, total: int):
        """
        Updates the session progress bar at the top of the left panel.

        Args:
            completed: Number of completed orders.
            total: Total orders in the session.
        """
        self.session_progress_bar.setMaximum(max(total, 1))
        self.session_progress_bar.setValue(completed)
        self.session_progress_bar.setFormat(f"{completed} / {total} orders")
        self.packed_stat_label.setText(f"Packed: {completed} / {total}")

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

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _update_summary_panel(
        self,
        items: list[dict[str, Any]],
        order_state: list[dict[str, Any]],
    ):
        """
        Deduplicates items by SKU and updates the summary table with summed quantities.
        This handles duplicate SKU rows that can appear in Shopify exports.
        Columns: SKU | Product | Packed/Total | Status
        """
        sku_totals: dict[str, int] = defaultdict(int)
        sku_packed: dict[str, int] = defaultdict(int)
        sku_name: dict[str, str] = {}

        for item in items:
            sku = item.get("SKU", item.get("sku", ""))
            try:
                qty = int(float(item.get("Quantity", item.get("quantity", 1))))
            except (ValueError, TypeError):
                qty = 1
            sku_totals[sku] += qty
            if sku not in sku_name:
                sku_name[sku] = item.get("Product_Name", item.get("product_name", ""))

        for state in order_state:
            orig = state.get("original_sku", "")
            sku_packed[orig] += state.get("packed", 0)

        unique_skus = sorted(sku_totals.keys())
        self.summary_table.setRowCount(len(unique_skus))

        for i, sku in enumerate(unique_skus):
            total = sku_totals[sku]
            packed = sku_packed.get(sku, 0)
            self.summary_table.setItem(i, 0, QTableWidgetItem(sku))
            self.summary_table.setItem(i, 1, QTableWidgetItem(sku_name.get(sku, "")))
            self.summary_table.setItem(i, 2, QTableWidgetItem(f"{packed} / {total}"))
            status_text = "Done" if packed >= total else "Pending"
            status_item = QTableWidgetItem(status_text)
            if packed >= total:
                status_item.setForeground(QColor(current_tokens().status_success))
            self.summary_table.setItem(i, 3, status_item)

        total_packed = sum(sku_packed.get(sku, 0) for sku in unique_skus)
        total_qty = sum(sku_totals.values())
        self.items_stat_label.setText(f"Items: {total_packed} / {total_qty}")

    def _refresh_summary_from_table(self):
        """
        Rebuild the summary table by reading current row data directly from the
        items table. Called from update_item_row() so the summary stays live.
        Main table columns: 0=Product Name, 1=SKU, 2="packed / total", 3=Status, 4=Actions.
        Summary columns: 0=SKU, 1=Product, 2=Packed/Total, 3=Status.
        """
        # summary_frame now lives inside main_tabs, so isVisible() would reflect
        # whether "Session Summary" happens to be the active tab rather than
        # whether an order is loaded. Use summary_table's row count instead —
        # it's populated by _update_summary_panel whenever an order is displayed.
        if self.summary_table.rowCount() == 0:
            return

        sku_packed: dict[str, int] = defaultdict(int)
        sku_totals: dict[str, int] = defaultdict(int)
        sku_name: dict[str, str] = {}

        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 0)
            sku_item = self.table.item(r, 1)
            qty_item = self.table.item(r, 2)
            if sku_item is None or qty_item is None:
                continue
            sku = sku_item.text()
            if sku not in sku_name:
                sku_name[sku] = name_item.text() if name_item else ""
            parts = qty_item.text().split(" / ")
            try:
                packed = int(parts[0])
                total = int(parts[1]) if len(parts) > 1 else 1
            except (ValueError, IndexError):
                packed, total = 0, 1
            sku_packed[sku] += packed
            sku_totals[sku] += total

        unique_skus = sorted(sku_totals.keys())
        self.summary_table.setRowCount(len(unique_skus))
        for i, sku in enumerate(unique_skus):
            total = sku_totals[sku]
            packed = sku_packed.get(sku, 0)
            self.summary_table.setItem(i, 0, QTableWidgetItem(sku))
            self.summary_table.setItem(i, 1, QTableWidgetItem(sku_name.get(sku, "")))
            self.summary_table.setItem(i, 2, QTableWidgetItem(f"{packed} / {total}"))
            status_text = "Done" if packed >= total else "Pending"
            status_item = QTableWidgetItem(status_text)
            if packed >= total:
                status_item.setForeground(QColor(current_tokens().status_success))
            self.summary_table.setItem(i, 3, status_item)

        total_packed = sum(sku_packed.get(sku, 0) for sku in unique_skus)
        total_qty = sum(sku_totals.values())
        self.items_stat_label.setText(f"Items: {total_packed} / {total_qty}")
