from typing import Any

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget


class OrderTableModel(QAbstractTableModel):
    """
    A Qt Table Model to display order summary data from a pandas DataFrame.

    This class provides the necessary interface between a pandas DataFrame
    containing summarized order information and a QTableView widget. It handles
    data retrieval, header information, and cell styling based on order status.

    Attributes:
        _data (pd.DataFrame): The underlying DataFrame holding the order data.
    """
    def __init__(self, data: pd.DataFrame, parent: QWidget = None):
        """
        Initializes the OrderTableModel.

        Args:
            data (pd.DataFrame): The pandas DataFrame to be displayed.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of rows in the model.

        Args:
            parent (QModelIndex): The parent index.

        Returns:
            int: The number of rows in the DataFrame.
        """
        return self._data.shape[0]

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of columns in the model.

        Args:
            parent (QModelIndex): The parent index.

        Returns:
            int: The number of columns in the DataFrame.
        """
        return self._data.shape[1]

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """
        Returns the data for a given index and role.

        This method provides the text to be displayed and sets the background
        color for rows of 'Completed' orders.

        Args:
            index (QModelIndex): The index of the data to retrieve.
            role (int): The role for which data is requested (e.g., DisplayRole).

        Returns:
            Any: The data for the specified index and role, or None if invalid.
        """
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if role == Qt.DisplayRole:
            return str(self._data.iloc[row, col])

        if role == Qt.BackgroundRole:
            try:
                status_col_index = self.get_column_index('Status')
                if self._data.iloc[row, status_col_index] == 'Completed':
                    return QColor('lightgreen')
            except KeyError:
                pass  # 'Status' column might not exist

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> str | None:
        """
        Returns the header data for the table.

        Args:
            section (int): The row or column number.
            orientation (Qt.Orientation): The orientation (Horizontal or Vertical).
            role (int): The role for which data is requested.

        Returns:
            str | None: The column header text, or None for other cases.
        """
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return str(self._data.columns[section])
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        """
        Sets the data for a given index.

        This allows the model's data to be updated externally, for instance,
        when the status or progress of an order changes.

        Args:
            index (QModelIndex): The index of the data to set.
            value (Any): The new value.
            role (int): The role for which data is being set.

        Returns:
            bool: True if the data was set successfully, False otherwise.
        """
        if role == Qt.EditRole:
            row = index.row()
            col = index.column()
            self._data.iloc[row, col] = value
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Returns the item flags for a given index.

        Marks all items as editable to allow programmatic updates.

        Args:
            index (QModelIndex): The index of the item.

        Returns:
            Qt.ItemFlags: The flags for the item.
        """
        return super().flags(index) | Qt.ItemIsEditable

    def get_column_index(self, column_name: str) -> int:
        """
        Retrieves the numerical index for a given column name.

        Args:
            column_name (str): The name of the column.

        Returns:
            int: The index of the column, or -1 if not found.
        """
        try:
            return self._data.columns.get_loc(column_name)
        except KeyError:
            return -1
