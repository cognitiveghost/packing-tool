"""Orders Tab - Hierarchical view of orders and items with timing data"""

import logging
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class OrdersTab(QWidget):
    """Tab showing orders tree with items and timing"""

    def __init__(self, details: dict, parent=None):
        """
        Initialize Orders Tab.

        Args:
            details: Dict with session details (must include session_summary for Phase 2b data)
            parent: Parent widget
        """
        super().__init__(parent)

        self.details = details
        self.all_orders = []
        self.filtered_orders = []

        self._load_orders()
        self._init_ui()
        self._populate_tree()

    def _load_orders(self):
        """Load orders from session data."""

        # Try session_summary first (Phase 2b data with full timing)
        if 'session_summary' in self.details:
            orders = self.details['session_summary'].get('orders', [])
            skipped = self.details['session_summary'].get('skipped_orders', [])
            self.all_orders = list(orders) + list(skipped)
            logger.debug(f"Loaded {len(orders)} completed + {len(skipped)} skipped orders")
            return

        # Fallback: Try packing_state (less detailed)
        if 'packing_state' in self.details:
            completed = self.details['packing_state'].get('completed', [])
            skipped = [
                {"order_number": n, "skipped_at": None, "status": "skipped"}
                for n in self.details['packing_state'].get('skipped_orders', [])
            ]
            self.all_orders = [
                {
                    'order_number': order.get('order_number', 'Unknown'),
                    'completed_at': order.get('completed_at', ''),
                    'items_count': order.get('items_count', 0),
                    'duration_seconds': order.get('duration_seconds', 0),
                    'items': []
                }
                for order in completed
                if isinstance(order, dict)
            ] + skipped

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Top bar: Search + Actions
        top_bar = QHBoxLayout()

        top_bar.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by order number...")
        self.search_input.textChanged.connect(self._on_search)
        top_bar.addWidget(self.search_input)

        expand_btn = QPushButton("Expand All")
        expand_btn.clicked.connect(lambda: self.tree.expandAll())
        top_bar.addWidget(expand_btn)

        collapse_btn = QPushButton("Collapse All")
        collapse_btn.clicked.connect(lambda: self.tree.collapseAll())
        top_bar.addWidget(collapse_btn)

        layout.addLayout(top_bar)

        # Info label
        self.info_label = QLabel()
        layout.addWidget(self.info_label)

        # Tree widget — 6 columns (added "Flags" at the end)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "Order / Item",
            "Duration",
            "Count",
            "Started / Scanned",
            "Completed",
            "Flags",
        ])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(5, 140)
        layout.addWidget(self.tree)

    def _populate_tree(self):
        """Populate tree with orders."""
        self.tree.clear()

        # Apply filter
        search_term = self.search_input.text().strip().lower()

        if search_term:
            self.filtered_orders = [
                o for o in self.all_orders
                if search_term in str(o.get('order_number', '')).lower()
            ]
        else:
            self.filtered_orders = self.all_orders

        # Update info label
        if not self.all_orders:
            self.info_label.setText("No order data available for this session.")
            self.info_label.setStyleSheet("color: #888888; font-weight: bold;")
            return
        else:
            self.info_label.setText(f"Showing {len(self.filtered_orders)} of {len(self.all_orders)} orders")
            self.info_label.setStyleSheet("")

        # Add orders to tree
        for order in self.filtered_orders:
            is_skipped = order.get('status') == 'skipped'

            # Top level: Order
            order_item = QTreeWidgetItem(self.tree)

            order_label = order.get('order_number', 'Unknown')
            if is_skipped:
                order_label = f"[SKIPPED] {order_label}"
            order_item.setText(0, order_label)

            if is_skipped:
                # Skipped order — show skip time, no duration/items
                order_item.setText(1, "—")
                order_item.setText(2, "—")
                order_item.setText(3, self._format_timestamp(order.get('skipped_at', '')))
                order_item.setText(4, "—")
                order_item.setText(5, "⏭ skipped")
                grey = QColor(150, 150, 150)
                for col in range(6):
                    order_item.setForeground(col, grey)
            else:
                # Duration
                duration = order.get('duration_seconds', 0)
                order_item.setText(1, f"{duration}s ({duration/60:.1f}m)" if duration else "N/A")

                # Items count (actual scan events)
                items_count = order.get('items_count', len(order.get('items', [])))
                order_item.setText(2, f"{items_count} items")

                # Started
                order_item.setText(3, self._format_timestamp(order.get('started_at', '')))

                # Completed
                order_item.setText(4, self._format_timestamp(order.get('completed_at', '')))

                # Flags column: quality indicators
                flags = self._build_order_flags(order)
                order_item.setText(5, flags if flags else "✓ ok")

                # Colour the flags cell if there are quality issues
                if any(s in flags for s in ('⟲', 'manual', '+', '?')):
                    order_item.setForeground(5, QColor(200, 160, 0))

            # Make order row bold
            font = order_item.font(0)
            font.setBold(True)
            for col in range(6):
                order_item.setFont(col, font)

            if is_skipped:
                continue

            # --- Children: item scan records ---
            items = order.get('items', [])
            if items:
                for item in items:
                    item_node = QTreeWidgetItem(order_item)

                    sku = item.get('sku', 'Unknown')
                    method = item.get('confirmation_method', 'scanned')
                    prefix = "" if method == 'force_confirmed' else "→ "
                    item_node.setText(0, f"  {prefix}{sku}")

                    time_from_start = item.get('time_from_order_start_seconds', 0)
                    if time_from_start:
                        item_node.setText(1, f"+{time_from_start}s")

                    qty = item.get('quantity', 1)
                    item_node.setText(2, f"×{qty}")

                    item_node.setText(3, self._format_timestamp(item.get('scanned_at', '')))

                    # Show method in flags column
                    if method == 'force_confirmed':
                        item_node.setText(5, "manual")
                        item_node.setForeground(5, QColor(200, 120, 0))
                    else:
                        item_node.setText(5, "✓ scan")
            else:
                no_data_node = QTreeWidgetItem(order_item)
                no_data_node.setText(0, "  (Item details not available)")
                no_data_node.setForeground(0, Qt.GlobalColor.gray)

            # --- Quality summary sub-nodes (corrections, extras, unknowns) ---
            corrections = order.get('corrections', 0)
            extra_scans = order.get('extra_scans_count', 0)
            unknown_scans = order.get('unknown_scans_count', 0)
            first_scan = order.get('time_to_first_scan_seconds')

            if corrections:
                c_node = QTreeWidgetItem(order_item)
                c_node.setText(0, f"  ⟲ {corrections} scan correction(s) (Undo pressed)")
                c_node.setForeground(0, QColor(180, 120, 0))

            if extra_scans:
                e_node = QTreeWidgetItem(order_item)
                e_node.setText(0, f"  + {extra_scans} extra scan(s) (over-scanned SKU)")
                e_node.setForeground(0, QColor(160, 100, 0))

            if unknown_scans:
                u_node = QTreeWidgetItem(order_item)
                u_node.setText(0, f"  ? {unknown_scans} unknown scan(s) (wrong barcode)")
                u_node.setForeground(0, QColor(180, 60, 60))

            if first_scan is not None:
                fs_node = QTreeWidgetItem(order_item)
                fs_node.setText(0, f"  ⏱ First scan after {first_scan}s from order start")
                fs_node.setForeground(0, Qt.GlobalColor.gray)

        # Auto-expand if few orders
        if len(self.filtered_orders) <= 10:
            self.tree.expandAll()

    def _build_order_flags(self, order: dict) -> str:
        """Build a short flags string for the order's quality indicators."""
        parts = []
        corrections = order.get('corrections', 0)
        extra_scans = order.get('extra_scans_count', 0)
        unknown_scans = order.get('unknown_scans_count', 0)
        items = order.get('items', [])
        has_force = any(i.get('confirmation_method') == 'force_confirmed' for i in items)

        if has_force:
            parts.append("manual")
        if corrections:
            parts.append(f"⟲{corrections}")
        if extra_scans:
            parts.append(f"+{extra_scans} extra")
        if unknown_scans:
            parts.append(f"?{unknown_scans} unkn")
        return "  ".join(parts)

    def _on_search(self):
        """Handle search text change."""
        self._populate_tree()

    def _format_timestamp(self, ts: str) -> str:
        """Format ISO timestamp for display."""
        if not ts:
            return "N/A"

        try:
            ts_clean = ts.replace('Z', '+00:00')
            dt = datetime.fromisoformat(ts_clean)
            return dt.strftime("%H:%M:%S")
        except Exception:
            return ts
