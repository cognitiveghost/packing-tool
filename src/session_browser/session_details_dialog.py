"""Session Details Dialog - Detailed view of session with orders, items, metrics"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QMessageBox, QFileDialog
)

from .overview_tab import OverviewTab
from .orders_tab import OrdersTab
from .metrics_tab import MetricsTab

from pathlib import Path
import json
from logger import get_logger
from json_cache import get_cached_json
from packer_logic import compute_order_timing_metrics

logger = get_logger(__name__)


class SessionDetailsDialog(QDialog):
    """Dialog showing detailed session information"""

    def __init__(
        self,
        session_data: dict,
        session_history_manager,
        parent=None
    ):
        """
        Initialize Session Details Dialog.

        Args:
            session_data: Dict with session info
                For completed: {client_id, session_id, work_dir (optional)}
                For active: {client_id, session_id, work_dir, lock_info (optional)}
            session_history_manager: SessionHistoryManager instance
            parent: Parent widget
        """
        super().__init__(parent)

        self.session_data = session_data
        self.session_history_manager = session_history_manager
        self.details = None

        self._load_session_details()
        self._init_ui()

        self.setWindowTitle(f"Session Details: {session_data['session_id']}")
        self.resize(900, 700)
        self.setMinimumSize(700, 500)

    def _load_session_details(self):
        """Load session details from files or use provided session_data."""

        # Check if session_data already has complete information (standardized format)
        if self._is_standardized_data(self.session_data):
            # Use the standardized data directly
            self._build_details_from_standardized_data()
            return

        client_id = self.session_data['client_id']
        session_id = self.session_data['session_id']
        work_dir = self.session_data.get('work_dir')

        # If work_dir specified explicitly, use it directly
        if work_dir:
            work_dir_path = Path(work_dir)

            # OPTIMIZED: Load packing_state.json for basic info (with caching)
            state_file = work_dir_path / "packing_state.json"
            packing_state = {}
            if state_file.exists():
                try:
                    packing_state = get_cached_json(state_file, default={})
                except Exception as e:
                    logger.warning(f"Failed to load packing_state.json: {e}")

            # OPTIMIZED: Load session_summary.json for Phase 2b data (with caching)
            summary_file = work_dir_path / "session_summary.json"
            session_summary = {}
            if summary_file.exists():
                try:
                    session_summary = get_cached_json(summary_file, default={})
                except Exception as e:
                    logger.warning(f"Failed to load session_summary.json: {e}")

            # OPTIMIZED: Load session_info.json for metadata (with caching)
            info_file = work_dir_path.parent / "session_info.json"
            session_info = {}
            if info_file.exists():
                try:
                    session_info = get_cached_json(info_file, default={})
                except Exception as e:
                    logger.warning(f"Failed to load session_info.json: {e}")

            # Build record from available data
            # Prefer session_summary, fallback to packing_state
            if session_summary:
                record = {
                    'session_id': session_summary.get('session_id', session_id),
                    'client_id': session_summary.get('client_id', client_id),
                    'packing_list_path': session_summary.get('packing_list_path', ''),
                    'packing_list_name': session_summary.get('packing_list_name', ''),
                    'worker_id': session_summary.get('worker_id', ''),
                    'worker_name': session_summary.get('worker_name', ''),
                    'pc_name': session_summary.get('pc_name', ''),
                    'start_time': session_summary.get('started_at', ''),
                    'end_time': session_summary.get('completed_at', ''),
                    'duration_seconds': session_summary.get('duration_seconds', 0),
                    'total_orders': session_summary.get('total_orders', 0),
                    'completed_orders': session_summary.get('completed_orders', 0),
                    'in_progress_orders': session_summary.get('in_progress_orders', 0),
                    'skipped_orders_count': session_summary.get('skipped_orders_count', 0),
                    'total_items_packed': session_summary.get('total_items', 0)
                }
            elif session_info:
                record = {
                    'session_id': session_info.get('session_id', session_id),
                    'client_id': session_info.get('client_id', client_id),
                    'packing_list_path': session_info.get('packing_list_path', ''),
                    'packing_list_name': session_info.get('packing_list_name', ''),
                    'worker_id': session_info.get('worker_id', ''),
                    'worker_name': session_info.get('worker_name', ''),
                    'pc_name': session_info.get('pc_name', ''),
                    'start_time': session_info.get('started_at', ''),
                    'end_time': None,
                    'duration_seconds': 0,
                    'total_orders': packing_state.get('progress', {}).get('total_orders', 0),
                    'completed_orders': len(packing_state.get('completed', [])),
                    'in_progress_orders': sum(
                        1 for k in packing_state.get('in_progress', {})
                        if not k.startswith('_')
                    ),
                    'skipped_orders_count': len(packing_state.get('skipped_orders', [])),
                    'total_items_packed': sum(o.get('items_count', 0) for o in packing_state.get('completed', []))
                }
            else:
                raise ValueError(f"No valid session data found in work_dir: {work_dir}")

            # For incomplete sessions (no session_summary.json), build a partial summary
            # from the completed orders stored in packing_state.json so that MetricsTab
            # can display whatever metrics are available instead of "Metrics not available".
            if not session_summary and packing_state:
                session_summary = self._build_partial_summary(packing_state, session_info)
                if session_summary:
                    logger.info("Built partial session summary from packing_state.json")

            self.details = {
                'record': record,
                'packing_state': packing_state,
                'session_info': session_info,
                'session_summary': session_summary
            }

            logger.info(f"Loaded session details from work_dir: {work_dir}")
            return

        # If no work_dir, try to load using SessionHistoryManager
        self.details = self.session_history_manager.get_session_details(
            client_id=client_id,
            session_id=session_id
        )

        if not self.details:
            raise ValueError(f"Session not found: {session_id}")

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Tab widget
        self.tab_widget = QTabWidget()

        # Overview tab
        self.overview_tab = OverviewTab(self.details, parent=self)
        self.tab_widget.addTab(self.overview_tab, "Overview")

        # Orders tab (Phase 2b data)
        self.orders_tab = OrdersTab(self.details, parent=self)
        self.tab_widget.addTab(self.orders_tab, "Orders")

        # Metrics tab
        self.metrics_tab = MetricsTab(self.details, parent=self)
        self.tab_widget.addTab(self.metrics_tab, "Metrics")

        layout.addWidget(self.tab_widget)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        export_excel_btn = QPushButton("Export Excel")
        export_excel_btn.clicked.connect(self._export_excel)
        btn_layout.addWidget(export_excel_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _export_excel(self):
        """Export session details to Excel."""

        # Get orders data
        orders = self._get_orders_for_export()

        if not orders:
            QMessageBox.warning(
                self,
                "No Data",
                "No orders data available for export."
            )
            return

        # Ask for save location
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Session Details",
            f"session_{self.session_data['session_id']}.xlsx",
            "Excel Files (*.xlsx)"
        )

        if not filepath:
            return

        try:
            import pandas as pd

            # Convert orders to flat structure
            rows = []
            for order in orders:
                for item in order.get('items', []):
                    rows.append({
                        'Order Number': order['order_number'],
                        'Order Started': order.get('started_at', ''),
                        'Order Completed': order.get('completed_at', ''),
                        'Order Duration (s)': order.get('duration_seconds', 0),
                        'SKU': item['sku'],
                        'Quantity': item['quantity'],
                        'Scanned At': item.get('scanned_at', ''),
                        'Time from Start (s)': item.get('time_from_order_start_seconds', 0)
                    })

            df = pd.DataFrame(rows)

            # Write to Excel
            df.to_excel(filepath, index=False, sheet_name="Session Details")

            QMessageBox.information(
                self,
                "Success",
                f"Session details exported to:\n{filepath}"
            )

        except Exception as e:
            logger.error(f"Failed to export: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export session details:\n{str(e)}"
            )

    def _get_orders_for_export(self) -> list:
        """Get orders array for export."""

        # Try session_summary first (Phase 2b data)
        if 'session_summary' in self.details:
            orders = self.details['session_summary'].get('orders', [])
            if orders:
                return orders

        # Try packing_state
        if 'packing_state' in self.details:
            # Build from completed orders (less detailed)
            completed = self.details['packing_state'].get('completed', [])
            return completed

        return []

    def _build_partial_summary(self, packing_state: dict, session_info: dict) -> dict:
        """Build a minimal session_summary-compatible dict from packing_state for incomplete sessions.

        Called when session_summary.json does not yet exist (session ended without full completion).
        Computes the same metrics that generate_session_summary() would compute, but from the
        data available in packing_state.json.

        Returns an empty dict if there is insufficient data to compute any metrics.
        """
        completed_orders = packing_state.get('completed', [])
        if not completed_orders:
            return {}

        # Only orders with timing metadata contribute to metrics
        orders_with_timing = [o for o in completed_orders if isinstance(o, dict) and o.get('duration_seconds')]

        if not orders_with_timing:
            # No timing data — return minimal summary with just counts
            return {
                'metrics': {},
                'orders': [o for o in completed_orders if isinstance(o, dict)],
                'skipped_orders': [
                    {"order_number": n, "skipped_at": None, "status": "skipped"}
                    for n in packing_state.get('skipped_orders', [])
                ],
                'skipped_orders_count': len(packing_state.get('skipped_orders', [])),
                'completed_orders': len([o for o in completed_orders if isinstance(o, dict)]),
                'total_orders': packing_state.get('progress', {}).get('total_orders', 0),
                'started_at': session_info.get('started_at') or packing_state.get('started_at'),
                'status': 'incomplete',
            }

        # Compute the same metrics as generate_session_summary()
        timing_metrics = compute_order_timing_metrics(orders_with_timing)

        # Session duration from state timestamps (best-effort)
        started_at = session_info.get('started_at') or packing_state.get('started_at')
        last_updated = packing_state.get('last_updated')
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
                    total_items_packed = sum(o.get('items_count', 0) for o in orders_with_timing)
                    if total_items_packed > 0:
                        items_per_hour = round(total_items_packed / hours, 1)
            except (ValueError, TypeError):
                pass

        # Count in-progress orders from raw in_progress dict (exclude _timing key)
        raw_in_progress = packing_state.get('in_progress', {})
        in_progress_count = sum(1 for k in raw_in_progress if not k.startswith('_'))

        skipped_timing = packing_state.get('skipped_orders_timing', {})
        return {
            'status': 'incomplete',
            'started_at': started_at,
            'completed_at': last_updated,
            'duration_seconds': duration_seconds,
            'total_orders': packing_state.get('progress', {}).get('total_orders', 0),
            'completed_orders': len([o for o in completed_orders if isinstance(o, dict)]),
            'in_progress_orders': in_progress_count,
            'skipped_orders_count': len(packing_state.get('skipped_orders', [])),
            'metrics': {
                **timing_metrics,
                'orders_per_hour': orders_per_hour,
                'items_per_hour': items_per_hour,
            },
            'orders': [o for o in completed_orders if isinstance(o, dict)],
            'skipped_orders': [
                {"order_number": n, "skipped_at": skipped_timing.get(n), "status": "skipped"}
                for n in packing_state.get('skipped_orders', [])
            ],
        }

    def _is_standardized_data(self, data: dict) -> bool:
        """Check if session_data is in standardized format (has all required fields)."""
        required_fields = ['session_id', 'client_id', 'packing_list_name', 'status']
        return all(field in data for field in required_fields)

    def _build_details_from_standardized_data(self):
        """Build self.details from standardized session_data format."""
        from datetime import datetime

        data = self.session_data

        # Convert ISO timestamp strings to datetime objects if needed
        start_time = data.get('started_at')
        if start_time and isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time)
            except (ValueError, TypeError):
                pass

        end_time = data.get('ended_at')
        if end_time and isinstance(end_time, str):
            try:
                end_time = datetime.fromisoformat(end_time)
            except (ValueError, TypeError):
                pass

        # Build record in expected format
        record = {
            'session_id': data.get('session_id'),
            'client_id': data.get('client_id'),
            'packing_list_path': data.get('packing_list_name', ''),  # Name, not full path
            'packing_list_name': data.get('packing_list_name', ''),
            'worker_id': data.get('worker_id', 'Unknown'),
            'worker_name': data.get('worker_name', ''),
            'pc_name': data.get('pc_name', 'Unknown'),
            'start_time': start_time,
            'end_time': end_time,
            'duration_seconds': data.get('duration_seconds', 0),
            'total_orders': data.get('orders_total', 0),
            'completed_orders': data.get('orders_completed', 0),
            'in_progress_orders': data.get('in_progress_orders', 0),
            'skipped_orders_count': data.get('skipped_orders_count', 0),
            'total_items_packed': data.get('items_packed', 0)
        }

        # Load additional data from work_dir if available
        work_dir = data.get('work_dir')
        packing_state = {}
        session_summary = {}

        if work_dir:
            work_dir_path = Path(work_dir)

            # Load packing_state.json
            state_file = work_dir_path / "packing_state.json"
            if state_file.exists():
                try:
                    with open(state_file, 'r', encoding='utf-8') as f:
                        packing_state = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load packing_state.json: {e}")

            # Load session_summary.json
            summary_file = work_dir_path / "session_summary.json"
            if summary_file.exists():
                try:
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        session_summary = json.load(f)
                        orders_count = len(session_summary.get('orders', []))
                        logger.info(f"Loaded session_summary.json for session {data.get('session_id')} with {orders_count} orders")

                        # Update record with worker info from session_summary if available
                        if 'worker_id' in session_summary:
                            record['worker_id'] = session_summary['worker_id']
                        if 'worker_name' in session_summary:
                            record['worker_name'] = session_summary['worker_name']
                except Exception as e:
                    logger.warning(f"Failed to load session_summary.json: {e}")

        # Same partial-metrics fallback as the work_dir path: build from packing_state when
        # session_summary.json hasn't been created yet (incomplete session).
        if not session_summary and packing_state:
            session_info_hint = {'started_at': data.get('started_at')}
            session_summary = self._build_partial_summary(packing_state, session_info_hint)
            if session_summary:
                logger.info("Built partial session summary from packing_state.json (standardized path)")

        self.details = {
            'record': record,
            'packing_state': packing_state,
            'session_info': {},
            'session_summary': session_summary
        }

        logger.info(f"Built session details from standardized data for session: {data.get('session_id')}")
