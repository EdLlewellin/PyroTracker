# preferences_dialog.py
"""
Preferences dialog for customizing application visual settings.
"""
import logging
from typing import Dict, Any, Optional # Removed unused Callable

from PySide6 import QtCore, QtGui, QtWidgets

import settings_manager # Assumes settings_manager defines the KEY_* constants

logger = logging.getLogger(__name__)

class ColorButton(QtWidgets.QPushButton):
    """A button that displays a color and opens a QColorDialog on click."""
    colorChanged = QtCore.Signal(QtGui.QColor) # Signal emitted when color changes via dialog

    def __init__(self, initial_color: QtGui.QColor = QtGui.QColor("white"), parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._color = QtGui.QColor() # Internal storage for the current color
        self.set_color(initial_color) # Set initial color and appearance
        self.clicked.connect(self.select_color)
        self.setToolTip("Click to select color")
        self.setFixedSize(QtCore.QSize(50, 25)) # Fixed size for consistency

    def set_color(self, color: QtGui.QColor) -> None:
        """Sets the button's background color, text color, and internal state."""
        if color.isValid() and color != self._color:
            self._color = color
            # Set text color based on background brightness for readability
            brightness = (self._color.red() * 299 + self._color.green() * 587 + self._color.blue() * 114) / 1000
            text_color = "black" if brightness > 128 else "white"
            # Update stylesheet in one go
            self.setStyleSheet(
                f"background-color: {self._color.name()}; "
                f"color: {text_color}; "
                f"border: 1px solid gray;"
            )
            # Optional: Display the hex code on the button
            # self.setText(self._color.name())

    def color(self) -> QtGui.QColor:
        """Returns the current QColor object."""
        return self._color

    def select_color(self) -> None:
        """Opens a QColorDialog to allow the user to select a new color."""
        # Create a dialog instance separate from the button to avoid inheriting styles
        dialog = QtWidgets.QColorDialog(self._color, self.window())
        dialog.setWindowTitle("Select Color")
        dialog.setStyleSheet("")  # Clear any inherited stylesheet rules
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_color = dialog.selectedColor()
            if new_color.isValid():
                self.set_color(new_color)
                self.colorChanged.emit(new_color)  # Emit signal if color changed

class PreferencesDialog(QtWidgets.QDialog):
    """Dialog for editing application preferences stored via settings_manager."""

    # Signal emitted when settings are successfully applied (via OK or Apply)
    settingsApplied = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(400)

        # Dictionary to hold references to the input widgets, keyed by setting key
        self.setting_widgets: Dict[str, QtWidgets.QWidget] = {}

        self._setup_ui()
        self._load_settings()
        logger.debug("PreferencesDialog initialized.")

    def _setup_ui(self) -> None:
        """Creates the UI layout and widgets."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(15) # Spacing between group boxes/widgets

        # --- Visuals Group ---
        visuals_group = QtWidgets.QGroupBox("Track Visuals")
        visuals_layout = QtWidgets.QFormLayout(visuals_group)
        visuals_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        visuals_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        visuals_layout.setHorizontalSpacing(10) # Spacing between labels and fields
        visuals_layout.setVerticalSpacing(8)   # Spacing between rows

        # --- Helper functions to add rows to the form layout ---
        def add_color_setting(label_text: str, setting_key: str) -> None:
            """Adds a label and ColorButton row for a color setting."""
            color_button = ColorButton()
            visuals_layout.addRow(label_text, color_button)
            self.setting_widgets[setting_key] = color_button

        def add_spinbox_setting(label_text: str, setting_key: str, min_val: float, max_val: float, decimals: int, step: float) -> None:
            """Adds a label and QDoubleSpinBox row for a numeric setting."""
            spin_box = QtWidgets.QDoubleSpinBox()
            spin_box.setMinimum(min_val)
            spin_box.setMaximum(max_val)
            spin_box.setDecimals(decimals)
            spin_box.setSingleStep(step)
            visuals_layout.addRow(label_text, spin_box)
            self.setting_widgets[setting_key] = spin_box
        # --- End Helper functions ---

        # Add settings rows using helpers and keys from settings_manager
        add_color_setting("Active Track Marker (Current Frame):", settings_manager.KEY_ACTIVE_CURRENT_MARKER_COLOR)
        add_color_setting("Active Track Marker (Other Frames):", settings_manager.KEY_ACTIVE_MARKER_COLOR)
        add_color_setting("Active Track Line:", settings_manager.KEY_ACTIVE_LINE_COLOR)
        add_color_setting("Inactive Track Marker (Current Frame):", settings_manager.KEY_INACTIVE_CURRENT_MARKER_COLOR)
        add_color_setting("Inactive Track Marker (Other Frames):", settings_manager.KEY_INACTIVE_MARKER_COLOR)
        add_color_setting("Inactive Track Line:", settings_manager.KEY_INACTIVE_LINE_COLOR)
        add_spinbox_setting("Track Marker Size (pixels):", settings_manager.KEY_MARKER_SIZE, 1.0, 20.0, 1, 0.5)
        add_spinbox_setting("Track Line Width (pixels):", settings_manager.KEY_LINE_WIDTH, 0.5, 10.0, 1, 0.5)

        # Add a separator row within the form layout for visual grouping
        separator_label = QtWidgets.QLabel("--- Origin Marker ---")
        separator_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        visuals_layout.addRow(separator_label) # Spans both columns

        add_color_setting("Origin Marker Color:", settings_manager.KEY_ORIGIN_MARKER_COLOR)
        add_spinbox_setting("Origin Marker Size (pixels):", settings_manager.KEY_ORIGIN_MARKER_SIZE, 1.0, 20.0, 1, 0.5)

        main_layout.addWidget(visuals_group)
        main_layout.addStretch() # Pushes elements upwards

        # --- Standard Buttons (OK, Cancel, Apply) ---
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self.accept) # OK clicked
        button_box.rejected.connect(self.reject) # Cancel clicked

        # Connect the Apply button specifically to the _apply_settings slot
        apply_button = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Apply)
        apply_button.clicked.connect(self._apply_settings)

        main_layout.addWidget(button_box)

    def _load_settings(self) -> None:
        """Loads current settings from settings_manager into the UI widgets."""
        logger.debug("Loading settings into PreferencesDialog widgets.")
        for key, widget in self.setting_widgets.items():
            current_value = settings_manager.get_setting(key)
            try:
                if isinstance(widget, ColorButton):
                    # Attempt to create a QColor from the stored value (likely a string name)
                    color = QtGui.QColor(current_value)
                    if color.isValid():
                         widget.set_color(color)
                    else:
                         logger.warning(f"Invalid color value '{current_value}' for key '{key}' in settings.")
                         # Optionally set a default color here if loading fails
                elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                     widget.setValue(float(current_value))
                # Add handlers for other widget types here if needed (e.g., QCheckBox, QLineEdit)

            except (ValueError, TypeError, AttributeError) as e:
                 # Catch potential errors during conversion or if value is None/unexpected type
                 logger.warning(f"Could not load value for key '{key}' from setting '{current_value}': {e}")
                 # Optionally set a default value in the widget here

    def _apply_settings(self) -> bool:
        """Reads values from UI widgets and saves them using settings_manager. Returns True on success."""
        logger.info("Applying preferences...")
        try:
            for key, widget in self.setting_widgets.items():
                value_to_save: Any = None
                if isinstance(widget, ColorButton):
                    # Store color as its hex name string (e.g., '#ffffff') for robustness
                    value_to_save = widget.color().name()
                elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                    value_to_save = widget.value()
                # Add handlers for other widget types here if needed

                if value_to_save is not None:
                    settings_manager.set_setting(key, value_to_save)

            logger.info("Preferences applied and saved.")
            self.settingsApplied.emit() # Notify other parts of the application
            return True
        except Exception as e:
             # Catch broad exceptions during saving process (e.g., QSettings issues)
             logger.exception("Error applying settings.") # Logs traceback
             QtWidgets.QMessageBox.warning(self, "Error", f"Could not apply settings:\n{e}")
             return False

    def accept(self) -> None:
        """Applies settings and then closes the dialog if successful."""
        logger.debug("PreferencesDialog accepted (OK clicked).")
        if self._apply_settings():
            # Only call the base class accept (which closes the dialog) if applying settings succeeded
            super().accept()

    def reject(self) -> None:
        """Closes the dialog without applying any pending changes."""
        logger.debug("PreferencesDialog rejected (Cancel clicked).")
        super().reject() # Closes the dialog