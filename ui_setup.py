# ui_setup.py
"""
Handles the creation and layout of UI elements for the MainWindow.

Separates the UI construction logic from the main application logic
in MainWindow.
"""
import logging
from typing import TYPE_CHECKING, List

from PySide6 import QtCore, QtGui, QtWidgets

import config
from interactive_image_view import InteractiveImageView

if TYPE_CHECKING:
    from main_window import MainWindow

logger = logging.getLogger(__name__)


def setup_main_window_ui(main_window: 'MainWindow') -> None:
    logger.info("Setting up MainWindow UI elements...")
    style: QtWidgets.QStyle = main_window.style()

    main_window.mainSplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
    # main_window.setCentralWidget(main_window.mainSplitter)

    # --- Left Panel (ImageView and Video Controls) ---
    main_window.leftPanelWidget = QtWidgets.QWidget()
    leftPanelLayout = QtWidgets.QVBoxLayout(main_window.leftPanelWidget)
    leftPanelLayout.setContentsMargins(0, 0, 0, 0)
    leftPanelLayout.setSpacing(5)
    main_window.imageView = InteractiveImageView(main_window.leftPanelWidget)
    leftPanelLayout.addWidget(main_window.imageView, stretch=1)
    video_controls_group = QtWidgets.QGroupBox("Video Navigation")
    video_controls_layout = QtWidgets.QVBoxLayout(video_controls_group)
    main_window.frameSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
    main_window.frameSlider.setMinimum(0); main_window.frameSlider.setMaximum(0)
    main_window.frameSlider.setValue(0); main_window.frameSlider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
    video_controls_layout.addWidget(main_window.frameSlider)

    frame_nav_layout = QtWidgets.QHBoxLayout()
    main_window.play_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay)
    main_window.stop_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaStop)
    main_window.playPauseButton = QtWidgets.QPushButton(main_window.play_icon, "")
    main_window.playPauseButton.setToolTip("Play/Pause Video (Space)")
    main_window.prevFrameButton = QtWidgets.QPushButton("<< Prev"); main_window.prevFrameButton.setToolTip("Previous Frame")
    main_window.nextFrameButton = QtWidgets.QPushButton("Next >>"); main_window.nextFrameButton.setToolTip("Next Frame")

    frame_nav_layout.addWidget(main_window.playPauseButton)
    frame_nav_layout.addSpacing(10)
    frame_nav_layout.addWidget(main_window.prevFrameButton)
    frame_nav_layout.addWidget(main_window.nextFrameButton)
    frame_nav_layout.addStretch()

    frame_nav_layout.addWidget(QtWidgets.QLabel("Frame:"))
    main_window.currentFrameLineEdit = QtWidgets.QLineEdit("-")
    main_window.currentFrameLineEdit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.currentFrameLineEdit.setMaximumWidth(60)
    main_window.currentFrameLineEdit.setToolTip("Current frame (Press Enter to seek)")
    main_window.currentFrameLineEdit.setReadOnly(True)
    frame_nav_layout.addWidget(main_window.currentFrameLineEdit)

    main_window.totalFramesLabel = QtWidgets.QLabel("/ -")
    main_window.totalFramesLabel.setMinimumWidth(50)
    main_window.totalFramesLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    frame_nav_layout.addWidget(main_window.totalFramesLabel)
    frame_nav_layout.addSpacing(10)

    frame_nav_layout.addWidget(QtWidgets.QLabel("Time:"))
    main_window.currentTimeLineEdit = QtWidgets.QLineEdit("--:--.---")
    main_window.currentTimeLineEdit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.currentTimeLineEdit.setMaximumWidth(75)
    main_window.currentTimeLineEdit.setToolTip("Current time (Enter MM:SS.mmm or SSS.mmm to seek)")
    main_window.currentTimeLineEdit.setReadOnly(True)
    frame_nav_layout.addWidget(main_window.currentTimeLineEdit)

    main_window.totalTimeLabel = QtWidgets.QLabel("/ --:--.---")
    main_window.totalTimeLabel.setMinimumWidth(90)
    main_window.totalTimeLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    frame_nav_layout.addWidget(main_window.totalTimeLabel)
    frame_nav_layout.addSpacing(10)

    frame_nav_layout.addWidget(QtWidgets.QLabel("Zoom:"))
    main_window.zoomLevelLineEdit = QtWidgets.QLineEdit("---.-")
    main_window.zoomLevelLineEdit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.zoomLevelLineEdit.setMaximumWidth(70)
    main_window.zoomLevelLineEdit.setToolTip("Current zoom (100% = fit to view). Enter value and press Enter.")
    main_window.zoomLevelLineEdit.setReadOnly(True)
    frame_nav_layout.addWidget(main_window.zoomLevelLineEdit)
    frame_nav_layout.addWidget(QtWidgets.QLabel("%"))

    video_controls_layout.addLayout(frame_nav_layout)
    leftPanelLayout.addWidget(video_controls_group, stretch=0)
    main_window.mainSplitter.addWidget(main_window.leftPanelWidget)
    logger.debug("Left panel UI configured.")

    # --- Right Panel (Controls and Data Tabs) ---
    main_window.rightPanelWidget = QtWidgets.QWidget()
    main_window.rightPanelWidget.setMaximumWidth(450)
    main_window.rightPanelWidget.setMinimumWidth(380)
    rightPanelLayout = QtWidgets.QVBoxLayout(main_window.rightPanelWidget)
    rightPanelLayout.setContentsMargins(5, 5, 5, 5)
    rightPanelLayout.setSpacing(6)

    main_window.dataTabsWidget = QtWidgets.QTabWidget()
    main_window.dataTabsWidget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
    rightPanelLayout.addWidget(main_window.dataTabsWidget, stretch=1)

    # --- Tracks Tab ---
    tracksTab = QtWidgets.QWidget()
    tracksTabLayout = QtWidgets.QVBoxLayout(tracksTab)
    tracksTabLayout.setContentsMargins(2, 2, 2, 2)

    track_controls_layout = QtWidgets.QHBoxLayout()
    track_controls_layout.setContentsMargins(0, 0, 0, 0)
    track_controls_layout.setSpacing(6)

    # Save Tracks Table Button
    main_window.saveTracksTableButton = QtWidgets.QPushButton()
    main_window.saveTracksTableButton.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton))
    main_window.saveTracksTableButton.setToolTip("Save tracks data to CSV (uses current display units)")
    main_window.saveTracksTableButton.setFlat(True)
    main_window.saveTracksTableButton.setEnabled(False)
    track_controls_layout.addWidget(main_window.saveTracksTableButton)

    # Copy Tracks Table Button
    main_window.copyTracksTableButton = QtWidgets.QPushButton()
    main_window.copyTracksTableButton.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogContentsView)) # Using this as a placeholder for "copy"
    main_window.copyTracksTableButton.setToolTip("Copy tracks data to clipboard (uses current display units)")
    main_window.copyTracksTableButton.setFlat(True)
    main_window.copyTracksTableButton.setEnabled(False)
    track_controls_layout.addWidget(main_window.copyTracksTableButton)
    
    track_controls_layout.addSpacing(10) # Spacer

    main_window.newTrackButton = QtWidgets.QPushButton("New")
    main_window.newTrackButton.setObjectName("newTrackButton")
    main_window.newTrackButton.setToolTip("Create a new track for marking points (Ctrl+N)")
    main_window.newTrackButton.setEnabled(False)
    main_window.newTrackButton.setFlat(True) 
    track_controls_layout.addWidget(main_window.newTrackButton)

    track_controls_layout.addSpacing(10)

    main_window.autoAdvanceCheckBox = QtWidgets.QCheckBox("Auto-advance")
    main_window.autoAdvanceCheckBox.setToolTip("Automatically advance frame after adding/updating a point")
    track_controls_layout.addWidget(main_window.autoAdvanceCheckBox)

    main_window.autoAdvanceSpinBox = QtWidgets.QSpinBox()
    main_window.autoAdvanceSpinBox.setMinimum(1)
    main_window.autoAdvanceSpinBox.setMaximum(100)
    main_window.autoAdvanceSpinBox.setValue(1)
    main_window.autoAdvanceSpinBox.setToolTip("Number of frames to advance automatically")
    track_controls_layout.addWidget(main_window.autoAdvanceSpinBox)

    track_controls_layout.addStretch(1)

    tracksTabLayout.addLayout(track_controls_layout)
    logger.debug("Tracks tab: Control buttons (Save, Copy, New Track, Auto-Advance) configured.")


    main_window.tracksTableWidget = QtWidgets.QTableWidget()
    main_window.tracksTableWidget.verticalHeader().setVisible(False)
    main_window.tracksTableWidget.setColumnCount(config.TOTAL_TRACK_COLUMNS)
    main_window.tracksTableWidget.setHorizontalHeaderLabels(["", "ID", "Points", "Start", "End", "", "", "", ""])
    main_window.tracksTableWidget.setAlternatingRowColors(True); main_window.tracksTableWidget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    main_window.tracksTableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    main_window.tracksTableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

    tracksHeader: QtWidgets.QHeaderView = main_window.tracksTableWidget.horizontalHeader()

    icon_hidden = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogCancelButton)
    tracksHeader.model().setHeaderData(config.COL_VIS_HIDDEN, QtCore.Qt.Orientation.Horizontal, icon_hidden, QtCore.Qt.ItemDataRole.DecorationRole)
    tracksHeader.model().setHeaderData(config.COL_VIS_HIDDEN, QtCore.Qt.Orientation.Horizontal, "Hidden: Track is never shown.", QtCore.Qt.ItemDataRole.ToolTipRole)

    icon_home_frame = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogInfoView)
    tracksHeader.model().setHeaderData(config.COL_VIS_HOME_FRAME, QtCore.Qt.Orientation.Horizontal, icon_home_frame, QtCore.Qt.ItemDataRole.DecorationRole)
    tracksHeader.model().setHeaderData(config.COL_VIS_HOME_FRAME, QtCore.Qt.Orientation.Horizontal, "Home Frame: Markers visible only on frames with points. No lines.", QtCore.Qt.ItemDataRole.ToolTipRole)

    icon_incremental = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowRight)
    tracksHeader.model().setHeaderData(config.COL_VIS_INCREMENTAL, QtCore.Qt.Orientation.Horizontal, icon_incremental, QtCore.Qt.ItemDataRole.DecorationRole)
    tracksHeader.model().setHeaderData(config.COL_VIS_INCREMENTAL, QtCore.Qt.Orientation.Horizontal, "Incremental: Track appears point-by-point as video advances.", QtCore.Qt.ItemDataRole.ToolTipRole)

    icon_always = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton)
    tracksHeader.model().setHeaderData(config.COL_VIS_ALWAYS, QtCore.Qt.Orientation.Horizontal, icon_always, QtCore.Qt.ItemDataRole.DecorationRole)
    tracksHeader.model().setHeaderData(config.COL_VIS_ALWAYS, QtCore.Qt.Orientation.Horizontal, "Always Visible: Entire track is shown on all frames.", QtCore.Qt.ItemDataRole.ToolTipRole)

    tracksHeader.setSectionResizeMode(config.COL_DELETE, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksHeader.setSectionResizeMode(config.COL_TRACK_ID, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksHeader.setSectionResizeMode(config.COL_TRACK_POINTS, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksHeader.setSectionResizeMode(config.COL_TRACK_START_FRAME, QtWidgets.QHeaderView.ResizeMode.Stretch)
    tracksHeader.setSectionResizeMode(config.COL_TRACK_END_FRAME, QtWidgets.QHeaderView.ResizeMode.Stretch)

    visibility_track_columns = [
        config.COL_VIS_HIDDEN, config.COL_VIS_HOME_FRAME,
        config.COL_VIS_INCREMENTAL, config.COL_VIS_ALWAYS
    ]
    for col_idx in visibility_track_columns:
        tracksHeader.setSectionResizeMode(col_idx, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

    main_window.tracksTableWidget.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksTabLayout.addWidget(main_window.tracksTableWidget)
    main_window.dataTabsWidget.addTab(tracksTab, "Tracks")
    logger.debug("Tracks tab configured with table.")

    # --- Lines Tab ---
    linesTab = QtWidgets.QWidget()
    linesTabLayout = QtWidgets.QVBoxLayout(linesTab)
    linesTabLayout.setContentsMargins(2, 2, 2, 2)

    line_controls_layout = QtWidgets.QHBoxLayout()
    line_controls_layout.setContentsMargins(0,0,0,0)
    line_controls_layout.setSpacing(6)

    main_window.saveLinesTableButton = QtWidgets.QPushButton()
    main_window.saveLinesTableButton.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton))
    main_window.saveLinesTableButton.setToolTip("Save lines data to CSV (uses current display units)")
    main_window.saveLinesTableButton.setFlat(True)
    main_window.saveLinesTableButton.setEnabled(False)
    line_controls_layout.addWidget(main_window.saveLinesTableButton)

    main_window.copyLinesTableButton = QtWidgets.QPushButton()
    main_window.copyLinesTableButton.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogContentsView)) 
    main_window.copyLinesTableButton.setToolTip("Copy lines data to clipboard (uses current display units)")
    main_window.copyLinesTableButton.setFlat(True)
    main_window.copyLinesTableButton.setEnabled(False)
    line_controls_layout.addWidget(main_window.copyLinesTableButton)
    
    line_controls_layout.addSpacing(10) 

    main_window.newLineButton = QtWidgets.QPushButton("New")
    main_window.newLineButton.setObjectName("newLineButton")
    main_window.newLineButton.setToolTip("Create a new measurement line")
    main_window.newLineButton.setEnabled(False)
    main_window.newLineButton.setFlat(True) 
    line_controls_layout.addWidget(main_window.newLineButton)
    
    line_controls_layout.addStretch(1) 
    linesTabLayout.addLayout(line_controls_layout) 

    main_window.linesTableWidget = QtWidgets.QTableWidget()
    main_window.linesTableWidget.setObjectName("linesTableWidget")
    main_window.linesTableWidget.verticalHeader().setVisible(False)
    main_window.linesTableWidget.setColumnCount(config.TOTAL_LINE_COLUMNS)

    header_labels_lines: List[str] = [""] * config.TOTAL_LINE_COLUMNS
    header_labels_lines[config.COL_LINE_ID] = "ID"
    header_labels_lines[config.COL_LINE_FRAME] = "Frame"
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_LENGTH: header_labels_lines[config.COL_LINE_LENGTH] = "Length"
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_ANGLE: header_labels_lines[config.COL_LINE_ANGLE] = "Angle"
    # Visibility icon columns will have empty text headers
    main_window.linesTableWidget.setHorizontalHeaderLabels(header_labels_lines)

    main_window.linesTableWidget.setAlternatingRowColors(True)
    main_window.linesTableWidget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    main_window.linesTableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    main_window.linesTableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

    linesHeader: QtWidgets.QHeaderView = main_window.linesTableWidget.horizontalHeader()
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_VIS_HIDDEN:
        linesHeader.model().setHeaderData(config.COL_LINE_VIS_HIDDEN, QtCore.Qt.Orientation.Horizontal, icon_hidden, QtCore.Qt.ItemDataRole.DecorationRole)
        linesHeader.model().setHeaderData(config.COL_LINE_VIS_HIDDEN, QtCore.Qt.Orientation.Horizontal, "Hidden: Line is never shown.", QtCore.Qt.ItemDataRole.ToolTipRole)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_VIS_HOME_FRAME:
        linesHeader.model().setHeaderData(config.COL_LINE_VIS_HOME_FRAME, QtCore.Qt.Orientation.Horizontal, icon_home_frame, QtCore.Qt.ItemDataRole.DecorationRole)
        linesHeader.model().setHeaderData(config.COL_LINE_VIS_HOME_FRAME, QtCore.Qt.Orientation.Horizontal, "Home Frame: Line visible only on its definition frame.", QtCore.Qt.ItemDataRole.ToolTipRole)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_VIS_INCREMENTAL:
        linesHeader.model().setHeaderData(config.COL_LINE_VIS_INCREMENTAL, QtCore.Qt.Orientation.Horizontal, icon_incremental, QtCore.Qt.ItemDataRole.DecorationRole)
        linesHeader.model().setHeaderData(config.COL_LINE_VIS_INCREMENTAL, QtCore.Qt.Orientation.Horizontal, "Incremental: Line visible on its definition frame and all subsequent frames.", QtCore.Qt.ItemDataRole.ToolTipRole)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_VIS_ALWAYS:
        linesHeader.model().setHeaderData(config.COL_LINE_VIS_ALWAYS, QtCore.Qt.Orientation.Horizontal, icon_always, QtCore.Qt.ItemDataRole.DecorationRole)
        linesHeader.model().setHeaderData(config.COL_LINE_VIS_ALWAYS, QtCore.Qt.Orientation.Horizontal, "Always Visible: Line is shown on all frames.", QtCore.Qt.ItemDataRole.ToolTipRole)

    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_DELETE: linesHeader.setSectionResizeMode(config.COL_LINE_DELETE, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_ID: linesHeader.setSectionResizeMode(config.COL_LINE_ID, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_FRAME: linesHeader.setSectionResizeMode(config.COL_LINE_FRAME, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_LENGTH: linesHeader.setSectionResizeMode(config.COL_LINE_LENGTH, QtWidgets.QHeaderView.ResizeMode.Stretch)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_ANGLE: linesHeader.setSectionResizeMode(config.COL_LINE_ANGLE, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

    visibility_line_columns = []
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_VIS_HIDDEN: visibility_line_columns.append(config.COL_LINE_VIS_HIDDEN)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_VIS_HOME_FRAME: visibility_line_columns.append(config.COL_LINE_VIS_HOME_FRAME)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_VIS_INCREMENTAL: visibility_line_columns.append(config.COL_LINE_VIS_INCREMENTAL)
    if config.TOTAL_LINE_COLUMNS > config.COL_LINE_VIS_ALWAYS: visibility_line_columns.append(config.COL_LINE_VIS_ALWAYS)

    for col_idx in visibility_line_columns:
        linesHeader.setSectionResizeMode(col_idx, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

    linesTabLayout.addWidget(main_window.linesTableWidget)
    main_window.dataTabsWidget.addTab(linesTab, "Measurement Lines")
    logger.debug("Measurement Lines tab configured.")

    # --- Points Tab ---
    pointsTab = QtWidgets.QWidget(); pointsTabLayout = QtWidgets.QVBoxLayout(pointsTab); pointsTabLayout.setContentsMargins(2, 2, 2, 2); pointsTabLayout.setSpacing(4)
    main_window.pointsTabLabel = QtWidgets.QLabel("Points for Track: -"); main_window.pointsTabLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    pointsTabLayout.addWidget(main_window.pointsTabLabel)
    main_window.pointsTableWidget = QtWidgets.QTableWidget(); main_window.pointsTableWidget.setColumnCount(config.TOTAL_POINT_COLUMNS); main_window.pointsTableWidget.setHorizontalHeaderLabels(["Frame", "Time (s)", "X", "Y"])
    main_window.pointsTableWidget.setFont(QtGui.QFont("Monospace", 10)); main_window.pointsTableWidget.setAlternatingRowColors(True); main_window.pointsTableWidget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    main_window.pointsTableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows); main_window.pointsTableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection); main_window.pointsTableWidget.verticalHeader().setVisible(False)
    pointsHeader: QtWidgets.QHeaderView = main_window.pointsTableWidget.horizontalHeader()
    pointsHeader.setSectionResizeMode(config.COL_POINT_FRAME, QtWidgets.QHeaderView.ResizeMode.ResizeToContents); pointsHeader.setSectionResizeMode(config.COL_POINT_TIME, QtWidgets.QHeaderView.ResizeMode.ResizeToContents); pointsHeader.setSectionResizeMode(config.COL_POINT_X, QtWidgets.QHeaderView.ResizeMode.Stretch); pointsHeader.setSectionResizeMode(config.COL_POINT_Y, QtWidgets.QHeaderView.ResizeMode.Stretch)
    pointsTabLayout.addWidget(main_window.pointsTableWidget)
    main_window.dataTabsWidget.addTab(pointsTab, "Points")
    logger.debug("Points tab configured.")

    # --- Collapsible Group Boxes (Scale, Coords) ---
    main_window.scale_config_group = QtWidgets.QGroupBox("Scale Configuration")
    main_window.scale_config_group.setCheckable(True); main_window.scale_config_group.setChecked(False)
    main_window.scale_config_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
    main_window.scale_config_group.setProperty("collapsible", "true")
    scale_group_outer_layout = QtWidgets.QVBoxLayout(main_window.scale_config_group); scale_group_outer_layout.setContentsMargins(6, 6, 6, 6); scale_group_outer_layout.setSpacing(0)
    scale_contents_widget = QtWidgets.QWidget(); scale_group_contents_layout = QtWidgets.QVBoxLayout(scale_contents_widget); scale_group_contents_layout.setContentsMargins(0, 8, 0, 0); scale_group_contents_layout.setSpacing(8)
    scale_input_layout = QtWidgets.QHBoxLayout(); scale_input_layout.setSpacing(5); scale_input_layout.addWidget(QtWidgets.QLabel("Manual scale:")); scale_input_layout.addStretch(1); scale_input_layout.addWidget(QtWidgets.QLabel("m/px:"))
    main_window.scale_m_per_px_input = QtWidgets.QLineEdit(); main_window.scale_m_per_px_input.setPlaceholderText("-"); main_window.scale_m_per_px_input.setValidator(QtGui.QDoubleValidator(0.0, 1000000.0, 8, main_window.scale_m_per_px_input)); main_window.scale_m_per_px_input.setToolTip("Enter scale as meters per pixel (e.g., 0.001)"); main_window.scale_m_per_px_input.setMaximumWidth(100)
    scale_input_layout.addWidget(main_window.scale_m_per_px_input); scale_input_layout.addWidget(QtWidgets.QLabel("px/m:"))
    main_window.scale_px_per_m_input = QtWidgets.QLineEdit(); main_window.scale_px_per_m_input.setPlaceholderText("-"); main_window.scale_px_per_m_input.setValidator(QtGui.QDoubleValidator(0.0, 100000000.0, 8, main_window.scale_px_per_m_input)); main_window.scale_px_per_m_input.setToolTip("Enter scale as pixels per meter (e.g., 1000)"); main_window.scale_px_per_m_input.setMaximumWidth(100)
    scale_input_layout.addWidget(main_window.scale_px_per_m_input)
    main_window.scale_reset_button = QtWidgets.QPushButton(); main_window.scale_reset_button.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogResetButton)); main_window.scale_reset_button.setToolTip("Reset scale to undefined"); main_window.scale_reset_button.setFixedSize(main_window.scale_reset_button.iconSize() + QtCore.QSize(10,5))
    scale_input_layout.addWidget(main_window.scale_reset_button); scale_input_layout.addStretch(2); scale_group_contents_layout.addLayout(scale_input_layout)
    scale_from_feature_layout = QtWidgets.QHBoxLayout(); scale_from_feature_layout.setSpacing(5); scale_from_feature_layout.addWidget(QtWidgets.QLabel("Scale from feature:"))
    main_window.setScaleByFeatureButton = QtWidgets.QPushButton("Set"); main_window.setScaleByFeatureButton.setToolTip("Define scale by clicking two points on a feature of known length"); main_window.setScaleByFeatureButton.setEnabled(False)
    scale_from_feature_layout.addWidget(main_window.setScaleByFeatureButton)
    main_window.showScaleLineCheckBox = QtWidgets.QCheckBox("Show scale line"); main_window.showScaleLineCheckBox.setToolTip("Show/hide the line used to define the scale"); main_window.showScaleLineCheckBox.setChecked(False); main_window.showScaleLineCheckBox.setEnabled(False)
    scale_from_feature_layout.addWidget(main_window.showScaleLineCheckBox); scale_from_feature_layout.addStretch(); scale_group_contents_layout.addLayout(scale_from_feature_layout)
    scale_toggle_layout = QtWidgets.QHBoxLayout(); scale_toggle_layout.setSpacing(10)
    main_window.scale_display_meters_checkbox = QtWidgets.QCheckBox("Display in meters"); main_window.scale_display_meters_checkbox.setToolTip("Convert displayed values to meters (only if scale is set)"); main_window.scale_display_meters_checkbox.setChecked(False); main_window.scale_display_meters_checkbox.setEnabled(False)
    scale_toggle_layout.addWidget(main_window.scale_display_meters_checkbox)
    main_window.showScaleBarCheckBox = QtWidgets.QCheckBox("Show Scale Bar"); main_window.showScaleBarCheckBox.setToolTip("Toggle visibility of the scale bar on the image (only if scale is set)"); main_window.showScaleBarCheckBox.setChecked(False); main_window.showScaleBarCheckBox.setEnabled(False)
    scale_toggle_layout.addWidget(main_window.showScaleBarCheckBox); scale_toggle_layout.addStretch(); scale_group_contents_layout.addLayout(scale_toggle_layout)
    scale_group_outer_layout.addWidget(scale_contents_widget)
    main_window.scale_config_group.toggled.connect(scale_contents_widget.setVisible)
    scale_contents_widget.setVisible(main_window.scale_config_group.isChecked())
    rightPanelLayout.addWidget(main_window.scale_config_group)
    logger.debug("Scale Configuration panel configured.")

    main_window.coords_group = QtWidgets.QGroupBox("Coordinate System")
    main_window.coords_group.setCheckable(True); main_window.coords_group.setChecked(False)
    main_window.coords_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
    main_window.coords_group.setProperty("collapsible", "true")
    coords_group_outer_layout = QtWidgets.QVBoxLayout(main_window.coords_group); coords_group_outer_layout.setContentsMargins(6, 6, 6, 6); coords_group_outer_layout.setSpacing(0)
    coords_contents_widget = QtWidgets.QWidget(); coords_group_contents_layout = QtWidgets.QVBoxLayout(coords_contents_widget); coords_group_contents_layout.setContentsMargins(0, 8, 0, 0); coords_group_contents_layout.setSpacing(8)
    grid_layout = QtWidgets.QGridLayout(); grid_layout.setContentsMargins(0, 0, 0, 0); grid_layout.setHorizontalSpacing(10); grid_layout.setVerticalSpacing(5)
    main_window.coordSystemGroup = QtWidgets.QButtonGroup(main_window)
    label_min_width = 100; cursor_label_min_width = 100
    header_origin_label = QtWidgets.QLabel("Origin"); header_origin_label.setStyleSheet("font-weight: bold;"); header_origin_label.setToolTip("The Top-Left coordinates of the system's origin"); header_origin_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    header_cursor_label = QtWidgets.QLabel("Cursor [px]"); header_cursor_label.setStyleSheet("font-weight: bold;"); header_cursor_label.setToolTip("Live position of the mouse cursor in this coordinate system"); header_cursor_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    header_cursor_m_label = QtWidgets.QLabel("Cursor [m]"); header_cursor_m_label.setStyleSheet("font-weight: bold;"); header_cursor_m_label.setToolTip("Live mouse cursor position in meters (if scale is set)"); header_cursor_m_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    grid_layout.addWidget(header_origin_label, 0, 1); grid_layout.addWidget(header_cursor_label, 0, 2); grid_layout.addWidget(header_cursor_m_label, 0, 3)
    main_window.coordTopLeftRadio = QtWidgets.QRadioButton("TL"); main_window.coordTopLeftRadio.setToolTip("Origin at (0,0), Y increases downwards"); main_window.coordSystemGroup.addButton(main_window.coordTopLeftRadio)
    main_window.coordTopLeftOriginLabel = QtWidgets.QLabel("(0.0, 0.0)"); main_window.coordTopLeftOriginLabel.setToolTip("Effective origin (Top-Left Coordinates)"); main_window.coordTopLeftOriginLabel.setMinimumWidth(label_min_width); main_window.coordTopLeftOriginLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.cursorPosLabelTL = QtWidgets.QLabel("(--, --)"); main_window.cursorPosLabelTL.setToolTip("Cursor position (Top-Left pixels)"); main_window.cursorPosLabelTL.setMinimumWidth(cursor_label_min_width); main_window.cursorPosLabelTL.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.cursorPosLabelTL_m = QtWidgets.QLabel("(--, --)"); main_window.cursorPosLabelTL_m.setToolTip("Cursor position (Top-Left meters)"); main_window.cursorPosLabelTL_m.setMinimumWidth(cursor_label_min_width); main_window.cursorPosLabelTL_m.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    grid_layout.addWidget(main_window.coordTopLeftRadio, 1, 0); grid_layout.addWidget(main_window.coordTopLeftOriginLabel, 1, 1); grid_layout.addWidget(main_window.cursorPosLabelTL, 1, 2); grid_layout.addWidget(main_window.cursorPosLabelTL_m, 1, 3)
    main_window.coordBottomLeftRadio = QtWidgets.QRadioButton("BL"); main_window.coordBottomLeftRadio.setToolTip("Origin at (0, Frame Height), Y increases upwards"); main_window.coordSystemGroup.addButton(main_window.coordBottomLeftRadio)
    main_window.coordBottomLeftOriginLabel = QtWidgets.QLabel("(0.0, -)"); main_window.coordBottomLeftOriginLabel.setToolTip("Effective origin (Top-Left Coordinates)"); main_window.coordBottomLeftOriginLabel.setMinimumWidth(label_min_width); main_window.coordBottomLeftOriginLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.cursorPosLabelBL = QtWidgets.QLabel("(--, --)"); main_window.cursorPosLabelBL.setToolTip("Cursor position (Bottom-Left pixels)"); main_window.cursorPosLabelBL.setMinimumWidth(cursor_label_min_width); main_window.cursorPosLabelBL.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.cursorPosLabelBL_m = QtWidgets.QLabel("(--, --)"); main_window.cursorPosLabelBL_m.setToolTip("Cursor position (Bottom-Left meters)"); main_window.cursorPosLabelBL_m.setMinimumWidth(cursor_label_min_width); main_window.cursorPosLabelBL_m.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    grid_layout.addWidget(main_window.coordBottomLeftRadio, 2, 0); grid_layout.addWidget(main_window.coordBottomLeftOriginLabel, 2, 1); grid_layout.addWidget(main_window.cursorPosLabelBL, 2, 2); grid_layout.addWidget(main_window.cursorPosLabelBL_m, 2, 3)
    main_window.coordCustomRadio = QtWidgets.QRadioButton("Cust."); main_window.coordCustomRadio.setToolTip("Origin set by user click, Y increases upwards"); main_window.coordCustomRadio.setEnabled(False); main_window.coordSystemGroup.addButton(main_window.coordCustomRadio)
    main_window.coordCustomOriginLabel = QtWidgets.QLabel("(-, -)"); main_window.coordCustomOriginLabel.setToolTip("Effective custom origin (Top-Left Coordinates)"); main_window.coordCustomOriginLabel.setMinimumWidth(label_min_width); main_window.coordCustomOriginLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.cursorPosLabelCustom = QtWidgets.QLabel("(--, --)"); main_window.cursorPosLabelCustom.setToolTip("Cursor position (Custom pixels)"); main_window.cursorPosLabelCustom.setMinimumWidth(cursor_label_min_width); main_window.cursorPosLabelCustom.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.cursorPosLabelCustom_m = QtWidgets.QLabel("(--, --)"); main_window.cursorPosLabelCustom_m.setToolTip("Cursor position (Custom meters)"); main_window.cursorPosLabelCustom_m.setMinimumWidth(cursor_label_min_width); main_window.cursorPosLabelCustom_m.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    grid_layout.addWidget(main_window.coordCustomRadio, 3, 0); grid_layout.addWidget(main_window.coordCustomOriginLabel, 3, 1); grid_layout.addWidget(main_window.cursorPosLabelCustom, 3, 2); grid_layout.addWidget(main_window.cursorPosLabelCustom_m, 3, 3)
    grid_layout.setColumnMinimumWidth(1, label_min_width); grid_layout.setColumnMinimumWidth(2, cursor_label_min_width); grid_layout.setColumnMinimumWidth(3, cursor_label_min_width); grid_layout.setColumnStretch(4, 1)
    coords_group_contents_layout.addLayout(grid_layout)
    bottom_controls_layout = QtWidgets.QHBoxLayout(); bottom_controls_layout.setContentsMargins(0, 5, 0, 0); bottom_controls_layout.setSpacing(10)
    main_window.showOriginCheckBox = QtWidgets.QCheckBox("Show Origin"); main_window.showOriginCheckBox.setToolTip("Toggle visibility of the effective origin marker on the image"); main_window.showOriginCheckBox.setChecked(True)
    bottom_controls_layout.addWidget(main_window.showOriginCheckBox)
    main_window.setOriginButton = QtWidgets.QPushButton("Pick Custom"); main_window.setOriginButton.setToolTip("Click to enable origin selection mode, then click on the image")
    bottom_controls_layout.addWidget(main_window.setOriginButton); bottom_controls_layout.addStretch()
    coords_group_contents_layout.addLayout(bottom_controls_layout)
    coords_group_outer_layout.addWidget(coords_contents_widget)
    main_window.coords_group.toggled.connect(coords_contents_widget.setVisible)
    coords_contents_widget.setVisible(main_window.coords_group.isChecked())
    rightPanelLayout.addWidget(main_window.coords_group)
    logger.debug("Coordinate System panel configured.")


    main_window.mainSplitter.addWidget(main_window.rightPanelWidget)
    logger.debug("Right panel UI configured.")

    try:
        initial_width = main_window.width()
        initial_sizes: List[int] = [int(initial_width * 0.70), int(initial_width * 0.30)]
        main_window.mainSplitter.setSizes(initial_sizes)
    except Exception as e:
        logger.warning(f"Could not set initial splitter sizes dynamically: {e}. Using fixed fallback.")
        main_window.mainSplitter.setSizes([600, 400])
    main_window.mainSplitter.setStretchFactor(0, 3)
    main_window.mainSplitter.setStretchFactor(1, 1)
    logger.debug("Main splitter sizes and stretch factors configured.")

    # --- Create Menus ---
    logger.debug("Creating menus...")
    menu_bar: QtWidgets.QMenuBar = main_window.menuBar()
    file_menu: QtWidgets.QMenu = menu_bar.addMenu("&File")

    open_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton)
    open_action = QtGui.QAction(open_icon, "&Open Video...", main_window)
    open_action.setStatusTip("Select and load a video file")
    open_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
    open_action.triggered.connect(main_window.open_video)
    file_menu.addAction(open_action)

    file_menu.addSeparator()

    load_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowUp)
    main_window.loadProjectAction = QtGui.QAction(load_icon, "&Open Project...", main_window)
    main_window.loadProjectAction.setStatusTip("Load project data from a JSON file")
    main_window.loadProjectAction.setEnabled(True) # Connection in MainWindow.__init__
    file_menu.addAction(main_window.loadProjectAction)

    save_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton)
    main_window.saveProjectAsAction = QtGui.QAction(save_icon, "&Save Project As...", main_window)
    main_window.saveProjectAsAction.setStatusTip("Save current project data to a new JSON file") 
    main_window.saveProjectAsAction.setShortcut(QtGui.QKeySequence.StandardKey.SaveAs)
    main_window.saveProjectAsAction.setEnabled(False) 
    file_menu.addAction(main_window.saveProjectAsAction)

    file_menu.addSeparator() 

    export_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton) # Re-use save icon for now
    main_window.exportViewAction = QtGui.QAction(export_icon, "Export Video with Overlays...", main_window)
    main_window.exportViewAction.setStatusTip("Export the current view with overlays to a video file")
    main_window.exportViewAction.setEnabled(False)
    file_menu.addAction(main_window.exportViewAction)

    export_frame_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DriveHDIcon) # Placeholder
    main_window.exportFrameAction = QtGui.QAction(export_frame_icon, "Export Current Frame to PNG...", main_window)
    main_window.exportFrameAction.setStatusTip("Export the current frame with overlays to a PNG image file")
    main_window.exportFrameAction.setEnabled(False)
    file_menu.addAction(main_window.exportFrameAction)

    file_menu.addSeparator()

    info_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogInfoView)
    main_window.videoInfoAction = QtGui.QAction(info_icon, "Video Information...", main_window)
    main_window.videoInfoAction.setStatusTip("Show technical information about the loaded video")
    main_window.videoInfoAction.setEnabled(False)
    file_menu.addAction(main_window.videoInfoAction)

    file_menu.addSeparator()

    exit_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogCloseButton)
    exit_action = QtGui.QAction(exit_icon, "E&xit", main_window)
    exit_action.setStatusTip("Exit the application")
    exit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
    exit_action.triggered.connect(main_window.close)
    file_menu.addAction(exit_action)

    edit_menu: QtWidgets.QMenu = menu_bar.addMenu("&Edit")
    undo_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowBack)
    main_window.undoAction = QtGui.QAction(undo_icon, "&Undo Point Action", main_window)
    main_window.undoAction.setStatusTip("Undo the last point addition or modification (Ctrl+Z)")
    main_window.undoAction.setShortcut(QtGui.QKeySequence.StandardKey.Undo)
    main_window.undoAction.setEnabled(False)
    edit_menu.addAction(main_window.undoAction)

    edit_menu.addSeparator()

    main_window.newTrackAction = QtGui.QAction("&New Track", main_window)
    main_window.newTrackAction.setStatusTip("Create a new track for marking points (Ctrl+N)") # Ctrl+N added to tip
    main_window.newTrackAction.setEnabled(False)
    # main_window.newTrackAction.setShortcut(QtGui.QKeySequence.StandardKey.New) # Set in MainWindow now
    edit_menu.addAction(main_window.newTrackAction)
    
    # --- REMOVE Preferences from Edit Menu ---
    # edit_menu.addSeparator() # Remove this separator if Preferences was the only item after
    # prefs_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView)
    # main_window.preferencesAction = QtGui.QAction(prefs_icon, "&Preferences...", main_window)
    # main_window.preferencesAction.setStatusTip("Edit application preferences (colors, sizes, etc.)")
    # edit_menu.addAction(main_window.preferencesAction)
    # --- END REMOVE ---
    
    # --- ADD "New Measurement Line" to Edit Menu ---
    # Icon can be chosen later, for now, just text
    # A simple "plus" or "line" icon could work.
    # Example: add_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileIcon) # Placeholder icon
    main_window.newMeasurementLineAction = QtGui.QAction("New Measurement &Line", main_window)
    main_window.newMeasurementLineAction.setStatusTip("Create a new measurement line")
    main_window.newMeasurementLineAction.setEnabled(False) # Initially disabled
    edit_menu.addAction(main_window.newMeasurementLineAction)
    # --- END ADD ---

    # Create Preferences action here so MainWindow can connect it, but don't add to Edit menu
    prefs_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView)
    main_window.preferencesAction = QtGui.QAction(prefs_icon, "&Preferences...", main_window)
    main_window.preferencesAction.setStatusTip("Edit application preferences (colors, sizes, etc.)")
    # This action will be added to the View menu by ViewMenuController


    # --- ADD "Analysis" Menu (empty for now) ---
    menu_bar.addMenu("&Analysis")
    # --- END ADD ---

    main_window.setStatusBar(QtWidgets.QStatusBar())
    logger.info("MainWindow UI setup complete.")