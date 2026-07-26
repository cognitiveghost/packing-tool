"""
Session Selector Widget - Choose Shopify sessions to pack.

This module provides a UI widget for selecting Shopify Tool sessions
to load into Packing Tool. It displays available sessions with metadata
such as order count and allows filtering by date.

Integration with Shopify Tool (Phase 1.3.2):
- Scans Sessions/CLIENT_{ID}/ directories
- Looks for sessions with analysis/analysis_data.json
- Displays session info (date, orders count)
- Returns selected session path for loading
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QListWidget, QListWidgetItem, QPushButton, QDateEdit,
    QCheckBox, QMessageBox, QGroupBox, QApplication
)
from PySide6.QtGui import QPalette
from PySide6.QtCore import Qt, QDate, QThread, Signal

from logger import get_logger
from json_cache import get_cached_json
from session_registry_manager import SessionRegistryManager
from shared.metadata_utils import parse_timestamp

logger = get_logger(__name__)


class SessionScanWorker(QThread):
    """
    Background worker that scans session directories off the UI thread.

    Emits scan_complete with the raw session list when done, or scan_failed
    with an error message on failure.
    """

    scan_complete = Signal(list)   # list[dict]
    scan_failed = Signal(str)      # error message

    def __init__(self, scan_fn, client_id: str, parent=None):
        super().__init__(parent)
        self._scan_fn = scan_fn
        self._client_id = client_id

    def run(self) -> None:
        try:
            sessions = self._scan_fn(self._client_id)
            self.scan_complete.emit(sessions)
        except Exception as exc:
            logger.error(f"SessionScanWorker failed: {exc}", exc_info=True)
            self.scan_failed.emit(str(exc))


class SessionSelectorDialog(QDialog):
    """
    Dialog for selecting a Shopify session to load for packing.

    Displays:
    - Client selector dropdown
    - List of available Shopify sessions
    - Session metadata (date, orders count)
    - Date range filter

    Returns:
    - Selected session path (Path object)
    - Session metadata dictionary
    """

    def __init__(self, profile_manager, pre_selected_client=None, parent=None):
        """
        Initialize SessionSelectorDialog.

        Args:
            profile_manager: ProfileManager instance for accessing sessions
            pre_selected_client: Optional pre-selected client ID
                                If provided, client selector will be hidden
                                and sessions filtered to this client only
            parent: Parent widget
        """
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.pre_selected_client = pre_selected_client
        self.selected_session_path = None
        self.selected_session_data = None
        self.selected_packing_list_path = None  # NEW: Selected packing list JSON path
        self._all_sessions: Optional[List[Dict]] = None  # Cached raw session list
        self._scan_worker: Optional[SessionScanWorker] = None

        self.setWindowTitle("Select Shopify Session to Pack")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)  # Increased height for packing lists section

        self._init_ui()

        # If client pre-selected, apply pre-selection immediately
        if self.pre_selected_client:
            self._apply_pre_selection()
        else:
            self._load_clients()

        logger.info("SessionSelectorDialog initialized")

    def _init_ui(self):
        """Initialize user interface components."""
        layout = QVBoxLayout(self)

        # ====================================================================
        # CLIENT SELECTION
        # ====================================================================
        client_group = QGroupBox("Select Client")
        client_layout = QHBoxLayout(client_group)

        client_label = QLabel("Client:")
        client_layout.addWidget(client_label)

        self.client_combo = QComboBox()
        self.client_combo.setMinimumWidth(200)
        self.client_combo.currentIndexChanged.connect(self._on_client_changed)
        client_layout.addWidget(self.client_combo)

        client_layout.addStretch()
        layout.addWidget(client_group)

        # ====================================================================
        # FILTER OPTIONS
        # ====================================================================
        filter_group = QGroupBox("Filter Sessions")
        filter_layout = QHBoxLayout(filter_group)

        # Date range filter
        self.use_date_filter_checkbox = QCheckBox("Filter by date range:")
        self.use_date_filter_checkbox.stateChanged.connect(self._refresh_sessions)
        filter_layout.addWidget(self.use_date_filter_checkbox)

        filter_layout.addWidget(QLabel("From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.dateChanged.connect(self._refresh_sessions)
        filter_layout.addWidget(self.date_from)

        filter_layout.addWidget(QLabel("To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self._refresh_sessions)
        filter_layout.addWidget(self.date_to)

        # Show only sessions with Shopify data
        self.shopify_only_checkbox = QCheckBox("Shopify sessions only")
        self.shopify_only_checkbox.setChecked(True)
        self.shopify_only_checkbox.stateChanged.connect(self._refresh_sessions)
        filter_layout.addWidget(self.shopify_only_checkbox)

        filter_layout.addStretch()
        layout.addWidget(filter_group)

        # ====================================================================
        # SESSIONS LIST
        # ====================================================================
        sessions_group = QGroupBox("Available Sessions")
        sessions_layout = QVBoxLayout(sessions_group)

        self.sessions_list = QListWidget()
        self.sessions_list.itemDoubleClicked.connect(self._on_session_double_clicked)
        sessions_layout.addWidget(self.sessions_list)

        layout.addWidget(sessions_group)

        # ====================================================================
        # PACKING LISTS (NEW)
        # ====================================================================
        packing_lists_group = QGroupBox("Packing Lists (Optional)")
        packing_lists_layout = QVBoxLayout(packing_lists_group)

        packing_info = QLabel("Select a specific packing list to load only those orders, or load the entire session")
        packing_info.setWordWrap(True)
        packing_info.setStyleSheet("color: gray; font-style: italic;")
        packing_lists_layout.addWidget(packing_info)

        self.packing_lists_widget = QListWidget()
        self.packing_lists_widget.itemSelectionChanged.connect(self._on_packing_list_selected)
        self.packing_lists_widget.itemDoubleClicked.connect(self._on_packing_list_double_clicked)
        packing_lists_layout.addWidget(self.packing_lists_widget)

        layout.addWidget(packing_lists_group)

        # ====================================================================
        # SESSION INFO
        # ====================================================================
        info_group = QGroupBox("Selection Details")
        info_layout = QVBoxLayout(info_group)

        self.info_label = QLabel("Select a session to see details")
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)

        layout.addWidget(info_group)

        # ====================================================================
        # BUTTONS
        # ====================================================================
        button_layout = QHBoxLayout()

        self.load_button = QPushButton("Load Session")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self._on_load_clicked)
        button_layout.addWidget(self.load_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Connect selection change
        self.sessions_list.itemSelectionChanged.connect(self._on_session_selected)

    def _load_clients(self):
        """Load available clients from ProfileManager."""
        logger.info("Loading available clients")

        self.client_combo.blockSignals(True)
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
                    display_name = f"{config.get('client_name', client_id)} ({client_id})"
                else:
                    display_name = client_id

                self.client_combo.addItem(display_name, client_id)

            logger.info(f"Loaded {len(clients)} clients")

        except Exception as e:
            logger.error(f"Error loading clients: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load clients:\n\n{e}")

        finally:
            self.client_combo.blockSignals(False)

        # Trigger loading sessions for first client
        if self.client_combo.count() > 0 and self.client_combo.currentData():
            self._on_client_changed(0)

    def _apply_pre_selection(self):
        """
        Apply pre-selected client filter and hide client selector.

        Called when dialog is opened with a pre-selected client from main menu.
        Hides the client ComboBox and shows static label instead.
        """
        logger.info(f"Applying pre-selection for client: {self.pre_selected_client}")

        # Hide client selector ComboBox
        if hasattr(self, 'client_combo'):
            self.client_combo.setVisible(False)
            self.client_combo.setEnabled(False)

        # Create and show static label instead
        if not hasattr(self, 'client_label'):
            # Get client display name
            try:
                config = self.profile_manager.load_client_config(self.pre_selected_client)
                if config:
                    display_name = f"{config.get('client_name', self.pre_selected_client)} ({self.pre_selected_client})"
                else:
                    display_name = self.pre_selected_client
            except:
                display_name = self.pre_selected_client

            self.client_label = QLabel(f"Client: {display_name}")
            self.client_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #2E7D32;")

            # Insert into client group layout (before combo)
            client_group = self.client_combo.parent()
            if client_group:
                layout = client_group.layout()
                if layout:
                    # Insert at position 1 (after "Client:" label)
                    layout.insertWidget(1, self.client_label)

        self.client_label.setVisible(True)

        # Update window title
        self.setWindowTitle(f"Select Shopify Session - {self.pre_selected_client}")

        # Load sessions immediately for this client
        self._refresh_sessions_for_client(self.pre_selected_client)

        logger.info(f"Pre-selection applied successfully for client {self.pre_selected_client}")

    def _refresh_sessions_for_client(self, client_id: str):
        """
        Refresh sessions list for a specific client (non-blocking).

        Shows a loading placeholder immediately, then starts a background scan.
        When the scan completes _on_sessions_loaded() populates the list.
        """
        logger.info(f"Refreshing sessions for client {client_id}")

        # Reset cached session list so we force a fresh scan
        self._all_sessions = None

        self.sessions_list.clear()
        self.info_label.setText("Select a session to see details")
        self.load_button.setEnabled(False)

        # Show loading placeholder
        loading_item = QListWidgetItem("Loading sessions...")
        loading_item.setForeground(Qt.gray)
        loading_item.setFlags(loading_item.flags() & ~Qt.ItemIsSelectable)
        self.sessions_list.addItem(loading_item)

        # In test environments run the scan synchronously so tests that call
        # _refresh_sessions() and immediately inspect the list continue to work.
        import os
        if 'PYTEST_CURRENT_TEST' in os.environ:
            try:
                sessions = self._scan_shopify_sessions(client_id)
                self._on_sessions_loaded(sessions)
            except Exception as exc:
                self._on_scan_failed(str(exc))
            return

        # Stop any previous scan worker that might still be running
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.scan_complete.disconnect()
            self._scan_worker.scan_failed.disconnect()
            self._scan_worker.quit()
            self._scan_worker.wait(500)

        self._scan_worker = SessionScanWorker(self._scan_shopify_sessions, client_id, self)
        self._scan_worker.scan_complete.connect(self._on_sessions_loaded)
        self._scan_worker.scan_failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_sessions_loaded(self, sessions: List[Dict]):
        """Called on the UI thread when background session scan finishes."""
        self._all_sessions = sessions
        self._apply_filters_and_populate()

    def _on_scan_failed(self, error_msg: str):
        """Called on the UI thread when background session scan fails."""
        self.sessions_list.clear()
        error_item = QListWidgetItem(f"Error loading sessions: {error_msg}")
        error_item.setForeground(Qt.red)
        self.sessions_list.addItem(error_item)
        logger.error(f"Session scan failed: {error_msg}")

    def _apply_filters_and_populate(self):
        """Apply current filters to cached session list and populate the UI list."""
        if self._all_sessions is None:
            return

        sessions = list(self._all_sessions)

        # Apply filters
        if self.use_date_filter_checkbox.isChecked():
            sessions = self._filter_by_date(sessions)

        if self.shopify_only_checkbox.isChecked():
            sessions = [s for s in sessions if s.get('has_shopify_data', False)]

        logger.info(f"Found {len(sessions)} sessions after filtering")

        self.sessions_list.clear()

        for session in sessions:
            item = QListWidgetItem()

            session_name = session['name']
            orders_count = session.get('orders_count', 0)
            has_shopify = session.get('has_shopify_data', False)

            display_text = f"{session_name}"
            if has_shopify:
                display_text += f" - {orders_count} orders (Shopify)"
            else:
                display_text += " - No Shopify data"

            item.setText(display_text)
            item.setData(Qt.UserRole, session)

            if has_shopify:
                item.setForeground(Qt.darkGreen)
            else:
                item.setForeground(Qt.gray)

            self.sessions_list.addItem(item)

        if len(sessions) == 0:
            info_item = QListWidgetItem("No sessions found for this client")
            info_item.setForeground(Qt.gray)
            self.sessions_list.addItem(info_item)

    def _on_client_changed(self, index: int):
        """Handle client selection change."""
        client_id = self.client_combo.currentData()

        if not client_id:
            logger.debug("No valid client selected")
            return

        logger.info(f"Client changed to: {client_id}")
        # Client changed — invalidate cached session list so next refresh re-scans
        self._all_sessions = None
        self._refresh_sessions()

    def _refresh_sessions(self):
        """Refresh sessions list for current client with filters.

        If a cached session list exists (from a previous scan), only re-applies
        filters without hitting the file server again.  A full rescan is triggered
        only when the client changes or when no cache is available.
        """
        if self.pre_selected_client:
            client_id = self.pre_selected_client
        else:
            client_id = self.client_combo.currentData()

        if not client_id:
            return

        if self._all_sessions is not None:
            # We already have data — just re-apply filters (instant, no I/O)
            self._apply_filters_and_populate()
        else:
            # No cached data yet — trigger a full background scan
            self._refresh_sessions_for_client(client_id)

    def _scan_shopify_sessions(self, client_id: str) -> List[Dict]:
        """
        Scan for Shopify sessions in Sessions/CLIENT_{ID}/ directory.

        A Shopify session is identified by:
        - Has analysis/analysis_data.json file
        - Created by Shopify Tool

        Args:
            client_id: Client identifier

        Returns:
            List of session dictionaries with metadata
        """
        sessions_dir = self.profile_manager.get_sessions_root() / f"CLIENT_{client_id}"

        if not sessions_dir.exists():
            logger.debug(f"No sessions directory for client {client_id}")
            return []

        # Keep the packing-list registry in sync before _scan_packing_lists()
        # reads it, same as Session Browser's RegistryRefreshWorker. Without
        # this, packing lists uploaded since the registry was last written
        # are invisible here even though they're on disk.
        try:
            registry_manager = SessionRegistryManager(self.profile_manager)
            registry_manager.ensure_registry(client_id)
            registry_manager.refresh_available_lists(client_id)
        except Exception as e:
            logger.error(f"Error refreshing packing-list registry: {e}", exc_info=True)

        sessions = []

        try:
            for session_dir in sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                session_info = {
                    'name': session_dir.name,
                    'path': session_dir,
                    'modified': datetime.fromtimestamp(session_dir.stat().st_mtime),
                    'has_shopify_data': False,
                    'orders_count': 0
                }

                # Check for Shopify data
                analysis_data_path = session_dir / "analysis" / "analysis_data.json"

                if analysis_data_path.exists():
                    try:
                        analysis_data = get_cached_json(str(analysis_data_path), default={})
                        if analysis_data:
                            session_info['has_shopify_data'] = True
                            session_info['orders_count'] = analysis_data.get('total_orders', 0)
                            session_info['analysis_data'] = analysis_data
                            logger.debug(f"Found Shopify session: {session_dir.name} ({session_info['orders_count']} orders)")

                    except Exception as e:
                        logger.warning(f"Error reading analysis_data.json for {session_dir.name}: {e}")

                sessions.append(session_info)

            # Sort by modification time (newest first)
            sessions.sort(key=lambda x: x['modified'], reverse=True)

            return sessions

        except Exception as e:
            logger.error(f"Error scanning sessions: {e}", exc_info=True)
            return []

    def _filter_by_date(self, sessions: List[Dict]) -> List[Dict]:
        """
        Filter sessions by date range.

        Args:
            sessions: List of session dictionaries

        Returns:
            Filtered list of sessions
        """
        from_date = self.date_from.date().toPython()
        to_date = self.date_to.date().toPython()

        filtered = []
        for session in sessions:
            session_date = session['modified'].date()
            if from_date <= session_date <= to_date:
                filtered.append(session)

        return filtered

    def _scan_packing_lists(self, client_id: str, session_path: Path) -> List[Dict]:
        """
        List packing lists for a session from registry_index.json instead of
        re-scanning session/packing_lists/*.json on the file server.

        Args:
            client_id: Client identifier
            session_path: Path to session directory

        Returns:
            List of packing list dictionaries with metadata
        """
        try:
            registry_manager = SessionRegistryManager(self.profile_manager)
            entries = registry_manager.get_all_entries(client_id)
        except Exception as e:
            logger.error(f"Error reading registry for packing lists: {e}", exc_info=True)
            return []

        session_path_str = str(session_path)
        packing_lists = []

        for entry in entries:
            if entry.get('session_path') != session_path_str:
                continue

            name = entry.get('packing_list_name', '')
            timestamp = entry.get('last_updated') or entry.get('created_at') or entry.get('started_at') or ''

            packing_lists.append({
                'name': name,
                'filename': f"{name}.json",
                'path': session_path / "packing_lists" / f"{name}.json",
                'modified': parse_timestamp(timestamp) or datetime.min,
                'orders_count': entry.get('total_orders', 0),
                'courier': entry.get('courier') or None,
                'list_name': name,
            })

        packing_lists.sort(key=lambda x: x['name'])
        return packing_lists

    def _on_session_selected(self):
        """Handle session selection change."""
        selected_items = self.sessions_list.selectedItems()

        if not selected_items:
            self.info_label.setText("Select a session to see details")
            self.load_button.setEnabled(False)
            self.packing_lists_widget.clear()
            self.selected_packing_list_path = None
            return

        item = selected_items[0]
        session = item.data(Qt.UserRole)

        if not session or not isinstance(session, dict):
            return

        # Clear previous packing list selection
        self.selected_packing_list_path = None

        # Update info label
        info_text = f"<b>Session:</b> {session['name']}<br>"
        info_text += f"<b>Modified:</b> {session['modified'].strftime('%Y-%m-%d %H:%M')}<br>"

        if session.get('has_shopify_data'):
            info_text += f"<b>Orders:</b> {session.get('orders_count', 0)}<br>"
            info_text += f"<b>Type:</b> Shopify Session<br>"

            # Show path to analysis data
            analysis_path = session['path'] / "analysis" / "analysis_data.json"
            info_text += f"<b>Data:</b> {analysis_path.name}"

            self.load_button.setEnabled(True)

            # Load packing lists from the registry
            client_id = self.pre_selected_client or self.client_combo.currentData()
            packing_lists = self._scan_packing_lists(client_id, session['path'])
            self.packing_lists_widget.clear()

            if packing_lists:
                info_text += f"<br><b>Packing Lists:</b> {len(packing_lists)} available"

                for pl in packing_lists:
                    list_item = QListWidgetItem()

                    display_text = f"{pl['list_name']}"
                    if pl['courier']:
                        display_text += f" ({pl['courier']})"
                    display_text += f" - {pl['orders_count']} orders"

                    list_item.setText(display_text)
                    list_item.setData(Qt.UserRole, pl)
                    list_item.setForeground(QApplication.palette().color(QPalette.Text))

                    self.packing_lists_widget.addItem(list_item)

                logger.info(f"Loaded {len(packing_lists)} packing lists for session {session['name']}")
            else:
                no_lists_item = QListWidgetItem("No packing lists available (load entire session)")
                no_lists_item.setForeground(Qt.gray)
                self.packing_lists_widget.addItem(no_lists_item)

        else:
            info_text += "<b>Type:</b> Regular session (no Shopify data)"
            self.load_button.setEnabled(False)
            self.packing_lists_widget.clear()

        self.info_label.setText(info_text)

    def _on_packing_list_selected(self):
        """Handle packing list selection change."""
        selected_items = self.packing_lists_widget.selectedItems()

        if not selected_items:
            # No packing list selected, will load entire session
            self.selected_packing_list_path = None
            return

        item = selected_items[0]
        packing_list = item.data(Qt.UserRole)

        if not packing_list or not isinstance(packing_list, dict):
            self.selected_packing_list_path = None
            return

        # Store selected packing list path
        self.selected_packing_list_path = packing_list['path']

        # Update info label to show selected packing list
        session_items = self.sessions_list.selectedItems()
        if session_items:
            session = session_items[0].data(Qt.UserRole)
            if session:
                info_text = f"<b>Session:</b> {session['name']}<br>"
                info_text += f"<b>Modified:</b> {session['modified'].strftime('%Y-%m-%d %H:%M')}<br>"
                info_text += f"<hr><b>Selected Packing List:</b> {packing_list['list_name']}<br>"
                info_text += f"<b>Orders:</b> {packing_list['orders_count']}<br>"
                if packing_list['courier']:
                    info_text += f"<b>Courier:</b> {packing_list['courier']}<br>"
                info_text += f"<b>File:</b> {packing_list['filename']}"

                self.info_label.setText(info_text)

        logger.info(f"Selected packing list: {packing_list['list_name']}")

    def _on_packing_list_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on packing list (same as clicking Load)."""
        packing_list = item.data(Qt.UserRole)

        if packing_list and isinstance(packing_list, dict):
            self._on_load_clicked()

    def _on_session_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on session (same as clicking Load)."""
        session = item.data(Qt.UserRole)

        if session and isinstance(session, dict) and session.get('has_shopify_data'):
            self._on_load_clicked()

    def _on_load_clicked(self):
        """Handle Load button click."""
        selected_items = self.sessions_list.selectedItems()

        if not selected_items:
            return

        item = selected_items[0]
        session = item.data(Qt.UserRole)

        if not session or not isinstance(session, dict):
            return

        if not session.get('has_shopify_data'):
            QMessageBox.warning(
                self,
                "Invalid Session",
                "Selected session does not have Shopify data.\n"
                "Please select a session created by Shopify Tool."
            )
            return

        logger.info(f"Loading Shopify session: {session['name']}")

        self.selected_session_path = session['path']
        self.selected_session_data = session.get('analysis_data')

        # Packing list path is already set by _on_packing_list_selected or None
        if self.selected_packing_list_path:
            logger.info(f"Will load packing list: {self.selected_packing_list_path.name}")
        else:
            logger.info("Will load entire session (no specific packing list selected)")

        self.accept()

    def get_selected_session(self) -> Optional[Path]:
        """
        Get selected session path.

        Returns:
            Path to selected session directory, or None if cancelled
        """
        return self.selected_session_path

    def get_session_data(self) -> Optional[Dict]:
        """
        Get selected session's analysis data.

        Returns:
            Analysis data dictionary, or None if not available
        """
        return self.selected_session_data

    def get_selected_packing_list(self) -> Optional[Path]:
        """
        Get selected packing list path.

        Returns:
            Path to selected packing list JSON file, or None if no specific list selected
        """
        return self.selected_packing_list_path
