"""Metrics Tab - Performance statistics and rates"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class MetricsTab(QWidget):
    """Tab showing session performance metrics"""

    def __init__(self, details: dict, parent=None):
        """
        Initialize Metrics Tab.

        Args:
            details: Dict with session details (must include session_summary.metrics)
            parent: Parent widget
        """
        super().__init__(parent)

        self.details = details
        self._init_ui()

    def _init_ui(self):
        """Initialize UI."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll)

        # Check if metrics available
        metrics = self._get_metrics()
        session_summary = self.details.get('session_summary', {})
        is_incomplete = session_summary.get('status') == 'incomplete'

        if not metrics:
            no_data_label = QLabel(
                "Metrics not available\n\n"
                "Timing metrics are not available for this session."
            )
            no_data_label.setObjectName("no_metrics_label")
            no_data_label.setStyleSheet("color: #888888; font-weight: bold;")
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_data_label)
            layout.addStretch()
            return

        # Incomplete-session notice
        if is_incomplete:
            notice = QLabel(
                "⚠ Partial metrics — session was not fully completed.\n"
                "Only data from completed orders is shown."
            )
            notice.setObjectName("incomplete_session_notice")
            notice.setStyleSheet("color: #c87800; font-style: italic; padding: 4px;")
            notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(notice)

        # --- Order Metrics Group ---
        order_group = QGroupBox("Order Metrics")
        order_form = QFormLayout()

        order_form.addRow(
            "Average Time per Order:",
            QLabel(self._format_seconds(metrics.get('avg_time_per_order', 0)))
        )
        order_form.addRow(
            "Fastest Order:",
            QLabel(self._format_seconds(metrics.get('fastest_order_seconds', 0)))
        )
        order_form.addRow(
            "Slowest Order:",
            QLabel(self._format_seconds(metrics.get('slowest_order_seconds', 0)))
        )

        avg_first_scan = metrics.get('avg_time_to_first_scan', 0)
        if avg_first_scan:
            order_form.addRow(
                "Avg Time to First Scan:",
                QLabel(self._format_seconds(avg_first_scan))
            )

        order_group.setLayout(order_form)
        layout.addWidget(order_group)

        # --- Item Metrics Group ---
        item_group = QGroupBox("Item Metrics")
        item_form = QFormLayout()

        item_form.addRow(
            "Average Time per Item:",
            QLabel(self._format_seconds(metrics.get('avg_time_per_item', 0)))
        )

        item_group.setLayout(item_form)
        layout.addWidget(item_group)

        # --- Performance Rates Group ---
        rate_group = QGroupBox("Performance Rates")
        rate_form = QFormLayout()

        rate_form.addRow(
            "Orders per Hour:",
            QLabel(f"{metrics.get('orders_per_hour', 0):.1f}")
        )
        rate_form.addRow(
            "Items per Hour:",
            QLabel(f"{metrics.get('items_per_hour', 0):.1f}")
        )

        rate_group.setLayout(rate_form)
        layout.addWidget(rate_group)

        # --- Accuracy / Quality Group ---
        quality_group = QGroupBox("Scan Quality")
        quality_form = QFormLayout()

        total_corrections = metrics.get('total_corrections', 0)
        avg_corrections = metrics.get('avg_corrections_per_order', 0)
        quality_form.addRow(
            "Total Scan Corrections:",
            QLabel(f"{total_corrections}")
        )
        quality_form.addRow(
            "Avg Corrections per Order:",
            QLabel(f"{avg_corrections:.2f}")
        )

        total_extra = metrics.get('total_extra_scans', 0)
        quality_form.addRow(
            "Total Extra Scans:",
            QLabel(f"{total_extra}")
        )

        total_unknown = metrics.get('total_unknown_scans', 0)
        quality_form.addRow(
            "Total Unknown Scans:",
            QLabel(f"{total_unknown}")
        )

        quality_group.setLayout(quality_form)
        layout.addWidget(quality_group)

        # --- Skipped Orders Group (show only if any exist) ---
        skipped_orders = session_summary.get('skipped_orders', [])
        skipped_count = session_summary.get('skipped_orders_count', len(skipped_orders))
        if skipped_count or skipped_orders:
            skipped_group = QGroupBox("Skipped Orders")
            skipped_form = QFormLayout()

            skipped_form.addRow(
                "Skipped Orders Count:",
                QLabel(str(skipped_count))
            )

            for entry in skipped_orders:
                order_num = entry.get('order_number', '?')
                skipped_at = entry.get('skipped_at')
                label_text = self._format_timestamp(skipped_at) if skipped_at else "—"
                skipped_form.addRow(f"  {order_num}:", QLabel(label_text))

            skipped_group.setLayout(skipped_form)
            layout.addWidget(skipped_group)

        layout.addStretch()

    def _get_metrics(self) -> dict:
        """Get metrics from session data."""
        if 'session_summary' in self.details:
            return self.details['session_summary'].get('metrics', {})
        return {}

    def _format_seconds(self, seconds: float) -> str:
        """Format seconds as readable time."""
        if not seconds:
            return "N/A"

        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m ({seconds:.0f}s)"
        else:
            hours = seconds / 3600
            minutes = (seconds % 3600) / 60
            return f"{hours:.1f}h {minutes:.0f}m"

    def _format_timestamp(self, ts: str) -> str:
        """Format an ISO timestamp for display."""
        if not ts:
            return "—"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return ts
