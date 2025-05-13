# preferences_dialog.py
"""
Preferences dialog for customizing application visual settings.
"""
import logging
from typing import Dict, Any, Optional # Removed unused Callable

from PySide6 import QtCore, QtGui, QtWidgets

# Ensure tooltips use the default palette to avoid inheriting widget styles
app = QtWidgets.QApplication.instance()
if app is not None:
    QtWidgets.QToolTip.setPalette(app.palette())

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
                f"QPushButton {{ background-color: {self._color.name()}; color: {text_color}; border: 1px solid gray; }}"
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
    settingsApplied = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(450) # Adjusted for potentially more content with tabs
        self.setMinimumHeight(350)

        self.setting_widgets: Dict[str, QtWidgets.QWidget] = {}
        self.tab_widget: Optional[QtWidgets.QTabWidget] = None # For easy access if needed later

        self._setup_ui()
        self._load_settings()
        logger.debug("PreferencesDialog initialized with tabs.")

    def _setup_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(10)

        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create and add tabs
        self._create_tracks_tab()
        self._create_origin_tab()
        self._create_scales_tab() # New tab

        # Standard Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        apply_button = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Apply)
        if apply_button: # Ensure button exists
            apply_button.clicked.connect(self._apply_settings)
        main_layout.addWidget(button_box)

    # --- Helper function to add rows to a form layout (reusable) ---
    def _add_setting_to_form(self, form_layout: QtWidgets.QFormLayout,
                             label_text: str, setting_key: str,
                             widget_type: str, widget_params: Optional[Dict] = None) -> None:
        widget: Optional[QtWidgets.QWidget] = None
        if widget_type == "color":
            widget = ColorButton()
        elif widget_type == "double_spinbox":
            widget = QtWidgets.QDoubleSpinBox()
            if widget_params:
                widget.setMinimum(widget_params.get("min_val", 0.0))
                widget.setMaximum(widget_params.get("max_val", 100.0))
                widget.setDecimals(widget_params.get("decimals", 1))
                widget.setSingleStep(widget_params.get("step", 0.5))
        elif widget_type == "int_spinbox": # New helper for integer spinbox
            widget = QtWidgets.QSpinBox()
            if widget_params:
                widget.setMinimum(widget_params.get("min_val", 1))
                widget.setMaximum(widget_params.get("max_val", 100))
                widget.setSingleStep(widget_params.get("step", 1))

        if widget:
            form_layout.addRow(label_text, widget)
            self.setting_widgets[setting_key] = widget
        else:
            logger.warning(f"Unsupported widget_type '{widget_type}' for setting '{setting_key}'.")

    def _create_tracks_tab(self) -> None:
        tracks_tab_widget = QtWidgets.QWidget()
        tracks_layout = QtWidgets.QFormLayout(tracks_tab_widget)
        tracks_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        tracks_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        tracks_layout.setHorizontalSpacing(10)
        tracks_layout.setVerticalSpacing(8)

        self._add_setting_to_form(tracks_layout, "Active Track Marker (Current Frame):", settings_manager.KEY_ACTIVE_CURRENT_MARKER_COLOR, "color")
        self._add_setting_to_form(tracks_layout, "Active Track Marker (Other Frames):", settings_manager.KEY_ACTIVE_MARKER_COLOR, "color")
        self._add_setting_to_form(tracks_layout, "Active Track Line:", settings_manager.KEY_ACTIVE_LINE_COLOR, "color")
        self._add_setting_to_form(tracks_layout, "Inactive Track Marker (Current Frame):", settings_manager.KEY_INACTIVE_CURRENT_MARKER_COLOR, "color")
        self._add_setting_to_form(tracks_layout, "Inactive Track Marker (Other Frames):", settings_manager.KEY_INACTIVE_MARKER_COLOR, "color")
        self._add_setting_to_form(tracks_layout, "Inactive Track Line:", settings_manager.KEY_INACTIVE_LINE_COLOR, "color")
        self._add_setting_to_form(tracks_layout, "Track Marker Size (pixels):", settings_manager.KEY_MARKER_SIZE, "double_spinbox", {"min_val": 1.0, "max_val": 20.0, "decimals": 1, "step": 0.5})
        self._add_setting_to_form(tracks_layout, "Track Line Width (pixels):", settings_manager.KEY_LINE_WIDTH, "double_spinbox", {"min_val": 0.5, "max_val": 10.0, "decimals": 1, "step": 0.5})

        if self.tab_widget:
            self.tab_widget.addTab(tracks_tab_widget, "Tracks")

    def _create_origin_tab(self) -> None:
        origin_tab_widget = QtWidgets.QWidget()
        origin_layout = QtWidgets.QFormLayout(origin_tab_widget)
        origin_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        origin_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        origin_layout.setHorizontalSpacing(10)
        origin_layout.setVerticalSpacing(8)

        self._add_setting_to_form(origin_layout, "Origin Marker Color:", settings_manager.KEY_ORIGIN_MARKER_COLOR, "color")
        self._add_setting_to_form(origin_layout, "Origin Marker Size (pixels):", settings_manager.KEY_ORIGIN_MARKER_SIZE, "double_spinbox", {"min_val": 1.0, "max_val": 20.0, "decimals": 1, "step": 0.5})

        if self.tab_widget:
            self.tab_widget.addTab(origin_tab_widget, "Origin")

    def _create_scales_tab(self) -> None: # NEW METHOD
        scales_tab_widget = QtWidgets.QWidget()
        scales_main_layout = QtWidgets.QVBoxLayout(scales_tab_widget) # Main layout for this tab
        scales_main_layout.setSpacing(15)

        # --- Feature Scale Line Group ---
        feature_line_group = QtWidgets.QGroupBox("Defined Feature Scale Line Visuals")
        feature_line_layout = QtWidgets.QFormLayout(feature_line_group)
        feature_line_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        feature_line_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        feature_line_layout.setHorizontalSpacing(10)
        feature_line_layout.setVerticalSpacing(8)

        self._add_setting_to_form(feature_line_layout, "Line Color:", settings_manager.KEY_FEATURE_SCALE_LINE_COLOR, "color")
        self._add_setting_to_form(feature_line_layout, "Text Color:", settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_COLOR, "color")
        self._add_setting_to_form(feature_line_layout, "Text Size (pt):", settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_SIZE, "int_spinbox", {"min_val": 6, "max_val": 72, "step": 1})
        self._add_setting_to_form(feature_line_layout, "Line Width (px):", settings_manager.KEY_FEATURE_SCALE_LINE_WIDTH, "double_spinbox", {"min_val": 0.5, "max_val": 10.0, "decimals": 1, "step": 0.5})
        scales_main_layout.addWidget(feature_line_group)

        # --- Scale Bar Group ---
        scale_bar_group = QtWidgets.QGroupBox("On-Screen Scale Bar Visuals")
        scale_bar_layout = QtWidgets.QFormLayout(scale_bar_group)
        scale_bar_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        scale_bar_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        scale_bar_layout.setHorizontalSpacing(10)
        scale_bar_layout.setVerticalSpacing(8)

        self._add_setting_to_form(scale_bar_layout, "Bar & Text Color:", settings_manager.KEY_SCALE_BAR_COLOR, "color")
        # Note: Scale bar placement is complex and not handled by a simple QSetting.
        # Its text size is currently fixed or derived from the widget's font.
        # Its border color is also fixed in the widget.
        # We are only adding color for the bar itself for now.
        scales_main_layout.addWidget(scale_bar_group)

        scales_main_layout.addStretch() # Push groups upwards

        if self.tab_widget:
            self.tab_widget.addTab(scales_tab_widget, "Scales")


    def _load_settings(self) -> None:
        logger.debug("Loading settings into PreferencesDialog widgets.")
        for key, widget in self.setting_widgets.items():
            # get_setting should return the correctly typed value (e.g., QColor for colors)
            # or the correctly typed default value from DEFAULT_SETTINGS.
            current_value_from_manager = settings_manager.get_setting(key)
            
            try:
                if isinstance(widget, ColorButton):
                    if isinstance(current_value_from_manager, QtGui.QColor):
                        if current_value_from_manager.isValid():
                            widget.set_color(current_value_from_manager)
                        else:
                            # This case implies the default QColor in DEFAULT_SETTINGS was invalid, which shouldn't happen.
                            logger.error(f"Default QColor for key '{key}' is invalid. Check DEFAULT_SETTINGS.")
                            # Fallback to a hardcoded valid color for safety.
                            widget.set_color(QtGui.QColor("black")) 
                    else:
                        # This means get_setting didn't return a QColor for a key mapped to a ColorButton.
                        logger.error(f"Type mismatch for ColorButton key '{key}'. Expected QColor, got {type(current_value_from_manager)}. Value: '{current_value_from_manager}'. Check DEFAULT_SETTINGS for this key.")
                        # Fallback to a hardcoded valid color
                        widget.set_color(QtGui.QColor("black")) 

                elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                    if isinstance(current_value_from_manager, (float, int)):
                        widget.setValue(float(current_value_from_manager))
                    else:
                        logger.warning(f"Type mismatch for QDoubleSpinBox key '{key}'. Expected float/int, got {type(current_value_from_manager)}. Value: '{current_value_from_manager}'. Using default from map.")
                        default_val = settings_manager.DEFAULT_SETTINGS.get(key, 0.0) # Fallback default
                        widget.setValue(float(default_val))

                elif isinstance(widget, QtWidgets.QSpinBox): 
                    if isinstance(current_value_from_manager, int):
                        widget.setValue(current_value_from_manager)
                    elif isinstance(current_value_from_manager, float): # Allow float to int conversion if it's whole number
                        widget.setValue(int(current_value_from_manager))
                    else:
                        logger.warning(f"Type mismatch for QSpinBox key '{key}'. Expected int, got {type(current_value_from_manager)}. Value: '{current_value_from_manager}'. Using default from map.")
                        default_val = settings_manager.DEFAULT_SETTINGS.get(key, 0) # Fallback default
                        widget.setValue(int(default_val))

            except Exception as e: # Broad exception catch for safety during widget value setting
                logger.error(f"Error setting widget value for key '{key}' with value '{current_value_from_manager}': {e}", exc_info=True)
                # Attempt to set a fallback default from DEFAULT_SETTINGS if widget specific logic failed
                try:
                    fallback_default = settings_manager.DEFAULT_SETTINGS.get(key)
                    if fallback_default is not None:
                        if isinstance(widget, ColorButton) and isinstance(fallback_default, QtGui.QColor):
                            widget.set_color(fallback_default)
                        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                            widget.setValue(float(fallback_default))
                        elif isinstance(widget, QtWidgets.QSpinBox):
                            widget.setValue(int(fallback_default))
                except Exception as fallback_e:
                    logger.error(f"Failed to set even fallback default for key '{key}': {fallback_e}")


    def _apply_settings(self) -> bool:
        logger.info("Applying preferences...")
        try:
            for key, widget in self.setting_widgets.items():
                value_to_save: Any = None
                if isinstance(widget, ColorButton):
                    value_to_save = widget.color().name() 
                elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                    value_to_save = widget.value()
                elif isinstance(widget, QtWidgets.QSpinBox): # For integer spinboxes
                    value_to_save = widget.value()

                if value_to_save is not None:
                    settings_manager.set_setting(key, value_to_save)
            
            logger.info("Preferences applied and saved.")
            self.settingsApplied.emit()
            return True
        except Exception as e:
            logger.exception("Error applying settings.")
            QtWidgets.QMessageBox.warning(self, "Error", f"Could not apply settings:\n{e}")
            return False

    def accept(self) -> None:
        logger.debug("PreferencesDialog accepted (OK clicked).")
        if self._apply_settings():
            super().accept()

    def reject(self) -> None:
        logger.debug("PreferencesDialog rejected (Cancel clicked).")
        super().reject()