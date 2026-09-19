"""Overview Tab - Session metadata and summary"""

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from shared.components.card import Card


class OverviewTab(QWidget):
    """Tab showing session overview and metadata, as two dl-row cards."""

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

        record = self.details.get("record")

        grid = QHBoxLayout()
        grid.addWidget(self._build_session_card(record))
        grid.addWidget(self._build_timing_card(record))
        layout.addLayout(grid)
        layout.addStretch()

    def _build_session_card(self, record: dict | None) -> Card:
        card = Card()
        card.add_text("Session", "label")

        if not record:
            return card

        card.add_row("Session ID", record.get("session_id", "Unknown"), mono=True)
        card.add_row("Client", f"CLIENT_{record.get('client_id', 'Unknown')}")

        packing_list_path = record.get("packing_list_path")
        list_name = Path(packing_list_path).stem if packing_list_path else "Unknown"
        card.add_row("Packing list", list_name)

        worker_name = record.get("worker_name", "")
        worker_id = record.get("worker_id", "")
        if worker_name:
            worker_display = (
                f"{worker_name} ({worker_id})" if worker_id else worker_name
            )
        elif worker_id:
            worker_display = worker_id
        else:
            worker_display = "Unknown"
        card.add_row("Worker", worker_display)

        card.add_row("PC", record.get("pc_name") or "Unknown", mono=True)
        return card

    def _build_timing_card(self, record: dict | None) -> Card:
        card = Card()
        card.add_text("Timing", "label")

        if not record:
            return card

        card.add_row("Started", self._format_datetime(record.get("start_time")))
        card.add_row("Completed", self._format_datetime(record.get("end_time")))

        # B2 draws Duration on an Active session as "3h 12m so far" -- a live
        # session has no duration_seconds yet, and dropping the row is how the
        # one number a supervisor came for goes missing.
        end_time = record.get("end_time")
        duration_seconds = record.get("duration_seconds") or _elapsed_seconds(
            record.get("start_time")
        )
        if duration_seconds:
            suffix = "" if end_time else " so far"
            card.add_row(
                "Duration", f"{self._format_duration(duration_seconds)}{suffix}"
            )
        else:
            card.add_row("Duration", "—")

        total_orders = record.get("total_orders", 0)
        completed_orders = record.get("completed_orders", 0)
        card.add_row("Orders packed", f"{completed_orders} / {total_orders}")
        card.add_row("Items packed", str(record.get("total_items_packed", 0)))
        return card

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


def _elapsed_seconds(start) -> int:
    """Seconds since `start`, which may be a datetime or an ISO string."""
    if not start:
        return 0
    if isinstance(start, str):
        try:
            start = datetime.fromisoformat(start)
        except ValueError:
            return 0
    if not isinstance(start, datetime):
        return 0
    # tzinfo of None gives a naive now, which is what a naive start needs.
    now = datetime.now(start.tzinfo)
    return max(0, int((now - start).total_seconds()))
