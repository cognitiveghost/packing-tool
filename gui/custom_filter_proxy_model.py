import pandas as pd
from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QWidget


class CustomFilterProxyModel(QSortFilterProxyModel):
    """
    A custom filter proxy model for advanced, multi-column filtering.

    This class extends QSortFilterProxyModel to provide a more sophisticated
    filtering mechanism tailored for the Packer's Assistant application. It
    allows filtering the main order table based on a single search term that is
    matched against the 'Order_Number', 'Status', and associated 'SKU' values
    for each order.

    Attributes:
        _processed_df (pd.DataFrame): A DataFrame containing the detailed order
                                      information, including SKUs.
        search_term (str): The current search term used for filtering.
    """
    def __init__(self, parent: QWidget = None):
        """
        Initializes the CustomFilterProxyModel.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self._processed_df = None
        self.search_term = ""

    def set_processed_df(self, df: pd.DataFrame):
        """
        Sets the DataFrame containing detailed order and SKU information.

        This DataFrame is used for the SKU-based search logic in the filter.

        Args:
            df (pd.DataFrame): The DataFrame with detailed order data.
        """
        self._processed_df = df

    def setFilterFixedString(self, text: str):
        """
        Sets the search term and triggers a filter invalidation.

        This method overrides the base class method to store the search term
        in a normalized (lowercase) format and then forces the model to
        re-evaluate its filter.

        Args:
            text (str): The search string entered by the user.
        """
        self.search_term = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """
        Determines whether a row should be included in the filtered view.

        This is the core filtering logic. It checks if the search term matches:
        1. The order number for the row.
        2. The status for the row.
        3. Any of the SKUs associated with the order number for that row.

        Args:
            source_row (int): The row number in the source model.
            source_parent (QModelIndex): The parent index in the source model.

        Returns:
            bool: True if the row should be included, False otherwise.
        """
        if not self.search_term:
            return True

        source_model = self.sourceModel()
        if source_model is None:
            return True

        # Get column indices from the source model
        order_col = source_model.get_column_index('Order_Number')
        status_col = source_model.get_column_index('Status')

        if order_col == -1 or status_col == -1:
            return True

        # Get data for the current row
        order_number_index = source_model.index(source_row, order_col, source_parent)
        status_index = source_model.index(source_row, status_col, source_parent)

        order_number_str = source_model.data(order_number_index, Qt.DisplayRole).lower()
        status_str = source_model.data(status_index, Qt.DisplayRole).lower()

        # 1. Check Order Number and Status
        if self.search_term in order_number_str or self.search_term in status_str:
            return True

        # 2. Check SKU from the detailed processed_df
        if self._processed_df is not None:
            current_order_number = source_model.data(order_number_index, Qt.DisplayRole)

            # This can be slow on very large datasets, but should be acceptable for typical packing lists.
            # It finds all rows in the detailed df matching the order number.
            order_items = self._processed_df[self._processed_df['Order_Number'] == current_order_number]

            # It then checks if the search term is present in any of the SKUs for that order.
            if order_items['SKU'].str.lower().str.contains(self.search_term, na=False).any():
                return True

        return False
