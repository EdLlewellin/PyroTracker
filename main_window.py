# main_window.py
import sys
import os
import logging
from PySide6 import QtCore, QtGui, QtWidgets
# Import necessary types from typing module
from typing import Optional, List, Tuple, Dict, Any
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
from panel_controllers import ScalePanelController

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

    # Coordinate System State
    _is_setting_origin: bool
    _show_origin_marker: bool
    
    # Add type hints for scale panel widgets
    scale_m_per_px_input: Optional[QtWidgets.QLineEdit] = None
    scale_px_per_m_input: Optional[QtWidgets.QLineEdit] = None
    scale_reset_button: Optional[QtWidgets.QPushButton] = None
    scale_display_meters_checkbox: Optional[QtWidgets.QCheckBox] = None
    showScaleBarCheckBox: Optional[QtWidgets.QCheckBox] = None
    cursorPosLabelTL_m: Optional[QtWidgets.QLabel] = None
    cursorPosLabelBL_m: Optional[QtWidgets.QLabel] = None
    cursorPosLabelCustom_m: Optional[QtWidgets.QLabel] = None

    # UI Elements (These are assigned by ui_setup.setup_main_window_ui)
    # Add type hints for elements accessed directly in MainWindow methods
    mainSplitter: QtWidgets.QSplitter
    leftPanelWidget: QtWidgets.QWidget
    rightPanelWidget: QtWidgets.QWidget
    frameSlider: QtWidgets.QSlider
    playPauseButton: QtWidgets.QPushButton
    prevFrameButton: QtWidgets.QPushButton
    nextFrameButton: QtWidgets.QPushButton
    frameLabel: QtWidgets.QLabel
    timeLabel: QtWidgets.QLabel
    fpsLabel: QtWidgets.QLabel # Assuming fpsLabel is created in ui_setup
    filenameLabel: QtWidgets.QLabel
    dataTabsWidget: QtWidgets.QTabWidget
    tracksTableWidget: QtWidgets.QTableWidget
    pointsTabLabel: QtWidgets.QLabel
    pointsTableWidget: QtWidgets.QTableWidget
    statusBar: QtWidgets.QStatusBar
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
    newTrackAction: QtGui.QAction # Shortcut action
    videoInfoAction: QtGui.QAction
    preferencesAction: QtGui.QAction
    scale_manager: ScaleManager

    # UI Element Collections / State
    track_visibility_button_groups: Dict[int, QtWidgets.QButtonGroup]

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

        # Set Application Icon
        if os.path.exists(ICON_PATH):
            app_icon = QtGui.QIcon(ICON_PATH)
            self.setWindowIcon(app_icon)
            logger.debug(f"Application icon set from: {ICON_PATH}")
        else:
            logger.warning(f"Application icon file not found at: {ICON_PATH}")

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
        logger.debug("Video state variables initialized.")

        # Initialize Auto-Advance State
        self._auto_advance_enabled = False
        self._auto_advance_frames = 1
        logger.debug("Auto-advance state variables initialized.")

        # Initialize Core Components
        self.video_handler = VideoHandler(self)
        logger.debug("VideoHandler initialized.")
        self.track_manager = TrackManager(self)
        logger.debug("TrackManager initialized.")
        self.coord_transformer = CoordinateTransformer()
        logger.debug("CoordinateTransformer initialized.")
        self.scale_manager = ScaleManager(self)
        logger.debug("ScaleManager initialized.")
        self.scale_panel_controller: Optional[ScalePanelController] = None # Initialize attribute

        # Initialize Coordinate System State
        self._is_setting_origin = False
        self._show_origin_marker = True
        logger.debug(f"Initial origin marker visibility state: {self._show_origin_marker}")
        self._last_scene_mouse_x: float = -1.0
        self._last_scene_mouse_y: float = -1.0

        self.track_visibility_button_groups = {}
        self._setup_pens()

        screen_geometry: QtCore.QRect = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        initial_width: int = int(screen_geometry.width() * 0.8)
        initial_height: int = int(screen_geometry.height() * 0.8)
        self.setGeometry(50, 50, initial_width, initial_height)
        self.setMinimumSize(800, 600)
        logger.debug(f"Window geometry set: initial size {initial_width}x{initial_height}, minimum 800x600")

        logger.debug("Setting up UI via ui_setup module...")
        ui_setup.setup_main_window_ui(self)

        # Instantiate Panel Controllers AFTER ui_setup has created the widgets
        if hasattr(self, 'scale_m_per_px_input') and self.scale_m_per_px_input: # Check if UI elements are ready
            self.scale_panel_controller = ScalePanelController(
                scale_manager=self.scale_manager,
                image_view=self.imageView,
                scale_m_per_px_input=self.scale_m_per_px_input,
                scale_px_per_m_input=self.scale_px_per_m_input,
                scale_reset_button=self.scale_reset_button,
                scale_display_meters_checkbox=self.scale_display_meters_checkbox,
                show_scale_bar_checkbox=self.showScaleBarCheckBox,
                parent=self
            )
            logger.debug("ScalePanelController initialized.")
        else:
            logger.error("Scale panel UI elements not found for ScalePanelController.")
            self.scale_panel_controller = None


        self.statusBar = self.statusBar()
        if self.statusBar:
            self.statusBar.showMessage("Ready. Load a video via File -> Open Video...")
            logger.debug("Status bar initialized.")
        else:
            logger.error("Status bar not created during UI setup!")

        # --- Connect Signals ---
        self.video_handler.videoLoaded.connect(self._handle_video_loaded)
        self.video_handler.videoLoadFailed.connect(self._handle_video_load_failed)
        self.video_handler.frameChanged.connect(self._handle_frame_changed)
        self.video_handler.playbackStateChanged.connect(self._handle_playback_state_changed)

        if hasattr(self, 'imageView') and self.imageView:
            self.imageView.pointClicked.connect(self._handle_add_point_click)
            self.imageView.frameStepRequested.connect(self._handle_frame_step)
            self.imageView.modifiedClick.connect(self._handle_modified_click)
            self.imageView.originSetRequest.connect(self._set_custom_origin)
            self.imageView.sceneMouseMoved.connect(self._handle_mouse_moved)
            if self.scale_panel_controller: # Connect imageView to ScalePanelController
                self.imageView.viewTransformChanged.connect(self.scale_panel_controller._on_view_transform_changed)
            else: # Fallback if controller failed (should not happen ideally)
                # self.imageView.viewTransformChanged.connect(self._on_view_transform_changed) # Old connection
                logger.error("Cannot connect imageView.viewTransformChanged to ScalePanelController as it's not initialized.")

        self.track_manager.trackListChanged.connect(self._update_tracks_table)
        self.track_manager.activeTrackDataChanged.connect(self._update_points_table)
        self.track_manager.visualsNeedUpdate.connect(self._redraw_scene_overlay)

        # Connect ScaleManager signals
        if self.scale_panel_controller:
            self.scale_manager.scaleOrUnitChanged.connect(self.scale_panel_controller.update_ui_from_manager)
        # Keep connections for parts of MainWindow still needing this signal
        self.scale_manager.scaleOrUnitChanged.connect(self._update_points_table)
        self.scale_manager.scaleOrUnitChanged.connect(self._trigger_cursor_label_update)

        # UI Element Signals (excluding those handled by ScalePanelController)
        if hasattr(self, 'tracksTableWidget'):
            self.tracksTableWidget.itemSelectionChanged.connect(self._track_selection_changed)
            self.tracksTableWidget.cellClicked.connect(self._on_tracks_table_cell_clicked)
        if hasattr(self, 'pointsTableWidget'):
            self.pointsTableWidget.cellClicked.connect(self._on_points_table_cell_clicked)
        if hasattr(self, 'frameSlider'):
            self.frameSlider.valueChanged.connect(self._slider_value_changed)
        if hasattr(self, 'playPauseButton'):
            self.playPauseButton.clicked.connect(self._toggle_playback)
        if hasattr(self, 'prevFrameButton'):
            self.prevFrameButton.clicked.connect(self._show_previous_frame)
        if hasattr(self, 'nextFrameButton'):
            self.nextFrameButton.clicked.connect(self._show_next_frame)
        if hasattr(self, 'autoAdvanceCheckBox'):
            self.autoAdvanceCheckBox.stateChanged.connect(self._handle_auto_advance_toggled)
        if hasattr(self, 'autoAdvanceSpinBox'):
            self.autoAdvanceSpinBox.valueChanged.connect(self._handle_auto_advance_frames_changed)
        if hasattr(self, 'coordSystemGroup'):
            self.coordSystemGroup.buttonToggled.connect(self._coordinate_mode_changed)
        if hasattr(self, 'setOriginButton'):
            self.setOriginButton.clicked.connect(self._enter_set_origin_mode)
        if hasattr(self, 'showOriginCheckBox'):
            self.showOriginCheckBox.stateChanged.connect(self._toggle_show_origin)
        # Connections for scale_m_per_px_input, scale_px_per_m_input, scale_reset_button,
        # scale_display_meters_checkbox, and showScaleBarCheckBox are now in ScalePanelController

        if hasattr(self, 'videoInfoAction'):
            self.videoInfoAction.triggered.connect(self._show_video_info_dialog)
        if hasattr(self, 'preferencesAction'):
            self.preferencesAction.triggered.connect(self._show_preferences_dialog)

        if hasattr(self, 'newTrackAction'):
            self.newTrackAction.setShortcut(QtGui.QKeySequence.StandardKey.New)
            self.newTrackAction.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            self.newTrackAction.triggered.connect(self._create_new_track)
        else:
             logger.warning("newTrackAction not found after UI setup. Ctrl+N shortcut not enabled.")

        self._update_ui_state()
        self._update_tracks_table()
        self._update_points_table()
        self._update_coordinate_ui_display() # Call this before scale panel controller update
        if self.scale_panel_controller:
            self.scale_panel_controller.update_ui_from_manager() # Initial update for scale panel
        
        logger.info("MainWindow initialization complete.")

    def _setup_pens(self) -> None:
        """
        Creates and configures QPen objects for drawing using current settings
        from SettingsManager. Also updates dynamic size values (marker/origin).
        """
        logger.debug("Setting up QPen objects using current settings...")

        # --- Retrieve Colors from Settings ---
        # Provide defaults from settings_manager itself as fallbacks
        color_active_marker = settings_manager.get_setting(settings_manager.KEY_ACTIVE_MARKER_COLOR)
        color_active_line = settings_manager.get_setting(settings_manager.KEY_ACTIVE_LINE_COLOR)
        color_active_current_marker = settings_manager.get_setting(settings_manager.KEY_ACTIVE_CURRENT_MARKER_COLOR)
        color_inactive_marker = settings_manager.get_setting(settings_manager.KEY_INACTIVE_MARKER_COLOR)
        color_inactive_line = settings_manager.get_setting(settings_manager.KEY_INACTIVE_LINE_COLOR)
        color_inactive_current_marker = settings_manager.get_setting(settings_manager.KEY_INACTIVE_CURRENT_MARKER_COLOR)
        color_origin_marker = settings_manager.get_setting(settings_manager.KEY_ORIGIN_MARKER_COLOR)

        # --- Retrieve Sizes/Widths from Settings ---
        try:
            line_width = float(settings_manager.get_setting(settings_manager.KEY_LINE_WIDTH))
            # Marker pen width is kept thin for clarity, not user-configurable currently.
            marker_pen_width = 1.0
            # Origin marker pen width uses default from config for now.
            origin_pen_width = config.DEFAULT_ORIGIN_MARKER_PEN_WIDTH
        except (TypeError, ValueError):
             logger.warning("Invalid size/width setting found, using defaults.")
             line_width = settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_LINE_WIDTH]
             marker_pen_width = 1.0
             origin_pen_width = config.DEFAULT_ORIGIN_MARKER_PEN_WIDTH

        # --- Helper to Create Pens (Handles Invalid Colors) ---
        def _create_pen(color_val: Any, width: float, default_color: QtGui.QColor) -> QtGui.QPen:
            """Creates a cosmetic QPen, falling back to default_color if color_val is invalid."""
            color = color_val if isinstance(color_val, QtGui.QColor) else QtGui.QColor(str(color_val))
            if not color.isValid():
                logger.warning(f"Invalid color '{color_val}' retrieved, using default {default_color.name()}.")
                color = default_color
            pen = QtGui.QPen(color, width)
            pen.setCosmetic(True) # Ensures consistent width regardless of zoom
            return pen

        # --- Create Pens for Drawing ---
        self.pen_marker_active_current = _create_pen(color_active_current_marker, marker_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ACTIVE_CURRENT_MARKER_COLOR])
        self.pen_marker_active_other = _create_pen(color_active_marker, marker_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ACTIVE_MARKER_COLOR])
        self.pen_line_active = _create_pen(color_active_line, line_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ACTIVE_LINE_COLOR])
        self.pen_marker_inactive_current = _create_pen(color_inactive_current_marker, marker_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_INACTIVE_CURRENT_MARKER_COLOR])
        self.pen_marker_inactive_other = _create_pen(color_inactive_marker, marker_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_INACTIVE_MARKER_COLOR])
        self.pen_line_inactive = _create_pen(color_inactive_line, line_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_INACTIVE_LINE_COLOR])
        self.pen_origin_marker = _create_pen(color_origin_marker, origin_pen_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ORIGIN_MARKER_COLOR])
        logger.debug("QPen setup complete using settings.")

    def _reset_ui_after_video_close(self) -> None:
        """Resets UI elements to their state when no video is loaded."""
        logger.debug("Resetting UI elements for no video loaded state.")
        if hasattr(self, 'statusBar'): self.statusBar.clearMessage()
        if hasattr(self, 'frameLabel'): self.frameLabel.setText("Frame: - / -")
        if hasattr(self, 'timeLabel'): self.timeLabel.setText("Time: --:--.--- / --:--.---")
        if hasattr(self, 'fpsLabel'): self.fpsLabel.setText("FPS: ---.--")
        if hasattr(self, 'filenameLabel'):
             self.filenameLabel.setText("File: -")
             self.filenameLabel.setToolTip("No video loaded")
        if hasattr(self, 'frameSlider'):
            self.frameSlider.blockSignals(True)
            self.frameSlider.setValue(0)
            self.frameSlider.setMaximum(0)
            self.frameSlider.blockSignals(False)
        if hasattr(self, 'imageView'):
            self.imageView.clearOverlay()
            self.imageView.setPixmap(QtGui.QPixmap())
            self.imageView.resetInitialLoadFlag()
            self.imageView.set_scale_bar_visibility(False) # Ensure scale bar is hidden

        if hasattr(self, 'coord_transformer'):
            self.coord_transformer = CoordinateTransformer()
        self._is_setting_origin = False
        self._show_origin_marker = True
        if hasattr(self, 'showOriginCheckBox'):
            self.showOriginCheckBox.setChecked(True)

        placeholder = "(--, --)"
        if hasattr(self, 'cursorPosLabelTL'): self.cursorPosLabelTL.setText(placeholder)
        if hasattr(self, 'cursorPosLabelBL'): self.cursorPosLabelBL.setText(placeholder)
        if hasattr(self, 'cursorPosLabelCustom'): self.cursorPosLabelCustom.setText(placeholder)
        if hasattr(self, 'cursorPosLabelTL_m'): self.cursorPosLabelTL_m.setText(placeholder)
        if hasattr(self, 'cursorPosLabelBL_m'): self.cursorPosLabelBL_m.setText(placeholder)
        if hasattr(self, 'cursorPosLabelCustom_m'): self.cursorPosLabelCustom_m.setText(placeholder)

        self.scale_manager.reset() # Reset scale manager state
        
        # Update controller about video loaded status (which will trigger its UI update)
        if self.scale_panel_controller:
            self.scale_panel_controller.set_video_loaded_status(False)
        
        self._update_coordinate_ui_display() # Call this after resetting coord_transformer
        self._update_ui_state() # This will also inform controllers if necessary

    def _update_ui_state(self) -> None:
        """Updates the enabled/disabled state and appearance of UI elements based on application state."""
        is_video_loaded: bool = self.video_loaded

        if hasattr(self, 'frameSlider'): self.frameSlider.setEnabled(is_video_loaded)
        if hasattr(self, 'prevFrameButton'): self.prevFrameButton.setEnabled(is_video_loaded)
        if hasattr(self, 'nextFrameButton'): self.nextFrameButton.setEnabled(is_video_loaded)
        if hasattr(self, 'newTrackAction'): self.newTrackAction.setEnabled(is_video_loaded)
        if hasattr(self, 'autoAdvanceCheckBox'): self.autoAdvanceCheckBox.setEnabled(is_video_loaded)
        if hasattr(self, 'autoAdvanceSpinBox'): self.autoAdvanceSpinBox.setEnabled(is_video_loaded)

        can_play: bool = is_video_loaded and self.fps > 0
        if hasattr(self, 'playPauseButton'): self.playPauseButton.setEnabled(can_play)

        if hasattr(self, 'playPauseButton') and hasattr(self, 'stop_icon') and hasattr(self, 'play_icon'):
            self.playPauseButton.setIcon(self.stop_icon if self.is_playing else self.play_icon)
            self.playPauseButton.setToolTip("Stop Video (Space)" if self.is_playing else "Play Video (Space)")

        if hasattr(self, 'loadTracksAction'): self.loadTracksAction.setEnabled(is_video_loaded)
        can_save: bool = is_video_loaded and hasattr(self, 'track_manager') and len(self.track_manager.tracks) > 0
        if hasattr(self, 'saveTracksAction'): self.saveTracksAction.setEnabled(can_save)
        if hasattr(self, 'videoInfoAction'): self.videoInfoAction.setEnabled(is_video_loaded)

        if hasattr(self, 'coordTopLeftRadio'): self.coordTopLeftRadio.setEnabled(is_video_loaded)
        if hasattr(self, 'coordBottomLeftRadio'): self.coordBottomLeftRadio.setEnabled(is_video_loaded)
        if hasattr(self, 'coordCustomRadio'): self.coordCustomRadio.setEnabled(is_video_loaded)
        if hasattr(self, 'setOriginButton'): self.setOriginButton.setEnabled(is_video_loaded)
        if hasattr(self, 'showOriginCheckBox'): self.showOriginCheckBox.setEnabled(is_video_loaded)

        # Inform ScalePanelController about the video loaded state.
        # Its update_ui_from_manager method (called by set_video_loaded_status if state changed)
        # will handle the detailed enabling/disabling of its managed widgets.
        if self.scale_panel_controller:
            self.scale_panel_controller.set_video_loaded_status(is_video_loaded)

    def _update_ui_for_frame(self, frame_index: int) -> None:
        """Updates UI elements displaying current frame number and time."""
        if not self.video_loaded: return

        # Update slider position (block signals to avoid loop)
        if hasattr(self, 'frameSlider'):
            self.frameSlider.blockSignals(True)
            self.frameSlider.setValue(frame_index)
            self.frameSlider.blockSignals(False)

        # Update frame label
        if hasattr(self, 'frameLabel'):
            self.frameLabel.setText(f"Frame: {frame_index + 1} / {self.total_frames}")

        # Update time label
        if hasattr(self, 'timeLabel'):
            if self.fps > 0 and self.total_duration_ms >= 0:
                current_ms = (frame_index / self.fps) * 1000
                current_t_str = self._format_time(current_ms)
                total_t_str = self._format_time(self.total_duration_ms)
                self.timeLabel.setText(f"Time: {current_t_str} / {total_t_str}")
            else:
                self.timeLabel.setText("Time: --:--.--- / --:--.---") # Fallback if FPS invalid


    # --- File Menu Action Slots ---

    @QtCore.Slot()
    def open_video(self) -> None:
        """Handles the File -> Open Video action."""
        logger.info("Open Video action triggered.")
        # If a video is already loaded, release it first to ensure clean state
        if self.video_loaded:
            logger.info("Releasing previously loaded video before opening new one.")
            self._release_video()

        # Open file dialog
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Video File", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)"
        )
        if not file_path:
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Video loading cancelled.", 3000)
            logger.info("Video loading cancelled by user.")
            return

        # Request VideoHandler to load the file
        logger.info(f"Requesting VideoHandler to load: {file_path}")
        if hasattr(self, 'statusBar'): self.statusBar.showMessage(f"Opening video: {os.path.basename(file_path)}...", 0)
        QtWidgets.QApplication.processEvents() # Ensure message updates immediately
        # VideoHandler will emit videoLoaded or videoLoadFailed signal upon completion
        self.video_handler.open_video(file_path)

    def _release_video(self) -> None:
        """Releases video resources via VideoHandler and resets related state and UI."""
        logger.info("Releasing video resources and resetting state...")
        if hasattr(self, 'video_handler'):
            self.video_handler.release_video()

        # Clear internal UI state related to tracks
        self._clear_visibility_button_groups()

        # Reset MainWindow's video state variables
        self.video_loaded = False
        self.total_frames = 0
        self.current_frame_index = -1
        self.fps = 0.0
        self.total_duration_ms = 0.0
        self.video_filepath = ""
        self.frame_width = 0
        self.frame_height = 0
        self.is_playing = False # Ensure playback state is reset
        logger.debug("MainWindow video state variables reset.")

        # Reset the TrackManager's data
        if hasattr(self, 'track_manager'):
            logger.debug("Resetting TrackManager...")
            self.track_manager.reset()
            logger.debug("TrackManager reset complete.")

        self.scale_manager.reset()
        
        # Reset UI elements to initial state (clears image, labels, tables etc.)
        self._reset_ui_after_video_close()
        logger.info("Video release and associated reset complete.")

    @QtCore.Slot()
    def _trigger_save_tracks(self) -> None:
        if hasattr(self, 'track_manager') and hasattr(self, 'coord_transformer') and hasattr(self, 'scale_manager'): # Added scale_manager check
            file_io.save_tracks_dialog(self, self.track_manager, self.coord_transformer, self.scale_manager) # Pass scale_manager
        else:   
            logger.error("Cannot save tracks: TrackManager or CoordinateTransformer not available.")
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Save Error: Components missing.", 3000)

    @QtCore.Slot()
    def _trigger_load_tracks(self) -> None:
        if hasattr(self, 'track_manager') and hasattr(self, 'coord_transformer') and hasattr(self, 'scale_manager'): # Added scale_manager check
            file_io.load_tracks_dialog(self, self.track_manager, self.coord_transformer, self.scale_manager) # Pass scale_manager
        else:
             logger.error("Cannot load tracks: TrackManager or CoordinateTransformer not available.")
             if hasattr(self, 'statusBar'): self.statusBar.showMessage("Load Error: Components missing.", 3000)


    # --- Preferences Dialog Slots ---
    @QtCore.Slot()
    def _show_preferences_dialog(self) -> None:
        """Shows the preferences dialog."""
        logger.debug("Showing Preferences dialog.")
        dialog = PreferencesDialog(self) # Parent to main window
        # Connect the dialog's applied signal to update visuals immediately if Apply is clicked
        dialog.settingsApplied.connect(self._handle_settings_applied)
        dialog.exec() # Show modal dialog (blocks until closed)
        # Note: If user clicks OK, accept() applies settings and emits settingsApplied too.

    @QtCore.Slot()
    def _handle_settings_applied(self) -> None:
        """Updates the application visuals after settings have been applied/saved."""
        logger.info("Settings applied in preferences dialog. Updating visuals.")
        # Re-create pens based on the newly saved settings
        self._setup_pens()
        # Trigger a redraw of the overlay to use the new pens/sizes
        self._redraw_scene_overlay()


    # --- Video Navigation/Playback Slots ---

    @QtCore.Slot(int)
    def _slider_value_changed(self, value: int) -> None:
        """Handles the frame slider's valueChanged signal (user interaction)."""
        # Only seek if the value actually changed and video is loaded
        if self.video_loaded and self.current_frame_index != value:
            logger.debug(f"Slider value changed to {value}, requesting seek via VideoHandler.")
            self.video_handler.seek_frame(value)

    @QtCore.Slot(int)
    def _handle_frame_step(self, step: int) -> None:
        """Handles the frameStepRequested signal from the image view (mouse wheel)."""
        if not self.video_loaded: return
        logger.debug(f"Frame step requested: {step}. Delegating to VideoHandler.")
        # Delegate to VideoHandler's next/previous frame methods
        if step > 0: # Step = +1 (Scroll Down) -> Next Frame
            self.video_handler.next_frame()
        elif step < 0: # Step = -1 (Scroll Up) -> Previous Frame
            self.video_handler.previous_frame()

    @QtCore.Slot()
    def _show_previous_frame(self) -> None:
        """Handles the 'Previous Frame' button click."""
        if self.video_loaded:
            logger.debug("Previous frame button clicked. Delegating to VideoHandler.")
            self.video_handler.previous_frame()

    @QtCore.Slot()
    def _show_next_frame(self) -> None:
        """Handles the 'Next Frame' button click."""
        if self.video_loaded:
            logger.debug("Next frame button clicked. Delegating to VideoHandler.")
            self.video_handler.next_frame()

    @QtCore.Slot()
    def _toggle_playback(self) -> None:
        """Handles the Play/Pause button click or Spacebar press."""
        if not self.video_loaded or self.fps <= 0: return # Cannot play without video/valid FPS
        logger.debug("Play/Pause button toggled. Delegating to VideoHandler.")
        self.video_handler.toggle_playback()


    # --- VideoHandler Signal Handler Slots ---

    @QtCore.Slot(dict)
    def _handle_video_loaded(self, video_info: Dict[str, Any]) -> None:
        """Handles the successful loading of a video."""
        logger.info(f"Received videoLoaded signal: {video_info.get('filename', 'N/A')}")
        self.total_frames = video_info.get('total_frames', 0)
        self.video_loaded = True
        self.fps = video_info.get('fps', 0.0)
        self.total_duration_ms = video_info.get('duration_ms', 0.0)
        self.video_filepath = video_info.get('filepath', '')
        self.frame_width = video_info.get('width', 0)
        self.frame_height = video_info.get('height', 0)
        self.is_playing = False

        if hasattr(self, 'coord_transformer'):
            self.coord_transformer.set_video_height(self.frame_height)

        filename = video_info.get('filename', 'N/A')
        filepath = video_info.get('filepath', '')
        if hasattr(self, 'filenameLabel'):
            self.filenameLabel.setText(f"File: {filename}")
            self.filenameLabel.setToolTip(filepath)
        if hasattr(self, 'fpsLabel'):
            fps_str = f"{self.fps:.2f}" if self.fps > 0 else "N/A"
            self.fpsLabel.setText(f"FPS: {fps_str}")

        logger.debug("Resetting TrackManager for new video.")
        if hasattr(self, 'track_manager'): self.track_manager.reset()

        logger.debug("Updating UI controls for loaded video...")
        if hasattr(self, 'frameSlider'):
            self.frameSlider.setMaximum(self.total_frames - 1 if self.total_frames > 0 else 0)
            self.frameSlider.setValue(0)

        if hasattr(self, 'imageView'): self.imageView.resetInitialLoadFlag()
        
        self.scale_manager.reset() # Reset scale manager for new video

        # Update ScalePanelController about video loaded status
        if self.scale_panel_controller:
            self.scale_panel_controller.set_video_loaded_status(True)
            # The controller will update its UI via update_ui_from_manager,
            # which can be called internally by set_video_loaded_status or explicitly if needed.

        self._update_ui_state() # General UI state update
        self._update_coordinate_ui_display() # Update coordinate specific UI

        status_msg = (f"Loaded '{filename}' ({self.total_frames} frames, "
                      f"{self.frame_width}x{self.frame_height}, {self.fps:.2f} FPS)")
        if hasattr(self, 'statusBar'): self.statusBar.showMessage(status_msg, 5000)
        logger.info(f"Video loaded successfully handled: {status_msg}")

    @QtCore.Slot(str)
    def _handle_video_load_failed(self, error_msg: str) -> None:
        """Handles the failure to load a video."""
        logger.error(f"Received videoLoadFailed signal: {error_msg}")
        QtWidgets.QMessageBox.critical(self, "Video Load Error", error_msg)
        if hasattr(self, 'statusBar'): self.statusBar.showMessage(f"Error loading video", 5000)
        # Ensure resources are released and UI is reset
        self._release_video()

    @QtCore.Slot(QtGui.QPixmap, int)
    def _handle_frame_changed(self, pixmap: QtGui.QPixmap, frame_index: int) -> None:
        """Handles the signal indicating a new frame is ready from VideoHandler."""
        logger.debug(f"Received frameChanged signal for frame index {frame_index}.")
        if not self.video_loaded:
            logger.warning("frameChanged received but video not marked as loaded. Ignoring.")
            return

        self.current_frame_index = frame_index
        # Display the new pixmap
        if hasattr(self, 'imageView'):
            self.imageView.setPixmap(pixmap)
        # Update UI elements (slider, labels)
        self._update_ui_for_frame(frame_index)
        # Redraw track overlays for the new frame
        self._redraw_scene_overlay()
        if hasattr(self, 'imageView') and hasattr(self, 'scale_manager') and \
           hasattr(self, 'showScaleBarCheckBox') and self.showScaleBarCheckBox.isChecked():
            current_m_per_px = self.scale_manager.get_scale_m_per_px()
            if current_m_per_px is not None:
                self.imageView.update_scale_bar_dimensions(current_m_per_px)


    @QtCore.Slot(bool)
    def _handle_playback_state_changed(self, is_playing: bool) -> None:
        """Handles the signal indicating playback has started or stopped."""
        logger.info(f"Received playbackStateChanged signal: is_playing={is_playing}")
        self.is_playing = is_playing

        # Update play/pause button appearance and status bar message
        if hasattr(self, 'playPauseButton') and hasattr(self, 'stop_icon') and hasattr(self, 'play_icon'):
            if self.is_playing:
                self.playPauseButton.setIcon(self.stop_icon)
                self.playPauseButton.setToolTip("Stop Video (Space)")
                if hasattr(self, 'statusBar'): self.statusBar.showMessage("Playing...", 0) # Persistent
            else:
                self.playPauseButton.setIcon(self.play_icon)
                self.playPauseButton.setToolTip("Play Video (Space)")
                if hasattr(self, 'statusBar'):
                    status = "Stopped." if self.video_loaded else "Ready."
                    self.statusBar.showMessage(status, 3000)
        # Update overall UI enabled states if necessary
        self._update_ui_state()


    # --- ImageView Signal Handler Slots ---

    @QtCore.Slot(float, float)
    def _handle_add_point_click(self, x: float, y: float) -> None:
        """Handles a standard (unmodified) click in the image view to add/update a point."""
        # Ignore clicks if currently in the 'Set Origin' mode
        if self._is_setting_origin:
            logger.debug("Standard click ignored while in 'Set Custom Origin' mode.")
            return

        if not self.video_loaded:
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Cannot add point: No video loaded.", 3000)
            return
        if not hasattr(self, 'imageView') or not self.imageView._scene: return

        logger.debug(f"ImageView standard click at scene coordinates ({x:.3f}, {y:.3f}) for adding point.")

        # --- Add/Update Point Logic ---
        if not hasattr(self, 'track_manager') or self.track_manager.active_track_index == -1:
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Cannot add point: No track selected.", 3000)
            return

        # Calculate time_ms for the point
        time_ms: float = (self.current_frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
        # Tell TrackManager to add/update the point (uses internal TL coords)
        success: bool = self.track_manager.add_point(self.current_frame_index, time_ms, x, y)

        if success:
            active_track_id = self.track_manager.get_active_track_id()
            # Display coordinates in current system for user feedback
            x_disp, y_disp = self.coord_transformer.transform_point_for_display(x, y)
            message = (f"Point for Track {active_track_id} on Frame {self.current_frame_index + 1}: "
                       f"({x_disp:.1f}, {y_disp:.1f})")
            if hasattr(self, 'statusBar'): self.statusBar.showMessage(message, 3000)
            logger.info(message)

            # --- Auto-Advance Logic ---
            if self._auto_advance_enabled and self._auto_advance_frames > 0:
                target_frame = self.current_frame_index + self._auto_advance_frames
                target_frame = min(target_frame, self.total_frames - 1) # Clamp to end
                if target_frame > self.current_frame_index:
                    logger.info(f"Auto-advancing by {self._auto_advance_frames} frame(s) to frame {target_frame + 1}")
                    self.video_handler.seek_frame(target_frame)
                else:
                    logger.debug(f"Auto-advance skipped: Already at or past target frame {target_frame + 1}.")
        else:
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Failed to add point (see log).", 3000)
        # Note: TrackManager signals trigger table/visual updates.

    @QtCore.Slot(float, float, QtCore.Qt.KeyboardModifiers)
    def _handle_modified_click(self, x: float, y: float, modifiers: QtCore.Qt.KeyboardModifiers) -> None:
        """Handles modified clicks (Ctrl+Click, Shift+Click) from the image view."""
        if not self.video_loaded or not hasattr(self, 'track_manager') or not hasattr(self, 'video_handler'):
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Cannot interact: Video/components not ready.", 3000)
            return

        logger.debug(f"ImageView modified click at ({x:.2f}, {y:.2f}) with modifiers: {modifiers}")

        # Find the specific track point clicked on (if any)
        result = self.track_manager.find_closest_visible_point(x, y, self.current_frame_index)

        if result is None:
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("No track marker found near click.", 3000)
            return

        found_track_index, point_data = result
        found_track_id = found_track_index + 1
        clicked_frame_index = point_data[0] # Frame index of the clicked marker

        # --- Ctrl+Click Logic: Select Track ---
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            logger.info(f"Ctrl+Click: Selecting Track {found_track_id}")
            if self.track_manager.active_track_index != found_track_index:
                self.track_manager.set_active_track(found_track_index)
            # Update table selection (deferred)
            QtCore.QTimer.singleShot(0, lambda: self._select_track_row_by_id(found_track_id))
            if hasattr(self, 'statusBar'): self.statusBar.showMessage(f"Selected Track {found_track_id}.", 3000)

        # --- Shift+Click Logic: Select Track and Jump to Frame ---
        elif modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:
            logger.info(f"Shift+Click: Selecting Track {found_track_id}, jumping to Frame {clicked_frame_index + 1}")
            if self.track_manager.active_track_index != found_track_index:
                self.track_manager.set_active_track(found_track_index)
            # Update table selection (deferred)
            QtCore.QTimer.singleShot(0, lambda: self._select_track_row_by_id(found_track_id))
            # Seek to the frame of the clicked marker
            if self.current_frame_index != clicked_frame_index:
                self.video_handler.seek_frame(clicked_frame_index)
            if hasattr(self, 'statusBar'): self.statusBar.showMessage(f"Selected Track {found_track_id}, jumped to Frame {clicked_frame_index + 1}.", 3000)

        else:
            logger.debug(f"Ignoring modified click with unhandled modifier combination: {modifiers}")


    # --- Auto-Advance UI Slots ---

    @QtCore.Slot(int)
    def _handle_auto_advance_toggled(self, state: int) -> None:
        """Updates the auto-advance state when the checkbox is toggled."""
        self._auto_advance_enabled = (state == QtCore.Qt.CheckState.Checked.value)
        logger.info(f"Auto-advance {'enabled' if self._auto_advance_enabled else 'disabled'}.")

    @QtCore.Slot(int)
    def _handle_auto_advance_frames_changed(self, value: int) -> None:
        """Updates the auto-advance frame count when the spinbox value changes."""
        self._auto_advance_frames = value
        logger.info(f"Auto-advance frame count set to: {self._auto_advance_frames}")


    # --- Track Management UI Slots ---

    @QtCore.Slot()
    def _create_new_track(self) -> None:
        """Handles the 'New Track' button click or Ctrl+N shortcut."""
        if not self.video_loaded:
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Load a video first to create tracks.", 3000)
            return
        logger.info("Create new track requested.")
        if not hasattr(self, 'track_manager'): return

        new_track_id: int = self.track_manager.create_new_track()
        if hasattr(self, 'statusBar'): self.statusBar.showMessage(f"Created Track {new_track_id}. It is now active.", 3000)
        # Select the new row in the tracks table (deferred for reliability)
        QtCore.QTimer.singleShot(0, lambda: self._select_track_row_by_id(new_track_id))
        # Switch focus to the tracks tab
        if hasattr(self, 'dataTabsWidget'): self.dataTabsWidget.setCurrentIndex(0)
        self._update_ui_state() # Update save action enabled state

    @QtCore.Slot()
    def _track_selection_changed(self) -> None:
        """Handles selection changes initiated *by the user* in the tracks table."""
        if not hasattr(self, 'tracksTableWidget') or not hasattr(self, 'track_manager'): return

        selected_items = self.tracksTableWidget.selectedItems()
        if not selected_items:
            # Potentially deactivate track if selection is cleared by user interaction
            # self.track_manager.set_active_track(-1)
            return

        selected_row = self.tracksTableWidget.row(selected_items[0])
        id_item = self.tracksTableWidget.item(selected_row, config.COL_TRACK_ID)
        if id_item:
            track_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if track_id is not None and isinstance(track_id, int):
                track_index = track_id - 1
                # Set the active track in the manager *only if it changed*
                if self.track_manager.active_track_index != track_index:
                    logger.debug(f"Tracks table selection changed by user to row {selected_row}, track ID {track_id}.")
                    self.track_manager.set_active_track(track_index)
                    # TrackManager signals will update points table and visuals

    @QtCore.Slot(int, int)
    def _on_tracks_table_cell_clicked(self, row: int, column: int) -> None:
        """Handles clicks on specific cells in the tracks table (e.g., frame links)."""
        if not self.video_loaded or not hasattr(self, 'tracksTableWidget') or not hasattr(self, 'track_manager'): return

        # Check if Start or End Frame column was clicked
        if column == config.COL_TRACK_START_FRAME or column == config.COL_TRACK_END_FRAME:
            item = self.tracksTableWidget.item(row, column)
            id_item = self.tracksTableWidget.item(row, config.COL_TRACK_ID) # Get track ID item
            if item and id_item:
                frame_text = item.text()
                track_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole) # Get stored track ID
                try:
                    target_frame_0based = int(frame_text) - 1 # Display is 1-based
                    # Validate frame index and track ID
                    if 0 <= target_frame_0based < self.total_frames and isinstance(track_id, int):
                        track_index = track_id - 1
                        # Select the track if not already selected
                        if self.track_manager.active_track_index != track_index:
                           self.track_manager.set_active_track(track_index)
                           # Manually update table selection visually without emitting signals
                           self._select_track_row_by_id(track_id)
                        # Seek to the target frame
                        logger.debug(f"Track table frame link clicked: Seeking to frame {target_frame_0based + 1}")
                        self.video_handler.seek_frame(target_frame_0based)
                except (ValueError, TypeError):
                    # Ignore if cell content is not a valid integer (e.g., "N/A")
                    pass

    @QtCore.Slot(int, int)
    def _on_points_table_cell_clicked(self, row: int, column: int) -> None:
        """Handles clicks on specific cells in the points table (e.g., frame links)."""
        if not self.video_loaded or not hasattr(self, 'pointsTableWidget'): return

        # Check if Frame column was clicked
        if column == config.COL_POINT_FRAME:
            item = self.pointsTableWidget.item(row, column)
            if item:
                try:
                    target_frame_0based = int(item.text()) - 1 # Display is 1-based
                    # Validate frame index
                    if 0 <= target_frame_0based < self.total_frames:
                        # Seek to the target frame
                        logger.debug(f"Points table frame link clicked: Seeking to frame {target_frame_0based + 1}")
                        self.video_handler.seek_frame(target_frame_0based)
                        # Reselect the row to give visual feedback (no signal loop expected here)
                        self.pointsTableWidget.selectRow(row)
                except ValueError:
                    # Ignore if cell content is not a valid integer
                    pass


    # --- TrackManager Signal Handler Slots ---

    @QtCore.Slot()
    def _update_tracks_table(self) -> None:
        """
        Updates the tracks table based on data from TrackManager.
        Includes data rows and a final row with a 'New Track' button.
        """
        if not hasattr(self, 'tracksTableWidget') or not hasattr(self, 'track_manager'): return
        logger.debug("Updating tracks table...")

        current_active_id = self.track_manager.get_active_track_id()
        selected_row_to_restore = -1

        self.tracksTableWidget.blockSignals(True) # Prevent selection signals during update
        self._clear_visibility_button_groups() # Disconnect old button groups

        track_summary = self.track_manager.get_track_summary()
        num_data_rows = len(track_summary)
        total_rows = num_data_rows + 1 # Add 1 for the button row
        self.tracksTableWidget.setRowCount(total_rows)

        link_color = QtGui.QColor("blue")
        link_tooltip = "Click to jump to this frame"
        style = self.style() # For standard icons

        # --- Populate Data Rows ---
        for row in range(num_data_rows):
            self.tracksTableWidget.setSpan(row, 0, 1, 1) # Ensure first col span is reset
            summary_data = track_summary[row]
            track_id, num_points, start_frame, end_frame = summary_data
            track_index = track_id - 1

            # Col 0: Delete Button
            delete_button = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon), "")
            delete_button.setToolTip(f"Delete Track {track_id}"); delete_button.setFlat(True); delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            delete_button.setProperty("track_index", track_index) # Store index for lambda
            delete_button.clicked.connect(lambda checked=False, t_idx=track_index: self._on_delete_track_button_clicked(t_idx))
            self.tracksTableWidget.setCellWidget(row, config.COL_DELETE, self._create_centered_cell_widget(delete_button))

            # Col 1: Track ID
            id_item = QtWidgets.QTableWidgetItem(str(track_id))
            id_item.setData(QtCore.Qt.ItemDataRole.UserRole, track_id) # Store ID for retrieval
            id_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.tracksTableWidget.setItem(row, config.COL_TRACK_ID, id_item)

            # Col 2: Points Count
            points_item = QtWidgets.QTableWidgetItem(str(num_points))
            points_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            points_item.setFlags(points_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.tracksTableWidget.setItem(row, config.COL_TRACK_POINTS, points_item)

            # Col 3: Start Frame (1-based)
            start_frame_str = str(start_frame + 1) if start_frame != -1 else "N/A"
            start_item = QtWidgets.QTableWidgetItem(start_frame_str)
            start_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            start_item.setFlags(start_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            if start_frame != -1: start_item.setForeground(link_color); start_item.setToolTip(link_tooltip)
            self.tracksTableWidget.setItem(row, config.COL_TRACK_START_FRAME, start_item)

            # Col 4: End Frame (1-based)
            end_frame_str = str(end_frame + 1) if end_frame != -1 else "N/A"
            end_item = QtWidgets.QTableWidgetItem(end_frame_str)
            end_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            end_item.setFlags(end_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            if end_frame != -1: end_item.setForeground(link_color); end_item.setToolTip(link_tooltip)
            self.tracksTableWidget.setItem(row, config.COL_TRACK_END_FRAME, end_item)

            # Col 5, 6, 7: Visibility Radio Buttons
            current_mode = self.track_manager.get_track_visibility_mode(track_index)
            rb_hidden = QtWidgets.QRadioButton(); rb_incremental = QtWidgets.QRadioButton(); rb_always = QtWidgets.QRadioButton()
            rb_hidden.setProperty("visibility_mode", TrackVisibilityMode.HIDDEN); rb_hidden.setProperty("track_index", track_index)
            rb_incremental.setProperty("visibility_mode", TrackVisibilityMode.INCREMENTAL); rb_incremental.setProperty("track_index", track_index)
            rb_always.setProperty("visibility_mode", TrackVisibilityMode.ALWAYS_VISIBLE); rb_always.setProperty("track_index", track_index)
            button_group = QtWidgets.QButtonGroup(self) # Parent to main window
            button_group.addButton(rb_hidden); button_group.addButton(rb_incremental); button_group.addButton(rb_always)
            button_group.setExclusive(True)
            self.track_visibility_button_groups[track_id] = button_group # Store group
            button_group.blockSignals(True) # Block during programmatic check
            if current_mode == TrackVisibilityMode.HIDDEN: rb_hidden.setChecked(True)
            elif current_mode == TrackVisibilityMode.INCREMENTAL: rb_incremental.setChecked(True)
            else: rb_always.setChecked(True)
            button_group.blockSignals(False) # Unblock
            self.tracksTableWidget.setCellWidget(row, config.COL_VIS_HIDDEN, self._create_centered_cell_widget(rb_hidden))
            self.tracksTableWidget.setCellWidget(row, config.COL_VIS_INCREMENTAL, self._create_centered_cell_widget(rb_incremental))
            self.tracksTableWidget.setCellWidget(row, config.COL_VIS_ALWAYS, self._create_centered_cell_widget(rb_always))
            button_group.buttonToggled.connect(self._on_visibility_changed)

            # Check if this row corresponds to the currently active track
            if track_id == current_active_id:
                selected_row_to_restore = row

        # --- Add the 'New Track' Button Row ---
        # Note: A new button instance is created each time the table updates.
        button_row_index = num_data_rows
        new_track_button_in_table = QtWidgets.QPushButton("New Track")
        new_track_button_in_table.setToolTip("Start a new track for marking points (Ctrl+N)")
        new_track_button_in_table.clicked.connect(self._create_new_track)
        new_track_button_in_table.setEnabled(self.video_loaded) # Enable based on video state
        self.tracksTableWidget.setCellWidget(button_row_index, 0, new_track_button_in_table)
        self.tracksTableWidget.setSpan(button_row_index, 0, 1, config.TOTAL_TRACK_COLUMNS) # Span across all columns
        self.tracksTableWidget.setRowHeight(button_row_index, new_track_button_in_table.sizeHint().height() + 4) # Adjust height

        # Restore selection if an active track existed
        if selected_row_to_restore != -1:
            self.tracksTableWidget.selectRow(selected_row_to_restore)

        self.tracksTableWidget.blockSignals(False) # Re-enable signals

        # Update overall UI state (e.g., save button enablement)
        self._update_ui_state()

    @QtCore.Slot()
    def _on_delete_track_button_clicked(self, track_index: int) -> None:
        """Handles the click signal from a track's delete button."""
        if not hasattr(self, 'track_manager'): return
        track_id = track_index + 1 # 1-based ID for user message
        reply = QtWidgets.QMessageBox.question(self, "Confirm Delete", f"Delete Track {track_id}?",
                                             QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
                                             QtWidgets.QMessageBox.StandardButton.Cancel)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            logger.info(f"User confirmed deletion for track index {track_index} (ID: {track_id}).")
            success = self.track_manager.delete_track(track_index)
            if hasattr(self, 'statusBar'): self.statusBar.showMessage(f"Deleted Track {track_id}" if success else f"Failed to delete Track {track_id}", 3000)
            if not success:
                logger.error(f"TrackManager failed to delete track index {track_index}.")
                QtWidgets.QMessageBox.warning(self, "Delete Error", f"Could not delete track {track_id}.")
            # Note: TrackManager signals trigger table updates.

    @QtCore.Slot(QtWidgets.QAbstractButton, bool)
    def _on_visibility_changed(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        """Handles the buttonToggled signal from visibility radio button groups."""
        if checked and hasattr(self, 'track_manager'): # Only act when checked
            mode = button.property("visibility_mode")
            track_index = button.property("track_index")
            if isinstance(mode, TrackVisibilityMode) and isinstance(track_index, int):
                logger.debug(f"Visibility changed for track index {track_index} to {mode.name}")
                self.track_manager.set_track_visibility_mode(track_index, mode)
                # Note: TrackManager's visualsNeedUpdate signal triggers redraw.

    @QtCore.Slot(int)
    def _on_visibility_header_clicked(self, logical_index: int) -> None:
        """Handles clicks on the visibility column headers to set mode for all tracks."""
        if not hasattr(self, 'track_manager') or not self.track_manager.tracks: return

        target_mode: Optional[TrackVisibilityMode] = None
        if logical_index == config.COL_VIS_HIDDEN: target_mode = TrackVisibilityMode.HIDDEN
        elif logical_index == config.COL_VIS_INCREMENTAL: target_mode = TrackVisibilityMode.INCREMENTAL
        elif logical_index == config.COL_VIS_ALWAYS: target_mode = TrackVisibilityMode.ALWAYS_VISIBLE

        if target_mode:
            logger.info(f"Setting all tracks visibility to {target_mode.name} via header click.")
            self.track_manager.set_all_tracks_visibility(target_mode)
            # Note: TrackManager signals trigger table/visual updates.

    def _clear_visibility_button_groups(self) -> None:
        """Disconnects signals and clears the stored visibility button groups."""
        if not hasattr(self, 'track_visibility_button_groups'): return
        for group in self.track_visibility_button_groups.values():
            try: # Disconnect safely
                group.buttonToggled.disconnect(self._on_visibility_changed)
            except (TypeError, RuntimeError): pass
        self.track_visibility_button_groups.clear()

    def _select_track_row_by_id(self, track_id_to_select: int) -> None:
         """Selects the row in the tracks table corresponding to the given track ID."""
         if not hasattr(self, 'tracksTableWidget'): return
         if track_id_to_select == -1: # Handle case where no track is active
              self.tracksTableWidget.clearSelection()
              return

         # Find row with matching track ID in UserRole data
         found_row = -1
         for row in range(self.tracksTableWidget.rowCount() -1 ): # Exclude button row
              item = self.tracksTableWidget.item(row, config.COL_TRACK_ID)
              if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == track_id_to_select:
                  found_row = row
                  break

         if found_row != -1:
             self.tracksTableWidget.blockSignals(True) # Prevent selection signal loop
             self.tracksTableWidget.selectRow(found_row)
             self.tracksTableWidget.blockSignals(False)
             # Ensure the selected row is visible
             if item: # Ensure item exists before scrolling
                 self.tracksTableWidget.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
         else:
             logger.warning(f"Could not find row for track ID {track_id_to_select} in tracks table.")


    def _create_centered_cell_widget(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Helper to create a container widget to center another widget within a table cell."""
        cell_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(cell_widget)
        layout.addWidget(widget)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0) # No extra margins
        return cell_widget

    @QtCore.Slot()
    def _update_points_table(self) -> None:
        """Updates the points table based on the currently active track."""
        if not all(hasattr(self, attr) for attr in ['pointsTableWidget', 'track_manager', 'pointsTabLabel', 'coord_transformer', 'scale_manager']): # Added scale_manager
             logger.debug("_update_points_table skipped: Essential components not ready.")
             return
        logger.debug("Updating points table...")

        active_track_id = self.track_manager.get_active_track_id()
        self.pointsTabLabel.setText(f"Points for Track: {active_track_id}" if active_track_id != -1 else "Points for Track: -")
        self.pointsTableWidget.setRowCount(0) # Clear existing rows
        active_points = self.track_manager.get_active_track_points_for_table()

        link_color = QtGui.QColor("blue")
        link_tooltip = "Click to jump to this frame"

        # Get current display unit from ScaleManager for headers
        display_unit_short = self.scale_manager.get_display_unit_short()
        x_header_text = f"X [{display_unit_short}]"
        y_header_text = f"Y [{display_unit_short}]"

        pointsHeader = self.pointsTableWidget.horizontalHeader()
        pointsHeader.model().setHeaderData(config.COL_POINT_X, QtCore.Qt.Orientation.Horizontal, x_header_text)
        pointsHeader.model().setHeaderData(config.COL_POINT_Y, QtCore.Qt.Orientation.Horizontal, y_header_text)

        self.pointsTableWidget.setRowCount(len(active_points))
        for row, point_data in enumerate(active_points):
            frame_idx, time_ms, x_internal_px, y_internal_px = point_data

            frame_item = QtWidgets.QTableWidgetItem(str(frame_idx + 1))
            frame_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            frame_item.setForeground(link_color); frame_item.setToolTip(link_tooltip)
            frame_item.setFlags(frame_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.pointsTableWidget.setItem(row, config.COL_POINT_FRAME, frame_item)

            time_sec_str = f"{(time_ms / 1000.0):.3f}" if time_ms >= 0 else "--.---"
            time_item = QtWidgets.QTableWidgetItem(time_sec_str)
            time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            time_item.setFlags(time_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.pointsTableWidget.setItem(row, config.COL_POINT_TIME, time_item)

            # 1. Transform for coordinate system (origin, Y-axis) - result is still in pixels
            x_coord_sys_px, y_coord_sys_px = self.coord_transformer.transform_point_for_display(x_internal_px, y_internal_px)

            # 2. Transform for scale (pixels to meters if applicable) using ScaleManager
            x_display, y_display, _ = self.scale_manager.get_transformed_coordinates_for_display(x_coord_sys_px, y_coord_sys_px)

            # Use the precision from ScaleManager's transformation
            x_item = QtWidgets.QTableWidgetItem(f"{x_display}") 
            x_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            x_item.setFlags(x_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.pointsTableWidget.setItem(row, config.COL_POINT_X, x_item)

            y_item = QtWidgets.QTableWidgetItem(f"{y_display}")
            y_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            y_item.setFlags(y_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.pointsTableWidget.setItem(row, config.COL_POINT_Y, y_item)

    # --- Drawing ---

    @QtCore.Slot()
    def _redraw_scene_overlay(self) -> None:
        """Clears and redraws all track markers/lines and origin marker on the image view."""
        if not all(hasattr(self, attr) for attr in ['imageView', 'track_manager', 'coord_transformer']) or \
           not self.imageView or not self.imageView._scene:
             logger.debug("_redraw_scene_overlay skipped: Components not ready.")
             return
        if not self.video_loaded or self.current_frame_index < 0:
             if hasattr(self, 'imageView'): self.imageView.clearOverlay()
             logger.debug("_redraw_scene_overlay skipped: No video loaded or invalid frame.")
             return

        logger.debug(f"Redrawing scene overlay for frame {self.current_frame_index}")
        scene = self.imageView._scene
        self.imageView.clearOverlay() # Clear previous overlay items

        try:
            # --- Get current sizes from settings ---
            # Retrieve marker/origin sizes dynamically for drawing
            try: track_marker_size = float(settings_manager.get_setting(settings_manager.KEY_MARKER_SIZE))
            except (ValueError, TypeError): track_marker_size = settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_MARKER_SIZE]
            try: origin_marker_size = float(settings_manager.get_setting(settings_manager.KEY_ORIGIN_MARKER_SIZE))
            except (ValueError, TypeError): origin_marker_size = settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_ORIGIN_MARKER_SIZE]

            # Get visual elements (markers, lines) from TrackManager for the current frame
            visual_elements: List[VisualElement] = self.track_manager.get_visual_elements(self.current_frame_index)

            # Map style identifiers to pre-configured QPen objects (using self.pen_*)
            pen_map: Dict[str, QtGui.QPen] = {
                config.STYLE_MARKER_ACTIVE_CURRENT: self.pen_marker_active_current,
                config.STYLE_MARKER_ACTIVE_OTHER: self.pen_marker_active_other,
                config.STYLE_MARKER_INACTIVE_CURRENT: self.pen_marker_inactive_current,
                config.STYLE_MARKER_INACTIVE_OTHER: self.pen_marker_inactive_other,
                config.STYLE_LINE_ACTIVE: self.pen_line_active,
                config.STYLE_LINE_INACTIVE: self.pen_line_inactive,
            }

            # Create QGraphicsItems for each visual element
            for element in visual_elements:
                pen = pen_map.get(element.get('style'))
                if not pen: continue # Skip if style unknown

                # Draw Markers (crosses using the retrieved size)
                if element.get('type') == 'marker' and element.get('pos'):
                    x, y = element['pos']; r = track_marker_size / 2.0
                    path = QtGui.QPainterPath()
                    path.moveTo(x - r, y); path.lineTo(x + r, y)
                    path.moveTo(x, y - r); path.lineTo(x, y + r)
                    item = QtWidgets.QGraphicsPathItem(path)
                    item.setPen(pen)
                    item.setZValue(10) # Ensure markers are above lines
                    scene.addItem(item)

                # Draw Lines
                elif element.get('type') == 'line' and element.get('p1') and element.get('p2'):
                    p1, p2 = element['p1'], element['p2']
                    item = QtWidgets.QGraphicsLineItem(p1[0], p1[1], p2[0], p2[1])
                    item.setPen(pen)
                    item.setZValue(9) # Draw lines below markers
                    scene.addItem(item)

            # Draw Origin Marker if enabled
            if self._show_origin_marker:
                origin_x_tl, origin_y_tl = self.coord_transformer.get_current_origin_tl()
                radius = origin_marker_size / 2.0 # Use retrieved size
                origin_item = QtWidgets.QGraphicsEllipseItem(
                    origin_x_tl - radius, origin_y_tl - radius, # top-left x, y
                    origin_marker_size, origin_marker_size # width, height
                )
                origin_item.setPen(self.pen_origin_marker)
                # Fill the origin marker with its pen color for visibility
                origin_item.setBrush(QtGui.QBrush(self.pen_origin_marker.color()))
                origin_item.setZValue(11) # Ensure origin is above tracks
                scene.addItem(origin_item)
                logger.debug(f"Drew origin marker at TL: ({origin_x_tl:.1f}, {origin_y_tl:.1f}) with size {origin_marker_size}")

            # Explicitly request the viewport to repaint (might not be strictly necessary but ensures update)
            if self.imageView and self.imageView.viewport():
                self.imageView.viewport().update()

        except Exception as e:
            # Log any errors during drawing and clear overlay to avoid partial state
            logger.exception(f"Error during _redraw_scene_overlay: {e}")
            if hasattr(self, 'imageView'): self.imageView.clearOverlay()


    # --- Event Handlers ---

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handles key presses for shortcuts like Space (play/pause) and Delete/Backspace (delete point)."""
        key = event.key()
        accepted = False # Flag to check if we handled the key press

        # Spacebar: Toggle playback
        if key == QtCore.Qt.Key.Key_Space:
            if self.video_loaded and hasattr(self, 'playPauseButton') and self.playPauseButton.isEnabled():
                self._toggle_playback()
                accepted = True

        # Delete or Backspace: Delete point for active track on current frame
        elif key == QtCore.Qt.Key.Key_Delete or key == QtCore.Qt.Key.Key_Backspace:
            if (self.video_loaded and hasattr(self, 'track_manager') and
                self.track_manager.active_track_index != -1 and self.current_frame_index != -1):

                active_track_index = self.track_manager.active_track_index
                target_frame_index = self.current_frame_index
                logger.info(f"Delete/Backspace key pressed. Attempting to delete point for track index {active_track_index} on frame {target_frame_index}")
                deleted = self.track_manager.delete_point(active_track_index, target_frame_index)
                if hasattr(self, 'statusBar'):
                    status_msg = (f"Deleted point from Track {active_track_index+1} on Frame {target_frame_index+1}"
                                  if deleted else "No point found to delete on this frame for the active track.")
                    self.statusBar.showMessage(status_msg, 3000)
                accepted = True # Indicate we handled the key, even if no point was deleted
            elif hasattr(self, 'statusBar'):
                 # Cannot delete (e.g., no active track)
                self.statusBar.showMessage("Cannot delete point (no active track or invalid frame?).", 3000)
                # Do not set accepted = True, let base class handle if needed (e.g., in a text box)

        # If we handled the key press, accept the event
        if accepted:
            event.accept()
        else:
            # Otherwise, pass the event to the base class implementation
            super().keyPressEvent(event)


    # --- Coordinate System Slots ---

    @QtCore.Slot(QtWidgets.QAbstractButton, bool)
    def _coordinate_mode_changed(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        """Handles changes in the coordinate system radio buttons."""
        if not checked or not hasattr(self, 'coord_transformer'):
             return # Only react when a button is checked

        new_mode = CoordinateSystem.TOP_LEFT # Default assumption
        if button == self.coordBottomLeftRadio: new_mode = CoordinateSystem.BOTTOM_LEFT
        elif button == self.coordCustomRadio: new_mode = CoordinateSystem.CUSTOM

        if self.coord_transformer.mode != new_mode:
            self.coord_transformer.set_mode(new_mode)
            logger.info(f"Coordinate system mode changed to: {new_mode.name}")
            # Update UI labels, points table, and visuals
            self._update_coordinate_ui_display() # Updates radio buttons & labels
            self._update_points_table()          # Updates displayed coordinates
            if self._show_origin_marker:         # Redraw if origin marker is visible
                 self._redraw_scene_overlay()
        # Ensure general UI state (button enablements) is correct
        self._update_ui_state()

    @QtCore.Slot()
    def _enter_set_origin_mode(self) -> None:
        """Enters the mode where the next click sets the custom origin."""
        if not self.video_loaded:
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Load a video first to set origin.", 3000)
            return
        self._is_setting_origin = True
        if hasattr(self, 'imageView'):
            self.imageView.set_interaction_mode(InteractionMode.SET_ORIGIN)
        if hasattr(self, 'statusBar'): self.statusBar.showMessage("Click on the image to set the custom origin.", 0) # Persistent message
        logger.info("Entered 'Set Custom Origin' mode.")

    @QtCore.Slot(float, float)
    def _set_custom_origin(self, scene_x: float, scene_y: float) -> None:
        """Sets the custom origin based on a click signal from the image view."""
        if not hasattr(self, 'coord_transformer') or not hasattr(self, 'imageView'): return

        # Exit the setting mode and revert cursor/interaction
        self._is_setting_origin = False
        self.imageView.set_interaction_mode(InteractionMode.NORMAL)

        # Update the transformer (this automatically sets mode to CUSTOM)
        self.coord_transformer.set_custom_origin(scene_x, scene_y)

        # Update UI (Labels, radio button check)
        self._update_coordinate_ui_display()

        # Update points table display and redraw overlay
        self._update_points_table()
        self._redraw_scene_overlay() # Redraw needed to show new origin position if visible

        # Update status bar
        origin_meta = self.coord_transformer.get_metadata()
        cust_x = origin_meta.get('origin_x_tl', 0.0)
        cust_y = origin_meta.get('origin_y_tl', 0.0)
        if hasattr(self, 'statusBar'): self.statusBar.showMessage(f"Custom origin set at (TL): ({cust_x:.1f}, {cust_y:.1f})", 5000)
        logger.info(f"Custom origin set via click at scene coordinates ({scene_x:.1f}, {scene_y:.1f})")

    @QtCore.Slot(int)
    def _toggle_show_origin(self, state: int) -> None:
        """Toggles the visibility of the origin marker based on checkbox state."""
        self._show_origin_marker = (state == QtCore.Qt.CheckState.Checked.value)
        logger.info(f"Origin marker visibility set to: {self._show_origin_marker}")
        # Trigger redraw to show/hide the marker
        self._redraw_scene_overlay()


    # --- UI Update Helpers ---

    def _update_coordinate_ui_display(self) -> None:
        """Updates the coordinate system radio buttons, origin labels, and checkbox state."""
        required_attrs = [
            'coord_transformer', 'coordSystemGroup', 'coordTopLeftRadio',
            'coordBottomLeftRadio', 'coordCustomRadio', 'coordTopLeftOriginLabel',
            'coordBottomLeftOriginLabel', 'coordCustomOriginLabel',
            'showOriginCheckBox'
        ]
        if not all(hasattr(self, attr) for attr in required_attrs):
            logger.warning("_update_coordinate_ui_display skipped: UI elements or transformer not ready.")
            return

        current_mode = self.coord_transformer.mode
        origin_meta = self.coord_transformer.get_metadata()
        video_h = self.coord_transformer.video_height

        # --- Update Origin Labels ---
        self.coordTopLeftOriginLabel.setText("(0.0, 0.0)")
        bl_origin_y_str = f"{video_h:.1f}" if video_h > 0 else "-"
        self.coordBottomLeftOriginLabel.setText(f"(0.0, {bl_origin_y_str})")
        cust_x = origin_meta.get('origin_x_tl', 0.0)
        cust_y = origin_meta.get('origin_y_tl', 0.0)
        self.coordCustomOriginLabel.setText(f"({cust_x:.1f}, {cust_y:.1f})")

        # --- Update Radio Button Selection ---
        self.coordSystemGroup.blockSignals(True)
        if current_mode == CoordinateSystem.TOP_LEFT: self.coordTopLeftRadio.setChecked(True)
        elif current_mode == CoordinateSystem.BOTTOM_LEFT: self.coordBottomLeftRadio.setChecked(True)
        elif current_mode == CoordinateSystem.CUSTOM:
             # Ensure custom radio is enabled if video loaded (handled in _update_ui_state)
             self.coordCustomRadio.setChecked(True)
        self.coordSystemGroup.blockSignals(False)

        # --- Sync Show Origin Checkbox State ---
        # Match checkbox visual state to internal state (_show_origin_marker)
        if hasattr(self, 'showOriginCheckBox'):
            self.showOriginCheckBox.blockSignals(True)
            self.showOriginCheckBox.setChecked(self._show_origin_marker)
            self.showOriginCheckBox.blockSignals(False)

        # Note: _update_ui_state() handles general enablement based on video loaded.

    @QtCore.Slot(float, float)
    def _handle_mouse_moved(self, scene_x_px: float, scene_y_px: float) -> None:
        self._last_scene_mouse_x = scene_x_px
        self._last_scene_mouse_y = scene_y_px

        required_labels_px = ['cursorPosLabelTL', 'cursorPosLabelBL', 'cursorPosLabelCustom']
        required_labels_m = ['cursorPosLabelTL_m', 'cursorPosLabelBL_m', 'cursorPosLabelCustom_m']
        
        if not all(hasattr(self, attr) for attr in required_labels_px + required_labels_m + ['coord_transformer', 'scale_manager']):
            return

        placeholder = "(--, --)"
        scale_is_set = self.scale_manager.get_scale_m_per_px() is not None

        if not self.video_loaded or scene_x_px == -1.0:
            for label_name in required_labels_px + required_labels_m:
                if hasattr(self, label_name):
                    getattr(self, label_name).setText(placeholder)
            return

        # --- PIXEL DISPLAY (Always calculated and shown) ---
        # 1. Top-Left [px]
        self.cursorPosLabelTL.setText(f"({scene_x_px:.1f}, {scene_y_px:.1f})")

        # 2. Bottom-Left [px]
        video_h_px = self.coord_transformer.video_height
        if video_h_px > 0:
            bl_x_equivalent_px = scene_x_px
            bl_y_equivalent_px = -(scene_y_px - float(video_h_px))
            self.cursorPosLabelBL.setText(f"({bl_x_equivalent_px:.1f}, {bl_y_equivalent_px:.1f})")
        else:
            self.cursorPosLabelBL.setText(placeholder)

        # 3. Custom [px]
        origin_meta = self.coord_transformer.get_metadata()
        cust_origin_x_tl_px = origin_meta.get('origin_x_tl', 0.0)
        cust_origin_y_tl_px = origin_meta.get('origin_y_tl', 0.0)
        custom_x_equivalent_px = scene_x_px - cust_origin_x_tl_px
        custom_y_equivalent_px = -(scene_y_px - cust_origin_y_tl_px)
        self.cursorPosLabelCustom.setText(f"({custom_x_equivalent_px:.1f}, {custom_y_equivalent_px:.1f})")

        # --- METRIC DISPLAY (Shown if scale is set) ---
        if scale_is_set:
            # Convert TL pixels to meters
            tl_x_m, tl_y_m = scene_x_px * self.scale_manager.get_scale_m_per_px(), \
                             scene_y_px * self.scale_manager.get_scale_m_per_px()
            self.cursorPosLabelTL_m.setText(f"({tl_x_m:.1f}, {tl_y_m:.1f})")
    
            # Convert BL equivalent pixels to meters
            if video_h_px > 0:
                bl_x_m, bl_y_m = bl_x_equivalent_px * self.scale_manager.get_scale_m_per_px(), \
                                 bl_y_equivalent_px * self.scale_manager.get_scale_m_per_px()
                self.cursorPosLabelBL_m.setText(f"({bl_x_m:.1f}, {bl_y_m:.1f})")
            else:
                self.cursorPosLabelBL_m.setText(placeholder)
    
            # Convert Custom equivalent pixels to meters
            custom_x_m, custom_y_m = custom_x_equivalent_px * self.scale_manager.get_scale_m_per_px(), \
                                     custom_y_equivalent_px * self.scale_manager.get_scale_m_per_px()
            self.cursorPosLabelCustom_m.setText(f"({custom_x_m:.1f}, {custom_y_m:.1f})")
        else:
            # If no scale is set, show placeholder in metric labels
            self.cursorPosLabelTL_m.setText(placeholder)
            self.cursorPosLabelBL_m.setText(placeholder)
            self.cursorPosLabelCustom_m.setText(placeholder)

    @QtCore.Slot()
    def _trigger_cursor_label_update(self) -> None:
        """
        Forces an update of cursor position labels.
        Called when scale or display unit changes, to reflect the change
        even if the mouse hasn't moved.
        """
        if hasattr(self, '_last_scene_mouse_x') and hasattr(self, '_last_scene_mouse_y'):
             logger.debug("Triggering cursor label update due to scale/unit change.")
             self._handle_mouse_moved(self._last_scene_mouse_x, self._last_scene_mouse_y)
        else:
             logger.warning("_trigger_cursor_label_update called but last mouse position not available.")

    # --- Dialog Slots ---

    @QtCore.Slot()
    def _show_video_info_dialog(self) -> None:
        """Handles the File -> Video Information... action."""
        if not self.video_loaded or not hasattr(self, 'video_handler'):
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("No video loaded.", 3000)
            logger.warning("Video Info action triggered but no video loaded.")
            return

        logger.info("Video Info action triggered. Retrieving metadata...")
        try:
            metadata_dict = self.video_handler.get_metadata_dictionary()
            if not metadata_dict:
                logger.warning("Video handler returned empty metadata dictionary.")
                QtWidgets.QMessageBox.information(self, "Video Information", "Could not retrieve video metadata.")
                return

            dialog = MetadataDialog(metadata_dict, self)
            dialog.exec() # Show as modal dialog

        except Exception as e:
            logger.exception("Error retrieving or displaying video metadata.")
            QtWidgets.QMessageBox.critical(self, "Error", f"Could not display video information:\n{e}")

    @QtCore.Slot()
    def _show_about_dialog(self) -> None:
        """Displays the About dialog."""
        app_icon = self.windowIcon() # Get the application icon

        about_box = QtWidgets.QMessageBox(self)
        about_box.setWindowTitle(f"About {config.APP_NAME}")
        about_box.setTextFormat(QtCore.Qt.TextFormat.RichText) # Allow HTML
        about_box.setText(
            f"<b>{config.APP_NAME}</b><br>"
            f"Version {config.APP_VERSION}<br><br>"
            "Tool for tracking volcanic pyroclasts in eruption videos.<br><br>"
            f"Using Python {sys.version.split()[0]} and PySide6 {QtCore.__version__}"
        )
        # Set the icon
        if not app_icon.isNull():
             icon_pixmap = app_icon.pixmap(QtCore.QSize(64, 64)) # Generate suitable pixmap
             if not icon_pixmap.isNull():
                 about_box.setIconPixmap(icon_pixmap)
             else:
                 about_box.setIcon(QtWidgets.QMessageBox.Icon.Information) # Fallback
                 logger.warning("Failed to generate pixmap from application icon for About dialog.")
        else:
            about_box.setIcon(QtWidgets.QMessageBox.Icon.Information) # Fallback

        about_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
        about_box.exec()


    # --- Window Close Event ---

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Ensures video resources are released when the window is closed."""
        logger.info("Close event triggered. Releasing video...")
        self._release_video()
        super().closeEvent(event)


    # --- Utility Methods ---

    def _format_time(self, milliseconds: float) -> str:
        """Formats milliseconds into a MM:SS.mmm string."""
        if milliseconds < 0: return "--:--.---"
        try:
            total_seconds, msecs = divmod(milliseconds, 1000)
            minutes, seconds = divmod(int(total_seconds), 60)
            return f"{minutes:02}:{seconds:02}.{int(msecs):03}"
        except (ValueError, TypeError):
            logger.warning(f"Could not format time from milliseconds: {milliseconds}", exc_info=False)
            return "--:--.---"