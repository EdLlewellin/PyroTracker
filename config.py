# config.py
"""
Central configuration file for PyroTracker constants.
"""
from PySide6 import QtGui

# --- CSV Constants ---
CSV_METADATA_PREFIX = "# "
CSV_HEADER = ["track_id", "frame_index", "time_ms", "x", "y"]

# Metadata Keys
META_FILENAME = "Video Filename"
META_WIDTH = "Frame Width"
META_HEIGHT = "Frame Height"
META_FRAMES = "Frame Count"
META_FPS = "FPS"
META_DURATION = "Duration (ms)"
META_COORD_SYSTEM_MODE = "Coordinate System Mode"
META_COORD_ORIGIN_X_TL = "Coordinate Origin X (TL)"
META_COORD_ORIGIN_Y_TL = "Coordinate Origin Y (TL)"
META_APP_NAME = "Application Name"
META_APP_VERSION = "Application Version"

# Metadata keys expected in CSV header for validation and writing.
EXPECTED_METADATA_KEYS = [
    META_APP_NAME, META_APP_VERSION,
    META_FILENAME, META_WIDTH, META_HEIGHT, META_FRAMES, META_FPS, META_DURATION,
    META_COORD_SYSTEM_MODE, META_COORD_ORIGIN_X_TL, META_COORD_ORIGIN_Y_TL
]


# --- Table Column Indices ---
# Shared column indices for UI tables.
# Tracks Table Columns
COL_DELETE = 0
COL_TRACK_ID = 1
COL_TRACK_POINTS = 2
COL_TRACK_START_FRAME = 3
COL_TRACK_END_FRAME = 4
COL_VIS_HIDDEN = 5
COL_VIS_INCREMENTAL = 6
COL_VIS_ALWAYS = 7
TOTAL_TRACK_COLUMNS = 8

# Points Table Columns
COL_POINT_FRAME = 0
COL_POINT_TIME = 1
COL_POINT_X = 2
COL_POINT_Y = 3
TOTAL_POINT_COLUMNS = 4


# --- Visual Style Constants ---
# Shared visual style constants.
# Track Markers/Lines
DEFAULT_MARKER_SIZE = 5.0   # Diameter/length of the marker cross in pixels
DEFAULT_LINE_WIDTH = 1.0    # Width of the connecting lines in pixels

# Default color values (as strings).
DEFAULT_ACTIVE_MARKER_COLOR_STR = "yellow"
DEFAULT_ACTIVE_LINE_COLOR_STR = "yellow"
DEFAULT_ACTIVE_CURRENT_MARKER_COLOR_STR = "red"
DEFAULT_INACTIVE_MARKER_COLOR_STR = "blue"
DEFAULT_INACTIVE_LINE_COLOR_STR = "blue"
DEFAULT_INACTIVE_CURRENT_MARKER_COLOR_STR = "cyan"
DEFAULT_ORIGIN_MARKER_COLOR_STR = "red"

# Origin Marker Defaults (Size and Pen Width)
DEFAULT_ORIGIN_MARKER_SIZE = 8.0
DEFAULT_ORIGIN_MARKER_PEN_WIDTH = 1.0

# Style identifiers used for drawing.
STYLE_MARKER_ACTIVE_CURRENT = "marker_active_current"
STYLE_MARKER_ACTIVE_OTHER = "marker_active_other"
STYLE_MARKER_INACTIVE_CURRENT = "marker_inactive_current"
STYLE_MARKER_INACTIVE_OTHER = "marker_inactive_other"
STYLE_LINE_ACTIVE = "line_active"
STYLE_LINE_INACTIVE = "line_inactive"

CLICK_TOLERANCE = 10.0      # Pixel distance tolerance for selecting tracks via click
CLICK_TOLERANCE_SQ = CLICK_TOLERANCE * CLICK_TOLERANCE # Squared tolerance avoids sqrt

# --- Interaction Constants ---
# Shared interaction constants.
DRAG_THRESHOLD = 5      # Pixels mouse must move to register as a drag, not a click
MAX_ABS_SCALE = 50.0    # Absolute maximum allowed view scale factor (e.g., 50x zoom)


# --- Application Info ---
APP_NAME = "PyroTracker"
APP_ORGANIZATION = "Durham University"
APP_VERSION = "2.0.0 Beta"