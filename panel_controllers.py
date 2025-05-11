# panel_controllers.py
"""
Contains controller classes for managing UI logic for various panels
in the MainWindow.
"""
import logging
from typing import Optional, TYPE_CHECKING, Dict
from PySide6 import QtCore, QtGui, QtWidgets

# Import project-specific modules
from coordinates import CoordinateSystem, CoordinateTransformer # For CoordinatePanelController
from interactive_image_view import InteractionMode      # For CoordinatePanelController

if TYPE_CHECKING:
    # These are only for type hinting to avoid circular imports
    from main_window import MainWindow
    from scale_manager import ScaleManager
    from interactive_image_view import InteractiveImageView

logger = logging.getLogger(__name__)

# UI logic for scale panel

class ScalePanelController(QtCore.QObject):
    """
    Manages the UI logic for the Scale Configuration panel.
    """
    def __init__(self,
                 scale_manager: 'ScaleManager',
                 image_view: 'InteractiveImageView',
                 scale_m_per_px_input: QtWidgets.QLineEdit,
                 scale_px_per_m_input: QtWidgets.QLineEdit,
                 scale_reset_button: QtWidgets.QPushButton,
                 scale_display_meters_checkbox: QtWidgets.QCheckBox,
                 show_scale_bar_checkbox: QtWidgets.QCheckBox,
                 parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)

        self._scale_manager = scale_manager
        self._image_view = image_view
        self._scale_m_per_px_input = scale_m_per_px_input
        self._scale_px_per_m_input = scale_px_per_m_input
        self._scale_reset_button = scale_reset_button
        self._scale_display_meters_checkbox = scale_display_meters_checkbox
        self._show_scale_bar_checkbox = show_scale_bar_checkbox

        self._block_scale_signals: bool = False
        self._video_loaded: bool = False # Internal state, updated by MainWindow

        # Connect signals from UI elements to controller slots
        self._scale_m_per_px_input.editingFinished.connect(self._on_scale_m_per_px_editing_finished)
        self._scale_px_per_m_input.editingFinished.connect(self._on_scale_px_per_m_editing_finished)
        self._scale_reset_button.clicked.connect(self._on_scale_reset_clicked)
        self._scale_display_meters_checkbox.toggled.connect(self._on_display_units_toggled)
        self._show_scale_bar_checkbox.toggled.connect(self._on_show_scale_bar_toggled)

        # MainWindow will connect these external signals:
        # self._scale_manager.scaleOrUnitChanged.connect(self.update_ui_from_manager)
        # self._image_view.viewTransformChanged.connect(self._on_view_transform_changed)

    def set_video_loaded_status(self, is_loaded: bool) -> None:
        """Updates the controller's knowledge of video load status."""
        if self._video_loaded != is_loaded:
            self._video_loaded = is_loaded
            self.update_ui_from_manager() # Update UI enable/disable states

    @QtCore.Slot()
    def _on_scale_m_per_px_editing_finished(self) -> None:
        if self._block_scale_signals:
            return
        if not self._scale_m_per_px_input:
            return

        text = self._scale_m_per_px_input.text()
        try:
            if not text:
                other_text_empty = True
                if self._scale_px_per_m_input and self._scale_px_per_m_input.text():
                    other_text_empty = False
                
                if other_text_empty:
                    self._scale_manager.set_scale(None)
                elif self._scale_manager.get_scale_m_per_px() is not None:
                     self._scale_manager.set_scale(None)
                return

            value = float(text)
            if value > 0.0:
                self._scale_manager.set_scale(value)
            elif value == 0.0:
                self._scale_manager.set_scale(None)
            else:
                logger.warning(f"Invalid (negative) scale input for m/px: '{text}'. Reverting UI.")
                self.update_ui_from_manager()
        except ValueError:
            logger.warning(f"Invalid float conversion for m/px: '{text}'. Reverting UI.")
            self.update_ui_from_manager()

    @QtCore.Slot()
    def _on_scale_px_per_m_editing_finished(self) -> None:
        if self._block_scale_signals:
            return
        if not self._scale_px_per_m_input:
            return

        text = self._scale_px_per_m_input.text()
        try:
            if not text:
                other_text_empty = True
                if self._scale_m_per_px_input and self._scale_m_per_px_input.text():
                    other_text_empty = False
                
                if other_text_empty:
                    self._scale_manager.set_scale(None)
                elif self._scale_manager.get_scale_m_per_px() is not None: # Check if scale was previously set
                     self._scale_manager.set_scale(None)
                return

            value = float(text)
            if value > 0.0:
                m_per_px = 1.0 / value
                self._scale_manager.set_scale(m_per_px)
            elif value == 0.0:
                self._scale_manager.set_scale(None)
            else: # Negative
                logger.warning(f"Invalid (negative) scale input for px/m: '{text}'. Reverting UI.")
                self.update_ui_from_manager()
        except ValueError:
            logger.warning(f"Invalid float conversion for px/m: '{text}'. Reverting UI.")
            self.update_ui_from_manager()

    @QtCore.Slot()
    def _on_scale_reset_clicked(self) -> None:
        logger.debug("Scale reset button clicked.")
        self._scale_manager.reset()

    @QtCore.Slot(bool)
    def _on_display_units_toggled(self, checked: bool) -> None:
        if self._scale_display_meters_checkbox:
            if self._scale_display_meters_checkbox.isEnabled():
                self._scale_manager.set_display_in_meters(checked)
            else:
                logger.warning("Display units toggled while checkbox was disabled. Forcing manager state.")
                self._scale_manager.set_display_in_meters(False)

    @QtCore.Slot(bool)
    def _on_show_scale_bar_toggled(self, checked: bool) -> None:
        if not (self._image_view and self._scale_manager and self._show_scale_bar_checkbox):
            logger.warning("_on_show_scale_bar_toggled skipped: Components not ready.")
            return

        logger.debug(f"'Show Scale Bar' checkbox toggled to: {checked}")
        scale_is_set = self._scale_manager.get_scale_m_per_px() is not None

        if self._show_scale_bar_checkbox.isEnabled() and scale_is_set:
            self._image_view.set_scale_bar_visibility(checked)
            if checked:
                self._image_view.update_scale_bar_dimensions(self._scale_manager.get_scale_m_per_px())
        elif not scale_is_set:
            self._image_view.set_scale_bar_visibility(False)
            self._show_scale_bar_checkbox.setChecked(False)
            self._show_scale_bar_checkbox.setEnabled(False)

    @QtCore.Slot()
    def _on_view_transform_changed(self) -> None:
        if not (self._image_view and self._scale_manager and self._show_scale_bar_checkbox):
            logger.debug("_on_view_transform_changed skipped: Components not ready.")
            return

        scale_is_set = self._scale_manager.get_scale_m_per_px() is not None
        scale_bar_should_be_visible = self._show_scale_bar_checkbox.isChecked()

        if self._video_loaded and scale_is_set and scale_bar_should_be_visible:
            logger.debug("View transform changed, updating scale bar dimensions.")
            self._image_view.update_scale_bar_dimensions(self._scale_manager.get_scale_m_per_px())
        elif self._image_view._scale_bar_widget.isVisible() and (not scale_is_set or not scale_bar_should_be_visible):
            logger.debug("View transform changed, but scale bar should be hidden. Hiding.")
            self._image_view.set_scale_bar_visibility(False)

    @QtCore.Slot()
    def update_ui_from_manager(self) -> None:
        """Updates the scale panel UI elements based on ScaleManager's state."""
        # Check for all necessary UI elements and managers
        required_widgets = [
            self._scale_m_per_px_input, self._scale_px_per_m_input,
            self._scale_display_meters_checkbox, self._scale_reset_button,
            self._show_scale_bar_checkbox
        ]
        if not all(required_widgets) or not self._scale_manager or not self._image_view:
            logger.debug("ScalePanelController.update_ui_from_manager skipped: UI elements or manager not ready.")
            return

        logger.debug("ScalePanelController: Updating scale UI from ScaleManager state.")
        self._block_scale_signals = True

        current_m_per_px = self._scale_manager.get_scale_m_per_px()
        current_reciprocal_px_m = self._scale_manager.get_reciprocal_scale_px_per_m()
        display_in_meters_state = self._scale_manager.display_in_meters()
        scale_is_set = current_m_per_px is not None

        self._scale_m_per_px_input.setText(f"{current_m_per_px:.6g}" if current_m_per_px is not None else "")
        self._scale_px_per_m_input.setText(f"{current_reciprocal_px_m:.6g}" if current_reciprocal_px_m is not None else "")

        if self._video_loaded:
            self._scale_display_meters_checkbox.setEnabled(scale_is_set)
            self._scale_display_meters_checkbox.setChecked(display_in_meters_state if scale_is_set else False)
            self._scale_reset_button.setEnabled(scale_is_set)
            self._show_scale_bar_checkbox.setEnabled(scale_is_set)

            if scale_is_set:
                # If the checkbox itself is managing its checked state based on user interaction,
                # we might only want to control its enabled state here, and let _on_show_scale_bar_toggled
                # handle the visibility based on its current checked state.
                # However, if we want to default it to show when scale becomes available:
                if not self._show_scale_bar_checkbox.isChecked(): # If scale just became available and it's not checked
                     self._show_scale_bar_checkbox.setChecked(True) # This will trigger its toggled signal
                else: # Already checked, ensure visibility and update dimensions
                    self._image_view.set_scale_bar_visibility(True)
                    self._image_view.update_scale_bar_dimensions(current_m_per_px)

            else: # Scale is not set
                self._show_scale_bar_checkbox.setChecked(False) # This will trigger toggled if state changes
                self._image_view.set_scale_bar_visibility(False) # Explicitly hide
        else: # No video loaded
            self._scale_display_meters_checkbox.setEnabled(False)
            self._scale_display_meters_checkbox.setChecked(False)
            self._scale_reset_button.setEnabled(False)
            self._show_scale_bar_checkbox.setEnabled(False)
            self._show_scale_bar_checkbox.setChecked(False)
            self._image_view.set_scale_bar_visibility(False)

        self._block_scale_signals = False
        logger.debug(f"ScalePanelController: Scale UI update complete. Scale bar visible: {self._image_view._scale_bar_widget.isVisible() if hasattr(self._image_view, '_scale_bar_widget') else 'N/A'}")

# UI logic for coordinate panel

class CoordinatePanelController(QtCore.QObject):
    """
    Manages the UI logic for the Coordinate System panel.
    """
    # Signals to notify MainWindow of necessary actions
    needsRedraw = QtCore.Signal()
    pointsTableNeedsUpdate = QtCore.Signal()
    statusBarMessage = QtCore.Signal(str, int) # message, timeout

    def __init__(self,
                 coord_transformer: 'CoordinateTransformer',
                 image_view: 'InteractiveImageView',
                 scale_manager: 'ScaleManager',
                 coord_system_group: QtWidgets.QButtonGroup,
                 coord_top_left_radio: QtWidgets.QRadioButton,
                 coord_bottom_left_radio: QtWidgets.QRadioButton,
                 coord_custom_radio: QtWidgets.QRadioButton,
                 coord_top_left_origin_label: QtWidgets.QLabel,
                 coord_bottom_left_origin_label: QtWidgets.QLabel,
                 coord_custom_origin_label: QtWidgets.QLabel,
                 set_origin_button: QtWidgets.QPushButton,
                 show_origin_checkbox: QtWidgets.QCheckBox,
                 cursor_pos_labels_px: Dict[str, QtWidgets.QLabel], # e.g., {"TL": tl_label, "BL": bl_label ...}
                 cursor_pos_labels_m: Dict[str, QtWidgets.QLabel],
                 parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)

        self._coord_transformer = coord_transformer
        self._image_view = image_view
        self._scale_manager = scale_manager # For metric cursor display

        self._coord_system_group = coord_system_group
        self._coord_top_left_radio = coord_top_left_radio
        self._coord_bottom_left_radio = coord_bottom_left_radio
        self._coord_custom_radio = coord_custom_radio
        self._coord_top_left_origin_label = coord_top_left_origin_label
        self._coord_bottom_left_origin_label = coord_bottom_left_origin_label
        self._coord_custom_origin_label = coord_custom_origin_label
        self._set_origin_button = set_origin_button
        self._show_origin_checkbox = show_origin_checkbox
        self._cursor_pos_labels_px = cursor_pos_labels_px # Store the dictionary
        self._cursor_pos_labels_m = cursor_pos_labels_m   # Store the dictionary for metric labels

        self._is_setting_origin: bool = False
        self._show_origin_marker: bool = True # Default, will be synced by update_ui_display
        self._last_scene_mouse_x: float = -1.0
        self._last_scene_mouse_y: float = -1.0
        self._video_loaded: bool = False

        # Connect signals from UI elements
        self._coord_system_group.buttonToggled.connect(self._on_coordinate_mode_changed)
        self._set_origin_button.clicked.connect(self._on_enter_set_origin_mode)
        self._show_origin_checkbox.stateChanged.connect(self._on_toggle_show_origin)

        # MainWindow will connect these:
        # self._image_view.originSetRequest.connect(self._on_set_custom_origin)
        # self._image_view.sceneMouseMoved.connect(self._on_handle_mouse_moved)
        # self._scale_manager.scaleOrUnitChanged.connect(self._trigger_cursor_label_update_slot)

        self.update_ui_display() # Initial UI setup

    def set_video_loaded_status(self, is_loaded: bool) -> None:
        """Updates the controller's knowledge of video load status and updates UI."""
        if self._video_loaded != is_loaded:
            self._video_loaded = is_loaded
            if not is_loaded: # If video is closed/unloaded
                self._is_setting_origin = False # Ensure this mode is exited
                if self._image_view:
                    self._image_view.set_interaction_mode(InteractionMode.NORMAL)
                # Reset internal state, transformer might be reset by MainWindow
                self._show_origin_marker = True # Default back
            self.update_ui_display() # Update enable/disable states

    def set_video_height(self, height: int) -> None:
        """Passes video height to the coordinate transformer."""
        self._coord_transformer.set_video_height(height)
        self.update_ui_display() # Origin labels might change (e.g., BL)

    @QtCore.Slot(QtWidgets.QAbstractButton, bool)
    def _on_coordinate_mode_changed(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        """Handles changes in the coordinate system radio buttons."""
        if not checked:
            return # Only react when a button is checked

        new_mode = CoordinateSystem.TOP_LEFT # Default assumption
        if button == self._coord_bottom_left_radio:
            new_mode = CoordinateSystem.BOTTOM_LEFT
        elif button == self._coord_custom_radio:
            new_mode = CoordinateSystem.CUSTOM

        if self._coord_transformer.mode != new_mode:
            self._coord_transformer.set_mode(new_mode)
            logger.info(f"Coordinate system mode changed to: {new_mode.name}")
            self.update_ui_display() # Updates radio buttons & labels
            self.pointsTableNeedsUpdate.emit()
            if self._show_origin_marker:
                self.needsRedraw.emit()

    @QtCore.Slot()
    def _on_enter_set_origin_mode(self) -> None:
        """Enters the mode where the next click sets the custom origin."""
        if not self._video_loaded:
            self.statusBarMessage.emit("Load a video first to set origin.", 3000)
            return
        self._is_setting_origin = True
        self._image_view.set_interaction_mode(InteractionMode.SET_ORIGIN)
        self.statusBarMessage.emit("Click on the image to set the custom origin.", 0)
        logger.info("Entered 'Set Custom Origin' mode.")

    @QtCore.Slot(float, float)
    def _on_set_custom_origin(self, scene_x: float, scene_y: float) -> None:
        """Sets the custom origin based on a click signal from the image view."""
        self._is_setting_origin = False
        self._image_view.set_interaction_mode(InteractionMode.NORMAL)

        self._coord_transformer.set_custom_origin(scene_x, scene_y)
        self.update_ui_display()
        self.pointsTableNeedsUpdate.emit()
        self.needsRedraw.emit()

        origin_meta = self._coord_transformer.get_metadata()
        cust_x = origin_meta.get('origin_x_tl', 0.0)
        cust_y = origin_meta.get('origin_y_tl', 0.0)
        self.statusBarMessage.emit(f"Custom origin set at (TL): ({cust_x:.1f}, {cust_y:.1f})", 5000)
        logger.info(f"Custom origin set via click at scene coordinates ({scene_x:.1f}, {scene_y:.1f})")

    @QtCore.Slot(int)
    def _on_toggle_show_origin(self, state: int) -> None:
        """Toggles the visibility of the origin marker based on checkbox state."""
        self._show_origin_marker = (state == QtCore.Qt.CheckState.Checked.value)
        logger.info(f"Origin marker visibility set to: {self._show_origin_marker}")
        self.needsRedraw.emit()

    def get_show_origin_marker_status(self) -> bool:
        """Returns whether the origin marker should be shown."""
        return self._show_origin_marker
        
    def is_setting_origin_mode(self) -> bool:
        """Returns true if currently in 'set origin' interaction mode."""
        return self._is_setting_origin

    @QtCore.Slot()
    def update_ui_display(self) -> None:
        """Updates the coordinate system panel UI elements."""
        logger.debug("CoordinatePanelController: Updating UI display.")
        current_mode = self._coord_transformer.mode
        origin_meta = self._coord_transformer.get_metadata()
        video_h = self._coord_transformer.video_height

        self._coord_top_left_origin_label.setText("(0.0, 0.0)")
        bl_origin_y_str = f"{video_h:.1f}" if video_h > 0 else "-"
        self._coord_bottom_left_origin_label.setText(f"(0.0, {bl_origin_y_str})")
        cust_x = origin_meta.get('origin_x_tl', 0.0)
        cust_y = origin_meta.get('origin_y_tl', 0.0)
        self._coord_custom_origin_label.setText(f"({cust_x:.1f}, {cust_y:.1f})")

        self._coord_system_group.blockSignals(True)
        if current_mode == CoordinateSystem.TOP_LEFT: self._coord_top_left_radio.setChecked(True)
        elif current_mode == CoordinateSystem.BOTTOM_LEFT: self._coord_bottom_left_radio.setChecked(True)
        elif current_mode == CoordinateSystem.CUSTOM: self._coord_custom_radio.setChecked(True)
        self._coord_system_group.blockSignals(False)

        self._show_origin_checkbox.blockSignals(True)
        self._show_origin_checkbox.setChecked(self._show_origin_marker)
        self._show_origin_checkbox.blockSignals(False)

        # Enable/disable widgets based on video loaded status
        is_enabled = self._video_loaded
        self._coord_top_left_radio.setEnabled(is_enabled)
        self._coord_bottom_left_radio.setEnabled(is_enabled)
        self._coord_custom_radio.setEnabled(is_enabled)
        self._set_origin_button.setEnabled(is_enabled)
        self._show_origin_checkbox.setEnabled(is_enabled)
        
        # Update cursor labels (as origin might have changed)
        self._on_handle_mouse_moved(self._last_scene_mouse_x, self._last_scene_mouse_y)
        logger.debug("CoordinatePanelController.update_ui_display emitting pointsTableNeedsUpdate.")
        self.pointsTableNeedsUpdate.emit()


    @QtCore.Slot(float, float)
    def _on_handle_mouse_moved(self, scene_x_px: float, scene_y_px: float) -> None:
        """Updates cursor position labels in all coordinate systems."""
        self._last_scene_mouse_x = scene_x_px
        self._last_scene_mouse_y = scene_y_px

        placeholder = "(--, --)"
        scale_is_set = self._scale_manager.get_scale_m_per_px() is not None

        if not self._video_loaded or scene_x_px == -1.0:
            for label_group in [self._cursor_pos_labels_px, self._cursor_pos_labels_m]:
                for label in label_group.values():
                    label.setText(placeholder)
            return

        # Calculate transformed coordinates for each system
        # Format: (display_x_px, display_y_px)
        coords_px = {
            "TL": self._coord_transformer.transform_point_for_display(scene_x_px, scene_y_px)
                  if self._coord_transformer.mode == CoordinateSystem.TOP_LEFT else
                  CoordinateTransformer().transform_point_for_display(scene_x_px, scene_y_px), # Use a temp TL transformer
            "BL": CoordinateTransformer().transform_point_for_display(scene_x_px, scene_y_px) # Start with TL
        }
        # For BL, adjust relative to its specific origin
        bl_origin_x_tl_temp, bl_origin_y_tl_temp = (0.0, float(self._coord_transformer.video_height)) if self._coord_transformer.video_height > 0 else (0.0,0.0)
        coords_px["BL"] = (coords_px["BL"][0] - bl_origin_x_tl_temp, -(coords_px["BL"][1] - bl_origin_y_tl_temp))


        # For Custom, adjust relative to its specific origin
        # Calculate Custom origin in TL
        if self._coord_transformer.mode == CoordinateSystem.CUSTOM:
            custom_origin_x_tl, custom_origin_y_tl = self._coord_transformer.get_current_origin_tl()
        else: # If not in custom mode, get the stored/default custom origin for display
            meta = self._coord_transformer.get_metadata()
            custom_origin_x_tl = meta.get("origin_x_tl", 0.0)
            custom_origin_y_tl = meta.get("origin_y_tl", 0.0)
        
        # Calculate TL equivalent for custom display
        tl_for_custom_display = CoordinateTransformer().transform_point_for_display(scene_x_px, scene_y_px)
        coords_px["Custom"] = (tl_for_custom_display[0] - custom_origin_x_tl, -(tl_for_custom_display[1] - custom_origin_y_tl))


        # Update Pixel Labels
        for key, label in self._cursor_pos_labels_px.items():
            if key in coords_px:
                label.setText(f"({coords_px[key][0]:.1f}, {coords_px[key][1]:.1f})")
            else: # Fallback for safety, though should not happen if keys match
                label.setText(placeholder)

        # Update Metric Labels
        if scale_is_set:
            m_per_px = self._scale_manager.get_scale_m_per_px()
            for key, label in self._cursor_pos_labels_m.items():
                if key in coords_px and m_per_px is not None:
                    coords_m = (coords_px[key][0] * m_per_px, coords_px[key][1] * m_per_px)
                    label.setText(f"({coords_m[0]:.2f}, {coords_m[1]:.2f})") # Higher precision for meters
                else:
                    label.setText(placeholder)
        else:
            for label in self._cursor_pos_labels_m.values():
                label.setText(placeholder)
    
    @QtCore.Slot()
    def _trigger_cursor_label_update_slot(self) -> None:
        """Slot to be connected to scale_manager.scaleOrUnitChanged signal."""
        self._on_handle_mouse_moved(self._last_scene_mouse_x, self._last_scene_mouse_y)

