# metadata_dialog.py
"""
Dialog window for displaying video metadata.
"""
import logging
from typing import Dict, Any, Optional

from PySide6 import QtCore, QtGui, QtWidgets

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
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        self._metadata = metadata_dict
        self._setup_ui()
        self.populate_data()

        # Enable context menu for the table
        if hasattr(self, 'tableWidget'):
            self.tableWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            self.tableWidget.customContextMenuRequested.connect(self._show_table_context_menu)

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
        self.tableWidget.setRowCount(0) 
        if not self._metadata:
            logger.warning("No metadata provided to MetadataDialog.")
            return

        self.tableWidget.setRowCount(len(self._metadata))
        row = 0
        for key, value in self._metadata.items():
            key_item = QtWidgets.QTableWidgetItem(str(key))

            value_str = f"{value:.3f}" if isinstance(value, float) else str(value)
            value_item = QtWidgets.QTableWidgetItem(value_str)
            value_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

            # --- Tooltip for File Path ---
            if str(key).lower() == "file path":
                value_item.setToolTip(value_str) # Tooltip will show the full value_str
                logger.debug(f"Tooltip set for File Path: {value_str}")

            self.tableWidget.setItem(row, 0, key_item)
            self.tableWidget.setItem(row, 1, value_item)
            row += 1

        logger.debug(f"Populated MetadataDialog table with {row} items.")


    @QtCore.Slot(QtCore.QPoint)
    def _show_table_context_menu(self, pos: QtCore.QPoint) -> None:
        """Shows a context menu for the table, offering a copy action."""
        if not hasattr(self, 'tableWidget'):
            return

        selected_items = self.tableWidget.selectedItems()
        if not selected_items:
            return

        # We are interested in the item in the "Value" column (index 1) of the selected row.
        # Since selection is by row, we can iterate through selected items to find one in column 1.
        item_to_copy = None
        for item in selected_items:
            if item.column() == 1: # "Value" column
                item_to_copy = item
                break
        
        if item_to_copy is None and selected_items: # Fallback: if no specific value cell is part of selection model, take first selected item's text.
            # This might happen if selection model is complex or only row is selected.
            # For row selection, if we want to always copy the "Value" of the selected row:
            current_row = self.tableWidget.currentRow()
            if current_row >= 0:
                item_to_copy = self.tableWidget.item(current_row, 1) # Get item from value column

        if item_to_copy:
            menu = QtWidgets.QMenu(self)
            copy_action = menu.addAction("Copy Value")
            action = menu.exec(self.tableWidget.mapToGlobal(pos))

            if action == copy_action:
                clipboard = QtGui.QGuiApplication.clipboard()
                if clipboard:
                    text_to_copy = item_to_copy.text()
                    # If it's the file path, we prefer the full path from tooltip if available and different
                    if item_to_copy.toolTip() and item_to_copy.toolTip() != text_to_copy:
                        key_item_text = self.tableWidget.item(item_to_copy.row(), 0).text() # Get corresponding key
                        if str(key_item_text).lower() == "file path":
                            text_to_copy = item_to_copy.toolTip()
                            logger.debug(f"Copying full file path from tooltip: {text_to_copy}")
                    
                    clipboard.setText(text_to_copy)
                    logger.info(f"Copied to clipboard: '{text_to_copy[:50]}...'")