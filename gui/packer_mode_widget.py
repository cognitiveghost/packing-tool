import logging
import os
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.command_bar import BAR_HEIGHT, CONTROL_HEIGHT, bar_css
from gui.packer_bridge import (
    banner_payload,
    flash_role,
    force_question,
    item_rows,
    order_label,
    sku_rollup,
    summary_lines,
    unknown_rows,
)
from gui.theme import current_tokens
from shared.theme import font_css, on_theme_changed

logger = logging.getLogger(__name__)

SCANNER_WIDTH = 280
SIM_INPUT_WIDTH = 160
# Mockup frame 6b. The type scale has no rung between 17 and 28pt.
ORDER_NUMBER_PT = 24


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
    manual_confirm_requested = Signal(str)  # a row's SKU, confirmed by hand (not a scan)

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
        self._unknown = []
        self._sku_map = {}
        self._orders_done = 0
        self._orders_total = 0
        self._history = []
        self._unsaved = False
        # Why the scanner is off, when it is: see _sync_scanner().
        self._order_open = False
        self._session_over = False
        self._taken_over = False
        self._paused = False
        self._question: dict = {}
        # The reset that follows a finished order. Here, not in MainWindow:
        # showing an order and clearing the screen are what it races with.
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self.clear_screen)

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
        self.bridge.questionAnswered.connect(self._on_question_answered)

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
        self._order_label.setObjectName("packerOrder")
        self._order_label.setMinimumWidth(120)
        bar.addWidget(self._order_label)

        # The scanner field: the one widget on this screen that takes keys.
        # Fixed height, because the 2px edge below would add to the global
        # sheet's min-height.
        self.scanner_input = QLineEdit()
        self.scanner_input.setObjectName("packerScanner")
        self.scanner_input.setFixedSize(SCANNER_WIDTH, CONTROL_HEIGHT)
        self.scanner_input.setPlaceholderText("Order number or SKU")
        self.scanner_input.returnPressed.connect(self._on_scan)
        bar.addWidget(self.scanner_input)

        self._scanner_dot = QLabel()
        self._scanner_dot.setObjectName("packerScannerDot")
        self._scanner_dot.setFixedSize(12, 12)
        bar.addWidget(self._scanner_dot)
        self._scanner_state = QLabel("Ready to scan")
        self._scanner_state.setObjectName("packerScannerState")
        bar.addWidget(self._scanner_state)

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

        on_theme_changed(self, self._restyle)
        self._sync_scanner()

    def _build_sim_group(self) -> QWidget:
        """The dev scan simulator, inline in the bar (artboard P3-1920).

        A plain QWidget, not a QGroupBox: the artboard's `.sim-group` is one
        44px row with the "DEV" label beside the input, not a fieldset with a
        title above it -- a QGroupBox title reserves space above its layout
        that a 44px-tall box inside a 60px bar does not have, which squeezed
        the input and button down to an unreadable few px.

        Opt-in only: the ScanSimulatorMode config setting (wired through
        main.py) or PACKER_DEV_SIM=1 for a one-off.
        """
        group = QWidget()
        group.setObjectName("SimGroup")
        group.setAttribute(Qt.WA_StyledBackground, True)
        group.setFixedHeight(BAR_HEIGHT - 16)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)
        label = QLabel("DEV")
        label.setObjectName("SimGroupLabel")
        self.sim_input = QLineEdit()
        self.sim_input.setFixedWidth(SIM_INPUT_WIDTH)
        self.sim_input.setPlaceholderText("Order number or SKU")
        self.sim_input.returnPressed.connect(self._on_sim_scan)
        button = QPushButton("Simulate scan")
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(self._on_sim_scan)
        layout.addWidget(label)
        layout.addWidget(self.sim_input)
        layout.addWidget(button)
        return group

    def _restyle(self, _tokens=None) -> None:
        """The bar's sheet, for the current theme and the scanner's state.

        gui.theme's tokens, not the argument on_theme_changed passes: only
        those carry the bundled font family.
        """
        tokens = current_tokens()
        off = not self.scanner_input.isEnabled()
        if self._order_open and not self._session_over:
            order = (
                f"font-size: {ORDER_NUMBER_PT}pt; font-weight: bold;"
                f" font-family: {tokens.font_family_mono}; color: {tokens.text};"
            )
        else:
            order = f"{font_css('display', bold=True)} color: {tokens.text_secondary};"
        dot = tokens.text_disabled if off else tokens.status_success_dot
        state = tokens.text_secondary if off else tokens.status_success
        self.setStyleSheet(
            bar_css(tokens, "QWidget#PackerBar")
            + f" QLabel#packerOrder {{ {order} background: transparent; }}"
            f" QLineEdit#packerScanner {{ {font_css('heading', bold=False)}"
            f" font-family: {tokens.font_family_mono}; }}"
            f" QLineEdit#packerScanner:enabled {{ border: 2px solid {tokens.selection_border}; }}"
            f" QLabel#packerScannerDot {{ background: {dot}; border-radius: 6px; }}"
            f" QLabel#packerScannerState {{ {font_css('body', bold=True)} color: {state};"
            " background: transparent; }"
            f" QWidget#SimGroup {{ border: 1px dashed {tokens.status_warning};"
            f" border-radius: {tokens.radius}px; }}"
            f" QLabel#SimGroupLabel {{ color: {tokens.status_warning};"
            f" {font_css('caption', bold=True)} }}"
        )

    def _sync_scanner(self) -> None:
        """The one place that decides whether the scanner is on.

        Off when the session is over, another PC took the list, a question is
        open, or the widget is paused (a finished order held on screen, or the
        window about to leave Packer Mode). Skip order follows it, and needs
        an order.
        """
        off = (
            self._session_over or self._taken_over or bool(self._question) or self._paused
        )
        self.scanner_input.setEnabled(not off)
        self._scanner_state.setText("Scanner disabled" if off else "Ready to scan")
        self.skip_order_button.setEnabled(self._order_open and not off)
        self._restyle()
        if not off:
            self.set_focus_to_scanner()

    @property
    def taken_over(self) -> bool:
        """Another PC holds this list's lock (see show_takeover)."""
        return self._taken_over

    def pause_scanner(self) -> None:
        self._paused = True
        self._sync_scanner()

    def resume_scanner(self) -> None:
        self._paused = False
        self._sync_scanner()

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
        if text and self.scanner_input.isEnabled():
            self.sim_input.clear()
            self.barcode_scanned.emit(text)

    # ─── Action button slots ──────────────────────────────────────────────────

    def _on_manual_confirm(self, row: int):
        """Confirm one item by hand. Packs like a scan, but is recorded as manual (AUDIT-02-9)."""
        if 0 <= row < len(self._rows):
            self.manual_confirm_requested.emit(self._rows[row]["sku"])
        self.set_focus_to_scanner()

    def _on_cancel_item(self, row: int):
        """Undo the last scan for one item.

        No confirmation: undoing a scan is undone by scanning again, and a
        confirm is for acts Undo cannot reach (shared.components.ConfirmDialog).
        """
        self.cancel_item_requested.emit(row)
        self.set_focus_to_scanner()

    def _on_force_confirm(self, row: int):
        """Open the Force confirm question for one item (frame 6f).

        The page draws it. The scanner is off until it is answered, so a scan
        cannot answer it by accident.
        """
        if not 0 <= row < len(self._rows) or not self._rows[row]["force"]:
            return
        self._question = force_question(self._rows[row])
        self.bridge.set_question(self._question)
        self._sync_scanner()

    def _on_question_answered(self, confirmed: bool):
        """Cancel or Force confirm. Forcing is not undoable."""
        question, self._question = self._question, {}
        self.bridge.set_question({})
        self._sync_scanner()
        if confirmed and question:
            self.force_confirm_requested.emit(question["row"])

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
        self._clear_timer.stop()
        self._paused = False
        # A question is about a row of the order it was asked on.
        self._question = {}
        self.bridge.set_question({})
        self._order_open = True
        self._items = list(items)
        self._unknown = []
        self._sku_map = dict(sku_map or {})
        self._rows = item_rows(self._items, order_state, self._sku_map)
        order_number = (
            items[0].get("Order_Number", items[0].get("order_number", ""))
            if items
            else ""
        )
        self.bridge.set_banner(banner_payload(order_number, metadata))
        self._order_label.setText(order_label(order_number))
        self._push_rows()
        self._sync_scanner()

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
            [
                {"row": r["row"], "packed": r["packed"], "required": r["required"]}
                for r in self._rows
            ],
            self._sku_map,
        )
        self._rows[row]["just_changed"] = True
        self._push_rows()

    def row_at(self, row: int) -> dict[str, Any]:
        """One item row's payload, for a caller writing a message about it."""
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}

    def _push_rows(self):
        """Send the item rows plus the unmatched scans, and the numbers.

        The unknown rows ride in the same `items` property so the list stays
        one list in one scroll container. The progress numbers are built from
        the item rows alone -- an unmatched scan is not a line to pack.
        """
        self.bridge.set_items(self._rows + unknown_rows(self._unknown))
        self.bridge.set_sku_rollup(sku_rollup(self._rows))
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

    def clear_screen_later(self, ms: int):
        """Hold the finished order on screen, scanner off, then reset.

        Showing another order or clearing the screen before then cancels it.
        """
        self._paused = True
        self._sync_scanner()
        self._clear_timer.start(ms)

    def clear_screen(self):
        """Reset the document to waiting for the next order.

        The session's history and order counts stay: they belong to the
        session, not to the order that just ended.

        A finished session outranks a per-order reset, so this refuses
        while the session-complete panel is up: the last order schedules
        this call 3s out, and it would otherwise wipe the panel that is
        the only way to end the session from this screen.
        """
        self._clear_timer.stop()
        if self._session_over:
            return
        self._items = []
        self._rows = []
        self._unknown = []
        self._sku_map = {}
        self._order_open = False
        self._paused = False
        self._question = {}
        self.bridge.set_question({})
        self.bridge.set_banner(banner_payload("", None))
        self.bridge.set_extras([])
        self.bridge.set_sku_rollup([])
        self._order_label.setText("No order")
        self.scanner_input.clear()
        self._raw_scan = ""
        self.show_notification("Scan an order barcode", "status_info")
        self._push_rows()
        self._sync_scanner()

    def show_session_complete(self, payload: dict[str, str]):
        """Show the session's terminal state in place of the order document.

        Args:
            payload: gui.packer_bridge.session_end_payload()'s title and body.
        """
        self._session_over = True
        self.bridge.set_session_end(payload)
        self._order_label.setText("Session complete")
        self._sync_scanner()

    def reset_for_new_session(self):
        """Take the session-complete panel down and clear the whole document.

        clear_screen() resets the *order*; this also resets what belongs to
        the *session* -- its history and order counts -- because the widget
        outlives every session the app runs.
        """
        self._session_over = False
        self.bridge.set_session_end({})
        self._taken_over = False
        self.bridge.set_takeover({})
        self._history = []
        self.bridge.set_history([])
        self._orders_done = 0
        self._orders_total = 0
        self._unsaved = False
        self.bridge.set_unsaved(False)
        self.clear_screen()  # pushes progress through _push_rows()

    def show_takeover(self, holder: str, list_name: str):
        """Another PC took this list's lock: block the screen (frame 6j).

        Nothing on the page works after this but Exit packing. Only
        reset_for_new_session() takes it down.
        """
        self._taken_over = True
        self._question = {}
        self.bridge.set_question({})
        self.bridge.set_takeover({"holder": str(holder), "list": str(list_name)})
        self._sync_scanner()

    def show_unknown_scans(self, scans: list[str]):
        """Show this order's unmatched scans as rows under the item rows.

        Args:
            scans: PackerLogic.unknown_scans -- the raw text of every scan
                in this order that matched no item and no mapping.
        """
        self._unknown = list(scans or [])
        self._push_rows()

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

    def set_unsaved(self, unsaved: bool):
        """Show, or clear, that the packing state is not reaching disk.

        A banner above the band (frame 6i), not part of it: scanning
        continues and the band keeps reporting each scan.
        """
        self._unsaved = bool(unsaved)
        self.bridge.set_unsaved(self._unsaved)

    def _push_feedback(self):
        self.bridge.set_feedback(self._feedback_text, self._feedback_role, self._raw_scan)

    def add_order_to_history(self, order_number: str, status: str = ""):
        """Add an order to the top of the session's history.

        One entry per order: a skipped order that is later packed moves to
        the top as complete (AUDIT-02-10).

        Args:
            order_number: The order that was just packed or skipped.
            status: "[SKIPPED]" for a skipped order; empty for a completed one.
        """
        self._history = [h for h in self._history if h["order"] != str(order_number)]
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
