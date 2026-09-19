"""Session Detail Page — a page in the browser's stack, not a modal dialog.

B2 draws the same rail, command bar and status bar as the list, with only the
page area swapped -- so this is one more widget in SessionBrowserWidget's
QStackedWidget, not a QDialog with its own event loop and its own close
button. The data-loading logic below is carried over unchanged from the
QDialog it replaced.
"""

import json
import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.theme import current_tokens
from packing_tool.json_cache import get_cached_json
from packing_tool.packer_logic import compute_order_timing_metrics
from shared.theme import StatusChip

from .metrics_tab import MetricsTab
from .orders_tab import OrdersTab
from .overview_tab import OverviewTab
from .sessions_list_widget import status_chip_config

logger = logging.getLogger(__name__)


class SessionDetailPage(QWidget):
    """One session's detail: header, tab strip, and the three tabs.

    Signals:
        back_requested: the ghost button was clicked; the browser should
            show the list again.
    """

    back_requested = Signal()

    def __init__(
        self, session_data: dict, session_history_manager=None, parent=None
    ) -> None:
        super().__init__(parent)

        self.session_data = session_data
        self.session_history_manager = session_history_manager
        self.details = {}

        self._load_session_details()
        self._init_ui()

    # ------------------------------------------------------------------ #
    #  UI                                                                   #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        header = QHBoxLayout()

        self.back_button = QPushButton("← Sessions")
        self.back_button.clicked.connect(self.back_requested)
        header.addWidget(self.back_button)

        self.title_label = QLabel(self.session_data.get("session_id", ""))
        header.addWidget(self.title_label)

        status = self.session_data.get("status", "")
        cfg = status_chip_config(status)
        self.status_chip = StatusChip(
            cfg["role"],
            cfg["label"],
            current_tokens(),
            live=cfg["live"],
            manual=cfg["manual"],
        )
        header.addWidget(self.status_chip)

        header.addStretch()

        export_btn = QPushButton("Export Excel")
        export_btn.clicked.connect(self._export_excel)
        header.addWidget(export_btn)

        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.overview_tab = OverviewTab(self.details, parent=self)
        self.tabs.addTab(self.overview_tab, "Overview")

        self.orders_tab = OrdersTab(self.details, parent=self)
        self.tabs.addTab(self.orders_tab, "Orders")

        self.metrics_tab = MetricsTab(self.details, parent=self)
        self.tabs.addTab(self.metrics_tab, "Metrics")

        layout.addWidget(self.tabs)

    # ------------------------------------------------------------------ #
    #  Data loading -- unchanged from the dialog this page replaces         #
    # ------------------------------------------------------------------ #

    def _load_session_details(self):
        """Load session details from files or use provided session_data."""

        if self._is_standardized_data(self.session_data):
            self._build_details_from_standardized_data()
            return

        client_id = self.session_data.get("client_id")
        session_id = self.session_data.get("session_id")
        work_dir = self.session_data.get("work_dir")

        if work_dir:
            work_dir_path = Path(work_dir)

            state_file = work_dir_path / "packing_state.json"
            packing_state = {}
            if state_file.exists():
                try:
                    packing_state = get_cached_json(state_file, default={})
                except Exception as e:
                    logger.warning(f"Failed to load packing_state.json: {e}")

            summary_file = work_dir_path / "session_summary.json"
            session_summary = {}
            if summary_file.exists():
                try:
                    session_summary = get_cached_json(summary_file, default={})
                except Exception as e:
                    logger.warning(f"Failed to load session_summary.json: {e}")

            info_file = work_dir_path.parent / "session_info.json"
            session_info = {}
            if info_file.exists():
                try:
                    session_info = get_cached_json(info_file, default={})
                except Exception as e:
                    logger.warning(f"Failed to load session_info.json: {e}")

            if session_summary:
                record = {
                    "session_id": session_summary.get("session_id", session_id),
                    "client_id": session_summary.get("client_id", client_id),
                    "packing_list_path": session_summary.get("packing_list_path", ""),
                    "packing_list_name": session_summary.get("packing_list_name", ""),
                    "worker_id": session_summary.get("worker_id", ""),
                    "worker_name": session_summary.get("worker_name", ""),
                    "pc_name": session_summary.get("pc_name", ""),
                    "start_time": session_summary.get("started_at", ""),
                    "end_time": session_summary.get("completed_at", ""),
                    "duration_seconds": session_summary.get("duration_seconds", 0),
                    "total_orders": session_summary.get("total_orders", 0),
                    "completed_orders": session_summary.get("completed_orders", 0),
                    "in_progress_orders": session_summary.get("in_progress_orders", 0),
                    "skipped_orders_count": session_summary.get(
                        "skipped_orders_count", 0
                    ),
                    "total_items_packed": session_summary.get("total_items", 0),
                }
            elif session_info:
                record = {
                    "session_id": session_info.get("session_id", session_id),
                    "client_id": session_info.get("client_id", client_id),
                    "packing_list_path": session_info.get("packing_list_path", ""),
                    "packing_list_name": session_info.get("packing_list_name", ""),
                    "worker_id": session_info.get("worker_id", ""),
                    "worker_name": session_info.get("worker_name", ""),
                    "pc_name": session_info.get("pc_name", ""),
                    "start_time": session_info.get("started_at", ""),
                    "end_time": None,
                    "duration_seconds": 0,
                    "total_orders": packing_state.get("progress", {}).get(
                        "total_orders", 0
                    ),
                    "completed_orders": len(packing_state.get("completed", [])),
                    "in_progress_orders": sum(
                        1
                        for k in packing_state.get("in_progress", {})
                        if not k.startswith("_")
                    ),
                    "skipped_orders_count": len(
                        packing_state.get("skipped_orders", [])
                    ),
                    "total_items_packed": sum(
                        o.get("items_count", 0)
                        for o in packing_state.get("completed", [])
                    ),
                }
            else:
                logger.warning(f"No valid session data found in work_dir: {work_dir}")
                return

            if not session_summary and packing_state:
                session_summary = self._build_partial_summary(
                    packing_state, session_info
                )
                if session_summary:
                    logger.info("Built partial session summary from packing_state.json")

            self.details = {
                "record": record,
                "packing_state": packing_state,
                "session_info": session_info,
                "session_summary": session_summary,
            }

            logger.info(f"Loaded session details from work_dir: {work_dir}")
            return

        # No work_dir: fall back to SessionHistoryManager, when there is one.
        # A page embedded in a stack must not crash the whole app over a
        # session record that carries neither -- it just shows empty tabs.
        if self.session_history_manager is None:
            return

        details = self.session_history_manager.get_session_details(
            client_id=client_id, session_id=session_id
        )
        if details:
            self.details = details

    def _build_partial_summary(self, packing_state: dict, session_info: dict) -> dict:
        """Build a minimal session_summary-compatible dict from packing_state for incomplete sessions.

        Called when session_summary.json does not yet exist (session ended without full completion).
        Computes the same metrics that generate_session_summary() would compute, but from the
        data available in packing_state.json.

        Returns an empty dict if there is insufficient data to compute any metrics.
        """
        completed_orders = packing_state.get("completed", [])
        if not completed_orders:
            return {}

        orders_with_timing = [
            o
            for o in completed_orders
            if isinstance(o, dict) and o.get("duration_seconds")
        ]

        if not orders_with_timing:
            return {
                "metrics": {},
                "orders": [o for o in completed_orders if isinstance(o, dict)],
                "skipped_orders": [
                    {"order_number": n, "skipped_at": None, "status": "skipped"}
                    for n in packing_state.get("skipped_orders", [])
                ],
                "skipped_orders_count": len(packing_state.get("skipped_orders", [])),
                "completed_orders": len(
                    [o for o in completed_orders if isinstance(o, dict)]
                ),
                "total_orders": packing_state.get("progress", {}).get(
                    "total_orders", 0
                ),
                "started_at": session_info.get("started_at")
                or packing_state.get("started_at"),
                "status": "incomplete",
            }

        timing_metrics = compute_order_timing_metrics(orders_with_timing)

        started_at = session_info.get("started_at") or packing_state.get("started_at")
        last_updated = packing_state.get("last_updated")
        duration_seconds = 0
        orders_per_hour = 0
        items_per_hour = 0
        if started_at and last_updated:
            try:
                from datetime import datetime

                start_dt = datetime.fromisoformat(started_at)
                end_dt = datetime.fromisoformat(last_updated)
                duration_seconds = max(0, int((end_dt - start_dt).total_seconds()))
                if duration_seconds > 0:
                    hours = duration_seconds / 3600.0
                    orders_per_hour = round(len(orders_with_timing) / hours, 1)
                    total_items_packed = sum(
                        o.get("items_count", 0) for o in orders_with_timing
                    )
                    if total_items_packed > 0:
                        items_per_hour = round(total_items_packed / hours, 1)
            except (ValueError, TypeError):
                pass

        raw_in_progress = packing_state.get("in_progress", {})
        in_progress_count = sum(1 for k in raw_in_progress if not k.startswith("_"))

        skipped_timing = packing_state.get("skipped_orders_timing", {})
        return {
            "status": "incomplete",
            "started_at": started_at,
            "completed_at": last_updated,
            "duration_seconds": duration_seconds,
            "total_orders": packing_state.get("progress", {}).get("total_orders", 0),
            "completed_orders": len(
                [o for o in completed_orders if isinstance(o, dict)]
            ),
            "in_progress_orders": in_progress_count,
            "skipped_orders_count": len(packing_state.get("skipped_orders", [])),
            "metrics": {
                **timing_metrics,
                "orders_per_hour": orders_per_hour,
                "items_per_hour": items_per_hour,
            },
            "orders": [o for o in completed_orders if isinstance(o, dict)],
            "skipped_orders": [
                {
                    "order_number": n,
                    "skipped_at": skipped_timing.get(n),
                    "status": "skipped",
                }
                for n in packing_state.get("skipped_orders", [])
            ],
        }

    def _is_standardized_data(self, data: dict) -> bool:
        """Check if session_data carries the pre-built totals this page can use directly.

        Sniff a field only that producer emits. Identity fields like
        ``status`` or ``packing_list_name`` are also present on a plain
        registry entry, which has none of the totals below -- gating on
        those routes a registry entry into the wrong loader and renders
        the session as Unknown/0.
        """
        return "orders_total" in data

    def _build_details_from_standardized_data(self):
        """Build self.details from standardized session_data format."""
        from datetime import datetime

        data = self.session_data

        start_time = data.get("started_at")
        if start_time and isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time)
            except (ValueError, TypeError):
                pass

        end_time = data.get("ended_at")
        if end_time and isinstance(end_time, str):
            try:
                end_time = datetime.fromisoformat(end_time)
            except (ValueError, TypeError):
                pass

        record = {
            "session_id": data.get("session_id"),
            "client_id": data.get("client_id"),
            "packing_list_path": data.get("packing_list_name", ""),
            "packing_list_name": data.get("packing_list_name", ""),
            "worker_id": data.get("worker_id", "Unknown"),
            "worker_name": data.get("worker_name", ""),
            "pc_name": data.get("pc_name", "Unknown"),
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": data.get("duration_seconds", 0),
            "total_orders": data.get("orders_total", 0),
            "completed_orders": data.get("orders_completed", 0),
            "in_progress_orders": data.get("in_progress_orders", 0),
            "skipped_orders_count": data.get("skipped_orders_count", 0),
            "total_items_packed": data.get("items_packed", 0),
        }

        work_dir = data.get("work_dir")
        packing_state = {}
        session_summary = {}

        if work_dir:
            work_dir_path = Path(work_dir)

            state_file = work_dir_path / "packing_state.json"
            if state_file.exists():
                try:
                    with open(state_file, encoding="utf-8") as f:
                        packing_state = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load packing_state.json: {e}")

            summary_file = work_dir_path / "session_summary.json"
            if summary_file.exists():
                try:
                    with open(summary_file, encoding="utf-8") as f:
                        session_summary = json.load(f)
                        if "worker_id" in session_summary:
                            record["worker_id"] = session_summary["worker_id"]
                        if "worker_name" in session_summary:
                            record["worker_name"] = session_summary["worker_name"]
                except Exception as e:
                    logger.warning(f"Failed to load session_summary.json: {e}")

        if not session_summary and packing_state:
            session_info_hint = {"started_at": data.get("started_at")}
            session_summary = self._build_partial_summary(
                packing_state, session_info_hint
            )
            if session_summary:
                logger.info(
                    "Built partial session summary from packing_state.json (standardized path)"
                )

        self.details = {
            "record": record,
            "packing_state": packing_state,
            "session_info": {},
            "session_summary": session_summary,
        }

        logger.info(
            f"Built session details from standardized data for session: {data.get('session_id')}"
        )

    # ------------------------------------------------------------------ #
    #  Export                                                              #
    # ------------------------------------------------------------------ #

    def _export_excel(self):
        orders = self._get_orders_for_export()

        if not orders:
            QMessageBox.warning(self, "No Data", "No orders data available for export.")
            return

        session_id = self.session_data.get("session_id", "session")
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Session Details",
            f"session_{session_id}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not filepath:
            return

        try:
            import pandas as pd

            rows = []
            for order in orders:
                for item in order.get("items", []):
                    rows.append(
                        {
                            "Order Number": order["order_number"],
                            "Order Started": order.get("started_at", ""),
                            "Order Completed": order.get("completed_at", ""),
                            "Order Duration (s)": order.get("duration_seconds", 0),
                            "SKU": item["sku"],
                            "Quantity": item["quantity"],
                            "Scanned At": item.get("scanned_at", ""),
                            "Time from Start (s)": item.get(
                                "time_from_order_start_seconds", 0
                            ),
                        }
                    )

            df = pd.DataFrame(rows)
            df.to_excel(filepath, index=False, sheet_name="Session Details")
            QMessageBox.information(
                self, "Success", f"Session details exported to:\n{filepath}"
            )
        except Exception as e:
            logger.exception("Failed to export")
            QMessageBox.critical(
                self, "Export Failed", f"Failed to export session details:\n{e!s}"
            )

    def _get_orders_for_export(self) -> list:
        if "session_summary" in self.details:
            orders = self.details["session_summary"].get("orders", [])
            if orders:
                return orders

        if "packing_state" in self.details:
            return self.details["packing_state"].get("completed", [])

        return []
