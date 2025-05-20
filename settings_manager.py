# settings_manager.py
"""
Manages application settings using QSettings, providing type-safe access
and default values.
"""
import logging
from typing import Any, Optional

from PySide6 import QtCore, QtGui

import config # Used for app name/org and some default values

logger = logging.getLogger(__name__)

# --- Define Setting Keys ---
VISUALS_GROUP = "visuals" # Group for track and origin visuals
KEY_ACTIVE_MARKER_COLOR = f"{VISUALS_GROUP}/activeMarkerColor"
KEY_ACTIVE_LINE_COLOR = f"{VISUALS_GROUP}/activeLineColor"
KEY_ACTIVE_CURRENT_MARKER_COLOR = f"{VISUALS_GROUP}/activeCurrentMarkerColor"
KEY_INACTIVE_MARKER_COLOR = f"{VISUALS_GROUP}/inactiveMarkerColor"
KEY_INACTIVE_LINE_COLOR = f"{VISUALS_GROUP}/inactiveLineColor"
KEY_INACTIVE_CURRENT_MARKER_COLOR = f"{VISUALS_GROUP}/inactiveCurrentMarkerColor"
KEY_MARKER_SIZE = f"{VISUALS_GROUP}/markerSize"
KEY_LINE_WIDTH = f"{VISUALS_GROUP}/lineWidth"
KEY_ORIGIN_MARKER_COLOR = f"{VISUALS_GROUP}/originMarkerColor"
KEY_ORIGIN_MARKER_SIZE = f"{VISUALS_GROUP}/originMarkerSize"

SCALES_GROUP = "scales_visuals"
KEY_SCALE_BAR_COLOR = f"{SCALES_GROUP}/scaleBarColor"
KEY_FEATURE_SCALE_LINE_COLOR = f"{SCALES_GROUP}/featureScaleLineColor"
KEY_FEATURE_SCALE_LINE_TEXT_COLOR = f"{SCALES_GROUP}/featureScaleLineTextColor"
KEY_FEATURE_SCALE_LINE_TEXT_SIZE = f"{SCALES_GROUP}/featureScaleLineTextSize"
KEY_FEATURE_SCALE_LINE_WIDTH = f"{SCALES_GROUP}/featureScaleLineWidth"
KEY_FEATURE_SCALE_LINE_SHOW_TICKS = f"{SCALES_GROUP}/featureScaleLineShowTicks"
KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR = f"{SCALES_GROUP}/featureScaleLineTickLengthFactor"
KEY_SCALE_BAR_RECT_HEIGHT = f"{SCALES_GROUP}/scaleBarRectHeight"
KEY_SCALE_BAR_TEXT_FONT_SIZE = f"{SCALES_GROUP}/scaleBarTextFontSize"

# --- NEW: Info Overlays Group and Keys ---
INFO_OVERLAYS_GROUP = "info_overlays"
# Visibility Keys
KEY_INFO_OVERLAY_SHOW_FILENAME = f"{INFO_OVERLAYS_GROUP}/showFilename"
KEY_INFO_OVERLAY_SHOW_TIME = f"{INFO_OVERLAYS_GROUP}/showTime"
KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER = f"{INFO_OVERLAYS_GROUP}/showFrameNumber"

# Appearance Keys (Color)
KEY_INFO_OVERLAY_FILENAME_COLOR = f"{INFO_OVERLAYS_GROUP}/filenameColor"
KEY_INFO_OVERLAY_TIME_COLOR = f"{INFO_OVERLAYS_GROUP}/timeColor"
KEY_INFO_OVERLAY_FRAME_NUMBER_COLOR = f"{INFO_OVERLAYS_GROUP}/frameNumberColor"

# Appearance Keys (Font Size)
KEY_INFO_OVERLAY_FILENAME_FONT_SIZE = f"{INFO_OVERLAYS_GROUP}/filenameFontSize"
KEY_INFO_OVERLAY_TIME_FONT_SIZE = f"{INFO_OVERLAYS_GROUP}/timeFontSize"
KEY_INFO_OVERLAY_FRAME_NUMBER_FONT_SIZE = f"{INFO_OVERLAYS_GROUP}/frameNumberFontSize"

# (Future: Position keys could be added here, e.g., KEY_INFO_OVERLAY_FILENAME_POSITION)

DEFAULT_SETTINGS = {
    KEY_ACTIVE_MARKER_COLOR: QtGui.QColor("yellow"),
    KEY_ACTIVE_LINE_COLOR: QtGui.QColor("yellow"),
    KEY_ACTIVE_CURRENT_MARKER_COLOR: QtGui.QColor("red"),
    KEY_INACTIVE_MARKER_COLOR: QtGui.QColor("blue"),
    KEY_INACTIVE_LINE_COLOR: QtGui.QColor("blue"),
    KEY_INACTIVE_CURRENT_MARKER_COLOR: QtGui.QColor("cyan"),
    KEY_MARKER_SIZE: config.DEFAULT_MARKER_SIZE,
    KEY_LINE_WIDTH: config.DEFAULT_LINE_WIDTH,
    KEY_ORIGIN_MARKER_COLOR: QtGui.QColor(config.DEFAULT_ORIGIN_MARKER_COLOR_STR),
    KEY_ORIGIN_MARKER_SIZE: config.DEFAULT_ORIGIN_MARKER_SIZE,

    KEY_SCALE_BAR_COLOR: QtGui.QColor("white"),
    KEY_FEATURE_SCALE_LINE_COLOR: QtGui.QColor("magenta"),
    KEY_FEATURE_SCALE_LINE_TEXT_COLOR: QtGui.QColor("magenta"),
    KEY_FEATURE_SCALE_LINE_TEXT_SIZE: 18,
    KEY_FEATURE_SCALE_LINE_WIDTH: 1.5,
    KEY_FEATURE_SCALE_LINE_SHOW_TICKS: True,
    KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR: 3.0,
    KEY_SCALE_BAR_RECT_HEIGHT: 4,
    KEY_SCALE_BAR_TEXT_FONT_SIZE: 10,

    # --- NEW: Default values for Info Overlays ---
    # Visibility (default to visible for now, user can hide via View menu)
    KEY_INFO_OVERLAY_SHOW_FILENAME: True,
    KEY_INFO_OVERLAY_SHOW_TIME: True,
    KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER: True,

    # Appearance (Colors - default to white like scale bar)
    KEY_INFO_OVERLAY_FILENAME_COLOR: QtGui.QColor("white"),
    KEY_INFO_OVERLAY_TIME_COLOR: QtGui.QColor("white"),
    KEY_INFO_OVERLAY_FRAME_NUMBER_COLOR: QtGui.QColor("white"),

    # Appearance (Font Sizes - default to a readable size)
    KEY_INFO_OVERLAY_FILENAME_FONT_SIZE: 10, # pt
    KEY_INFO_OVERLAY_TIME_FONT_SIZE: 10,     # pt
    KEY_INFO_OVERLAY_FRAME_NUMBER_FONT_SIZE: 10, # pt
}

_settings_instance: Optional[QtCore.QSettings] = None

def _get_settings() -> QtCore.QSettings:
    global _settings_instance
    if _settings_instance is None:
        app = QtCore.QCoreApplication.instance()
        if app:
             if not QtCore.QCoreApplication.organizationName():
                 QtCore.QCoreApplication.setOrganizationName(config.APP_ORGANIZATION)
             if not QtCore.QCoreApplication.applicationName():
                 QtCore.QCoreApplication.setApplicationName(config.APP_NAME)
        else:
             logger.warning("QCoreApplication instance not found. Setting fallback names for QSettings.")
             import os
             QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
             config_path = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppConfigLocation)
             if not os.path.exists(config_path):
                 os.makedirs(config_path, exist_ok=True)
             pass # QSettings will use fallback paths if AppConfigLocation is tricky

        _settings_instance = QtCore.QSettings(config.APP_ORGANIZATION, config.APP_NAME)
        logger.info(f"QSettings initialized. Path: {_settings_instance.fileName()} Status: {_settings_instance.status().name}")
    return _settings_instance

def get_setting(key: str, default_override: Optional[Any] = None) -> Any:
    settings = _get_settings()
    default_value_from_map = DEFAULT_SETTINGS.get(key)

    effective_default = default_override if default_override is not None else default_value_from_map

    if effective_default is None and key not in DEFAULT_SETTINGS:
        logger.error(f"CRITICAL: No default defined anywhere for key '{key}'. This is a programming error.")
        return None # Or raise an exception

    stored_value = settings.value(key)

    # If the key has never been stored, settings.value() might return None.
    # In this case, we should definitely use our effective_default.
    if stored_value is None:
        # logger.debug(f"Setting key '{key}' not found in QSettings. Returning effective default: {effective_default}")
        return effective_default

    # Determine the expected type from our DEFAULT_SETTINGS map.
    # This is crucial for correct type conversion.
    expected_type = type(effective_default)

    # Type conversion logic
    if expected_type is QtGui.QColor:
        # QSettings stores QColor as string (its name()); we need to convert back.
        color = QtGui.QColor(str(stored_value))
        if color.isValid():
            return color
        else:
            logger.warning(f"Invalid color string '{stored_value}' retrieved for key '{key}'. Returning effective default.")
            return effective_default # Use the QColor object from defaults
    elif expected_type is float:
        try:
            return float(stored_value)
        except (ValueError, TypeError): # Catches if stored_value is not convertible
            logger.warning(f"Cannot convert stored value '{stored_value}' to float for key '{key}'. Returning effective default.")
            return effective_default
    elif expected_type is int:
        try:
            # Attempt conversion robustly, e.g., if it was stored as "10.0" for an int.
            return int(float(str(stored_value)))
        except (ValueError, TypeError):
            logger.warning(f"Cannot convert stored value '{stored_value}' to int for key '{key}'. Returning effective default.")
            return effective_default
    elif expected_type is bool:
        # QSettings might store bools as "true"/"false" strings, or 0/1.
        if isinstance(stored_value, str):
            if stored_value.lower() == 'true': return True
            if stored_value.lower() == 'false': return False
        try:
            # Try converting to int first, then to bool (0=False, non-zero=True)
            return bool(int(float(str(stored_value))))
        except (ValueError, TypeError): # Fallback if conversion fails
            logger.warning(f"Could not convert stored value '{stored_value}' to bool via int for key '{key}'. Returning effective default.")
            return effective_default

    # If no specific conversion was needed or successful,
    # check if the retrieved type matches the expected type.
    if isinstance(stored_value, expected_type):
        return stored_value
    else:
        # This case handles unexpected types not caught by specific conversions.
        logger.warning(f"Type mismatch for key '{key}'. Expected {expected_type}, got {type(stored_value)}. Value: '{stored_value}'. Returning effective default.")
        return effective_default


def set_setting(key: str, value: Any) -> None:
    settings = _get_settings()
    value_to_store = value

    # Convert specific types to storable formats
    if isinstance(value, QtGui.QColor):
        value_to_store = value.name() # QColor.name() gives string like "#RRGGBB"
    elif isinstance(value, bool):
        # Store booleans as "true" or "false" strings for clarity in INI files
        value_to_store = "true" if value else "false"
    # Floats and ints can often be stored directly, QSettings handles their string conversion.

    logger.debug(f"Saving setting '{key}' with value: {value_to_store} (Original type: {type(value)})")
    settings.setValue(key, value_to_store)
    settings.sync() # Ensure changes are written to disk
    logger.debug(f"QSettings status after sync for '{key}': {settings.status().name}")
    if settings.status() != QtCore.QSettings.Status.NoError:
        logger.error(f"Error saving setting '{key}': {settings.status().name}")