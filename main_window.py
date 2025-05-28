# main_window.py
import sys
import os
import math
import logging
import json
from PySide6 import QtCore, QtGui, QtWidgets
from typing import Optional, List, Tuple, Dict, Any

from metadata_dialog import MetadataDialog
import config
from interactive_image_view import InteractiveImageView, InteractionMode
from element_manager import ElementManager, ElementVisibilityMode, PointData, VisualElement, UndoActionType, ElementType
import file_io
from video_handler import VideoHandler
import ui_setup # Will use the modified version
from coordinates import CoordinateSystem, CoordinateTransformer
import settings_manager
from preferences_dialog import PreferencesDialog
from scale_manager import ScaleManager
from panel_controllers import ScalePanelController, CoordinatePanelController
from table_controllers import TrackDataViewController
from export_handler import ExportHandler, ExportResolutionMode
from export_options_dialog import ExportOptionsDialog
from view_menu_controller import ViewMenuController
from project_manager import ProjectManager
import settings_manager as sm_module
import graphics_utils

from file_io import UnitSelectionDialog


logger = logging.getLogger(__name__)

basedir = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(basedir, "PyroTracker.ico")

class MainWindow(QtWidgets.QMainWindow):
    # --- Instance Variable Type Hinting (ensure these match ui_setup.py) ---
    element_manager: ElementManager
    imageView: InteractiveImageView
    video_handler: VideoHandler
    coord_transformer: CoordinateTransformer
    scale_manager: ScaleManager
    project_manager: ProjectManager 
    settings_manager_instance: sm_module

    scale_panel_controller: Optional[ScalePanelController]
    coord_panel_controller: Optional[CoordinatePanelController]
    table_data_controller: Optional[TrackDataViewController]
    _export_handler: Optional[ExportHandler] = None
    view_menu_controller: Optional[ViewMenuController] = None

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

    _is_defining_measurement_line: bool = False
    _current_line_definition_frame_index: int = -1
    _project_load_warnings: List[str] = []
    _export_action_busy: bool = False


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
    linesTableWidget: Optional[QtWidgets.QTableWidget] = None
    newLineButton: Optional[QtWidgets.QPushButton] = None
    pointsTabLabel: QtWidgets.QLabel
    pointsTableWidget: QtWidgets.QTableWidget
    newTrackButton: QtWidgets.QPushButton # From ui_setup
    newMeasurementLineAction: Optional[QtGui.QAction] = None # From ui_setup, will be connected
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

    loadProjectAction: QtGui.QAction
    saveProjectAsAction: QtGui.QAction 
    saveAction: Optional[QtGui.QAction] = None
    closeProjectAction: Optional[QtGui.QAction] = None
    exportViewAction: QtGui.QAction
    exportFrameAction: QtGui.QAction
    newTrackAction: QtGui.QAction
    videoInfoAction: QtGui.QAction
    preferencesAction: QtGui.QAction # Still created in ui_setup, moved to View menu by ViewMenuController
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

    exportDataMenu: Optional[QtWidgets.QMenu] = None
    exportTracksCsvAction: Optional[QtGui.QAction] = None
    exportLinesCsvAction: Optional[QtGui.QAction] = None

    saveTracksTableButton: Optional[QtWidgets.QPushButton] = None
    copyTracksTableButton: Optional[QtWidgets.QPushButton] = None
    saveLinesTableButton: Optional[QtWidgets.QPushButton] = None
    copyLinesTableButton: Optional[QtWidgets.QPushButton] = None
    
    # Help Menu Actions
    manualAction: Optional[QtGui.QAction] = None
    aboutAction: Optional[QtGui.QAction] = None


    pen_origin_marker: QtGui.QPen
    pen_marker_active_current: QtGui.QPen
    pen_marker_active_other: QtGui.QPen
    pen_marker_inactive_current: QtGui.QPen
    pen_marker_inactive_other: QtGui.QPen
    pen_line_active: QtGui.QPen
    pen_line_inactive: QtGui.QPen
    pen_measurement_line_normal: QtGui.QPen
    pen_measurement_line_active: QtGui.QPen

    _export_progress_dialog: Optional[QtWidgets.QProgressDialog] = None

    def __init__(self) -> None:
        super().__init__()
        logger.info("Initializing MainWindow...")
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QtGui.QIcon(ICON_PATH))

        # Initialize core managers
        self.video_handler = VideoHandler(self)
        self.element_manager = ElementManager(self)
        self.coord_transformer = CoordinateTransformer()
        self.scale_manager = ScaleManager(self)
        self.settings_manager_instance = sm_module

        self.project_manager = ProjectManager(
            element_manager=self.element_manager,
            scale_manager=self.scale_manager,
            coord_transformer=self.coord_transformer,
            settings_manager=self.settings_manager_instance,
            main_window_ref=self
        )
        self.project_manager.unsavedChangesStateChanged.connect(self._handle_unsaved_changes_state_changed)

        self._setup_pens()

        screen_geometry = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        self.setGeometry(50, 50, int(screen_geometry.width() * 0.8), int(screen_geometry.height() * 0.8))
        self.setMinimumSize(800, 600)

        ui_setup.setup_main_window_ui(self) 
        # Menu actions defined in ui_setup.py are now attributes of self (e.g., self.newTrackAction)
        
        self._setup_file_menu() # Consolidate File menu setup

        # Connect actions created in ui_setup or _setup_file_menu
        if hasattr(self, 'loadProjectAction') and self.loadProjectAction:
            self.loadProjectAction.triggered.connect(self._trigger_load_project)
        if hasattr(self, 'saveProjectAsAction') and self.saveProjectAsAction:
            self.saveProjectAsAction.triggered.connect(self._trigger_save_project_as)
        if hasattr(self, 'saveAction') and self.saveAction: # From _setup_file_menu
            self.saveAction.triggered.connect(self._trigger_save_project_direct)
        if hasattr(self, 'closeProjectAction') and self.closeProjectAction: # From _setup_file_menu
            self.closeProjectAction.triggered.connect(self._trigger_close_project)
        
        if hasattr(self, 'exportTracksCsvAction') and self.exportTracksCsvAction: # From _setup_file_menu
            self.exportTracksCsvAction.triggered.connect(self._trigger_export_tracks_data_csv)
        if hasattr(self, 'exportLinesCsvAction') and self.exportLinesCsvAction: # From _setup_file_menu
            self.exportLinesCsvAction.triggered.connect(self._trigger_export_lines_data_csv)

        if hasattr(self, 'newTrackAction') and self.newTrackAction: # From ui_setup
            self.newTrackAction.setShortcut(QtGui.QKeySequence.StandardKey.New) # Ctrl+N
            self.newTrackAction.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            self.newTrackAction.triggered.connect(self._create_new_track)
        
        # Connect "New Measurement Line" action (created in ui_setup.py)
        if hasattr(self, 'newMeasurementLineAction') and self.newMeasurementLineAction:
            self.newMeasurementLineAction.triggered.connect(self._trigger_new_measurement_line)
            logger.debug("Connected newMeasurementLineAction to _trigger_new_measurement_line.")
        else:
            logger.error("newMeasurementLineAction QAction not found after UI setup.")


        # View Menu and Help Menu setup
        menu_bar_instance = self.menuBar()
        if self.imageView:
            self.view_menu_controller = ViewMenuController(main_window_ref=self, image_view_ref=self.imageView, parent=self)
            if menu_bar_instance:
                 self.view_menu_controller.setup_view_menu(menu_bar_instance) # ViewMenuController adds Preferences here

                 logger.debug("Creating Help menu in MainWindow...")
                 help_menu: QtWidgets.QMenu = menu_bar_instance.addMenu("&Help")
                 
                 # PyroTracker Manual action with icon
                 manual_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogHelpButton) # Or SP_MessageBoxInformation
                 self.manualAction = QtGui.QAction(manual_icon, "PyroTracker &Manual", self)
                 self.manualAction.setStatusTip("Open the PyroTracker user manual (PDF)")
                 self.manualAction.triggered.connect(self._trigger_show_manual)
                 help_menu.addAction(self.manualAction)
                 
                 # About action with application icon
                 app_icon_for_menu = self.windowIcon() # Get the already set window icon
                 self.aboutAction = QtGui.QAction(app_icon_for_menu, "&About PyroTracker", self)
                 self.aboutAction.setStatusTip("Show information about this application")
                 self.aboutAction.triggered.connect(self._show_about_dialog)
                 help_menu.addAction(self.aboutAction)
                 logger.debug("Help menu created and added.")
        else:
            logger.error("ImageView not available for ViewMenuController or Help menu initialization.")
            self.view_menu_controller = None


        if hasattr(self, 'currentFrameLineEdit') and isinstance(self.currentFrameLineEdit, QtWidgets.QLineEdit):
            self.currentFrameLineEdit.editingFinished.connect(self._handle_frame_input_finished)
            self.currentFrameLineEdit.installEventFilter(self)
        if hasattr(self, 'currentTimeLineEdit') and isinstance(self.currentTimeLineEdit, QtWidgets.QLineEdit):
            self.currentTimeLineEdit.editingFinished.connect(self._handle_time_input_finished)
            self.currentTimeLineEdit.installEventFilter(self)
        if hasattr(self, 'zoomLevelLineEdit') and isinstance(self.zoomLevelLineEdit, QtWidgets.QLineEdit):
            self.zoomLevelLineEdit.editingFinished.connect(self._handle_zoom_input_finished)
            self.zoomLevelLineEdit.installEventFilter(self)

        if self.imageView:
            self.imageView.viewTransformChanged.connect(self._update_zoom_display)

        if hasattr(self, 'undoAction') and self.undoAction: # From ui_setup
            self.undoAction.triggered.connect(self._trigger_undo_point_action)
            self.undoAction.setEnabled(False)

        if self.element_manager and hasattr(self, 'undoAction') and self.undoAction:
            self.element_manager.undoStateChanged.connect(self.undoAction.setEnabled)
            self.element_manager.elementListChanged.connect(lambda: self.project_manager.set_project_dirty(True))
            self.element_manager.activeElementDataChanged.connect(lambda: self.project_manager.set_project_dirty(True))

        if all(hasattr(self, attr) and getattr(self, attr) is not None for attr in [
            'scale_m_per_px_input', 'scale_px_per_m_input', 'scale_reset_button',
            'scale_display_meters_checkbox', 'showScaleBarCheckBox',
            'setScaleByFeatureButton', 'showScaleLineCheckBox',
            'imageView', 'scale_manager'
        ]):
            self.scale_panel_controller = ScalePanelController(
                scale_manager=self.scale_manager, image_view=self.imageView,
                main_window_ref=self, scale_m_per_px_input=self.scale_m_per_px_input,
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
            if self.showScaleBarCheckBox and self.view_menu_controller:
                self.showScaleBarCheckBox.toggled.connect(
                    lambda checked, cb=self.showScaleBarCheckBox: self.view_menu_controller.sync_panel_checkbox_to_menu(cb) if self.view_menu_controller else None
                )
                self.showScaleBarCheckBox.toggled.connect(lambda: self.project_manager.set_project_dirty(True))
            if self.showScaleLineCheckBox and self.view_menu_controller:
                self.showScaleLineCheckBox.toggled.connect(
                    lambda checked, cb=self.showScaleLineCheckBox: self.view_menu_controller.sync_panel_checkbox_to_menu(cb) if self.view_menu_controller else None
                )
                self.showScaleLineCheckBox.toggled.connect(lambda: self.project_manager.set_project_dirty(True))
            if self.scale_display_meters_checkbox:
                self.scale_display_meters_checkbox.toggled.connect(lambda: self.project_manager.set_project_dirty(True))
        else:
            logger.error("Scale panel UI elements or core components not found for ScalePanelController.")
            self.scale_panel_controller = None

        if all(hasattr(self, attr) and getattr(self, attr) is not None for attr in [
            'coordSystemGroup', 'coordTopLeftRadio', 'coordBottomLeftRadio', 'coordCustomRadio',
            'coordTopLeftOriginLabel', 'coordBottomLeftOriginLabel', 'coordCustomOriginLabel',
            'setOriginButton', 'showOriginCheckBox', 'cursorPosLabelTL', 'cursorPosLabelBL',
            'cursorPosLabelCustom', 'cursorPosLabelTL_m', 'cursorPosLabelBL_m', 'cursorPosLabelCustom_m',
            'imageView', 'scale_manager', 'coord_transformer'
        ]):
            cursor_labels_px_dict = { "TL": self.cursorPosLabelTL, "BL": self.cursorPosLabelBL, "Custom": self.cursorPosLabelCustom }
            cursor_labels_m_dict = { "TL": self.cursorPosLabelTL_m, "BL": self.cursorPosLabelBL_m, "Custom": self.cursorPosLabelCustom_m }
            self.coord_panel_controller = CoordinatePanelController(
                main_window_ref=self,
                coord_transformer=self.coord_transformer,
                image_view=self.imageView,
                scale_manager=self.scale_manager,
                coord_system_group=self.coordSystemGroup,
                coord_top_left_radio=self.coordTopLeftRadio,
                coord_bottom_left_radio=self.coordBottomLeftRadio,
                coord_custom_radio=self.coordCustomRadio,
                coord_top_left_origin_label=self.coordTopLeftOriginLabel,
                coord_bottom_left_origin_label=self.coordBottomLeftOriginLabel,
                coord_custom_origin_label=self.coordCustomOriginLabel,
                set_origin_button=self.setOriginButton,
                show_origin_checkbox=self.showOriginCheckBox,
                cursor_pos_labels_px=cursor_labels_px_dict,
                cursor_pos_labels_m=cursor_labels_m_dict,
                parent=self
            )
            if self.showOriginCheckBox and self.view_menu_controller:
                self.showOriginCheckBox.toggled.connect(
                    lambda state, cb=self.showOriginCheckBox: self.view_menu_controller.sync_panel_checkbox_to_menu(cb) if self.view_menu_controller else None
                )
                self.showOriginCheckBox.toggled.connect(lambda: self.project_manager.set_project_dirty(True))
        else:
            logger.error("Coordinate panel UI elements or core components not found for CoordinatePanelController.")
            self.coord_panel_controller = None

        if all(hasattr(self, attr) and getattr(self, attr) is not None for attr in [
            'tracksTableWidget', 'pointsTableWidget', 'pointsTabLabel', 'element_manager',
            'video_handler', 'scale_manager', 'coord_transformer'
        ]):
            self.table_data_controller = TrackDataViewController(
                main_window_ref=self, element_manager=self.element_manager, video_handler=self.video_handler,
                scale_manager=self.scale_manager, coord_transformer=self.coord_transformer,
                tracks_table_widget=self.tracksTableWidget, points_table_widget=self.pointsTableWidget,
                points_tab_label=self.pointsTabLabel, parent=self
            )
        else:
            logger.error("Table UI elements or core components not found for TrackDataViewController.")
            self.table_data_controller = None

        status_bar_instance = self.statusBar()
        if status_bar_instance:
            status_bar_instance.showMessage("Ready. Load a video via File -> Open Video...")

        self._export_handler = ExportHandler(
            video_handler=self.video_handler, element_manager=self.element_manager,
            scale_manager=self.scale_manager, coord_transformer=self.coord_transformer,
            image_view=self.imageView, main_window=self, parent=self )
        
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
                self.imageView.originSetRequest.connect(lambda: self.project_manager.set_project_dirty(True))
                self.imageView.sceneMouseMoved.connect(self.coord_panel_controller._on_handle_mouse_moved)
            if self.scale_panel_controller:
                self.imageView.viewTransformChanged.connect(self.scale_panel_controller._on_view_transform_changed)
            self.imageView.scaleLinePoint1Clicked.connect(self._handle_scale_or_measurement_line_first_point)
            self.imageView.scaleLinePoint2Clicked.connect(self._handle_scale_or_measurement_line_second_point)
            self.imageView.scaleLinePoint2Clicked.connect(lambda: self.project_manager.set_project_dirty(True))


        if self.table_data_controller:
            self.element_manager.elementListChanged.connect(self.table_data_controller.update_tracks_table_ui)
            if hasattr(self.table_data_controller, '_lines_table') and self.table_data_controller._lines_table:
                 self.element_manager.elementListChanged.connect(self.table_data_controller.update_lines_table_ui)
            self.element_manager.activeElementDataChanged.connect(self.table_data_controller.update_points_table_ui)
            self.element_manager.activeElementDataChanged.connect(self.table_data_controller._sync_active_element_selection_in_tables)
        self.element_manager.visualsNeedUpdate.connect(self._redraw_scene_overlay)

        if self.scale_panel_controller:
            self.scale_manager.scaleOrUnitChanged.connect(self.scale_panel_controller.update_ui_from_manager)
            self.scale_manager.scaleOrUnitChanged.connect(lambda: self.project_manager.set_project_dirty(True))
        if self.table_data_controller:
            self.scale_manager.scaleOrUnitChanged.connect(self.table_data_controller.update_points_table_ui)
            if hasattr(self.table_data_controller, '_lines_table') and self.table_data_controller._lines_table:
                self.scale_manager.scaleOrUnitChanged.connect(self.table_data_controller.update_lines_table_ui)
        if self.coord_panel_controller:
            self.scale_manager.scaleOrUnitChanged.connect(self.coord_panel_controller._trigger_cursor_label_update_slot)

        if self.coord_panel_controller:
            self.coord_panel_controller.needsRedraw.connect(self._redraw_scene_overlay)
            if self.table_data_controller:
                self.coord_panel_controller.pointsTableNeedsUpdate.connect(self.table_data_controller.update_points_table_ui)
                if hasattr(self.table_data_controller, '_lines_table') and self.table_data_controller._lines_table:
                    self.coord_panel_controller.pointsTableNeedsUpdate.connect(self.table_data_controller.update_lines_table_ui)
            self.coord_panel_controller.pointsTableNeedsUpdate.connect(lambda: self.project_manager.set_project_dirty(True))
            if status_bar_instance:
                self.coord_panel_controller.statusBarMessage.connect(status_bar_instance.showMessage)

        if self.table_data_controller:
            self.table_data_controller.seekVideoToFrame.connect(self.video_handler.seek_frame)
            self.table_data_controller.updateMainWindowUIState.connect(self._update_ui_state)
            if status_bar_instance:
                self.table_data_controller.statusBarMessage.connect(status_bar_instance.showMessage)
            if hasattr(self.tracksTableWidget, 'horizontalHeader') and hasattr(self.tracksTableWidget.horizontalHeader(), 'sectionClicked'):
                 self.tracksTableWidget.horizontalHeader().sectionClicked.connect(
                     lambda logical_index: self.table_data_controller.handle_visibility_header_clicked(logical_index, ElementType.TRACK) if self.table_data_controller else None
                 )
            if hasattr(self, 'linesTableWidget') and self.linesTableWidget and \
               hasattr(self.linesTableWidget, 'horizontalHeader') and \
               hasattr(self.linesTableWidget.horizontalHeader(), 'sectionClicked'):
                self.linesTableWidget.horizontalHeader().sectionClicked.connect(
                    lambda logical_index: self.table_data_controller.handle_visibility_header_clicked(logical_index, ElementType.MEASUREMENT_LINE) if self.table_data_controller else None
                )

        if self.frameSlider:
            self.frameSlider.valueChanged.connect(self._slider_value_changed)
        if self.playPauseButton:
            self.playPauseButton.clicked.connect(self._toggle_playback)
        if self.prevFrameButton:
            self.prevFrameButton.clicked.connect(self._show_previous_frame)
        if self.nextFrameButton:
            self.nextFrameButton.clicked.connect(self._show_next_frame)

        if self.autoAdvanceCheckBox:
            self.autoAdvanceCheckBox.stateChanged.connect(self._handle_auto_advance_toggled)
        if self.autoAdvanceSpinBox:
            self.autoAdvanceSpinBox.valueChanged.connect(self._handle_auto_advance_frames_changed)

        if self.videoInfoAction:
            self.videoInfoAction.triggered.connect(self._show_video_info_dialog)
        if self.preferencesAction: # This action is now added to View menu by ViewMenuController
            self.preferencesAction.triggered.connect(self._show_preferences_dialog)

        if hasattr(self, 'newTrackButton') and self.newTrackButton: # From Tracks Tab
            self.newTrackButton.clicked.connect(self._create_new_track)
        if hasattr(self, 'newLineButton') and self.newLineButton: # From Lines Tab
            self.newLineButton.clicked.connect(self._trigger_new_measurement_line) # Use the same slot as menu

        if hasattr(self, 'exportViewAction') and self.exportViewAction and self._export_handler:
            self.exportViewAction.triggered.connect(self._trigger_export_video)
        if hasattr(self, 'exportFrameAction') and self.exportFrameAction and self._export_handler:
            self.exportFrameAction.triggered.connect(self._trigger_export_frame)

        if self._export_handler:
            self._export_handler.exportStarted.connect(self._on_export_started)
            self._export_handler.exportProgress.connect(self._on_export_progress)
            self._export_handler.exportFinished.connect(self._on_export_finished)

        if hasattr(self, 'saveTracksTableButton') and self.saveTracksTableButton:
            self.saveTracksTableButton.clicked.connect(self._trigger_save_tracks_table_data)
        if hasattr(self, 'copyTracksTableButton') and self.copyTracksTableButton:
            self.copyTracksTableButton.clicked.connect(self._trigger_copy_tracks_table_data)
        if hasattr(self, 'saveLinesTableButton') and self.saveLinesTableButton:
            self.saveLinesTableButton.clicked.connect(self._trigger_save_lines_table_data)
        if hasattr(self, 'copyLinesTableButton') and self.copyLinesTableButton:
            self.copyLinesTableButton.clicked.connect(self._trigger_copy_lines_table_data)

        self._update_ui_state() 
        if self.table_data_controller:
            self.table_data_controller.update_tracks_table_ui()
            if self.table_data_controller._lines_table:
                self.table_data_controller.update_lines_table_ui()
            self.table_data_controller.update_points_table_ui()
        if self.coord_panel_controller:
            self.coord_panel_controller.update_ui_display()
        if self.scale_panel_controller:
            self.scale_panel_controller.update_ui_from_manager()

        if self.view_menu_controller:
            self.view_menu_controller.sync_all_menu_items_from_settings_and_panels()
            if self.view_menu_controller.viewShowFilenameAction:
                self.view_menu_controller.viewShowFilenameAction.triggered.connect(lambda: self.project_manager.set_project_dirty(True))
            if self.view_menu_controller.viewShowTimeAction:
                self.view_menu_controller.viewShowTimeAction.triggered.connect(lambda: self.project_manager.set_project_dirty(True))
            if self.view_menu_controller.viewShowFrameNumberAction:
                self.view_menu_controller.viewShowFrameNumberAction.triggered.connect(lambda: self.project_manager.set_project_dirty(True))
            if self.view_menu_controller.viewShowMeasurementLineLengthsAction:
                 self.view_menu_controller.viewShowMeasurementLineLengthsAction.triggered.connect(lambda: self.project_manager.set_project_dirty(True))

        if self.project_manager:
            self.project_manager.set_project_dirty(False) 

        logger.info("MainWindow initialization complete.")

    # --- Modified File Menu Setup ---
    def _setup_file_menu(self) -> None:
        """Configures the File menu according to the new structure."""
        logger.debug("MainWindow: Setting up File menu...")
        menu_bar = self.menuBar()
        file_menu = None
        # Find existing File menu created by ui_setup
        for action in menu_bar.actions():
            if action.menu() and action.text() == "&File":
                file_menu = action.menu()
                break
        
        if not file_menu:
            logger.error("MainWindow: File menu not found from ui_setup. Cannot restructure.")
            return

        # Clear existing File menu actions before rebuilding
        file_menu.clear()

        style = self.style()

        # --- Open Video... ---
        # This action was created in ui_setup.py but as a local variable.
        # We need to recreate it or ensure it's an attribute. Let's recreate for clarity here.
        self.openVideoAction = QtGui.QAction(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton), "&Open Video...", self)
        self.openVideoAction.setStatusTip("Select and load a video file")
        self.openVideoAction.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        self.openVideoAction.triggered.connect(self.open_video) # Connect to the existing slot
        file_menu.addAction(self.openVideoAction)

        file_menu.addSeparator()

        # --- Open Project... ---
        # self.loadProjectAction is expected to be an attribute from ui_setup.py
        if hasattr(self, 'loadProjectAction') and self.loadProjectAction:
            file_menu.addAction(self.loadProjectAction)
        else: 
            logger.error("loadProjectAction not found on MainWindow, cannot add to File menu.")

        # --- Save Project ---
        save_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton)
        self.saveAction = QtGui.QAction(save_icon, "&Save Project", self)
        self.saveAction.setStatusTip("Save the current project (Ctrl+S)")
        self.saveAction.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        self.saveAction.setEnabled(False) 
        self.saveAction.triggered.connect(self._trigger_save_project_direct)
        file_menu.addAction(self.saveAction)

        # --- Save Project As... ---
        # self.saveProjectAsAction is expected to be an attribute from ui_setup.py
        if hasattr(self, 'saveProjectAsAction') and self.saveProjectAsAction:
            file_menu.addAction(self.saveProjectAsAction)
        else:
            logger.error("saveProjectAsAction not found on MainWindow, cannot add to File menu.")

        # --- Close Project ---
        close_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DockWidgetCloseButton) 
        self.closeProjectAction = QtGui.QAction(close_icon, "&Close Project", self)
        self.closeProjectAction.setStatusTip("Close the current project")
        self.closeProjectAction.setEnabled(False) 
        self.closeProjectAction.triggered.connect(self._trigger_close_project)
        file_menu.addAction(self.closeProjectAction)

        file_menu.addSeparator()

        # --- Export Data (submenu) ---
        self.exportDataMenu = QtWidgets.QMenu("Export Data", self)
        
        self.exportTracksCsvAction = QtGui.QAction("Export Tracks (as CSV)...", self)
        self.exportTracksCsvAction.setStatusTip("Export track data to a simple CSV file")
        self.exportTracksCsvAction.setEnabled(False) # Will be enabled when tracks exist
        self.exportTracksCsvAction.triggered.connect(self._trigger_export_tracks_data_csv)
        self.exportDataMenu.addAction(self.exportTracksCsvAction)

        self.exportLinesCsvAction = QtGui.QAction("Export Lines (as CSV)...", self)
        self.exportLinesCsvAction.setStatusTip("Export measurement line data to a simple CSV file")
        self.exportLinesCsvAction.setEnabled(False) # Will be enabled when lines exist
        self.exportLinesCsvAction.triggered.connect(self._trigger_export_lines_data_csv)
        self.exportDataMenu.addAction(self.exportLinesCsvAction)
        
        file_menu.addMenu(self.exportDataMenu)

        # --- Export Video with Overlays... ---
        # self.exportViewAction is expected to be an attribute from ui_setup.py
        if hasattr(self, 'exportViewAction') and self.exportViewAction:
            file_menu.addAction(self.exportViewAction)
        else:
            logger.error("exportViewAction not found on MainWindow, cannot add to File menu.")


        # --- Export Current Frame to PNG... ---
        # self.exportFrameAction is expected to be an attribute from ui_setup.py
        if hasattr(self, 'exportFrameAction') and self.exportFrameAction:
            file_menu.addAction(self.exportFrameAction)
        else:
            logger.error("exportFrameAction not found on MainWindow, cannot add to File menu.")
            
        file_menu.addSeparator()

        # --- Video Information... ---
        # self.videoInfoAction is expected to be an attribute from ui_setup.py
        if hasattr(self, 'videoInfoAction') and self.videoInfoAction:
            file_menu.addAction(self.videoInfoAction)
        else:
            logger.error("videoInfoAction not found on MainWindow, cannot add to File menu.")

        file_menu.addSeparator()

        # --- Exit ---
        # This action was created in ui_setup.py but as a local variable.
        # Recreate it here.
        self.exitAction = QtGui.QAction(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogCloseButton), "E&xit", self)
        self.exitAction.setStatusTip("Exit the application")
        self.exitAction.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        self.exitAction.triggered.connect(self.close) # Connect to QMainWindow.close
        file_menu.addAction(self.exitAction)
        
        logger.debug("File menu setup complete.")

    def _find_or_create_action(self, 
                               existing_actions: List[QtGui.QAction], 
                               text: str, 
                               icon: Optional[QtGui.QIcon] = None, 
                               status_tip: Optional[str] = None,
                               shortcut: Optional[QtGui.QKeySequence] = None,
                               triggered_slot: Optional[QtCore.Slot] = None,
                               checkable: bool = False) -> QtGui.QAction:
        """Helper to find an existing action by text or create a new one."""
        for action in existing_actions:
            if action.text() == text:
                # Optionally update properties if needed, or just return
                if icon and action.icon().isNull(): action.setIcon(icon)
                if status_tip and not action.statusTip(): action.setStatusTip(status_tip)
                if shortcut and action.shortcut().isEmpty(): action.setShortcut(shortcut)
                if triggered_slot and not self._is_slot_connected(action.triggered, triggered_slot):
                    action.triggered.connect(triggered_slot)
                return action
        
        # If not found, create it
        new_action = QtGui.QAction(text, self)
        if icon: new_action.setIcon(icon)
        if status_tip: new_action.setStatusTip(status_tip)
        if shortcut: new_action.setShortcut(shortcut)
        if triggered_slot: new_action.triggered.connect(triggered_slot)
        new_action.setCheckable(checkable)
        return new_action
        
    def _is_slot_connected(self, signal: QtCore.SignalInstance, slot_method: Any) -> bool:
        """Checks if a specific method (slot) is connected to a signal."""
        # This is a bit tricky with PySide6 as there's no direct public API
        # to list connected slots by method reference for non-QObject senders if slot is lambda etc.
        # For direct method connections to QObject methods, it's more feasible.
        # This is a simplified check and might not be perfectly robust for all cases.
        try:
            # This works if the slot is a direct method of an object
            if signal.receivers(slot_method.__self__) > 0 : # type: ignore
                return True # Crude check, assumes if any receiver exists for that object, it might be this one
        except AttributeError: # slot_method might not have __self__ (e.g. function, lambda)
            pass
        return False # Fallback


    # Method previously named _setup_additional_file_menu_actions is now integrated into _setup_file_menu
    # delete or rename if it's not used elsewhere. For now, it's effectively replaced.

    # --- NEW Slot for "New Measurement Line" menu action ---
    @QtCore.Slot()
    def _trigger_new_measurement_line(self) -> None:
        """Handles the 'New Measurement Line' menu action."""
        logger.info("'New Measurement Line' action triggered from menu.")
        # This logic is identical to the button press for creating a new line
        self._create_new_line_action()

    # --- Slot for "PyroTracker Manual" menu action ---
    @QtCore.Slot()
    def _trigger_show_manual(self) -> None:
        """Handles the 'PyroTracker Manual' menu action."""
        logger.info("'PyroTracker Manual' action triggered.")
        manual_filename = "PyroTracker_Manual.pdf" # Define the filename
        manual_path = os.path.join(basedir, manual_filename) 
        
        github_repo_url = "https://github.com/EdLlewellin/PyroTracker"
        releases_page_url = f"{github_repo_url}/releases"

        if os.path.exists(manual_path):
            success = QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(manual_path))
            if not success:
                QtWidgets.QMessageBox.warning(self, "Open Manual Error", 
                                              f"Could not open the manual at:\n{manual_path}\n\n"
                                              "Please ensure you have a PDF viewer installed.")
                logger.error(f"Failed to open manual PDF: {manual_path}")
        else:
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
            msg_box.setWindowTitle("Manual Not Found")
            msg_box.setTextFormat(QtCore.Qt.TextFormat.RichText) # Enable rich text
            msg_box.setText(
                f"The PyroTracker Manual (<i>{manual_filename}</i>) could not be found in the application directory:<br>"
                f"<i>{basedir}</i><br><br>"
                f"You can download it from the latest release page on GitHub:"
            )
            msg_box.setInformativeText(f"<a href='{releases_page_url}'>{releases_page_url}</a>")
            msg_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
            msg_box.exec()
            logger.warning(f"Manual PDF not found at: {manual_path}")


    @QtCore.Slot(bool)
    def _handle_unsaved_changes_state_changed(self, has_unsaved_changes: bool) -> None:
        """Updates the enabled state of the 'Save' action and window title."""
        if hasattr(self, 'saveAction') and self.saveAction:
            self.saveAction.setEnabled(has_unsaved_changes and self.video_loaded)
        
        title = f"{config.APP_NAME} v{config.APP_VERSION}"
        current_file_display_name = ""
        if self.project_manager and self.project_manager.get_current_project_filepath():
            current_file_display_name = os.path.basename(self.project_manager.get_current_project_filepath())
        elif self.video_loaded:
            current_file_display_name = os.path.basename(self.video_filepath) + " (Video)"
        
        if current_file_display_name:
            title += f" - {current_file_display_name}"
        
        if has_unsaved_changes and (self.video_loaded or (self.project_manager and self.project_manager.get_current_project_filepath() is not None)):
            title += "*" # Add asterisk if there's something potentially saveable
        
        self.setWindowTitle(title)


    @QtCore.Slot()
    def _trigger_save_project_direct(self) -> None:
        # ... (existing method)
        status_bar = self.statusBar()
        if not self.video_loaded and not (self.project_manager and self.project_manager.get_current_project_filepath()):
            if status_bar: status_bar.showMessage("Cannot save: No project/video loaded.", 3000)
            return

        current_path = self.project_manager.get_current_project_filepath()
        if current_path:
            logger.info(f"Saving project directly to: {current_path}")
            if status_bar: status_bar.showMessage(f"Saving project to {os.path.basename(current_path)}...", 0)
            QtWidgets.QApplication.processEvents()
            success = self.project_manager.save_project(current_path) 
            if success:
                if status_bar: status_bar.showMessage(f"Project saved to {os.path.basename(current_path)}", 5000)
            else:
                if status_bar: status_bar.showMessage("Error saving project. See log.", 5000)
                QtWidgets.QMessageBox.critical(self, "Save Project Error", f"Could not save project to {current_path}.\nPlease check the logs for details.")
        else:
            logger.info("'Save Project' triggered with no current path, deferring to 'Save Project As...'")
            self._trigger_save_project_as()
        
        self._update_ui_state()


    @QtCore.Slot()
    def _trigger_export_tracks_data_csv(self) -> None:
        logger.info("Export Tracks (CSV) action triggered.")
        if self._export_action_busy:
            logger.warning("Export Tracks (CSV) action re-triggered while busy. Ignoring.")
            return
        self._export_action_busy = True
        try:
            self._handle_data_export_request(ElementType.TRACK)
        finally:
            # Use QTimer.singleShot to reset the flag after the current event processing cycle
            # This helps prevent issues if the dialog closing itself causes immediate re-triggering
            QtCore.QTimer.singleShot(0, lambda: setattr(self, '_export_action_busy', False))

    @QtCore.Slot()
    def _trigger_export_lines_data_csv(self) -> None:
        logger.info("Export Lines (CSV) action triggered.")
        if self._export_action_busy:
            logger.warning("Export Lines (CSV) action re-triggered while busy. Ignoring.")
            return
        self._export_action_busy = True
        try:
            self._handle_data_export_request(ElementType.MEASUREMENT_LINE)
        finally:
            QtCore.QTimer.singleShot(0, lambda: setattr(self, '_export_action_busy', False))

    def _handle_data_export_request(self, element_type_to_export: ElementType) -> None:
        # ... (existing method)
        if not self.video_loaded: 
            QtWidgets.QMessageBox.warning(self, "Export Data Error", "A video must be loaded to export element data.")
            return
        if not self.element_manager or not self.scale_manager or not self.coord_transformer:
            logger.error(f"Cannot export {element_type_to_export.name} data: Core manager(s) missing.")
            QtWidgets.QMessageBox.critical(self, "Export Data Error", "Internal error: Required components missing.")
            return

        elements_to_export = self.element_manager.get_elements_by_type(element_type_to_export)

        type_name_plural = f"{element_type_to_export.name.lower().replace('_', ' ')}s"
        if not elements_to_export:
            QtWidgets.QMessageBox.information(self, "Export Data", f"No {type_name_plural} available to export.")
            return

        scale_is_defined = self.scale_manager.get_scale_m_per_px() is not None
        unit_dialog = UnitSelectionDialog(is_scale_defined=scale_is_defined, parent=self)
        
        if unit_dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            chosen_units = unit_dialog.get_selected_units()
            if not chosen_units: 
                logger.warning("Unit selection dialog returned no choice. Aborting export.")
                return

            base_filename_part = os.path.splitext(os.path.basename(self.video_filepath))[0] if self.video_filepath else "untitled"
            suggested_filename = f"{base_filename_part}_{type_name_plural}_export.csv"
            start_dir = os.path.dirname(self.video_filepath) if self.video_filepath and os.path.isdir(os.path.dirname(self.video_filepath)) else os.getcwd()
            
            save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, f"Export {type_name_plural.title()} to CSV", 
                os.path.join(start_dir, suggested_filename),
                "CSV Files (*.csv);;All Files (*)"
            )

            if not save_path:
                if self.statusBar(): self.statusBar().showMessage(f"{type_name_plural.title()} export cancelled.", 3000)
                return

            if not save_path.lower().endswith(".csv"):
                save_path += ".csv"

            if self.statusBar(): self.statusBar().showMessage(f"Exporting {type_name_plural} to {os.path.basename(save_path)}...", 0)
            QtWidgets.QApplication.processEvents()

            try:
                success = file_io.export_elements_to_simple_csv(
                    save_path, elements_to_export, element_type_to_export,
                    chosen_units, self.scale_manager, self.coord_transformer
                )

                if success:
                    if self.statusBar(): self.statusBar().showMessage(f"{type_name_plural.title()} exported to {os.path.basename(save_path)}", 5000)
                else:
                    if self.statusBar(): self.statusBar().showMessage(f"Error exporting {type_name_plural}. See log.", 5000)
                    QtWidgets.QMessageBox.warning(self, "Export Error", f"Could not export {type_name_plural} to CSV.")
            except Exception as e:
                logger.exception(f"Error during {type_name_plural} data export process.")
                QtWidgets.QMessageBox.critical(self, "Export Error", f"An unexpected error occurred during export: {e}")
                if self.statusBar(): self.statusBar().showMessage(f"Critical error exporting {type_name_plural}. See log.", 5000)
        else:
            if self.statusBar(): self.statusBar().showMessage(f"{type_name_plural.title()} export cancelled (unit selection).", 3000)


    def _setup_pens(self) -> None:
        # ... (existing method)
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
             logger.warning("Invalid size/width setting found, using defaults for track/origin.")
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

        ml_color = settings_manager.get_setting(settings_manager.KEY_MEASUREMENT_LINE_COLOR)
        ml_active_color = settings_manager.get_setting(settings_manager.KEY_MEASUREMENT_LINE_ACTIVE_COLOR)
        try:
            ml_width = float(settings_manager.get_setting(settings_manager.KEY_MEASUREMENT_LINE_WIDTH))
        except (TypeError, ValueError):
            logger.warning("Invalid measurement line width setting, using default.")
            ml_width = settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_MEASUREMENT_LINE_WIDTH]

        self.pen_measurement_line_normal = _create_pen(ml_color, ml_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_MEASUREMENT_LINE_COLOR])
        self.pen_measurement_line_active = _create_pen(ml_active_color, ml_width, settings_manager.DEFAULT_SETTINGS[settings_manager.KEY_MEASUREMENT_LINE_ACTIVE_COLOR])
        logger.debug("QPen setup complete using settings.")

    def _reset_ui_after_video_close(self) -> None:
        # ... (existing method with title update)
        logger.debug("Resetting UI elements for no video loaded state.")
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")
        status_bar = self.statusBar()
        if status_bar: status_bar.clearMessage()

        if hasattr(self, 'currentFrameLineEdit') and isinstance(self.currentFrameLineEdit, QtWidgets.QLineEdit):
            self.currentFrameLineEdit.blockSignals(True); self.currentFrameLineEdit.setReadOnly(True)
            self.currentFrameLineEdit.setText("-"); self.currentFrameLineEdit.deselect(); self.currentFrameLineEdit.blockSignals(False)
        if hasattr(self, 'totalFramesLabel') and isinstance(self.totalFramesLabel, QtWidgets.QLabel):
            self.totalFramesLabel.setText("/ -")
        if hasattr(self, 'currentTimeLineEdit') and isinstance(self.currentTimeLineEdit, QtWidgets.QLineEdit):
            self.currentTimeLineEdit.blockSignals(True); self.currentTimeLineEdit.setReadOnly(True)
            self.currentTimeLineEdit.setText("--:--.---"); self.currentTimeLineEdit.deselect(); self.currentTimeLineEdit.blockSignals(False)
        if hasattr(self, 'totalTimeLabel') and isinstance(self.totalTimeLabel, QtWidgets.QLabel):
            self.totalTimeLabel.setText("/ --:--.---")
        if hasattr(self, 'zoomLevelLineEdit') and self.zoomLevelLineEdit is not None:
            self.zoomLevelLineEdit.blockSignals(True); self.zoomLevelLineEdit.setReadOnly(True)
            self.zoomLevelLineEdit.setText("---.-"); self.zoomLevelLineEdit.deselect()
            self.zoomLevelLineEdit.clearFocus(); self.zoomLevelLineEdit.blockSignals(False)

        if self.frameSlider:
            self.frameSlider.blockSignals(True); self.frameSlider.setValue(0)
            self.frameSlider.setMaximum(0); self.frameSlider.blockSignals(False)

        if self.imageView:
            self.imageView.clearOverlay()
            self.imageView.setPixmap(QtGui.QPixmap())
            self.imageView.resetInitialLoadFlag()
            self.imageView.set_scale_bar_visibility(False)
            self.imageView.set_info_overlay_video_data("", 0, 0.0)
            self.imageView.set_info_overlay_current_frame_time(-1, 0.0)
            if hasattr(self.imageView, '_info_overlay_widget') and self.imageView._info_overlay_widget:
                self.imageView._info_overlay_widget.setVisible(False)
            self.imageView.set_interaction_mode(InteractionMode.NORMAL)

        self.coord_transformer.reset() 
        if self.coord_panel_controller:
            if self.coord_panel_controller._coord_transformer is not self.coord_transformer:
                 logger.warning("CoordinatePanelController was holding a different CoordinateTransformer instance post-reset. This indicates an issue. Re-assigning for safety.")
                 self.coord_panel_controller._coord_transformer = self.coord_transformer

        self.scale_manager.reset()
        if self.scale_panel_controller: self.scale_panel_controller.set_video_loaded_status(False)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_loaded_status(False)
        if self.table_data_controller: self.table_data_controller.set_video_loaded_status(False)

        if self.project_manager:
            self.project_manager.clear_project_state_for_close()

        self._update_ui_state()

        if self.view_menu_controller:
            self.view_menu_controller.handle_video_loaded_state_changed(False)


    def _prepare_for_project_load(self) -> None:
        # ... (existing method)
        logger.info("Preparing MainWindow for project load...")

        if self.project_manager and self.project_manager.project_has_unsaved_changes():
            logger.info("Project has unsaved changes. Prompting user before loading new project.")
            original_close_event = self.closeEvent
            def temp_no_op_close_event(event: QtGui.QCloseEvent) -> None: event.ignore() 
            self.closeEvent = temp_no_op_close_event # type: ignore
            self._trigger_close_project() 
            self.closeEvent = original_close_event 
            if self.project_manager.project_has_unsaved_changes():
                 logger.info("User cancelled loading new project due to unsaved changes prompt.")
                 raise InterruptedError("Project load cancelled by user due to unsaved changes.") 

        if self.video_loaded:
            self._release_video() 

        self.element_manager.reset()
        self.scale_manager.reset()
        self.coord_transformer.reset()
        
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}") 
        status_bar = self.statusBar()
        if status_bar:
            status_bar.showMessage("Ready. Project loading...", 0) 

        self._update_ui_state()
        if self.table_data_controller:
            self.table_data_controller.update_tracks_table_ui()
            if self.table_data_controller._lines_table:
                self.table_data_controller.update_lines_table_ui()
            self.table_data_controller.update_points_table_ui()
        if self.coord_panel_controller:
            self.coord_panel_controller.update_ui_display()
        if self.scale_panel_controller:
            self.scale_panel_controller.update_ui_from_manager()
        if self.view_menu_controller:
            self.view_menu_controller.sync_all_menu_items_from_settings_and_panels()
        if self.imageView:
            self.imageView.clearOverlay() 
            self.imageView.viewport().update()

        logger.info("MainWindow preparation for project load complete.")

    def _cancel_active_line_definition_ui_reset(self) -> None:
        # ... (existing method)
        if self.element_manager:
            self.element_manager.cancel_active_line_definition()

        self._is_defining_measurement_line = False
        if self.imageView:
            self.imageView.set_interaction_mode(InteractionMode.NORMAL)
            self.imageView.clearTemporaryScaleVisuals()
        self._handle_disable_frame_navigation(False)
        self._update_ui_state() 
        logger.debug("Measurement line definition UI reset.")

    def _update_ui_state(self) -> None:
        # ... (existing method with Save/SaveAs/Close Project updates)
        is_video_loaded: bool = self.video_loaded
        is_setting_scale_by_line = False
        if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line'):
            is_setting_scale_by_line = self.scale_panel_controller._is_setting_scale_by_line
        
        is_defining_any_line = is_setting_scale_by_line or self._is_defining_measurement_line
        nav_enabled_during_action = not is_defining_any_line

        if self.frameSlider: self.frameSlider.setEnabled(is_video_loaded and nav_enabled_during_action)
        if self.prevFrameButton: self.prevFrameButton.setEnabled(is_video_loaded and nav_enabled_during_action)
        if self.nextFrameButton: self.nextFrameButton.setEnabled(is_video_loaded and nav_enabled_during_action)

        can_play: bool = is_video_loaded and self.fps > 0 and nav_enabled_during_action
        if self.playPauseButton: self.playPauseButton.setEnabled(can_play)

        if hasattr(self, 'currentFrameLineEdit') and self.currentFrameLineEdit is not None:
            self.currentFrameLineEdit.setEnabled(is_video_loaded and nav_enabled_during_action)
        if hasattr(self, 'currentTimeLineEdit') and self.currentTimeLineEdit is not None:
            self.currentTimeLineEdit.setEnabled(is_video_loaded and nav_enabled_during_action)
        if hasattr(self, 'zoomLevelLineEdit') and self.zoomLevelLineEdit is not None:
            self.zoomLevelLineEdit.setEnabled(is_video_loaded and nav_enabled_during_action)
            if not is_video_loaded: self.zoomLevelLineEdit.setText("---.-")

        can_create_new_element = is_video_loaded and not is_defining_any_line
        if self.newTrackAction: 
            self.newTrackAction.setEnabled(can_create_new_element)
        if hasattr(self, 'newMeasurementLineAction') and self.newMeasurementLineAction:
            self.newMeasurementLineAction.setEnabled(can_create_new_element)
        
        if hasattr(self, 'newTrackButton') and self.newTrackButton:
            self.newTrackButton.setEnabled(can_create_new_element)

        if hasattr(self, 'newLineButton') and self.newLineButton:
            self.newLineButton.setEnabled(can_create_new_element)

        if self.autoAdvanceCheckBox: self.autoAdvanceCheckBox.setEnabled(is_video_loaded)
        if self.autoAdvanceSpinBox: self.autoAdvanceSpinBox.setEnabled(is_video_loaded)

        if self.playPauseButton and self.stop_icon and self.play_icon:
            self.playPauseButton.setIcon(self.stop_icon if self.is_playing else self.play_icon)
            self.playPauseButton.setToolTip("Stop Video (Space)" if self.is_playing else "Play Video (Space)")
        
        can_interact_with_project = is_video_loaded or (self.project_manager and self.project_manager.get_current_project_filepath() is not None)

        if hasattr(self, 'saveAction') and self.saveAction:
            self.saveAction.setEnabled(
                can_interact_with_project and self.project_manager.project_has_unsaved_changes()
            )
        
        if hasattr(self, 'saveProjectAsAction') and self.saveProjectAsAction:
            self.saveProjectAsAction.setEnabled(can_interact_with_project)
        
        if hasattr(self, 'closeProjectAction') and self.closeProjectAction:
            self.closeProjectAction.setEnabled(can_interact_with_project)
        
        if hasattr(self, 'loadProjectAction') and self.loadProjectAction:
            self.loadProjectAction.setEnabled(True) # Always enabled

        if self.videoInfoAction: self.videoInfoAction.setEnabled(is_video_loaded)

        has_tracks = any(el.get('type') == ElementType.TRACK for el in self.element_manager.elements) if self.element_manager else False
        has_lines = any(el.get('type') == ElementType.MEASUREMENT_LINE for el in self.element_manager.elements) if self.element_manager else False

        if hasattr(self, 'exportTracksCsvAction') and self.exportTracksCsvAction:
            self.exportTracksCsvAction.setEnabled(is_video_loaded and has_tracks)
        if hasattr(self, 'exportLinesCsvAction') and self.exportLinesCsvAction:
            self.exportLinesCsvAction.setEnabled(is_video_loaded and has_lines)

        if hasattr(self, 'saveTracksTableButton') and self.saveTracksTableButton:
            self.saveTracksTableButton.setEnabled(is_video_loaded and has_tracks)
        if hasattr(self, 'copyTracksTableButton') and self.copyTracksTableButton:
            self.copyTracksTableButton.setEnabled(is_video_loaded and has_tracks)
        
        if hasattr(self, 'saveLinesTableButton') and self.saveLinesTableButton:
            self.saveLinesTableButton.setEnabled(is_video_loaded and has_lines)
        if hasattr(self, 'copyLinesTableButton') and self.copyLinesTableButton:
            self.copyLinesTableButton.setEnabled(is_video_loaded and has_lines)

        if hasattr(self, 'exportViewAction') and self.exportViewAction:
            self.exportViewAction.setEnabled(is_video_loaded)
        if hasattr(self, 'exportFrameAction') and self.exportFrameAction:
            self.exportFrameAction.setEnabled(is_video_loaded)

        if hasattr(self, 'undoAction') and self.undoAction:
            self.undoAction.setEnabled(self.element_manager.can_undo_last_point_action() and is_video_loaded)

        if self.scale_panel_controller: self.scale_panel_controller.set_video_loaded_status(is_video_loaded)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_loaded_status(is_video_loaded)

        if self.table_data_controller: self.table_data_controller.set_video_loaded_status(is_video_loaded, self.total_frames if is_video_loaded else 0)

        if self.view_menu_controller:
            self.view_menu_controller.sync_all_menu_items_from_settings_and_panels()
        
        if self.project_manager:
             self._handle_unsaved_changes_state_changed(self.project_manager.project_has_unsaved_changes())

    def _update_ui_for_frame(self, frame_index: int) -> None:
        # ... (existing method)
        if not self.video_loaded:
            if hasattr(self, 'currentFrameLineEdit'): self.currentFrameLineEdit.blockSignals(True); self.currentFrameLineEdit.setReadOnly(True); self.currentFrameLineEdit.setText("-"); self.currentFrameLineEdit.deselect(); self.currentFrameLineEdit.blockSignals(False)
            if hasattr(self, 'totalFramesLabel'): self.totalFramesLabel.setText("/ -")
            if hasattr(self, 'currentTimeLineEdit'): self.currentTimeLineEdit.blockSignals(True); self.currentTimeLineEdit.setReadOnly(True); self.currentTimeLineEdit.setText("--:--.---"); self.currentTimeLineEdit.deselect(); self.currentTimeLineEdit.blockSignals(False)
            if hasattr(self, 'totalTimeLabel'): self.totalTimeLabel.setText("/ --:--.---")
            return

        if self.frameSlider: self.frameSlider.blockSignals(True); self.frameSlider.setValue(frame_index); self.frameSlider.blockSignals(False)
        if hasattr(self, 'currentFrameLineEdit') and isinstance(self.currentFrameLineEdit, QtWidgets.QLineEdit): self.currentFrameLineEdit.blockSignals(True); self.currentFrameLineEdit.setReadOnly(True) ; self.currentFrameLineEdit.setText(str(frame_index + 1)); self.currentFrameLineEdit.deselect(); self.currentFrameLineEdit.blockSignals(False)
        if hasattr(self, 'totalFramesLabel') and isinstance(self.totalFramesLabel, QtWidgets.QLabel): self.totalFramesLabel.setText(f"/ {self.total_frames}")
        if hasattr(self, 'currentTimeLineEdit') and isinstance(self.currentTimeLineEdit, QtWidgets.QLineEdit):
            current_ms = (frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
            self.currentTimeLineEdit.blockSignals(True); self.currentTimeLineEdit.setReadOnly(True); self.currentTimeLineEdit.setText(self._format_time(current_ms)); self.currentTimeLineEdit.deselect(); self.currentTimeLineEdit.blockSignals(False)
        if hasattr(self, 'totalTimeLabel') and isinstance(self.totalTimeLabel, QtWidgets.QLabel): self.totalTimeLabel.setText(f"/ {self._format_time(self.total_duration_ms)}")

    @QtCore.Slot()
    def _handle_frame_input_finished(self) -> None:
        # ... (existing method)
        if not self.video_loaded or not hasattr(self, 'currentFrameLineEdit') or not isinstance(self.currentFrameLineEdit, QtWidgets.QLineEdit): return
        line_edit = self.currentFrameLineEdit; status_bar = self.statusBar(); input_text = line_edit.text().strip()
        if line_edit.isReadOnly(): return
        try:
            target_frame_1_based = int(input_text); target_frame_0_based = target_frame_1_based - 1
            if 0 <= target_frame_0_based < self.total_frames:
                if self.current_frame_index != target_frame_0_based: self.video_handler.seek_frame(target_frame_0_based)
            elif status_bar: status_bar.showMessage(f"Invalid frame. Must be 1-{self.total_frames}.", 3000)
        except ValueError:
            if status_bar: status_bar.showMessage("Invalid frame input: Not a number.", 3000)
        finally: self._update_ui_for_frame(self.current_frame_index); line_edit.clearFocus()

    @QtCore.Slot()
    def _handle_time_input_finished(self) -> None:
        # ... (existing method)
        if not self.video_loaded or not hasattr(self, 'currentTimeLineEdit') or not isinstance(self.currentTimeLineEdit, QtWidgets.QLineEdit): return
        line_edit = self.currentTimeLineEdit; status_bar = self.statusBar(); input_text = line_edit.text().strip()
        if line_edit.isReadOnly(): return
        try:
            target_ms = self.video_handler.parse_time_to_ms(input_text)
            if target_ms is not None:
                target_frame_0_based = self.video_handler.time_ms_to_frame_index(target_ms)
                if target_frame_0_based is not None:
                    if self.current_frame_index != target_frame_0_based: self.video_handler.seek_frame(target_frame_0_based)
                elif status_bar: status_bar.showMessage("Time is out of video duration.", 3000)
            elif status_bar: status_bar.showMessage(f"Invalid time format or out of range [0 - {self._format_time(self.total_duration_ms)}].", 4000)
        except Exception as e:
            if status_bar: status_bar.showMessage("Error processing time input.", 3000)
        finally: self._update_ui_for_frame(self.current_frame_index); line_edit.clearFocus()

    @QtCore.Slot()
    def open_video(self) -> None:
        # ... (existing method)
        logger.info("Open Video action triggered."); status_bar = self.statusBar(); proceed_with_file_dialog = False
        if self.video_loaded: # Modified this condition slightly for clarity for project context
            # If a project is loaded (even if video part failed), prompt for closing that project.
            # Otherwise, if just a video is loaded without a project context, prompt for closing video.
            prompt_message = ("Opening a new video will close the current project and video. "
                              "Any unsaved project changes will be lost.\n\nDo you want to proceed?") \
                             if self.project_manager and self.project_manager.get_current_project_filepath() else \
                             ("Opening a new video will close the current video. "
                              "Any unsaved tracks will be lost.\n\nDo you want to proceed?")

            # Delegate to _trigger_close_project if a project might have unsaved changes
            if self.project_manager and self.project_manager.project_has_unsaved_changes():
                logger.info("Open Video: Current project has unsaved changes. Triggering close project flow first.")
                try:
                    self._trigger_close_project() # This handles save/discard/cancel
                    if self.project_manager.project_has_unsaved_changes(): # If user cancelled save/close
                        logger.info("Open Video: Close project was cancelled. Aborting opening new video.")
                        if status_bar: status_bar.showMessage("Open new video cancelled.", 3000)
                        return
                    # If close was successful (saved or discarded), proceed
                    proceed_with_file_dialog = True
                except Exception as e: # Should not happen if _trigger_close_project is robust
                    logger.error(f"Error during _trigger_close_project call from open_video: {e}")
                    proceed_with_file_dialog = False # Don't proceed if error
            else: # No project changes, or no project loaded, just ask to close video
                reply = QtWidgets.QMessageBox.question(self, "Confirm Open New Video", prompt_message,
                                                       QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                                       QtWidgets.QMessageBox.StandardButton.No)
                if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    proceed_with_file_dialog = True
                elif status_bar:
                    status_bar.showMessage("Open new video cancelled.", 3000)
                    return
        else: # No video currently loaded
            proceed_with_file_dialog = True

        if proceed_with_file_dialog:
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)")
            if not file_path:
                if status_bar: status_bar.showMessage("Video loading cancelled.", 3000)
                return
            
            # If a project was open, it should have been handled (saved/discarded/closed) above.
            # Now, explicitly clear any remaining project context before loading just a video.
            if self.project_manager and self.project_manager.get_current_project_filepath():
                logger.info("Clearing previous project state before opening standalone video.")
                self._release_video() # Ensure video resources are released
                self.project_manager.clear_project_state_for_close() # Clear project path and dirty flag
                self._reset_ui_after_video_close() # Full UI reset

            if self.video_loaded: # If a video (but no project) was loaded, release it
                self._release_video()

            if status_bar: status_bar.showMessage(f"Opening video: {os.path.basename(file_path)}...", 0)
            QtWidgets.QApplication.processEvents()
            self.video_handler.open_video(file_path)


    def _release_video(self) -> None:
        # ... (existing method)
        logger.info("Releasing video resources and resetting state...")
        self.video_handler.release_video(); self.video_loaded = False; self.total_frames = 0; self.current_frame_index = -1; self.fps = 0.0
        self.total_duration_ms = 0.0; self.video_filepath = ""; self.frame_width = 0; self.frame_height = 0; self.is_playing = False
        self.element_manager.reset(); self.scale_manager.reset(); self._reset_ui_after_video_close()
        logger.info("Video release and associated reset complete.")

    @QtCore.Slot()
    def _trigger_save_project_as(self) -> None:
        # ... (existing method)
        status_bar = self.statusBar()
        if not self.video_loaded and not (self.project_manager and self.project_manager.get_current_project_filepath()): # Allow save as if project loaded but video failed
            if status_bar: status_bar.showMessage("Cannot save project: No video or project data loaded.", 3000)
            # Allow saving project metadata even if video failed to load, if a project path is known
            if not (self.project_manager and self.project_manager.get_current_project_filepath()):
                 QtWidgets.QMessageBox.warning(self, "Save Project Error", "A video must be loaded or a project opened to save a project.")
                 return
        if not self.project_manager:
            if status_bar: status_bar.showMessage("Save Project Error: ProjectManager not initialized.", 3000)
            logger.error("Cannot save project: ProjectManager not initialized.")
            return

        logger.info("'Save Project As...' action triggered.") 
        
        current_project_path = self.project_manager.get_current_project_filepath()
        default_dir = os.path.dirname(current_project_path) if current_project_path else \
                      (os.path.dirname(self.video_filepath) if self.video_filepath and os.path.isdir(os.path.dirname(self.video_filepath)) else os.getcwd())
        
        base_video_name: str = os.path.splitext(os.path.basename(self.video_filepath))[0] if self.video_filepath else "untitled_project"
        default_filename = os.path.basename(current_project_path) if current_project_path else f"{base_video_name}_project.json"
        
        suggested_filepath: str = os.path.join(default_dir, default_filename)
        
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Project As...", suggested_filepath, "PyroTracker Project Files (*.json);;All Files (*)"
        )

        if not save_path:
            if status_bar: status_bar.showMessage("Save project cancelled.", 3000)
            logger.info("Project saving cancelled by user.")
            return
        
        if not save_path.lower().endswith(".json"):
            save_path += ".json"
            logger.info(f"Ensured .json extension. Path is now: {save_path}")

        if status_bar:
            status_bar.showMessage(f"Saving project to {os.path.basename(save_path)}...", 0) 
        QtWidgets.QApplication.processEvents()

        success = self.project_manager.save_project(save_path) 

        if success:
            if status_bar: status_bar.showMessage(f"Project saved to {os.path.basename(save_path)}", 5000)
            # self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION} - {os.path.basename(save_path)}") # This is handled by dirty state
        else:
            if status_bar: status_bar.showMessage("Error saving project. See log.", 5000)
            QtWidgets.QMessageBox.critical(self, "Save Project Error", f"Could not save project to {save_path}.\nPlease check the logs for details.")
        
        self._update_ui_state() 

    @QtCore.Slot()
    def _trigger_close_project(self) -> None:
        # ... (existing method)
        logger.info("'Close Project' action triggered.")
        status_bar = self.statusBar()

        if not self.video_loaded and not (self.project_manager and self.project_manager.get_current_project_filepath()):
            if status_bar: status_bar.showMessage("No project is currently open.", 3000)
            return 

        if self.project_manager and self.project_manager.project_has_unsaved_changes():
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Unsaved Changes",
                "The current project has unsaved changes. Do you want to save before closing?",
                QtWidgets.QMessageBox.StandardButton.Save |
                QtWidgets.QMessageBox.StandardButton.Discard | 
                QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Cancel
            )

            if reply == QtWidgets.QMessageBox.StandardButton.Save:
                self._trigger_save_project_direct() 
                if self.project_manager.project_has_unsaved_changes():
                    logger.info("Save was cancelled or failed during close project prompt. Aborting close.")
                    if status_bar: status_bar.showMessage("Close project aborted.", 3000)
                    return 
            elif reply == QtWidgets.QMessageBox.StandardButton.Cancel:
                logger.info("Close project cancelled by user.")
                if status_bar: status_bar.showMessage("Close project cancelled.", 3000)
                return
            
        logger.info("Closing current project.")
        self._release_video() 

        if self.project_manager:
            self.project_manager.clear_project_state_for_close() 

        if status_bar: status_bar.showMessage("Project closed. Ready.", 3000)
        # self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}") # Handled by dirty state / _update_ui_state

    @QtCore.Slot()
    def _trigger_load_project(self) -> None:
        # ... (existing method)
        logger.info("Load Project action triggered by user.")
        status_bar = self.statusBar()
        if not self.project_manager:
            if status_bar: status_bar.showMessage("Load Project Error: ProjectManager not initialized.", 3000)
            logger.error("Cannot load project: ProjectManager not initialized.")
            return
    
        try:
            self._prepare_for_project_load() 
        except InterruptedError as e:
            logger.info(f"Project loading process interrupted during preparation: {e}")
            if status_bar: status_bar.showMessage("Project loading cancelled.", 3000)
            self._update_ui_state() 
            if self.view_menu_controller:
                self.view_menu_controller.sync_all_menu_items_from_settings_and_panels()
            return
    
        start_dir = os.path.dirname(self.video_filepath) if self.video_filepath and os.path.isdir(os.path.dirname(self.video_filepath)) else os.getcwd()
        load_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Project File", start_dir, "PyroTracker Project Files (*.json);;All Files (*)"
        )
    
        if not load_path:
            if status_bar: status_bar.showMessage("Load project cancelled.", 3000)
            logger.info("Project loading cancelled by user (file dialog).")
            self._update_ui_state()
            if self.view_menu_controller:
                self.view_menu_controller.sync_all_menu_items_from_settings_and_panels()
            return
    
        if status_bar: status_bar.showMessage(f"Loading project from {os.path.basename(load_path)}...", 0)
        QtWidgets.QApplication.processEvents()
    
        self._project_load_warnings = [] 
        loaded_state_dict: Optional[Dict[str, Any]] = None
        project_applied_successfully = False
        video_loaded_for_this_project = False 
    
        try:
            self.project_manager._is_loading_project = True 
            logger.debug("MainWindow: Set ProjectManager._is_loading_project to True.")
    
            loaded_state_dict = self.project_manager.load_project_file_data(load_path) 
    
            if loaded_state_dict:
                project_metadata = loaded_state_dict.get('metadata', {})
                saved_video_filename_from_project = project_metadata.get(config.META_FILENAME)
    
                video_width_for_apply = 0
                video_height_for_apply = 0
                total_frames_for_apply = 0
                fps_for_apply = 0.0
    
                if saved_video_filename_from_project and saved_video_filename_from_project != "N/A":
                    project_dir = os.path.dirname(load_path)
                    potential_video_path = os.path.join(project_dir, saved_video_filename_from_project)
                    logger.info(f"Project specifies video: '{saved_video_filename_from_project}'. Attempting to open from: '{potential_video_path}'.")
                    
                    self.video_handler.open_video(potential_video_path) 
                    video_loaded_for_this_project = self.video_handler.is_loaded 
    
                    if video_loaded_for_this_project:
                        logger.info(f"Video '{saved_video_filename_from_project}' loaded successfully for the project.")
                        video_width_for_apply = self.frame_width
                        video_height_for_apply = self.frame_height
                        total_frames_for_apply = self.total_frames
                        fps_for_apply = self.fps
                    else:
                        msg = f"Video '{saved_video_filename_from_project}' from project not found or failed to load from '{potential_video_path}'. Project data will be applied using metadata for context if available."
                        logger.warning(msg)
                        self._project_load_warnings.append(msg)
                        QtWidgets.QMessageBox.warning(self, "Video Not Found", msg)
                        video_width_for_apply = int(project_metadata.get(config.META_WIDTH, 0))
                        video_height_for_apply = int(project_metadata.get(config.META_HEIGHT, 0))
                        total_frames_for_apply = int(project_metadata.get(config.META_FRAMES, 0))
                        fps_for_apply = float(project_metadata.get(config.META_FPS, 0.0))
                else:
                    logger.info("Project file does not specify a video. No video loaded automatically.")
                    if self.video_loaded: 
                        self._release_video() 
                    video_width_for_apply = int(project_metadata.get(config.META_WIDTH, 0))
                    video_height_for_apply = int(project_metadata.get(config.META_HEIGHT, 0))
                    total_frames_for_apply = int(project_metadata.get(config.META_FRAMES, 0))
                    fps_for_apply = float(project_metadata.get(config.META_FPS, 0.0))
    
                project_applied_successfully = self.project_manager.apply_project_state(
                    loaded_state_dict,
                    video_loaded_for_this_project, 
                    video_width_for_apply,
                    video_height_for_apply,
                    total_frames_for_apply,
                    fps_for_apply
                )
    
                if project_applied_successfully:
                    self.project_manager.mark_project_as_loaded(load_path) 
                    
                    final_status_message = f"Project loaded from {os.path.basename(load_path)}"
                    if self._project_load_warnings:
                        final_status_message += f" with {len(self._project_load_warnings)} warning(s)."
                    if status_bar: status_bar.showMessage(final_status_message, 7000)
                else:
                    if status_bar: status_bar.showMessage("Error applying project settings/elements. See log.", 5000)
            
            else: 
                if status_bar: status_bar.showMessage("Failed to read project file. See log.", 5000)
                project_applied_successfully = False 
    
        except (FileNotFoundError, PermissionError, json.JSONDecodeError, ValueError) as e:
            if status_bar: status_bar.showMessage(f"Error reading project file: {e}", 5000)
            logger.error(f"Error reading project file: {e}", exc_info=True)
            project_applied_successfully = False
        except Exception as e:
            if status_bar: status_bar.showMessage(f"Critical error during project load: {str(e)}", 5000)
            logger.error(f"A critical error occurred during project loading sequence: {e}", exc_info=True)
            project_applied_successfully = False
        finally:
            logger.debug("MainWindow._trigger_load_project: Entering finally block for UI updates and flag reset.")
            
            if self.table_data_controller: 
                self.table_data_controller.update_tracks_table_ui()
                if self.table_data_controller._lines_table:
                    self.table_data_controller.update_lines_table_ui()
                self.table_data_controller.update_points_table_ui()
            if self.coord_panel_controller: 
                self.coord_panel_controller.update_ui_display()
            if self.scale_panel_controller: 
                self.scale_panel_controller.update_ui_from_manager()
            
            self._update_ui_state() 
            
            if self.view_menu_controller: 
                self.view_menu_controller.sync_all_menu_items_from_settings_and_panels()
            
            if not video_loaded_for_this_project:
                 if self.imageView:
                    self.imageView.clearOverlay()
                    self.imageView.setPixmap(QtGui.QPixmap()) 
    
            if self.project_manager:
                self.project_manager._is_loading_project = False 
                logger.debug("MainWindow: ProjectManager._is_loading_project set to False.")
    
                if project_applied_successfully:
                    self.project_manager.unsavedChangesStateChanged.emit(self.project_manager.project_has_unsaved_changes())
                else:
                    if loaded_state_dict is not None or load_path: 
                         if not self.video_loaded: 
                            self.project_manager.clear_project_state_for_close() 
                         self.project_manager.set_project_dirty(True) 
                         self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION} (Load Failed)")
    
            logger.info("Project loading attempt finished in MainWindow.")


    @QtCore.Slot()
    def _show_preferences_dialog(self) -> None:
        # ... (existing method)
        dialog = PreferencesDialog(self); dialog.settingsApplied.connect(self._handle_settings_applied); dialog.exec()

    @QtCore.Slot()
    def _handle_settings_applied(self) -> None:
        # ... (existing method)
        logger.info("MainWindow: Settings applied, refreshing visuals.")
        self._setup_pens()
        if self.imageView and hasattr(self.imageView, '_scale_bar_widget') and self.imageView._scale_bar_widget:
            self.imageView._scale_bar_widget.update_appearance_from_settings()
            if self.imageView._scale_bar_widget.isVisible(): self.imageView._update_overlay_widget_positions()
        if self.imageView: self.imageView.refresh_info_overlay_appearance()
        self._redraw_scene_overlay()
        if self.imageView and self.scale_manager and hasattr(self, 'showScaleBarCheckBox') and self.showScaleBarCheckBox and self.showScaleBarCheckBox.isChecked():
            current_m_per_px = self.scale_manager.get_scale_m_per_px()
            if current_m_per_px is not None: self.imageView.update_scale_bar_dimensions(current_m_per_px)
        if self.view_menu_controller: self.view_menu_controller.handle_preferences_applied()

    @QtCore.Slot(int)
    def _slider_value_changed(self, value: int) -> None:
        # ... (existing method)
        if self.video_loaded and self.current_frame_index != value: self.video_handler.seek_frame(value)

    @QtCore.Slot(int)
    def _handle_frame_step(self, step: int) -> None:
        # ... (existing method)
        if self.video_loaded: self.video_handler.next_frame() if step > 0 else self.video_handler.previous_frame()

    @QtCore.Slot()
    def _show_previous_frame(self) -> None:
        # ... (existing method)
        if self.video_loaded: self.video_handler.previous_frame()

    @QtCore.Slot()
    def _show_next_frame(self) -> None:
        # ... (existing method)
        if self.video_loaded: self.video_handler.next_frame()

    @QtCore.Slot()
    def _toggle_playback(self) -> None:
        # ... (existing method)
        if self.video_loaded and self.fps > 0: self.video_handler.toggle_playback()

    @QtCore.Slot()
    def _update_zoom_display(self) -> None:
        # ... (existing method)
        if not self.video_loaded or not hasattr(self, 'imageView') or not hasattr(self, 'zoomLevelLineEdit') or self.zoomLevelLineEdit is None:
            if hasattr(self, 'zoomLevelLineEdit') and self.zoomLevelLineEdit is not None: self.zoomLevelLineEdit.setText("---.-")
            return
        if self.zoomLevelLineEdit.hasFocus(): return
        try:
            min_scale = self.imageView.get_min_view_scale()
            if min_scale <= 0: self.zoomLevelLineEdit.setText("---.-"); return
            current_view_scale = self.imageView.transform().m11(); zoom_percentage = (current_view_scale / min_scale) * 100.0
            self.zoomLevelLineEdit.blockSignals(True); self.zoomLevelLineEdit.setText(f"{zoom_percentage:.1f}"); self.zoomLevelLineEdit.blockSignals(False)
        except Exception as e: self.zoomLevelLineEdit.setText("ERR")

    @QtCore.Slot()
    def _handle_zoom_input_finished(self) -> None:
        # ... (existing method)
        if not self.video_loaded or not hasattr(self, 'imageView') or not hasattr(self, 'zoomLevelLineEdit') or self.zoomLevelLineEdit is None: return
        line_edit = self.zoomLevelLineEdit; status_bar = self.statusBar(); input_text = line_edit.text().strip()
        if line_edit.isReadOnly(): return
        try:
            entered_percentage = float(input_text); min_view_scale = self.imageView.get_min_view_scale(); max_view_scale = self.imageView.get_max_view_scale()
            if min_view_scale <= 0:
                if status_bar: status_bar.showMessage("Error: Cannot determine zoom limits.", 3000)
                self._update_zoom_display(); line_edit.clearFocus(); return
            min_percentage = 100.0; max_percentage = (max_view_scale / min_view_scale) * 100.0 + 0.01
            if not (min_percentage <= entered_percentage <= max_percentage):
                if status_bar: status_bar.showMessage(f"Zoom must be {min_percentage:.0f}% - {max_percentage:.0f}%.", 3000)
                self._update_zoom_display()
            else:
                current_view_scale = self.imageView.transform().m11(); target_view_scale = (entered_percentage / 100.0) * min_view_scale
                if not math.isclose(current_view_scale, target_view_scale, rel_tol=1e-3):
                    zoom_factor_to_apply = target_view_scale / current_view_scale; viewport_center = self.imageView.viewport().rect().center()
                    self.imageView._zoom(zoom_factor_to_apply, viewport_center)
                else: self._update_zoom_display()
        except ValueError:
            if status_bar: status_bar.showMessage("Invalid zoom input: Not a number.", 3000)
            self._update_zoom_display()
        finally: line_edit.setReadOnly(True); line_edit.clearFocus()

    @QtCore.Slot(dict)
    def _handle_video_loaded(self, video_info: Dict[str, Any]) -> None:
        # ... (existing method)
        self.total_frames = video_info.get('total_frames', 0); self.video_loaded = True; self.fps = video_info.get('fps', 0.0)
        self.total_duration_ms = video_info.get('duration_ms', 0.0); self.video_filepath = video_info.get('filepath', ''); self.frame_width = video_info.get('width', 0)
        self.frame_height = video_info.get('height', 0); self.is_playing = False; # self.setWindowTitle - handled by dirty state
        self.coord_transformer.set_video_height(self.frame_height)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_height(self.frame_height)
        self.element_manager.reset()
        if self.frameSlider: self.frameSlider.setMaximum(self.total_frames - 1 if self.total_frames > 0 else 0); self.frameSlider.setValue(0)
        if self.imageView:
            self.imageView.resetInitialLoadFlag()
            self.imageView.set_info_overlay_video_data(filename=video_info.get('filename', 'N/A'), total_frames=self.total_frames, total_duration_ms=self.total_duration_ms)
            self.imageView.refresh_info_overlay_appearance()
        self.scale_manager.reset()
        if self.scale_panel_controller: self.scale_panel_controller.set_video_loaded_status(True)
        if self.coord_panel_controller: self.coord_panel_controller.set_video_loaded_status(True)
        if self.table_data_controller: self.table_data_controller.set_video_loaded_status(True, self.total_frames)
        self._update_zoom_display(); self._update_ui_state() # Calls _handle_unsaved_changes_state_changed
        if self.view_menu_controller: self.view_menu_controller.handle_video_loaded_state_changed(True)
        status_msg = (f"Loaded '{video_info.get('filename', 'N/A')}' ({self.total_frames} frames, {self.frame_width}x{self.frame_height}, {self.fps:.2f} FPS)")
        if self.statusBar(): self.statusBar().showMessage(status_msg, 5000)
        if self.project_manager: self.project_manager.set_project_dirty(False) # Video load without project is considered 'clean' initially

    @QtCore.Slot(str)
    def _handle_video_load_failed(self, error_msg: str) -> None:
        # ... (existing method)
        QtWidgets.QMessageBox.critical(self, "Video Load Error", error_msg)
        if self.statusBar(): self.statusBar().showMessage("Error loading video", 5000)
        self._release_video()

    @QtCore.Slot(QtGui.QPixmap, int)
    def _handle_frame_changed(self, pixmap: QtGui.QPixmap, frame_index: int) -> None:
        # ... (existing method)
        if not self.video_loaded: return
        self.current_frame_index = frame_index
        if self.imageView:
            self.imageView.setPixmap(pixmap)
            current_time_ms = (self.current_frame_index / self.fps) * 1000 if self.fps > 0 else 0.0
            self.imageView.set_info_overlay_current_frame_time(self.current_frame_index, current_time_ms)
        self._update_ui_for_frame(frame_index); self._redraw_scene_overlay()
        if self.imageView and self.scale_manager and hasattr(self, 'showScaleBarCheckBox') and self.showScaleBarCheckBox and self.showScaleBarCheckBox.isChecked():
            current_m_per_px = self.scale_manager.get_scale_m_per_px()
            if current_m_per_px is not None: self.imageView.update_scale_bar_dimensions(current_m_per_px)

    @QtCore.Slot(bool)
    def _handle_playback_state_changed(self, is_playing: bool) -> None:
        # ... (existing method)
        self.is_playing = is_playing; status_bar = self.statusBar()
        if self.playPauseButton and self.stop_icon and self.play_icon:
            self.playPauseButton.setIcon(self.stop_icon if self.is_playing else self.play_icon)
            self.playPauseButton.setToolTip("Stop Video (Space)" if self.is_playing else "Play Video (Space)")
            if self.is_playing and status_bar: status_bar.showMessage("Playing...", 0)
            elif status_bar: status_bar.showMessage("Stopped." if self.video_loaded else "Ready.", 3000)
        self._update_ui_state()

    @QtCore.Slot(float, float)
    def _handle_add_point_click(self, x: float, y: float) -> None:
        # ... (existing method)
        if self._is_defining_measurement_line: logger.debug("_handle_add_point_click: Ignoring as currently defining a measurement line."); return
        status_bar = self.statusBar()
        if self.coord_panel_controller and self.coord_panel_controller.is_setting_origin_mode(): return
        if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and self.scale_panel_controller._is_setting_scale_by_line: return
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Cannot add point: No video loaded.", 3000); return
        if self.element_manager.active_element_index == -1:
            if status_bar: status_bar.showMessage("Select a track to add points.", 3000); return
        time_ms = (self.current_frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
        if self.element_manager.add_point(self.current_frame_index, time_ms, x, y):
            x_d, y_d = self.coord_transformer.transform_point_for_display(x,y); active_id = self.element_manager.get_active_element_id()
            msg = f"Point for Track {active_id} on Frame {self.current_frame_index+1}: ({x_d:.1f}, {y_d:.1f})"
            if status_bar: status_bar.showMessage(msg, 3000)
            if self._auto_advance_enabled and self._auto_advance_frames > 0:
                target = min(self.current_frame_index + self._auto_advance_frames, self.total_frames - 1)
                if target > self.current_frame_index: self.video_handler.seek_frame(target)
        elif status_bar: status_bar.showMessage("Failed to add point (see log).", 3000)
        if hasattr(self, 'undoAction') and self.undoAction: self.undoAction.setEnabled(self.element_manager.can_undo_last_point_action())

    @QtCore.Slot(float, float, QtCore.Qt.KeyboardModifiers)
    def _handle_modified_click(self, x: float, y: float, modifiers: QtCore.Qt.KeyboardModifiers) -> None:
        # ... (existing method)
        status_bar = self.statusBar()
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Cannot interact: Video/components not ready.", 3000); return
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            result = self.element_manager.find_closest_visible_point(x, y, self.current_frame_index)
            if result is None:
                if self.element_manager.active_element_index != -1: self.element_manager.set_active_element(-1); 
                if status_bar: status_bar.showMessage("Track deselected." if self.element_manager.active_element_index == -1 else "No track to deselect.", 3000)
                return
        result = self.element_manager.find_closest_visible_point(x, y, self.current_frame_index)
        if result is None:
            if modifiers != QtCore.Qt.KeyboardModifier.ControlModifier and status_bar: status_bar.showMessage("No track marker found near click.", 3000)
            return
        element_idx, point_data = result; element_id = -1
        if 0 <= element_idx < len(self.element_manager.elements): element_id = self.element_manager.elements[element_idx]['id']
        if element_id == -1: return
        frame_idx_of_point = point_data[0]
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            if self.element_manager.active_element_index != element_idx:
                self.element_manager.set_active_element(element_idx)
                if self.table_data_controller: QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_element_row_by_id_in_ui(element_id, self.tracksTableWidget, config.COL_TRACK_ID)) # Specify table
                if status_bar: status_bar.showMessage(f"Selected Track {element_id}.", 3000)
        elif modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:
            if self.element_manager.active_element_index != element_idx: self.element_manager.set_active_element(element_idx)
            if self.table_data_controller: QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_element_row_by_id_in_ui(element_id, self.tracksTableWidget, config.COL_TRACK_ID)) # Specify table
            if self.current_frame_index != frame_idx_of_point: self.video_handler.seek_frame(frame_idx_of_point)
            if status_bar: status_bar.showMessage(f"Selected Track {element_id}, jumped to Frame {frame_idx_of_point + 1}.", 3000)

    @QtCore.Slot(float, float)
    def _handle_scale_or_measurement_line_first_point(self, scene_x: float, scene_y: float) -> None:
        # ... (existing method)
        if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and \
           self.scale_panel_controller._is_setting_scale_by_line:
            logger.debug("MainWindow: First point click routed to ScalePanelController.")
            self.scale_panel_controller._on_image_view_scale_line_point1_clicked(scene_x, scene_y)
        elif self._is_defining_measurement_line:
            logger.debug("MainWindow: First point click routed for Measurement Line definition.")
            self._handle_measurement_line_first_point_defined(scene_x, scene_y)
        else:
            logger.debug("MainWindow: First point click ignored, no relevant definition mode active.")

    @QtCore.Slot(float, float, float, float)
    def _handle_scale_or_measurement_line_second_point(self, p1x: float, p1y: float, p2x: float, p2y: float) -> None:
        # ... (existing method)
        if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and \
           self.scale_panel_controller._is_setting_scale_by_line:
            logger.debug("MainWindow: Second point click routed to ScalePanelController.")
            self.scale_panel_controller._on_image_view_scale_line_point2_clicked(p1x, p1y, p2x, p2y)
        elif self._is_defining_measurement_line:
            logger.debug("MainWindow: Second point click routed for Measurement Line definition.")
            self._handle_measurement_line_second_point_defined(p1x, p1y, p2x, p2y)
        else:
            logger.debug("MainWindow: Second point click ignored, no relevant definition mode active.")

    @QtCore.Slot(float, float)
    def _handle_measurement_line_first_point_defined(self, scene_x: float, scene_y: float) -> None:
        # ... (existing method)
        status_bar = self.statusBar()
        if not self._is_defining_measurement_line or not self.imageView or self.imageView._current_mode != InteractionMode.SET_SCALE_LINE_START:
             logger.debug("_handle_measurement_line_first_point_defined called out of context or wrong ImageView mode.")
             return
        if self.element_manager.active_element_index == -1 or self.element_manager.get_active_element_type() != ElementType.MEASUREMENT_LINE:
            logger.warning("No active measurement line. Cancelling."); self._cancel_active_line_definition_ui_reset(); return
        logger.info(f"Measurement Line: First point for ID {self.element_manager.get_active_element_id()} at ({scene_x:.2f}, {scene_y:.2f}) on frame {self._current_line_definition_frame_index}")
        time_ms = (self._current_line_definition_frame_index / self.fps) * 1000 if self.fps > 0 else 0.0
        if self.element_manager.add_point(self._current_line_definition_frame_index, time_ms, scene_x, scene_y):
            active_line_id = self.element_manager.get_active_element_id()
            if status_bar: status_bar.showMessage(f"Line {active_line_id} - First point. Click second point on Frame {self._current_line_definition_frame_index + 1}. (Esc to cancel)", 0)
            self.imageView.set_interaction_mode(InteractionMode.SET_SCALE_LINE_END)
        else:
            logger.error("ElementManager failed to process first point for measurement line.")
            if status_bar: status_bar.showMessage("Error setting first line point. Cancelling.", 3000)
            self._cancel_active_line_definition_ui_reset()

    @QtCore.Slot(float, float, float, float)
    def _handle_measurement_line_second_point_defined(self, p1x: float, p1y: float, p2x: float, p2y: float) -> None:
        # ... (existing method)
        status_bar = self.statusBar()
        if not self._is_defining_measurement_line or not self.imageView or self.imageView._current_mode != InteractionMode.SET_SCALE_LINE_END:
            logger.debug("_handle_measurement_line_second_point_defined called out of context or wrong ImageView mode.")
            return
        if self.element_manager.active_element_index == -1 or self.element_manager.get_active_element_type() != ElementType.MEASUREMENT_LINE or self.element_manager._defining_element_first_point_data is None:
            logger.warning("No active measurement line or first point not set. Cancelling."); self._cancel_active_line_definition_ui_reset(); return
        logger.info(f"Measurement Line: Second point for ID {self.element_manager.get_active_element_id()} at ({p2x:.2f}, {p2y:.2f}) on frame {self._current_line_definition_frame_index}")
        time_ms = (self._current_line_definition_frame_index / self.fps) * 1000 if self.fps > 0 else 0.0
        if self.element_manager.add_point(self._current_line_definition_frame_index, time_ms, p2x, p2y):
            active_line_id = self.element_manager.get_active_element_id()
            if status_bar: status_bar.showMessage(f"Measurement Line {active_line_id} defined.", 3000)
            self._is_defining_measurement_line = False; self.imageView.set_interaction_mode(InteractionMode.NORMAL)
            self.imageView.clearTemporaryScaleVisuals(); self._handle_disable_frame_navigation(False); self._update_ui_state()
        else:
            logger.error("ElementManager failed to process second point for measurement line (e.g., frame mismatch).")
            if status_bar: status_bar.showMessage("Error: Second point must be on the same frame. Line not defined.", 4000)

    @QtCore.Slot(int)
    def _handle_auto_advance_toggled(self, state: int) -> None: self._auto_advance_enabled = (state == QtCore.Qt.CheckState.Checked.value)
    @QtCore.Slot(int)
    def _handle_auto_advance_frames_changed(self, value: int) -> None: self._auto_advance_frames = value
    @QtCore.Slot()
    def _create_new_track(self) -> None:
        # ... (existing method)
        status_bar = self.statusBar()
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Load a video first to create tracks.", 3000); return
        new_id = self.element_manager.create_new_track()
        if status_bar: status_bar.showMessage(f"Created Track {new_id}. It is now active.", 3000)
        if self.table_data_controller: QtCore.QTimer.singleShot(0, lambda: self.table_data_controller._select_element_row_by_id_in_ui(new_id, self.tracksTableWidget, config.COL_TRACK_ID)) # Specify table
        if self.dataTabsWidget: self.dataTabsWidget.setCurrentIndex(0)
        self._update_ui_state()

    @QtCore.Slot()
    def _create_new_line_action(self) -> None: # Renamed from _create_new_line_action
        # ... (existing method)
        status_bar = self.statusBar()
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("Load a video first to create a measurement line.", 3000); return
        if self._is_defining_measurement_line:
            logger.info("New Line clicked while another was being defined. Cancelling previous.")
            self._cancel_active_line_definition_ui_reset()
            if status_bar: status_bar.showMessage("Previous line definition cancelled. Starting new line.", 2000)
        if self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and self.scale_panel_controller._is_setting_scale_by_line:
            self.scale_panel_controller.cancel_set_scale_by_line()
        if self.coord_panel_controller and self.coord_panel_controller.is_setting_origin_mode():
            self.coord_panel_controller._is_setting_origin = False
            if self.imageView: self.imageView.set_interaction_mode(InteractionMode.NORMAL)
        new_line_id = self.element_manager.create_new_line()
        if new_line_id != -1:
            self._is_defining_measurement_line = True; self._current_line_definition_frame_index = self.current_frame_index
            if status_bar: status_bar.showMessage(f"Defining Line {new_line_id}: Click first point on Frame {self.current_frame_index + 1}. (Esc to cancel)", 0)
            if hasattr(self, 'dataTabsWidget') and self.dataTabsWidget and hasattr(self, 'linesTableWidget') and self.linesTableWidget:
                # Find the "Measurement Lines" tab and switch to it
                for i in range(self.dataTabsWidget.count()):
                    if self.dataTabsWidget.tabText(i) == "Measurement Lines":
                         self.dataTabsWidget.setCurrentIndex(i); break
            if self.imageView: self.imageView.set_interaction_mode(InteractionMode.SET_SCALE_LINE_START)
            self._handle_disable_frame_navigation(True); self._update_ui_state()
        elif status_bar: status_bar.showMessage("Failed to create new measurement line.", 3000)

    @QtCore.Slot(bool)
    def _handle_disable_frame_navigation(self, disable: bool) -> None:
        # ... (existing method)
        logger.debug(f"Setting frame navigation controls disabled: {disable}")
        enabled = not disable and self.video_loaded
        if self.frameSlider: self.frameSlider.setEnabled(enabled)
        if self.playPauseButton: self.playPauseButton.setEnabled(enabled and self.fps > 0)
        if self.prevFrameButton: self.prevFrameButton.setEnabled(enabled)
        if self.nextFrameButton: self.nextFrameButton.setEnabled(enabled)
        status_bar = self.statusBar()
        if disable:
            message = "Frame navigation disabled while defining scale."
            if self._is_defining_measurement_line:
                message = "Frame navigation disabled while defining measurement line."
            elif self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and self.scale_panel_controller._is_setting_scale_by_line:
                pass 
            else: 
                message = "Frame navigation disabled."
            if status_bar: status_bar.showMessage(message, 0)
        elif status_bar and status_bar.currentMessage().startswith("Frame navigation disabled"):
            status_bar.clearMessage()
        if not disable:
            self._update_ui_state()


    @QtCore.Slot()
    def _redraw_scene_overlay(self) -> None:
        # ... (existing method)
        if not (self.imageView and self.imageView._scene and self.video_loaded and self.current_frame_index >= 0):
            if self.imageView: self.imageView.clearOverlay()
            return

        scene = self.imageView._scene
        self.imageView.clearOverlay() 

        try:
            marker_sz = float(settings_manager.get_setting(settings_manager.KEY_MARKER_SIZE))
            visual_elements_to_draw = self.element_manager.get_visual_elements(
                self.current_frame_index,
                self.scale_manager
            )

            pens = {
                config.STYLE_MARKER_ACTIVE_CURRENT: self.pen_marker_active_current,
                config.STYLE_MARKER_ACTIVE_OTHER: self.pen_marker_active_other,
                config.STYLE_MARKER_INACTIVE_CURRENT: self.pen_marker_inactive_current,
                config.STYLE_MARKER_INACTIVE_OTHER: self.pen_marker_inactive_other,
                config.STYLE_LINE_ACTIVE: self.pen_line_active,
                config.STYLE_LINE_INACTIVE: self.pen_line_inactive,
                config.STYLE_MEASUREMENT_LINE_NORMAL: self.pen_measurement_line_normal,
                config.STYLE_MEASUREMENT_LINE_ACTIVE: self.pen_measurement_line_active,
            }

            items_to_add_to_scene: List[QtWidgets.QGraphicsItem] = []

            for el in visual_elements_to_draw:
                el_type = el.get('type')
                style_key = el.get('style')
                pen = pens.get(style_key)
                item: Optional[QtWidgets.QGraphicsItem] = None

                if el_type == 'marker' and el.get('pos'):
                    if not pen:
                        logger.warning(f"No pen defined for marker style '{style_key}'. Skipping.")
                        continue
                    x, y = el['pos']
                    item = graphics_utils.create_marker_qgraphicsitem(QtCore.QPointF(x, y), marker_sz, pen, z_value=10)

                elif el_type == 'line' and el.get('p1') and el.get('p2'):
                    if not pen:
                        logger.warning(f"No pen defined for line style '{style_key}'. Skipping.")
                        continue
                    p1_coords, p2_coords = el['p1'], el['p2']
                    z_value = 9
                    if style_key in [config.STYLE_MEASUREMENT_LINE_NORMAL, config.STYLE_MEASUREMENT_LINE_ACTIVE]:
                        z_value = 9.5
                    item = graphics_utils.create_line_qgraphicsitem(QtCore.QPointF(p1_coords[0], p1_coords[1]), QtCore.QPointF(p2_coords[0], p2_coords[1]), pen, z_value=z_value)

                elif el_type == 'text' and el.get('label_type') == 'measurement_line_length':
                    text_string = el.get('text')
                    line_p1_coords_tuple = el.get('line_p1')
                    line_p2_coords_tuple = el.get('line_p2')
                    font_size_pt = el.get('font_size')
                    q_color = el.get('color')

                    if not all([text_string, line_p1_coords_tuple, line_p2_coords_tuple,
                                isinstance(font_size_pt, int), isinstance(q_color, QtGui.QColor)]):
                        logger.warning(f"Incomplete data for text visual element (ID: {el.get('element_id')}). Skipping label.")
                        continue
                    
                    item = graphics_utils.create_text_label_qgraphicsitem(
                        text=text_string,
                        line_p1=QtCore.QPointF(line_p1_coords_tuple[0], line_p1_coords_tuple[1]),
                        line_p2=QtCore.QPointF(line_p2_coords_tuple[0], line_p2_coords_tuple[1]),
                        font_size=font_size_pt,
                        color=q_color,
                        scene_context_rect=self.imageView.sceneRect(),
                        z_value=12 
                    )

                if item:
                    items_to_add_to_scene.append(item)

            for item_to_add in items_to_add_to_scene:
                scene.addItem(item_to_add)

            if self.coord_panel_controller and self.coord_panel_controller.get_show_origin_marker_status():
                origin_sz = float(settings_manager.get_setting(settings_manager.KEY_ORIGIN_MARKER_SIZE))
                ox, oy = self.coord_transformer.get_current_origin_tl()
                r_orig = origin_sz / 2.0
                
                origin_pen_cosmetic = QtGui.QPen(self.pen_origin_marker)
                origin_pen_cosmetic.setCosmetic(True)

                origin_item = QtWidgets.QGraphicsEllipseItem(ox - r_orig, oy - r_orig, origin_sz, origin_sz)
                origin_item.setPen(origin_pen_cosmetic)
                origin_item.setBrush(self.pen_origin_marker.color())
                origin_item.setZValue(11)
                scene.addItem(origin_item)

            if self.showScaleLineCheckBox and self.showScaleLineCheckBox.isChecked() and \
               self.scale_manager and self.scale_manager.has_defined_scale_line():
                line_data_tuple = self.scale_manager.get_defined_scale_line_data()
                scale_m_per_px = self.scale_manager.get_scale_m_per_px()

                if line_data_tuple and scale_m_per_px is not None and scale_m_per_px > 0:
                    p1x, p1y, p2x, p2y = line_data_tuple
                    
                    dx = p2x - p1x
                    dy = p2y - p1y
                    pixel_length = math.sqrt(dx*dx + dy*dy)
                    meter_length = pixel_length * scale_m_per_px
                    
                    length_text = "Err"
                    if hasattr(self, '_export_handler') and self._export_handler:
                        length_text = self._export_handler.format_length_value_for_line(meter_length)
                    else: 
                        logger.warning("_redraw_scene_overlay: _export_handler not available for formatting scale line length.")
                        length_text = f"{meter_length:.2f} m" 
                    
                    line_clr = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_COLOR)
                    text_clr = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_COLOR)
                    font_sz = int(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_SIZE))
                    pen_w = float(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_WIDTH))
                    show_ticks = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_SHOW_TICKS)
                    tick_factor = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR)

                    defined_line_pen = QtGui.QPen(line_clr, pen_w)

                    created_items = graphics_utils.create_defined_scale_display_items(
                        p1x=p1x, p1y=p1y, p2x=p2x, p2y=p2y,
                        length_text=length_text,
                        line_pen=defined_line_pen,
                        text_color=text_clr,
                        font_size=font_sz,
                        show_ticks=show_ticks,
                        tick_length_factor=tick_factor,
                        scene_context_rect=self.imageView.sceneRect(),
                        z_value_line=11.7, 
                        z_value_text=11.8  
                    )
                    for item_to_add in created_items:
                        scene.addItem(item_to_add)
        except Exception as e:
            logger.exception(f"Error during overlay drawing: {e}")
        finally:
            if self.imageView and self.imageView.viewport():
                self.imageView.viewport().update()


    def _get_export_resolution_choice(self) -> Optional[ExportResolutionMode]:
        # ... (existing method)
        dialog = QtWidgets.QDialog(self); dialog.setWindowTitle("Choose Export Resolution"); dialog.setModal(True)
        layout = QtWidgets.QVBoxLayout(dialog); label = QtWidgets.QLabel("Select the resolution for the export:"); layout.addWidget(label)
        radio_group = QtWidgets.QButtonGroup(dialog); viewport_res_radio = QtWidgets.QRadioButton("Current Viewport Resolution"); viewport_res_radio.setChecked(True)
        radio_group.addButton(viewport_res_radio); layout.addWidget(viewport_res_radio); original_res_radio = QtWidgets.QRadioButton("Original Video Resolution")
        if not (self.video_loaded and self.frame_width > 0 and self.frame_height > 0): original_res_radio.setEnabled(False); original_res_radio.setToolTip("Original video resolution is not available.")
        else: original_res_radio.setToolTip(f"Exports at {self.frame_width}x{self.frame_height} pixels.")
        radio_group.addButton(original_res_radio); layout.addWidget(original_res_radio)
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept); button_box.rejected.connect(dialog.reject); layout.addWidget(button_box)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            if original_res_radio.isChecked(): return ExportResolutionMode.ORIGINAL_VIDEO
            return ExportResolutionMode.VIEWPORT
        return None

    @QtCore.Slot()
    def _trigger_export_video(self) -> None:
        # ... (existing method)
        if not self.video_loaded or not self._export_handler: QtWidgets.QMessageBox.warning(self, "Export Error", "No video loaded or export handler not ready."); return
        export_options_dialog = ExportOptionsDialog(total_frames=self.total_frames, fps=self.fps, current_frame_idx=self.current_frame_index, video_frame_width=self.frame_width, video_frame_height=self.frame_height, parent=self)
        if export_options_dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            start_frame_0_based, end_frame_0_based = export_options_dialog.get_selected_range_0_based(); export_mode = export_options_dialog.get_resolution_mode()
            base_video_name = os.path.splitext(os.path.basename(self.video_filepath))[0] + "_tracked" if self.video_filepath else "video_with_overlays"
            export_formats = [("mp4", "mp4v", "MP4 Video Files (*.mp4)"), ("avi", "MJPG", "AVI Video Files (Motion JPEG) (*.avi)")]; file_filters = ";;".join([opt[2] for opt in export_formats])
            default_filename_suffix = "_origRes" if export_mode == ExportResolutionMode.ORIGINAL_VIDEO else "_viewportRes"
            is_full_range = (start_frame_0_based == 0 and end_frame_0_based == (self.total_frames - 1 if self.total_frames > 0 else 0))
            if not is_full_range and self.total_frames > 0: num_digits_for_padding = len(str(self.total_frames)); start_frame_display = f"{start_frame_0_based + 1:0{num_digits_for_padding}d}"; end_frame_display = f"{end_frame_0_based + 1:0{num_digits_for_padding}d}"; default_filename_suffix += f"_f{start_frame_display}-f{end_frame_display}"
            elif not is_full_range: default_filename_suffix += f"_f{start_frame_0_based + 1}-f{end_frame_0_based + 1}"
            default_filename = f"{base_video_name}{default_filename_suffix}.{export_formats[0][0]}"; start_dir = os.path.dirname(self.video_filepath) if self.video_filepath and os.path.isdir(os.path.dirname(self.video_filepath)) else os.getcwd()
            save_path, selected_filter_desc = QtWidgets.QFileDialog.getSaveFileName(self, "Export Video with Overlays", os.path.join(start_dir, default_filename), file_filters)
            if not save_path:
                if self.statusBar(): self.statusBar().showMessage("Video export cancelled.", 3000); return
            chosen_fourcc_str = ""; chosen_extension_dot = ""
            for ext, fcc, desc in export_formats:
                if desc == selected_filter_desc: chosen_fourcc_str = fcc; chosen_extension_dot = f".{ext}"; break
            if not chosen_fourcc_str:
                _name_part, ext_part_from_path = os.path.splitext(save_path)
                if ext_part_from_path:
                    ext_part_from_path_lower = ext_part_from_path.lower()
                    for ext, fcc, _desc in export_formats:
                        if f".{ext}" == ext_part_from_path_lower: chosen_fourcc_str = fcc; chosen_extension_dot = ext_part_from_path_lower; break
                if not chosen_fourcc_str: chosen_fourcc_str = export_formats[0][1]; chosen_extension_dot = f".{export_formats[0][0]}"
            current_name_part, current_ext_part = os.path.splitext(save_path)
            if current_ext_part.lower() != chosen_extension_dot.lower(): save_path = current_name_part + chosen_extension_dot
            if self._export_handler: self._export_handler.export_video_with_overlays(save_path, chosen_fourcc_str, chosen_extension_dot, export_mode, start_frame_0_based, end_frame_0_based)
            else: QtWidgets.QMessageBox.critical(self, "Export Error", "Export handler is not initialized.")
        elif self.statusBar(): self.statusBar().showMessage("Video export cancelled by user.", 3000)

    @QtCore.Slot()
    def _trigger_export_frame(self) -> None:
        # ... (existing method)
        if not self.video_loaded or self.current_frame_index < 0 or not self._export_handler: QtWidgets.QMessageBox.warning(self, "Export Frame Error", "No video loaded, no current frame, or export handler not ready."); return
        export_mode = self._get_export_resolution_choice()
        if export_mode is None:
            if self.statusBar(): self.statusBar().showMessage("Frame export cancelled by user.", 3000); return
        base_video_name = os.path.splitext(os.path.basename(self.video_filepath))[0] if self.video_filepath else "frame"
        filename_suffix = "_orig_res" if export_mode == ExportResolutionMode.ORIGINAL_VIDEO else "_viewport_res"; default_filename = f"{base_video_name}_frame_{self.current_frame_index + 1}{filename_suffix}.png"
        start_dir = os.path.dirname(self.video_filepath) if self.video_filepath and os.path.isdir(os.path.dirname(self.video_filepath)) else os.getcwd()
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Current Frame to PNG", os.path.join(start_dir, default_filename), "PNG Image Files (*.png);;All Files (*)")
        if not save_path:
            if self.statusBar(): self.statusBar().showMessage("Frame export cancelled.", 3000); return
        if not save_path.lower().endswith(".png"): save_path += ".png"
        if self._export_handler: self._export_handler.export_current_frame_to_png(save_path, export_mode)

    @QtCore.Slot()
    def _on_export_started(self) -> None:
        # ... (existing method)
        if self.exportViewAction: self.exportViewAction.setEnabled(False); 
        if self.exportFrameAction: self.exportFrameAction.setEnabled(False)
        self._export_progress_dialog = QtWidgets.QProgressDialog("Exporting...", "Cancel", 0, 100, self)
        self._export_progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal); self._export_progress_dialog.setWindowTitle("Export Progress")
        self._export_progress_dialog.setValue(0); self._export_progress_dialog.show()
        if self.statusBar(): self.statusBar().showMessage("Exporting...", 0)

    @QtCore.Slot(str, int, int)
    def _on_export_progress(self, message: str, current_value: int, max_value: int) -> None:
        # ... (existing method)
        if self._export_progress_dialog:
            if self._export_progress_dialog.maximum() != max_value: self._export_progress_dialog.setMaximum(max_value)
            self._export_progress_dialog.setValue(current_value); self._export_progress_dialog.setLabelText(message)
        QtWidgets.QApplication.processEvents()

    @QtCore.Slot(bool, str)
    def _on_export_finished(self, success: bool, message: str) -> None:
        # ... (existing method)
        if self._export_progress_dialog: self._export_progress_dialog.close(); self._export_progress_dialog = None
        status_bar = self.statusBar()
        if status_bar: status_bar.showMessage(message, 5000 if success else 8000)
        if not success: QtWidgets.QMessageBox.warning(self, "Export Problem", message)
        self._update_ui_state()
        if self.video_loaded and self.imageView and self.scale_manager and hasattr(self, 'showScaleBarCheckBox') and self.showScaleBarCheckBox and self.showScaleBarCheckBox.isChecked():
            current_m_per_px = self.scale_manager.get_scale_m_per_px()
            if current_m_per_px is not None:
                self.imageView.update_scale_bar_dimensions(current_m_per_px)
                if hasattr(self.imageView, '_scale_bar_widget') and self.imageView._scale_bar_widget:
                    if not self.imageView._scale_bar_widget.isVisible() and self.imageView._scale_bar_widget.get_current_bar_pixel_length() > 0: self.imageView.set_scale_bar_visibility(True)
                    elif self.imageView._scale_bar_widget.isVisible(): self.imageView._update_overlay_widget_positions()
            else: self.imageView.set_scale_bar_visibility(False)
        elif self.imageView : self.imageView.set_scale_bar_visibility(False)

    @QtCore.Slot()
    def _trigger_save_tracks_table_data(self) -> None:
        # ... (existing method)
        logger.info("Save Tracks Table Data button clicked.")
        self._export_or_copy_table_data(ElementType.TRACK, to_clipboard=False)

    @QtCore.Slot()
    def _trigger_copy_tracks_table_data(self) -> None:
        # ... (existing method)
        logger.info("Copy Tracks Table Data button clicked.")
        self._export_or_copy_table_data(ElementType.TRACK, to_clipboard=True)

    @QtCore.Slot()
    def _trigger_save_lines_table_data(self) -> None:
        # ... (existing method)
        logger.info("Save Lines Table Data button clicked.")
        self._export_or_copy_table_data(ElementType.MEASUREMENT_LINE, to_clipboard=False)

    @QtCore.Slot()
    def _trigger_copy_lines_table_data(self) -> None:
        # ... (existing method)
        logger.info("Copy Lines Table Data button clicked.")
        self._export_or_copy_table_data(ElementType.MEASUREMENT_LINE, to_clipboard=True)

    def _export_or_copy_table_data(self, element_type: ElementType, to_clipboard: bool) -> None:
        # ... (existing method)
        action_verb = "copy" if to_clipboard else "export"
        action_ing = "Copying" if to_clipboard else "Exporting"
        type_name_plural = f"{element_type.name.lower().replace('_', ' ')}s"

        if not self.video_loaded:
            QtWidgets.QMessageBox.warning(self, f"{action_ing} Data Error", f"A video must be loaded to {action_verb} {type_name_plural} data.")
            return
        if not all([self.element_manager, self.scale_manager, self.coord_transformer]):
            logger.error(f"Cannot {action_verb} {type_name_plural} data: Core manager(s) missing.")
            QtWidgets.QMessageBox.critical(self, f"{action_ing} Data Error", "Internal error: Required components missing.")
            return

        elements_to_process = self.element_manager.get_elements_by_type(element_type)

        if not elements_to_process:
            QtWidgets.QMessageBox.information(self, f"{action_ing} Data", f"No {type_name_plural} available to {action_verb}.")
            return

        desired_units = "pixels"
        if self.scale_manager.display_in_meters() and self.scale_manager.get_scale_m_per_px() is not None:
            desired_units = "meters"
        
        logger.info(f"Processing {action_verb} for {type_name_plural} in {desired_units}.")

        if to_clipboard:
            try:
                csv_string = file_io.generate_csv_string_for_elements(
                    elements_to_process, element_type, desired_units,
                    self.scale_manager, self.coord_transformer
                )
                if csv_string:
                    QtWidgets.QApplication.clipboard().setText(csv_string)
                    if self.statusBar(): self.statusBar().showMessage(f"{type_name_plural.title()} data copied to clipboard (units: {desired_units}).", 3000)
                else:
                    if self.statusBar(): self.statusBar().showMessage(f"Failed to generate {type_name_plural} data for copying.", 3000)
                    QtWidgets.QMessageBox.warning(self, "Copy Error", f"Could not generate {type_name_plural} data for clipboard.")
            except Exception as e:
                logger.exception(f"Error during {type_name_plural} data copy process.")
                QtWidgets.QMessageBox.critical(self, "Copy Error", f"An unexpected error occurred during copy: {e}")
                if self.statusBar(): self.statusBar().showMessage(f"Critical error copying {type_name_plural}. See log.", 5000)
        else: 
            base_filename_part = os.path.splitext(os.path.basename(self.video_filepath))[0] if self.video_filepath else "untitled"
            suggested_filename = f"{base_filename_part}_{type_name_plural}_data_{desired_units}.csv"
            start_dir = os.path.dirname(self.video_filepath) if self.video_filepath and os.path.isdir(os.path.dirname(self.video_filepath)) else os.getcwd()

            save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, f"Save {type_name_plural.title()} Data to CSV",
                os.path.join(start_dir, suggested_filename),
                "CSV Files (*.csv);;All Files (*)"
            )

            if not save_path:
                if self.statusBar(): self.statusBar().showMessage(f"{type_name_plural.title()} data save cancelled.", 3000)
                return

            if not save_path.lower().endswith(".csv"):
                save_path += ".csv"

            if self.statusBar(): self.statusBar().showMessage(f"Saving {type_name_plural} to {os.path.basename(save_path)}...", 0)
            QtWidgets.QApplication.processEvents()

            try:
                success = file_io.export_elements_to_simple_csv(
                    save_path, elements_to_process, element_type,
                    desired_units, self.scale_manager, self.coord_transformer
                )
                if success:
                    if self.statusBar(): self.statusBar().showMessage(f"{type_name_plural.title()} data saved to {os.path.basename(save_path)} (units: {desired_units}).", 5000)
                else:
                    if self.statusBar(): self.statusBar().showMessage(f"Error saving {type_name_plural} data. See log.", 5000)
                    QtWidgets.QMessageBox.warning(self, "Save Error", f"Could not save {type_name_plural} data to CSV.")
            except Exception as e:
                logger.exception(f"Error during {type_name_plural} data save process.")
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An unexpected error occurred during save: {e}")
                if self.statusBar(): self.statusBar().showMessage(f"Critical error saving {type_name_plural}. See log.", 5000)


    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        # ... (existing method)
        key = event.key(); modifiers = event.modifiers(); accepted = False; status_bar = self.statusBar()
        if key == QtCore.Qt.Key.Key_Escape:
            if self._is_defining_measurement_line: self._cancel_active_line_definition_ui_reset(); 
            if status_bar: status_bar.showMessage("Measurement line definition cancelled.", 3000); accepted = True
            elif self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and self.scale_panel_controller._is_setting_scale_by_line:
                self.scale_panel_controller.cancel_set_scale_by_line(); 
                if status_bar: status_bar.showMessage("Set scale by line cancelled.", 3000); accepted = True
            elif self.coord_panel_controller and self.coord_panel_controller.is_setting_origin_mode():
                self.coord_panel_controller._is_setting_origin = False
                if self.imageView: self.imageView.set_interaction_mode(InteractionMode.NORMAL)
                if status_bar: status_bar.showMessage("Set origin cancelled.", 3000); accepted = True
        elif key == QtCore.Qt.Key.Key_Space:
            if self.video_loaded and self.playPauseButton and self.playPauseButton.isEnabled():
                nav_disabled = (self.scale_panel_controller and hasattr(self.scale_panel_controller, '_is_setting_scale_by_line') and self.scale_panel_controller._is_setting_scale_by_line) or self._is_defining_measurement_line
                if not nav_disabled: self._toggle_playback(); accepted = True
        elif key == QtCore.Qt.Key.Key_Delete or key == QtCore.Qt.Key.Key_Backspace:
            if self.video_loaded and self.element_manager.active_element_index != -1 and self.current_frame_index != -1:
                deleted = self.element_manager.delete_point(self.element_manager.active_element_index, self.current_frame_index)
                if status_bar: status_bar.showMessage(f"Deleted point..." if deleted else "No point to delete on this frame.", 3000)
                if hasattr(self, 'undoAction') and self.undoAction: self.undoAction.setEnabled(self.element_manager.can_undo_last_point_action())
                accepted = True
            elif self.video_loaded and self.element_manager.active_element_index == -1:
                if status_bar: status_bar.showMessage("No track selected to delete points from.", 3000); accepted = True
            elif status_bar: status_bar.showMessage("Cannot delete point.", 3000)
        elif modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and key == QtCore.Qt.Key.Key_Z:
            if hasattr(self, 'undoAction') and self.undoAction and self.undoAction.isEnabled(): self._trigger_undo_point_action(); accepted = True
            elif status_bar: status_bar.showMessage("Nothing to undo.", 3000); accepted = True
        if accepted: event.accept()
        else: super().keyPressEvent(event)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        # ... (existing method)
        if self.video_loaded and isinstance(watched, QtWidgets.QLineEdit):
            line_edit_to_process: Optional[QtWidgets.QLineEdit] = None; is_frame_edit = False; is_time_edit = False; is_zoom_edit = False
            if hasattr(self, 'currentFrameLineEdit') and watched is self.currentFrameLineEdit: line_edit_to_process = self.currentFrameLineEdit; is_frame_edit = True
            elif hasattr(self, 'currentTimeLineEdit') and watched is self.currentTimeLineEdit: line_edit_to_process = self.currentTimeLineEdit; is_time_edit = True
            elif hasattr(self, 'zoomLevelLineEdit') and watched is self.zoomLevelLineEdit: line_edit_to_process = self.zoomLevelLineEdit; is_zoom_edit = True
            if line_edit_to_process:
                if event.type() == QtCore.QEvent.Type.FocusIn:
                    line_edit_to_process.setReadOnly(False)
                    if is_frame_edit and self.current_frame_index >= 0: line_edit_to_process.setText(str(self.current_frame_index + 1))
                    elif is_time_edit and self.current_frame_index >= 0:
                        current_ms = (self.current_frame_index / self.fps) * 1000 if self.fps > 0 else -1.0
                        line_edit_to_process.setText(self._format_time(current_ms))
                    elif is_zoom_edit:
                        if self.imageView and self.imageView.get_min_view_scale() > 0:
                            current_view_scale = self.imageView.transform().m11(); min_scale = self.imageView.get_min_view_scale()
                            zoom_percentage = (current_view_scale / min_scale) * 100.0; line_edit_to_process.setText(f"{zoom_percentage:.1f}")
                        else: line_edit_to_process.setText("---.-")
                    else: line_edit_to_process.setText("")
                    line_edit_to_process.selectAll(); return False
                elif event.type() == QtCore.QEvent.Type.FocusOut:
                    if not line_edit_to_process.isReadOnly():
                        if is_frame_edit: self._handle_frame_input_finished()
                        elif is_time_edit: self._handle_time_input_finished()
                        elif is_zoom_edit: self._handle_zoom_input_finished()
                    return False
        return super().eventFilter(watched, event)

    @QtCore.Slot()
    def _trigger_undo_point_action(self) -> None:
        # ... (existing method)
        if not self.video_loaded:
            if self.statusBar(): self.statusBar().showMessage("Cannot undo: No video loaded.", 3000); return
        if self.element_manager.undo_last_point_action():
            if self.statusBar(): self.statusBar().showMessage("Last point action undone.", 3000)
        else:
            if self.statusBar(): self.statusBar().showMessage("Nothing to undo.", 3000)
        if hasattr(self, 'undoAction') and self.undoAction: self.undoAction.setEnabled(self.element_manager.can_undo_last_point_action())

    @QtCore.Slot()
    def _show_video_info_dialog(self) -> None:
        # ... (existing method)
        status_bar = self.statusBar()
        if not self.video_loaded:
            if status_bar: status_bar.showMessage("No video loaded.", 3000); return
        try:
            meta = self.video_handler.get_metadata_dictionary()
            if not meta: QtWidgets.QMessageBox.information(self, "Video Information", "Could not retrieve metadata."); return
            dialog = MetadataDialog(meta, self); dialog.exec()
        except Exception as e: QtWidgets.QMessageBox.critical(self, "Error", f"Could not display video info:\\n{e}")

    @QtCore.Slot()
    def _show_about_dialog(self) -> None:
        # ... (keep existing method)
        icon = self.windowIcon()
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(f"About {config.APP_NAME}")
        box.setTextFormat(QtCore.Qt.TextFormat.RichText) # Ensure RichText for wrapping and HTML
        
        # Constructing the text with HTML for better control over wrapping and formatting
        about_text = (
            f"<b>{config.APP_NAME}</b><br>"
            f"Version {config.APP_VERSION}<br><br>"
            "PyroTracker is a tool for tracking volcanic pyroclasts in eruption videos, "
            "allowing users to mark element positions, manage coordinate systems, "
            "set scales, and export data and visuals.<br><br>"
            f"Developed at Durham University.<br>" # Example addition
            f"Project Page: <a href='https://github.com/EdLlewellin/PyroTracker'>github.com/EdLlewellin/PyroTracker</a><br><br>" # Example addition
            f"Python {sys.version.split()[0]}, PySide6 {QtCore.__version__}"
        )
        box.setText(about_text)
        
        if not icon.isNull():
            pix = icon.pixmap(QtCore.QSize(64,64))
            if not pix.isNull(): 
                box.setIconPixmap(pix)
            else: 
                # Fallback if pixmap creation failed for some reason, though unlikely if icon is valid
                box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        else: 
            box.setIcon(QtWidgets.QMessageBox.Icon.Information)
            
        box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
        box.exec()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # ... (existing method)
        logger.info("Application close event triggered.")
        if self.project_manager and self.project_manager.project_has_unsaved_changes():
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Unsaved Changes",
                "The current project has unsaved changes. Do you want to save before exiting?",
                QtWidgets.QMessageBox.StandardButton.Save |
                QtWidgets.QMessageBox.StandardButton.Discard |
                QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Cancel
            )

            if reply == QtWidgets.QMessageBox.StandardButton.Save:
                self._trigger_save_project_direct() 
                if not self.project_manager.project_has_unsaved_changes():
                    self._release_video() 
                    event.accept()
                else:
                    event.ignore() 
                    return
            elif reply == QtWidgets.QMessageBox.StandardButton.Cancel:
                event.ignore() 
                return
            
        self._release_video() 
        super().closeEvent(event)
        
    def _format_time(self, ms: float) -> str:
        # ... (existing method)
        if ms < 0: return "--:--.---"
        try: s,mils = divmod(ms,1000); m,s = divmod(int(s),60); return f"{m:02}:{s:02}.{int(mils):03}"
        except: return "--:--.---"