# panel_controllers.py
"""
Contains controller classes for managing UI logic for various panels
in the MainWindow.
"""
import logging
from typing import Optional, TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from main_window import MainWindow # To avoid circular import, only for type hinting
    from scale_manager import ScaleManager
    from interactive_image_view import InteractiveImageView

logger = logging.getLogger(__name__)

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