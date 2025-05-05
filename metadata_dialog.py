# metadata_dialog.py
"""
Dialog window for displaying video metadata.
"""
import logging
from typing import Dict, Any, Optional

from PySide6 import QtCore, QtWidgets

logger = logging.getLogger(__name__)

class MetadataDialog(QtWidgets.QDialog):
    """
    A simple dialog box to display key-value metadata pairs in a table.
    """

    def __init__(self, metadata_dict: Dict[str, Any], parent: Optional[QtWidgets.QWidget] = None):
        """
        Initializes the dialog.

        Args:
            metadata_dict: A dictionary containing the metadata to display.
            parent: The parent widget, if any.
        """
        super().__init__(parent)
        self.setWindowTitle("Video Information")
        self.setMinimumWidth(450) # Ensure dialog isn't too small
        self.setMinimumHeight(300) # Ensure dialog isn't too small
        # Allow the dialog to expand if placed in a layout that allows it
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        self._metadata = metadata_dict
        self._setup_ui()
        self.populate_data()
        logger.debug("MetadataDialog initialized and UI set up.")

    def _setup_ui(self) -> None:
        """Creates and arranges the UI elements within the dialog."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10) # Padding around the layout
        layout.setSpacing(10) # Spacing between widgets

        # --- Table Widget ---
        self.tableWidget = QtWidgets.QTableWidget()
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Property", "Value"])
        self.tableWidget.verticalHeader().setVisible(False) # Hide row numbers
        self.tableWidget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers) # Read-only
        self.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.tableWidget.setAlternatingRowColors(True) # Improve readability
        self.tableWidget.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone) # Show full text, prevent '...'

        # Set column resize modes
        header = self.tableWidget.horizontalHeader()
        # Property column adjusts to content size
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        # Value column takes remaining space
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.tableWidget)

        # --- Buttons ---
        # Standard button box with just a Close button
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        # Connect the button box's rejected signal (emitted by Close) to the dialog's reject slot
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

    def populate_data(self) -> None:
        """Fills the table widget with the metadata dictionary."""
        self.tableWidget.setRowCount(0) # Clear existing rows before populating
        if not self._metadata:
            logger.warning("No metadata provided to MetadataDialog.")
            return

        self.tableWidget.setRowCount(len(self._metadata))
        row = 0
        for key, value in self._metadata.items():
            # Create item for the property name (key)
            key_item = QtWidgets.QTableWidgetItem(str(key))
            # Ensure item flags indicate it's not editable (redundant with table setting, but safe)
            key_item.setFlags(key_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)

            # Create item for the property value
            # Format value nicely before creating the item
            if isinstance(value, float):
                value_str = f"{value:.3f}" # Format floats to 3 decimal places
            else:
                value_str = str(value) # Convert other types to string

            value_item = QtWidgets.QTableWidgetItem(value_str)
            # Ensure item flags indicate it's not editable
            value_item.setFlags(value_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)

            # Add items to the current row
            self.tableWidget.setItem(row, 0, key_item)
            self.tableWidget.setItem(row, 1, value_item)
            row += 1

        # Optional: Uncomment to resize rows to fit content height if needed
        # self.tableWidget.resizeRowsToContents()
        logger.debug(f"Populated MetadataDialog table with {row} items.")