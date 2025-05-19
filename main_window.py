# main_window.py
import sys
import os
import math
import logging
from PySide6 import QtCore, QtGui, QtWidgets
from typing import Optional, List, Tuple, Dict, Any

from metadata_dialog import MetadataDialog
import config
from interactive_image_view import InteractiveImageView, InteractionMode
from track_manager import TrackManager, TrackVisibilityMode, PointData, VisualElement, UndoActionType
import file_io
from video_handler import VideoHandler
import ui_setup # This will setup the new QLineEdit and QLabel attributes
from coordinates import CoordinateSystem, CoordinateTransformer
import settings_manager
from preferences_dialog import PreferencesDialog
from scale_manager import ScaleManager
from panel_controllers import ScalePanelController, CoordinatePanelController
from table_controllers import TrackDataViewController
from export_handler import ExportHandler, ExportResolutionMode

logger = logging.getLogger(__name__)

basedir = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(basedir, "PyroTracker.ico")

class MainWindow(QtWidgets.QMainWindow):
    # --- Instance Variable Type Hinting (ensure these match ui_setup.py) ---
    track_manager: TrackManager
    imageView: InteractiveImageView
    video_handler: VideoHandler
    coord_transformer: CoordinateTransformer
    scale_manager: ScaleManager
    scale_panel_controller: Optional[ScalePanelController]
    coord_panel_controller: Optional[CoordinatePanelController]
    table_data_controller: Optional[TrackDataViewController]
    _export_handler: Optional[ExportHandler] = None

    total_frames: int = 0
    current_frame_index: int = -1
    video_loaded: bool = False
    is_playing: bool = False
    fps: float = 0.0
    total_duration_ms: float = 0.0
    video_filepath: str = ""
    frame_width: int = 0
    frame_height: int = 0
    _auto_advance_enabled: bool = False
    _auto_advance_frames: int = 1

    mainSplitter: QtWidgets.QSplitter
    leftPanelWidget: QtWidgets.QWidget
    rightPanelWidget: QtWidgets.QWidget
    frameSlider: QtWidgets.QSlider
    playPauseButton: QtWidgets.QPushButton
    prevFrameButton: QtWidgets.QPushButton
    nextFrameButton: QtWidgets.QPushButton
    currentFrameLineEdit: QtWidgets.QLineEdit 
    totalFramesLabel: QtWidgets.QLabel     
    currentTimeLineEdit: QtWidgets.QLineEdit
    totalTimeLabel: QtWidgets.QLabel      
    zoomLevelLineEdit: Optional[QtWidgets.QLineEdit] = None
    dataTabsWidget: QtWidgets.QTabWidget
    tracksTableWidget: QtWidgets.QTableWidget
    pointsTabLabel: QtWidgets.QLabel
    pointsTableWidget: QtWidgets.QTableWidget
    autoAdvanceCheckBox: QtWidgets.QCheckBox
    autoAdvanceSpinBox: QtWidgets.QSpinBox
    coordSystemGroup: QtWidgets.QButtonGroup
    coordTopLeftRadio: QtWidgets.QRadioButton
    coordBottomLeftRadio: QtWidgets.QRadioButton
    coordCustomRadio: QtWidgets.QRadioButton
    coordTopLeftOriginLabel: QtWidgets.QLabel
    coordBottomLeftOriginLabel: QtWidgets.QLabel
    coordCustomOriginLabel: QtWidgets.QLabel
    setOriginButton: QtWidgets.QPushButton
    showOriginCheckBox: QtWidgets.QCheckBox
    cursorPosLabelTL: QtWidgets.QLabel
    cursorPosLabelBL: QtWidgets.QLabel
    cursorPosLabelCustom: QtWidgets.QLabel
    play_icon: QtGui.QIcon
    stop_icon: QtGui.QIcon
    loadTracksAction: QtGui.QAction
    saveTracksAction: QtGui.QAction
    exportViewAction: QtGui.QAction
    exportFrameAction: QtGui.QAction
    newTrackAction: QtGui.QAction
    videoInfoAction: QtGui.QAction
    preferencesAction: QtGui.QAction
    undoAction: Optional[QtGui.QAction] = None
    scale_m_per_px_input: Optional[QtWidgets.QLineEdit] = None
    scale_px_per_m_input: Optional[QtWidgets.QLineEdit] = None
    setScaleByFeatureButton: Optional[QtWidgets.QPushButton] = None
    showScaleLineCheckBox: Optional[QtWidgets.QCheckBox] = None
    scale_reset_button: Optional[QtWidgets.QPushButton] = None
    scale_display_meters_checkbox: Optional[QtWidgets.QCheckBox] = None
    showScaleBarCheckBox: Optional[QtWidgets.QCheckBox] = None
    cursorPosLabelTL_m: Optional[QtWidgets.QLabel] = None
    cursorPosLabelBL_m: Optional[QtWidgets.QLabel] = None
    cursorPosLabelCustom_m: Optional[QtWidgets.QLabel] = None

    pen_origin_marker: QtGui.QPen
    pen_marker_active_current: QtGui.QPen
    pen_marker_active_other: QtGui.QPen
    pen_marker_inactive_current: QtGui.QPen
    pen_marker_inactive_other: QtGui.QPen
    pen_line_active: QtGui.QPen
    pen_line_inactive: QtGui.QPen

    _export_progress_dialog: Optional[QtWidgets.QProgressDialog] = None
    # Properties to store original text during editing are no longer needed at class level
    # if we directly populate with current value on focus.

    def __init__(self) -> None:
        super().__init__()
        logger.info("Initializing MainWindow...")
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QtGui.QIcon(ICON_PATH))

        self.video_handler = VideoHandler(self)
        self.track_manager = TrackManager(self)
        self.coord_transformer = CoordinateTransformer()
        self.scale_manager = ScaleManager(self)
        self._setup_pens()
        
        screen_geometry = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        self.setGeometry(50, 50, int(screen_geometry.width() * 0.8), int(screen_geometry.height() * 0.8))
        self.setMinimumSize(800, 600)

        ui_setup.setup_main_window_ui(self)

        if hasattr(self, 'currentFrameLineEdit') and isinstance(self.currentFrameLineEdit, QtWidgets.QLineEdit):
            self.currentFrameLineEdit.editingFinished.connect(self._handle_frame_input_finished)
            self.currentFrameLineEdit.installEventFilter(self)
            logger.debug("Connected currentFrameLineEdit editingFinished signal and event filter.")
        else:
            logger.error("currentFrameLineEdit is not a QLineEdit or not found after UI setup.")

        if hasattr(self, 'currentTimeLineEdit') and isinstance(self.currentTimeLineEdit, QtWidgets.QLineEdit):
            self.currentTimeLineEdit.editingFinished.connect(self._handle_time_input_finished)
            self.currentTimeLineEdit.installEventFilter(self)
            logger.debug("Connected currentTimeLineEdit editingFinished signal and event filter.")
        else:
            logger.error("currentTimeLineEdit is not a QLineEdit or not found after UI setup.")

        if hasattr(self, 'zoomLevelLineEdit') and isinstance(self.zoomLevelLineEdit, QtWidgets.QLineEdit):
            self.zoomLevelLineEdit.editingFinished.connect(self._handle_zoom_input_finished)
            self.zoomLevelLineEdit.installEventFilter(self) # Use the same event filter
            logger.debug("Connected zoomLevelLineEdit editingFinished signal and event filter.")
        else:
            logger.error("zoomLevelLineEdit is not a QLineEdit or not found after UI setup.")
        
        if self.imageView:
            # Connect viewTransformChanged to update zoom display
            self.imageView.viewTransformChanged.connect(self._update_zoom_display)

        if hasattr(self, 'undoAction') and self.undoAction:
            self.undoAction.triggered.connect(self._trigger_undo_point_action)
            self.undoAction.setEnabled(False) 
            logger.debug("Undo action connected and initially disabled.")
        else:
            logger.warning("Undo action (self.undoAction) not found after UI setup.")

        if self.track_manager and hasattr(self, 'undoAction') and self.undoAction:
            self.track_manager.undoStateChanged.connect(self.undoAction.setEnabled)
            logger.debug("Connected TrackManager.undoStateChanged to undoAction.setEnabled.")

        if all(hasattr(self, attr) and getattr(self, attr) is not None for attr in [
            'scale_m_per_px_input', 'scale_px_per_m_input', 'scale_reset_button',
            'scale_display_meters_checkbox', 'showScaleBarCheckBox',
            'setScaleByFeatureButton', 'showScaleLineCheckBox',
            'imageView', 'scale_manager'
        ]):
            self.scale_panel_controller = ScalePanelController(
                scale_manager=self.scale_manager,
                image_view=self.imageView,
                main_window_ref=self,
                scale_m_per_px_input=self.scale_m_per_px_input, # type: ignore
                scale_px_per_m_input=self.scale_px_per_m_input, # type: ignore
                set_scale_by_feature_button=self.setScaleByFeatureButton, # type: ignore
                show_scale_line_checkbox=self.showScaleLineCheckBox, # type: ignore
                scale_reset_button=self.scale_reset_button, # type: ignore
                scale_display_meters_checkbox=self.scale_display_meters_checkbox, # type: ignore
                show_scale_bar_checkbox=self.showScaleBarCheckBox, # type: ignore
                parent=self
            )
            if self.statusBar():
                 self.scale_panel_controller.statusBarMessage.connect(self.statusBar().showMessage)
            self.scale_panel_controller.requestFrameNavigationControlsDisabled.connect(self._handle_disable_frame_navigation)
            logger.debug("ScalePanelController initialized and signals connected.")
        else:
            logger.error("Scale panel UI elements or core components not found for ScalePanelController.")
            self.scale_panel_controller = None

        if all(hasattr(self, attr) and getattr(self, attr) is not None for attr in [
            'coordSystemGroup', 'coordTopLeftRadio', 'coordBottomLeftRadio', 'coordCustomRadio',
            'coordTopLeftOriginLabel', 'coordBottomLeftOriginLabel', 'coordCustomOriginLabel',
            'setOriginButton', 'showOriginCheckBox', 'cursorPosLabelTL', 'cursorPosLabelBL',
            'cursorPosLabelCustom', 'cursorPosLabelTL_m', 'cursorPosLabelBL_m', 'cursorPosLabelCustom_m',
            'imageView', 'scale_manager'
        ]):
            cursor_labels_px_dict = { "TL": self.cursorPosLabelTL, "BL": self.cursorPosLabelBL, "Custom": self.cursorPosLabelCustom }
            cursor_labels_m_dict = { "TL": self.cursorPosLabelTL_m, "BL": self.cursorPosLabelBL_m, "Custom": self.cursorPosLabelCustom_m } # type: ignore
            self.coord_panel_controller = CoordinatePanelController(
                coord_transformer=self.coord_transformer, image_view=self.imageView,
                scale_manager=self.scale_manager, coord_system_group=self.coordSystemGroup, # type: ignore
                coord_top_left_radio=self.coordTopLeftRadio, coord_bottom_left_radio=self.coordBottomLeftRadio, # type: ignore
                coord_custom_radio=self.coordCustomRadio, coord_top_left_origin_label=self.coordTopLeftOriginLabel, # type: ignore
                coord_bottom_left_origin_label=self.coordBottomLeftOriginLabel, coord_custom_origin_label=self.coordCustomOriginLabel, # type: ignore
                set_origin_button=self.setOriginButton, show_origin_checkbox=self.showOriginCheckBox, # type: ignore
                cursor_pos_labels_px=cursor_labels_px_dict, cursor_pos_labels_m=cursor_labels_m_dict, parent=self
            )
            logger.debug("CoordinatePanelController initialized.")
        else:
            logger.error("Coordinate panel UI elements or core components not found for CoordinatePanelController.")
            self.coord_panel_controller = None

        if all(hasattr(self, attr) and getattr(self, attr) is not None for attr in [
            'tracksTableWidget', 'pointsTableWidget', 'pointsTabLabel', 'track_manager',
            'video_handler', 'scale_manager', 'coord_transformer'
        ]):
            self.table_data_controller = TrackDataViewController(
                main_window_ref=self,
                track_manager=self.track_manager,
                video_handler=self.video_handler,
                scale_manager=self.scale_manager,
                coord_transformer=self.coord_transformer,
                tracks_table_widget=self.tracksTableWidget, # type: ignore
                points_table_widget=self.pointsTableWidget, # type: ignore
                points_tab_label=self.pointsTabLabel, # type: ignore
                parent=self
            )
            logger.debug("TrackDataViewController initialized.")
        else:
            logger.error("Table UI elements or core components not found for TrackDataViewController.")
            self.table_data_controller = None

        status_bar_instance = self.statusBar()
        if status_bar_instance:
            status_bar_instance.showMessage("Ready. Load a video via File -> Open Video...")

        self._export_handler = ExportHandler(
            video_handler=self.video_handler, track_manager=self.track_manager,
            scale_manager=self.scale_manager, coord_transformer=self.coord_transformer,
            image_view=self.imageView, main_window=self, parent=self )
        logger.debug("ExportHandler initialized in MainWindow.")

        self.video_handler.videoLoaded.connect(self._handle_video_loaded)
        self.video_handler.videoLoadFailed.connect(self._handle_video_load_failed)
        self.video_handler.frameChanged.connect(self._handle_frame_changed)
        self.video_handler.playbackStateChanged.connect(self._handle_playback_state_changed)
        if self.imageView:
            self.imageView.pointClicked.connect(self._handle_add_point_click)
            self.imageView.frameStepRequested.connect(self._handle_frame_step)
            self.imageView.modifiedClick.connect(self._handle_modified_click)
            if self.coord_panel_controller:
                self.imageView.originSetRequest.connect(self.coord_panel_controller._on_set_custom_origin)
                self.imageView.sceneMouseMoved.connect(self.coord_panel_controller._on_handle_mouse_moved)
            if self.scale_panel_controller:
                self.imageView.viewTransformChanged.connect(self.scale_panel_controller._on_view_transform_changed)
        if self.table_data_controller:
            self.track_manager.trackListChanged.connect(self.table_data_controller.update_tracks_table_ui)
            self.track_manager.activeTrackDataChanged.connect(self.table_data_controller.update_points_table_ui)
            self.track_manager.activeTrackDataChanged.connect(self.table_data_controller._sync_tracks_table_selection_with_manager)
        self.track_manager.visualsNeedUpdate.connect(self._redraw_scene_overlay)
        if self.scale_panel_controller: self.scale_manager.scaleOrUnitChanged.connect(self.scale_panel_controller.update_ui_from_manager)
        if self.table_data_controller: self.scale_manager.scaleOrUnitChanged.connect(self.table_data_controller.update_points_table_ui)
        if self.coord_panel_controller: self.scale_manager.scaleOrUnitChanged.connect(self.coord_panel_controller._trigger_cursor_label_update_slot)
        if self.coord_panel_controller:
            self.coord_panel_controller.needsRedraw.connect(self._redraw_scene_overlay)
            if self.table_data_controller: self.coord_panel_controller.pointsTableNeedsUpdate.connect(self.table_data_controller.update_points_table_ui)
            if status_bar_instance: self.coord_panel_controller.statusBarMessage.connect(status_bar_instance.showMessage)
        if self.table_data_controller:
            self.table_data_controller.seekVideoToFrame.connect(self.video_handler.seek_frame)
            self.table_data_controller.updateMainWindowUIState.connect(self._update_ui_state)
            if status_bar_instance: self.table_data_controller.statusBarMessage.connect(status_bar_instance.showMessage)
            if hasattr(self.tracksTableWidget, 'horizontalHeader') and hasattr(self.tracksTableWidget.horizontalHeader(), 'sectionClicked'): # type: ignore
                 self.tracksTableWidget.horizontalHeader().sectionClicked.connect(self.table_data_controller.handle_visibility_header_clicked) # type: ignore
        if self.frameSlider: self.frameSlider.valueChanged.connect(self._slider_value_changed) # type: ignore
        if self.playPauseButton: self.playPauseButton.clicked.connect(self._toggle_playback) # type: ignore
        if self.prevFrameButton: self.prevFrameButton.clicked.connect(self._show_previous_frame) # type: ignore
        if self.nextFrameButton: self.nextFrameButton.clicked.connect(self._show_next_frame) # type: ignore
        if self.autoAdvanceCheckBox: self.autoAdvanceCheckBox.stateChanged.connect(self._handle_auto_advance_toggled) # type: ignore
        if self.autoAdvanceSpinBox: self.autoAdvanceSpinBox.valueChanged.connect(self._handle_auto_advance_frames_changed) # type: ignore
        if self.videoInfoAction: self.videoInfoAction.triggered.connect(self._show_video_info_dialog) # type: ignore
        if self.preferencesAction: self.preferencesAction.triggered.connect(self._show_preferences_dialog) # type: ignore
        if self.newTrackAction:
            self.newTrackAction.setShortcut(QtGui.QKeySequence.StandardKey.New)
            self.newTrackAction.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            self.newTrackAction.triggered.connect(self._create_new_track)
        if hasattr(self, 'exportViewAction') and self.exportViewAction and self._export_handler: # type: ignore
            self.exportViewAction.triggered.connect(self._trigger_export_video) # type: ignore
        if hasattr(self, 'exportFrameAction') and self.exportFrameAction and self._export_handler: # type: ignore
            self.exportFrameAction.triggered.connect(self._trigger_export_frame) # type: ignore
        if self._export_handler:
            self._export_handler.exportStarted.connect(self._on_export_started)
            self._export_handler.exportProgress.connect(self._on_export_progress)
            self._export_handler.exportFinished.connect(self._on_export_finished)

        self._update_ui_state()
        if self.table_data_controller:
            self.table_data_controller.update_tracks_table_ui()
            self.table_data_controller.update_points_table_ui()
        if self.coord_panel_controller: self.coord_panel_controller.update_ui_display()
        if self.scale_panel_controller: self.scale_panel_controller.update_ui_from_manager()
        logger.info("MainWindow initialization complete.")


    def _setup_pens(self) -> None:
        logger.debug("Setting up QPen objects using current settings...")
        color_active_marker = settings_manager.get_setting(settings_manager.KEY_ACTIVE_MARKER_COLOR)
        color_active_line = settings_manager.get_setting(settings_manager.KEY_ACTIVE_LINE_COLOR)
        color_active_current_marker = settings_manager.get_setting(settings_manager.KEY_ACTIVE_CURRENT_MARKER_COLOR)
        color_inactive_marker = settings_manager.get_setting(settings_manager.KEY_INACTIVE_MARKER_COLOR)
        color_inactive_line = settings_manager.get_setting(settings_manager.KEY_INACTIVE_LINE_COLOR)
        color_inactive_current_marker = settings_manager.get_setting(settings_manager.KEY_INACTIVE_CURRENT_MARKER_COLOR)
        color_origin_marker = settings_manager.get_setting(settings_manager.KEY_ORIGIN_MARKER_COLOR)
        try:
            line_width = float(settings_manager.get_setting(settings_manager.KEY_LINE_WIDTH))
            marker_pen_width = 1.0
            origin_pen_width = config.DEFAULT_ORIGIN_MARKER_PEN_WIDTH
        except (TypeError, ValueError):
             logger.warning("Invalid size/width setting found, using defaults.")
             line_width = settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_LINE_WIDTH]
             marker_pen_width = 1.0
             origin_pen_width = config.DEFAULT_ORIGIN_MARKER_PEN_WIDTH
        def _create_pen(color_val: Any, width: float, default_color: QtGui.QColor) -> QtGui.QPen:
            color = color_val if isinstance(color_val, QtGui.QColor) else QtGui.QColor(str(color_val))
            if not color.isValid():
                logger.warning(f"Invalid color '{color_val}' retrieved, using default {default_color.name()}.")
                color = default_color
            pen = QtGui.QPen(color, width); pen.setCosmetic(True); return pen
        self.pen_marker_active_current = _create_pen(color_active_current_marker, marker_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ACTIVE_CURRENT_MARKER_COLOR])
        self.pen_marker_active_other = _create_pen(color_active_marker, marker_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ACTIVE_MARKER_COLOR])
        self.pen_line_active = _create_pen(color_active_line, line_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ACTIVE_LINE_COLOR])
        self.pen_marker_inactive_current = _create_pen(color_inactive_current_marker, marker_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_INACTIVE_CURRENT_MARKER_COLOR])
        self.pen_marker_inactive_other = _create_pen(color_inactive_marker, marker_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_INACTIVE_MARKER_COLOR])
        self.pen_line_inactive = _create_pen(color_inactive_line, line_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_INACTIVE_LINE_COLOR])
        self.pen_origin_marker = _create_pen(color_origin_marker, origin_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ORIGIN_MARKER_COLOR])
        logger.debug("QPen setup complete using settings.")


    def _reset_ui_after_video_close(self) -> None:
        logger.debug("Resetting UI elements for no video loaded state.")
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")
        status_bar = self.statusBar()
        if status_bar: status_bar.clearMessage()

        # Reset new QLineEdits and QLabels for frame/time
        if hasattr(self, 'currentFrameLineEdit') and isinstance(self.currentFrameLineEdit, QtWidgets.QLineEdit):
            self.currentFrameLineEdit.blockSignals(True)
            self.currentFrameLineEdit.setReadOnly(True)
            self.currentFrameLineEdit.setText("-")
            self.currentFrameLineEdit.deselect()
            self.currentFrameLineEdit.blockSignals(False)
        if hasattr(self, 'totalFramesLabel') and isinstance(self.totalFramesLabel, QtWidgets.QLabel):
            self.totalFramesLabel.setText("/ -")

        if hasattr(self, 'currentTimeLineEdit') and isinstance(self.currentTimeLineEdit, QtWidgets.QLineEdit):
            self.currentTimeLineEdit.blockSignals(True)
            self.currentTimeLineEdit.setReadOnly(True)
            self.currentTimeLineEdit.setText("--:--.---")
            self.currentTimeLineEdit.deselect()
            self.currentTimeLineEdit.blockSignals(False)
        if hasattr(self, 'totalTimeLabel') and isinstance(self.totalTimeLabel, QtWidgets.QLabel):
            self.totalTimeLabel.setText("/ --:--.---")

        if hasattr(self, 'zoomLevelLineEdit') and self.zoomLevelLineEdit is not None:
            self.zoomLevelLineEdit.blockSignals(True)
            self.zoomLevelLineEdit.setReadOnly(True)
            self.zoomLevelLineEdit.setText("---.-")
            self.zoomLevelLineEdit.deselect()
            self.zoomLevelLineEdit.clearFocus()
            self.zoomLevelLineEdit.blockSignals(False)
        
        if self.frameSlider:
            self.frameSlider.blockSignals(True)
            self.frameSlider.setValue(0)
            self.frameSlider.setMaximum(0)
            self.frameSlider.blockSignals(False)
        if self.imageView:
            self.imageView.clearOverlay()
            self.imageView.setPixmap(QtGui.QPixmap())
            self.imageView.resetInitialLoadFlag()
            self.imageView.set_scale_bar_visibility(False)
            self.imageView.set_interaction_mode(InteractionMode.NORMAL)
        
        self.coord_transformer = CoordinateTransformer()
        if self.coord_panel_controller:
            self.coord_panel_controller._coord_transformer = self.coord_transformer
        
        self.scale_manager.reset()
        if self.scale_panel_controller: self.scale_panel_controller.set_video_loaded_status(False)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_loaded_status(False)
        if self.table_data_controller: self.table_data_controller.set_video_loaded_status(False)
        
        self._update_ui_state()


    def _update_ui_state(self) -> None:
        is_video_loaded: bool = self.video_loaded
        is_setting_scale_by_line = False
        if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line'):
            is_setting_scale_by_line = self.scale_panel_controller._is_setting_scale_by_line # type: ignore

        nav_enabled_during_action = not is_setting_scale_by_line

        if self.frameSlider: self.frameSlider.setEnabled(is_video_loaded and nav_enabled_during_action)
        if self.prevFrameButton: self.prevFrameButton.setEnabled(is_video_loaded and nav_enabled_during_action)
        if self.nextFrameButton: self.nextFrameButton.setEnabled(is_video_loaded and nav_enabled_during_action)

        can_play: bool = is_video_loaded and self.fps > 0 and nav_enabled_during_action
        if self.playPauseButton: self.playPauseButton.setEnabled(can_play)

        # Enable/disable frame and time input fields
        if hasattr(self, 'currentFrameLineEdit') and self.currentFrameLineEdit is not None:
            self.currentFrameLineEdit.setEnabled(is_video_loaded and nav_enabled_during_action)
        if hasattr(self, 'currentTimeLineEdit') and self.currentTimeLineEdit is not None:
            self.currentTimeLineEdit.setEnabled(is_video_loaded and nav_enabled_during_action)

        # --- NEW: Enable/Disable Zoom Level LineEdit ---
        if hasattr(self, 'zoomLevelLineEdit') and self.zoomLevelLineEdit is not None:
            self.zoomLevelLineEdit.setEnabled(is_video_loaded and nav_enabled_during_action)
            if not is_video_loaded: # Also ensure text is reset if video becomes unloaded
                self.zoomLevelLineEdit.setText("---.-")
        # --- END NEW ---

        if self.newTrackAction: self.newTrackAction.setEnabled(is_video_loaded)
        if self.autoAdvanceCheckBox: self.autoAdvanceCheckBox.setEnabled(is_video_loaded)
        if self.autoAdvanceSpinBox: self.autoAdvanceSpinBox.setEnabled(is_video_loaded)

        if self.playPauseButton and self.stop_icon and self.play_icon:
            self.playPauseButton.setIcon(self.stop_icon if self.is_playing else self.play_icon)
            self.playPauseButton.setToolTip("Stop Video (Space)" if self.is_playing else "Play Video (Space)")

        if self.loadTracksAction: self.loadTracksAction.setEnabled(is_video_loaded)
        can_save: bool = is_video_loaded and hasattr(self, 'track_manager') and len(self.track_manager.tracks) > 0
        if self.saveTracksAction: self.saveTracksAction.setEnabled(can_save)
        if self.videoInfoAction: self.videoInfoAction.setEnabled(is_video_loaded)

        if hasattr(self, 'exportViewAction') and self.exportViewAction:
            self.exportViewAction.setEnabled(is_video_loaded)
        if hasattr(self, 'exportFrameAction') and self.exportFrameAction:
            self.exportFrameAction.setEnabled(is_video_loaded)
        
        if hasattr(self, 'undoAction') and self.undoAction: # Enable/disable undo action
            self.undoAction.setEnabled(self.track_manager.can_undo_last_point_action() and is_video_loaded)


        if self.scale_panel_controller: self.scale_panel_controller.set_video_loaded_status(is_video_loaded)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_loaded_status(is_video_loaded)
        if self.table_data_controller: self.table_data_controller.set_video_loaded_status(is_video_loaded, self.total_frames if is_video_loaded else 0)


    def _update_ui_for_frame(self, frame_index: int) -> None:
        """Updates UI elements that display current frame and time information."""
        if not self.video_loaded:
            # Reset frame display
            if hasattr(self, 'currentFrameLineEdit'):
                self.currentFrameLineEdit.blockSignals(True)
                self.currentFrameLineEdit.setReadOnly(True)
                self.currentFrameLineEdit.setText("-")
                self.currentFrameLineEdit.deselect()
                self.currentFrameLineEdit.blockSignals(False)
            if hasattr(self, 'totalFramesLabel'):
                self.totalFramesLabel.setText("/ -")
            # Reset time display
            if hasattr(self, 'currentTimeLineEdit'):
                self.currentTimeLineEdit.blockSignals(True)
                self.currentTimeLineEdit.setReadOnly(True)
                self.currentTimeLineEdit.setText("--:--.---")
                self.currentTimeLineEdit.deselect()
                self.currentTimeLineEdit.blockSignals(False)
            if hasattr(self, 'totalTimeLabel'):
                self.totalTimeLabel.setText("/ --:--.---")
            return

        if self.frameSlider:
            self.frameSlider.blockSignals(True)
            self.frameSlider.setValue(frame_index)
            self.frameSlider.blockSignals(False)

        # Update Frame Display
        if hasattr(self, 'currentFrameLineEdit') and isinstance(self.currentFrameLineEdit, QtWidgets.QLineEdit):
            self.currentFrameLineEdit.blockSignals(True)
            self.currentFrameLineEdit.setReadOnly(True) 
            self.currentFrameLineEdit.setText(str(frame_index + 1))
            self.currentFrameLineEdit.deselect()
            self.currentFrameLineEdit.blockSignals(False)
        if hasattr(self, 'totalFramesLabel') and isinstance(self.totalFramesLabel, QtWidgets.QLabel):
            self.totalFramesLabel.setText(f"/ {self.total_frames}")

        # Update Time Display
        if hasattr(self, 'currentTimeLineEdit') and isinstance(self.currentTimeLineEdit, QtWidgets.QLineEdit):
            current_ms = (frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
            self.currentTimeLineEdit.blockSignals(True)
            self.currentTimeLineEdit.setReadOnly(True)
            self.currentTimeLineEdit.setText(self._format_time(current_ms))
            self.currentTimeLineEdit.deselect()
            self.currentTimeLineEdit.blockSignals(False)
        if hasattr(self, 'totalTimeLabel') and isinstance(self.totalTimeLabel, QtWidgets.QLabel):
            self.totalTimeLabel.setText(f"/ {self._format_time(self.total_duration_ms)}")

    @QtCore.Slot()
    def _handle_frame_input_finished(self) -> None:
        if not self.video_loaded or not hasattr(self, 'currentFrameLineEdit') or not isinstance(self.currentFrameLineEdit, QtWidgets.QLineEdit):
            return

        line_edit = self.currentFrameLineEdit
        # Check if processing is already done (e.g., by FocusOut then Enter)
        if line_edit.isReadOnly(): 
            return

        status_bar = self.statusBar()
        input_text = line_edit.text().strip()
        
        try:
            target_frame_1_based = int(input_text)
            target_frame_0_based = target_frame_1_based - 1

            if 0 <= target_frame_0_based < self.total_frames:
                logger.info(f"User entered frame: {target_frame_1_based}. Seeking to {target_frame_0_based}.")
                if self.current_frame_index != target_frame_0_based:
                    self.video_handler.seek_frame(target_frame_0_based)
                # If same frame, _update_ui_for_frame will be called by _handle_frame_changed or directly below
            else:
                logger.warning(f"Invalid frame number entered: {target_frame_1_based}. Range is 1-{self.total_frames}.")
                if status_bar: status_bar.showMessage(f"Invalid frame. Must be 1-{self.total_frames}.", 3000)
        except ValueError:
            logger.warning(f"Non-numeric frame input: '{input_text}'.")
            if status_bar: status_bar.showMessage("Invalid frame input: Not a number.", 3000)
        finally:
            # Always update UI to reflect current state (either new or reverted)
            # and set QLineEdit back to read-only, then clear focus.
            self._update_ui_for_frame(self.current_frame_index) # Ensures correct format and read-only
            line_edit.clearFocus()


    @QtCore.Slot()
    def _handle_time_input_finished(self) -> None:
        if not self.video_loaded or not hasattr(self, 'currentTimeLineEdit') or not isinstance(self.currentTimeLineEdit, QtWidgets.QLineEdit):
            return

        line_edit = self.currentTimeLineEdit
        if line_edit.isReadOnly():
            return

        status_bar = self.statusBar()
        input_text = line_edit.text().strip()
        
        try:
            target_ms = self.video_handler.parse_time_to_ms(input_text)
            if target_ms is not None:
                target_frame_0_based = self.video_handler.time_ms_to_frame_index(target_ms)
                if target_frame_0_based is not None:
                    logger.info(f"User entered time '{input_text}' ({target_ms:.0f}ms). Seeking to frame {target_frame_0_based}.")
                    if self.current_frame_index != target_frame_0_based:
                        self.video_handler.seek_frame(target_frame_0_based)
                else: # Should be caught by parse_time_to_ms for duration
                    logger.warning(f"Could not convert parsed time {target_ms:.0f}ms to a valid frame index.")
                    if status_bar: status_bar.showMessage("Time is out of video duration.", 3000)
            else:
                logger.warning(f"Invalid time input: '{input_text}'.")
                if status_bar: status_bar.showMessage(f"Invalid time format or out of range [0 - {self._format_time(self.total_duration_ms)}].", 4000)
        except Exception as e: # Catch any unexpected errors during parsing/conversion
            logger.error(f"Error processing time input '{input_text}': {e}")
            if status_bar: status_bar.showMessage("Error processing time input.", 3000)
        finally:
            # Always update UI and clear focus
            self._update_ui_for_frame(self.current_frame_index)
            line_edit.clearFocus()


    @QtCore.Slot()
    def open_video(self) -> None:
        logger.info("Open Video action triggered.")
        if self.video_loaded: self._release_video()
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)")
        if not file_path:
            status_bar = self.statusBar()
            if status_bar: status_bar.showMessage("Video loading cancelled.", 3000)
            return
        status_bar = self.statusBar()
        if status_bar: status_bar.showMessage(f"Opening video: {os.path.basename(file_path)}...", 0)
        QtWidgets.QApplication.processEvents()
        self.video_handler.open_video(file_path)

    def _release_video(self) -> None:
        logger.info("Releasing video resources and resetting state...")
        self.video_handler.release_video()
        self.video_loaded = False; self.total_frames = 0; self.current_frame_index = -1; self.fps = 0.0
        self.total_duration_ms = 0.0; self.video_filepath = ""; self.frame_width = 0; self.frame_height = 0
        self.is_playing = False
        self.track_manager.reset() # This will also clear undo state
        self.scale_manager.reset()
        self._reset_ui_after_video_close()
        logger.info("Video release and associated reset complete.")

    @QtCore.Slot()
    def _trigger_save_tracks(self) -> None:
        if self.video_loaded and self.track_manager and self.coord_transformer and self.scale_manager:
            file_io.save_tracks_dialog(self, self.track_manager, self.coord_transformer, self.scale_manager)
        else:
            status_bar = self.statusBar()
            if status_bar: status_bar.showMessage("Save Error: Components missing or video not loaded.", 3000)

    @QtCore.Slot()
    def _trigger_load_tracks(self) -> None:
        if self.video_loaded and self.track_manager and self.coord_transformer and self.scale_manager:
            file_io.load_tracks_dialog(self, self.track_manager, self.coord_transformer, self.scale_manager)
            if hasattr(self, 'undoAction') and self.undoAction: # After loading tracks, undo should be disabled
                 self.undoAction.setEnabled(False)
        else:
            status_bar = self.statusBar()
            if status_bar: status_bar.showMessage("Load Error: Components missing or video not loaded.", 3000)

    @QtCore.Slot()
    def _show_preferences_dialog(self) -> None:
        dialog = PreferencesDialog(self)
        dialog.settingsApplied.connect(self._handle_settings_applied)
        dialog.exec()

    @QtCore.Slot()
    def _handle_settings_applied(self) -> None:
        logger.info("MainWindow: Settings applied, refreshing visuals.")
        self._setup_pens()
        if self.imageView and hasattr(self.imageView, '_scale_bar_widget') and self.imageView._scale_bar_widget: # type: ignore
            logger.debug("MainWindow: Calling update_appearance_from_settings on ScaleBarWidget.")
            self.imageView._scale_bar_widget.update_appearance_from_settings() # type: ignore
            if self.imageView._scale_bar_widget.isVisible(): # type: ignore
                 self.imageView._update_overlay_widget_positions() # type: ignore
        else:
            logger.warning("ScaleBarWidget not available or not setup on imageView for settings update.")
        self._redraw_scene_overlay()
        if self.imageView and self.scale_manager and self.showScaleBarCheckBox and self.showScaleBarCheckBox.isChecked():
            current_m_per_px = self.scale_manager.get_scale_m_per_px()
            if current_m_per_px is not None:
                self.imageView.update_scale_bar_dimensions(current_m_per_px)

    @QtCore.Slot(int)
    def _slider_value_changed(self, value: int) -> None:
        if self.video_loaded and self.current_frame_index != value:
            self.video_handler.seek_frame(value)

    @QtCore.Slot(int)
    def _handle_frame_step(self, step: int) -> None:
        if self.video_loaded: self.video_handler.next_frame() if step > 0 else self.video_handler.previous_frame()

    @QtCore.Slot()
    def _show_previous_frame(self) -> None:
        if self.video_loaded: self.video_handler.previous_frame()

    @QtCore.Slot()
    def _show_next_frame(self) -> None:
        if self.video_loaded: self.video_handler.next_frame()

    @QtCore.Slot()
    def _toggle_playback(self) -> None:
        if self.video_loaded and self.fps > 0: self.video_handler.toggle_playback()

    @QtCore.Slot()
    def _update_zoom_display(self) -> None:
        """Updates the zoomLevelLineEdit with the current zoom percentage."""
        if not self.video_loaded or not hasattr(self, 'imageView') or \
           not hasattr(self, 'zoomLevelLineEdit') or self.zoomLevelLineEdit is None:
            if hasattr(self, 'zoomLevelLineEdit') and self.zoomLevelLineEdit is not None:
                 self.zoomLevelLineEdit.setText("---.-")
            return

        # Only update if the line edit does not have focus, to avoid disrupting user input
        if self.zoomLevelLineEdit.hasFocus():
            return

        try:
            min_scale = self.imageView.get_min_view_scale()
            if min_scale <= 0: # Avoid division by zero or negative scales
                logger.warning("Cannot update zoom display: ImageView min_scale is invalid.")
                self.zoomLevelLineEdit.setText("---.-")
                return

            current_view_scale = self.imageView.transform().m11()
            zoom_percentage = (current_view_scale / min_scale) * 100.0
            
            self.zoomLevelLineEdit.blockSignals(True)
            self.zoomLevelLineEdit.setText(f"{zoom_percentage:.1f}")
            self.zoomLevelLineEdit.blockSignals(False)
            # logger.debug(f"Zoom display updated to: {zoom_percentage:.1f}%")
        except Exception as e:
            logger.error(f"Error updating zoom display: {e}")
            self.zoomLevelLineEdit.setText("ERR")


    @QtCore.Slot()
    def _handle_zoom_input_finished(self) -> None:
        """Handles the editingFinished signal from zoomLevelLineEdit."""
        if not self.video_loaded or \
           not hasattr(self, 'imageView') or \
           not hasattr(self, 'zoomLevelLineEdit') or self.zoomLevelLineEdit is None:
            return

        line_edit = self.zoomLevelLineEdit
        if line_edit.isReadOnly(): # Should have been made writable on focus
            return

        status_bar = self.statusBar()
        input_text = line_edit.text().strip()

        try:
            entered_percentage = float(input_text)
            
            min_view_scale = self.imageView.get_min_view_scale()
            max_view_scale = self.imageView.get_max_view_scale()

            if min_view_scale <= 0:
                logger.error("Cannot process zoom input: ImageView min_scale is invalid.")
                if status_bar: status_bar.showMessage("Error: Cannot determine zoom limits.", 3000)
                self._update_zoom_display() # Revert to current actual zoom
                line_edit.clearFocus()
                return

            min_percentage = 100.0 
            # Allow a tiny bit of flexibility for max due to float precision
            max_percentage = (max_view_scale / min_view_scale) * 100.0 + 0.01 

            if not (min_percentage <= entered_percentage <= max_percentage):
                logger.warning(f"Invalid zoom percentage: {entered_percentage}%. Must be between {min_percentage:.1f}% and {max_percentage:.1f}%.")
                if status_bar: status_bar.showMessage(f"Zoom must be {min_percentage:.0f}% - {max_percentage:.0f}%.", 3000)
                # Revert to current actual zoom
                self._update_zoom_display()
            else:
                current_view_scale = self.imageView.transform().m11()
                target_view_scale = (entered_percentage / 100.0) * min_view_scale
                
                if not math.isclose(current_view_scale, target_view_scale, rel_tol=1e-3): # Only zoom if significantly different
                    zoom_factor_to_apply = target_view_scale / current_view_scale
                    viewport_center = self.imageView.viewport().rect().center()
                    
                    logger.info(f"User entered zoom: {entered_percentage:.1f}%. Target scale: {target_view_scale:.4f}. Applying factor: {zoom_factor_to_apply:.4f}")
                    self.imageView._zoom(zoom_factor_to_apply, viewport_center) # _zoom emits viewTransformChanged
                else:
                    logger.debug(f"Entered zoom {entered_percentage:.1f}% results in current scale. No change applied.")
                    # Ensure display is updated even if no zoom, to format correctly
                    self._update_zoom_display()


        except ValueError:
            logger.warning(f"Non-numeric zoom input: '{input_text}'.")
            if status_bar: status_bar.showMessage("Invalid zoom input: Not a number.", 3000)
            self._update_zoom_display() # Revert
        finally:
            # The _update_zoom_display will be called by viewTransformChanged if zoom occurs.
            # If no zoom or error, it's called above.
            line_edit.setReadOnly(True) # Set back to read-only after processing
            line_edit.clearFocus() # Remove focus

    @QtCore.Slot(dict)
    def _handle_video_loaded(self, video_info: Dict[str, Any]) -> None:
        logger.info(f"Received videoLoaded signal: {video_info.get('filename', 'N/A')}")
        self.total_frames = video_info.get('total_frames', 0); self.video_loaded = True; self.fps = video_info.get('fps', 0.0)
        self.total_duration_ms = video_info.get('duration_ms', 0.0); self.video_filepath = video_info.get('filepath', '')
        self.frame_width = video_info.get('width', 0); self.frame_height = video_info.get('height', 0); self.is_playing = False
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION} - {video_info.get('filename', 'N/A')}")
        self.coord_transformer.set_video_height(self.frame_height)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_height(self.frame_height)
        self.track_manager.reset() # Resets tracks and undo state
        if self.frameSlider: self.frameSlider.setMaximum(self.total_frames - 1 if self.total_frames > 0 else 0); self.frameSlider.setValue(0)
        if self.imageView: self.imageView.resetInitialLoadFlag()
        self.scale_manager.reset()
        if self.scale_panel_controller: self.scale_panel_controller.set_video_loaded_status(True)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_loaded_status(True); self.coord_panel_controller.update_ui_display()
        if self.table_data_controller: self.table_data_controller.set_video_loaded_status(True, self.total_frames)
        self._update_zoom_display() # This will calculate and set the initial 100%
        self._update_ui_state() # Will also update undoAction enabled state
        status_msg = (f"Loaded '{video_info.get('filename', 'N/A')}' ({self.total_frames} frames, {self.frame_width}x{self.frame_height}, {self.fps:.2f} FPS)")
        status_bar = self.statusBar()
        if status_bar: status_bar.showMessage(status_msg, 5000)

    @QtCore.Slot(str)
    def _handle_video_load_failed(self, error_msg: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Video Load Error", error_msg)
        status_bar = self.statusBar()
        if status_bar: status_bar.showMessage("Error loading video", 5000)
        self._release_video() # This will also update UI state including undoAction

    @QtCore.Slot(QtGui.QPixmap, int)
    def _handle_frame_changed(self, pixmap: QtGui.QPixmap, frame_index: int) -> None:
        if not self.video_loaded: return
        self.current_frame_index = frame_index
        if self.imageView: self.imageView.setPixmap(pixmap)
        self._update_ui_for_frame(frame_index)
        self._redraw_scene_overlay()
        if self.imageView and self.scale_manager and self.showScaleBarCheckBox and self.showScaleBarCheckBox.isChecked():
            current_m_per_px = self.scale_manager.get_scale_m_per_px()
            if current_m_per_px is not None: self.imageView.update_scale_bar_dimensions(current_m_per_px)

    @QtCore.Slot(bool)
    def _handle_playback_state_changed(self, is_playing: bool) -> None:
        self.is_playing = is_playing
        status_bar = self.statusBar()
        if self.playPauseButton and self.stop_icon and self.play_icon:
            self.playPauseButton.setIcon(self.stop_icon if self.is_playing else self.play_icon)
            self.playPauseButton.setToolTip("Stop Video (Space)" if self.is_playing else "Play Video (Space)")
            if self.is_playing and status_bar: status_bar.showMessage("Playing...", 0)
            elif status_bar: status_bar.showMessage("Stopped." if self.video_loaded else "Ready.", 3000)
        self._update_ui_state()

    @QtCore.Slot(float, float)
    def _handle_add_point_click(self, x: float, y: float) -> None:
        status_bar = self.statusBar()
        if self.coord_panel_controller and self.coord_panel_controller.is_setting_origin_mode(): return
        if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and \
           self.scale_panel_controller._is_setting_scale_by_line: return # type: ignore

        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Cannot add point: No video loaded.", 3000)
            return
        
        if self.track_manager.active_track_index == -1:
            if status_bar: status_bar.showMessage("Select a track to add points.", 3000)
            logger.info("Attempted to add point, but no track is active.")
            return

        time_ms = (self.current_frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
        
        # The TrackManager's add_point method now handles storing undo information.
        if self.track_manager.add_point(self.current_frame_index, time_ms, x, y):
            x_d, y_d = self.coord_transformer.transform_point_for_display(x,y)
            msg = f"Point for Track {self.track_manager.get_active_track_id()} on Frame {self.current_frame_index+1}: ({x_d:.1f}, {y_d:.1f})"
            if status_bar: status_bar.showMessage(msg, 3000)
            if self._auto_advance_enabled and self._auto_advance_frames > 0:
                target = min(self.current_frame_index + self._auto_advance_frames, self.total_frames - 1)
                if target > self.current_frame_index: self.video_handler.seek_frame(target)
        elif status_bar: status_bar.showMessage("Failed to add point (see log).", 3000)
        # Update undo action enabled state
        if hasattr(self, 'undoAction') and self.undoAction:
            self.undoAction.setEnabled(self.track_manager.can_undo_last_point_action())


    @QtCore.Slot(float, float, QtCore.Qt.KeyboardModifiers)
    def _handle_modified_click(self, x: float, y: float, modifiers: QtCore.Qt.KeyboardModifiers) -> None:
        status_bar = self.statusBar()
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Cannot interact: Video/components not ready.", 3000)
            return

        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            result = self.track_manager.find_closest_visible_point(x, y, self.current_frame_index)
            if result is None: 
                if self.track_manager.active_track_index != -1:
                    self.track_manager.set_active_track(-1) 
                    if status_bar: status_bar.showMessage("Track deselected.", 3000)
                else:
                    if status_bar: status_bar.showMessage("No track to deselect.", 3000)
                return 

        result = self.track_manager.find_closest_visible_point(x, y, self.current_frame_index)
        if result is None:
            if modifiers != QtCore.Qt.KeyboardModifier.ControlModifier and status_bar:
                status_bar.showMessage("No track marker found near click.", 3000)
            return

        track_idx, point_data = result
        track_id = track_idx + 1
        frame_idx = point_data[0]

        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            if self.track_manager.active_track_index != track_idx:
                self.track_manager.set_active_track(track_idx)
                if self.table_data_controller:
                    QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_track_row_by_id_in_ui(track_id)) # type: ignore
                if status_bar: status_bar.showMessage(f"Selected Track {track_id}.", 3000)

        elif modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:
            if self.track_manager.active_track_index != track_idx:
                self.track_manager.set_active_track(track_idx)
            if self.table_data_controller:
                QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_track_row_by_id_in_ui(track_id)) # type: ignore
            if self.current_frame_index != frame_idx:
                self.video_handler.seek_frame(frame_idx)
            if status_bar: status_bar.showMessage(f"Selected Track {track_id}, jumped to Frame {frame_idx + 1}.", 3000)

    @QtCore.Slot(int)
    def _handle_auto_advance_toggled(self, state: int) -> None:
        self._auto_advance_enabled = (state == QtCore.Qt.CheckState.Checked.value)

    @QtCore.Slot(int)
    def _handle_auto_advance_frames_changed(self, value: int) -> None:
        self._auto_advance_frames = value

    @QtCore.Slot()
    def _create_new_track(self) -> None:
        status_bar = self.statusBar()
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Load a video first to create tracks.", 3000)
            return
        new_id = self.track_manager.create_new_track()
        if status_bar: status_bar.showMessage(f"Created Track {new_id}. It is now active.", 3000)
        if self.table_data_controller: QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_track_row_by_id_in_ui(new_id)) # type: ignore
        if self.dataTabsWidget: self.dataTabsWidget.setCurrentIndex(0)
        self._update_ui_state() # Will update undoAction enabled state

    @QtCore.Slot(bool)
    def _handle_disable_frame_navigation(self, disable: bool) -> None:
        logger.debug(f"Setting frame navigation controls disabled: {disable}")
        enabled = not disable and self.video_loaded
        if self.frameSlider: self.frameSlider.setEnabled(enabled)
        if self.playPauseButton: self.playPauseButton.setEnabled(enabled and self.fps > 0)
        if self.prevFrameButton: self.prevFrameButton.setEnabled(enabled)
        if self.nextFrameButton: self.nextFrameButton.setEnabled(enabled)
        status_bar = self.statusBar()
        if disable and status_bar:
            status_bar.showMessage("Frame navigation disabled while defining scale line.", 0)


    @QtCore.Slot()
    def _redraw_scene_overlay(self) -> None:
        if not (self.imageView and self.imageView._scene and self.video_loaded and self.current_frame_index >= 0):
            if self.imageView: self.imageView.clearOverlay()
            return

        scene = self.imageView._scene # type: ignore
        self.imageView.clearOverlay() 

        try:
            marker_sz = float(settings_manager.get_setting(settings_manager.KEY_MARKER_SIZE))
            elements = self.track_manager.get_visual_elements(self.current_frame_index)
            pens = {
                config.STYLE_MARKER_ACTIVE_CURRENT: self.pen_marker_active_current,
                config.STYLE_MARKER_ACTIVE_OTHER: self.pen_marker_active_other,
                config.STYLE_MARKER_INACTIVE_CURRENT: self.pen_marker_inactive_current,
                config.STYLE_MARKER_INACTIVE_OTHER: self.pen_marker_inactive_other,
                config.STYLE_LINE_ACTIVE: self.pen_line_active,
                config.STYLE_LINE_INACTIVE: self.pen_line_inactive,
            }
            for el in elements:
                pen = pens.get(el.get('style'))
                if not pen: continue
                current_pen = QtGui.QPen(pen) 
                current_pen.setCosmetic(True) 
                if el.get('type') == 'marker' and el.get('pos'):
                    x, y = el['pos']; r = marker_sz / 2.0
                    path = QtGui.QPainterPath(); path.moveTo(x - r, y); path.lineTo(x + r, y); path.moveTo(x, y - r); path.lineTo(x, y + r)
                    item = QtWidgets.QGraphicsPathItem(path); item.setPen(current_pen); item.setZValue(10); scene.addItem(item)
                elif el.get('type') == 'line' and el.get('p1') and el.get('p2'):
                    p1, p2 = el['p1'], el['p2']
                    item = QtWidgets.QGraphicsLineItem(p1[0], p1[1], p2[0], p2[1]); item.setPen(current_pen); item.setZValue(9); scene.addItem(item)

            if self.coord_panel_controller and self.coord_panel_controller.get_show_origin_marker_status():
                origin_sz = float(settings_manager.get_setting(settings_manager.KEY_ORIGIN_MARKER_SIZE))
                ox, oy = self.coord_transformer.get_current_origin_tl()
                r_orig = origin_sz / 2.0
                origin_pen_cosmetic = QtGui.QPen(self.pen_origin_marker) 
                origin_pen_cosmetic.setCosmetic(True)
                origin_item = QtWidgets.QGraphicsEllipseItem(ox - r_orig, oy - r_orig, origin_sz, origin_sz)
                origin_item.setPen(origin_pen_cosmetic); origin_item.setBrush(self.pen_origin_marker.color()); origin_item.setZValue(11)
                scene.addItem(origin_item)

            if self.showScaleLineCheckBox and self.showScaleLineCheckBox.isChecked() and \
               self.scale_manager and self.scale_manager.has_defined_scale_line():
                line_data = self.scale_manager.get_defined_scale_line_data()
                scale_m_per_px = self.scale_manager.get_scale_m_per_px()
                if line_data and scale_m_per_px is not None and scale_m_per_px > 0:
                    p1x, p1y, p2x, p2y = line_data
                    dx = p2x - p1x; dy = p2y - p1y
                    pixel_length = math.sqrt(dx*dx + dy*dy)
                    meter_length = pixel_length * scale_m_per_px
                    length_text = "Err"
                    if self._export_handler: 
                        length_text = self._export_handler.format_length_value_for_line(meter_length)
                    else: 
                        logger.warning("Export handler not available for formatting scale line text in redraw.")
                        length_text = f"{meter_length:.2f} m"
                    line_clr = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_COLOR)
                    text_clr = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_COLOR)
                    font_sz = int(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_SIZE))
                    pen_w = float(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_WIDTH))
                    self.imageView.draw_persistent_scale_line( # type: ignore
                        line_data=line_data, length_text=length_text, line_color=line_clr,
                        text_color=text_clr, font_size=font_sz, pen_width=pen_w
                    )
                    logger.debug("MainWindow requested ImageView to draw persistent scale line with updated settings.")
        except Exception as e:
            logger.exception(f"Error during overlay drawing in _redraw_scene_overlay: {e}")
        finally:
            if self.imageView and self.imageView.viewport():
                self.imageView.viewport().update()


    def _get_export_resolution_choice(self) -> Optional[ExportResolutionMode]: # From previous step
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Choose Export Resolution")
        dialog.setModal(True)
        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel("Select the resolution for the export:")
        layout.addWidget(label)
        radio_group = QtWidgets.QButtonGroup(dialog)
        viewport_res_radio = QtWidgets.QRadioButton("Current Viewport Resolution")
        viewport_res_radio.setChecked(True)
        radio_group.addButton(viewport_res_radio)
        layout.addWidget(viewport_res_radio)
        original_res_radio = QtWidgets.QRadioButton("Original Video Resolution")
        if not (self.video_loaded and self.frame_width > 0 and self.frame_height > 0):
            original_res_radio.setEnabled(False)
            original_res_radio.setToolTip("Original video resolution is not available (no video loaded or invalid dimensions).")
        else:
            original_res_radio.setToolTip(f"Exports at {self.frame_width}x{self.frame_height} pixels.")
        radio_group.addButton(original_res_radio)
        layout.addWidget(original_res_radio)
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            if original_res_radio.isChecked():
                return ExportResolutionMode.ORIGINAL_VIDEO
            return ExportResolutionMode.VIEWPORT
        return None

    @QtCore.Slot()
    def _trigger_export_video(self) -> None: # From previous step, ensure it's using ExportResolutionMode
        if not self.video_loaded or not self._export_handler:
            QtWidgets.QMessageBox.warning(self, "Export Error", "No video loaded or export handler not ready.")
            return
        export_mode = self._get_export_resolution_choice()
        if export_mode is None:
            if self.statusBar(): self.statusBar().showMessage("Video export cancelled by user.", 3000)
            return
        # ... (rest of the _trigger_export_video from previous step, ensuring export_mode is passed)
        base_video_name = "video_with_overlays"
        if self.video_filepath:
            base_video_name = os.path.splitext(os.path.basename(self.video_filepath))[0] + "_tracked"
        export_options = [("mp4", "mp4v", "MP4 Video Files (*.mp4)"), ("avi", "MJPG", "AVI Video Files (Motion JPEG) (*.avi)")]
        file_filters = ";;".join([opt[2] for opt in export_options])
        default_filename_suffix = "_orig_res" if export_mode == ExportResolutionMode.ORIGINAL_VIDEO else "_viewport_res"
        default_filename = f"{base_video_name}{default_filename_suffix}.{export_options[0][0]}"
        start_dir = os.path.dirname(self.video_filepath) if self.video_filepath and os.path.isdir(os.path.dirname(self.video_filepath)) else os.getcwd()
        save_path, selected_filter_desc = QtWidgets.QFileDialog.getSaveFileName(self, "Export Video with Overlays", os.path.join(start_dir, default_filename), file_filters)
        if not save_path:
            if self.statusBar(): self.statusBar().showMessage("Video export cancelled.", 3000)
            return
        chosen_fourcc_str = ""; chosen_extension_dot = ""
        for ext, fcc, desc in export_options:
            if desc == selected_filter_desc: chosen_fourcc_str = fcc; chosen_extension_dot = f".{ext}"; break
        if not chosen_fourcc_str:
            _name_part, ext_part_from_path = os.path.splitext(save_path)
            if ext_part_from_path:
                ext_part_from_path_lower = ext_part_from_path.lower()
                for ext, fcc, desc in export_options:
                    if f".{ext}" == ext_part_from_path_lower: chosen_fourcc_str = fcc; chosen_extension_dot = ext_part_from_path_lower; break
            if not chosen_fourcc_str: chosen_fourcc_str = export_options[0][1]; chosen_extension_dot = f".{export_options[0][0]}"
        current_name_part, current_ext_part = os.path.splitext(save_path)
        if current_ext_part.lower() != chosen_extension_dot.lower(): save_path = current_name_part + chosen_extension_dot
        if self._export_handler: self._export_handler.export_video_with_overlays(save_path, chosen_fourcc_str, chosen_extension_dot, export_mode)


    @QtCore.Slot()
    def _trigger_export_frame(self) -> None: # From previous step, ensure it's using ExportResolutionMode
        if not self.video_loaded or self.current_frame_index < 0 or not self._export_handler:
            QtWidgets.QMessageBox.warning(self, "Export Frame Error", "No video loaded, no current frame, or export handler not ready.")
            return
        export_mode = self._get_export_resolution_choice()
        if export_mode is None:
            if self.statusBar(): self.statusBar().showMessage("Frame export cancelled by user.", 3000)
            return
        # ... (rest of the _trigger_export_frame from previous step, ensuring export_mode is passed)
        base_video_name = "frame"
        if self.video_filepath: base_video_name = os.path.splitext(os.path.basename(self.video_filepath))[0]
        filename_suffix = "_orig_res" if export_mode == ExportResolutionMode.ORIGINAL_VIDEO else "_viewport_res"
        default_filename = f"{base_video_name}_frame_{self.current_frame_index + 1}{filename_suffix}.png"
        start_dir = os.path.dirname(self.video_filepath) if self.video_filepath and os.path.isdir(os.path.dirname(self.video_filepath)) else os.getcwd()
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Current Frame to PNG", os.path.join(start_dir, default_filename), "PNG Image Files (*.png);;All Files (*)")
        if not save_path:
            if self.statusBar(): self.statusBar().showMessage("Frame export cancelled.", 3000)
            return
        if not save_path.lower().endswith(".png"): save_path += ".png"
        if self._export_handler: self._export_handler.export_current_frame_to_png(save_path, export_mode)

    # Ensure _on_export_started, _on_export_progress, _on_export_finished are present
    @QtCore.Slot()
    def _on_export_started(self) -> None: # From previous step
        logger.info("MainWindow: Export process started.")
        if self.exportViewAction: self.exportViewAction.setEnabled(False)
        if self.exportFrameAction: self.exportFrameAction.setEnabled(False)
        self._export_progress_dialog = QtWidgets.QProgressDialog("Exporting...", "Cancel", 0, 100, self)
        self._export_progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self._export_progress_dialog.setWindowTitle("Export Progress")
        self._export_progress_dialog.setValue(0)
        self._export_progress_dialog.show()
        if self.statusBar(): self.statusBar().showMessage("Exporting...", 0)

    @QtCore.Slot(str, int, int)
    def _on_export_progress(self, message: str, current_value: int, max_value: int) -> None: # From previous step
        if self._export_progress_dialog:
            if self._export_progress_dialog.maximum() != max_value: self._export_progress_dialog.setMaximum(max_value)
            self._export_progress_dialog.setValue(current_value)
            self._export_progress_dialog.setLabelText(message)
            if self._export_progress_dialog.wasCanceled(): logger.info("MainWindow: Export cancel detected by progress dialog.")
        QtWidgets.QApplication.processEvents()

    @QtCore.Slot(bool, str)
    def _on_export_finished(self, success: bool, message: str) -> None: # From previous step
        logger.info(f"MainWindow: Export process finished. Success: {success}, Message: {message}")
        if self._export_progress_dialog: self._export_progress_dialog.close(); self._export_progress_dialog = None
        if self.statusBar(): self.statusBar().showMessage(message, 5000 if success else 8000)
        if not success: QtWidgets.QMessageBox.warning(self, "Export Problem", message)
        self._update_ui_state()
        

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()
        accepted = False
        status_bar = self.statusBar()

        if key == QtCore.Qt.Key.Key_Escape:
            # ... (existing escape logic) ...
            if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and \
               self.scale_panel_controller._is_setting_scale_by_line: # type: ignore
                self.scale_panel_controller.cancel_set_scale_by_line() # type: ignore
                if status_bar: status_bar.showMessage("Set scale by line cancelled.", 3000)
                accepted = True
            elif self.coord_panel_controller and self.coord_panel_controller.is_setting_origin_mode():
                self.coord_panel_controller._is_setting_origin = False # type: ignore
                if self.imageView: self.imageView.set_interaction_mode(InteractionMode.NORMAL) # type: ignore
                if status_bar: status_bar.showMessage("Set origin cancelled.", 3000)
                accepted = True
        elif key == QtCore.Qt.Key.Key_Space:
            # ... (existing spacebar logic) ...
            if self.video_loaded and self.playPauseButton and self.playPauseButton.isEnabled():
                nav_disabled = False
                if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line'):
                    nav_disabled = self.scale_panel_controller._is_setting_scale_by_line # type: ignore
                if not nav_disabled: self._toggle_playback(); accepted = True
        elif key == QtCore.Qt.Key.Key_Delete or key == QtCore.Qt.Key.Key_Backspace:
            if self.video_loaded and self.track_manager.active_track_index != -1 and self.current_frame_index != -1:
                # --- MODIFICATION: Call TrackManager's delete_point ---
                # TrackManager.delete_point now sets up its own undo state.
                deleted = self.track_manager.delete_point(self.track_manager.active_track_index, self.current_frame_index)
                if status_bar: status_bar.showMessage(f"Deleted point..." if deleted else "No point to delete on this frame.", 3000)
                
                # Update undo action availability (TrackManager.delete_point emits undoStateChanged)
                # So this direct call might be redundant if undoAction.setEnabled is connected to that signal,
                # but it ensures immediate consistency.
                if hasattr(self, 'undoAction') and self.undoAction:
                    self.undoAction.setEnabled(self.track_manager.can_undo_last_point_action())
                accepted = True
            elif self.video_loaded and self.track_manager.active_track_index == -1:
                if status_bar: status_bar.showMessage("No track selected to delete points from.", 3000)
                accepted = True # Accept to prevent further processing if no track is active
            elif status_bar: status_bar.showMessage("Cannot delete point.", 3000) # Fallback
        elif modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and key == QtCore.Qt.Key.Key_Z:
            if hasattr(self, 'undoAction') and self.undoAction and self.undoAction.isEnabled():
                self._trigger_undo_point_action()
                accepted = True
            elif status_bar:
                 status_bar.showMessage("Nothing to undo.", 3000)
                 accepted = True # Still accept to prevent other actions

        if accepted:
            event.accept()
        else:
            super().keyPressEvent(event)


    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if self.video_loaded and isinstance(watched, QtWidgets.QLineEdit):
            line_edit_to_process: Optional[QtWidgets.QLineEdit] = None
            is_frame_edit = False
            is_time_edit = False
            is_zoom_edit = False # New flag

            if hasattr(self, 'currentFrameLineEdit') and watched is self.currentFrameLineEdit:
                line_edit_to_process = self.currentFrameLineEdit
                is_frame_edit = True
            elif hasattr(self, 'currentTimeLineEdit') and watched is self.currentTimeLineEdit:
                line_edit_to_process = self.currentTimeLineEdit
                is_time_edit = True
            # --- NEW: Check for zoomLevelLineEdit ---
            elif hasattr(self, 'zoomLevelLineEdit') and watched is self.zoomLevelLineEdit:
                line_edit_to_process = self.zoomLevelLineEdit
                is_zoom_edit = True
            # --- END NEW ---

            if line_edit_to_process:
                if event.type() == QtCore.QEvent.Type.FocusIn:
                    line_edit_to_process.setReadOnly(False)
                    # Populate with current value only, for editing
                    if is_frame_edit and self.current_frame_index >= 0:
                        line_edit_to_process.setText(str(self.current_frame_index + 1))
                    elif is_time_edit and self.current_frame_index >= 0:
                        current_ms = (self.current_frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
                        line_edit_to_process.setText(self._format_time(current_ms))
                    # --- NEW: Populate zoomLevelLineEdit on focus ---
                    elif is_zoom_edit:
                        if self.imageView and self.imageView.get_min_view_scale() > 0:
                            current_view_scale = self.imageView.transform().m11()
                            min_scale = self.imageView.get_min_view_scale()
                            zoom_percentage = (current_view_scale / min_scale) * 100.0
                            line_edit_to_process.setText(f"{zoom_percentage:.1f}")
                        else:
                            line_edit_to_process.setText("---.-")
                    # --- END NEW ---
                    else: # No video or invalid frame, make sure it's empty for editing
                        line_edit_to_process.setText("") 
                    
                    line_edit_to_process.selectAll()
                    logger.debug(f"FocusIn on {line_edit_to_process.objectName()}, set to writable, content selected.")
                    return False 

                elif event.type() == QtCore.QEvent.Type.FocusOut:
                    if not line_edit_to_process.isReadOnly():
                        logger.debug(f"FocusOut on {line_edit_to_process.objectName()} while writable. Processing content.")
                        if is_frame_edit:
                            self._handle_frame_input_finished() 
                        elif is_time_edit:
                            self._handle_time_input_finished()
                        # --- NEW: Handle zoomLevelLineEdit focus out ---
                        elif is_zoom_edit:
                            # Typically, editingFinished is preferred. 
                            # If content changed, could call _handle_zoom_input_finished.
                            # For now, just ensure it becomes read-only and updates to current view.
                            self._update_zoom_display() # Update to actual current zoom
                            line_edit_to_process.setReadOnly(True)
                        # --- END NEW ---
                    return False 
        return super().eventFilter(watched, event)

    # --- Method to Trigger Undo ---
    @QtCore.Slot()
    def _trigger_undo_point_action(self) -> None:
        """Triggers the undo action in the TrackManager."""
        if not self.video_loaded:
            if self.statusBar(): self.statusBar().showMessage("Cannot undo: No video loaded.", 3000)
            return

        if self.track_manager.undo_last_point_action():
            if self.statusBar(): self.statusBar().showMessage("Last point action undone.", 3000)
            # TrackManager signals will handle UI updates (tables, visuals)
        else:
            if self.statusBar(): self.statusBar().showMessage("Nothing to undo.", 3000)
        
        # Update the enabled state of the undo action itself
        if hasattr(self, 'undoAction') and self.undoAction:
            self.undoAction.setEnabled(self.track_manager.can_undo_last_point_action())


    @QtCore.Slot()
    def _show_video_info_dialog(self) -> None:
        status_bar = self.statusBar()
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("No video loaded.", 3000)
            return
        try:
            meta = self.video_handler.get_metadata_dictionary()
            if not meta: QtWidgets.QMessageBox.information(self, "Video Information", "Could not retrieve metadata."); return
            dialog = MetadataDialog(meta, self); dialog.exec()
        except Exception as e: QtWidgets.QMessageBox.critical(self, "Error", f"Could not display video info:\\n{e}")

    @QtCore.Slot()
    def _show_about_dialog(self) -> None:
        icon = self.windowIcon(); box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(f"About {config.APP_NAME}"); box.setTextFormat(QtCore.Qt.TextFormat.RichText)
        box.setText(f"<b>{config.APP_NAME}</b><br>Version {config.APP_VERSION}<br><br>Tool for tracking.<br><br>Python {sys.version.split()[0]}, PySide6 {QtCore.__version__}")
        if not icon.isNull():
            pix = icon.pixmap(QtCore.QSize(64,64))
            if not pix.isNull(): box.setIconPixmap(pix)
            else: box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        else: box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok); box.exec()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._release_video(); super().closeEvent(event)

    def _format_time(self, ms: float) -> str:
        if ms < 0: return "--:--.---"
        try: s,mils = divmod(ms,1000); m,s = divmod(int(s),60); return f"{m:02}:{s:02}.{int(mils):03}"
        except: return "--:--.---"