# view_menu_controller.py
"""
Controller for managing the 'View' menu and its associated overlay visibility actions.
"""
import logging
from typing import TYPE_CHECKING, Optional

from PySide6 import QtCore, QtGui, QtWidgets

import settings_manager # For accessing setting keys and values

if TYPE_CHECKING:
    from main_window import MainWindow # For type hinting main_window_ref
    from interactive_image_view import InteractiveImageView

logger = logging.getLogger(__name__)

class ViewMenuController(QtCore.QObject):
    """
    Manages the creation, state, and actions of the View menu items
    related to overlay visibility.
    """
    # Type hints for QActions managed by this controller
    viewShowFilenameAction: Optional[QtGui.QAction] = None
    viewShowTimeAction: Optional[QtGui.QAction] = None
    viewShowFrameNumberAction: Optional[QtGui.QAction] = None
    viewShowScaleBarAction: Optional[QtGui.QAction] = None
    viewShowScaleLineAction: Optional[QtGui.QAction] = None
    viewShowOriginMarkerAction: Optional[QtGui.QAction] = None
    # --- NEW ACTION FOR MEASUREMENT LINE LENGTHS ---
    viewShowMeasurementLineLengthsAction: Optional[QtGui.QAction] = None

    def __init__(self,
                 main_window_ref: 'MainWindow',
                 image_view_ref: 'InteractiveImageView',
                 parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._main_window_ref = main_window_ref
        self._image_view_ref = image_view_ref
        self._view_menu: Optional[QtWidgets.QMenu] = None
        logger.debug("ViewMenuController initialized.")

    def setup_view_menu(self, menu_bar: QtWidgets.QMenuBar) -> None:
        """Creates the View menu and populates it with actions."""
        logger.info("Setting up View menu...")
        self._view_menu = menu_bar.addMenu("&View")

        # --- Info Overlays ---
        self.viewShowFilenameAction = QtGui.QAction("Show Filename", self._main_window_ref, checkable=True)
        self.viewShowFilenameAction.setStatusTip("Toggle visibility of the video filename overlay")
        self.viewShowFilenameAction.triggered.connect(
            lambda checked: self._handle_info_overlay_action_triggered(settings_manager.KEY_INFO_OVERLAY_SHOW_FILENAME, checked)
        )
        self._view_menu.addAction(self.viewShowFilenameAction)

        self.viewShowTimeAction = QtGui.QAction("Show Time", self._main_window_ref, checkable=True)
        self.viewShowTimeAction.setStatusTip("Toggle visibility of the current/total time overlay")
        self.viewShowTimeAction.triggered.connect(
            lambda checked: self._handle_info_overlay_action_triggered(settings_manager.KEY_INFO_OVERLAY_SHOW_TIME, checked)
        )
        self._view_menu.addAction(self.viewShowTimeAction)

        self.viewShowFrameNumberAction = QtGui.QAction("Show Frame Number", self._main_window_ref, checkable=True)
        self.viewShowFrameNumberAction.setStatusTip("Toggle visibility of the current/total frame number overlay")
        self.viewShowFrameNumberAction.triggered.connect(
            lambda checked: self._handle_info_overlay_action_triggered(settings_manager.KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER, checked)
        )
        self._view_menu.addAction(self.viewShowFrameNumberAction)

        self._view_menu.addSeparator()

        # --- Synced Overlays (Scale Bar, Scale Line, Origin Marker) ---
        self.viewShowScaleBarAction = QtGui.QAction("Show Scale Bar", self._main_window_ref, checkable=True)
        self.viewShowScaleBarAction.setStatusTip("Toggle visibility of the on-screen scale bar")
        self.viewShowScaleBarAction.triggered.connect(
            lambda checked: self._handle_synced_overlay_action_triggered(self._main_window_ref.showScaleBarCheckBox, checked)
        )
        self._view_menu.addAction(self.viewShowScaleBarAction)

        self.viewShowScaleLineAction = QtGui.QAction("Show Defined Scale Line", self._main_window_ref, checkable=True)
        self.viewShowScaleLineAction.setStatusTip("Toggle visibility of the user-defined scale line")
        self.viewShowScaleLineAction.triggered.connect(
            lambda checked: self._handle_synced_overlay_action_triggered(self._main_window_ref.showScaleLineCheckBox, checked)
        )
        self._view_menu.addAction(self.viewShowScaleLineAction)

        self.viewShowOriginMarkerAction = QtGui.QAction("Show Origin Marker", self._main_window_ref, checkable=True)
        self.viewShowOriginMarkerAction.setStatusTip("Toggle visibility of the coordinate system origin marker")
        self.viewShowOriginMarkerAction.triggered.connect(
            lambda checked: self._handle_synced_overlay_action_triggered(self._main_window_ref.showOriginCheckBox, checked)
        )
        self._view_menu.addAction(self.viewShowOriginMarkerAction)

        self._view_menu.addSeparator() # Separator before measurement line specific toggle

        # --- NEW: Action for Measurement Line Lengths --- [cite: 63]
        self.viewShowMeasurementLineLengthsAction = QtGui.QAction("Show Measurement Line Lengths", self._main_window_ref, checkable=True)
        self.viewShowMeasurementLineLengthsAction.setStatusTip("Toggle visibility of length labels on measurement lines")
        self.viewShowMeasurementLineLengthsAction.triggered.connect(self._handle_show_measurement_line_lengths_triggered)
        self._view_menu.addAction(self.viewShowMeasurementLineLengthsAction)
        # --- END NEW ---

        self.sync_all_menu_items_from_settings_and_panels() # Initial sync
        logger.info("View menu setup complete.")

    @QtCore.Slot(str, bool)
    def _handle_info_overlay_action_triggered(self, setting_key: str, checked: bool) -> None:
        """Handles toggling for info overlays (Filename, Time, Frame Number)."""
        if not self._main_window_ref.video_loaded:
            if setting_key == settings_manager.KEY_INFO_OVERLAY_SHOW_FILENAME and self.viewShowFilenameAction: self.viewShowFilenameAction.setChecked(False)
            elif setting_key == settings_manager.KEY_INFO_OVERLAY_SHOW_TIME and self.viewShowTimeAction: self.viewShowTimeAction.setChecked(False)
            elif setting_key == settings_manager.KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER and self.viewShowFrameNumberAction: self.viewShowFrameNumberAction.setChecked(False)
            return

        logger.debug(f"Info overlay action triggered: {setting_key} to {checked}")
        settings_manager.set_setting(setting_key, checked)
        if self._image_view_ref:
            self._image_view_ref.refresh_info_overlay_appearance()

    # --- NEW HANDLER for Measurement Line Lengths Visibility ---
    @QtCore.Slot(bool)
    def _handle_show_measurement_line_lengths_triggered(self, checked: bool) -> None:
        """Handles toggling for showing measurement line lengths."""
        # This action's enabled state might depend on video loaded, but the setting itself is global.
        logger.debug(f"ViewMenuController: Show Measurement Line Lengths action triggered to {checked}.")
        settings_manager.set_setting(settings_manager.KEY_SHOW_MEASUREMENT_LINE_LENGTHS, checked)
        # Trigger a redraw of the scene overlay in MainWindow
        if hasattr(self._main_window_ref, '_redraw_scene_overlay'):
            self._main_window_ref._redraw_scene_overlay()
        self.sync_all_menu_items_from_settings_and_panels() # Ensure menu is up-to-date
    # --- END NEW HANDLER ---

    @QtCore.Slot(QtWidgets.QCheckBox, bool)
    def _handle_synced_overlay_action_triggered(self,
                                                 panel_checkbox: Optional[QtWidgets.QCheckBox],
                                                 menu_action_checked_state: bool) -> None:
        """
        Handles toggling for synced overlays (Scale Bar, Scale Line, Origin) from the View menu.
        """
        if not panel_checkbox:
            logger.warning("Synced overlay action triggered but panel_checkbox is None.")
            return

        logger.debug(f"ViewMenuController: Menu action for '{panel_checkbox.objectName()}' triggered. Desired state: {menu_action_checked_state}")

        if panel_checkbox.isChecked() != menu_action_checked_state:
            panel_checkbox.blockSignals(True)
            panel_checkbox.setChecked(menu_action_checked_state)
            panel_checkbox.blockSignals(False)
            logger.debug(f"ViewMenuController: Panel checkbox '{panel_checkbox.objectName()}' state programmatically set to {menu_action_checked_state}.")

        if panel_checkbox is self._main_window_ref.showScaleBarCheckBox:
            if self._main_window_ref.scale_panel_controller:
                logger.debug(f"ViewMenuController: Directly calling ScalePanelController._on_show_scale_bar_toggled({menu_action_checked_state})")
                self._main_window_ref.scale_panel_controller._on_show_scale_bar_toggled(menu_action_checked_state)
        elif panel_checkbox is self._main_window_ref.showScaleLineCheckBox:
            if self._main_window_ref.scale_panel_controller:
                logger.debug(f"ViewMenuController: Directly calling ScalePanelController._on_show_defined_scale_line_toggled({menu_action_checked_state})")
                self._main_window_ref.scale_panel_controller._on_show_defined_scale_line_toggled(menu_action_checked_state)
        elif panel_checkbox is self._main_window_ref.showOriginCheckBox:
            if self._main_window_ref.coord_panel_controller:
                qt_check_state = QtCore.Qt.CheckState.Checked.value if menu_action_checked_state else QtCore.Qt.CheckState.Unchecked.value
                logger.debug(f"ViewMenuController: Directly calling CoordinatePanelController._on_toggle_show_origin({qt_check_state})")
                self._main_window_ref.coord_panel_controller._on_toggle_show_origin(qt_check_state)
        
        self.sync_all_menu_items_from_settings_and_panels()

    @QtCore.Slot()
    def sync_panel_checkbox_to_menu(self, panel_checkbox: QtWidgets.QCheckBox) -> None:
        """
        Called when a panel checkbox (Scale Bar, Scale Line, Origin) is toggled by the user.
        Updates the corresponding View menu QAction's checked state.
        """
        if not self._view_menu: return

        action_to_sync: Optional[QtGui.QAction] = None
        # --- NO CHANGE HERE FOR MEASUREMENT LINE LENGTHS AS IT'S NOT DIRECTLY TIED TO A PANEL CHECKBOX ---
        if panel_checkbox is self._main_window_ref.showScaleBarCheckBox:
            action_to_sync = self.viewShowScaleBarAction
        elif panel_checkbox is self._main_window_ref.showScaleLineCheckBox:
            action_to_sync = self.viewShowScaleLineAction
        elif panel_checkbox is self._main_window_ref.showOriginCheckBox:
            action_to_sync = self.viewShowOriginMarkerAction

        if action_to_sync:
            new_checkbox_state = panel_checkbox.isChecked()
            if action_to_sync.isChecked() != new_checkbox_state:
                logger.debug(f"ViewMenuController: Panel checkbox '{panel_checkbox.objectName()}' changed by user to {new_checkbox_state}. Syncing menu action '{action_to_sync.text()}'.")
                action_to_sync.blockSignals(True)
                action_to_sync.setChecked(new_checkbox_state)
                action_to_sync.blockSignals(False)
            
            self.sync_all_menu_items_from_settings_and_panels()

    def sync_all_menu_items_from_settings_and_panels(self) -> None:
        """
        Synchronizes all View menu checkable actions with their current settings
        or corresponding panel checkbox states. Also updates enabled states.
        """
        if not self._view_menu:
            logger.warning("ViewMenuController: sync_all_menu_items_from_settings_and_panels called but viewMenu not initialized.")
            return
        logger.debug("ViewMenuController: Syncing all View menu states...")

        video_is_loaded = self._main_window_ref.video_loaded
        scale_is_set = False
        scale_line_is_defined = False
        if self._main_window_ref.scale_manager:
            scale_is_set = self._main_window_ref.scale_manager.get_scale_m_per_px() is not None
            scale_line_is_defined = self._main_window_ref.scale_manager.has_defined_scale_line()

        # Info Overlays
        if self.viewShowFilenameAction:
            self.viewShowFilenameAction.blockSignals(True)
            self.viewShowFilenameAction.setChecked(settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_FILENAME))
            self.viewShowFilenameAction.setEnabled(video_is_loaded)
            self.viewShowFilenameAction.blockSignals(False)
        if self.viewShowTimeAction:
            self.viewShowTimeAction.blockSignals(True)
            self.viewShowTimeAction.setChecked(settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_TIME))
            self.viewShowTimeAction.setEnabled(video_is_loaded)
            self.viewShowTimeAction.blockSignals(False)
        if self.viewShowFrameNumberAction:
            self.viewShowFrameNumberAction.blockSignals(True)
            self.viewShowFrameNumberAction.setChecked(settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER))
            self.viewShowFrameNumberAction.setEnabled(video_is_loaded)
            self.viewShowFrameNumberAction.blockSignals(False)

        # Synced Overlays
        if self.viewShowOriginMarkerAction and self._main_window_ref.showOriginCheckBox:
            self.viewShowOriginMarkerAction.blockSignals(True)
            self.viewShowOriginMarkerAction.setChecked(self._main_window_ref.showOriginCheckBox.isChecked())
            self.viewShowOriginMarkerAction.setEnabled(video_is_loaded)
            self.viewShowOriginMarkerAction.blockSignals(False)
        if self.viewShowScaleBarAction and self._main_window_ref.showScaleBarCheckBox:
            self.viewShowScaleBarAction.blockSignals(True)
            self.viewShowScaleBarAction.setChecked(self._main_window_ref.showScaleBarCheckBox.isChecked())
            self.viewShowScaleBarAction.setEnabled(video_is_loaded and scale_is_set)
            self.viewShowScaleBarAction.blockSignals(False)
        if self.viewShowScaleLineAction and self._main_window_ref.showScaleLineCheckBox:
            self.viewShowScaleLineAction.blockSignals(True)
            self.viewShowScaleLineAction.setChecked(self._main_window_ref.showScaleLineCheckBox.isChecked())
            self.viewShowScaleLineAction.setEnabled(video_is_loaded and scale_line_is_defined)
            self.viewShowScaleLineAction.blockSignals(False)

        # --- NEW: Sync Measurement Line Lengths Action --- [cite: 64]
        if self.viewShowMeasurementLineLengthsAction:
            self.viewShowMeasurementLineLengthsAction.blockSignals(True)
            # Checked state from settings
            self.viewShowMeasurementLineLengthsAction.setChecked(settings_manager.get_setting(settings_manager.KEY_SHOW_MEASUREMENT_LINE_LENGTHS))
            # Enabled if video is loaded (as lengths might be shown for any existing lines)
            # or perhaps if element_manager has any measurement lines. For simplicity, video_is_loaded for now.
            self.viewShowMeasurementLineLengthsAction.setEnabled(video_is_loaded)
            self.viewShowMeasurementLineLengthsAction.blockSignals(False)
        # --- END NEW ---

        logger.debug("ViewMenuController: All View menu states synced.")

    def handle_video_loaded_state_changed(self, is_loaded: bool) -> None:
        logger.debug(f"ViewMenuController handling video loaded state: {is_loaded}")
        self.sync_all_menu_items_from_settings_and_panels()
        if is_loaded and self._image_view_ref:
             self._image_view_ref.refresh_info_overlay_appearance()

    def handle_preferences_applied(self) -> None:
        logger.debug("ViewMenuController handling preferences applied.")
        self.sync_all_menu_items_from_settings_and_panels()
        if self._image_view_ref:
            self._image_view_ref.refresh_info_overlay_appearance()