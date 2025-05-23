# preferences_dialog.py
"""
Preferences dialog for customizing application visual settings.
"""
import logging
from typing import Dict, Any, Optional

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
            brightness = (self._color.red() * 299 + self._color.green() * 587 + self._color.blue() * 114) / 1000
            text_color = "black" if brightness > 128 else "white"
            self.setStyleSheet(
                f"QPushButton {{ background-color: {self._color.name()}; color: {text_color}; border: 1px solid gray; }}"
            )

    def color(self) -> QtGui.QColor:
        return self._color

    def select_color(self) -> None:
        dialog = QtWidgets.QColorDialog(self._color, self.window())
        dialog.setWindowTitle("Select Color")
        dialog.setStyleSheet("") # Ensure system default style for color dialog
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_color = dialog.selectedColor()
            if new_color.isValid():
                self.set_color(new_color)
                self.colorChanged.emit(new_color)

class PreferencesDialog(QtWidgets.QDialog):
    settingsApplied = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(500) 
        self.setMinimumHeight(500) # Increased slightly for new tab

        self.setting_widgets: Dict[str, QtWidgets.QWidget] = {}
        self.tab_widget: Optional[QtWidgets.QTabWidget] = None

        self._setup_ui()
        self._load_settings()
        logger.debug("PreferencesDialog initialized with tabs.")

    def _setup_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(10)

        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self._create_tracks_tab()
        self._create_origin_tab()
        self._create_scales_tab()
        self._create_info_overlays_tab()
        self._create_measurement_lines_tab() # <-- NEW: Call to create the Measurement Lines tab

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        apply_button = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Apply)
        if apply_button:
            apply_button.clicked.connect(self._apply_settings)
        main_layout.addWidget(button_box)

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
        elif widget_type == "int_spinbox":
            widget = QtWidgets.QSpinBox()
            if widget_params:
                widget.setMinimum(widget_params.get("min_val", 1))
                widget.setMaximum(widget_params.get("max_val", 100))
                widget.setSingleStep(widget_params.get("step", 1))
        elif widget_type == "checkbox":
            widget = QtWidgets.QCheckBox()
            # CheckBox text is set by the label_text in QFormLayout.addRow

        if widget:
            if widget_params and "tooltip" in widget_params:
                 widget.setToolTip(widget_params.get("tooltip"))
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

    def _create_scales_tab(self) -> None:
        scales_tab_widget = QtWidgets.QWidget()
        scales_main_layout = QtWidgets.QVBoxLayout(scales_tab_widget)
        scales_main_layout.setSpacing(15)

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
        self._add_setting_to_form(feature_line_layout, "Show End Ticks:", settings_manager.KEY_FEATURE_SCALE_LINE_SHOW_TICKS, "checkbox", {"tooltip": "Show short perpendicular ticks at the ends of the feature scale line."})
        self._add_setting_to_form(feature_line_layout, "Tick Length Factor:", settings_manager.KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR, "double_spinbox", {"min_val": 0.5, "max_val": 10.0, "decimals": 1, "step": 0.5, "tooltip": "Length of end ticks as a multiple of the line width (e.g., 3.0 means ticks are 3x line width)."})
        scales_main_layout.addWidget(feature_line_group)

        scale_bar_group = QtWidgets.QGroupBox("On-Screen Scale Bar Visuals")
        scale_bar_layout = QtWidgets.QFormLayout(scale_bar_group)
        scale_bar_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        scale_bar_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        scale_bar_layout.setHorizontalSpacing(10)
        scale_bar_layout.setVerticalSpacing(8)

        self._add_setting_to_form(scale_bar_layout, "Bar & Text Color:", settings_manager.KEY_SCALE_BAR_COLOR, "color")
        self._add_setting_to_form(scale_bar_layout, "Bar Height (px):", settings_manager.KEY_SCALE_BAR_RECT_HEIGHT, "int_spinbox", {"min_val": 1, "max_val": 20, "step": 1, "tooltip": "Height of the actual scale bar rectangle."})
        self._add_setting_to_form(scale_bar_layout, "Text Font Size (pt):", settings_manager.KEY_SCALE_BAR_TEXT_FONT_SIZE, "int_spinbox", {"min_val": 6, "max_val": 72, "step": 1})
        scales_main_layout.addWidget(scale_bar_group)

        scales_main_layout.addStretch()

        if self.tab_widget:
            self.tab_widget.addTab(scales_tab_widget, "Scales")

    def _create_info_overlays_tab(self) -> None:
        info_tab_widget = QtWidgets.QWidget()
        info_main_layout = QtWidgets.QVBoxLayout(info_tab_widget)
        info_main_layout.setSpacing(15) 

        filename_group = QtWidgets.QGroupBox("Filename Overlay")
        filename_layout = QtWidgets.QFormLayout(filename_group)
        filename_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        filename_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        filename_layout.setHorizontalSpacing(10); filename_layout.setVerticalSpacing(8)
        self._add_setting_to_form(filename_layout, "Text Color:", settings_manager.KEY_INFO_OVERLAY_FILENAME_COLOR, "color")
        self._add_setting_to_form(filename_layout, "Font Size (pt):", settings_manager.KEY_INFO_OVERLAY_FILENAME_FONT_SIZE, "int_spinbox", {"min_val": 6, "max_val": 48, "step": 1})
        info_main_layout.addWidget(filename_group)

        time_group = QtWidgets.QGroupBox("Time Overlay (Current / Total)")
        time_layout = QtWidgets.QFormLayout(time_group)
        time_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        time_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        time_layout.setHorizontalSpacing(10); time_layout.setVerticalSpacing(8)
        self._add_setting_to_form(time_layout, "Text Color:", settings_manager.KEY_INFO_OVERLAY_TIME_COLOR, "color")
        self._add_setting_to_form(time_layout, "Font Size (pt):", settings_manager.KEY_INFO_OVERLAY_TIME_FONT_SIZE, "int_spinbox", {"min_val": 6, "max_val": 48, "step": 1})
        info_main_layout.addWidget(time_group)

        frame_group = QtWidgets.QGroupBox("Frame Number Overlay (Current / Total)")
        frame_layout = QtWidgets.QFormLayout(frame_group)
        frame_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        frame_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        frame_layout.setHorizontalSpacing(10); frame_layout.setVerticalSpacing(8)
        self._add_setting_to_form(frame_layout, "Text Color:", settings_manager.KEY_INFO_OVERLAY_FRAME_NUMBER_COLOR, "color")
        self._add_setting_to_form(frame_layout, "Font Size (pt):", settings_manager.KEY_INFO_OVERLAY_FRAME_NUMBER_FONT_SIZE, "int_spinbox", {"min_val": 6, "max_val": 48, "step": 1})
        info_main_layout.addWidget(frame_group)

        info_main_layout.addStretch() 

        if self.tab_widget:
            self.tab_widget.addTab(info_tab_widget, "Info Overlays")

    # --- NEW METHOD: _create_measurement_lines_tab ---
    def _create_measurement_lines_tab(self) -> None:
        measure_lines_tab_widget = QtWidgets.QWidget()
        measure_lines_main_layout = QtWidgets.QVBoxLayout(measure_lines_tab_widget)
        measure_lines_main_layout.setSpacing(15)

        # Group for Line Appearance
        line_appearance_group = QtWidgets.QGroupBox("Line Appearance")
        line_appearance_layout = QtWidgets.QFormLayout(line_appearance_group)
        line_appearance_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        line_appearance_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        line_appearance_layout.setHorizontalSpacing(10)
        line_appearance_layout.setVerticalSpacing(8)

        self._add_setting_to_form(line_appearance_layout, "Line Color:", settings_manager.KEY_MEASUREMENT_LINE_COLOR, "color", {"tooltip": "Default color for measurement lines."})
        self._add_setting_to_form(line_appearance_layout, "Active Line Color:", settings_manager.KEY_MEASUREMENT_LINE_ACTIVE_COLOR, "color", {"tooltip": "Color for the currently selected/active measurement line."})
        self._add_setting_to_form(line_appearance_layout, "Line Width (px):", settings_manager.KEY_MEASUREMENT_LINE_WIDTH, "double_spinbox", {"min_val": 0.5, "max_val": 10.0, "decimals": 1, "step": 0.5, "tooltip": "Width of measurement lines."})
        measure_lines_main_layout.addWidget(line_appearance_group)

        # Group for Length Label Appearance
        length_label_group = QtWidgets.QGroupBox("Length Label Appearance")
        length_label_layout = QtWidgets.QFormLayout(length_label_group)
        length_label_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        length_label_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        length_label_layout.setHorizontalSpacing(10)
        length_label_layout.setVerticalSpacing(8)
        
        self._add_setting_to_form(length_label_layout, "Show Length Labels:", settings_manager.KEY_SHOW_MEASUREMENT_LINE_LENGTHS, "checkbox", {"tooltip": "Globally show or hide length labels for all measurement lines."})
        self._add_setting_to_form(length_label_layout, "Text Color:", settings_manager.KEY_MEASUREMENT_LINE_LENGTH_TEXT_COLOR, "color", {"tooltip": "Color of the length label text."})
        self._add_setting_to_form(length_label_layout, "Font Size (pt):", settings_manager.KEY_MEASUREMENT_LINE_LENGTH_TEXT_FONT_SIZE, "int_spinbox", {"min_val": 6, "max_val": 48, "step": 1, "tooltip": "Font size for the length label text."})
        measure_lines_main_layout.addWidget(length_label_group)

        measure_lines_main_layout.addStretch()

        if self.tab_widget:
            self.tab_widget.addTab(measure_lines_tab_widget, "Measurement Lines")
    # --- END NEW METHOD ---

    def _load_settings(self) -> None:
        logger.debug("Loading settings into PreferencesDialog widgets.")
        for key, widget in self.setting_widgets.items():
            current_value_from_manager = settings_manager.get_setting(key)
            try:
                if isinstance(widget, ColorButton):
                    if isinstance(current_value_from_manager, QtGui.QColor) and current_value_from_manager.isValid():
                        widget.set_color(current_value_from_manager)
                    else: 
                        default_color = settings_manager.DEFAULT_SETTINGS.get(key, QtGui.QColor("black"))
                        logger.warning(f"Invalid or wrong type for ColorButton key '{key}'. Value: '{current_value_from_manager}'. Using default: {default_color.name()}.")
                        widget.set_color(default_color)
                elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                    if isinstance(current_value_from_manager, (float, int)):
                        widget.setValue(float(current_value_from_manager))
                    else:
                        default_val = float(settings_manager.DEFAULT_SETTINGS.get(key, 0.0))
                        logger.warning(f"Type mismatch for QDoubleSpinBox key '{key}'. Using default {default_val}. Value: {current_value_from_manager}")
                        widget.setValue(default_val)
                elif isinstance(widget, QtWidgets.QSpinBox):
                    if isinstance(current_value_from_manager, int):
                        widget.setValue(current_value_from_manager)
                    elif isinstance(current_value_from_manager, float) and current_value_from_manager.is_integer():
                        widget.setValue(int(current_value_from_manager))
                    else: 
                        try:
                            widget.setValue(int(float(str(current_value_from_manager))))
                        except (ValueError, TypeError):
                            default_val = int(settings_manager.DEFAULT_SETTINGS.get(key, 0))
                            logger.warning(f"Type mismatch/conversion error for QSpinBox key '{key}'. Using default {default_val}. Value: {current_value_from_manager}")
                            widget.setValue(default_val)
                elif isinstance(widget, QtWidgets.QCheckBox):
                    if isinstance(current_value_from_manager, bool):
                        widget.setChecked(current_value_from_manager)
                    else: 
                        str_val = str(current_value_from_manager).lower()
                        if str_val == "true": widget.setChecked(True)
                        elif str_val == "false": widget.setChecked(False)
                        else:
                            try:
                                widget.setChecked(bool(int(float(str_val))))
                            except (ValueError, TypeError):
                                default_val = bool(settings_manager.DEFAULT_SETTINGS.get(key, False))
                                logger.warning(f"Type mismatch/conversion error for QCheckBox key '{key}'. Using default {default_val}. Value: {current_value_from_manager}")
                                widget.setChecked(default_val)
            except Exception as e:
                logger.error(f"Error setting widget value for key '{key}' with value '{current_value_from_manager}': {e}", exc_info=True)
                if isinstance(widget, ColorButton): widget.set_color(QtGui.QColor("black"))
                elif isinstance(widget, QtWidgets.QDoubleSpinBox): widget.setValue(0.0)
                elif isinstance(widget, QtWidgets.QSpinBox): widget.setValue(0)
                elif isinstance(widget, QtWidgets.QCheckBox): widget.setChecked(False)


    def _apply_settings(self) -> bool:
        logger.info("Applying preferences...")
        try:
            for key, widget in self.setting_widgets.items():
                value_to_save: Any = None
                if isinstance(widget, ColorButton):
                    value_to_save = widget.color()
                elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                    value_to_save = widget.value()
                elif isinstance(widget, QtWidgets.QSpinBox):
                    value_to_save = widget.value()
                elif isinstance(widget, QtWidgets.QCheckBox):
                    value_to_save = widget.isChecked()

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