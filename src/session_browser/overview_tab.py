"""Overview Tab - Session metadata and summary"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel,
    QGroupBox
)

from datetime import datetime


class OverviewTab(QWidget):
    """Tab showing session overview and metadata"""

    def __init__(self, details: dict, parent=None):
        """
        Initialize Overview Tab.

        Args:
            details: Dict with session details from SessionHistoryManager
            parent: Parent widget
        """
        super().__init__(parent)

        self.details = details
        self._init_ui()

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Session Info Group
        session_group = QGroupBox("Session Information")
        session_form = QFormLayout()

        record = self.details.get('record')

        if record:
            session_form.addRow("Session ID:", QLabel(record.get('session_id', 'Unknown')))
            session_form.addRow("Client:", QLabel(f"CLIENT_{record.get('client_id', 'Unknown')}"))

            # Packing list
            packing_list_path = record.get('packing_list_path')
            if packing_list_path:
                from pathlib import Path
                list_name = Path(packing_list_path).stem
            else:
                list_name = "Unknown"
            session_form.addRow("Packing List:", QLabel(list_name))

            # Worker
            worker_name = record.get('worker_name', '')
            worker_id = record.get('worker_id', '')
            if worker_name:
                worker_display = f"{worker_name} ({worker_id})" if worker_id else worker_name
            elif worker_id:
                worker_display = worker_id
            else:
                worker_display = "Unknown"
            session_form.addRow("Worker:", QLabel(worker_display))

            # PC
            pc = record.get('pc_name') or "Unknown"
            session_form.addRow("PC:", QLabel(pc))

        session_group.setLayout(session_form)
        layout.addWidget(session_group)

        # Timing Group
        timing_group = QGroupBox("Timing")
        timing_form = QFormLayout()

        if record:
            # Started
            started = self._format_datetime(record.get('start_time'))
            timing_form.addRow("Started:", QLabel(started))

            # Completed
            completed = self._format_datetime(record.get('end_time'))
            timing_form.addRow("Completed:", QLabel(completed))

            # Duration
            duration_seconds = record.get('duration_seconds')
            if duration_seconds:
                duration = self._format_duration(duration_seconds)
                timing_form.addRow("Duration:", QLabel(duration))

        timing_group.setLayout(timing_form)
        layout.addWidget(timing_group)

        # Progress Group
        progress_group = QGroupBox("Progress")
        progress_form = QFormLayout()

        if record:
            total_orders = record.get('total_orders', 0)
            completed_orders = record.get('completed_orders', 0)
            in_progress_orders = record.get('in_progress_orders', 0)
            total_items = record.get('total_items_packed', 0)

            progress_form.addRow(
                "Orders:",
                QLabel(f"{completed_orders} / {total_orders}")
            )
            progress_form.addRow(
                "Items:",
                QLabel(str(total_items))
            )

            # Status — count skipped orders toward completion
            skipped_orders_count = record.get('skipped_orders_count', 0)
            if total_orders > 0 and (completed_orders + skipped_orders_count) >= total_orders:
                status = "Complete"
            else:
                status = f"Incomplete ({in_progress_orders} in progress)"
            progress_form.addRow("Status:", QLabel(status))

        progress_group.setLayout(progress_form)
        layout.addWidget(progress_group)

        layout.addStretch()

    def _format_datetime(self, dt) -> str:
        """Format datetime for display."""
        if not dt:
            return "N/A"

        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        return str(dt)

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if not seconds:
            return "N/A"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
