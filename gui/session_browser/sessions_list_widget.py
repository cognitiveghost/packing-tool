"""
Sessions List Widget — unified session table for Session Browser.

Shows all sessions (started + available packing lists) for the currently
selected client.  Data comes from registry_index.json via SessionRegistryManager,
so initial load is < 1 second regardless of session count.

Background refresh path:
    RegistryRefreshWorker → registry file read + lock-file staleness checks
    → emit refresh_complete(entries) → populate_table()

Filter / search works purely on already-loaded table data (no server I/O).
"""

import csv
import logging
from datetime import datetime

from PySide6.QtCore import QDate, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.theme import current_tokens
from shared.metadata_utils import parse_timestamp
from shared.theme import StatusDot

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Status display configuration                                         #
# ------------------------------------------------------------------ #

# The stale/paused and abandoned/incomplete pairs render identically until
# 8.9's StatusChip work adds a distinguishing _bg tint -- 8.3 only removes
# the literals. Still better than today's #E74C3C vs #C0392B, which a
# supervisor could not tell apart either.
STATUS_CONFIG = {
    "not_started": {"label": "Not Started", "role": "text_secondary"},
    "in_progress": {"label": "Active",      "role": "status_info"},
    "paused":      {"label": "Paused",      "role": "status_warning"},
    "stale":       {"label": "Stale",       "role": "status_warning"},
    "completed":   {"label": "Completed",   "role": "status_success"},
    "incomplete":  {"label": "Incomplete",  "role": "status_danger"},
    "abandoned":   {"label": "Abandoned",   "role": "status_danger"},
}

# Column indices
COL_STATUS      = 0
COL_LIST_NAME   = 1
COL_SESSION_ID  = 2
COL_WORKER      = 3
COL_PC          = 4
COL_PROGRESS    = 5
COL_STARTED     = 6
COL_DURATION    = 7
COL_ITEMS       = 8
COLUMN_COUNT    = 9

COLUMN_HEADERS = ["Status", "Packing List", "Session", "Worker", "PC",
                  "Progress", "Started", "Duration", "Items"]


# ------------------------------------------------------------------ #
#  Background refresh worker                                           #
# ------------------------------------------------------------------ #

class RegistryRefreshWorker(QThread):
    """
    Background thread that reads the registry file and resolves statuses.

    Work performed:
    1. ensure_registry() — one-time migration scan if file missing
    2. refresh_available_lists() — lightweight scan for new packing lists
    3. get_all_entries() — load + status-resolve all entries

    Emits refresh_complete with a list of entry dicts on success, or
    refresh_failed with an error string on failure.
    """

    # Carries client_id so stale responses from a previous client can be discarded
    refresh_complete = Signal(str, list)  # (client_id, entries)
    refresh_failed   = Signal(str, str)   # (client_id, error_message)

    def __init__(self, registry_manager, client_id: str, parent=None):
        super().__init__(parent)
        self._registry = registry_manager
        self._client_id = client_id

    def run(self):
        try:
            # One-time migration: build registry from scan if not present
            self._registry.ensure_registry(self._client_id)
            # Lightweight: find new packing lists not yet in registry
            self._registry.refresh_available_lists(self._client_id)
            # Resolve statuses (reads lock files for in_progress entries)
            entries = self._registry.get_all_entries(self._client_id)
            self.refresh_complete.emit(self._client_id, entries)
        except Exception as exc:
            logger.exception("RegistryRefreshWorker failed")
            self.refresh_failed.emit(self._client_id, str(exc))


# ------------------------------------------------------------------ #
#  Helper functions                                                    #
# ------------------------------------------------------------------ #

def _fmt_duration(seconds: float | None) -> str:
    if not seconds:
        return "—"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _fmt_date(ts_str: str | None) -> str:
    if not ts_str:
        return "—"
    dt = parse_timestamp(ts_str)
    if dt is None:
        return ts_str[:10] if len(ts_str) >= 10 else ts_str
    return dt.strftime("%Y-%m-%d %H:%M")


def _fmt_progress(entry: dict) -> str:
    total = entry.get("total_orders", 0)
    done  = entry.get("completed_orders", 0)
    if total == 0:
        return "—"
    return f"{done}/{total}"


def _status_display(status: str) -> str:
    cfg = STATUS_CONFIG.get(status, {"label": status.replace("_", " ").title()})
    return cfg["label"]


# ------------------------------------------------------------------ #
#  Sessions List Widget                                                #
# ------------------------------------------------------------------ #

class SessionsListWidget(QWidget):
    """
    Unified session table for one selected client.

    Signals:
        resume_session_requested(dict):  Emitted when user wants to resume
                                         an in-progress / paused / incomplete session.
        start_packing_requested(dict):   Emitted when user wants to start
                                         packing from an available list.
    """

    resume_session_requested = Signal(dict)
    start_packing_requested  = Signal(dict)

    def __init__(self, registry_manager, session_history_manager, parent=None):
        super().__init__(parent)
        self._registry = registry_manager
        self._history_mgr = session_history_manager
        self._client_id: str | None = None
        self._all_entries: list = []
        self._refresh_worker: RegistryRefreshWorker | None = None

        self._init_ui()

    # ------------------------------------------------------------------ #
    #  UI construction                                                     #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # --- placeholder shown before client is selected ---
        self._placeholder = QLabel("← Select a client to view sessions")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {current_tokens().text_secondary};")
        root.addWidget(self._placeholder)

        # --- main container (hidden until client selected) ---
        self._main_frame = QFrame()
        self._main_frame.setVisible(False)
        main_layout = QVBoxLayout(self._main_frame)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)
        root.addWidget(self._main_frame)

        # Header: client name + quick stats
        self._header_label = QLabel()
        self._header_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(self._header_label)

        # Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(6)

        self._status_combo = QComboBox()
        self._status_combo.setMinimumWidth(140)
        self._status_combo.addItem("All statuses", "")
        for key, cfg in STATUS_CONFIG.items():
            self._status_combo.addItem(cfg["label"], key)
        self._status_combo.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(QLabel("Status:"))
        filter_layout.addWidget(self._status_combo)

        filter_layout.addWidget(QLabel("From:"))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate(2020, 1, 1))
        self._date_from.setSpecialValueText(" ")
        self._date_from.dateChanged.connect(self._apply_filters)
        filter_layout.addWidget(self._date_from)

        filter_layout.addWidget(QLabel("To:"))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.dateChanged.connect(self._apply_filters)
        filter_layout.addWidget(self._date_to)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search list, session, worker…")
        self._search_input.setMinimumWidth(200)
        self._search_input.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self._search_input)

        filter_layout.addStretch()
        main_layout.addLayout(filter_layout)

        # Progress / status bar for refresh
        self._status_bar = QLabel("")
        self._status_bar.setStyleSheet(f"color: {current_tokens().text_secondary}; font-style: italic;")
        main_layout.addWidget(self._status_bar)

        # Table
        self._table = QTableWidget(0, COLUMN_COUNT)
        self._table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(
            COL_LIST_NAME, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            COL_STATUS, QHeaderView.ResizeMode.Fixed
        )
        self._table.setColumnWidth(COL_STATUS,    115)
        self._table.setColumnWidth(COL_SESSION_ID, 110)
        self._table.setColumnWidth(COL_WORKER,     105)
        self._table.setColumnWidth(COL_PC,         105)
        self._table.setColumnWidth(COL_PROGRESS,    75)
        self._table.setColumnWidth(COL_STARTED,    130)
        self._table.setColumnWidth(COL_DURATION,    75)
        self._table.setColumnWidth(COL_ITEMS,       55)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.setShowGrid(False)
        self._table.setSortingEnabled(True)
        self._table.selectionModel().currentRowChanged.connect(
            lambda current, _prev: self._on_row_selected(current.row())
        )
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        main_layout.addWidget(self._table)

        # Consolidated action bar (replaces the old preview QGroupBox + separate
        # action_layout — see 2026-07-26-unified-ui-design-system-design.md)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self._preview_label = QLabel("Select a row for quick info")
        self._preview_label.setWordWrap(True)
        action_bar.addWidget(self._preview_label, 1)

        self._preview_action_btn = QPushButton()
        self._preview_action_btn.setVisible(False)
        self._preview_action_btn.clicked.connect(self._on_preview_action)
        action_bar.addWidget(self._preview_action_btn)

        self._preview_details_btn = QPushButton("View Details")
        self._preview_details_btn.setVisible(False)
        self._preview_details_btn.clicked.connect(self._on_preview_details)
        action_bar.addWidget(self._preview_details_btn)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        action_bar.addWidget(divider)

        self._export_csv_btn = QPushButton("Export CSV")
        self._export_csv_btn.clicked.connect(self._export_csv)
        action_bar.addWidget(self._export_csv_btn)

        self._export_excel_btn = QPushButton("Export Excel")
        self._export_excel_btn.clicked.connect(self._export_excel)
        action_bar.addWidget(self._export_excel_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        action_bar.addWidget(self._refresh_btn)

        main_layout.addLayout(action_bar)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def load_client(self, client_id: str):
        """Switch to displaying sessions for the given client."""
        self._client_id = client_id
        self._placeholder.setVisible(False)
        self._main_frame.setVisible(True)
        self._header_label.setText(f"Client:  {client_id}")
        self._clear_table()

        if self._registry is None:
            self._status_bar.setText("Session registry not available — cannot load sessions.")
            return

        self._status_bar.setText("Loading…")
        self.refresh()

    def refresh(self):
        """Trigger a background registry read for the current client."""
        if not self._client_id or self._registry is None:
            return

        # If a previous worker is still running (e.g. user switched clients
        # quickly), disconnect its signals so its stale result never reaches
        # the UI.  Let it finish naturally — no need to kill the thread.
        if self._refresh_worker and self._refresh_worker.isRunning():
            try:
                self._refresh_worker.refresh_complete.disconnect()
                self._refresh_worker.refresh_failed.disconnect()
            except RuntimeError:
                pass  # Already disconnected

        self._refresh_btn.setEnabled(False)
        self._status_bar.setText("Refreshing…")

        self._refresh_worker = RegistryRefreshWorker(
            self._registry, self._client_id, parent=self
        )
        self._refresh_worker.refresh_complete.connect(self._on_refresh_complete)
        self._refresh_worker.refresh_failed.connect(self._on_refresh_failed)
        self._refresh_worker.finished.connect(
            lambda: self._refresh_btn.setEnabled(True)
        )
        self._refresh_worker.start()

    # ------------------------------------------------------------------ #
    #  Table population                                                    #
    # ------------------------------------------------------------------ #

    def _on_refresh_complete(self, client_id: str, entries: list):
        # Discard stale responses that arrived after the user switched clients
        if client_id != self._client_id:
            return
        self._all_entries = entries
        self._populate_table(entries)
        self._update_header_stats(entries)
        self._status_bar.setText(
            f"Last refreshed: {datetime.now().astimezone().strftime('%H:%M:%S')}  "
            f"({len(entries)} entries)"
        )

    def _on_refresh_failed(self, client_id: str, error: str):
        if client_id != self._client_id:
            return
        self._status_bar.setText(f"Refresh failed: {error}")
        logger.error(f"SessionsListWidget refresh failed: {error}")

    def _populate_table(self, entries: list):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        # Sort: active first, then by started_at descending within each group
        _STATUS_PRIORITY = {
            "in_progress": 0, "stale": 1, "paused": 2, "not_started": 3,
            "incomplete": 4, "abandoned": 5, "completed": 6,
        }
        sorted_entries = sorted(
            entries,
            key=lambda e: (
                _STATUS_PRIORITY.get(e.get("status", ""), 9),
                -(self._ts_to_epoch(e.get("started_at") or e.get("created_at", "")))
            ),
        )

        for entry in sorted_entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._fill_row(row, entry)

        self._table.setSortingEnabled(True)
        self._apply_filters()

    @staticmethod
    def _ts_to_epoch(ts: str) -> float:
        if not ts:
            return 0.0
        dt = parse_timestamp(ts)
        if dt:
            return dt.timestamp()
        return 0.0

    def _make_status_cell(self, status: str) -> QWidget:
        cfg = STATUS_CONFIG.get(status, {"label": status.replace("_", " ").title(), "role": "text_secondary"})
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(6)
        layout.addWidget(StatusDot(cfg["role"], current_tokens()))
        layout.addWidget(QLabel(cfg["label"]))
        layout.addStretch()
        return cell

    def _fill_row(self, row: int, entry: dict):
        status = entry.get("status", "")

        # Col 0: Status — hidden sort-key item carries the sortable label and
        # the row's entry data (read by _get_row_entry/_apply_filters); the
        # visible content is the StatusDot cell widget set alongside it.
        sort_item = QTableWidgetItem()
        sort_item.setData(Qt.ItemDataRole.DisplayRole,
                          STATUS_CONFIG.get(status, {}).get("label", ""))
        sort_item.setData(Qt.ItemDataRole.UserRole, entry)
        self._table.setItem(row, COL_STATUS, sort_item)
        self._table.setCellWidget(row, COL_STATUS, self._make_status_cell(status))

        # Col 1: Packing List
        self._table.setItem(row, COL_LIST_NAME,
                            QTableWidgetItem(entry.get("packing_list_name", "—")))

        # Col 2: Session ID
        self._table.setItem(row, COL_SESSION_ID,
                            QTableWidgetItem(entry.get("session_id", "—")))

        # Col 3: Worker
        worker = entry.get("worker_name") or entry.get("worker_id") or "—"
        self._table.setItem(row, COL_WORKER, QTableWidgetItem(worker))

        # Col 4: PC
        self._table.setItem(row, COL_PC,
                            QTableWidgetItem(entry.get("pc_name") or "—"))

        # Col 5: Progress (center-aligned)
        prog_item = QTableWidgetItem(_fmt_progress(entry))
        prog_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, COL_PROGRESS, prog_item)

        # Col 6: Started
        ts = entry.get("started_at") or entry.get("created_at") or ""
        self._table.setItem(row, COL_STARTED, QTableWidgetItem(_fmt_date(ts)))

        # Col 7: Duration (center-aligned)
        dur_item = QTableWidgetItem(_fmt_duration(entry.get("duration_seconds")))
        dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, COL_DURATION, dur_item)

        # Col 8: Items (center-aligned)
        items = entry.get("total_items", 0)
        items_item = QTableWidgetItem(str(items) if items else "—")
        items_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, COL_ITEMS, items_item)

    def _update_header_stats(self, entries: list):
        counts = {}
        for e in entries:
            s = e.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1

        active = counts.get("in_progress", 0)
        stale = counts.get("stale", 0)
        paused = counts.get("paused", 0)
        total = len(entries)
        parts = [f"Client: {self._client_id}", f"{total} entries"]
        if active:
            parts.append(f"{active} active")
        if stale:
            parts.append(f"⚠ {stale} stale")
        if paused:
            parts.append(f"{paused} paused")
        self._header_label.setText("   ·   ".join(parts))

    def _clear_table(self):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setSortingEnabled(True)

    # ------------------------------------------------------------------ #
    #  Filters                                                             #
    # ------------------------------------------------------------------ #

    def _apply_filters(self):
        status_filter = self._status_combo.currentData()
        search = self._search_input.text().strip().lower()
        date_from = self._date_from.date().toPython()
        date_to   = self._date_to.date().toPython()

        for row in range(self._table.rowCount()):
            entry = self._table.item(row, COL_STATUS).data(Qt.ItemDataRole.UserRole)
            show = True

            # Status filter
            if status_filter and entry.get("status", "") != status_filter:
                show = False

            # Date filter
            if show:
                ts_str = entry.get("started_at") or entry.get("created_at", "")
                if ts_str:
                    dt = parse_timestamp(ts_str)
                    if dt:
                        d = dt.date()
                        if d < date_from or d > date_to:
                            show = False

            # Text search
            if show and search:
                haystack = " ".join([
                    entry.get("packing_list_name", ""),
                    entry.get("session_id", ""),
                    entry.get("worker_name", ""),
                    entry.get("worker_id", ""),
                    entry.get("pc_name", ""),
                ]).lower()
                if search not in haystack:
                    show = False

            self._table.setRowHidden(row, not show)

    # ------------------------------------------------------------------ #
    #  Row selection / preview panel                                       #
    # ------------------------------------------------------------------ #

    def _get_row_entry(self, row: int) -> dict | None:
        if row < 0:
            return None
        item = self._table.item(row, COL_STATUS)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_row_selected(self, row: int):
        entry = self._get_row_entry(row)
        if entry is None:
            self._preview_label.setText("Select a row for quick info")
            self._preview_action_btn.setVisible(False)
            return

        status = entry.get("status", "")
        worker = entry.get("worker_name") or entry.get("worker_id") or "—"
        pc     = entry.get("pc_name", "—")
        total  = entry.get("total_orders", 0)
        done   = entry.get("completed_orders", 0)
        skip   = entry.get("skipped_orders", 0)
        items  = entry.get("total_items", 0)
        dur    = _fmt_duration(entry.get("duration_seconds"))
        metrics = entry.get("metrics") or {}
        corrections = metrics.get("total_corrections", "—")
        unknowns    = metrics.get("total_unknown_scans", "—")

        text = (
            f"<b>{entry.get('packing_list_name', '—')}</b>  ·  "
            f"Worker: {worker}  ·  PC: {pc}  ·  Duration: {dur}<br>"
            f"Orders: {done}/{total}  (skipped: {skip})  ·  Items: {items}"
        )
        if metrics:
            text += f"  ·  Corrections: {corrections}  ·  Unknown scans: {unknowns}"
        self._preview_label.setText(text)

        # Configure action buttons
        if status == "not_started":
            self._preview_action_btn.setText("▶  Start Packing")
            self._preview_action_btn.setVisible(True)
            self._preview_details_btn.setVisible(False)
        elif status == "incomplete":
            self._preview_action_btn.setText("↩  Resume Session")
            self._preview_action_btn.setVisible(True)
            self._preview_details_btn.setVisible(True)
        elif status in ("in_progress", "stale", "paused"):
            self._preview_action_btn.setText("↩  Resume Session")
            self._preview_action_btn.setVisible(True)
            self._preview_details_btn.setVisible(False)
        elif status in ("completed", "abandoned"):
            self._preview_action_btn.setText("View Details")
            self._preview_action_btn.setVisible(True)
            self._preview_details_btn.setVisible(False)
        else:
            self._preview_action_btn.setVisible(False)
            self._preview_details_btn.setVisible(False)

    def _on_row_double_clicked(self, index):
        entry = self._get_row_entry(index.row())
        if entry:
            self._open_details_for_entry(entry)

    def _on_preview_action(self):
        row = self._table.currentRow()
        entry = self._get_row_entry(row)
        if entry is None:
            return
        status = entry.get("status", "")
        if status == "not_started":
            self._emit_start_packing(entry)
        elif status in ("in_progress", "stale", "paused", "incomplete"):
            self._emit_resume_session(entry)
        else:
            self._open_details_for_entry(entry)

    def _on_preview_details(self):
        row = self._table.currentRow()
        entry = self._get_row_entry(row)
        if entry:
            self._open_details_for_entry(entry)

    def _open_details_for_entry(self, entry: dict):
        """Open SessionDetailsDialog for any entry that has enough data."""
        if not entry.get("session_id"):
            return
        try:
            from .session_details_dialog import SessionDetailsDialog
            session_data = {
                "client_id": self._client_id,
                "session_id": entry["session_id"],
                "work_dir": entry.get("work_dir", ""),
                "packing_list_name": entry.get("packing_list_name", ""),
            }
            dlg = SessionDetailsDialog(
                session_data=session_data,
                session_history_manager=self._history_mgr,
                parent=self,
            )
            dlg.exec()
        except Exception as e:
            logger.exception("Failed to open session details")
            QMessageBox.warning(self, "Error", f"Could not load session details:\n{e}")

    def _emit_resume_session(self, entry: dict):
        info = {
            "session_path":       entry.get("session_path", ""),
            "client_id":          self._client_id,
            "packing_list_name":  entry.get("packing_list_name", ""),
            "work_dir":           entry.get("work_dir", ""),
            "session_id":         entry.get("session_id", ""),
        }
        self.resume_session_requested.emit(info)

    def _emit_start_packing(self, entry: dict):
        info = {
            "session_path":       entry.get("session_path", ""),
            "client_id":          self._client_id,
            "packing_list_name":  entry.get("packing_list_name", ""),
            "list_file":          entry.get("packing_list_path", ""),
        }
        self.start_packing_requested.emit(info)

    # ------------------------------------------------------------------ #
    #  Export                                                              #
    # ------------------------------------------------------------------ #

    def _visible_entries(self) -> list:
        """Return entries corresponding to currently visible (non-hidden) rows."""
        result = []
        for row in range(self._table.rowCount()):
            if not self._table.isRowHidden(row):
                entry = self._get_row_entry(row)
                if entry:
                    result.append(entry)
        return result

    def _export_csv(self):
        entries = self._visible_entries()
        if not entries:
            QMessageBox.information(self, "Export", "No rows to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", f"sessions_{self._client_id}.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Status", "Packing List", "Session ID", "Worker", "PC",
                    "Progress", "Started", "Duration (s)", "Total Items",
                    "Total Orders", "Completed Orders", "Skipped Orders"
                ])
                for e in entries:
                    writer.writerow([
                        e.get("status", ""),
                        e.get("packing_list_name", ""),
                        e.get("session_id", ""),
                        e.get("worker_name") or e.get("worker_id", ""),
                        e.get("pc_name", ""),
                        _fmt_progress(e),
                        e.get("started_at") or e.get("created_at", ""),
                        e.get("duration_seconds", ""),
                        e.get("total_items", ""),
                        e.get("total_orders", ""),
                        e.get("completed_orders", ""),
                        e.get("skipped_orders", ""),
                    ])
            QMessageBox.information(self, "Export Complete",
                                    f"Saved {len(entries)} rows to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _export_excel(self):
        entries = self._visible_entries()
        if not entries:
            QMessageBox.information(self, "Export", "No rows to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel", f"sessions_{self._client_id}.xlsx",
            "Excel files (*.xlsx)"
        )
        if not path:
            return
        try:
            import pandas as pd
            rows = []
            for e in entries:
                rows.append({
                    "Status":            STATUS_CONFIG.get(
                        e.get("status", ""), {"label": e.get("status", "")}
                    )["label"],
                    "Packing List":      e.get("packing_list_name", ""),
                    "Session ID":        e.get("session_id", ""),
                    "Worker":            e.get("worker_name") or e.get("worker_id", ""),
                    "PC":                e.get("pc_name", ""),
                    "Progress":          _fmt_progress(e),
                    "Started":           e.get("started_at") or e.get("created_at", ""),
                    "Duration (s)":      e.get("duration_seconds"),
                    "Total Items":       e.get("total_items"),
                    "Total Orders":      e.get("total_orders"),
                    "Completed Orders":  e.get("completed_orders"),
                    "Skipped Orders":    e.get("skipped_orders"),
                })
            df = pd.DataFrame(rows)
            df.to_excel(path, index=False)
            QMessageBox.information(self, "Export Complete",
                                    f"Saved {len(entries)} rows to:\n{path}")
        except ImportError:
            QMessageBox.critical(self, "Export Failed",
                                 "pandas is required for Excel export. Use CSV instead.")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
