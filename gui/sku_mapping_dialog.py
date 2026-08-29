"""
SKU Mapping Dialog - Centralized Barcode-to-SKU mapping management.

Phase 1.3: Redesigned to use ProfileManager for centralized storage on file server.
All changes are synchronized across all PCs accessing the same client.
"""

import logging

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from gui.theme import current_tokens
from shared.theme import set_button_role

logger = logging.getLogger(__name__)


class SKUMappingDialog(QDialog):
    """
    A dialog window for users to manage Barcode-to-SKU mappings.

    Phase 1.3: Uses ProfileManager for centralized storage on file server.
    Changes are synchronized across all PCs with file locking.

    Provides a table view to display the current mappings and buttons to
    add, edit, or delete entries. Changes are saved to the centralized
    file server when the user clicks "Save & Close".
    """

    def __init__(self, client_id: str, profile_manager, parent=None):
        """
        Initializes the dialog with centralized storage.

        Args:
            client_id: Client identifier for loading/saving mappings
            profile_manager: ProfileManager instance for centralized storage
            parent: The parent widget
        """
        super().__init__(parent)
        self.setWindowTitle(f"SKU Mapping - Client {client_id}")
        self.setMinimumSize(700, 500)

        self.client_id = client_id
        self.profile_manager = profile_manager

        # Load current mappings from file server
        try:
            self.current_map = self.profile_manager.load_sku_mapping(client_id).copy()
            logger.info(f"Loaded {len(self.current_map)} SKU mappings for client {client_id}")
        except Exception as e:
            logger.exception("Failed to load SKU mappings")
            self.current_map = {}
            QMessageBox.warning(
                self,
                "Load Error",
                f"Could not load existing SKU mappings:\n\n{e}\n\nStarting with empty mappings."
            )

        self._init_ui()
        self._populate_table()

    def _init_ui(self):
        """Sets up the UI components and layout."""
        layout = QVBoxLayout(self)

        # Header with info
        header_layout = QVBoxLayout()
        title_label = QLabel(f"SKU Mapping for Client {self.client_id}")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(title_label)

        info_label = QLabel(
            "Map product barcodes to internal SKU codes. "
            "Changes are saved to the file server and synchronized across all PCs."
        )
        info_label.setStyleSheet(f"color: {current_tokens().text_secondary}; font-size: 9pt;")
        info_label.setWordWrap(True)
        header_layout.addWidget(info_label)

        layout.addLayout(header_layout)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Product Barcode", "Internal SKU"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # Status label
        self.status_label = QLabel(f"{len(self.current_map)} mapping(s) loaded from file server")
        self.status_label.setStyleSheet(f"color: {current_tokens().text_secondary}; font-size: 9pt;")
        layout.addWidget(self.status_label)

        # CRUD Buttons
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add Mapping")
        add_button.clicked.connect(self._add_item)
        edit_button = QPushButton("Edit Selected")
        edit_button.clicked.connect(self._edit_item)
        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self._delete_item)

        self.refresh_button = QPushButton("Reload from Server")
        self.refresh_button.clicked.connect(self._reload_from_server)
        self.refresh_button.setToolTip("Reload mappings from file server (discard unsaved changes)")

        button_layout.addWidget(add_button)
        button_layout.addWidget(edit_button)
        button_layout.addWidget(delete_button)
        button_layout.addStretch()
        button_layout.addWidget(self.refresh_button)
        layout.addLayout(button_layout)

        # Dialog Buttons
        dialog_button_layout = QHBoxLayout()
        dialog_button_layout.addStretch()

        save_button = QPushButton("Save & Close")
        save_button.setDefault(True)
        save_button.clicked.connect(self._save_and_close)
        set_button_role(save_button, "primary")

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        dialog_button_layout.addWidget(save_button)
        dialog_button_layout.addWidget(cancel_button)
        layout.addLayout(dialog_button_layout)

    def _populate_table(self):
        """Fills the table with data from the current map."""
        self.table.setSortingEnabled(False)  # Disable while populating
        self.table.setRowCount(0)  # Clear table

        for barcode, sku in sorted(self.current_map.items()):
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)
            self.table.setItem(row_position, 0, QTableWidgetItem(barcode))
            self.table.setItem(row_position, 1, QTableWidgetItem(sku))

        self.table.setSortingEnabled(True)  # Re-enable sorting
        self.status_label.setText(f"{len(self.current_map)} mapping(s)")

    def _add_item(self):
        """Handles the logic for adding a new mapping entry."""
        barcode, ok1 = QInputDialog.getText(
            self,
            "Add Mapping",
            "Enter Product Barcode:\n(This will be scanned from the product)"
        )

        if not (ok1 and barcode):
            return

        barcode = barcode.strip()
        if not barcode:
            return

        if barcode in self.current_map:
            QMessageBox.warning(
                self,
                "Duplicate Barcode",
                f"Barcode '{barcode}' already exists in the mapping.\n\n"
                f"Current SKU: {self.current_map[barcode]}\n\n"
                f"Use 'Edit' to change it."
            )
            return

        sku, ok2 = QInputDialog.getText(
            self,
            "Add Mapping",
            f"Enter Internal SKU for barcode '{barcode}':"
        )

        if not (ok2 and sku):
            return

        sku = sku.strip()
        if not sku:
            return

        self.current_map[barcode] = sku
        self._populate_table()
        self.status_label.setText(f"{len(self.current_map)} mapping(s) - Not saved yet")

        logger.info(f"Added SKU mapping: {barcode} -> {sku}")

    def _edit_item(self):
        """Handles the logic for editing an existing entry."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(
                self,
                "Selection Error",
                "Please select a row to edit."
            )
            return

        row_index = selected_rows[0].row()
        barcode_item = self.table.item(row_index, 0)
        old_sku_item = self.table.item(row_index, 1)

        barcode = barcode_item.text()
        old_sku = old_sku_item.text()

        new_sku, ok = QInputDialog.getText(
            self,
            "Edit SKU",
            f"Barcode: {barcode}\n\nEnter new Internal SKU:",
            text=old_sku
        )

        if ok and new_sku:
            new_sku = new_sku.strip()
            if new_sku and new_sku != old_sku:
                self.current_map[barcode] = new_sku
                self._populate_table()
                self.status_label.setText(f"{len(self.current_map)} mapping(s) - Not saved yet")
                # Reselect the edited row
                self.table.selectRow(row_index)

                logger.info(f"Updated SKU mapping: {barcode}: {old_sku} -> {new_sku}")

    def _delete_item(self):
        """Handles the logic for deleting an entry."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(
                self,
                "Selection Error",
                "Please select a row to delete."
            )
            return

        row_index = selected_rows[0].row()
        barcode = self.table.item(row_index, 0).text()
        sku = self.table.item(row_index, 1).text()

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete this mapping?\n\n"
            f"Barcode: {barcode}\n"
            f"SKU: {sku}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes and barcode in self.current_map:
            del self.current_map[barcode]
            self._populate_table()
            self.status_label.setText(f"{len(self.current_map)} mapping(s) - Not saved yet")

            logger.info(f"Deleted SKU mapping: {barcode}")

    def _reload_from_server(self):
        """Reload mappings from file server, discarding unsaved changes."""
        if len(self.current_map) > 0:
            reply = QMessageBox.question(
                self,
                "Reload from Server",
                "This will discard any unsaved changes.\n\n"
                "Are you sure you want to reload from the file server?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            self.current_map = self.profile_manager.load_sku_mapping(self.client_id).copy()
            self._populate_table()
            self.status_label.setText(f"{len(self.current_map)} mapping(s) loaded from file server")

            logger.info(f"Reloaded {len(self.current_map)} SKU mappings from server")

        except Exception as e:
            logger.exception("Failed to reload SKU mappings")
            QMessageBox.critical(
                self,
                "Reload Error",
                f"Failed to reload mappings from server:\n\n{e}"
            )

    def _save_and_close(self):
        """
        Saves the changes to the file server and closes the dialog.
        """
        try:
            # Save to ProfileManager (centralized storage with file locking)
            success = self.profile_manager.save_sku_mapping(self.client_id, self.current_map)

            if success:
                logger.info(f"Saved {len(self.current_map)} SKU mappings to file server")
                QMessageBox.information(
                    self,
                    "Saved",
                    f"Successfully saved {len(self.current_map)} mapping(s) to file server.\n\n"
                    f"Changes are now synchronized across all PCs."
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Save Failed",
                    "Failed to save mappings to file server.\n\n"
                    "Please check your network connection and try again."
                )

        except Exception as e:
            logger.exception("Error saving SKU mappings")
            QMessageBox.critical(
                self,
                "Save Error",
                f"An error occurred while saving:\n\n{e}\n\n"
                f"Your changes were NOT saved."
            )

    def get_mappings(self) -> dict[str, str]:
        """
        Returns the current mappings.

        Returns:
            Dictionary of barcode -> SKU mappings
        """
        return self.current_map.copy()
