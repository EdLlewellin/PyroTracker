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

# Use TYPE_CHECKING to avoid circular import with MainWindow for type hints
if TYPE_CHECKING:
    from main_window import MainWindow

logger = logging.getLogger(__name__)

def setup_main_window_ui(main_window: 'MainWindow') -> None:
    """
    Creates and arranges the main UI widgets, layouts, and menus for the MainWindow.

    Assigns created widgets (like imageView, frameSlider, tracksTableWidget)
    and actions (like loadTracksAction, saveTracksAction, videoInfoAction)
    as attributes of the passed main_window object. Connections for these
    widgets and actions are typically handled within the MainWindow class itself
    after this setup function is called, although some basic connections might be
    established here.

    Args:
        main_window: The MainWindow instance to populate with UI elements.
    """
    logger.info("Setting up MainWindow UI elements...")

    # Get the application style for standard icons
    style: QtWidgets.QStyle = main_window.style()

    # --- Main Layout: Splitter ---
    # Use a splitter to allow resizing between the image panel and the data panel.
    main_window.mainSplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
    main_window.setCentralWidget(main_window.mainSplitter)

    # --- Left Panel (ImageView and Video Controls) ---
    main_window.leftPanelWidget = QtWidgets.QWidget()
    leftPanelLayout = QtWidgets.QVBoxLayout(main_window.leftPanelWidget)
    leftPanelLayout.setContentsMargins(0, 0, 0, 0) # No margins for this panel
    leftPanelLayout.setSpacing(5)

    # Interactive Image View
    main_window.imageView = InteractiveImageView(main_window.leftPanelWidget)
    leftPanelLayout.addWidget(main_window.imageView, stretch=1) # Allow vertical stretching

    # Video Navigation Controls GroupBox
    video_controls_group = QtWidgets.QGroupBox("Video Navigation")
    video_controls_layout = QtWidgets.QVBoxLayout(video_controls_group)

    # Frame Slider
    main_window.frameSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
    main_window.frameSlider.setMinimum(0)
    main_window.frameSlider.setMaximum(0) # Range updated when video loads
    main_window.frameSlider.setValue(0)
    main_window.frameSlider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
    video_controls_layout.addWidget(main_window.frameSlider)

    # Bottom Row Controls (Play/Pause, Prev/Next, Labels) Layout
    frame_nav_layout = QtWidgets.QHBoxLayout()

    # Play/Pause Button
    main_window.play_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay)
    main_window.stop_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaStop)
    main_window.playPauseButton = QtWidgets.QPushButton(main_window.play_icon, "")
    main_window.playPauseButton.setToolTip("Play/Pause Video (Space)")

    # Prev/Next Frame Buttons
    main_window.prevFrameButton = QtWidgets.QPushButton("<< Prev")
    main_window.prevFrameButton.setToolTip("Previous Frame")
    main_window.nextFrameButton = QtWidgets.QPushButton("Next >>")
    main_window.nextFrameButton.setToolTip("Next Frame")

    # Frame, Time, FPS, and Filename Labels
    main_window.frameLabel = QtWidgets.QLabel("Frame: - / -")
    main_window.frameLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    main_window.frameLabel.setMinimumWidth(100)
    main_window.timeLabel = QtWidgets.QLabel("Time: --:--.--- / --:--.---")
    main_window.timeLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    main_window.timeLabel.setMinimumWidth(210) # Ensure space for MM:SS.mmm format
    main_window.fpsLabel = QtWidgets.QLabel("FPS: ---.--")
    main_window.fpsLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    main_window.fpsLabel.setMinimumWidth(80)
    main_window.fpsLabel.setToolTip("Video Frames Per Second")
    main_window.filenameLabel = QtWidgets.QLabel("File: -")
    main_window.filenameLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    main_window.filenameLabel.setMinimumWidth(150)
    main_window.filenameLabel.setStyleSheet("QLabel { color : grey; }") # Subtle styling
    main_window.filenameLabel.setToolTip("Currently loaded video file")

    # Arrange Frame Navigation Controls
    frame_nav_layout.addWidget(main_window.playPauseButton)
    frame_nav_layout.addSpacing(10)
    frame_nav_layout.addWidget(main_window.prevFrameButton)
    frame_nav_layout.addWidget(main_window.nextFrameButton)
    frame_nav_layout.addStretch() # Push labels to the right
    frame_nav_layout.addWidget(main_window.frameLabel)
    frame_nav_layout.addSpacing(5)
    frame_nav_layout.addWidget(main_window.timeLabel)
    frame_nav_layout.addSpacing(5)
    frame_nav_layout.addWidget(main_window.fpsLabel)
    frame_nav_layout.addSpacing(10)
    frame_nav_layout.addWidget(main_window.filenameLabel)

    video_controls_layout.addLayout(frame_nav_layout)
    leftPanelLayout.addWidget(video_controls_group, stretch=0) # Don't stretch groupbox vertically
    main_window.mainSplitter.addWidget(main_window.leftPanelWidget)
    logger.debug("Left panel UI configured.")

    # --- Right Panel (Track Controls and Data Tabs) ---
    main_window.rightPanelWidget = QtWidgets.QWidget()
    # Set a maximum width for the right panel to prevent it becoming too wide.
    main_window.rightPanelWidget.setMaximumWidth(400)
    main_window.rightPanelWidget.setMinimumWidth(300) # Ensure minimum space
    rightPanelLayout = QtWidgets.QVBoxLayout(main_window.rightPanelWidget)
    rightPanelLayout.setContentsMargins(5, 5, 5, 5)
    rightPanelLayout.setSpacing(6)

    # Auto-Advance Controls GroupBox
    auto_advance_group = QtWidgets.QGroupBox("Frame Advance")
    auto_advance_layout = QtWidgets.QHBoxLayout(auto_advance_group)
    auto_advance_layout.setContentsMargins(6, 2, 6, 6) # Compact margins
    auto_advance_layout.setSpacing(6)

    main_window.autoAdvanceCheckBox = QtWidgets.QCheckBox("Auto-Advance on Click")
    main_window.autoAdvanceCheckBox.setToolTip("Automatically advance frame after adding/updating a point")
    auto_advance_layout.addWidget(main_window.autoAdvanceCheckBox)

    main_window.autoAdvanceSpinBox = QtWidgets.QSpinBox()
    main_window.autoAdvanceSpinBox.setMinimum(1)
    main_window.autoAdvanceSpinBox.setMaximum(100) # Sensible maximum
    main_window.autoAdvanceSpinBox.setValue(1)
    main_window.autoAdvanceSpinBox.setToolTip("Number of frames to advance automatically")
    auto_advance_layout.addWidget(main_window.autoAdvanceSpinBox)
    auto_advance_layout.addStretch(1) # Push controls left
    rightPanelLayout.addWidget(auto_advance_group)
    logger.debug("Auto-Advance panel configured.")

    # Data Tabs (Tracks, Points)
    main_window.dataTabsWidget = QtWidgets.QTabWidget()
    main_window.dataTabsWidget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
    rightPanelLayout.addWidget(main_window.dataTabsWidget, stretch=1) # Allow tabs vertical stretch

    # Tracks Tab
    tracksTab = QtWidgets.QWidget()
    tracksTabLayout = QtWidgets.QVBoxLayout(tracksTab)
    tracksTabLayout.setContentsMargins(2, 2, 2, 2) # Minimal tab margins

    main_window.tracksTableWidget = QtWidgets.QTableWidget()
    main_window.tracksTableWidget.verticalHeader().setVisible(False)
    main_window.tracksTableWidget.setColumnCount(config.TOTAL_TRACK_COLUMNS)
    main_window.tracksTableWidget.setHorizontalHeaderLabels(
        ["", "ID", "Points", "Start", "End", "", "", ""] # Use icons for visibility columns
    )
    main_window.tracksTableWidget.setAlternatingRowColors(True)
    main_window.tracksTableWidget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    main_window.tracksTableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    main_window.tracksTableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

    # Configure Tracks Table Header (Icons and Tooltips for Visibility)
    tracksHeader: QtWidgets.QHeaderView = main_window.tracksTableWidget.horizontalHeader()
    icon_hidden = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogCancelButton)
    tracksHeader.model().setHeaderData(config.COL_VIS_HIDDEN, QtCore.Qt.Orientation.Horizontal, icon_hidden, QtCore.Qt.ItemDataRole.DecorationRole)
    tracksHeader.model().setHeaderData(config.COL_VIS_HIDDEN, QtCore.Qt.Orientation.Horizontal, "Hidden: Track is never shown.", QtCore.Qt.ItemDataRole.ToolTipRole)
    icon_incremental = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowRight)
    tracksHeader.model().setHeaderData(config.COL_VIS_INCREMENTAL, QtCore.Qt.Orientation.Horizontal, icon_incremental, QtCore.Qt.ItemDataRole.DecorationRole)
    tracksHeader.model().setHeaderData(config.COL_VIS_INCREMENTAL, QtCore.Qt.Orientation.Horizontal, "Incremental: Track appears point-by-point as video advances.", QtCore.Qt.ItemDataRole.ToolTipRole)
    icon_always = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton)
    tracksHeader.model().setHeaderData(config.COL_VIS_ALWAYS, QtCore.Qt.Orientation.Horizontal, icon_always, QtCore.Qt.ItemDataRole.DecorationRole)
    tracksHeader.model().setHeaderData(config.COL_VIS_ALWAYS, QtCore.Qt.Orientation.Horizontal, "Always Visible: Entire track is shown on all frames.", QtCore.Qt.ItemDataRole.ToolTipRole)

    # Set Tracks Table Column Resize Modes
    tracksHeader.setSectionResizeMode(config.COL_DELETE, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksHeader.setSectionResizeMode(config.COL_TRACK_ID, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksHeader.setSectionResizeMode(config.COL_TRACK_POINTS, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksHeader.setSectionResizeMode(config.COL_TRACK_START_FRAME, QtWidgets.QHeaderView.ResizeMode.Stretch)
    tracksHeader.setSectionResizeMode(config.COL_TRACK_END_FRAME, QtWidgets.QHeaderView.ResizeMode.Stretch)
    tracksHeader.setSectionResizeMode(config.COL_VIS_HIDDEN, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksHeader.setSectionResizeMode(config.COL_VIS_INCREMENTAL, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tracksHeader.setSectionResizeMode(config.COL_VIS_ALWAYS, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    main_window.tracksTableWidget.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # Rows fit content

    tracksTabLayout.addWidget(main_window.tracksTableWidget)
    main_window.dataTabsWidget.addTab(tracksTab, "Tracks")
    logger.debug("Tracks tab configured.")

    # Points Tab
    pointsTab = QtWidgets.QWidget()
    pointsTabLayout = QtWidgets.QVBoxLayout(pointsTab)
    pointsTabLayout.setContentsMargins(2, 2, 2, 2)
    pointsTabLayout.setSpacing(4)

    main_window.pointsTabLabel = QtWidgets.QLabel("Points for Track: -")
    main_window.pointsTabLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    pointsTabLayout.addWidget(main_window.pointsTabLabel)

    main_window.pointsTableWidget = QtWidgets.QTableWidget()
    main_window.pointsTableWidget.setColumnCount(config.TOTAL_POINT_COLUMNS)
    main_window.pointsTableWidget.setHorizontalHeaderLabels(["Frame", "Time (s)", "X", "Y"])
    main_window.pointsTableWidget.setFont(QtGui.QFont("Monospace", 10)) # Monospace for coordinate alignment
    main_window.pointsTableWidget.setAlternatingRowColors(True)
    main_window.pointsTableWidget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    main_window.pointsTableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    main_window.pointsTableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    main_window.pointsTableWidget.verticalHeader().setVisible(False)

    # Set Points Table Column Resize Modes
    pointsHeader: QtWidgets.QHeaderView = main_window.pointsTableWidget.horizontalHeader()
    pointsHeader.setSectionResizeMode(config.COL_POINT_FRAME, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    pointsHeader.setSectionResizeMode(config.COL_POINT_TIME, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    pointsHeader.setSectionResizeMode(config.COL_POINT_X, QtWidgets.QHeaderView.ResizeMode.Stretch)
    pointsHeader.setSectionResizeMode(config.COL_POINT_Y, QtWidgets.QHeaderView.ResizeMode.Stretch)

    pointsTabLayout.addWidget(main_window.pointsTableWidget)
    main_window.dataTabsWidget.addTab(pointsTab, "Points")
    logger.debug("Points tab configured.")

    rightPanelLayout.addWidget(main_window.dataTabsWidget, stretch=1) # Add tabs before scale and coord

    # Scale Configuration Panel
    scale_config_group = QtWidgets.QGroupBox("Scale Configuration")
    scale_config_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
    scale_group_layout = QtWidgets.QVBoxLayout(scale_config_group)
    scale_group_layout.setContentsMargins(6, 6, 6, 6)
    scale_group_layout.setSpacing(8)

    # Input Row
    scale_input_layout = QtWidgets.QHBoxLayout()
    scale_input_layout.setSpacing(5) # Compact spacing within the row

    scale_input_layout.addWidget(QtWidgets.QLabel("Set scale:")) # General label
    scale_input_layout.addStretch(1) # Push specific inputs to the right a bit

    scale_input_layout.addWidget(QtWidgets.QLabel("m/px:"))
    main_window.scale_m_per_px_input = QtWidgets.QLineEdit()
    main_window.scale_m_per_px_input.setPlaceholderText("-")
    main_window.scale_m_per_px_input.setValidator(QtGui.QDoubleValidator(0.0, 1000000.0, 8, main_window.scale_m_per_px_input))
    main_window.scale_m_per_px_input.setToolTip("Enter scale as meters per pixel (e.g., 0.001)")
    main_window.scale_m_per_px_input.setMaximumWidth(100)
    scale_input_layout.addWidget(main_window.scale_m_per_px_input)

    scale_input_layout.addWidget(QtWidgets.QLabel("px/m:"))
    main_window.scale_px_per_m_input = QtWidgets.QLineEdit()
    main_window.scale_px_per_m_input.setPlaceholderText("-")
    main_window.scale_px_per_m_input.setValidator(QtGui.QDoubleValidator(0.0, 100000000.0, 8, main_window.scale_px_per_m_input))
    main_window.scale_px_per_m_input.setToolTip("Enter scale as pixels per meter (e.g., 1000)")
    main_window.scale_px_per_m_input.setMaximumWidth(100)
    scale_input_layout.addWidget(main_window.scale_px_per_m_input)

    main_window.scale_reset_button = QtWidgets.QPushButton()
    main_window.scale_reset_button.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogResetButton))
    main_window.scale_reset_button.setToolTip("Reset scale to undefined")
    main_window.scale_reset_button.setFixedSize(main_window.scale_reset_button.iconSize() + QtCore.QSize(10,5))
    scale_input_layout.addWidget(main_window.scale_reset_button)
    scale_input_layout.addStretch(2)

    scale_group_layout.addLayout(scale_input_layout)

    # Toggle Row (Display in meters AND Show Scale Bar)
    scale_toggle_layout = QtWidgets.QHBoxLayout()
    scale_toggle_layout.setSpacing(10) # Add some spacing between checkboxes

    main_window.scale_display_meters_checkbox = QtWidgets.QCheckBox("Display in meters")
    main_window.scale_display_meters_checkbox.setToolTip("Convert displayed values to meters (only if scale is set)")
    main_window.scale_display_meters_checkbox.setChecked(False)
    main_window.scale_display_meters_checkbox.setEnabled(False)
    scale_toggle_layout.addWidget(main_window.scale_display_meters_checkbox)

    # --- NEW: Add "Show Scale Bar" Checkbox ---
    main_window.showScaleBarCheckBox = QtWidgets.QCheckBox("Show Scale Bar")
    main_window.showScaleBarCheckBox.setToolTip("Toggle visibility of the scale bar on the image (only if scale is set)")
    main_window.showScaleBarCheckBox.setChecked(False) # Default to unchecked (will be checked if scale is set)
    main_window.showScaleBarCheckBox.setEnabled(False) # Initially disabled
    scale_toggle_layout.addWidget(main_window.showScaleBarCheckBox)
    # --- END NEW ---

    scale_toggle_layout.addStretch() # Align checkboxes to the left
    scale_group_layout.addLayout(scale_toggle_layout)

    rightPanelLayout.addWidget(scale_config_group)
    logger.debug("Scale Configuration panel configured.")

    # Coordinate System Controls GroupBox (using GridLayout)
    coords_group = QtWidgets.QGroupBox("Coordinate System")
    coords_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed) # Fixed vertical size
    coords_main_layout = QtWidgets.QVBoxLayout(coords_group)
    coords_main_layout.setContentsMargins(6, 6, 6, 6)
    coords_main_layout.setSpacing(8)

    # Grid layout for radio buttons, origin labels, and cursor labels
    grid_layout = QtWidgets.QGridLayout()
    grid_layout.setContentsMargins(0, 5, 0, 0) # Top margin before headers
    grid_layout.setHorizontalSpacing(10)
    grid_layout.setVerticalSpacing(5)

    main_window.coordSystemGroup = QtWidgets.QButtonGroup(main_window) # Manages radio button exclusivity

    label_min_width = 100 # Minimum width for origin coordinate labels
    cursor_label_min_width = 100 # Minimum width for cursor coordinate labels

    # Grid Column Headers (Row 0)
    header_origin_label = QtWidgets.QLabel("Origin")
    header_origin_label.setStyleSheet("font-weight: bold;")
    header_origin_label.setToolTip("The Top-Left coordinates of the system's origin")
    header_origin_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    header_cursor_label = QtWidgets.QLabel("Cursor [px]")
    header_cursor_label.setStyleSheet("font-weight: bold;")
    header_cursor_label.setToolTip("Live position of the mouse cursor in this coordinate system")
    header_cursor_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    header_cursor_m_label = QtWidgets.QLabel("Cursor [m]")
    header_cursor_m_label.setStyleSheet("font-weight: bold;")
    header_cursor_m_label.setToolTip("Live mouse cursor position in meters (if scale is set)")
    header_cursor_m_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

    grid_layout.addWidget(header_origin_label, 0, 1) # Origin header in Col 1
    grid_layout.addWidget(header_cursor_label, 0, 2) # Cursor [px] header in Col 2
    grid_layout.addWidget(header_cursor_m_label, 0, 3)  # Cursor [m] header in Col 3

    # Row 1: Top Left
    main_window.coordTopLeftRadio = QtWidgets.QRadioButton("TL")
    main_window.coordTopLeftRadio.setToolTip("Origin at (0,0), Y increases downwards")
    main_window.coordSystemGroup.addButton(main_window.coordTopLeftRadio)
    main_window.coordTopLeftOriginLabel = QtWidgets.QLabel("(0.0, 0.0)") # Fixed origin
    main_window.coordTopLeftOriginLabel.setToolTip("Effective origin (Top-Left Coordinates)")
    main_window.coordTopLeftOriginLabel.setMinimumWidth(label_min_width)
    main_window.coordTopLeftOriginLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    
    main_window.cursorPosLabelTL = QtWidgets.QLabel("(--, --)") # This is for [px]
    main_window.cursorPosLabelTL.setToolTip("Cursor position (Top-Left pixels)")
    main_window.cursorPosLabelTL.setMinimumWidth(cursor_label_min_width) # cursor_label_min_width might need adjustment
    main_window.cursorPosLabelTL.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

    main_window.cursorPosLabelTL_m = QtWidgets.QLabel("(--, --)") # NEW for [m]
    main_window.cursorPosLabelTL_m.setToolTip("Cursor position (Top-Left meters)")
    main_window.cursorPosLabelTL_m.setMinimumWidth(cursor_label_min_width) # Adjust as needed
    main_window.cursorPosLabelTL_m.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

    grid_layout.addWidget(main_window.coordTopLeftRadio, 1, 0)
    grid_layout.addWidget(main_window.coordTopLeftOriginLabel, 1, 1)
    grid_layout.addWidget(main_window.cursorPosLabelTL, 1, 2)    # px display
    grid_layout.addWidget(main_window.cursorPosLabelTL_m, 1, 3) # NEW: m display

    # Row 2: Bottom Left
    main_window.coordBottomLeftRadio = QtWidgets.QRadioButton("BL")
    main_window.coordBottomLeftRadio.setToolTip("Origin at (0, Frame Height), Y increases upwards")
    main_window.coordSystemGroup.addButton(main_window.coordBottomLeftRadio)
    main_window.coordBottomLeftOriginLabel = QtWidgets.QLabel("(0.0, -)") # Placeholder
    main_window.coordBottomLeftOriginLabel.setToolTip("Effective origin (Top-Left Coordinates)")
    main_window.coordBottomLeftOriginLabel.setMinimumWidth(label_min_width)
    main_window.coordBottomLeftOriginLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    
    main_window.cursorPosLabelBL = QtWidgets.QLabel("(--, --)") # px
    main_window.cursorPosLabelBL.setToolTip("Cursor position (Bottom-Left pixels)")
    main_window.cursorPosLabelBL.setMinimumWidth(cursor_label_min_width)
    main_window.cursorPosLabelBL.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

    main_window.cursorPosLabelBL_m = QtWidgets.QLabel("(--, --)") # NEW for [m]
    main_window.cursorPosLabelBL_m.setToolTip("Cursor position (Bottom-Left meters)")
    main_window.cursorPosLabelBL_m.setMinimumWidth(cursor_label_min_width)
    main_window.cursorPosLabelBL_m.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

    grid_layout.addWidget(main_window.coordBottomLeftRadio, 2, 0)
    grid_layout.addWidget(main_window.coordBottomLeftOriginLabel, 2, 1)
    grid_layout.addWidget(main_window.cursorPosLabelBL, 2, 2)    # px display
    grid_layout.addWidget(main_window.cursorPosLabelBL_m, 2, 3) # NEW: m display

    # Row 3: Custom
    main_window.coordCustomRadio = QtWidgets.QRadioButton("Cust.")
    main_window.coordCustomRadio.setToolTip("Origin set by user click, Y increases upwards")
    main_window.coordCustomRadio.setEnabled(False) # Enabled when video loads
    main_window.coordSystemGroup.addButton(main_window.coordCustomRadio)
    main_window.coordCustomOriginLabel = QtWidgets.QLabel("(-, -)") # Placeholder
    main_window.coordCustomOriginLabel.setToolTip("Effective custom origin (Top-Left Coordinates)")
    main_window.coordCustomOriginLabel.setMinimumWidth(label_min_width)
    main_window.coordCustomOriginLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    
    main_window.cursorPosLabelCustom = QtWidgets.QLabel("(--, --)") # px
    main_window.cursorPosLabelCustom.setToolTip("Cursor position (Custom pixels)")
    main_window.cursorPosLabelCustom.setMinimumWidth(cursor_label_min_width)
    main_window.cursorPosLabelCustom.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

    main_window.cursorPosLabelCustom_m = QtWidgets.QLabel("(--, --)") # NEW for [m]
    main_window.cursorPosLabelCustom_m.setToolTip("Cursor position (Custom meters)")
    main_window.cursorPosLabelCustom_m.setMinimumWidth(cursor_label_min_width)
    main_window.cursorPosLabelCustom_m.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

    grid_layout.addWidget(main_window.coordCustomRadio, 3, 0)
    grid_layout.addWidget(main_window.coordCustomOriginLabel, 3, 1)
    grid_layout.addWidget(main_window.cursorPosLabelCustom, 3, 2)    # px display
    grid_layout.addWidget(main_window.cursorPosLabelCustom_m, 3, 3) # NEW: m display

    # Configure grid stretching and minimum widths for alignment
    grid_layout.setColumnMinimumWidth(1, label_min_width) # Origin TL
    grid_layout.setColumnMinimumWidth(2, cursor_label_min_width) # Cursor [px]
    grid_layout.setColumnMinimumWidth(3, cursor_label_min_width) # Cursor [m]
    grid_layout.setColumnStretch(4, 1) # Add stretch to a new last column if needed, or adjust existing.
                                       # Or, allow the last content column to take available space.
    coords_main_layout.addLayout(grid_layout) # Add grid to the group's main layout

    # Bottom Controls Row (Show Origin Checkbox and Pick Custom Button)
    bottom_controls_layout = QtWidgets.QHBoxLayout()
    bottom_controls_layout.setContentsMargins(0, 5, 0, 0) # Top margin
    bottom_controls_layout.setSpacing(10)
    main_window.showOriginCheckBox = QtWidgets.QCheckBox("Show Origin")
    main_window.showOriginCheckBox.setToolTip("Toggle visibility of the effective origin marker on the image")
    main_window.showOriginCheckBox.setChecked(True) # Default to showing origin
    bottom_controls_layout.addWidget(main_window.showOriginCheckBox)
    main_window.setOriginButton = QtWidgets.QPushButton("Pick Custom")
    main_window.setOriginButton.setToolTip("Click to enable origin selection mode, then click on the image")
    bottom_controls_layout.addWidget(main_window.setOriginButton)
    bottom_controls_layout.addStretch() # Push controls left
    coords_main_layout.addLayout(bottom_controls_layout)

    # Add the Coordinate System GroupBox to the main right panel layout
    rightPanelLayout.addWidget(coords_group, stretch=0) # Don't stretch groupbox vertically
    logger.debug("Coordinate System panel configured.")

    # Finish Right Panel and Splitter
    main_window.mainSplitter.addWidget(main_window.rightPanelWidget)
    logger.debug("Right panel UI configured.")

    # Set Initial Splitter Sizes and Stretch Factors
    try:
        # Attempt to set a reasonable initial size ratio
        initial_width = main_window.width()
        # Give more space to the image view initially (e.g., 75%)
        initial_sizes: List[int] = [int(initial_width * 0.75), int(initial_width * 0.25)]
        main_window.mainSplitter.setSizes(initial_sizes)
    except Exception as e:
        # Fallback if initial width isn't reliable yet
        logger.warning(f"Could not set initial splitter sizes dynamically: {e}. Using fixed fallback.")
        main_window.mainSplitter.setSizes([650, 350])

    # Control how panels resize relative to each other
    main_window.mainSplitter.setStretchFactor(0, 3) # Left Panel (ImageView) gets more resize space
    main_window.mainSplitter.setStretchFactor(1, 1) # Right Panel (Controls) gets less
    logger.debug("Main splitter sizes and stretch factors configured.")

    # --- Create Menus ---
    logger.debug("Creating menus...")
    menu_bar: QtWidgets.QMenuBar = main_window.menuBar()

    # File Menu
    file_menu: QtWidgets.QMenu = menu_bar.addMenu("&File")
    open_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton)
    open_action = QtGui.QAction(open_icon, "&Open Video...", main_window)
    open_action.setStatusTip("Select and load a video file")
    open_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
    open_action.triggered.connect(main_window.open_video) # Connection defined in main_window
    file_menu.addAction(open_action)
    file_menu.addSeparator()

    load_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowUp)
    main_window.loadTracksAction = QtGui.QAction(load_icon, "&Load Tracks...", main_window)
    main_window.loadTracksAction.setStatusTip("Load pyroclast track data from a CSV file")
    # *** RESTORED CONNECTION ***
    main_window.loadTracksAction.triggered.connect(main_window._trigger_load_tracks)
    main_window.loadTracksAction.setEnabled(False)
    file_menu.addAction(main_window.loadTracksAction)

    save_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton)
    main_window.saveTracksAction = QtGui.QAction(save_icon, "&Save Tracks As...", main_window)
    main_window.saveTracksAction.setStatusTip("Save current pyroclast track data to a CSV file")
    main_window.saveTracksAction.setShortcut(QtGui.QKeySequence.StandardKey.SaveAs)
    # Connection for _trigger_save_tracks defined in MainWindow __init__ or here if preferred
    main_window.saveTracksAction.triggered.connect(main_window._trigger_save_tracks) # Ensure connection exists
    main_window.saveTracksAction.setEnabled(False)
    file_menu.addAction(main_window.saveTracksAction)
    file_menu.addSeparator()

    info_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogInfoView)
    main_window.videoInfoAction = QtGui.QAction(info_icon, "Video Information...", main_window)
    main_window.videoInfoAction.setStatusTip("Show technical information about the loaded video")
    # Connection for _show_video_info_dialog in main_window
    main_window.videoInfoAction.setEnabled(False)
    file_menu.addAction(main_window.videoInfoAction)
    file_menu.addSeparator()

    exit_icon: QtGui.QIcon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogCloseButton)
    exit_action = QtGui.QAction(exit_icon, "E&xit", main_window)
    exit_action.setStatusTip("Exit the application")
    exit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
    exit_action.triggered.connect(main_window.close) # Connect directly to main window's close slot
    file_menu.addAction(exit_action)

    # Edit Menu
    edit_menu: QtWidgets.QMenu = menu_bar.addMenu("&Edit")

    # Add New Track action (primarily for shortcut)
    # Icon could be SP_FileIcon or similar if desired visually in menu
    main_window.newTrackAction = QtGui.QAction("&New Track", main_window)
    main_window.newTrackAction.setStatusTip("Create a new track for marking points")
    # Shortcut and connection handled in MainWindow.__init__
    main_window.newTrackAction.setEnabled(False)
    edit_menu.addAction(main_window.newTrackAction)
    edit_menu.addSeparator()

    # Preferences Action
    prefs_icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView)
    main_window.preferencesAction = QtGui.QAction(prefs_icon, "&Preferences...", main_window)
    main_window.preferencesAction.setStatusTip("Edit application preferences (colors, sizes, etc.)")
    # Connection for _show_preferences_dialog in main_window
    edit_menu.addAction(main_window.preferencesAction)

    # Help Menu
    help_menu: QtWidgets.QMenu = menu_bar.addMenu("&Help")
    about_action = QtGui.QAction("&About", main_window)
    about_action.setStatusTip("Show information about this application")
    about_action.triggered.connect(main_window._show_about_dialog) # Connection defined in main_window
    help_menu.addAction(about_action)

    # --- Status Bar ---
    # Create and set the status bar instance on the main window
    main_window.setStatusBar(QtWidgets.QStatusBar())

    logger.info("MainWindow UI setup complete.")