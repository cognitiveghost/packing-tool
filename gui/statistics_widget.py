"""The Statistics screen: session totals, by-courier cards, and the SKU table.

Draws what packing_tool.session_stats computes; carries no aggregation of its
own (see that module's docstring for why it isn't shared/stats_manager.py).
"""

from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.theme import current_tokens
from packing_tool.session_stats import courier_totals, session_totals, sku_summary
from shared.components import Card, StatCard, StatePanel
from shared.theme import StatusChip

_SKU_CHIP = {
    "packed": ("status_success", "Packed", False, False),
    "partial": ("status_warning", "Partial", True, False),
    "pending": ("text_secondary", "Pending", False, False),
}

_TOTALS_CARDS = (
    ("orders", "Orders"),
    ("completed", "Completed"),
    ("items", "Items"),
    ("unique_skus", "Unique SKUs"),
    ("progress_pct", "Progress"),
)


class StatisticsWidget(QWidget):
    """The Statistics screen. `update_from` fills it; `show_empty` clears it.

    Attributes:
        cards: the session-totals StatCards, keyed by session_stats' field names.
        courier_layout: the row the by-courier StatCards are added to.
        sku_table: the SKU summary table.
        state_panel: shown instead of `content` when there is no session.
        content: the scrollable totals/courier/SKU sections.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.stack = QStackedWidget()

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # --- Session totals ---
        totals_card = Card(margins=(12, 12, 12, 12), spacing=8)
        totals_row = QHBoxLayout()
        totals_row.setSpacing(16)
        self.cards = {}
        for key, label in _TOTALS_CARDS:
            card = StatCard("0", label)
            self.cards[key] = card
            totals_row.addWidget(card)
        totals_row.addStretch()
        totals_card.add_widget(_wrap(totals_row))
        scroll_layout.addWidget(totals_card)

        # --- By courier ---
        self._courier_card = Card(margins=(12, 12, 12, 12), spacing=8)
        self.courier_layout = QHBoxLayout()
        self.courier_layout.setSpacing(16)
        self._courier_card.add_widget(_wrap(self.courier_layout))
        scroll_layout.addWidget(self._courier_card)

        # --- SKU summary ---
        sku_card = Card(margins=(12, 12, 12, 12), spacing=8)
        self.sku_table = QTableWidget()
        self.sku_table.setColumnCount(4)
        self.sku_table.setHorizontalHeaderLabels(
            ["SKU", "Product", "Total qty", "Status"]
        )
        self.sku_table.horizontalHeader().setStretchLastSection(True)
        self.sku_table.setAlternatingRowColors(True)
        self.sku_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sku_table.setSelectionMode(QTableWidget.NoSelection)
        sku_card.add_widget(self.sku_table)
        scroll_layout.addWidget(sku_card)

        scroll.setWidget(scroll_widget)
        content_layout.addWidget(scroll)

        self.state_panel = StatePanel(
            "No session open",
            "Load a packing list to see this session's totals.",
            action_text="Open a packing list",
        )

        self.stack.addWidget(self.content)
        self.stack.addWidget(self.state_panel)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

        self.show_empty()

    def update_from(self, df, session_packing_state: dict) -> None:
        """Refresh every section from the current session's DataFrame and state."""
        state = session_packing_state or {}
        totals = session_totals(df, state.get("completed_orders", []))
        for key, _label in _TOTALS_CARDS:
            value = totals[key]
            self.cards[key].set_value(
                f"{value}%" if key == "progress_pct" else str(value)
            )

        while self.courier_layout.count():
            item = self.courier_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        for row in courier_totals(df):
            self.courier_layout.addWidget(
                StatCard(str(row["orders"]), f"{row['courier']} · orders", small=True)
            )

        rows = sku_summary(df, state)
        self.sku_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self.sku_table.setItem(index, 0, QTableWidgetItem(row["sku"]))
            self.sku_table.setItem(index, 1, QTableWidgetItem(row["product"]))
            self.sku_table.setItem(index, 2, QTableWidgetItem(str(row["required"])))
            role, text, live, manual = _SKU_CHIP[row["state"]]
            self.sku_table.setCellWidget(
                index,
                3,
                StatusChip(role, text, current_tokens(), live=live, manual=manual),
            )
        self.sku_table.resizeColumnsToContents()

        self.stack.setCurrentWidget(self.content)

    def show_empty(self) -> None:
        """No session loaded: show the state panel instead of the totals."""
        self.stack.setCurrentWidget(self.state_panel)


def _wrap(layout) -> QWidget:
    """A plain QWidget holding a pre-built layout, for Card.add_widget."""
    widget = QWidget()
    widget.setLayout(layout)
    return widget
