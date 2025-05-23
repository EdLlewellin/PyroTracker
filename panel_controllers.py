# panel_controllers.py
"""
Contains controller classes for managing UI logic for various panels
in the MainWindow.
"""
import logging
import math # Added for distance calculation
from typing import Optional, TYPE_CHECKING, Dict, Tuple # Added Tuple

from PySide6 import QtCore, QtGui, QtWidgets

# Import project-specific modules
from coordinates import CoordinateSystem, CoordinateTransformer # For CoordinatePanelController
from interactive_image_view import InteractionMode      # For CoordinatePanelController

if TYPE_CHECKING:
    # These are only for type hinting to avoid circular imports
    from main_window import MainWindow # For status bar and disabling frame nav
    from scale_manager import ScaleManager
    from interactive_image_view import InteractiveImageView

logger = logging.getLogger(__name__)


# --- NEW DIALOG CLASS FOR GETTING KNOWN DISTANCE ---
class GetDistanceDialog(QtWidgets.QDialog):
    """
    A simple dialog to get the known real-world distance from the user.
    """
    def __init__(self, pixel_distance: float, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Enter Known Distance")
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        info_label = QtWidgets.QLabel(f"Pixel distance of drawn line: {pixel_distance:.2f} px")
        layout.addWidget(info_label)

        prompt_label = QtWidgets.QLabel("Enter known real-world distance for this line (in meters):")
        layout.addWidget(prompt_label)

        self.distance_input = QtWidgets.QLineEdit()
        self.distance_input.setValidator(QtGui.QDoubleValidator(0.000001, 1e9, 6, self)) # Min > 0
        layout.addWidget(self.distance_input)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.distance_input.setFocus() # Set focus to input field

    def get_distance(self) -> Optional[float]:
        """Returns the entered distance as a float, or None if dialog was cancelled or input invalid."""
        if self.result() == QtWidgets.QDialog.DialogCode.Accepted:
            try:
                distance = float(self.distance_input.text())
                if distance > 0:
                    return distance
                else:
                    QtWidgets.QMessageBox.warning(self, "Invalid Input", "Distance must be a positive number.")
                    return None # Or re-open dialog, but for now just return None
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please enter a valid number for the distance.")
                return None
        return None

# --- END OF NEW DIALOG CLASS ---


class ScalePanelController(QtCore.QObject):
    """
    Manages the UI logic for the Scale Configuration panel, including setting scale manually
    and by defining a line of known length on the image.
    """
    # --- NEW SIGNALS ---
    # Signal to MainWindow to update status bar
    statusBarMessage = QtCore.Signal(str, int)
    # Signal to MainWindow to enable/disable frame navigation controls
    requestFrameNavigationControlsDisabled = QtCore.Signal(bool)


    def __init__(self,
                 scale_manager: 'ScaleManager',
                 image_view: 'InteractiveImageView',
                 main_window_ref: 'MainWindow', # Added MainWindow reference for status bar and frame nav control
                 scale_m_per_px_input: QtWidgets.QLineEdit,
                 scale_px_per_m_input: QtWidgets.QLineEdit,
                 set_scale_by_feature_button: QtWidgets.QPushButton, # New UI element
                 show_scale_line_checkbox: QtWidgets.QCheckBox,    # New UI element
                 scale_reset_button: QtWidgets.QPushButton,
                 scale_display_meters_checkbox: QtWidgets.QCheckBox,
                 show_scale_bar_checkbox: QtWidgets.QCheckBox,
                 parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)

        self._scale_manager = scale_manager
        self._image_view = image_view
        self._main_window_ref = main_window_ref # Store MainWindow reference

        # Manual scale inputs
        self._scale_m_per_px_input = scale_m_per_px_input
        self._scale_px_per_m_input = scale_px_per_m_input
        self._scale_reset_button = scale_reset_button

        # Scale from feature UI
        self._set_scale_by_feature_button = set_scale_by_feature_button
        self._show_scale_line_checkbox = show_scale_line_checkbox

        # General scale display toggles
        self._scale_display_meters_checkbox = scale_display_meters_checkbox
        self._show_scale_bar_checkbox = show_scale_bar_checkbox

        self._block_scale_signals: bool = False
        self._video_loaded: bool = False

        # --- NEW State variables for "Set Scale by Line" ---
        self._is_setting_scale_by_line: bool = False
        self._scale_line_p1_scene: Optional[QtCore.QPointF] = None
        # To store the frame index where scale line points are defined.
        # We'll get this from MainWindow when the process starts.
        self._scale_line_definition_frame_index: int = -1


        # Connect signals from UI elements to controller slots
        self._scale_m_per_px_input.editingFinished.connect(self._on_scale_m_per_px_editing_finished)
        self._scale_px_per_m_input.editingFinished.connect(self._on_scale_px_per_m_editing_finished)
        self._scale_reset_button.clicked.connect(self._on_scale_reset_clicked)
        self._scale_display_meters_checkbox.toggled.connect(self._on_display_units_toggled)
        self._show_scale_bar_checkbox.toggled.connect(self._on_show_scale_bar_toggled)

        # --- NEW CONNECTIONS ---
        self._set_scale_by_feature_button.clicked.connect(self._on_set_scale_by_feature_button_clicked)
        self._show_scale_line_checkbox.toggled.connect(self._on_show_defined_scale_line_toggled)

        # Connect to InteractiveImageView signals for scale line definition
        self._image_view.scaleLinePoint1Clicked.connect(self._on_image_view_scale_line_point1_clicked)
        self._image_view.scaleLinePoint2Clicked.connect(self._on_image_view_scale_line_point2_clicked)

        # --- ADDED CONNECTION TO FIX THE BUG ---
        # Connect the ScaleManager signal to the UI update slot for this controller
        self._scale_manager.scaleOrUnitChanged.connect(self.update_ui_from_manager)
        # --- END OF ADDED CONNECTION ---

        # Initialize UI states
        self.update_ui_from_manager()


    def set_video_loaded_status(self, is_loaded: bool) -> None:
        """Updates the controller's knowledge of video load status."""
        if self._video_loaded != is_loaded:
            self._video_loaded = is_loaded
            if not is_loaded: # Video unloaded
                self.cancel_set_scale_by_line() # Cancel if in progress
                # ScaleManager.reset() will be called by MainWindow, which clears defined line
            self.update_ui_from_manager()

    @QtCore.Slot()
    def _on_set_scale_by_feature_button_clicked(self) -> None:
        if not self._video_loaded:
            self.statusBarMessage.emit("Load a video first to set scale by feature.", 3000)
            return

        if self._is_setting_scale_by_line:
            self.cancel_set_scale_by_line()
        else:
            # --- MODIFICATION: Cancel other definition modes ---
            if hasattr(self._main_window_ref, '_is_defining_measurement_line') and self._main_window_ref._is_defining_measurement_line:
                logger.debug("Cancelling active measurement line definition before starting 'Set Scale by Line'.")
                self._main_window_ref._cancel_active_line_definition_ui_reset()
            if hasattr(self._main_window_ref, 'coord_panel_controller') and self._main_window_ref.coord_panel_controller and self._main_window_ref.coord_panel_controller.is_setting_origin_mode():
                logger.debug("Cancelling active 'Set Origin' mode before starting 'Set Scale by Line'.")
                self._main_window_ref.coord_panel_controller._is_setting_origin = False
                self._image_view.set_interaction_mode(InteractionMode.NORMAL)
            # --- END MODIFICATION ---

            self._is_setting_scale_by_line = True
            self._image_view.set_interaction_mode(InteractionMode.SET_SCALE_LINE_START)
            self._scale_line_p1_scene = None 
            
            if hasattr(self._main_window_ref, 'current_frame_index'):
                 self._scale_line_definition_frame_index = self._main_window_ref.current_frame_index
            else: 
                 self._scale_line_definition_frame_index = -1
                 logger.error("Cannot get current_frame_index from MainWindow for scale line definition.")

            self.statusBarMessage.emit("Set Scale: Click first point of known length. (Esc to cancel)", 0)
            self._set_scale_by_feature_button.setText("Cancel") 
            self.requestFrameNavigationControlsDisabled.emit(True) 
            logger.info("Entered 'Set Scale by Line' mode. Waiting for first point.")
            self._scale_m_per_px_input.setEnabled(False)
            self._scale_px_per_m_input.setEnabled(False)
            self._scale_reset_button.setEnabled(False)

    @QtCore.Slot(float, float)
    def _on_image_view_scale_line_point1_clicked(self, scene_x: float, scene_y: float) -> None:
        # Primary guard: If SPC is not defining scale, ignore.
        if not self._is_setting_scale_by_line:
            logger.debug("ScalePanelController: Ignoring scaleLinePoint1Clicked as _is_setting_scale_by_line is False.")
            return
        
        # If we reach here, self._is_setting_scale_by_line is True.
        # The ImageView emitted this signal, indicating it was in SET_SCALE_LINE_START mode.
        # We don't need to re-check ImageView's mode here as it might have already changed.
        
        self._scale_line_p1_scene = QtCore.QPointF(scene_x, scene_y)
        # Controller tells ImageView to change mode for the *next* expected click.
        self._image_view.set_interaction_mode(InteractionMode.SET_SCALE_LINE_END)
        self.statusBarMessage.emit("Set Scale: Click second point of known length. (Esc to cancel)", 0)
        logger.info(f"ScalePanelController: Scale line point 1 received: ({scene_x:.2f}, {scene_y:.2f}) for its scale definition.")

    @QtCore.Slot(float, float, float, float)
    def _on_image_view_scale_line_point2_clicked(self, x1: float, y1: float, x2: float, y2: float) -> None:
        # Primary guard: If SPC is not defining scale, ignore.
        if not self._is_setting_scale_by_line:
            logger.debug("ScalePanelController: Ignoring scaleLinePoint2Clicked as _is_setting_scale_by_line is False.")
            return

        # If we reach here, self._is_setting_scale_by_line is True.
        # Check if the first point for scale definition was actually set by this controller.
        if self._scale_line_p1_scene is None:
            logger.warning("ScalePanelController: Received scaleLinePoint2Clicked but its _scale_line_p1_scene is None. Cancelling.")
            self.cancel_set_scale_by_line()
            return
        
        # Check if the received x1,y1 match the stored _scale_line_p1_scene
        # This ensures we are processing the second point corresponding to our stored first point.
        # Compare with a small tolerance for floating point comparisons.
        tolerance = 1e-5 
        if not (math.isclose(self._scale_line_p1_scene.x(), x1, rel_tol=tolerance) and \
                math.isclose(self._scale_line_p1_scene.y(), y1, rel_tol=tolerance)):
            logger.warning(f"ScalePanelController: scaleLinePoint2Clicked received with x1,y1 ({x1:.2f},{y1:.2f}) "
                           f"that don't match stored p1 ({self._scale_line_p1_scene.x():.2f},{self._scale_line_p1_scene.y():.2f}). "
                           "This might be a stray signal if multiple line definitions are interleaved. Ignoring.")
            # Not cancelling, as this might be a signal for a different process (e.g. measurement line)
            return

        logger.info(f"ScalePanelController: Scale line point 2 received: ({x2:.2f}, {y2:.2f}). Line defined for ITS scale: [({x1:.2f},{y1:.2f}) to ({x2:.2f},{y2:.2f})]")

        dx = x2 - x1; dy = y2 - y1
        pixel_distance = math.sqrt(dx*dx + dy*dy)

        if pixel_distance < 1e-3:
            QtWidgets.QMessageBox.warning(self._main_window_ref, "Set Scale Error", "The two points are too close or identical. Please define a longer line for scale.")
            self.cancel_set_scale_by_line()
            return

        dialog = GetDistanceDialog(pixel_distance, self._main_window_ref)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            known_distance_m = dialog.get_distance()
            if known_distance_m is not None and known_distance_m > 0:
                m_per_px = known_distance_m / pixel_distance
                self._scale_manager.set_defined_scale_line(x1, y1, x2, y2)
                self._scale_manager.set_scale(m_per_px, called_from_line_definition=True)
                self.statusBarMessage.emit(f"Scale set to {m_per_px:.6g} m/px.", 5000)
                if hasattr(self._main_window_ref, 'showScaleLineCheckBox') and self._main_window_ref.showScaleLineCheckBox:
                    self._main_window_ref.showScaleLineCheckBox.setChecked(True)
                if hasattr(self._main_window_ref, 'showScaleBarCheckBox') and self._main_window_ref.showScaleBarCheckBox:
                    self._main_window_ref.showScaleBarCheckBox.setChecked(True)
                if hasattr(self._main_window_ref, '_redraw_scene_overlay'):
                    self._main_window_ref._redraw_scene_overlay()
            else:
                self.statusBarMessage.emit("Set scale by line cancelled or invalid distance.", 3000)
                self._image_view.clearTemporaryScaleVisuals()
        else:
            self.statusBarMessage.emit("Set scale by line cancelled.", 3000)
            self._image_view.clearTemporaryScaleVisuals()

        self.cancel_set_scale_by_line(reset_button_text=False) 
        self._set_scale_by_feature_button.setText("Set")

    def cancel_set_scale_by_line(self, reset_button_text: bool = True) -> None:
        if self._is_setting_scale_by_line or self._image_view._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END]:
            logger.info("Cancelling 'Set Scale by Line' process.")
        self._is_setting_scale_by_line = False
        self._scale_line_p1_scene = None
        self._scale_line_definition_frame_index = -1
        self._image_view.set_interaction_mode(InteractionMode.NORMAL) 
        if reset_button_text:
            self._set_scale_by_feature_button.setText("Set")
        self.requestFrameNavigationControlsDisabled.emit(False) 
        
        manual_inputs_enabled = self._video_loaded
        self._scale_m_per_px_input.setEnabled(manual_inputs_enabled)
        self._scale_px_per_m_input.setEnabled(manual_inputs_enabled)
        self._scale_reset_button.setEnabled(self._video_loaded and self._scale_manager.get_scale_m_per_px() is not None)

    @QtCore.Slot(bool)
    def _on_show_defined_scale_line_toggled(self, checked: bool) -> None:
        logger.info(f"'Show defined scale line' checkbox toggled to: {checked}.")
        # Always request a redraw when this checkbox's state changes.
        # MainWindow._redraw_scene_overlay() will internally check both the
        # checkbox state and ScaleManager.has_defined_scale_line()
        # before deciding whether to draw or erase the line.
        if hasattr(self._main_window_ref, '_redraw_scene_overlay'):
            self._main_window_ref._redraw_scene_overlay()
            logger.debug("Requested scene overlay redraw due to 'Show scale line' toggle.")
        else:
            logger.warning("MainWindow reference for redraw not available in ScalePanelController for 'Show scale line' toggle.")

    @QtCore.Slot()
    def _on_scale_m_per_px_editing_finished(self) -> None:
        if self._block_scale_signals: return
        if not self._scale_m_per_px_input: return

        text = self._scale_m_per_px_input.text().strip()
        current_scale_m_per_px = self._scale_manager.get_scale_m_per_px()
        scale_successfully_set_to_new_value = False
        # Define a tolerance that accounts for display formatting (e.g., .6g)
        # This tolerance should be slightly larger than the precision of the display.
        comparison_tolerance = 1e-5 

        try:
            if not text: 
                other_text_is_also_empty = True 
                if self._scale_px_per_m_input:
                    other_text_is_also_empty = not self._scale_px_per_m_input.text().strip()
                
                if other_text_is_also_empty and current_scale_m_per_px is not None:
                    logger.debug(f"_on_scale_m_per_px_editing_finished: Both inputs empty, scale was {current_scale_m_per_px}. Clearing scale and defined line.")
                    self._scale_manager.clear_defined_scale_line() 
                    self._scale_manager.set_scale(None)
                return 

            value = float(text)
            if value > 0.0:
                if current_scale_m_per_px is None or \
                   not math.isclose(value, current_scale_m_per_px, rel_tol=comparison_tolerance):
                    logger.debug(f"_on_scale_m_per_px_editing_finished: New manual scale value {value} (from text: '{text}') is considered different from current ({current_scale_m_per_px}) with tolerance {comparison_tolerance}. Clearing defined line.")
                    self._scale_manager.clear_defined_scale_line() 
                    self._scale_manager.set_scale(value)
                    scale_successfully_set_to_new_value = True
                else:
                    logger.debug(f"_on_scale_m_per_px_editing_finished: Manual scale value {value} (from text: '{text}') is close enough to current ({current_scale_m_per_px}). Defined line preserved.")
            elif value == 0.0: 
                if current_scale_m_per_px is not None:
                    logger.debug("_on_scale_m_per_px_editing_finished: Manual scale set to 0. Clearing scale and defined line.")
                    self._scale_manager.clear_defined_scale_line()
                    self._scale_manager.set_scale(None)
            else: 
                self.update_ui_from_manager() 
        except ValueError: 
            self.update_ui_from_manager() 
        
        if scale_successfully_set_to_new_value and self._video_loaded:
            if hasattr(self._main_window_ref, 'showScaleBarCheckBox') and self._main_window_ref.showScaleBarCheckBox:
                self._main_window_ref.showScaleBarCheckBox.setChecked(True)
                logger.debug("Manually set m/px scale, auto-checked 'Show Scale Bar'.")

    @QtCore.Slot()
    def _on_scale_px_per_m_editing_finished(self) -> None:
        if self._block_scale_signals: return
        if not self._scale_px_per_m_input: return

        text = self._scale_px_per_m_input.text().strip()
        current_scale_m_per_px = self._scale_manager.get_scale_m_per_px()
        scale_successfully_set_to_new_value = False
        comparison_tolerance = 1e-5 # Same tolerance
        
        try:
            if not text: 
                other_text_is_also_empty = True
                if self._scale_m_per_px_input:
                    other_text_is_also_empty = not self._scale_m_per_px_input.text().strip()

                if other_text_is_also_empty and current_scale_m_per_px is not None:
                    logger.debug(f"_on_scale_px_per_m_editing_finished: Both inputs empty, scale was {current_scale_m_per_px}. Clearing scale and defined line.")
                    self._scale_manager.clear_defined_scale_line()
                    self._scale_manager.set_scale(None)
                return

            value_px_per_m = float(text)
            if value_px_per_m > 0.0:
                new_scale_m_per_px = 1.0 / value_px_per_m
                if current_scale_m_per_px is None or \
                   not math.isclose(new_scale_m_per_px, current_scale_m_per_px, rel_tol=comparison_tolerance):
                    logger.debug(f"_on_scale_px_per_m_editing_finished: New manual scale value {new_scale_m_per_px} (from text: '{text}' px/m) is considered different from current ({current_scale_m_per_px}) with tolerance {comparison_tolerance}. Clearing defined line.")
                    self._scale_manager.clear_defined_scale_line() 
                    self._scale_manager.set_scale(new_scale_m_per_px)
                    scale_successfully_set_to_new_value = True
                else:
                    logger.debug(f"_on_scale_px_per_m_editing_finished: Manual scale value {new_scale_m_per_px} (from text: '{text}' px/m) is close enough to current ({current_scale_m_per_px}). Defined line preserved.")
            elif value_px_per_m == 0.0: 
                if current_scale_m_per_px is not None:
                    logger.debug("_on_scale_px_per_m_editing_finished: Manual scale set to 0. Clearing scale and defined line.")
                    self._scale_manager.clear_defined_scale_line()
                    self._scale_manager.set_scale(None)
            else: 
                self.update_ui_from_manager()
        except ValueError: 
            self.update_ui_from_manager()

        if scale_successfully_set_to_new_value and self._video_loaded:
            if hasattr(self._main_window_ref, 'showScaleBarCheckBox') and self._main_window_ref.showScaleBarCheckBox:
                self._main_window_ref.showScaleBarCheckBox.setChecked(True)
                logger.debug("Manually set px/m scale, auto-checked 'Show Scale Bar'.")

    @QtCore.Slot()
    def _on_scale_reset_clicked(self) -> None:
        logger.debug("Scale reset button clicked.")
        self._scale_manager.reset() # ScaleManager.reset() now clears defined line data

    @QtCore.Slot(bool)
    def _on_display_units_toggled(self, checked: bool) -> None:
        if self._scale_display_meters_checkbox:
            if self._scale_display_meters_checkbox.isEnabled():
                self._scale_manager.set_display_in_meters(checked)
            else: # Should not happen if logic is correct, but good to be safe
                self._scale_manager.set_display_in_meters(False)

    @QtCore.Slot(bool)
    def _on_show_scale_bar_toggled(self, checked: bool) -> None:
        if not (self._image_view and self._scale_manager and self._show_scale_bar_checkbox): return

        scale_is_set = self._scale_manager.get_scale_m_per_px() is not None
        if self._show_scale_bar_checkbox.isEnabled() and scale_is_set:
            self._image_view.set_scale_bar_visibility(checked)
            if checked: self._image_view.update_scale_bar_dimensions(self._scale_manager.get_scale_m_per_px())
        elif not scale_is_set: # If scale not set, ensure bar is hidden and checkbox state reflects this
            self._image_view.set_scale_bar_visibility(False)
            if self._show_scale_bar_checkbox.isChecked(): # If it was checked but shouldn't be
                self._show_scale_bar_checkbox.setChecked(False)
            # self._show_scale_bar_checkbox.setEnabled(False) # This is handled by update_ui_from_manager

    @QtCore.Slot()
    def _on_view_transform_changed(self) -> None:
        if not (self._image_view and self._scale_manager and self._show_scale_bar_checkbox): return

        scale_is_set = self._scale_manager.get_scale_m_per_px() is not None
        scale_bar_should_be_visible = self._show_scale_bar_checkbox.isChecked()

        if self._video_loaded and scale_is_set and scale_bar_should_be_visible:
            self._image_view.update_scale_bar_dimensions(self._scale_manager.get_scale_m_per_px())
        # This redundant check ensures if scale bar is visible but shouldn't be, it's hidden
        elif self._image_view._scale_bar_widget.isVisible() and \
             (not self._video_loaded or not scale_is_set or not scale_bar_should_be_visible):
            self._image_view.set_scale_bar_visibility(False)

    @QtCore.Slot()
    def update_ui_from_manager(self) -> None:
        """Updates the scale panel UI elements based on ScaleManager's state."""
        required_attrs = [
            '_scale_manager', '_image_view', '_scale_m_per_px_input', '_scale_px_per_m_input',
            '_set_scale_by_feature_button', '_show_scale_line_checkbox', '_scale_reset_button',
            '_scale_display_meters_checkbox', '_show_scale_bar_checkbox'
        ]
        if not all(hasattr(self, attr) and getattr(self, attr) is not None for attr in required_attrs):
            logger.debug("ScalePanelController.update_ui_from_manager skipped: Core components not fully initialized.")
            return

        logger.debug("ScalePanelController: Updating UI from ScaleManager state.")
        self._block_scale_signals = True
        try:
            current_m_per_px = self._scale_manager.get_scale_m_per_px()
            current_reciprocal_px_m = self._scale_manager.get_reciprocal_scale_px_per_m()
            display_in_meters_state = self._scale_manager.display_in_meters()
            scale_is_set = current_m_per_px is not None
            line_is_defined = self._scale_manager.has_defined_scale_line()

            self._scale_m_per_px_input.setText(f"{current_m_per_px:.6g}" if current_m_per_px is not None else "")
            self._scale_px_per_m_input.setText(f"{current_reciprocal_px_m:.6g}" if current_reciprocal_px_m is not None else "")

            ui_enabled = self._video_loaded
            
            manual_input_enabled_state = ui_enabled and not self._is_setting_scale_by_line
            self._scale_m_per_px_input.setEnabled(manual_input_enabled_state)
            self._scale_px_per_m_input.setEnabled(manual_input_enabled_state)
            
            self._set_scale_by_feature_button.setEnabled(ui_enabled)
            if not self._is_setting_scale_by_line :
                self._set_scale_by_feature_button.setText("Set")
            
            self._scale_reset_button.setEnabled(ui_enabled and scale_is_set and not self._is_setting_scale_by_line)

            self._scale_display_meters_checkbox.setEnabled(ui_enabled and scale_is_set)
            self._scale_display_meters_checkbox.setChecked(display_in_meters_state if scale_is_set else False)

            self._show_scale_bar_checkbox.setEnabled(ui_enabled and scale_is_set)
            if ui_enabled and scale_is_set:
                is_checked = self._show_scale_bar_checkbox.isChecked()
                self._image_view.set_scale_bar_visibility(is_checked)
                if is_checked:
                    self._image_view.update_scale_bar_dimensions(current_m_per_px)
            else:
                self._show_scale_bar_checkbox.setChecked(False)
                self._image_view.set_scale_bar_visibility(False)

            can_show_defined_line = ui_enabled and line_is_defined
            self._show_scale_line_checkbox.setEnabled(can_show_defined_line)
            if not can_show_defined_line:
                self._show_scale_line_checkbox.setChecked(False)

        finally:
            self._block_scale_signals = False
        
        logger.debug(f"ScalePanelController: UI update complete. Scale bar visible: {self._image_view._scale_bar_widget.isVisible()}, "
                     f"ShowScaleLine enabled: {self._show_scale_line_checkbox.isEnabled()}, "
                     f"ShowScaleLine checked: {self._show_scale_line_checkbox.isChecked()}")


class CoordinatePanelController(QtCore.QObject):
    """
    Manages the UI logic for the Coordinate System panel.
    """
    # Signals to notify MainWindow of necessary actions
    needsRedraw = QtCore.Signal()
    pointsTableNeedsUpdate = QtCore.Signal()
    statusBarMessage = QtCore.Signal(str, int) # message, timeout

    def __init__(self,
                 main_window_ref: 'MainWindow', # Added MainWindow reference
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
                 cursor_pos_labels_px: Dict[str, QtWidgets.QLabel],
                 cursor_pos_labels_m: Dict[str, QtWidgets.QLabel],
                 parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._main_window_ref = main_window_ref # Store MainWindow reference
        self._coord_transformer = coord_transformer; self._image_view = image_view; self._scale_manager = scale_manager
        self._coord_system_group = coord_system_group; self._coord_top_left_radio = coord_top_left_radio; self._coord_bottom_left_radio = coord_bottom_left_radio
        self._coord_custom_radio = coord_custom_radio; self._coord_top_left_origin_label = coord_top_left_origin_label; self._coord_bottom_left_origin_label = coord_bottom_left_origin_label
        self._coord_custom_origin_label = coord_custom_origin_label; self._set_origin_button = set_origin_button; self._show_origin_checkbox = show_origin_checkbox
        self._cursor_pos_labels_px = cursor_pos_labels_px; self._cursor_pos_labels_m = cursor_pos_labels_m
        self._is_setting_origin: bool = False; self._show_origin_marker: bool = True; self._last_scene_mouse_x: float = -1.0; self._last_scene_mouse_y: float = -1.0; self._video_loaded: bool = False
        self._coord_system_group.buttonToggled.connect(self._on_coordinate_mode_changed)
        self._set_origin_button.clicked.connect(self._on_enter_set_origin_mode)
        self._show_origin_checkbox.stateChanged.connect(self._on_toggle_show_origin)
        self.update_ui_display()

    def set_video_loaded_status(self, is_loaded: bool) -> None:
        if self._video_loaded != is_loaded:
            self._video_loaded = is_loaded
            if not is_loaded:
                self._is_setting_origin = False
                if self._image_view:
                    self._image_view.set_interaction_mode(InteractionMode.NORMAL)
                self._show_origin_marker = True
            self.update_ui_display()

    def set_video_height(self, height: int) -> None:
        self._coord_transformer.set_video_height(height)
        self.update_ui_display()

    @QtCore.Slot(QtWidgets.QAbstractButton, bool)
    def _on_coordinate_mode_changed(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        if not checked: return

        new_mode = CoordinateSystem.TOP_LEFT
        if button == self._coord_bottom_left_radio: new_mode = CoordinateSystem.BOTTOM_LEFT
        elif button == self._coord_custom_radio: new_mode = CoordinateSystem.CUSTOM

        if self._coord_transformer.mode != new_mode:
            self._coord_transformer.set_mode(new_mode)
            logger.info(f"Coordinate system mode changed to: {new_mode.name}")
            self.update_ui_display()
            self.pointsTableNeedsUpdate.emit()
            if self._show_origin_marker: self.needsRedraw.emit()

    @QtCore.Slot()
    def _on_enter_set_origin_mode(self) -> None:
        if not self._video_loaded: self.statusBarMessage.emit("Load a video first to set origin.", 3000); return
        # --- MODIFICATION: Cancel other definition modes ---
        if hasattr(self._main_window_ref, '_is_defining_measurement_line') and self._main_window_ref._is_defining_measurement_line:
            logger.debug("Cancelling active measurement line definition before 'Set Origin'.")
            self._main_window_ref._cancel_active_line_definition_ui_reset()
        if hasattr(self._main_window_ref, 'scale_panel_controller') and self._main_window_ref.scale_panel_controller and self._main_window_ref.scale_panel_controller._is_setting_scale_by_line:
            logger.debug("Cancelling active 'Set Scale by Line' before 'Set Origin'.")
            self._main_window_ref.scale_panel_controller.cancel_set_scale_by_line()
        # --- END MODIFICATION ---
        self._is_setting_origin = True; self._image_view.set_interaction_mode(InteractionMode.SET_ORIGIN)
        self.statusBarMessage.emit("Click on the image to set the custom origin.", 0)

    @QtCore.Slot(float, float)
    def _on_set_custom_origin(self, scene_x: float, scene_y: float) -> None:
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
        self._show_origin_marker = (state == QtCore.Qt.CheckState.Checked.value)
        logger.info(f"Origin marker visibility set to: {self._show_origin_marker}")
        self.needsRedraw.emit()

    def get_show_origin_marker_status(self) -> bool:
        return self._show_origin_marker
        
    def is_setting_origin_mode(self) -> bool:
        return self._is_setting_origin

    @QtCore.Slot()
    def update_ui_display(self) -> None:
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

        is_enabled = self._video_loaded
        self._coord_top_left_radio.setEnabled(is_enabled)
        self._coord_bottom_left_radio.setEnabled(is_enabled)
        self._coord_custom_radio.setEnabled(is_enabled)
        self._set_origin_button.setEnabled(is_enabled)
        self._show_origin_checkbox.setEnabled(is_enabled)
        
        self._on_handle_mouse_moved(self._last_scene_mouse_x, self._last_scene_mouse_y)
        logger.debug("CoordinatePanelController.update_ui_display emitting pointsTableNeedsUpdate.")
        self.pointsTableNeedsUpdate.emit()

    @QtCore.Slot(float, float)
    def _on_handle_mouse_moved(self, scene_x_px: float, scene_y_px: float) -> None:
        self._last_scene_mouse_x = scene_x_px
        self._last_scene_mouse_y = scene_y_px
        placeholder = "(--, --)"
        scale_is_set = self._scale_manager.get_scale_m_per_px() is not None

        if not self._video_loaded or scene_x_px == -1.0:
            for label_group in [self._cursor_pos_labels_px, self._cursor_pos_labels_m]:
                for label in label_group.values(): label.setText(placeholder)
            return

        coords_px = {
            "TL": self._coord_transformer.transform_point_for_display(scene_x_px, scene_y_px)
                  if self._coord_transformer.mode == CoordinateSystem.TOP_LEFT else
                  CoordinateTransformer().transform_point_for_display(scene_x_px, scene_y_px),
            "BL": CoordinateTransformer().transform_point_for_display(scene_x_px, scene_y_px)
        }
        bl_origin_x_tl_temp, bl_origin_y_tl_temp = (0.0, float(self._coord_transformer.video_height)) if self._coord_transformer.video_height > 0 else (0.0,0.0)
        coords_px["BL"] = (coords_px["BL"][0] - bl_origin_x_tl_temp, -(coords_px["BL"][1] - bl_origin_y_tl_temp))

        if self._coord_transformer.mode == CoordinateSystem.CUSTOM:
            custom_origin_x_tl, custom_origin_y_tl = self._coord_transformer.get_current_origin_tl()
        else:
            meta = self._coord_transformer.get_metadata()
            custom_origin_x_tl = meta.get("origin_x_tl", 0.0)
            custom_origin_y_tl = meta.get("origin_y_tl", 0.0)
        
        tl_for_custom_display = CoordinateTransformer().transform_point_for_display(scene_x_px, scene_y_px)
        coords_px["Custom"] = (tl_for_custom_display[0] - custom_origin_x_tl, -(tl_for_custom_display[1] - custom_origin_y_tl))

        for key, label in self._cursor_pos_labels_px.items():
            if key in coords_px: label.setText(f"({coords_px[key][0]:.1f}, {coords_px[key][1]:.1f})")
            else: label.setText(placeholder)

        if scale_is_set:
            m_per_px = self._scale_manager.get_scale_m_per_px()
            for key, label in self._cursor_pos_labels_m.items():
                if key in coords_px and m_per_px is not None:
                    coords_m = (coords_px[key][0] * m_per_px, coords_px[key][1] * m_per_px)
                    label.setText(f"({coords_m[0]:.2f}, {coords_m[1]:.2f})")
                else: label.setText(placeholder)
        else:
            for label in self._cursor_pos_labels_m.values(): label.setText(placeholder)
    
    @QtCore.Slot()
    def _trigger_cursor_label_update_slot(self) -> None:
        self._on_handle_mouse_moved(self._last_scene_mouse_x, self._last_scene_mouse_y)