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
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.app_bridge import (
    packing_payload,
    session_payload,
    start_failure,
    statistics_payload,
)
from gui.app_pages import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS, AppPages
from gui.command_bar import PAGES, CommandBar
from gui.components.connection_banner import ConnectionBanner
from gui.components.sidebar import Sidebar
from gui.packer_bridge import order_label, session_end_payload
from gui.packer_mode_widget import PackerModeWidget
from gui.sessions_page import SessionsPage
from gui.sessions_payload import session_key
from gui.sku_mapping_dialog import SKUMappingDialog
from gui.theme import apply_theme, current_tokens
from gui.worker_selection_dialog import WorkerSelectionDialog
from gui.workers import SessionEndWorker, SessionStartWorker
from packing_tool import APP_NAME, __version__
from packing_tool.profile_manager import NetworkError, ProfileManager
from packing_tool.progress_publisher import ProgressPublisher
from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_manager import SessionManager
from packing_tool.session_registry_manager import SessionRegistryManager
from packing_tool.worker_manager import WorkerManager
from shared.components.toast import toast
from shared.fonts import load_bundled_fonts
from shared.icons import icon
from shared.server_connection import (
    ConnectionSettingsDialog,
    prompt_for_recovery_path,
    test_path_reachable,
)
from shared.session_id import derive_session_id
from shared.stats_manager import StatsManager
from shared.theme import (
    theme_notifier,
    themed_tokens,
)
from shared.web_page import switch_theme, when_painted

logger = logging.getLogger(__name__)

# (icon name, sidebar label, tooltip) per destination, in sidebar order. The
# tooltip names the shortcut, as the mockup's does.
RAIL_ITEMS = (
    ("clipboard-list", "Packing", "Packing  Ctrl+1"),
    ("table", "Statistics", "Statistics  Ctrl+2"),
    ("folder-open", "Sessions", "Sessions  Ctrl+3"),
)

# How long a finished order stays on screen before Packer Mode resets.
ORDER_CLEAR_MS = 3000

DEFAULT_CONFIG_PATH = "config.ini"


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


def list_changes_text(changes: dict) -> str:
    """The toast for a packing list Shopify rewrote after packing started (AUDIT-01-3)."""
    parts = []
    if changes.get("packed_dropped"):
        parts.append(f"{changes['packed_dropped']} packed order(s) no longer on it")
    if changes.get("open_dropped"):
        parts.append(f"{changes['open_dropped']} started order(s) removed")
    if changes.get("quantities_changed"):
        parts.append(f"{changes['quantities_changed']} started order(s) with new quantities")
    return "The packing list changed since packing started: " + ", ".join(parts) + "."


def _local_stamp(iso) -> str:
    """An ISO timestamp as local "YYYY-MM-DD HH:MM:SS"; empty when missing or unreadable."""
    try:
        return datetime.fromisoformat(str(iso)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return ""


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
    """

    # A background heartbeat found another PC holding the lock (its work_dir)
    _heartbeat_lost = Signal(str)
    # Emitted from the connection-check thread; queued to the UI thread.
    _connection_checked = Signal(bool)

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
        self.setWindowTitle(f"{APP_NAME} {__version__}")

        from shared.theme import restore_window_geometry

        self._geometry_settings = QSettings("PackingTool", "MainWindowGeometry")
        if not restore_window_geometry(self, self._geometry_settings):
            self.resize(1366, 768)

        logger.info("Initializing MainWindow")

        # Detect if running in test mode
        self._is_test_mode = skip_worker_selection or "pytest" in sys.modules

        # Initialize ProfileManager, offering a path-recovery prompt on
        # NetworkError instead of exiting immediately.
        while True:
            try:
                self.profile_manager = ProfileManager(config_path)
                logger.info("ProfileManager initialized successfully")
                logger.info("%s %s", APP_NAME, __version__)
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
        # Heartbeat I/O and lock release never overlap: a renewal landing after
        # a release would recreate a lock nobody holds (AUDIT-02-8).
        self._lock_io = threading.Lock()
        self._heartbeat_busy = False
        self._last_start = None
        self._starting = False  # see start_shopify_packing_session()
        self._heartbeat_lost.connect(self._on_heartbeat_lost)
        # ok / checking / down (spec 2026-10-08 section 6.5). Checked on Retry
        # and after a failed session action, never on a timer (owner decision).
        self._connection_state = "ok"
        self._connection_was_down = False
        self._connection_down_since = ""
        self._connection_checked.connect(self._on_connection_checked)
        logger.info("SessionLockManager initialized successfully")

        # Initialize WorkerManager
        base_path = self.profile_manager.base_path
        self.worker_manager = WorkerManager(str(base_path))
        logger.info("WorkerManager initialized successfully")

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
        self._progress_publisher = None  # ProgressPublisher for the open Shopify session
        self._leaving_packer_mode = False  # see _leave_packer_mode()
        self._entering_packer_mode = False  # see switch_to_packer_mode()
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

        self.sidebar = Sidebar()
        shell.addWidget(self.sidebar)
        # Alias: the call sites and tests that drive the pages speak this name.
        self.nav_rail = self.sidebar.rail

        pages_side = QWidget()
        main_layout = QVBoxLayout(pages_side)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        shell.addWidget(pages_side, 1)

        # (no inline stylesheet — global QSS + QPalette handle all colors and fonts)

        # Designed for 1366x768 (ADR 0002). The minimum is under that because a
        # maximised window on such a screen loses the taskbar and title bar.
        self.setMinimumSize(1280, 680)

        self.command_bar = CommandBar()
        main_layout.addWidget(self.command_bar)

        # Aliases: ~40 call sites already speak these names.
        self.client_combo = self.command_bar.client_combo
        self.client_combo.currentIndexChanged.connect(self.on_client_changed)
        self.search_input = self.command_bar.filter_input
        self.search_input.textChanged.connect(self._filter_orders)

        self.packer_mode_button = self.command_bar.start_packing_button
        self.packer_mode_button.setEnabled(False)
        self.packer_mode_button.clicked.connect(self.switch_to_packer_mode)

        self.toolbar_end_btn = self.command_bar.end_session_button
        self.toolbar_end_btn.clicked.connect(self.end_session)

        self.command_bar.open_session_button.clicked.connect(self.open_session_browser)

        # Packing, Statistics, Sessions and Session details are one web
        # document (ADR 0003). AppPages speaks the QTabWidget calls the code
        # below already makes.
        self.session_tabs = AppPages()
        pages = self.session_tabs.bridge
        pages.openSessionRequested.connect(lambda: self.open_session_browser())
        pages.startPackingRequested.connect(lambda: self.switch_to_packer_mode())
        pages.endSessionRequested.connect(lambda: self.end_session())
        pages.clearFilterRequested.connect(lambda: self.search_input.clear())
        pages.chooseClientRequested.connect(lambda: self.client_combo.showPopup())
        pages.pageRequested.connect(self._show_named_page)
        pages.retryStartRequested.connect(lambda: self._retry_start())
        pages.closeFailureRequested.connect(lambda: self._close_failure())

        # The Sessions pages' controller: the registry refresh, the take-over
        # question and the exports. Lambdas, so a test (or a subclass) that
        # replaces a handler is seen. on_client_changed gives it its client.
        self.sessions = SessionsPage(
            pages,
            self.registry_manager,
            self.lock_manager,
            window=self,
            is_showing=lambda: (
                self._shell_showing()
                and self.session_tabs.currentIndex() == PAGE_BROWSER
            ),
            client_label=lambda: self.client_combo.currentText(),
            toast=lambda message: self._toast(message),
            parent=self,
        )
        self.sessions.startRequested.connect(
            lambda info: self._handle_start_packing_from_browser(info)
        )
        self.sessions.resumeRequested.connect(
            lambda info: self._handle_resume_session_from_browser(info)
        )
        self.sessions.showPackingRequested.connect(
            lambda: self.session_tabs.setCurrentIndex(PAGE_PACKING)
        )

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
        self.session_tabs.currentChanged.connect(lambda index: self._on_page_changed(index))

        # The rail's stylesheet follows the theme on its own, but its icons are
        # rasterised at the colour in force when they were built.
        theme_notifier.changed.connect(self._refresh_rail_icons)
        # Lambdas, so a test (or a subclass) that replaces the handler is seen.
        self.sidebar.skuMappingRequested.connect(lambda: self.open_sku_mapping_dialog())
        self.sidebar.switchWorkerRequested.connect(lambda: self._select_worker())
        self.sidebar.themeRequested.connect(lambda name: self._switch_theme(name))
        self.sidebar.set_worker(self.current_worker_name or "")
        self.command_bar.sidebarToggled.connect(self._toggle_sidebar)
        self._shell_settings = QSettings("PackingTool", "Shell")
        self._set_sidebar_expanded(
            self._shell_settings.value("sidebar_expanded", True, type=bool)
        )

        # Frame 2e. Inset like the page content it sits above. The margins are
        # on a container, so hiding it leaves no gap above the page.
        self.connection_banner = ConnectionBanner()
        self.connection_banner.retryRequested.connect(self.check_connection)
        self._banner_row = QWidget()
        banner_layout = QVBoxLayout(self._banner_row)
        banner_layout.setContentsMargins(24, 20, 24, 0)
        banner_layout.addWidget(self.connection_banner)
        main_layout.addWidget(self._banner_row)

        main_layout.addWidget(self.session_tabs, 1)

        self.packer_mode_widget = PackerModeWidget(sim_mode=self._sim_mode)
        self.packer_mode_widget.barcode_scanned.connect(self.on_scanner_input)
        self.packer_mode_widget.manual_confirm_requested.connect(
            lambda sku: self.on_scanner_input(sku, "manual")
        )
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
        self.sidebar.retryRequested.connect(self.check_connection)
        self._set_connection_state("ok")

    def _refresh_rail_icons(self, _theme_name=None):
        """Re-render the rail's glyphs at the new theme's text colour."""
        for index, (icon_name, _label, _tip) in enumerate(RAIL_ITEMS):
            self.nav_rail.button(index).setIcon(icon(icon_name))

    def _toggle_sidebar(self):
        expanded = not self.sidebar.is_expanded()
        self._set_sidebar_expanded(expanded)
        self._shell_settings.setValue("sidebar_expanded", expanded)

    def _set_sidebar_expanded(self, expanded: bool):
        self.sidebar.set_expanded(expanded)
        self.command_bar.set_sidebar_expanded(expanded)

    def _show_named_page(self, name: str):
        """The document asks for a page by the name the bridge uses."""
        index = {"packing": PAGE_PACKING, "statistics": PAGE_STATISTICS}.get(name)
        if index is not None:
            self.session_tabs.setCurrentIndex(index)

    def _on_page_changed(self, index: int):
        if index == PAGE_BROWSER:
            # What Sessions shows should be now, not when it was last looked at.
            self.sessions.page_shown()

    def _switch_theme(self, name: str):
        """Light or Dark, from the sidebar's segment or its collapsed toggle.

        Through switch_theme, so the Qt chrome turns over with the visible web
        page instead of a frame ahead of it.
        """
        switch_theme(
            name,
            current_name=lambda: current_tokens().name,
            tokens_for=lambda theme: themed_tokens(theme, load_bundled_fonts()),
            set_theme=lambda theme: apply_theme(QApplication.instance(), theme),
        )

    def _init_overflow(self):
        """What is left behind the bar's ⋯ once the sidebar footer has the
        worker, SKU mapping and the theme (spec 2026-10-08 section 6.3)."""
        menu = self.command_bar.overflow
        menu.add_item("Server connection…", self._open_connection_settings)
        menu.addSeparator()
        exit_item = menu.add_item("Exit", self.close)
        # Shown beside the label, as the mockup draws it. The OS closes the
        # window on Alt+F4 either way.
        exit_item.setShortcut(QKeySequence("Alt+F4"))
        exit_item.setShortcutVisibleInContextMenu(True)

        # Through click(), which is a no-op on the disabled no-session button.
        end_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        end_shortcut.activated.connect(lambda: self.toolbar_end_btn.click())

        for page, _item in enumerate(RAIL_ITEMS):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{page + 1}"), self)
            shortcut.activated.connect(lambda p=page: self._go_to_page(p))

    def _go_to_page(self, page: int):
        """Ctrl+1/2/3. Nothing to go to until a client is chosen, and not
        from Packer Mode: the page behind it would change unseen."""
        in_shell = self.stacked_widget.currentWidget() is self.session_widget
        if self.current_client_id and in_shell:
            self.session_tabs.setCurrentIndex(page)

    def _filter_orders(self, text: str):
        """The bar's Filter orders field: the document redraws the index."""
        if self.logic is not None:
            self.session_tabs.bridge.set_packing(
                packing_payload(
                    self.logic.orders_data, self.logic.session_packing_state, text
                )
            )

    def _shell_showing(self) -> bool:
        return self.stacked_widget.currentWidget() is self.session_widget

    def _push_pages(self):
        """Send the document what Packing and Statistics show now.

        With no list open it empties both pages and leaves `session` alone:
        whoever closed, failed or is opening the session has said which.
        """
        bridge = self.session_tabs.bridge
        logic = self.logic
        if logic is None:
            bridge.set_packing({})
            bridge.set_statistics({})
            self.command_bar.set_complete(False)
            self._sync_sessions_context()
            return

        state = logic.session_packing_state
        packing = packing_payload(logic.orders_data, state, self.search_input.text())
        statistics = statistics_payload(getattr(logic, "processed_df", None), state)
        complete = packing["totals"]["complete"]
        bridge.set_session(
            session_payload(
                "open",
                list_name=self.current_packing_list or "",
                session_id=(
                    Path(self.current_session_path).name
                    if self.current_session_path
                    else ""
                ),
                orders=packing["totals"]["orders"],
                couriers=[courier["name"] for courier in statistics["couriers"]],
                complete=complete,
            )
        )
        bridge.set_packing(packing)
        bridge.set_statistics(statistics)
        self.command_bar.set_complete(complete)
        # Frame 3g: with every order packed there is nothing left to scan.
        self.packer_mode_button.setEnabled(not complete)
        self._sync_sessions_context()

    def _refresh_pages(self):
        """Push now if the shell is on screen; leaving Packer Mode pushes.

        A push is every order and line; during packing the pages sit under
        Packer Mode where nobody is looking (AUDIT-02-7).
        """
        if self._shell_showing():
            self._push_pages()

    def _toast(self, message: str, role: str = "success"):
        """A toast where it can be seen: a Qt child cannot paint over a web
        view, so the app document draws its own while it is on screen."""
        pages = self.session_tabs
        if pages.view.isVisible():
            pages.bridge.raise_toast(message)
        else:
            toast(self, message, role=role)

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
                    if hasattr(self, "sidebar"):
                        self.sidebar.set_worker(self.current_worker_name)
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

            # The remembered client; failing that the only one; failing that
            # none, and the packer chooses (spec 2026-10-08 section 6.6).
            last_client = self.settings.value("last_client")
            index = self.client_combo.findData(last_client) if last_client else -1
            if index < 0 and len(clients) == 1:
                index = 0
            self.client_combo.setCurrentIndex(index)
            logger.info(f"Client at startup: {self.client_combo.currentData()}")

            logger.info(f"Loaded {len(clients)} clients")

        except Exception as e:
            logger.exception("Error loading clients")
            QMessageBox.warning(self, "Error", f"Failed to load clients:\n\n{e}")

        finally:
            self.client_combo.blockSignals(False)
            self._sync_client_state()

        # Trigger selection if there's a valid item
        if self.client_combo.currentData():
            self.on_client_changed(self.client_combo.currentIndex())

    def _sync_client_state(self):
        """Enable or disable what needs a client (spec 2026-10-08 section 6.6)."""
        chosen = bool(self.current_client_id)
        self.sidebar.set_client_chosen(chosen)
        self.command_bar.set_client_chosen(chosen)
        if not chosen:
            # Every page draws "Choose a client"; Packing is the one to be on.
            self.session_tabs.setCurrentIndex(PAGE_PACKING)
        self._sync_shell()

    def _sync_shell(self):
        self.session_tabs.bridge.set_shell(
            client=bool(self.current_client_id),
            # With none, the selector's one item is "(No clients available)",
            # whose data is None. Not isEnabled(): an open session disables it.
            clients=self.client_combo.itemData(0) is not None,
            server_down=self._connection_state == "down",
        )
        self._sync_sessions_context()

    def _sync_sessions_context(self):
        """Tell Sessions which session is open on this PC and whether the
        server answers: both decide what a row's action is (section 5.5)."""
        open_key = ""
        if self.logic is not None and self.current_session_path:
            open_key = session_key({
                "session_id": Path(self.current_session_path).name,
                "packing_list_name": self.current_packing_list or "",
            })
        self.sessions.set_context(open_key, self._connection_state == "down")

    def on_client_changed(self, index: int):
        """
        Handle client selection change.

        Args:
            index: Index of selected item in combo box
        """
        client_id = self.client_combo.currentData()

        if self.logic is not None and client_id != self.current_client_id:
            # A list is open: its stats, registry entry and SKU mappings belong
            # to its client, so the picker holds still until it ends (AUDIT-02-6).
            self.client_combo.blockSignals(True)
            self.client_combo.setCurrentIndex(
                self.client_combo.findData(self.current_client_id)
            )
            self.client_combo.blockSignals(False)
            return

        if not client_id:
            logger.debug("No valid client selected")
            self.current_client_id = None
            self._sync_client_state()
            return

        logger.info(f"Client changed to: {client_id}")

        self.current_client_id = client_id
        self._close_failure()

        # Save as last selected client
        self.settings.setValue("last_client", client_id)

        logger.debug(f"Current client set to: {client_id}")

        # Sessions has no picker of its own (Bundle 6): the command bar's is
        # the only one, so it has to push the change.
        self.sessions.load_client(client_id)
        self._sync_client_state()

    def flash_border(self, color: str):
        """Flash the order document's edge with the scan's outcome.

        Args:
            color (str): "green", "red" or "orange". Anything else raises --
                a silently-passed-through value would emit a role no CSS rule
                matches, and would sail past style_lint.
        """
        self.packer_mode_widget.flash_scan(color)

    def check_connection(self):
        """Ask the server once, off the UI thread (a dead share can block for
        the whole timeout). One check at a time."""
        if self._connection_state == "checking":
            return
        self._connection_was_down = self._connection_state == "down"
        self._set_connection_state("checking")
        path = str(self.profile_manager.base_path)
        timeout = self.profile_manager.connection_timeout

        def run():
            reachable = test_path_reachable(path, timeout)
            try:
                self._connection_checked.emit(reachable)
            except RuntimeError:
                pass  # the window closed while the check ran

        threading.Thread(target=run, name="connection-check", daemon=True).start()

    def _on_connection_checked(self, reachable: bool):
        if reachable:
            self._set_connection_state("ok")
            if self._connection_was_down:
                self._toast(f"Server connected again · {self.profile_manager.base_path}")
            return
        if not self._connection_was_down:
            # The time we found out; when the server stopped is not knowable.
            self._connection_down_since = datetime.now().astimezone().strftime("%H:%M")
        self._set_connection_state("down")

    def _set_connection_state(self, state: str):
        self._connection_state = state
        path = str(self.profile_manager.base_path)
        down = state == "down"
        self.sidebar.set_connection(state, path)
        if down:
            self.connection_banner.set_outage(path, self._connection_down_since)
        # Both: the tests and the render read the banner, the layout reads the row.
        self.connection_banner.setVisible(down)
        self._banner_row.setVisible(down)
        self.command_bar.set_server_reachable(not down)
        self._sync_shell()

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
                    self._toast("SKU mapping saved and shared with every PC.")
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
        self.heartbeat_timer.timeout.connect(self._heartbeat_tick)
        self.heartbeat_timer.start(60000)  # 60 seconds
        logger.debug("Heartbeat timer started")

    def _heartbeat_tick(self):
        """The timer's heartbeat, off the UI thread.

        On an unreachable share a renewal can block for many seconds; on the UI
        thread that froze the packing screen with it (AUDIT-02-8).
        """
        if self._heartbeat_busy or not (self.logic and getattr(self, "current_work_dir", None)):
            return
        work_dir = Path(self.current_work_dir)
        self._heartbeat_busy = True

        def run():
            try:
                if self._renew_lock(work_dir):
                    self._heartbeat_lost.emit(str(work_dir))  # queued to the UI thread
            finally:
                self._heartbeat_busy = False

        threading.Thread(target=run, name="heartbeat", daemon=True).start()

    def _on_heartbeat_lost(self, work_dir: str):
        current = getattr(self, "current_work_dir", None)
        if self.logic and current and Path(current) == Path(work_dir):
            self._on_lock_lost(Path(work_dir))

    def _renew_lock(self, work_dir: Path) -> bool:
        """Renew the session lock. True when another PC has taken it (spec B3)."""
        try:
            with self._lock_io:
                if self.lock_manager.update_heartbeat(work_dir):
                    logger.debug("Lock heartbeat updated")
                    return False
                return self.lock_manager.owns_lock(work_dir) is False
        except Exception:
            logger.exception("Failed to update heartbeat")
            return False

    def _on_lock_lost(self, work_dir: Path):
        """Another PC holds this list's lock: stop writing, then leave it.

        In Packer Mode the page says so and blocks (frame 6j), and the session
        is torn down when the packer exits. On any other page: teardown, then
        a message box, as before.
        """
        _locked, info = self.lock_manager.is_locked(work_dir)
        holder = (info or {}).get("locked_by") or "Another PC"
        list_name = getattr(self, "current_packing_list", None) or work_dir.name
        logger.error(f"Session lock lost to {holder}: {work_dir}")
        self.logic.stop_writing()
        if self._progress_publisher is not None:
            self._progress_publisher.stop()
        widget = self.packer_mode_widget
        # Not while it is leaving: the panel would paint on a page about to be
        # covered, and the packer would land on a dead session with no word.
        if self.stacked_widget.currentWidget() is widget and not self._leaving_packer_mode:
            # The lock is gone and stays gone: nothing left to renew, and a
            # second report must not land on the panel.
            if hasattr(self, "heartbeat_timer"):
                self.heartbeat_timer.stop()
            self.packer_mode_widget.show_takeover(holder, list_name)
            return
        self._teardown_session()
        QMessageBox.critical(
            self,
            "This list is open on another PC",
            f"{holder} has taken over {list_name}. This PC has stopped packing it "
            "so the two don't overwrite each other's progress. Orders packed here "
            "up to now are saved.",
        )

    def _on_start_step(self, step: int):
        """Frame 3b: the worker says which step it is on.

        The signal is queued from the worker's thread, so it can arrive after
        the start has already ended. Only an opening session takes a step.
        """
        bridge = self.session_tabs.bridge
        session = bridge.session
        if session.get("state") == "opening":
            bridge.set_session(
                session_payload(
                    "opening",
                    list_name=session.get("list", ""),
                    session_id=session.get("id", ""),
                    step=step,
                )
            )

    def _show_start_failure(self, title: str, text: str, list_name: str):
        """Frame 3c: a session that did not open says why, on the Packing page."""
        self.session_tabs.bridge.set_session(
            session_payload("failed", list_name=list_name, title=title, text=text)
        )
        self._push_pages()
        self.session_tabs.setCurrentIndex(PAGE_PACKING)

    def _retry_start(self):
        if self._last_start is not None:
            self._start_or_resume_from_browser(**self._last_start)

    def _close_failure(self):
        if self.session_tabs.bridge.session.get("state") == "failed":
            self.session_tabs.bridge.set_session(session_payload())

    def _cleanup_failed_session_start(self):
        """
        Clean up resources after failed session start.
        Extracted to avoid code duplication in exception handlers.
        """
        self._close_progress_publisher()

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
                with self._lock_io:
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

        # A failed start may be the server going away: find out, so the
        # sidebar and the banner say so (spec 2026-10-08 section 6.5).
        self.check_connection()

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
        if self._starting:
            # The start worker is still running; closing now would leave its
            # thread and the lock behind. The start ends in seconds.
            event.ignore()
            return
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
                try:
                    self._close_progress_publisher()  # flush the last packed orders to the registry
                except Exception as e:
                    logger.warning(f"Failed to publish packing progress: {e}")

            # 3. Release lock on current work directory
            if hasattr(self, "current_work_dir") and self.current_work_dir:
                try:
                    with self._lock_io:
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

            # 5. Stop the Sessions timer and let its workers end
            try:
                self.sessions.shutdown()
            except Exception as e:
                logger.warning(f"Failed to stop the Sessions page: {e}")

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
        take_over: dict | None = None,
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
            take_over: The stale lock the packer agreed to take over (frame 7c), or None

        Returns:
            bool: True if session started successfully, False otherwise
        """
        # The start spins the event loop while its worker runs, and nothing
        # modal is up any more: a second start must not get in under it.
        if self._starting:
            return False
        self._starting = True
        try:
            logger.info(f"Starting Shopify packing session: {packing_list_path}")
            logger.info(f"Work directory: {work_dir}")
            logger.info(f"Session path: {session_path}")

            pages = self.session_tabs.bridge
            pages.set_session(
                session_payload(
                    "opening",
                    list_name=packing_list_name,
                    session_id=session_path.name,
                    step=1,
                )
            )
            # The lock is taken on this thread: let the page hear about step 1.
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

            # 1. Validate packing list file exists
            if not packing_list_path.exists():
                raise FileNotFoundError(f"Packing list not found: {packing_list_path}")

            # 2. Store session state
            self.current_session_path = str(session_path)
            self.current_packing_list = packing_list_name
            self.current_work_dir = str(work_dir)

            # 3. Acquire the lock on the work directory
            success, error_msg, taken_from = self._acquire_lock(
                client_id, work_dir, take_over
            )
            if not success:
                raise RuntimeError(error_msg)

            logger.info(f"Lock acquired on {work_dir}")

            # 4. Start heartbeat timer
            self._start_heartbeat_timer()
            logger.info("Heartbeat timer started")

            # 5 & 7. Initialize PackerLogic + load packing list in background thread
            # so the UI stays responsive and the page names the step it is on (frame 3b).
            start_worker = SessionStartWorker(
                client_id=client_id,
                profile_manager=self.profile_manager,
                work_dir=work_dir,
                packing_list_path=packing_list_path,
                parent=self,
            )
            start_worker.step.connect(self._on_start_step)
            start_worker.start()
            # No clicks or keys until the session is open or has failed: the
            # bar, the rail and the client selector are all live under 3b.
            while not start_worker.wait(50):
                QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

            if start_worker.error is not None:
                raise start_worker.error

            self.logic = start_worker.logic
            order_count = start_worker.order_count
            list_name = start_worker.list_name

            # 6. Connect signals (must happen on main thread after moveToThread)
            self.logic.item_packed.connect(self._on_item_packed)
            self.logic.all_orders_complete.connect(self._on_all_orders_complete)
            self.logic.save_failed.connect(self.packer_mode_widget.set_unsaved)

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
                    completed_orders=len(
                        self.logic.session_packing_state.get("completed_orders", [])
                    ),
                    skipped_orders=len(
                        self.logic.session_packing_state.get("skipped_orders", [])
                    ),
                )
            except Exception as _e:
                logger.warning(f"Registry update (session start) failed: {_e}")

            self._progress_publisher = ProgressPublisher(
                self.session_manager,
                getattr(self, "registry_manager", None),
                client_id,
                str(session_path),
                packing_list_name,
            )

            # 10. A clean Packer Mode document; enable_packing_mode pushes the pages
            self._open_packer_document()

            # 11. Update UI state
            if taken_from:
                self._toast(f"Took over {session_path.name} from {taken_from}.")
            else:
                self._toast(f"Loaded {order_count} orders from {packing_list_name}.")
            if self.logic.list_changes:
                self._toast(list_changes_text(self.logic.list_changes), role="info")

            # 12. Enable packing UI
            self.enable_packing_mode()

            logger.info("Shopify packing session started successfully")
            return True

        except Exception as e:
            # Every failed start is frame 3c, with its own sentence
            # (gui.app_bridge.start_failure); no message box.
            logger.exception("Session start failed")
            self._cleanup_failed_session_start()
            title, text = start_failure(e, packing_list_name)
            self._show_start_failure(title, text, packing_list_name)
            return False
        finally:
            self._starting = False

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

            # Add Completed At column: when each order was packed (AUDIT-01-5)
            packed_at = {
                o["order_number"]: _local_stamp(o.get("completed_at"))
                for o in self.logic.completed_orders_metadata
            }
            final_df["Completed At"] = final_df["Order_Number"].apply(
                lambda x: packed_at.get(x, "") if x in completed_orders_set else ""
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

            self._toast(f"Session ended. Report saved to {output_path}")

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
                # Stats get what this run added: a list ended, resumed and ended
                # again must not be counted twice (AUDIT-01-2).
                _start_time = self.logic.run_started_at
                _end_time = datetime.now().astimezone()
                _packed_orders = self.logic.packed_order_numbers()
                _new_orders = [
                    o for o in _packed_orders if o not in self.logic.stats_recorded_orders
                ]
                _completed_orders = len(_new_orders)
                _in_progress_orders = len(
                    self.logic.session_packing_state.get("in_progress", {})
                )
                _items_packed = sum(
                    o.get("items_count", 0)
                    for o in self.logic.completed_orders_metadata
                    if o["order_number"] in _new_orders
                )

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

                _duration_seconds = int((_end_time - _start_time).total_seconds())
                _stats_recorded = threading.Event()

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
                # Close the progress publisher first: its last "in_progress"
                # write must land before _do_slow_writes' final "completed".
                self._close_progress_publisher()
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
                                "started_at": _start_time.isoformat(),
                                "completed_at": _end_time.isoformat(),
                                "total_orders": _total_orders,
                                "in_progress_orders": _in_progress_orders,
                                "session_type": _session_type,
                                "user_name": os.environ.get("USERNAME", "Unknown"),
                                "worker_name": _worker_name,
                                "pc_name": os.environ.get("COMPUTERNAME", "Unknown"),
                            },
                        )
                        _stats_recorded.set()
                        logger.info(
                            f"Recorded {_completed_orders} orders, {_items_packed} items to stats"
                        )
                    except Exception:
                        logger.exception("record_packing failed")

                    # 3. Update worker stats. Only after the global stats took
                    # these orders: stats_recorded_orders follows record_packing,
                    # so a worker write without it would be repeated next End.
                    try:
                        if _worker_id and _stats_recorded.is_set():
                            _worker_mgr.update_worker_stats(
                                worker_id=_worker_id,
                                sessions=1,
                                orders=_completed_orders,
                                items=_items_packed,
                                duration_seconds=_duration_seconds,
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
                                completed_orders=_packed_orders,
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
                if _stats_recorded.is_set():
                    _logic_ref.stats_recorded_orders = _packed_orders
                    _logic_ref.save_state()

        except Exception as e:
            # Neutral title: this can fire after the report was already saved.
            QMessageBox.critical(
                self,
                "Session end failed",
                f"Could not finish ending the session:\n\n{e}",
            )
            logger.exception("Error during end_session")
            self.check_connection()

        self._teardown_session()

    def _teardown_session(self):
        """Stop the heartbeat, release the lock, drop the logic and return the UI to the session view.

        The tail of end_session(), and the whole of leaving a session whose lock was lost.
        """
        self._close_progress_publisher()  # idempotent: end_session() already closed it

        # CRITICAL: Stop heartbeat timer and release lock
        if hasattr(self, "heartbeat_timer"):
            self.heartbeat_timer.stop()
            logger.debug("Heartbeat timer stopped")

        if hasattr(self, "current_work_dir") and self.current_work_dir:
            try:
                with self._lock_io:
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
        self.client_combo.setEnabled(True)

        self._show_session(None)

        # Pushed even under Packer Mode: nothing of an ended session stays in
        # the document.
        self.session_tabs.bridge.set_session(session_payload())
        self._push_pages()

        if self.packer_mode_widget:
            self.packer_mode_widget.reset_for_new_session()

        # Return user to session view (avoids leaving a blank packer mode screen)
        if hasattr(self, "stacked_widget") and hasattr(self, "session_widget"):
            self._leave_packer_mode()

        logger.info("Session ended and all variables cleared")

    def _open_packer_document(self):
        """Give Packer Mode a clean document for the session just loaded.

        Runs at session start, so a session always opens clean however the
        last one ended. A resumed list opens on its real count.
        """
        state = self.logic.session_packing_state
        self.packer_mode_widget.reset_for_new_session()
        self.packer_mode_widget.update_session_progress(
            len(state.get("completed_orders", [])), len(self.logic.orders_data)
        )

    def switch_to_packer_mode(self):
        """Enter Packer Mode once the app document has painted itself empty.

        A hidden QWebEngineView keeps its last frame and shows it when it
        comes back. So the frame it keeps is the covered one, never orders
        that may be gone by then (ADR 0003): the document is told to draw
        nothing, and this waits for that paint, 150 ms at most.
        """
        if self._entering_packer_mode:
            return
        pages = self.session_tabs

        def enter():
            self._entering_packer_mode = False
            self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
            self.packer_mode_widget.resume_scanner()
            self.packer_mode_widget.set_focus_to_scanner()

        if pages.view.isVisible():
            self._entering_packer_mode = True
            pages.bridge.set_covered(True)
            when_painted(pages.bridge, enter)
        else:
            enter()

    def switch_to_session_view(self):
        """Switches the view back to the main session widget (tabbed interface)."""
        if self.packer_mode_widget.taken_over:
            # Another PC holds the list (frame 6j): there is no session left
            # here to come back to.
            self._teardown_session()
            return
        if self.logic:
            self.logic.clear_current_order()
        self.packer_mode_widget.clear_screen()
        self._leave_packer_mode()

    def _leave_packer_mode(self):
        """Leave Packer Mode once its page has painted what it was last sent.

        A hidden QWebEngineView keeps its last painted frame and shows it when
        it comes back, until a new one is ready. So the frame it keeps must be
        the cleared one: callers clear the page first, and this waits for the
        page's report (150 ms at most). The scanner is paused meanwhile, so a
        scan cannot open an order on a page about to be covered;
        switch_to_packer_mode gives it back.
        """
        widget = self.packer_mode_widget

        def switch():
            self._leaving_packer_mode = False
            # Before the shell shows: what it shows is current (spec section 8).
            self._push_pages()
            self.session_tabs.bridge.set_covered(False)
            self.stacked_widget.setCurrentWidget(self.session_widget)

        if self.stacked_widget.currentWidget() is widget and widget.isVisible():
            self._leaving_packer_mode = True
            widget.pause_scanner()
            when_painted(widget.bridge, switch)
        else:
            switch()

    def on_scanner_input(self, text: str, confirmation_method: str = "scanned"):
        """
        Handles input from the barcode scanner in Packer Mode.

        This is the central callback for all barcode scans. It determines if
        the scan is for an order or a product SKU and routes the logic accordingly.

        Args:
            text (str): The decoded text from the barcode scanner.
            confirmation_method: "manual" when the row's Confirm button sent it.
        """
        self.packer_mode_widget.update_raw_scan_display(text)
        self.packer_mode_widget.show_notification("", "transparent")

        if self.logic.current_order_number is None:
            items, status = self.logic.start_order_packing(text)
            if status == "ORDER_LOADED":
                order_number_from_scan = self.logic.current_order_number
                order_metadata = self.logic.orders_data.get(
                    order_number_from_scan, {}
                ).get("metadata", {})
                self.packer_mode_widget.display_order(
                    items,
                    self.logic.current_order_state,
                    metadata=order_metadata,
                    sku_map=self.logic.sku_map,
                )
                count = len(items)
                self.packer_mode_widget.show_notification(
                    f"Order {order_label(order_number_from_scan)} · {count} "
                    f"{'item' if count == 1 else 'items'}",
                    "status_info",
                )
                completed = len(
                    self.logic.session_packing_state.get("completed_orders", [])
                )
                self.packer_mode_widget.update_session_progress(
                    completed, len(self.logic.orders_data)
                )
                self._refresh_pages()
                _beep(1000, 120)
            elif status == "ORDER_ALREADY_COMPLETED":
                self.packer_mode_widget.show_notification(
                    f"Order {text} is already packed", "status_warning"
                )
                self.flash_border("orange")
            else:
                self.packer_mode_widget.show_notification(
                    f"No order matches {text}", "status_danger"
                )
                self.flash_border("red")
                _beep(400, 350)
        else:
            result, status = self.logic.process_sku_scan(text, confirmation_method)
            if status == "ORDER_BARCODE":
                self.packer_mode_widget.show_notification(
                    f"{text} is an order. Finish or skip "
                    f"{self.logic.current_order_number} first.",
                    "status_warning",
                )
                self.flash_border("orange")
                _beep(700, 200)
            elif status == "SKU_OK":
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
        It refreshes the pages to reflect the updated progress.

        Args:
            order_number (str): The order number that was updated.
            packed_count (int): The new total of items packed for the order.
            required_count (int): The total items required for the order.
        """
        self._refresh_pages()
        logger.debug(f"Order {order_number} progress: {packed_count}/{required_count}")

    def _handle_order_completion(self, order_number: str):
        """Shared teardown for every order-complete path (scan, force confirm, extra resolve)."""
        self.packer_mode_widget.add_order_to_history(order_number)
        self.packer_mode_widget.show_notification(
            f"Order #{order_number} packed. Scan the next order.", "status_success"
        )
        self.flash_border("green")
        _beep(1200, 80)
        QTimer.singleShot(180, lambda: _beep(1200, 80))
        self._refresh_pages()
        if self.logic:
            completed = len(
                self.logic.session_packing_state.get("completed_orders", [])
            )
            self.packer_mode_widget.update_session_progress(
                completed, len(self.logic.orders_data)
            )
        self.packer_mode_widget.clear_screen_later(ORDER_CLEAR_MS)
        self._publish_progress()

    def _publish_progress(self):
        """Hand the session's packed and skipped orders to the publisher."""
        if self._progress_publisher is None or not self.logic:
            return
        state = self.logic.session_packing_state
        self._progress_publisher.publish(
            self.logic.packed_order_numbers(),
            len(state.get("skipped_orders", [])),
            len(state.get("completed_orders", [])),  # off-list orders are out of the count
        )

    def _close_progress_publisher(self):
        if self._progress_publisher is not None:
            self._progress_publisher.close()
            self._progress_publisher = None

    def _on_skip_order(self):
        """Skip the currently active order (preserves packing progress for later)."""
        if not self.logic or not self.logic.current_order_number:
            return
        skipped = self.logic.current_order_number
        self.logic.skip_order()
        self._publish_progress()
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

            # One entry onto the mapping as it is on the server now (AUDIT-02-3)
            mapping = self.profile_manager.update_sku_mapping(
                self.current_client_id, {barcode: sku}
            )

            if self.logic:
                self.logic.sku_map = {
                    self.logic._normalize_sku(k): v for k, v in mapping.items()
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
        - Shows the session in the command bar
        - Prepares UI for packing operations
        """
        logger.info("Enabling packing mode UI")

        self._push_pages()
        self.client_combo.setEnabled(False)  # AUDIT-02-6

        session_id = (
            Path(self.current_session_path).name
            if self.current_session_path
            else (self.current_packing_list or "")
        )
        self._show_session(session_id or None, self.current_packing_list or "")

        logger.info("Packing mode UI enabled successfully")

    def _show_session(self, session_id, packing_list=""):
        """The session's id in the bar, and its tooltip, set together."""
        self.command_bar.set_session(session_id)
        self.command_bar.session_label.setToolTip(packing_list if session_id else "")

    def open_session_browser(self):
        """Show the Sessions page.

        The one place that navigation happens: the command bar's Open session
        and the document's own button both come here.
        """
        logger.info("Showing the Sessions page")
        self.session_tabs.setCurrentIndex(PAGE_BROWSER)

    def _start_or_resume_from_browser(
        self,
        client_id,
        packing_list_name,
        session_path,
        packing_list_path,
        work_dir=None,
        take_over=None,
    ):
        """
        Shared logic for Sessions' "Resume session" and "Start packing".

        If work_dir is None, one is created via SessionManager.get_packing_work_dir()
        (the "start packing" case); otherwise the existing work_dir is reused (resume).
        take_over is the stale lock the packer agreed to take over, or None.
        """
        if self._starting:
            return
        if self._connection_state == "down":
            self._toast(
                "Server unreachable. Sessions cannot be opened until it answers.",
                role="info",
            )
            return

        # One list at a time. is_active() covers only the legacy Excel path;
        # an open Shopify list is self.logic (AUDIT-02-2). The row's action is
        # disabled while one is open, so this is for a start that still arrives.
        if self.logic is not None or (
            self.session_manager and self.session_manager.is_active()
        ):
            logger.warning(
                "Attempted to start/resume packing while a session is already active"
            )
            open_id = (
                Path(self.current_session_path).name
                if self.current_session_path
                else "A session"
            )
            self._toast(f"{open_id} is open. End it before opening another.", role="info")
            return

        self._last_start = {
            "client_id": client_id,
            "packing_list_name": packing_list_name,
            "session_path": session_path,
            "packing_list_path": packing_list_path,
            "work_dir": work_dir,
            "take_over": take_over,
        }

        # The work happens on the Packing page: that is where the opening
        # steps (3b), a failure (3c) and the open list are drawn.
        self.session_tabs.setCurrentIndex(PAGE_PACKING)

        # Set current client if different
        if self.current_client_id != client_id:
            for i in range(self.client_combo.count()):
                if self.client_combo.itemData(i) == client_id:
                    self.client_combo.setCurrentIndex(i)
                    break

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
            try:
                work_dir = self.session_manager.get_packing_work_dir(
                    session_path=str(session_path), packing_list_name=packing_list_name
                )
            except OSError as e:
                # The usual way a packer first meets an outage: the work
                # folder cannot be made on a share that has gone away.
                logger.exception("Could not create the packing work directory")
                self._show_start_failure(
                    "Session could not be opened",
                    f"The work folder for {packing_list_name} could not be made: {e}.",
                    packing_list_name,
                )
                self.check_connection()
                return
            logger.info(f"Work directory created: {work_dir}")

        # The start's own toast says what loaded; a failure is frame 3c.
        self.start_shopify_packing_session(
            packing_list_path=packing_list_path,
            work_dir=work_dir,
            session_path=session_path,
            client_id=client_id,
            packing_list_name=packing_list_name,
            take_over=take_over,
        )

    def _handle_resume_session_from_browser(self, session_info: dict):
        """
        Handle resume request from Session Browser.

        Args:
            session_info: Dict with session_path, client_id, packing_list_name, work_dir, session_id, take_over
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
            take_over=session_info.get("take_over"),
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
        )

    def _acquire_lock(self, client_id: str, work_dir: Path, take_over: dict | None = None):
        """
        Take the session lock; take over a stale one only when the packer agreed to.

        take_over is the stale lock frame 7c asked about. It is released only
        if it is still that lock and still stale (AUDIT-02-1): while the
        question was open its PC may have come back, or another PC taken it.

        Returns:
            (True, None, None) when the lock was free.
            (True, None, "<PC>") when it was taken over from that PC.
            (False, sentence, None) when it was refused; the sentence is frame 3c's.
        """

        def acquire():
            return self.lock_manager.acquire_lock(
                client_id,
                work_dir,
                worker_id=self.current_worker_id,
                worker_name=self.current_worker_name,
            )

        def stale(lock) -> bool:
            return bool(lock) and self.lock_manager.is_lock_stale(lock)

        success, error_msg, lock = acquire()
        taken_from = None
        if not success and take_over is not None and stale(lock):
            if self.lock_manager.force_release_lock(work_dir, expected=take_over):
                taken_from = take_over.get("locked_by") or "another PC"
            success, error_msg, lock = acquire()
        if success:
            return True, None, taken_from
        if stale(lock):
            # Nobody was asked about this lock: the list was behind, this is a
            # Retry of 3c, or the lock changed while the question was open.
            pc = lock.get("locked_by") or "Another PC"
            return (
                False,
                (
                    f"{pc} stopped responding while this list was open there. "
                    "Resume it from Sessions to take it over."
                ),
                None,
            )
        return False, error_msg, None
