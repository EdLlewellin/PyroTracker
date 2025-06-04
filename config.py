# config.py
"""
Central configuration file for PyroTracker constants.
"""
from PySide6 import QtGui

# --- CSV Constants ---
# Legacy CSV constants (CSV_METADATA_PREFIX, CSV_HEADER, EXPECTED_METADATA_KEYS)
# have been removed as they are not used by the new JSON project format
# or the planned data-only CSV export. New CSV export headers will be
# defined by the export function itself.

# Metadata Keys (still relevant for JSON project metadata and potentially new CSV headers)
META_FILENAME = "Video Filename"
META_WIDTH = "Frame Width"
META_HEIGHT = "Frame Height"
META_FRAMES = "Frame Count"
META_FPS = "FPS"
META_DURATION = "Duration (ms)"
META_SCALE_FACTOR_M_PER_PX = "Scale Factor (m/px)"
META_DATA_UNITS = "Data Units" # Expected values: "px" or "m" for project metadata internal consistency
META_COORD_SYSTEM_MODE = "Coordinate System Mode"
META_COORD_ORIGIN_X_TL = "Coordinate Origin X (TL)"
META_COORD_ORIGIN_Y_TL = "Coordinate Origin Y (TL)"
META_APP_NAME = "Application Name"
META_APP_VERSION = "Application Version"
META_SCALE_LINE_P1X = "Scale Line P1 X (Scene px)"
META_SCALE_LINE_P1Y = "Scale Line P1 Y (Scene px)"
META_SCALE_LINE_P2X = "Scale Line P2 X (Scene px)"
META_SCALE_LINE_P2Y = "Scale Line P2 Y (Scene px)"
META_SHOW_MEASUREMENT_LINE_LENGTHS = "Show Measurement Line Lengths" # [cite: 75]


# --- Table Column Indices ---
# Shared column indices for UI tables.
# Tracks Table Columns
COL_DELETE = 0
COL_TRACK_ID = 1
COL_TRACK_POINTS = 2
COL_TRACK_START_FRAME = 3
COL_TRACK_END_FRAME = 4
COL_VIS_HIDDEN = 5
COL_VIS_HOME_FRAME = 6
COL_VIS_INCREMENTAL = 7
COL_VIS_ALWAYS = 8
TOTAL_TRACK_COLUMNS = 9

# Points Table Columns
COL_POINT_FRAME = 0
COL_POINT_TIME = 1
COL_POINT_X = 2
COL_POINT_Y = 3
TOTAL_POINT_COLUMNS = 4

# Lines Table Columns
COL_LINE_DELETE = 0
COL_LINE_ID = 1
COL_LINE_FRAME = 2
COL_LINE_LENGTH = 3
COL_LINE_ANGLE = 4
COL_LINE_VIS_HIDDEN = 5
COL_LINE_VIS_HOME_FRAME = 6
COL_LINE_VIS_INCREMENTAL = 7
COL_LINE_VIS_ALWAYS = 8
TOTAL_LINE_COLUMNS = 9

# --- Visual Style Constants ---
# Shared visual style constants.
# Track Markers/Lines
DEFAULT_MARKER_SIZE = 5.0
DEFAULT_LINE_WIDTH = 1.0

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
# --- NEW: Style identifiers for Measurement Lines ---
STYLE_MEASUREMENT_LINE_NORMAL = "style_measurement_line_normal"
STYLE_MEASUREMENT_LINE_ACTIVE = "style_measurement_line_active"
# --- END NEW ---

CLICK_TOLERANCE = 10.0
CLICK_TOLERANCE_SQ = CLICK_TOLERANCE * CLICK_TOLERANCE

# --- Formatting Constants for Scale Display ---
UNIT_PREFIXES = [
    (1e3, "km", None),
    (1.0, "m", None),
    (1e-2, "cm", None),
    (1e-3, "mm", None),
    (1e-6, "µm", None),
    (1e-9, "nm", None)
]
SCIENTIFIC_NOTATION_UPPER_THRESHOLD = 1000e3
SCIENTIFIC_NOTATION_LOWER_THRESHOLD = 1e-9
ROUND_NUMBER_SEQUENCE = [1.0, 2.0, 2.5, 5.0]

# --- Interaction Constants ---
DRAG_THRESHOLD = 5
MAX_ABS_SCALE = 50.0

# --- Application Info ---
APP_NAME = "PyroTracker"
APP_ORGANIZATION = "Durham University"
APP_VERSION = "3.1.0 Beta"