import json
import os
import sys
import threading
from pathlib import Path

try:
    import winsound as _winsound

    def _beep(frequency: int, duration_ms: int) -> None:
        """Play a beep on a fire-and-forget daemon thread (non-blocking)."""
        threading.Thread(
            target=_winsound.Beep, args=(frequency, duration_ms), daemon=True
        ).start()

except ImportError:

    def _beep(frequency: int, duration_ms: int) -> None:  # type: ignore[misc]
        pass


import logging
from datetime import datetime

import pandas as pd
from openpyxl.styles import PatternFill
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.command_bar import PAGES, CommandBar
from gui.packer_bridge import session_end_payload
from gui.packer_mode_widget import PackerModeWidget
from gui.session_browser.session_browser_widget import SessionBrowserWidget
from gui.sku_mapping_dialog import SKUMappingDialog
from gui.statistics_widget import StatisticsWidget
from gui.theme import current_tokens, toggle_theme
from gui.worker_selection_dialog import WorkerSelectionDialog
from gui.workers import SessionEndWorker, SessionStartWorker
from packing_tool.exceptions import SessionLockedError, StaleLockError
from packing_tool.packer_logic import PackerLogic
from packing_tool.profile_manager import NetworkError, ProfileManager
from packing_tool.session_history_manager import SessionHistoryManager
from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_manager import SessionManager
from packing_tool.session_registry_manager import SessionRegistryManager
from packing_tool.worker_manager import WorkerManager
from shared.components.card import Card
from shared.components.toast import toast
from shared.icons import icon
from shared.navrail import NavRail
from shared.server_connection import ConnectionSettingsDialog, prompt_for_recovery_path
from shared.session_id import derive_session_id
from shared.stats_manager import StatsManager
from shared.theme import (
    StatusChip,
    font_css,
    get_density_profile,
    on_theme_changed,
    theme_notifier,
)

logger = logging.getLogger(__name__)

# Wider than Depot's 56px because packing-tool's labels do not fit it:
# "Statistics" measures 59px at floor density against a 45.6px budget, and
# guardrail 2 forbids abbreviating an existing label in the release that moves
# it. Spec 2026-08-29 §4 has the full measurement table.
RAIL_WIDTH = 76

# (icon name, rail label, tooltip) per destination, in rail order.
# "Packing" and "Statistics" are the existing tab titles, verbatim.
# "Browse" is not a rename -- Session Browser was a dialog title and has never
# had a rail label to change -- so the full name lives in its tooltip.
RAIL_ITEMS = (
    ("clipboard-list", "Packing", "Packing — the current session's orders"),
    ("table", "Statistics", "Statistics — session totals"),
    (
        "folder-open",
        "Browse",
        "Session Browser — active, completed and available sessions",
    ),
)

PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER = range(len(RAIL_ITEMS))

# T1's three order states. An order in progress is the one a packer is
# working right now, so it carries the solid mark; the other two are the
# system's reading of the packing list.
ORDER_STATUS_CHIP = {
    "in_progress": ("status_warning", "In progress", True, True),
    "packed": ("status_success", "Packed", False, False),
    "not_started": ("text_secondary", "Not started", False, False),
}

DEFAULT_CONFIG_PATH = "config.ini"


def order_summary(total: int, packed: int, in_progress: int) -> str:
    """The status bar's right-hand text (artboard T1). Empty with no orders."""
    if not total:
        return ""
    noun = "order" if total == 1 else "orders"
    return f"{total} {noun} · {packed} packed · {in_progress} in progress"


def _session_seconds(started_at) -> int:
    """Seconds since an ISO session start; 0 when it is missing or unreadable.

    A session restored from disk can carry anything in started_at, and a
    sentence that reports "in 0s" is better than one that raises.
    """
    if not started_at:
        return 0
    try:
        start = datetime.fromisoformat(str(started_at))
    except (TypeError, ValueError):
        return 0
    return max(int((datetime.now(start.tzinfo) - start).total_seconds()), 0)


def _unmapped_choices(order_state) -> list[tuple[str, str]]:
    """This order's lines as (sku, label), the ones still owing scans first.

    An unmatched scan happened while packing this order, so the SKU the packer
    meant is almost always a line that is not finished yet.
    """
    return [
        (
            s["original_sku"],
            f"{s['original_sku']} — {s['packed']} / {s['required']} packed",
        )
        for s in sorted(
            order_state or [],
            key=lambda s: s["packed"] >= s["required"],
        )
    ]


class MainWindow(QMainWindow):
    """
    The main application window, acting as the central orchestrator.

    This class initializes the UI, manages application state, and connects UI
    events to the backend logic. It handles the overall workflow, including
    session management, data loading, and switching between different views.

    Attributes:
        session_manager (SessionManager): Manages the lifecycle of packing sessions.
        logic (PackerLogic | None): The core business logic for the current session.
        stats_manager (StatisticsManager): Manages persistent application statistics.
        session_widget (QWidget): The main widget for the session view.
        packer_mode_widget (PackerModeWidget): The widget for the packer mode view.
        stacked_widget (QStackedWidget): Manages switching between views.
        orders_table (QTableView): The table displaying the list of orders.
    """

    def __init__(
        self,
        skip_worker_selection: bool = False,
        config_path: str = DEFAULT_CONFIG_PATH,
    ):
        """Initialize the MainWindow, sets up UI, and loads initial state.

        Args:
            skip_worker_selection: If True, skip worker selection dialog (for tests)
            config_path: Path to the configuration file (default: config.ini).
                Use a dev config (e.g. config.dev.ini) to point at a local mock server.
        """
        super().__init__()
        self.setWindowTitle("Packer's Assistant")

        from shared.theme import restore_window_geometry

        self._geometry_settings = QSettings("PackingTool", "MainWindowGeometry")
        if not restore_window_geometry(self, self._geometry_settings):
            self.resize(1024, 768)

        logger.info("Initializing MainWindow")

        # Detect if running in test mode
        self._is_test_mode = skip_worker_selection or "pytest" in sys.modules

        # Initialize ProfileManager, offering a path-recovery prompt on
        # NetworkError instead of exiting immediately.
        while True:
            try:
                self.profile_manager = ProfileManager(config_path)
                logger.info("ProfileManager initialized successfully")
                break
            except NetworkError as e:
                logger.exception("Failed to initialize ProfileManager")
                if prompt_for_recovery_path(self, str(e), "PackingTool"):
                    continue
                sys.exit(1)
            except Exception as e:
                logger.exception("Unexpected error initializing ProfileManager")
                QMessageBox.critical(
                    self, "Error", f"Failed to initialize application:\n\n{e}"
                )
            sys.exit(1)

        # Initialize SessionLockManager
        self.lock_manager = SessionLockManager(self.profile_manager)
        logger.info("SessionLockManager initialized successfully")

        # Initialize WorkerManager
        base_path = self.profile_manager.base_path
        self.worker_manager = WorkerManager(str(base_path))
        logger.info("WorkerManager initialized successfully")

        # Initialize SessionHistoryManager
        self.session_history_manager = SessionHistoryManager(self.profile_manager)
        logger.info("SessionHistoryManager initialized successfully")

        # Initialize SessionRegistryManager (per-client index for fast browser loading)
        self.registry_manager = SessionRegistryManager(self.profile_manager)
        logger.info("SessionRegistryManager initialized successfully")

        # Read scan simulator mode from config (enabled in development / no physical scanner)
        self._sim_mode = self.profile_manager.config.getboolean(
            "General", "ScanSimulatorMode", fallback=False
        )
        if self._sim_mode:
            logger.info("Scan Simulator Mode enabled (dev/test environment)")

        # Worker state
        self.current_worker_id = None
        self.current_worker_name = None

        # Current client state
        self.current_client_id = None
        self.session_manager = None  # Will be instantiated per client
        self.logic = None  # Will be instantiated per session

        # Shopify session state (new workflow)
        self.current_session_path = None  # Path to current Shopify session
        self.current_packing_list = None  # Name of selected packing list
        self.current_work_dir = None  # Work directory for packing results
        self.packing_data = None  # Loaded packing list data

        # Phase 1.4: Unified StatsManager for integration with Shopify Tool statistics
        # Records packing statistics to shared Stats/global_stats.json on file server
        # Used for:
        # 1. Historical analytics and performance tracking across both tools
        # 2. Integration with Shopify Tool (shared statistics file)
        # 3. Warehouse operation audit trail and worker performance metrics
        # 4. Per-client analytics and reporting
        # Note: Called once per session (at completion) by design - records session totals
        self.stats_manager = StatsManager(base_path=str(base_path))

        # Settings for remembering last client
        self.settings = QSettings("PackingTool", "ClientSelection")

        # Show worker selection BEFORE main window initialization (skip in test mode)
        if not self._is_test_mode:
            if not self._select_worker():
                # User cancelled - exit app
                logger.info("Worker selection cancelled - exiting application")
                sys.exit(0)
        else:
            # Test mode - use dummy worker
            self.current_worker_id = "test_worker_001"
            self.current_worker_name = "Test Worker"
            logger.info(f"Test mode: Using dummy worker {self.current_worker_name}")

        self._init_ui()

        # Load available clients and restore last selected
        self.load_available_clients()

        logger.info("MainWindow initialized successfully")

    def _init_ui(self):
        """Initialize all user interface components and layouts."""
        self.session_widget = QWidget()

        # The rail is full-height beside the pages, so it sits outside the
        # column that holds the client bar, the pages and the status line.
        shell = QHBoxLayout(self.session_widget)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.nav_rail = NavRail(width=RAIL_WIDTH)
        shell.addWidget(self.nav_rail)

        pages_side = QWidget()
        main_layout = QVBoxLayout(pages_side)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        shell.addWidget(pages_side, 1)

        # (no inline stylesheet — global QSS + QPalette handle all colors and fonts)

        # Set minimum window size
        self.setMinimumSize(900, 600)

        self.command_bar = CommandBar()
        main_layout.addWidget(self.command_bar)

        # Aliases: ~40 call sites already speak these names.
        self.client_combo = self.command_bar.client_combo
        self.client_combo.currentIndexChanged.connect(self.on_client_changed)
        self.search_input = self.command_bar.filter_input
        self.search_input.textChanged.connect(self._filter_orders)

        self.packer_mode_button = self.command_bar.start_packing_button
        self.packer_mode_button.setEnabled(False)
        self.packer_mode_button.setToolTip("Switch to barcode scanning / packer mode")
        self.packer_mode_button.clicked.connect(self.switch_to_packer_mode)

        self.sku_mapping_button = self.command_bar.sku_mapping_button
        self.sku_mapping_button.setToolTip("Manage barcode to SKU mappings")
        self.sku_mapping_button.clicked.connect(self.open_sku_mapping_dialog)

        self.toolbar_end_btn = self.command_bar.end_session_button
        self.toolbar_end_btn.setEnabled(False)
        self.toolbar_end_btn.setToolTip("End the current packing session")
        self.toolbar_end_btn.clicked.connect(self.end_session)

        self.command_bar.open_session_button.clicked.connect(self.open_session_browser)

        # Create tab widget for session views. A hidden tab bar makes this
        # exactly a QStackedWidget with the API the existing call sites already
        # speak; swapping the class would rewrite all of them to produce a
        # screen no user can tell apart.
        self.session_tabs = QTabWidget()
        self.session_tabs.tabBar().hide()

        # Tab 1: Packing View with expandable tree
        packing_tab = QWidget()
        packing_layout = QVBoxLayout(packing_tab)
        packing_layout.setContentsMargins(0, 0, 0, 0)

        self._setup_order_tree()
        self.order_tree_card = Card(margins=(0, 0, 0, 0))
        self.order_tree_card.add_widget(self.order_tree)
        packing_layout.addWidget(self.order_tree_card)

        self.session_tabs.addTab(packing_tab, "Packing")

        # Tab 2: Statistics View
        self.statistics_widget = StatisticsWidget()
        self.session_tabs.addTab(self.statistics_widget, "Statistics")

        # Tab 3: Session Browser — a destination now, not a dialog.
        self.session_browser = SessionBrowserWidget(
            profile_manager=self.profile_manager,
            session_lock_manager=self.lock_manager,
            session_history_manager=self.session_history_manager,
            worker_manager=self.worker_manager,
            registry_manager=self.registry_manager,
        )
        self.session_browser.resume_session_requested.connect(
            self._handle_resume_session_from_browser
        )
        self.session_browser.start_packing_requested.connect(
            self._handle_start_packing_from_browser
        )
        self.session_browser.sessions_shown.connect(
            lambda shown, total: self.sb_summary_label.setText(
                f"{shown} of {total} sessions"
            )
        )
        self.session_tabs.addTab(self.session_browser, "Session Browser")
        # load_available_clients() ran before this widget existed, so the
        # client it settled on (restored last_client, if any) never reached
        # the browser -- push it now that there is somewhere to push it.
        if self.current_client_id:
            self.session_browser.load_client(self.current_client_id)

        for icon_name, label, tip in RAIL_ITEMS:
            index = self.nav_rail.add_item(icon(icon_name), label)
            self.nav_rail.button(index).setToolTip(tip)

        # Two-way, and the back edge is load-bearing: code that jumps pages
        # directly must not leave the rail lit on the page the user left. It
        # cannot loop -- both set_current and NavRail.set_current return
        # before emitting when the index is unchanged.
        self.nav_rail.currentChanged.connect(self.session_tabs.setCurrentIndex)
        self.session_tabs.currentChanged.connect(self.nav_rail.set_current)
        self.session_tabs.currentChanged.connect(
            lambda index: self.command_bar.set_page(PAGES[index])
        )

        # The rail's stylesheet follows the theme on its own, but its icons are
        # rasterised at the colour in force when they were built.
        theme_notifier.changed.connect(self._refresh_rail_icons)

        main_layout.addWidget(self.session_tabs)

        self.packer_mode_widget = PackerModeWidget(sim_mode=self._sim_mode)
        self.packer_mode_widget.barcode_scanned.connect(self.on_scanner_input)
        self.packer_mode_widget.exit_packing_mode.connect(self.switch_to_session_view)
        self.packer_mode_widget.skip_order_requested.connect(self._on_skip_order)
        self.packer_mode_widget.cancel_item_requested.connect(self._on_cancel_item)
        self.packer_mode_widget.force_confirm_requested.connect(self._on_force_confirm)
        self.packer_mode_widget.map_sku_requested.connect(self._on_map_sku_from_packer)
        self.packer_mode_widget.extra_confirmed.connect(self._on_extra_confirmed)
        self.packer_mode_widget.extra_removed.connect(self._on_extra_removed)
        self.packer_mode_widget.end_session_requested.connect(self.end_session)
        self.packer_mode_widget.map_barcode_requested.connect(
            self._on_map_barcode_from_packer
        )

        # Stacked widget to switch between session view and packer mode
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.session_widget)
        self.stacked_widget.addWidget(self.packer_mode_widget)
        self.setCentralWidget(self.stacked_widget)

        self._init_overflow()
        self._init_status_bar()

    def _refresh_rail_icons(self, _theme_name=None):
        """Re-render the rail's glyphs at the new theme's text colour."""
        for index, (icon_name, _label, _tip) in enumerate(RAIL_ITEMS):
            self.nav_rail.button(index).setIcon(icon(icon_name))

    def _init_overflow(self):
        """App-level actions behind the bar's ⋯ (spec E4, owner answer Q2)."""
        menu = self.command_bar.overflow
        # Also reachable without a session: mappings are per client, not per session.
        menu.add_item("SKU mapping…", self.open_sku_mapping_dialog)
        menu.add_item("Select worker…", self._select_worker)
        menu.add_item("Server connection…", self._open_connection_settings)
        menu.add_item("Toggle dark/light theme", self._toggle_theme)
        menu.addSeparator()
        menu.add_item("Exit", self.close)

        # Through click(), which is a no-op on the disabled no-session button.
        end_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        end_shortcut.activated.connect(lambda: self.toolbar_end_btn.click())

    def _init_status_bar(self):
        """Artboard T1's 40px strip: session id and worker left, order summary right.

        Labels use caption size in text_secondary, per artboard.css .statusbar;
        the session id is also mono.
        """
        status_bar = self.statusBar()
        status_bar.setFixedHeight(40)
        status_bar.setSizeGripEnabled(False)

        self.sb_session_label = QLabel("—")
        self.sb_worker_label = QLabel(self.current_worker_name or "")
        self.sb_worker_label.setObjectName("worker_label")
        self.sb_summary_label = QLabel("")

        def style_labels(tokens):
            caption = f"{font_css('caption')} color: {tokens.text_secondary};"
            self.sb_worker_label.setStyleSheet(caption)
            self.sb_summary_label.setStyleSheet(caption)
            self.sb_session_label.setStyleSheet(
                f"{caption} font-family: {tokens.font_family_mono};"
            )

        on_theme_changed(status_bar, style_labels)
        status_bar.addWidget(self.sb_session_label)
        status_bar.addWidget(self.sb_worker_label)
        status_bar.addPermanentWidget(self.sb_summary_label)

    def _setup_order_tree(self):
        """Setup expandable order tree view."""
        self.order_tree = QTreeWidget()
        self.order_tree.setHeaderLabels(
            ["Order / Item", "Product", "Quantity", "Status", "Courier"]
        )

        # Column widths (interactive, with sensible defaults)
        from PySide6.QtWidgets import QHeaderView

        self.order_tree.setColumnWidth(0, 180)  # Order/SKU
        self.order_tree.setColumnWidth(2, 80)  # Quantity
        self.order_tree.setColumnWidth(3, 110)  # Status
        self.order_tree.setColumnWidth(4, 130)  # Courier
        self.order_tree.header().setSectionResizeMode(
            1, QHeaderView.Stretch
        )  # Product stretches

        self.order_tree.setAlternatingRowColors(True)
        self.order_tree.setUniformRowHeights(False)
        self.order_tree.setItemsExpandable(True)
        self.order_tree.setRootIsDecorated(True)

        # The floor rung, not a literal: T1's row height comes off the active
        # density profile rather than a hardcoded pixel count.
        row_height = get_density_profile().row_height
        self.order_tree.setStyleSheet(
            f"QTreeWidget::item {{ height: {row_height}px; }}"
        )

    def _order_status_chip(self, status: str) -> StatusChip:
        role, text, live, manual = ORDER_STATUS_CHIP.get(
            status, ORDER_STATUS_CHIP["not_started"]
        )
        return StatusChip(role, text, current_tokens(), live=live, manual=manual)

    def _populate_order_tree(self):
        """Populate tree with orders and items."""
        self.order_tree.clear()

        if (
            not self.logic
            or not hasattr(self.logic, "processed_df")
            or self.logic.processed_df is None
        ):
            self.sb_summary_label.setText("")
            return

        # Group by order number
        grouped = self.logic.processed_df.groupby("Order_Number")

        # Get completed and in-progress orders
        completed_orders = self.logic.session_packing_state.get("completed_orders", [])
        in_progress_orders = self.logic.session_packing_state.get("in_progress", {})

        for order_num, order_items in grouped:
            items_df = order_items
            total_items = len(items_df)

            # Check order status
            is_completed = order_num in completed_orders

            # Order status -- T1's chip, not a text summary
            if is_completed:
                chip_status = "packed"
            elif order_num in in_progress_orders:
                chip_status = "in_progress"
            else:
                chip_status = "not_started"

            # Courier
            courier = (
                items_df.iloc[0].get("Courier", "N/A")
                if "Courier" in items_df.columns
                else "N/A"
            )

            # Create top-level order item. Column 3 (Status) is filled by a
            # StatusChip below, once the item is in the tree.
            order_item = QTreeWidgetItem(
                [f"{order_num}", f"{total_items} items", "", "", courier]
            )

            # Bold font for order
            font = QFont()
            font.setBold(True)
            font.setPointSize(11)
            for col in range(5):
                order_item.setFont(col, font)

            # Add child items (SKUs) - OPTIMIZED: replaced iterrows() with itertuples()
            # itertuples() is 5-10x faster than iterrows() for DataFrame iteration
            for row_tuple in items_df.itertuples(index=False):
                # Access by column index from tuple
                sku = (
                    getattr(row_tuple, "SKU", "Unknown")
                    if hasattr(row_tuple, "SKU")
                    else "Unknown"
                )
                product = (
                    getattr(row_tuple, "Product_Name", "Unknown")
                    if hasattr(row_tuple, "Product_Name")
                    else "Unknown"
                )
                qty = (
                    getattr(row_tuple, "Quantity", 1)
                    if hasattr(row_tuple, "Quantity")
                    else 1
                )

                # Create child item. Status and Courier stay blank -- T1
                # draws the chip on the order row only.
                child_item = QTreeWidgetItem([f"  {sku}", product, str(qty), "", ""])

                # Normal font for items
                item_font = QFont()
                item_font.setPointSize(10)
                for col in range(5):
                    child_item.setFont(col, item_font)

                order_item.addChild(child_item)

            self.order_tree.addTopLevelItem(order_item)
            self.order_tree.setItemWidget(
                order_item, 3, self._order_status_chip(chip_status)
            )

            # Expand completed orders, collapse pending
            if is_completed:
                order_item.setExpanded(False)  # Keep compact
            else:
                order_item.setExpanded(True)  # Show current work

        self.sb_summary_label.setText(
            order_summary(
                grouped.ngroups, len(completed_orders), len(in_progress_orders)
            )
        )

    def _filter_orders(self, text: str):
        """Filter tree items by search text."""
        if not hasattr(self, "order_tree"):
            return

        if not text:
            # Show all
            for i in range(self.order_tree.topLevelItemCount()):
                self.order_tree.topLevelItem(i).setHidden(False)
            return

        text = text.lower()

        for i in range(self.order_tree.topLevelItemCount()):
            order_item = self.order_tree.topLevelItem(i)
            order_text = order_item.text(0).lower()

            # Check if order matches
            order_match = text in order_text

            # Check if any child (SKU) matches
            child_match = False
            for j in range(order_item.childCount()):
                child = order_item.child(j)
                child_text = f"{child.text(0)} {child.text(1)}".lower()
                if text in child_text:
                    child_match = True
                    break

            # Show if order or child matches
            order_item.setHidden(not (order_match or child_match))

    def _update_statistics(self):
        """Refresh the Statistics screen from the current session."""
        if not self.logic or getattr(self.logic, "processed_df", None) is None:
            self.statistics_widget.show_empty()
            return
        self.statistics_widget.update_from(
            self.logic.processed_df, self.logic.session_packing_state
        )

    def _select_worker(self) -> bool:
        """Show worker selection dialog

        Returns:
            bool: True if worker selected, False if cancelled
        """
        try:
            # Show selection dialog
            dialog = WorkerSelectionDialog(self.worker_manager, self)

            if dialog.exec() == QDialog.Accepted:
                self.current_worker_id = dialog.get_selected_worker_id()

                # Get worker details
                worker = self.worker_manager.get_worker(self.current_worker_id)
                if worker:
                    self.current_worker_name = worker.name
                    if hasattr(self, "sb_worker_label"):
                        self.sb_worker_label.setText(self.current_worker_name)
                    logger.info(
                        f"Logged in as: {self.current_worker_name} ({self.current_worker_id})"
                    )
                    return True

            logger.info("Worker selection cancelled")
            return False

        except Exception as e:
            logger.exception("Worker selection failed")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load worker profiles:\n{e!s}\n\nApplication will exit.",
            )
            return False

    # ========================================================================
    # CLIENT MANAGEMENT (NEW)
    # ========================================================================

    def load_available_clients(self):
        """Load available client profiles and populate dropdown."""
        logger.info("Loading available clients")

        self.client_combo.blockSignals(
            True
        )  # Prevent triggering on_client_changed during load
        self.client_combo.clear()

        try:
            clients = self.profile_manager.get_available_clients()

            if not clients:
                logger.warning("No clients found")
                self.client_combo.addItem("(No clients available)", None)
                self.client_combo.setEnabled(False)
                return

            self.client_combo.setEnabled(True)

            for client_id in clients:
                config = self.profile_manager.load_client_config(client_id)
                if config:
                    display_name = (
                        f"{config.get('client_name', client_id)} ({client_id})"
                    )
                else:
                    display_name = client_id

                self.client_combo.addItem(display_name, client_id)
                logger.debug(f"Added client: {client_id}")

            # Restore last selected client
            last_client = self.settings.value("last_client")
            if last_client:
                index = self.client_combo.findData(last_client)
                if index >= 0:
                    self.client_combo.setCurrentIndex(index)
                    logger.info(f"Restored last selected client: {last_client}")

            logger.info(f"Loaded {len(clients)} clients")

        except Exception as e:
            logger.exception("Error loading clients")
            QMessageBox.warning(self, "Error", f"Failed to load clients:\n\n{e}")

        finally:
            self.client_combo.blockSignals(False)

        # Trigger selection if there's a valid item
        if self.client_combo.currentData():
            self.on_client_changed(self.client_combo.currentIndex())

    def on_client_changed(self, index: int):
        """
        Handle client selection change.

        Args:
            index: Index of selected item in combo box
        """
        client_id = self.client_combo.currentData()

        if not client_id:
            logger.debug("No valid client selected")
            self.current_client_id = None
            return

        logger.info(f"Client changed to: {client_id}")

        self.current_client_id = client_id

        # Save as last selected client
        self.settings.setValue("last_client", client_id)

        logger.debug(f"Current client set to: {client_id}")

        # The browser has no picker of its own (Bundle 6): the command bar's
        # is the only one, so it has to push the change.
        if hasattr(self, "session_browser"):
            self.session_browser.load_client(client_id)

    def flash_border(self, color: str):
        """Flash the order document's edge with the scan's outcome.

        Args:
            color (str): "green", "red" or "orange". Anything else raises --
                a silently-passed-through value would emit a role no CSS rule
                matches, and would sail past style_lint.
        """
        self.packer_mode_widget.flash_scan(color)

    def start_session(
        self, file_path: str | None = None, restore_dir: str | None = None
    ):
        """
        Start a new packing session for the currently selected client.

        This method is used to start or restore Shopify Tool sessions. All sessions
        must be created through Shopify Tool - direct Excel file loading is no longer supported.

        Args:
            file_path: Path to the Shopify session directory (contains analysis_data.json).
                      Must be provided - no file dialog shown. Use the Session Browser
                      to let users choose a session.
            restore_dir: Optional directory of the session to restore (for crash recovery)
        """
        logger.info("Starting new session")

        # Check if client is selected
        if not self.current_client_id:
            logger.warning("Attempted to start session without selecting client")
            self.client_combo.setStyleSheet(
                f"border: 2px solid {current_tokens().status_danger};"
            )
            QMessageBox.warning(
                self,
                "No Client Selected",
                "Please select a client before starting a session!",
            )
            QTimer.singleShot(2000, lambda: self.client_combo.setStyleSheet(""))
            return

        # Check if session already active
        if self.session_manager and self.session_manager.is_active():
            logger.warning("Attempted to start session while one is already active")
            toast(self, "A session is already open. End it first.", role="info")
            return

        # Require file_path for Shopify sessions
        if not file_path and not restore_dir:
            logger.error("start_session() called without file_path or restore_dir")
            QMessageBox.warning(
                self,
                "No Session Selected",
                "Please use 'Load Shopify Session' to select a session.\n\n"
                "All sessions must be created through Shopify Tool.",
            )
            return

        # Clear existing tree
        if hasattr(self, "order_tree"):
            self.order_tree.clear()

        logger.info(
            f"Starting session for client {self.current_client_id} with path: {file_path}"
        )

        try:
            # Create SessionManager for this client
            self.session_manager = SessionManager(
                client_id=self.current_client_id,
                profile_manager=self.profile_manager,
                lock_manager=self.lock_manager,
                worker_id=self.current_worker_id,
                worker_name=self.current_worker_name,
            )

            # Start session
            session_id = self.session_manager.start_session(
                file_path, restore_dir=restore_dir
            )
            logger.info(f"Session started: {session_id}")

            # Get barcode directory (for Excel workflow backward compatibility)
            # This will be detected as legacy workflow in PackerLogic
            barcodes_dir = self.session_manager.get_barcodes_dir()

            # Create PackerLogic instance
            self.logic = PackerLogic(
                client_id=self.current_client_id,
                profile_manager=self.profile_manager,
                work_dir=barcodes_dir,
            )

            # Connect signals
            self.logic.item_packed.connect(self._on_item_packed)
            self.logic.all_orders_complete.connect(self._on_all_orders_complete)

            # Load Shopify session data
            session_path = self.session_manager.output_dir
            order_count, analysis_timestamp = self.logic.load_from_shopify_analysis(
                session_path
            )

            logger.info(
                f"Loaded {order_count} orders from Shopify analysis (analyzed at: {analysis_timestamp})"
            )

            # Setup order table
            self.setup_order_table()

            # Update UI
            toast(self, f"Loaded {order_count} orders.")
            self.packer_mode_button.setEnabled(True)

        except StaleLockError as e:
            # Session has a stale lock - offer to force-release it
            logger.warning(f"Session has stale lock: {e}")
            self._handle_stale_lock_error(e, file_path, restore_dir)
            self.session_manager = None
            self.logic = None

        except SessionLockedError as e:
            # Session is actively locked by another process
            logger.warning(f"Session is locked: {e}")
            self._handle_session_locked_error(e)
            self.session_manager = None
            self.logic = None

        except Exception as e:
            logger.exception("Failed to start session")
            QMessageBox.critical(self, "Error", f"Failed to start session:\n\n{e}")
            if self.session_manager:
                self.session_manager.end_session()
            self.session_manager = None
            self.logic = None

    def _toggle_theme(self):
        """Toggle between dark and light themes."""
        from PySide6.QtWidgets import QApplication

        toggle_theme(QApplication.instance())

    def _open_connection_settings(self):
        """Open the Server Connection settings dialog."""
        config_fallback = self.profile_manager.config.get(
            "Network", "FileServerPath", fallback=None
        )
        ConnectionSettingsDialog(
            self, "PackingTool", "FULFILLMENT_SERVER_PATH", config_fallback
        ).exec()

    def open_sku_mapping_dialog(self):
        """
        Open SKU mapping dialog for current client.

        Phase 1.3: Uses ProfileManager for centralized storage on file server.
        All changes are synchronized across all PCs with file locking.
        """
        if not self.current_client_id:
            logger.warning("Attempted to open SKU mapping without selecting client")
            QMessageBox.warning(
                self, "No Client Selected", "Please select a client first!"
            )
            return

        logger.info(f"Opening SKU mapping dialog for client {self.current_client_id}")

        # Phase 1.3: Use ProfileManager directly for centralized storage
        dialog = SKUMappingDialog(self.current_client_id, self.profile_manager, self)

        if dialog.exec():  # User clicked "Save & Close"
            # Mappings are already saved by the dialog
            logger.info("SKU mapping dialog closed with save")

            # If a session is active, reload the SKU map into logic instance
            if self.logic:
                try:
                    new_map = self.profile_manager.load_sku_mapping(
                        self.current_client_id
                    )
                    self.logic.set_sku_map(new_map)
                    toast(self, "SKU mapping saved and shared with every PC.")
                    logger.info("SKU mapping reloaded into active session")
                except Exception as e:
                    logger.exception("Failed to reload SKU mapping into session")
                    QMessageBox.warning(
                        self,
                        "Reload Warning",
                        f"Mappings saved successfully but failed to reload into current session:\n\n{e}\n\n"
                        f"Please restart the session to use new mappings.",
                    )

    def _start_heartbeat_timer(self):
        """Start timer to update session lock heartbeat."""
        if hasattr(self, "heartbeat_timer"):
            self.heartbeat_timer.stop()

        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._update_session_heartbeat)
        self.heartbeat_timer.start(60000)  # 60 seconds
        logger.debug("Heartbeat timer started")

    def _update_session_heartbeat(self):
        """Update heartbeat for active session lock."""
        if self.logic and hasattr(self, "current_work_dir") and self.current_work_dir:
            try:
                self.lock_manager.update_heartbeat(Path(self.current_work_dir))
                logger.debug("Lock heartbeat updated")
            except Exception:
                logger.exception("Failed to update heartbeat")

    def _cleanup_failed_session_start(self):
        """
        Clean up resources after failed session start.
        Extracted to avoid code duplication in exception handlers.
        """
        # Stop heartbeat timer if running
        if hasattr(self, "heartbeat_timer") and self.heartbeat_timer:
            try:
                self.heartbeat_timer.stop()
                logger.debug("Heartbeat timer stopped in cleanup")
            except Exception as timer_error:
                logger.warning(f"Failed to stop heartbeat timer: {timer_error}")

        # Release lock if acquired
        if hasattr(self, "current_work_dir") and self.current_work_dir:
            try:
                self.lock_manager.release_lock(Path(self.current_work_dir))
                logger.info(f"Lock released during cleanup: {self.current_work_dir}")
            except Exception as lock_error:
                logger.warning(f"Failed to release lock: {lock_error}")

        # Clear state
        if hasattr(self, "logic") and self.logic:
            self.logic = None

        # Clear instance variables
        if hasattr(self, "current_work_dir"):
            self.current_work_dir = None
        if hasattr(self, "current_session_path"):
            self.current_session_path = None
        if hasattr(self, "current_packing_list"):
            self.current_packing_list = None
        if hasattr(self, "packing_data"):
            self.packing_data = None

    def closeEvent(self, event: QCloseEvent):
        """
        Handle application close event - ensure clean shutdown.

        This method is called when:
        - User clicks X button
        - User presses Alt+F4
        - Application receives SIGTERM
        - System shutdown initiated

        Critical for multi-PC warehouse deployment:
        - Releases session locks immediately
        - Stops heartbeat timers
        - Saves session state
        - Prevents 2-minute stale lock timeout

        Args:
            event: Qt close event
        """
        logger.info("Application closing, performing cleanup...")

        try:
            from shared.theme import save_window_geometry

            try:
                save_window_geometry(self, self._geometry_settings)
            except Exception as e:
                logger.warning(f"Failed to save window geometry: {e}")

            # 1. Stop heartbeat timer (prevents lock updates during cleanup)
            if hasattr(self, "heartbeat_timer") and self.heartbeat_timer:
                try:
                    self.heartbeat_timer.stop()
                    logger.info("Heartbeat timer stopped")
                except Exception as e:
                    logger.warning(f"Failed to stop heartbeat timer: {e}")

            # 2. Save current packing state (if session active)
            if hasattr(self, "logic") and self.logic:
                try:
                    self.logic.save_state()
                    logger.info("Packing state saved")
                except Exception as e:
                    logger.warning(f"Failed to save packing state: {e}")

            # 3. Release lock on current work directory
            if hasattr(self, "current_work_dir") and self.current_work_dir:
                try:
                    self.lock_manager.release_lock(Path(self.current_work_dir))
                    logger.info(f"Lock released: {self.current_work_dir}")
                except Exception as e:
                    logger.warning(f"Failed to release lock: {e}")

            # 4. End Excel session if active
            if hasattr(self, "session_manager") and self.session_manager:
                try:
                    if self.session_manager.is_active():
                        # Close without generating full report (unexpected close)
                        # The session can be resumed later via Session Browser
                        logger.info("Excel session detected, closing gracefully")
                except Exception as e:
                    logger.warning(f"Failed to check session manager: {e}")

            # 5. Stop auto-refresh timer in Session Browser if open
            if hasattr(self, "session_browser_dialog"):
                try:
                    if hasattr(self.session_browser_dialog, "auto_refresh_timer"):
                        self.session_browser_dialog.auto_refresh_timer.stop()
                        logger.info("Session browser auto-refresh stopped")
                except Exception as e:
                    logger.warning(f"Failed to stop session browser timer: {e}")

            logger.info("Application cleanup completed successfully")

        except Exception:
            # Log but don't prevent shutdown
            logger.exception("Error during application cleanup")

        # Always accept the event (allow application to close)
        event.accept()

    def start_shopify_packing_session(
        self,
        packing_list_path: Path,
        work_dir: Path,
        session_path: Path,
        client_id: str,
        packing_list_name: str,
    ) -> bool:
        """
        Start packing session for Shopify packing list (new or resumed).

        This method handles BOTH:
        - Resuming interrupted sessions (from Session Browser)
        - Starting new sessions (from the Session Browser page)

        Args:
            packing_list_path: Path to packing list JSON file
            work_dir: Path to work directory (packing/{list_name}/)
            session_path: Path to session directory (Sessions/CLIENT_X/2025-XX-XX_X/)
            client_id: Client identifier
            packing_list_name: Name of the packing list

        Returns:
            bool: True if session started successfully, False otherwise

        Raises:
            FileNotFoundError: If packing list file not found
            json.JSONDecodeError: If packing list JSON is invalid
            ValueError: If packing data is invalid
            RuntimeError: If barcode generation fails
        """
        try:
            logger.info(f"Starting Shopify packing session: {packing_list_path}")
            logger.info(f"Work directory: {work_dir}")
            logger.info(f"Session path: {session_path}")

            # 1. Validate packing list file exists
            if not packing_list_path.exists():
                raise FileNotFoundError(f"Packing list not found: {packing_list_path}")

            # 2. Store session state
            self.current_session_path = str(session_path)
            self.current_packing_list = packing_list_name
            self.current_work_dir = str(work_dir)

            # 3. Acquire lock on work directory (with stale lock handling)
            success, error_msg = self._acquire_lock_with_stale_prompt(
                client_id, work_dir
            )
            if not success:
                if error_msg is None:
                    # User chose not to force-release
                    return False
                raise RuntimeError(error_msg)

            logger.info(f"Lock acquired on {work_dir}")

            # 4. Start heartbeat timer
            self._start_heartbeat_timer()
            logger.info("Heartbeat timer started")

            # 5 & 7. Initialize PackerLogic + load packing list in background thread
            # so the UI remains responsive (progress dialog animates while server is slow).
            progress = QProgressDialog("Loading packing list…", None, 0, 0, self)
            progress.setWindowTitle("Please Wait")
            progress.setWindowModality(Qt.WindowModal)
            progress.setCancelButton(None)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            QApplication.processEvents()

            start_worker = SessionStartWorker(
                client_id=client_id,
                profile_manager=self.profile_manager,
                work_dir=work_dir,
                packing_list_path=packing_list_path,
                parent=self,
            )
            start_worker.start()
            while not start_worker.wait(50):
                QApplication.processEvents()
            progress.close()

            if start_worker.error is not None:
                raise start_worker.error

            self.logic = start_worker.logic
            order_count = start_worker.order_count
            list_name = start_worker.list_name

            # 6. Connect signals (must happen on main thread after moveToThread)
            self.logic.item_packed.connect(self._on_item_packed)
            self.logic.all_orders_complete.connect(self._on_all_orders_complete)

            logger.info(f"Loaded {order_count} orders from packing list")

            # 8. Set minimal packing data for UI
            self.packing_data = {
                "list_name": list_name,
                "total_orders": order_count,
                "orders": [],  # Don't duplicate data - PackerLogic has it
            }

            # 9. Update session metadata
            if hasattr(self.session_manager, "update_session_metadata"):
                try:
                    self.session_manager.update_session_metadata(
                        self.current_session_path,
                        self.current_packing_list,
                        "in_progress",
                    )
                except Exception as e:
                    logger.warning(f"Could not update session metadata: {e}")

            # 9b. Register session start in registry (enables fast browser loading)
            try:
                _reg_total_items = 0
                if self.logic and self.logic.processed_df is not None:
                    _reg_total_items = int(
                        pd.to_numeric(
                            self.logic.processed_df["Quantity"], errors="coerce"
                        )
                        .fillna(0)
                        .sum()
                    )
                self.registry_manager.register_session_start(
                    client_id=client_id,
                    session_id=session_path.name,
                    packing_list_name=packing_list_name,
                    worker_id=self.current_worker_id,
                    worker_name=self.current_worker_name,
                    pc_name=os.environ.get("COMPUTERNAME", "Unknown"),
                    total_orders=order_count,
                    total_items=_reg_total_items,
                    work_dir=str(work_dir),
                    session_path=str(session_path),
                )
            except Exception as _e:
                logger.warning(f"Registry update (session start) failed: {_e}")

            # 10. Setup order table
            self.setup_order_table()

            # 11. Update UI state
            toast(self, f"Loaded {order_count} orders from {packing_list_name}.")

            # 12. Enable packing UI
            self.enable_packing_mode()

            logger.info("Shopify packing session started successfully")
            return True

        except FileNotFoundError as e:
            logger.exception("Packing list file not found")
            self._cleanup_failed_session_start()
            QMessageBox.critical(
                self, "File Not Found", f"Packing list file not found:\n{e!s}"
            )
            return False

        except json.JSONDecodeError as e:
            logger.exception("Invalid JSON in packing list")
            self._cleanup_failed_session_start()
            QMessageBox.critical(
                self, "Invalid JSON", f"Packing list contains invalid JSON:\n{e!s}"
            )
            return False

        except ValueError as e:
            logger.exception("Invalid packing data")
            self._cleanup_failed_session_start()
            QMessageBox.critical(
                self, "Invalid Data", f"Packing list contains invalid data:\n{e!s}"
            )
            return False

        except RuntimeError as e:
            logger.exception("Failed to start session")
            self._cleanup_failed_session_start()
            QMessageBox.critical(
                self, "Session Start Failed", f"Failed to start packing session:\n{e!s}"
            )
            return False

        except Exception as e:
            logger.exception("Unexpected error starting session")
            self._cleanup_failed_session_start()
            QMessageBox.critical(
                self, "Error", f"Unexpected error starting packing session:\n{e!s}"
            )
            return False

    def end_session(self):
        """
        Ends the current session gracefully.

        This involves saving a final report, cleaning up session files, and
        resetting the UI to its initial state.

        For Shopify sessions (unified work directory):
        - Report saved to: current_work_dir/reports/packing_completed.xlsx

        For Excel sessions (legacy):
        - Report saved to: session_dir/[original_filename]_completed.xlsx
        """
        # Check if any session is active (Excel or Shopify)
        is_excel_session = self.session_manager and self.session_manager.is_active()
        is_shopify_session = hasattr(self, "current_work_dir") and self.current_work_dir

        if not (is_excel_session or is_shopify_session):
            logger.warning("end_session called but no active session found")
            return

        try:
            # Determine output path based on session type
            if hasattr(self, "current_work_dir") and self.current_work_dir:
                # Shopify session - save to unified work directory
                report_dir = Path(self.current_work_dir) / "reports"
                report_dir.mkdir(exist_ok=True, parents=True)
                new_filename = "packing_completed.xlsx"
                output_path = str(report_dir / new_filename)
                logger.info(f"Saving Shopify session report to: {output_path}")
            else:
                # Excel session - save to session directory (legacy behavior)
                output_dir = self.session_manager.get_output_dir()
                original_filename = os.path.basename(
                    self.session_manager.packing_list_path
                )
                new_filename = (
                    f"{os.path.splitext(original_filename)[0]}_completed.xlsx"
                )
                output_path = os.path.join(output_dir, new_filename)
                logger.info(f"Saving Excel session report to: {output_path}")

            # Generate status map from session packing state
            completed_orders_set = set(
                self.logic.session_packing_state.get("completed_orders", [])
            )
            in_progress_orders = self.logic.session_packing_state.get("in_progress", {})

            final_df = self.logic.packing_list_df.copy()

            # Add Status column
            final_df["Status"] = final_df["Order_Number"].apply(
                lambda x: (
                    "Completed"
                    if x in completed_orders_set
                    else ("In Progress" if x in in_progress_orders else "New")
                )
            )

            # Add Completed At column
            final_df["Completed At"] = final_df["Order_Number"].apply(
                lambda x: (
                    datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
                    if x in completed_orders_set
                    else ""
                )
            )

            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                final_df.to_excel(writer, index=False, sheet_name="Sheet1")
                worksheet = writer.sheets["Sheet1"]
                green_fill = PatternFill(
                    start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"
                )
                status_col_idx = final_df.columns.get_loc("Status") + 1

                for row_idx, row in enumerate(
                    worksheet.iter_rows(min_row=2, max_row=worksheet.max_row)
                ):
                    status_cell = worksheet.cell(row=row_idx + 2, column=status_col_idx)
                    if status_cell.value == "Completed":
                        for cell in row:
                            cell.fill = green_fill

            toast(self, f"Session ended. Report saved to {output_path}")

            # Generate session summary + record stats in background thread so the
            # UI stays responsive while writing to the (potentially slow) file server.
            if self.logic:
                _is_shopify = (
                    hasattr(self, "current_work_dir") and self.current_work_dir
                )

                if _is_shopify:
                    _summary_path = os.path.join(
                        self.current_work_dir, "session_summary.json"
                    )
                    _session_type = "shopify"
                else:
                    _barcodes_dir = self.session_manager.get_barcodes_dir()
                    _summary_path = os.path.join(_barcodes_dir, "session_summary.json")
                    _session_type = "excel"

                # --- Gather all stats data on the main thread (fast, no server I/O) ---
                try:
                    _session_info = self.session_manager.get_session_info()
                    _start_time = None
                    if _session_info and "started_at" in _session_info:
                        try:
                            _start_time = datetime.fromisoformat(
                                _session_info["started_at"]
                            )
                            if _start_time.tzinfo is None:
                                # Legacy session_info.json from before timestamps were
                                # made timezone-aware; interpret as local time so the
                                # subtraction against tz-aware _end_time below doesn't
                                # raise TypeError.
                                _start_time = _start_time.astimezone()
                        except (ValueError, TypeError):
                            logger.warning(
                                "Could not parse started_at from session_info"
                            )
                except Exception as e:
                    logger.warning(f"Could not get session_info: {e}")
                    _session_info = None
                    _start_time = None

                _end_time = datetime.now().astimezone()
                _completed_orders_list = self.logic.session_packing_state.get(
                    "completed_orders", []
                )
                _completed_orders = len(_completed_orders_list)
                _in_progress_orders_dict = self.logic.session_packing_state.get(
                    "in_progress", {}
                )
                _in_progress_orders = len(_in_progress_orders_dict)

                _items_packed = 0
                try:
                    if self.logic.processed_df is not None and _completed_orders_list:
                        _ci = pd.to_numeric(
                            self.logic.processed_df[
                                self.logic.processed_df["Order_Number"].isin(
                                    _completed_orders_list
                                )
                            ]["Quantity"],
                            errors="coerce",
                        ).sum()
                        _items_packed += int(_ci)
                    for _osl in _in_progress_orders_dict.values():
                        if isinstance(_osl, list):
                            for _sd in _osl:
                                if isinstance(_sd, dict):
                                    _items_packed += _sd.get("packed", 0)
                except Exception:
                    logger.exception("Error calculating items_packed")

                _total_orders, _total_items = 0, 0
                try:
                    if self.logic.processed_df is not None:
                        _total_orders = len(
                            self.logic.processed_df["Order_Number"].unique()
                        )
                        _total_items = int(
                            pd.to_numeric(
                                self.logic.processed_df["Quantity"], errors="coerce"
                            ).sum()
                        )
                except Exception:
                    logger.exception("Error calculating totals")

                if _is_shopify:
                    _session_id = derive_session_id(
                        getattr(self, "current_session_path", "")
                    )
                    _pl_path_str = (
                        getattr(self, "current_packing_list", "Unknown") or "Unknown"
                    )
                else:
                    _session_id = self.session_manager.session_id
                    _pl_path_str = str(
                        self.session_manager.packing_list_path or "Unknown"
                    )

                _duration_seconds = (
                    int((_end_time - _start_time).total_seconds())
                    if _start_time
                    else None
                )

                # Capture non-Qt references for the closure
                _logic_ref = self.logic
                _client_id = self.current_client_id
                _worker_id = self.current_worker_id
                _worker_name = self.current_worker_name
                _stats_mgr = self.stats_manager
                _worker_mgr = self.worker_manager
                _sess_mgr = self.session_manager
                _cur_sess_path = getattr(self, "current_session_path", None)
                _cur_pack_list = getattr(self, "current_packing_list", None)
                _registry_mgr = getattr(self, "registry_manager", None)

                # Flush any pending state write on the main thread *before*
                # handing off to the background worker.  AsyncStateWriter's
                # flush() must only be called from the main/UI thread.
                _logic_ref._state_writer.flush()

                def _do_slow_writes():
                    # 1. Save session summary
                    try:
                        _logic_ref.save_session_summary(
                            summary_path=_summary_path,
                            worker_id=_worker_id,
                            worker_name=_worker_name,
                            session_type=_session_type,
                        )
                        logger.info(f"Session summary saved to: {_summary_path}")
                    except Exception as exc:
                        logger.exception("save_session_summary failed")
                        try:
                            from shared.atomic_write import atomic_write_json
                            from shared.metadata_utils import get_current_timestamp

                            _minimal = {
                                "version": "1.3.0",
                                "session_id": _logic_ref.session_id
                                if _logic_ref
                                else "unknown",
                                "session_type": _session_type,
                                "client_id": _client_id,
                                "worker_id": _worker_id,
                                "worker_name": _worker_name,
                                "completed_at": get_current_timestamp(),
                                "error": str(exc),
                            }
                            atomic_write_json(
                                _summary_path, _minimal, indent=2, ensure_ascii=False
                            )
                        except Exception as minimal_exc:
                            logger.debug(
                                f"Failed to write minimal session summary fallback: {minimal_exc}"
                            )

                    # 2. Record to stats
                    try:
                        _stats_mgr.record_packing(
                            client_id=_client_id,
                            session_id=_session_id,
                            worker_id=_worker_id,
                            orders_count=_completed_orders,
                            items_count=_items_packed,
                            metadata={
                                "duration_seconds": _duration_seconds,
                                "packing_list_name": os.path.basename(_pl_path_str),
                                "started_at": _start_time.isoformat()
                                if _start_time
                                else None,
                                "completed_at": _end_time.isoformat(),
                                "total_orders": _total_orders,
                                "in_progress_orders": _in_progress_orders,
                                "session_type": _session_type,
                                "user_name": os.environ.get("USERNAME", "Unknown"),
                                "worker_name": _worker_name,
                                "pc_name": os.environ.get("COMPUTERNAME", "Unknown"),
                            },
                        )
                        logger.info(
                            f"Recorded {_completed_orders} orders, {_items_packed} items to stats"
                        )
                    except Exception:
                        logger.exception("record_packing failed")

                    # 3. Update worker stats
                    try:
                        if _worker_id:
                            _worker_mgr.update_worker_stats(
                                worker_id=_worker_id,
                                sessions=1,
                                orders=_completed_orders,
                                items=_items_packed,
                                duration_seconds=_duration_seconds or 0,
                                session_id=_session_id,
                            )
                            logger.info(f"Updated worker stats for {_worker_name}")
                    except Exception:
                        logger.exception("update_worker_stats failed")

                    # 4. Update session metadata
                    try:
                        if _cur_sess_path and _cur_pack_list:
                            _sess_mgr.update_session_metadata(
                                _cur_sess_path,
                                _cur_pack_list,
                                "completed",
                                completed_orders=list(
                                    _logic_ref.session_packing_state.get(
                                        "completed_orders", []
                                    )
                                )
                                if _logic_ref
                                else None,
                            )
                            logger.info("Updated session metadata to 'completed'")
                    except Exception as exc:
                        logger.warning(f"update_session_metadata failed: {exc}")

                    # 5. Update session registry with completed status + metrics
                    try:
                        if (
                            _registry_mgr
                            and _client_id
                            and _cur_sess_path
                            and _cur_pack_list
                        ):
                            with open(_summary_path, "r", encoding="utf-8") as _f_reg:
                                _reg_summary = json.load(_f_reg)
                            _session_id_reg = Path(_cur_sess_path).name
                            _registry_mgr.register_session_complete(
                                _client_id,
                                _session_id_reg,
                                _cur_pack_list,
                                _reg_summary,
                            )
                            logger.info("Registry updated with session completion")
                    except Exception as exc:
                        logger.warning(
                            f"Registry update (session complete) failed: {exc}"
                        )

                # Show progress dialog while writes happen in background
                _end_progress = QProgressDialog("Saving session…", None, 0, 0, self)
                _end_progress.setWindowTitle("Please Wait")
                _end_progress.setWindowModality(Qt.WindowModal)
                _end_progress.setCancelButton(None)
                _end_progress.setMinimumDuration(0)
                _end_progress.setValue(0)
                _end_progress.show()
                QApplication.processEvents()

                _end_worker = SessionEndWorker(_do_slow_writes, self)
                _end_worker.start()
                while not _end_worker.wait(50):
                    QApplication.processEvents()
                _end_progress.close()

                if _end_worker.error:
                    logger.error(
                        f"Session end writes had an error: {_end_worker.error}"
                    )

        except Exception as e:
            # Neutral title: this can fire after the report was already saved.
            QMessageBox.critical(
                self,
                "Session end failed",
                f"Could not finish ending the session:\n\n{e}",
            )
            logger.exception("Error during end_session")

        # CRITICAL: Stop heartbeat timer and release lock
        if hasattr(self, "heartbeat_timer"):
            self.heartbeat_timer.stop()
            logger.debug("Heartbeat timer stopped")

        if hasattr(self, "current_work_dir") and self.current_work_dir:
            try:
                self.lock_manager.release_lock(Path(self.current_work_dir))
                logger.info("Lock released")
            except Exception:
                logger.exception("Failed to release lock")

        # Cleanup PackerLogic state
        if self.logic:
            self.logic.end_session_cleanup()
            self.logic = None

        # End Excel session if active
        if self.session_manager and self.session_manager.is_active():
            self.session_manager.end_session()

        # Clear Shopify session variables
        if hasattr(self, "current_work_dir"):
            self.current_work_dir = None
        if hasattr(self, "current_session_path"):
            self.current_session_path = None
        if hasattr(self, "current_packing_list"):
            self.current_packing_list = None
        if hasattr(self, "packing_data"):
            self.packing_data = None

        self.packer_mode_button.setEnabled(False)

        self.toolbar_end_btn.setEnabled(False)
        self._show_session(None)

        if hasattr(self, "order_tree"):
            self.order_tree.clear()
        self.sb_summary_label.setText("")

        if self.packer_mode_widget:
            self.packer_mode_widget.reset_for_new_session()

        # Return user to session view (avoids leaving a blank packer mode screen)
        if hasattr(self, "stacked_widget") and hasattr(self, "session_widget"):
            self.stacked_widget.setCurrentWidget(self.session_widget)

        logger.info("Session ended and all variables cleared")

    def setup_order_table(self):
        """
        Sets up the expandable order tree and statistics display.

        This method populates the tree widget with orders and items,
        and updates the statistics tab with session metrics.
        """
        # Populate the expandable tree
        self._populate_order_tree()

        # Update statistics
        self._update_statistics()

        logger.info("Order tree and statistics updated successfully")

    def switch_to_packer_mode(self):
        """Switches the view to the Packer Mode widget."""
        self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
        self.packer_mode_widget.set_focus_to_scanner()

    def switch_to_session_view(self):
        """Switches the view back to the main session widget (tabbed interface)."""
        if self.logic:
            self.logic.clear_current_order()
        if self.packer_mode_widget:
            self.packer_mode_widget.clear_screen()
        self.stacked_widget.setCurrentWidget(self.session_widget)

    def on_scanner_input(self, text: str):
        """
        Handles input from the barcode scanner in Packer Mode.

        This is the central callback for all barcode scans. It determines if
        the scan is for an order or a product SKU and routes the logic accordingly.

        Args:
            text (str): The decoded text from the barcode scanner.
        """
        self.packer_mode_widget.update_raw_scan_display(text)
        self.packer_mode_widget.show_notification("", "transparent")

        if self.logic.current_order_number is None:
            items, status = self.logic.start_order_packing(text)
            if status == "ORDER_LOADED":
                order_number_from_scan = self.logic.current_order_number
                self.packer_mode_widget.add_order_to_history(order_number_from_scan)
                order_metadata = self.logic.orders_data.get(
                    order_number_from_scan, {}
                ).get("metadata", {})
                self.packer_mode_widget.display_order(
                    items,
                    self.logic.current_order_state,
                    metadata=order_metadata,
                    sku_map=self.logic.sku_map,
                )
                completed = len(
                    self.logic.session_packing_state.get("completed_orders", [])
                )
                self.packer_mode_widget.update_session_progress(
                    completed, len(self.logic.orders_data)
                )
                self.update_order_status(order_number_from_scan, "In Progress")
                _beep(1000, 120)
            elif status == "ORDER_ALREADY_COMPLETED":
                self.packer_mode_widget.show_notification(
                    f"Order #{text} is already packed", "status_warning"
                )
                self.flash_border("orange")
            else:
                self.packer_mode_widget.show_notification(
                    f"No order matches {text}", "status_danger"
                )
                self.flash_border("red")
                _beep(400, 350)
        else:
            result, status = self.logic.process_sku_scan(text)
            if status == "SKU_OK":
                self.packer_mode_widget.update_item_row(
                    result["row"], result["packed"], result["is_complete"]
                )
                row = self.packer_mode_widget.row_at(result["row"])
                self.packer_mode_widget.show_notification(
                    f"{row.get('sku', '')} confirmed — {result['packed']} of "
                    f"{row.get('required', 0)} packed",
                    "status_success",
                )
                self.flash_border("green")
                _beep(1200, 80)
            elif status == "SKU_NOT_FOUND":
                self.packer_mode_widget.show_notification(
                    f"Unknown SKU {text} — scan again or map it", "status_danger"
                )
                self.packer_mode_widget.show_unknown_scans(self.logic.unknown_scans)
                self.flash_border("red")
                _beep(400, 350)
            elif status == "SKU_EXTRA":
                self.packer_mode_widget.show_notification(
                    "Extra item scanned — keep it or remove it", "status_warning"
                )
                self.flash_border("orange")
                _beep(700, 200)
                self.packer_mode_widget.show_extras_panel(
                    self.logic.current_extra_items
                )
            elif status == "ORDER_COMPLETE_WITH_EXTRAS":
                self.packer_mode_widget.update_item_row(
                    result["row"], result["packed"], result["is_complete"]
                )
                self.packer_mode_widget.show_notification(
                    "Review the extra items before this order can close",
                    "status_warning",
                )
                self.flash_border("orange")
                self.packer_mode_widget.show_extras_panel(
                    self.logic.current_extra_items
                )
            elif status == "ORDER_COMPLETE":
                current_order_num = self.logic.current_order_number
                self.packer_mode_widget.update_item_row(
                    result["row"], result["packed"], result["is_complete"]
                )
                self._handle_order_completion(current_order_num)
                self.logic.clear_current_order()

    # REMOVED: _process_shopify_packing_data() method (dead code)
    # This method was never called. Functionality replaced by PackerLogic.load_packing_list_json()
    # which is used in start_shopify_packing_session()

    def _on_item_packed(
        self, order_number: str, packed_count: int, required_count: int
    ):
        """
        Slot to handle real-time progress updates from the logic layer.

        This method is connected to the `item_packed` signal from PackerLogic.
        It refreshes the tree and statistics to reflect the updated progress.

        Args:
            order_number (str): The order number that was updated.
            packed_count (int): The new total of items packed for the order.
            required_count (int): The total items required for the order.
        """
        # Refresh tree and statistics to show updated progress
        self._populate_order_tree()
        self._update_statistics()
        logger.debug(f"Order {order_number} progress: {packed_count}/{required_count}")

    def update_order_status(self, order_number: str, status: str):
        """
        Updates the status of an order in the tree view.

        Args:
            order_number (str): The order number to update.
            status (str): The new status ('In Progress' or 'Completed').
        """
        # Simply refresh the tree and statistics to reflect the new status
        self._populate_order_tree()
        self._update_statistics()
        logger.debug(f"Order {order_number} status updated to: {status}")

    # ─── Packer Mode new action handlers ─────────────────────────────────────

    def _handle_order_completion(self, order_number: str):
        """Shared teardown for every order-complete path (scan, force confirm, extra resolve)."""
        self.packer_mode_widget.show_notification(
            f"Order #{order_number} packed. Scan the next order.", "status_success"
        )
        self.flash_border("green")
        _beep(1200, 80)
        QTimer.singleShot(180, lambda: _beep(1200, 80))
        self.update_order_status(order_number, "Completed")
        if self.logic:
            completed = len(
                self.logic.session_packing_state.get("completed_orders", [])
            )
            self.packer_mode_widget.update_session_progress(
                completed, len(self.logic.orders_data)
            )
        self.packer_mode_widget.scanner_input.setEnabled(False)
        QTimer.singleShot(3000, self.packer_mode_widget.clear_screen)

    def _on_skip_order(self):
        """Skip the currently active order (preserves packing progress for later)."""
        if not self.logic or not self.logic.current_order_number:
            return
        skipped = self.logic.current_order_number
        self.logic.skip_order()
        self.packer_mode_widget.add_order_to_history(skipped, "[SKIPPED]")
        self.packer_mode_widget.clear_screen()
        logger.info(f"Order {skipped} skipped")

    def _on_cancel_item(self, row: int):
        """Handle -1 (undo last scan) for a specific item row."""
        if not self.logic:
            return
        result, status = self.logic.cancel_item_scan(row)
        if status == "ITEM_DECREMENTED":
            self.packer_mode_widget.update_item_row(row, result["packed"], False)
            self.flash_border("orange")
        elif status == "ITEM_ALREADY_ZERO":
            self.packer_mode_widget.show_notification(
                "Nothing packed on that line yet", "status_warning"
            )
        self.packer_mode_widget.set_focus_to_scanner()

    def _on_force_confirm(self, row: int):
        """Handle Force Confirm for a specific item row."""
        if not self.logic:
            return
        result, status = self.logic.force_confirm_item(row)
        if status == "FORCE_CONFIRMED":
            self.packer_mode_widget.update_item_row(row, result["packed"], True)
            if result.get("order_complete"):
                self.flash_border("green")
                order_num = self.logic.current_order_number
                self._handle_order_completion(order_num)
                self.logic.clear_current_order()
            elif self.logic.current_extra_items:
                # All items packed but extra items need resolution before completing
                self.flash_border("orange")
                self.packer_mode_widget.show_notification(
                    "Review the extra items before this order can close",
                    "status_warning",
                )
                self.packer_mode_widget.show_extras_panel(
                    self.logic.current_extra_items
                )
            else:
                self.flash_border("green")
        self.packer_mode_widget.set_focus_to_scanner()

    def _save_sku_mapping(self, barcode: str, sku: str) -> bool:
        """Save one barcode → SKU mapping, confirming an overwrite first.

        Shared by both directions of the Map SKU flow: the per-item button
        knows the SKU and asks for the barcode, and the unmatched-scan row
        knows the barcode and asks for the SKU.
        """
        try:
            existing = self.profile_manager.load_sku_mapping(self.current_client_id)
            if barcode in existing and existing[barcode] != sku:
                reply = QMessageBox.question(
                    self,
                    "Overwrite Mapping?",
                    f"Barcode '{barcode}' already maps to '{existing[barcode]}'.\n\n"
                    f"Replace with '{sku}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return False

            existing[barcode] = sku
            if not self.profile_manager.save_sku_mapping(
                self.current_client_id, existing
            ):
                QMessageBox.warning(
                    self, "Save Failed", "Could not save mapping to file server."
                )
                return False

            if self.logic:
                self.logic.sku_map = {
                    self.logic._normalize_sku(k): v for k, v in existing.items()
                }
                logger.info(f"Quick-mapped barcode '{barcode}' → SKU '{sku}'")
            self.packer_mode_widget.show_notification(
                f"Mapped: {barcode} → {sku}", "status_success"
            )
            return True
        except Exception as e:
            logger.exception("Failed to save quick SKU mapping")
            QMessageBox.critical(self, "Error", f"Failed to save mapping:\n\n{e}")
            return False

    def _on_map_sku_from_packer(self, sku: str):
        """Quick-add barcode→SKU mapping from packer mode.

        Pre-populates the SKU so the worker only needs to scan/type the barcode.
        The barcode field is left empty for the scanner to fill in.
        """
        if not self.current_client_id:
            self.packer_mode_widget.set_focus_to_scanner()
            return

        barcode, ok = QInputDialog.getText(
            self,
            "Map Barcode to SKU",
            f"SKU:  {sku}\n\nScan or type the product barcode to map to this SKU:",
        )
        if not (ok and barcode and barcode.strip()):
            self.packer_mode_widget.set_focus_to_scanner()
            return

        self._save_sku_mapping(barcode.strip(), sku)
        self.packer_mode_widget.set_focus_to_scanner()

    def _on_map_barcode_from_packer(self, barcode: str):
        """Map an unmatched scan to one of this order's SKUs, then replay it.

        The reverse of _on_map_sku_from_packer: here the barcode is known and
        the SKU is picked. Replaying the scan afterwards packs the item in the
        same gesture -- the scan already happened, and making the packer scan
        again to use a mapping they just made is a step with no purpose.
        """
        choices = (
            _unmapped_choices(self.logic.current_order_state) if self.logic else []
        )
        if not (choices and self.current_client_id):
            self.packer_mode_widget.set_focus_to_scanner()
            return

        labels = [label for _sku, label in choices]
        picked, ok = QInputDialog.getItem(
            self,
            "Map SKU",
            f"Barcode {barcode}\n\nWhich item did you scan?",
            labels,
            0,
            False,
        )
        if not (ok and picked):
            self.packer_mode_widget.set_focus_to_scanner()
            return

        sku = choices[labels.index(picked)][0]
        if self._save_sku_mapping(barcode, sku):
            # It matches an item now, so its "No match" row goes with the mapping.
            self.logic.unknown_scans = [
                scan for scan in self.logic.unknown_scans if scan != barcode
            ]
            self.packer_mode_widget.show_unknown_scans(self.logic.unknown_scans)
            self.on_scanner_input(barcode)
        self.packer_mode_widget.set_focus_to_scanner()

    def _on_extra_confirmed(self, norm_sku: str):
        """Handle 'Keep' for an extra item — user acknowledges it is intentional."""
        if not self.logic:
            return
        _, status = self.logic.confirm_keep_extra(norm_sku)
        self.packer_mode_widget.show_extras_panel(self.logic.current_extra_items)
        if status == "ORDER_NOW_COMPLETE":
            order_num = self.logic.current_order_number
            self._handle_order_completion(order_num)
            self.logic.clear_current_order()
        elif status == "EXTRA_CLEARED":
            self.packer_mode_widget.show_notification(
                "Extra cleared — continue scanning", "status_success"
            )
        self.packer_mode_widget.set_focus_to_scanner()

    def _on_extra_removed(self, norm_sku: str):
        """Handle 'Remove' for an extra item — user acknowledges it was a mistake."""
        if not self.logic:
            return
        _, status = self.logic.remove_extra_item(norm_sku)
        self.packer_mode_widget.show_extras_panel(self.logic.current_extra_items)
        if status == "ORDER_NOW_COMPLETE":
            order_num = self.logic.current_order_number
            self._handle_order_completion(order_num)
            self.logic.clear_current_order()
        elif status == "EXTRA_CLEARED":
            self.packer_mode_widget.show_notification(
                "Extra cleared — continue scanning", "status_success"
            )
        self.packer_mode_widget.set_focus_to_scanner()

    def _on_all_orders_complete(self):
        """Handle the all_orders_complete signal — defer dialog to next event loop tick.

        Deferring prevents an AttributeError that occurs when the signal is emitted
        synchronously inside process_sku_scan(), because showing a QMessageBox here
        (and the user clicking Yes → end_session() → self.logic = None) would corrupt
        the caller's stack frame that still holds references to self.logic.
        """
        QTimer.singleShot(0, self._show_session_complete)

    def _show_session_complete(self):
        """Show the session's terminal state in the document (Bundle 5 spec S2).

        This replaces the "End session now?" QMessageBox. The decision the
        modal asked is now P8's two buttons, so the packer answers it on the
        screen that announced the session was over instead of through a dialog
        over it.
        """
        if not self.logic:
            return
        state = self.logic.session_packing_state
        self.packer_mode_widget.show_session_complete(
            session_end_payload(
                packed=len(state.get("completed_orders", [])),
                total=len(self.logic.orders_data),
                skipped=len(state.get("skipped_orders", [])),
                items=sum(
                    order.get("items_count", 0)
                    for order in (self.logic.completed_orders_metadata or [])
                ),
                seconds=_session_seconds(self.logic.started_at),
            )
        )

    # REMOVED: open_restore_session_dialog() method (dead code)
    # This method was never called. Functionality replaced by Session Browser's
    # Active/Completed tabs which provide a better UX for session restoration

    def enable_packing_mode(self):
        """
        Enable packing UI after session data is loaded.

        This method:
        - Disables session start buttons
        - Enables packing operation buttons
        - Shows the session in the command bar and status bar
        - Prepares UI for packing operations
        """
        logger.info("Enabling packing mode UI")

        # Enable packing operation buttons
        self.packer_mode_button.setEnabled(True)

        self.toolbar_end_btn.setEnabled(True)

        session_id = (
            Path(self.current_session_path).name
            if self.current_session_path
            else (self.current_packing_list or "")
        )
        self._show_session(session_id or None, self.current_packing_list or "")

        logger.info("Packing mode UI enabled successfully")

    def _show_session(self, session_id, packing_list=""):
        """The session's id in the bar and status bar, and its tooltip, set together."""
        self.command_bar.set_session(session_id)
        self.command_bar.session_label.setToolTip(packing_list if session_id else "")
        self.sb_session_label.setText(session_id or "—")

    def open_session_browser(self):
        """Show the Session Browser page.

        What the old dialog-opening entry point became; the rail is the way
        there now, but this stays as the one place that navigation happens.
        """
        logger.info("Showing Session Browser page")
        self.session_tabs.setCurrentIndex(PAGE_BROWSER)

    def _start_or_resume_from_browser(
        self,
        client_id,
        packing_list_name,
        session_path,
        packing_list_path,
        work_dir=None,
        resumed=False,
    ):
        """
        Shared logic for the Session Browser's "Resume" and "Start Packing" actions.

        If work_dir is None, one is created via SessionManager.get_packing_work_dir()
        (the "start packing" case); otherwise the existing work_dir is reused (resume).
        """
        # The browser is a page now, so there is no dialog to accept -- the
        # equivalent is going back to the page the work happens on.
        self.session_tabs.setCurrentIndex(PAGE_PACKING)

        # Set current client if different
        if self.current_client_id != client_id:
            for i in range(self.client_combo.count()):
                if self.client_combo.itemData(i) == client_id:
                    self.client_combo.setCurrentIndex(i)
                    break

        # Check if session already active
        if self.session_manager and self.session_manager.is_active():
            logger.warning(
                "Attempted to start/resume packing while a session is already active"
            )
            QMessageBox.warning(
                self,
                "Session Active",
                "A session is already active. Please end it first.",
            )
            return

        # Create SessionManager for this client if not exists
        if not self.session_manager or self.session_manager.client_id != client_id:
            self.session_manager = SessionManager(
                client_id=client_id,
                profile_manager=self.profile_manager,
                lock_manager=self.lock_manager,
                worker_id=self.current_worker_id,
                worker_name=self.current_worker_name,
            )

        if work_dir is None:
            work_dir = self.session_manager.get_packing_work_dir(
                session_path=str(session_path), packing_list_name=packing_list_name
            )
            logger.info(f"Work directory created: {work_dir}")

        # Use unified session start method
        success = self.start_shopify_packing_session(
            packing_list_path=packing_list_path,
            work_dir=work_dir,
            session_path=session_path,
            client_id=client_id,
            packing_list_name=packing_list_name,
        )

        if not success:
            return

        # Get order count for success message
        order_count = (
            self.packing_data.get("total_orders", 0)
            if hasattr(self, "packing_data")
            else 0
        )
        list_name = (
            self.packing_data.get("list_name", packing_list_name)
            if hasattr(self, "packing_data")
            else packing_list_name
        )

        if resumed:
            QMessageBox.information(
                self,
                "Session Resumed",
                f"Successfully resumed packing list: {list_name}\n"
                f"Orders: {order_count}\n\n"
                f"Continue packing from where you left off.",
            )
            logger.info("Session resumed successfully from Session Browser")
        else:
            QMessageBox.information(
                self,
                "Session Loaded",
                f"Loaded packing list: {list_name}\n"
                f"Orders: {order_count}\n\n"
                f"Ready to start packing.",
            )
            logger.info("Packing session started successfully from Session Browser")

    def _handle_resume_session_from_browser(self, session_info: dict):
        """
        Handle resume request from Session Browser.

        Args:
            session_info: Dict with session_path, client_id, packing_list_name, work_dir
        """
        logger.info(
            f"Resuming session from browser: {session_info.get('session_id', 'Unknown')}"
        )

        session_path = Path(session_info["session_path"])
        client_id = session_info["client_id"]
        packing_list_name = session_info["packing_list_name"]
        work_dir = Path(session_info["work_dir"])
        packing_list_path = session_path / "packing_lists" / f"{packing_list_name}.json"

        self._start_or_resume_from_browser(
            client_id,
            packing_list_name,
            session_path,
            packing_list_path,
            work_dir=work_dir,
            resumed=True,
        )

    def _handle_start_packing_from_browser(self, packing_info: dict):
        """
        Handle start packing request from Session Browser Available tab.

        Args:
            packing_info: Dict with session_path, client_id, packing_list_name, list_file
        """
        logger.info(
            f"Starting packing session from browser: {packing_info.get('packing_list_name', 'Unknown')}"
        )

        session_path = Path(packing_info["session_path"])
        client_id = packing_info["client_id"]
        packing_list_name = packing_info["packing_list_name"]
        packing_list_path = Path(packing_info["list_file"])

        self._start_or_resume_from_browser(
            client_id,
            packing_list_name,
            session_path,
            packing_list_path,
            work_dir=None,
            resumed=False,
        )

    def _acquire_lock_with_stale_prompt(self, client_id: str, work_dir: Path):
        """
        Acquire a session lock, offering to force-release it if stale.

        Returns:
            (True, None) on success.
            (False, None) if the lock is stale and the user declined to force-release.
            (False, error_msg) if the lock is actively held, or force-release+retry failed.
        """
        success, error_msg, _ = self.lock_manager.acquire_lock(
            client_id,
            work_dir,
            worker_id=self.current_worker_id,
            worker_name=self.current_worker_name,
        )
        if success:
            return True, None

        if not (error_msg and "stale" in error_msg.lower()):
            return False, error_msg

        reply = QMessageBox.question(
            self,
            "Stale Lock Detected",
            f"{error_msg}\n\nForce-release lock and continue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False, None

        self.lock_manager.force_release_lock(work_dir)
        success, error_msg, _ = self.lock_manager.acquire_lock(
            client_id,
            work_dir,
            worker_id=self.current_worker_id,
            worker_name=self.current_worker_name,
        )
        return success, error_msg

    def _handle_session_locked_error(self, error: SessionLockedError):
        """
        Handle when a session is actively locked by another process.

        Shows a dialog informing the user that the session is currently in use.

        Args:
            error: SessionLockedError with lock information
        """
        lock_info = error.lock_info
        if not lock_info:
            QMessageBox.warning(
                self,
                "Session Locked",
                "This session is currently locked by another process.\n\n"
                "Please wait or choose a different session.",
            )
            return

        locked_by = lock_info.get("locked_by", "Unknown PC")
        user_name = lock_info.get("user_name", "Unknown user")
        lock_time = lock_info.get("lock_time", "Unknown time")

        # Format time nicely
        try:
            from datetime import datetime

            lock_dt = datetime.fromisoformat(lock_time)
            lock_time_formatted = lock_dt.strftime("%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            lock_time_formatted = lock_time

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Session Already in Use")
        msg.setText("This session is currently active on another computer.")
        msg.setInformativeText(
            f"<b>User:</b> {user_name}<br>"
            f"<b>Computer:</b> {locked_by}<br>"
            f"<b>Started:</b> {lock_time_formatted}<br><br>"
            "Please wait for the user to finish, or choose another session."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _handle_stale_lock_error(
        self, error: StaleLockError, file_path: str, restore_dir: str
    ):
        """
        Handle when a session has a stale lock (possible crash).

        Shows a dialog allowing the user to force-release the lock and open the session.

        Args:
            error: StaleLockError with lock information
            file_path: Path to the packing list file
            restore_dir: Directory of the session to restore
        """
        lock_info = error.lock_info
        if not lock_info:
            QMessageBox.warning(self, "Stale Lock", "Session has an invalid lock file.")
            return

        locked_by = lock_info.get("locked_by", "Unknown PC")
        user_name = lock_info.get("user_name", "Unknown user")
        heartbeat = lock_info.get("heartbeat", "Unknown")
        stale_minutes = error.stale_minutes

        # Format time nicely
        try:
            from datetime import datetime

            heartbeat_dt = datetime.fromisoformat(heartbeat)
            heartbeat_formatted = heartbeat_dt.strftime("%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            heartbeat_formatted = heartbeat

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Stale Session Lock Detected")
        msg.setText("This session has a stale lock - the application may have crashed.")
        msg.setInformativeText(
            f"<b>Original user:</b> {user_name}<br>"
            f"<b>Computer:</b> {locked_by}<br>"
            f"<b>Last heartbeat:</b> {heartbeat_formatted}<br>"
            f"<b>No response for:</b> {stale_minutes} minutes<br><br>"
            "The application may have crashed on that PC.<br><br>"
            "<b>Do you want to force-release the lock and open this session?</b>"
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)

        reply = msg.exec()

        if reply == QMessageBox.Yes:
            # Force release the lock
            logger.info(
                f"User chose to force-release stale lock for session {restore_dir}"
            )
            try:
                success = self.lock_manager.force_release_lock(Path(restore_dir))
                if success:
                    logger.info("Stale lock force-released successfully")
                    # Retry opening the session
                    QTimer.singleShot(
                        100,
                        lambda: self.start_session(
                            file_path=file_path, restore_dir=restore_dir
                        ),
                    )
                else:
                    logger.error("Failed to force-release lock")
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to release the lock. Please try again or contact support.",
                    )
            except Exception as e:
                logger.exception("Error force-releasing lock")
                QMessageBox.critical(self, "Error", f"Failed to release lock:\n\n{e}")
        else:
            logger.info("User cancelled force-release of stale lock")
