# main_window.py
import sys
import os
import math
import logging
from PySide6 import QtCore, QtGui, QtWidgets
# Import necessary types from typing module
from typing import Optional, List, Tuple, Dict, Any

# --- BEGIN ADDITION: Imports for video export ---
import cv2 # type: ignore
import numpy as np
# --- END ADDITION ---

from metadata_dialog import MetadataDialog

# Import constants and application components
import config
from interactive_image_view import InteractiveImageView, InteractionMode
from track_manager import TrackManager, TrackVisibilityMode, PointData, VisualElement
import file_io
from video_handler import VideoHandler
import ui_setup # Handles the creation of UI elements
from coordinates import CoordinateSystem, CoordinateTransformer
import settings_manager
from preferences_dialog import PreferencesDialog
from scale_manager import ScaleManager
# --- BEGIN MODIFICATION: Import ScaleBarWidget for type hinting if needed by export ---
from scale_bar_widget import ScaleBarWidget # For type hinting, or direct use if getters are sufficient
# --- END MODIFICATION ---
from panel_controllers import ScalePanelController, CoordinatePanelController
from table_controllers import TrackDataViewController


# Get a logger for this module
logger = logging.getLogger(__name__)

# Determine the base directory of the script reliably
basedir = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(basedir, "PyroTracker.ico")

class MainWindow(QtWidgets.QMainWindow):
    """
    Main application window for PyroTracker.

    Orchestrates interactions between UI elements, ImageView, TrackManager,
    VideoHandler, CoordinateTransformer, and SettingsManager. Handles UI updates,
    interaction modes, track management UI, drawing track visuals, and user actions.
    Delegates video loading/playback/navigation to VideoHandler.
    Delegates file I/O for tracks to file_io.
    Delegates UI layout setup to ui_setup.
    """
    # --- Instance Variable Type Hinting ---
    # Core Components
    track_manager: TrackManager
    imageView: InteractiveImageView # Assigned by ui_setup
    video_handler: VideoHandler
    coord_transformer: CoordinateTransformer
    scale_manager: ScaleManager
    scale_panel_controller: Optional[ScalePanelController]
    coord_panel_controller: Optional[CoordinatePanelController]
    table_data_controller: Optional[TrackDataViewController]


    # Video State (Mirrored from VideoHandler for easier UI updates)
    total_frames: int
    current_frame_index: int
    video_loaded: bool
    is_playing: bool
    fps: float
    total_duration_ms: float
    video_filepath: str
    frame_width: int
    frame_height: int

    # Auto-Advance State
    _auto_advance_enabled: bool
    _auto_advance_frames: int

    # UI Elements (These are assigned by ui_setup.setup_main_window_ui)
    mainSplitter: QtWidgets.QSplitter
    leftPanelWidget: QtWidgets.QWidget
    rightPanelWidget: QtWidgets.QWidget
    frameSlider: QtWidgets.QSlider
    playPauseButton: QtWidgets.QPushButton
    prevFrameButton: QtWidgets.QPushButton
    nextFrameButton: QtWidgets.QPushButton
    frameLabel: QtWidgets.QLabel
    timeLabel: QtWidgets.QLabel
    fpsLabel: QtWidgets.QLabel
    filenameLabel: QtWidgets.QLabel
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
    # --- BEGIN MODIFICATION: Add exportViewAction type hint ---
    exportViewAction: QtGui.QAction
    # --- END MODIFICATION ---
    newTrackAction: QtGui.QAction
    videoInfoAction: QtGui.QAction
    preferencesAction: QtGui.QAction
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


    # Drawing Pens (Configured based on settings)
    pen_origin_marker: QtGui.QPen
    pen_marker_active_current: QtGui.QPen
    pen_marker_active_other: QtGui.QPen
    pen_marker_inactive_current: QtGui.QPen
    pen_marker_inactive_other: QtGui.QPen
    pen_line_active: QtGui.QPen
    pen_line_inactive: QtGui.QPen

    def __init__(self) -> None:
        """Initializes the MainWindow, sets up components, pens, delegates UI setup, and connects signals."""
        super().__init__()
        logger.info("Initializing MainWindow...")
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QtGui.QIcon(ICON_PATH))

        # Initialize core components
        self.video_handler = VideoHandler(self)
        self.track_manager = TrackManager(self)
        self.coord_transformer = CoordinateTransformer()
        self.scale_manager = ScaleManager(self)

        # Initialize video state variables
        self.total_frames = 0
        self.current_frame_index = -1
        self.video_loaded = False
        self.is_playing = False
        self.fps = 0.0
        self.total_duration_ms = 0.0
        self.video_filepath = ""
        self.frame_width = 0
        self.frame_height = 0

        self._auto_advance_enabled = False
        self._auto_advance_frames = 1

        self._setup_pens()

        screen_geometry = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        self.setGeometry(50, 50, int(screen_geometry.width() * 0.8), int(screen_geometry.height() * 0.8))
        self.setMinimumSize(800, 600)

        ui_setup.setup_main_window_ui(self)

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
                scale_m_per_px_input=self.scale_m_per_px_input,
                scale_px_per_m_input=self.scale_px_per_m_input,
                set_scale_by_feature_button=self.setScaleByFeatureButton,
                show_scale_line_checkbox=self.showScaleLineCheckBox,
                scale_reset_button=self.scale_reset_button,
                scale_display_meters_checkbox=self.scale_display_meters_checkbox,
                show_scale_bar_checkbox=self.showScaleBarCheckBox,
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
            cursor_labels_px = { "TL": self.cursorPosLabelTL, "BL": self.cursorPosLabelBL, "Custom": self.cursorPosLabelCustom }
            cursor_labels_m = { "TL": self.cursorPosLabelTL_m, "BL": self.cursorPosLabelBL_m, "Custom": self.cursorPosLabelCustom_m }
            self.coord_panel_controller = CoordinatePanelController(
                coord_transformer=self.coord_transformer, image_view=self.imageView,
                scale_manager=self.scale_manager, coord_system_group=self.coordSystemGroup,
                coord_top_left_radio=self.coordTopLeftRadio, coord_bottom_left_radio=self.coordBottomLeftRadio,
                coord_custom_radio=self.coordCustomRadio, coord_top_left_origin_label=self.coordTopLeftOriginLabel,
                coord_bottom_left_origin_label=self.coordBottomLeftOriginLabel, coord_custom_origin_label=self.coordCustomOriginLabel,
                set_origin_button=self.setOriginButton, show_origin_checkbox=self.showOriginCheckBox,
                cursor_pos_labels_px=cursor_labels_px, cursor_pos_labels_m=cursor_labels_m, parent=self
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
                tracks_table_widget=self.tracksTableWidget,
                points_table_widget=self.pointsTableWidget,
                points_tab_label=self.pointsTabLabel,
                parent=self
            )
            logger.debug("TrackDataViewController initialized.")
        else:
            logger.error("Table UI elements or core components not found for TrackDataViewController.")
            self.table_data_controller = None

        status_bar_instance = self.statusBar()
        if status_bar_instance:
            status_bar_instance.showMessage("Ready. Load a video via File -> Open Video...")

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
        self.track_manager.visualsNeedUpdate.connect(self._redraw_scene_overlay)

        if self.scale_panel_controller:
            self.scale_manager.scaleOrUnitChanged.connect(self.scale_panel_controller.update_ui_from_manager)
        if self.table_data_controller:
            self.scale_manager.scaleOrUnitChanged.connect(self.table_data_controller.update_points_table_ui)
        if self.coord_panel_controller:
             self.scale_manager.scaleOrUnitChanged.connect(self.coord_panel_controller._trigger_cursor_label_update_slot)

        if self.coord_panel_controller:
            self.coord_panel_controller.needsRedraw.connect(self._redraw_scene_overlay)
            if self.table_data_controller:
                 self.coord_panel_controller.pointsTableNeedsUpdate.connect(self.table_data_controller.update_points_table_ui)
            if status_bar_instance:
                self.coord_panel_controller.statusBarMessage.connect(status_bar_instance.showMessage)

        if self.table_data_controller:
            self.table_data_controller.seekVideoToFrame.connect(self.video_handler.seek_frame)
            self.table_data_controller.updateMainWindowUIState.connect(self._update_ui_state)
            if status_bar_instance:
                self.table_data_controller.statusBarMessage.connect(status_bar_instance.showMessage)
            if hasattr(self.tracksTableWidget, 'horizontalHeader') and \
               hasattr(self.tracksTableWidget.horizontalHeader(), 'sectionClicked'):
                 self.tracksTableWidget.horizontalHeader().sectionClicked.connect(
                     self.table_data_controller.handle_visibility_header_clicked
                 )

        if self.frameSlider: self.frameSlider.valueChanged.connect(self._slider_value_changed)
        if self.playPauseButton: self.playPauseButton.clicked.connect(self._toggle_playback)
        if self.prevFrameButton: self.prevFrameButton.clicked.connect(self._show_previous_frame)
        if self.nextFrameButton: self.nextFrameButton.clicked.connect(self._show_next_frame)
        if self.autoAdvanceCheckBox: self.autoAdvanceCheckBox.stateChanged.connect(self._handle_auto_advance_toggled)
        if self.autoAdvanceSpinBox: self.autoAdvanceSpinBox.valueChanged.connect(self._handle_auto_advance_frames_changed)
        if self.videoInfoAction: self.videoInfoAction.triggered.connect(self._show_video_info_dialog)
        if self.preferencesAction: self.preferencesAction.triggered.connect(self._show_preferences_dialog)
        if self.newTrackAction:
            self.newTrackAction.setShortcut(QtGui.QKeySequence.StandardKey.New)
            self.newTrackAction.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            self.newTrackAction.triggered.connect(self._create_new_track)

        # --- BEGIN MODIFICATION: Connect exportViewAction ---
        if hasattr(self, 'exportViewAction') and self.exportViewAction:
            self.exportViewAction.triggered.connect(self._handle_export_current_view_to_mp4)
        # --- END MODIFICATION ---


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
        status_bar = self.statusBar()
        if status_bar: status_bar.clearMessage()
        if self.frameLabel: self.frameLabel.setText("Frame: - / -")
        if self.timeLabel: self.timeLabel.setText("Time: --:--.--- / --:--.---")
        if self.fpsLabel: self.fpsLabel.setText("FPS: ---.--")
        if self.filenameLabel:
             self.filenameLabel.setText("File: -")
             self.filenameLabel.setToolTip("No video loaded")
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
            is_setting_scale_by_line = self.scale_panel_controller._is_setting_scale_by_line

        nav_enabled_during_action = not is_setting_scale_by_line

        if self.frameSlider: self.frameSlider.setEnabled(is_video_loaded and nav_enabled_during_action)
        if self.prevFrameButton: self.prevFrameButton.setEnabled(is_video_loaded and nav_enabled_during_action)
        if self.nextFrameButton: self.nextFrameButton.setEnabled(is_video_loaded and nav_enabled_during_action)

        can_play: bool = is_video_loaded and self.fps > 0 and nav_enabled_during_action
        if self.playPauseButton: self.playPauseButton.setEnabled(can_play)

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

        # --- BEGIN MODIFICATION: Enable/disable exportViewAction ---
        if hasattr(self, 'exportViewAction') and self.exportViewAction:
            self.exportViewAction.setEnabled(is_video_loaded)
        # --- END MODIFICATION ---

        if self.scale_panel_controller: self.scale_panel_controller.set_video_loaded_status(is_video_loaded)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_loaded_status(is_video_loaded)
        if self.table_data_controller: self.table_data_controller.set_video_loaded_status(is_video_loaded, self.total_frames if is_video_loaded else 0)


    def _update_ui_for_frame(self, frame_index: int) -> None:
        if not self.video_loaded: return
        if self.frameSlider:
            self.frameSlider.blockSignals(True); self.frameSlider.setValue(frame_index); self.frameSlider.blockSignals(False)
        if self.frameLabel: self.frameLabel.setText(f"Frame: {frame_index + 1} / {self.total_frames}")
        if self.timeLabel:
            current_ms = (frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
            self.timeLabel.setText(f"Time: {self._format_time(current_ms)} / {self._format_time(self.total_duration_ms)}")

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
        self.track_manager.reset()
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
        """Handles the settingsApplied signal from the PreferencesDialog."""
        logger.info("MainWindow: Settings applied, refreshing visuals.")
        self._setup_pens()

        if self.imageView and hasattr(self.imageView, '_scale_bar_widget') and self.imageView._scale_bar_widget:
            logger.debug("MainWindow: Calling update_appearance_from_settings on ScaleBarWidget.")
            self.imageView._scale_bar_widget.update_appearance_from_settings()
            if self.imageView._scale_bar_widget.isVisible():
                 self.imageView._update_overlay_widget_positions()
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

    @QtCore.Slot(dict)
    def _handle_video_loaded(self, video_info: Dict[str, Any]) -> None:
        logger.info(f"Received videoLoaded signal: {video_info.get('filename', 'N/A')}")
        self.total_frames = video_info.get('total_frames', 0); self.video_loaded = True; self.fps = video_info.get('fps', 0.0)
        self.total_duration_ms = video_info.get('duration_ms', 0.0); self.video_filepath = video_info.get('filepath', '')
        self.frame_width = video_info.get('width', 0); self.frame_height = video_info.get('height', 0); self.is_playing = False
        self.coord_transformer.set_video_height(self.frame_height)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_height(self.frame_height)
        if self.filenameLabel: self.filenameLabel.setText(f"File: {video_info.get('filename', 'N/A')}"); self.filenameLabel.setToolTip(video_info.get('filepath', ''))
        if self.fpsLabel: self.fpsLabel.setText(f"FPS: {self.fps:.2f}" if self.fps > 0 else "FPS: N/A")
        self.track_manager.reset()
        if self.frameSlider: self.frameSlider.setMaximum(self.total_frames - 1 if self.total_frames > 0 else 0); self.frameSlider.setValue(0)
        if self.imageView: self.imageView.resetInitialLoadFlag()
        self.scale_manager.reset()
        if self.scale_panel_controller: self.scale_panel_controller.set_video_loaded_status(True)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_loaded_status(True); self.coord_panel_controller.update_ui_display()
        if self.table_data_controller: self.table_data_controller.set_video_loaded_status(True, self.total_frames)
        self._update_ui_state()
        status_msg = (f"Loaded '{video_info.get('filename', 'N/A')}' ({self.total_frames} frames, {self.frame_width}x{self.frame_height}, {self.fps:.2f} FPS)")
        status_bar = self.statusBar()
        if status_bar: status_bar.showMessage(status_msg, 5000)

    @QtCore.Slot(str)
    def _handle_video_load_failed(self, error_msg: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Video Load Error", error_msg)
        status_bar = self.statusBar()
        if status_bar: status_bar.showMessage("Error loading video", 5000)
        self._release_video()

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
           self.scale_panel_controller._is_setting_scale_by_line: return
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Cannot add point: No video loaded.", 3000)
            return
        if self.track_manager.active_track_index == -1:
            if status_bar: status_bar.showMessage("Cannot add point: No track selected.", 3000)
            return
        time_ms = (self.current_frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
        if self.track_manager.add_point(self.current_frame_index, time_ms, x, y):
            x_d, y_d = self.coord_transformer.transform_point_for_display(x,y)
            msg = f"Point for Track {self.track_manager.get_active_track_id()} on Frame {self.current_frame_index+1}: ({x_d:.1f}, {y_d:.1f})"
            if status_bar: status_bar.showMessage(msg, 3000)
            if self._auto_advance_enabled and self._auto_advance_frames > 0:
                target = min(self.current_frame_index + self._auto_advance_frames, self.total_frames - 1)
                if target > self.current_frame_index: self.video_handler.seek_frame(target)
        elif status_bar: status_bar.showMessage("Failed to add point (see log).", 3000)

    @QtCore.Slot(float, float, QtCore.Qt.KeyboardModifiers)
    def _handle_modified_click(self, x: float, y: float, modifiers: QtCore.Qt.KeyboardModifiers) -> None:
        status_bar = self.statusBar()
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Cannot interact: Video/components not ready.", 3000)
            return
        result = self.track_manager.find_closest_visible_point(x, y, self.current_frame_index)
        if result is None:
            if status_bar: status_bar.showMessage("No track marker found near click.", 3000)
            return
        track_idx, point_data = result; track_id = track_idx + 1; frame_idx = point_data[0]
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            if self.track_manager.active_track_index != track_idx: self.track_manager.set_active_track(track_idx)
            if self.table_data_controller: QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_track_row_by_id_in_ui(track_id))
            if status_bar: status_bar.showMessage(f"Selected Track {track_id}.", 3000)
        elif modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:
            if self.track_manager.active_track_index != track_idx: self.track_manager.set_active_track(track_idx)
            if self.table_data_controller: QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_track_row_by_id_in_ui(track_id))
            if self.current_frame_index != frame_idx: self.video_handler.seek_frame(frame_idx)
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
        if self.table_data_controller: QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_track_row_by_id_in_ui(new_id))
        if self.dataTabsWidget: self.dataTabsWidget.setCurrentIndex(0)
        self._update_ui_state()

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

    def _format_length_value_for_line(self, length_meters: float) -> str:
        """
        Formats a given length in meters into a human-readable string
        with appropriate units (km, m, cm, mm, µm, nm) or scientific notation.
        Uses constants from config.py.
        """
        if length_meters == 0:
            return "0 m"

        if abs(length_meters) >= config.SCIENTIFIC_NOTATION_UPPER_THRESHOLD or \
           (abs(length_meters) > 0 and abs(length_meters) <= config.SCIENTIFIC_NOTATION_LOWER_THRESHOLD):
            return f"{length_meters:.2e}"

        for factor, singular_abbr, plural_abbr in config.UNIT_PREFIXES:
            if abs(length_meters) >= factor * 0.99:
                value_in_unit = length_meters / factor
                if factor >= 1.0:
                    precision = 2 if abs(value_in_unit) < 10 else 1 if abs(value_in_unit) < 100 else 0
                elif factor >= 1e-3:
                    precision = 1 if abs(value_in_unit) < 100 else 0
                else:
                    precision = 0
                if abs(value_in_unit) >= 1 and value_in_unit == math.floor(value_in_unit) and precision > 0:
                     if abs(value_in_unit) > 10 : precision = 0
                formatted_value = f"{value_in_unit:.{precision}f}"
                unit_to_display = plural_abbr if plural_abbr and abs(value_in_unit) != 1.0 else singular_abbr
                return f"{formatted_value} {unit_to_display}"
        return f"{length_meters:.3f} m"

    @QtCore.Slot()
    def _redraw_scene_overlay(self) -> None:
        if not (self.imageView and self.imageView._scene and self.video_loaded and self.current_frame_index >= 0):
            if self.imageView: self.imageView.clearOverlay()
            return

        scene = self.imageView._scene
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
                if el.get('type') == 'marker' and el.get('pos'):
                    x, y = el['pos']; r = marker_sz / 2.0
                    path = QtGui.QPainterPath(); path.moveTo(x - r, y); path.lineTo(x + r, y); path.moveTo(x, y - r); path.lineTo(x, y + r)
                    item = QtWidgets.QGraphicsPathItem(path); item.setPen(pen); item.setZValue(10); scene.addItem(item)
                elif el.get('type') == 'line' and el.get('p1') and el.get('p2'):
                    p1, p2 = el['p1'], el['p2']
                    item = QtWidgets.QGraphicsLineItem(p1[0], p1[1], p2[0], p2[1]); item.setPen(pen); item.setZValue(9); scene.addItem(item)

            if self.coord_panel_controller and self.coord_panel_controller.get_show_origin_marker_status():
                origin_sz = float(settings_manager.get_setting(settings_manager.KEY_ORIGIN_MARKER_SIZE))
                ox, oy = self.coord_transformer.get_current_origin_tl()
                r_orig = origin_sz / 2.0
                origin_item = QtWidgets.QGraphicsEllipseItem(ox - r_orig, oy - r_orig, origin_sz, origin_sz)
                origin_item.setPen(self.pen_origin_marker); origin_item.setBrush(self.pen_origin_marker.color()); origin_item.setZValue(11)
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
                    length_text = self._format_length_value_for_line(meter_length)
                    line_clr = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_COLOR)
                    text_clr = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_COLOR)
                    font_sz = int(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_SIZE))
                    pen_w = float(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_WIDTH))
                    self.imageView.draw_persistent_scale_line(
                        line_data=line_data, length_text=length_text, line_color=line_clr,
                        text_color=text_clr, font_size=font_sz, pen_width=pen_w
                    )
                    logger.debug("MainWindow requested ImageView to draw persistent scale line with updated settings.")

            if self.imageView.viewport():
                self.imageView.viewport().update()
        except Exception as e:
            logger.exception(f"Error during overlay coordination in _redraw_scene_overlay: {e}")
            if self.imageView: self.imageView.clearOverlay()


    @QtCore.Slot()
    def _handle_export_current_view_to_mp4(self) -> None:
        action_to_disable = None
        if hasattr(self, 'exportViewAction') and self.exportViewAction:
            action_to_disable = self.exportViewAction
            if action_to_disable.isEnabled():
                action_to_disable.setEnabled(False)
            else:
                logger.warning("_handle_export_current_view_to_mp4 called while action already disabled. Aborting.")
                return

        try:
            if not self.video_loaded:
                QtWidgets.QMessageBox.warning(self, "Export Error", "No video loaded to export.")
                return
            if not self.imageView:
                logger.error("Cannot export: ImageView not available.")
                QtWidgets.QMessageBox.critical(self, "Export Error", "Internal error: ImageView component missing.")
                return

            default_filename = "video_with_overlays.mp4"
            if self.video_filepath:
                base, ext = os.path.splitext(os.path.basename(self.video_filepath))
                default_filename = f"{base}_tracked.mp4"

            save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export Current View to MP4", default_filename,
                "MP4 Video Files (*.mp4);;All Files (*)"
            )

            if not save_path:
                status_bar = self.statusBar()
                if status_bar: status_bar.showMessage("Export cancelled.", 3000)
                return

            view_transform = self.imageView.transform()
            viewport_size = self.imageView.viewport().size()
            export_width = viewport_size.width()
            export_height = viewport_size.height()

            if export_width <= 0 or export_height <= 0:
                QtWidgets.QMessageBox.critical(self, "Export Error", "Invalid viewport dimensions for export.")
                return

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_fps_for_export = self.fps if self.fps > 0 else 30.0
            video_writer = cv2.VideoWriter(save_path, fourcc, video_fps_for_export, (export_width, export_height))

            if not video_writer.isOpened():
                QtWidgets.QMessageBox.critical(self, "Export Error", f"Could not open video writer for: {save_path}")
                return

            progress_dialog = QtWidgets.QProgressDialog("Exporting video...", "Cancel", 0, self.total_frames, self)
            progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            progress_dialog.setWindowTitle("Export Progress")
            progress_dialog.show()
            QtWidgets.QApplication.processEvents()

            logger.info(f"Starting video export to {save_path} ({export_width}x{export_height} @ {video_fps_for_export} FPS)")
            status_bar = self.statusBar()
            if status_bar: status_bar.showMessage(f"Exporting to {os.path.basename(save_path)}...", 0)

            export_cancelled = False
            for frame_idx in range(self.total_frames):
                if progress_dialog.wasCanceled():
                    export_cancelled = True
                    break
                progress_dialog.setValue(frame_idx)
                QtWidgets.QApplication.processEvents()

                raw_cv_frame = self.video_handler.get_raw_frame_at_index(frame_idx)
                
                source_qimage_for_drawing: Optional[QtGui.QImage] = None
                if raw_cv_frame is not None:
                    h_raw, w_raw = raw_cv_frame.shape[:2]
                    channels_raw = raw_cv_frame.shape[2] if len(raw_cv_frame.shape) == 3 else 1
                    temp_qimage_wrapper: Optional[QtGui.QImage] = None
                    try:
                        if channels_raw == 3: 
                            contig_raw_cv_frame = np.require(raw_cv_frame, requirements=['C_CONTIGUOUS'])
                            rgb_frame_data = cv2.cvtColor(contig_raw_cv_frame, cv2.COLOR_BGR2RGB) 
                            temp_qimage_wrapper = QtGui.QImage(rgb_frame_data.data, w_raw, h_raw, rgb_frame_data.strides[0], QtGui.QImage.Format.Format_RGB888)
                        elif channels_raw == 1: 
                            contig_raw_cv_frame = np.require(raw_cv_frame, requirements=['C_CONTIGUOUS'])
                            temp_qimage_wrapper = QtGui.QImage(contig_raw_cv_frame.data, w_raw, h_raw, contig_raw_cv_frame.strides[0], QtGui.QImage.Format.Format_Grayscale8)
                        
                        if temp_qimage_wrapper is not None and not temp_qimage_wrapper.isNull():
                            if temp_qimage_wrapper.format() == QtGui.QImage.Format.Format_RGB888:
                                source_qimage_for_drawing = temp_qimage_wrapper.copy() 
                            else: 
                                source_qimage_for_drawing = temp_qimage_wrapper.convertToFormat(QtGui.QImage.Format.Format_RGB888)
                    except Exception as e_conv:
                        logger.error(f"Frame {frame_idx}: Error during raw_cv_frame to QImage conversion: {e_conv}", exc_info=True)
                    
                    if source_qimage_for_drawing is not None and source_qimage_for_drawing.isNull(): 
                        source_qimage_for_drawing = None
                
                if source_qimage_for_drawing is None:
                    logger.warning(f"Frame {frame_idx}: source_qimage_for_drawing is None. Using black frame.")
                    source_qimage_for_drawing = QtGui.QImage(export_width, export_height, QtGui.QImage.Format.Format_RGB888)
                    source_qimage_for_drawing.fill(QtCore.Qt.GlobalColor.black)

                export_canvas_qimage = QtGui.QImage(export_width, export_height, QtGui.QImage.Format.Format_RGB888)
                export_canvas_qimage.fill(QtCore.Qt.GlobalColor.black)

                painter = QtGui.QPainter(export_canvas_qimage)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
                painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
                # HighQualityAntialiasing was removed

                if source_qimage_for_drawing and not source_qimage_for_drawing.isNull():
                    target_export_rect = QtCore.QRectF(export_canvas_qimage.rect())
                    visible_scene_area_rect_float = self.imageView.mapToScene(self.imageView.viewport().rect()).boundingRect()
                    painter.drawImage(target_export_rect, source_qimage_for_drawing, visible_scene_area_rect_float)

                painter.save()
                visible_scene_area_rect_for_overlays_float = self.imageView.mapToScene(self.imageView.viewport().rect()).boundingRect()
                if not visible_scene_area_rect_for_overlays_float.isEmpty():
                    visible_scene_area_rect_for_overlays_int = visible_scene_area_rect_for_overlays_float.toRect()
                    painter.setWindow(visible_scene_area_rect_for_overlays_int)
                    painter.setViewport(export_canvas_qimage.rect())
                
                marker_sz = float(settings_manager.get_setting(settings_manager.KEY_MARKER_SIZE))
                track_elements = self.track_manager.get_visual_elements(frame_idx)
                pens = {
                    config.STYLE_MARKER_ACTIVE_CURRENT: self.pen_marker_active_current,
                    config.STYLE_MARKER_ACTIVE_OTHER: self.pen_marker_active_other,
                    config.STYLE_MARKER_INACTIVE_CURRENT: self.pen_marker_inactive_current,
                    config.STYLE_MARKER_INACTIVE_OTHER: self.pen_marker_inactive_other,
                    config.STYLE_LINE_ACTIVE: self.pen_line_active,
                    config.STYLE_LINE_INACTIVE: self.pen_line_inactive,
                }
                for el in track_elements:
                    pen_to_use = pens.get(el.get('style'))
                    if not pen_to_use: continue
                    current_pen = QtGui.QPen(pen_to_use) 
                    current_pen.setCosmetic(True) 
                    painter.setPen(current_pen)
                    if el.get('type') == 'marker' and el.get('pos'):
                        x, y = el['pos']; r = marker_sz / 2.0
                        painter.drawLine(QtCore.QPointF(x - r, y), QtCore.QPointF(x + r, y))
                        painter.drawLine(QtCore.QPointF(x, y - r), QtCore.QPointF(x, y + r))
                    elif el.get('type') == 'line' and el.get('p1') and el.get('p2'):
                        p1, p2 = el['p1'], el['p2']
                        painter.drawLine(QtCore.QPointF(p1[0], p1[1]), QtCore.QPointF(p2[0], p2[1]))

                if self.coord_panel_controller and self.coord_panel_controller.get_show_origin_marker_status():
                    origin_sz = float(settings_manager.get_setting(settings_manager.KEY_ORIGIN_MARKER_SIZE))
                    ox, oy = self.coord_transformer.get_current_origin_tl() 
                    r_orig = origin_sz / 2.0
                    origin_pen = QtGui.QPen(self.pen_origin_marker) 
                    origin_pen.setCosmetic(True) 
                    painter.setPen(origin_pen)
                    painter.setBrush(self.pen_origin_marker.color())
                    painter.drawEllipse(QtCore.QRectF(ox - r_orig, oy - r_orig, origin_sz, origin_sz))

                if self.showScaleLineCheckBox and self.showScaleLineCheckBox.isChecked() and \
                   self.scale_manager and self.scale_manager.has_defined_scale_line():
                    line_data = self.scale_manager.get_defined_scale_line_data() 
                    scale_m_per_px = self.scale_manager.get_scale_m_per_px()
                    if line_data and scale_m_per_px is not None and scale_m_per_px > 0:
                        p1x, p1y, p2x, p2y = line_data
                        dx_sl = p2x - p1x; dy_sl = p2y - p1y
                        pixel_length_sl = math.sqrt(dx_sl*dx_sl + dy_sl*dy_sl)
                        meter_length_sl = pixel_length_sl * scale_m_per_px
                        length_text_sl = self._format_length_value_for_line(meter_length_sl)
                        line_clr_sl = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_COLOR)
                        text_clr_sl = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_COLOR)
                        font_sz_sl = int(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_SIZE))
                        pen_w_sl = float(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_WIDTH))
                        
                        # This rect is defined earlier in your export method
                        self._draw_scale_line_on_painter(painter, line_data, length_text_sl, 
                                                         line_clr_sl, text_clr_sl, 
                                                         font_sz_sl, pen_w_sl,
                                                         visible_scene_area_rect_float) # Pass the rect here
                painter.restore() 

                if self.showScaleBarCheckBox and self.showScaleBarCheckBox.isChecked() and \
                   self.scale_manager and self.scale_manager.get_scale_m_per_px() is not None and \
                   hasattr(self.imageView, '_scale_bar_widget') and self.imageView._scale_bar_widget:
                    sb_widget: ScaleBarWidget = self.imageView._scale_bar_widget
                    sb_widget.update_dimensions( 
                        m_per_px_scene=self.scale_manager.get_scale_m_per_px(),
                        view_scale_factor=view_transform.m11(), 
                        parent_view_width=export_width
                    )
                    if sb_widget.isVisible() and sb_widget.get_current_bar_pixel_length() > 0:
                        sb_bar_len_px = sb_widget.get_current_bar_pixel_length()
                        sb_text = sb_widget.get_current_bar_text_label()
                        sb_bar_color = sb_widget.get_current_bar_color()
                        # ... (Rest of scale bar drawing logic remains the same)
                        sb_text_color = sb_widget.get_current_text_color()
                        sb_border_color = sb_widget.get_current_border_color()
                        sb_font = sb_widget.get_current_font()
                        sb_font_metrics = QtGui.QFontMetrics(sb_font) 
                        sb_rect_h_px = sb_widget.get_current_bar_rect_height()
                        sb_text_margin_bottom = sb_widget.get_text_margin_bottom()
                        sb_border_thickness_px = sb_widget.get_border_thickness()
                        sb_text_w_px, sb_text_h_px = sb_font_metrics.boundingRect(sb_text).width(), sb_font_metrics.height()
                        margin = 10 
                        overall_sb_width = int(max(sb_bar_len_px + 2 * sb_border_thickness_px, sb_text_w_px))
                        overall_sb_height = sb_text_h_px + sb_text_margin_bottom + sb_rect_h_px + 2 * sb_border_thickness_px
                        sb_x_offset = export_width - overall_sb_width - margin
                        sb_y_offset = export_height - overall_sb_height - margin
                        painter.save()
                        painter.translate(sb_x_offset, sb_y_offset) 
                        painter.setFont(sb_font)
                        painter.setPen(sb_text_color)
                        text_x_local = (overall_sb_width - sb_text_w_px) / 2.0
                        text_baseline_y_local = float(sb_font_metrics.ascent()) 
                        painter.drawText(QtCore.QPointF(text_x_local, text_baseline_y_local), sb_text)
                        bar_start_x_local = (overall_sb_width - sb_bar_len_px) / 2.0
                        bar_top_y_local = float(sb_text_h_px + sb_text_margin_bottom + sb_border_thickness_px) 
                        bar_rect_local = QtCore.QRectF(bar_start_x_local, bar_top_y_local, sb_bar_len_px, float(sb_rect_h_px))
                        current_scale_bar_pen = QtGui.QPen(sb_border_color, sb_border_thickness_px)
                        current_scale_bar_pen.setCosmetic(True) 
                        painter.setPen(current_scale_bar_pen)
                        painter.setBrush(sb_bar_color)
                        painter.drawRect(bar_rect_local)
                        painter.restore()
                painter.end() 

                if frame_idx == 0: 
                    try:
                        save_diag_path = os.path.join(os.path.dirname(save_path), "diag_export_frame_0.png")
                        if export_canvas_qimage.save(save_diag_path):
                            logger.info(f"Diagnostic frame saved to: {save_diag_path}")
                        else:
                            logger.error(f"Failed to save diagnostic frame to: {save_diag_path}")
                    except Exception as e_diag_save:
                        logger.error(f"Could not save diagnostic frame: {e_diag_save}")
                
                # --- QImage to OpenCV BGR format ---
                # Ensure the QImage is in the expected format for conversion
                if export_canvas_qimage.format() != QtGui.QImage.Format.Format_RGB888:
                    export_canvas_qimage = export_canvas_qimage.convertToFormat(QtGui.QImage.Format.Format_RGB888)

                width = export_canvas_qimage.width()
                height = export_canvas_qimage.height()
                bytes_per_line = export_canvas_qimage.bytesPerLine() # This will account for padding
                
                ptr = export_canvas_qimage.constBits()
                try:
                    # This is crucial for PySide6 with np.frombuffer or np.array(ptr)
                    ptr.setsize(export_canvas_qimage.sizeInBytes())
                except AttributeError:
                    logger.debug("ptr does not have setsize; proceeding with np.frombuffer.")
                
                # Create a 1D NumPy array from the QImage's buffer
                # np.frombuffer is generally safer as it doesn't try to infer shape initially
                buffer_size = export_canvas_qimage.sizeInBytes()
                full_buffer_1d = np.frombuffer(ptr, dtype=np.uint8, count=buffer_size)

                # Create an empty array for the RGB pixel data (no padding)
                cv_export_frame_rgb = np.empty((height, width, 3), dtype=np.uint8)
                
                # Copy data line by line, removing padding
                for i in range(height):
                    line_start_offset_in_buffer = i * bytes_per_line
                    # Length of actual pixel data in a line (width * 3 bytes for RGB)
                    pixel_data_len_for_line = width * 3
                    
                    # Slice the actual pixel data from the padded line in full_buffer_1d
                    line_pixel_data = full_buffer_1d[line_start_offset_in_buffer : line_start_offset_in_buffer + pixel_data_len_for_line]
                    
                    if line_pixel_data.size == pixel_data_len_for_line:
                        cv_export_frame_rgb[i] = line_pixel_data.reshape(width, 3)
                    else:
                        # This should ideally not happen if calculations are correct and buffer is large enough
                        logger.error(f"Frame {frame_idx}, line {i}: Mismatch in expected line data size. "
                                     f"Got {line_pixel_data.size}, expected {pixel_data_len_for_line}. Filling with black.")
                        cv_export_frame_rgb[i] = 0 # Fill line with black as an error indicator
                        
                cv_export_frame_bgr = cv2.cvtColor(cv_export_frame_rgb, cv2.COLOR_RGB2BGR)
                
                video_writer.write(cv_export_frame_bgr)

            video_writer.release()
            progress_dialog.setValue(self.total_frames)

            if status_bar:
                if export_cancelled:
                    status_bar.showMessage("Video export cancelled.", 5000)
                    logger.info(f"Video export to {save_path} cancelled by user.")
                    try:
                        if os.path.exists(save_path): os.remove(save_path)
                    except OSError as e:
                        logger.warning(f"Could not remove cancelled export file {save_path}: {e}")
                else:
                    status_bar.showMessage(f"Video export complete: {os.path.basename(save_path)}", 5000)
                    logger.info(f"Video export complete: {save_path}")
        
        finally: 
            if action_to_disable: 
                if self.video_loaded: 
                    action_to_disable.setEnabled(True)
                else: 
                    self._update_ui_state()


    def _draw_scale_line_on_painter(self, painter: QtGui.QPainter,
                                   line_data: Tuple[float, float, float, float],
                                   length_text: str,
                                   line_color_qcolor: QtGui.QColor,
                                   text_color_qcolor: QtGui.QColor,
                                   font_size_pt: int,
                                   pen_width_px: float,
                                   # --- MODIFICATION: Add scene_rect_for_text_placement ---
                                   scene_rect_for_text_placement: QtCore.QRectF) -> None:
        """
        Helper to draw a scale line with text onto a QPainter instance.
        This replicates the logic from InteractiveImageView.draw_persistent_scale_line.
        Assumes painter's transform is already set for scene coordinates.
        """
        p1x, p1y, p2x, p2y = line_data

        # --- Line Pen ---
        line_pen = QtGui.QPen(line_color_qcolor, pen_width_px)
        line_pen.setCosmetic(True)
        line_pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
        painter.setPen(line_pen)
        painter.drawLine(QtCore.QPointF(p1x, p1y), QtCore.QPointF(p2x, p2y))

        # --- End Ticks (if enabled in settings) ---
        show_ticks = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_SHOW_TICKS)
        tick_length_factor = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR)
        tick_total_length = pen_width_px * tick_length_factor
        half_tick_length = tick_total_length / 2.0

        dx = p2x - p1x # dx, dy needed for line_length_for_norm and text placement later
        dy = p2y - p1y
        line_length_for_norm = math.sqrt(dx*dx + dy*dy)

        if show_ticks and tick_total_length > 0:
            if line_length_for_norm > 1e-6:
                norm_perp_dx = -dy / line_length_for_norm
                norm_perp_dy = dx / line_length_for_norm

                for px_pt, py_pt in [(p1x, p1y), (p2x, p2y)]:
                    tick1_p1x = px_pt + norm_perp_dx * half_tick_length
                    tick1_p1y = py_pt + norm_perp_dy * half_tick_length
                    tick1_p2x = px_pt - norm_perp_dx * half_tick_length
                    tick1_p2y = py_pt - norm_perp_dy * half_tick_length
                    painter.drawLine(QtCore.QPointF(tick1_p1x, tick1_p1y), QtCore.QPointF(tick1_p2x, tick1_p2y))
        elif not show_ticks: # Fallback dots if ticks are off
            painter.setBrush(QtGui.QBrush(line_color_qcolor))
            dot_pen = QtGui.QPen(line_color_qcolor, 0.5) # Thin border for dots
            dot_pen.setCosmetic(True)
            painter.setPen(dot_pen)
            marker_radius = max(1.0, pen_width_px / 2.0)
            for px_dot, py_dot in [(p1x, p1y), (p2x, p2y)]:
                painter.drawEllipse(QtCore.QRectF(px_dot - marker_radius, py_dot - marker_radius,
                                                 2 * marker_radius, 2 * marker_radius))


        # --- Text ---
        current_font = painter.font() # Get painter's current font
        # Ensure point size is applied correctly if not already set on painter from outside
        if current_font.pointSize() != font_size_pt:
            current_font.setPointSize(font_size_pt)
        painter.setFont(current_font)
        painter.setPen(text_color_qcolor)

        font_metrics = QtGui.QFontMetrics(current_font)
        # Using tightBoundingRect can sometimes give more accurate width/height for rotated text.
        # However, boundingRect is generally used for layout before rotation.
        local_text_rect = font_metrics.boundingRect(length_text)
        text_width = local_text_rect.width()
        text_height = local_text_rect.height() # Height of the bounding rect

        # --- Text Placement (Logic adapted from InteractiveImageView) ---
        line_mid_x = (p1x + p2x) / 2.0
        line_mid_y = (p1y + p2y) / 2.0
        
        # line_length_for_norm already calculated for ticks, reuse it
        line_length = line_length_for_norm

        if line_length < 1e-6: # Zero-length line
            painter.drawText(QtCore.QPointF(p1x + 2, p1y - text_height - 2), length_text)
            return

        line_angle_rad = math.atan2(dy, dx) # dy, dx already calculated
        line_angle_deg = math.degrees(line_angle_rad)

        # Save painter state for text transformation
        painter.save()

        # Move painter origin to the text's intended center *before* rotation and shift
        # The text will be drawn relative to (0,0) after transformations.
        # The reference point for drawing the text is its top-left corner.
        # We want to rotate around the text's own center.
        painter.translate(line_mid_x, line_mid_y) # Move to line midpoint

        # Rotate painter to align with the line
        text_rotation_deg = line_angle_deg
        if text_rotation_deg > 90: text_rotation_deg -= 180
        elif text_rotation_deg < -90: text_rotation_deg += 180
        painter.rotate(text_rotation_deg)

        # Calculate perpendicular shift for text
        desired_gap_pixels = 3 # Consistent with InteractiveImageView
        # Shift magnitude relative to the text's height (for vertical clearance)
        shift_magnitude = (text_height / 2.0) + desired_gap_pixels

        # Determine which side of the line is "towards the center" of the scene_rect_for_text_placement
        img_center = scene_rect_for_text_placement.center()

        # To determine which side is "closer" to the image center, we effectively
        # test points shifted perpendicularly from the line's midpoint.
        # The painter is already rotated, so a Y-shift will be perpendicular.
        # We need to un-rotate the image center relative to the line's midpoint
        # to make this decision in the line's local coordinate system.

        # Transform image center to be relative to line_mid_x, line_mid_y
        relative_img_center_x = img_center.x() - line_mid_x
        relative_img_center_y = img_center.y() - line_mid_y

        # Rotate this relative point by the *negative* of the line's angle
        # to see where it lies in the line's unrotated coordinate frame.
        cos_neg_angle = math.cos(-line_angle_rad)
        sin_neg_angle = math.sin(-line_angle_rad)
        
        unrotated_img_center_y = relative_img_center_x * sin_neg_angle + relative_img_center_y * cos_neg_angle
        # unrotated_img_center_x is not needed for this decision.

        # If unrotated_img_center_y is negative, it means the image center is on the "up" side
        # of the horizontal line in its local frame (which corresponds to one perpendicular direction).
        # We want to shift the text away from the image center.
        # So, if image center is "up" (negative local Y), shift text "down" (positive Y shift).
        # If image center is "down" (positive local Y), shift text "up" (negative Y shift).
        final_shift_y = shift_magnitude
        if unrotated_img_center_y < 0: # Image center is "above" the line (in its local frame)
            final_shift_y = shift_magnitude # Shift text "down"
        else: # Image center is "below" or on the line
            final_shift_y = -shift_magnitude # Shift text "up"
            

        # Reset painter for this new logic block, as the previous translate/rotate was for a different approach
        painter.restore() # Restores to state before the previous painter.save()
        painter.save()    # Save again for this block

        painter.setPen(text_color_qcolor) # Ensure pen is set after restore

        # Calculate the final top-left position of the text including rotation and perpendicular shift
        # This is the complex part that needs to match QGraphicsSimpleTextItem's behavior.
        
        # Start with text centered at line_mid_x, line_mid_y (its center, not top-left)
        # Then apply shifts and rotation
        
        transform = QtGui.QTransform()
        transform.translate(line_mid_x, line_mid_y) # Move to line center
        transform.rotate(text_rotation_deg)         # Rotate
        
        # Perpendicular shift in the rotated system.
        # If final_shift_y determined above is correct direction:
        transform.translate(0, final_shift_y) # Shift perpendicularly
        
        # Now, adjust for the text's own bounding box to draw from top-left
        # The (0,0) of the painter is now where the center of the text baseline *should* be,
        # but rotated and shifted. We draw the text such that its bounding box is centered around this.
        # So, draw at (-text_width/2, -text_height/2), but need to consider baseline.
        # QPainter.drawText(QPointF, str) draws with QPointF as the top-left of the *text*.
        
        painter.setTransform(transform) # Apply the combined transform
        
        # Replicating the setPos then moveBy of QGraphicsItem:
        painter.restore() # Restore to before any text specific transforms
        painter.save()

        # 1. Initial position: text top-left as if it's horizontal and centered on line mid-point
        initial_text_top_left_x = line_mid_x - (text_width / 2)
        initial_text_top_left_y = line_mid_y - (text_height / 2)

        # 2. Perpendicular shift calculation (Global coordinates)
        # final_shift_y was calculated in the line's local rotated frame. Need global shift vector.
        # The perpendicular direction in global coords depends on line_angle_rad
        # perp_dx_global = -dy / line_length  (or math.sin(line_angle_rad + math.pi/2))
        # perp_dy_global =  dx / line_length  (or -math.cos(line_angle_rad + math.pi/2))
        
        # The `final_shift_y` determines direction. Let's use the sign.
        actual_shift_magnitude = shift_magnitude
        if final_shift_y < 0: # Corresponds to one perp direction
            shift_offset_x = actual_shift_magnitude * math.sin(math.radians(line_angle_deg)) # sin for y-component of perp vector if line is horizontal
            shift_offset_y = -actual_shift_magnitude * math.cos(math.radians(line_angle_deg))# cos for x-component
        else: # Corresponds to the other perp direction
            shift_offset_x = -actual_shift_magnitude * math.sin(math.radians(line_angle_deg))
            shift_offset_y = actual_shift_magnitude * math.cos(math.radians(line_angle_deg))
            
        # This is still not quite right. Let's use the InteractiveImageView's perp vector logic:
        perp_dx_global_norm = -dy / line_length # Normalized perpendicular vector component
        perp_dy_global_norm = dx / line_length  # Normalized perpendicular vector component

        # Choose direction based on `unrotated_img_center_y`
        # If unrotated_img_center_y < 0, image center is on the side pointed by (perp_dx_global_norm, perp_dy_global_norm)
        # So we want to shift the text in the OPPOSITE direction of that.
        # If unrotated_img_center_y >=0, image center is on the side pointed by (-perp_dx_global_norm, -perp_dy_global_norm)
        # So we want to shift the text in the direction of (perp_dx_global_norm, perp_dy_global_norm)
        
        chosen_shift_dx_component = 0.0
        chosen_shift_dy_component = 0.0

        if unrotated_img_center_y < 0: # img center is "above" (using the original logic's terms)
            chosen_shift_dx_component = -perp_dx_global_norm 
            chosen_shift_dy_component = -perp_dy_global_norm
        else:
            chosen_shift_dx_component = perp_dx_global_norm
            chosen_shift_dy_component = perp_dy_global_norm
            
        final_total_shift_x = chosen_shift_dx_component * shift_magnitude
        final_total_shift_y = chosen_shift_dy_component * shift_magnitude
        
        # Final position for text's top-left, before rotation applied around its center
        text_final_pos_x = initial_text_top_left_x + final_total_shift_x
        text_final_pos_y = initial_text_top_left_y + final_total_shift_y

        # Apply translation to this final top-left, then rotate around text's center.
        painter.translate(text_final_pos_x + text_width / 2, text_final_pos_y + text_height / 2)
        painter.rotate(text_rotation_deg)
        
        # Draw text with its top-left at (-text_width/2, -text_height/2) relative to current translated/rotated origin
        # For QPainter.drawText, the y-coordinate is the baseline if using QPointF.
        # Need to adjust for baseline from top-left.
        # font_metrics.ascent() is height from baseline to top.
        # So, draw at y = -text_height/2 + font_metrics.ascent()
        painter.drawText(QtCore.QPointF(-text_width / 2, -text_height / 2 + font_metrics.ascent()), length_text)
        
        painter.restore()


    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key(); accepted = False
        status_bar = self.statusBar()
        if key == QtCore.Qt.Key.Key_Escape:
            if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and \
               self.scale_panel_controller._is_setting_scale_by_line:
                self.scale_panel_controller.cancel_set_scale_by_line()
                if status_bar: status_bar.showMessage("Set scale by line cancelled.", 3000)
                accepted = True
            elif self.coord_panel_controller and self.coord_panel_controller.is_setting_origin_mode():
                self.coord_panel_controller._is_setting_origin = False # type: ignore
                self.imageView.set_interaction_mode(InteractionMode.NORMAL)
                if status_bar: status_bar.showMessage("Set origin cancelled.", 3000)
                accepted = True
        if not accepted and key == QtCore.Qt.Key.Key_Space:
            if self.video_loaded and self.playPauseButton and self.playPauseButton.isEnabled():
                nav_disabled = False
                if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line'):
                    nav_disabled = self.scale_panel_controller._is_setting_scale_by_line # type: ignore
                if not nav_disabled: self._toggle_playback(); accepted = True
        elif not accepted and (key == QtCore.Qt.Key.Key_Delete or key == QtCore.Qt.Key.Key_Backspace):
            if self.video_loaded and self.track_manager.active_track_index != -1 and self.current_frame_index != -1:
                deleted = self.track_manager.delete_point(self.track_manager.active_track_index, self.current_frame_index)
                if status_bar: status_bar.showMessage(f"Deleted point..." if deleted else "No point to delete.", 3000)
                accepted = True
            elif status_bar: status_bar.showMessage("Cannot delete point.", 3000)
        if accepted: event.accept()
        else: super().keyPressEvent(event)

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
        except Exception as e: QtWidgets.QMessageBox.critical(self, "Error", f"Could not display video info:\n{e}")

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