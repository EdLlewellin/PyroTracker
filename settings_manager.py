# settings_manager.py
"""
Manages application settings using QSettings, providing type-safe access
and default values.
"""
import logging
from typing import Any, Optional
import os # Import os for path operations

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

INFO_OVERLAYS_GROUP = "info_overlays"
KEY_INFO_OVERLAY_SHOW_FILENAME = f"{INFO_OVERLAYS_GROUP}/showFilename"
KEY_INFO_OVERLAY_SHOW_TIME = f"{INFO_OVERLAYS_GROUP}/showTime"
KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER = f"{INFO_OVERLAYS_GROUP}/showFrameNumber"
KEY_INFO_OVERLAY_FILENAME_COLOR = f"{INFO_OVERLAYS_GROUP}/filenameColor"
KEY_INFO_OVERLAY_TIME_COLOR = f"{INFO_OVERLAYS_GROUP}/timeColor"
KEY_INFO_OVERLAY_FRAME_NUMBER_COLOR = f"{INFO_OVERLAYS_GROUP}/frameNumberColor"
KEY_INFO_OVERLAY_FILENAME_FONT_SIZE = f"{INFO_OVERLAYS_GROUP}/filenameFontSize"
KEY_INFO_OVERLAY_TIME_FONT_SIZE = f"{INFO_OVERLAYS_GROUP}/timeFontSize"
KEY_INFO_OVERLAY_FRAME_NUMBER_FONT_SIZE = f"{INFO_OVERLAYS_GROUP}/frameNumberFontSize"

MEASUREMENT_LINES_GROUP = "measurement_lines_visuals"
KEY_MEASUREMENT_LINE_COLOR = f"{MEASUREMENT_LINES_GROUP}/measurementLineColor"
KEY_MEASUREMENT_LINE_ACTIVE_COLOR = f"{MEASUREMENT_LINES_GROUP}/measurementLineActiveColor"
KEY_MEASUREMENT_LINE_WIDTH = f"{MEASUREMENT_LINES_GROUP}/measurementLineWidth"
KEY_MEASUREMENT_LINE_LENGTH_TEXT_COLOR = f"{MEASUREMENT_LINES_GROUP}/measurementLineLengthTextColor"
KEY_MEASUREMENT_LINE_LENGTH_TEXT_FONT_SIZE = f"{MEASUREMENT_LINES_GROUP}/measurementLineLengthTextFontSize"
KEY_SHOW_MEASUREMENT_LINE_LENGTHS = f"{MEASUREMENT_LINES_GROUP}/showMeasurementLineLengths"

# --- BEGIN MODIFICATION: Add key for last project directory ---
PROJECT_STATE_GROUP = "project_state"
KEY_LAST_PROJECT_DIRECTORY = f"{PROJECT_STATE_GROUP}/lastProjectDirectory"
# --- END MODIFICATION ---


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

    KEY_INFO_OVERLAY_SHOW_FILENAME: True,
    KEY_INFO_OVERLAY_SHOW_TIME: True,
    KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER: True,
    KEY_INFO_OVERLAY_FILENAME_COLOR: QtGui.QColor("white"),
    KEY_INFO_OVERLAY_TIME_COLOR: QtGui.QColor("white"),
    KEY_INFO_OVERLAY_FRAME_NUMBER_COLOR: QtGui.QColor("white"),
    KEY_INFO_OVERLAY_FILENAME_FONT_SIZE: 10, 
    KEY_INFO_OVERLAY_TIME_FONT_SIZE: 10,     
    KEY_INFO_OVERLAY_FRAME_NUMBER_FONT_SIZE: 10, 

    KEY_MEASUREMENT_LINE_COLOR: QtGui.QColor("lime"), 
    KEY_MEASUREMENT_LINE_ACTIVE_COLOR: QtGui.QColor("aqua"), 
    KEY_MEASUREMENT_LINE_WIDTH: 1.5, 
    KEY_MEASUREMENT_LINE_LENGTH_TEXT_COLOR: QtGui.QColor("lime"), 
    KEY_MEASUREMENT_LINE_LENGTH_TEXT_FONT_SIZE: 12, 
    KEY_SHOW_MEASUREMENT_LINE_LENGTHS: True, 

    # --- BEGIN MODIFICATION: Add default for last project directory ---
    KEY_LAST_PROJECT_DIRECTORY: "", # Default to empty string, logic in MainWindow will handle fallback to os.getcwd()
    # --- END MODIFICATION ---
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
             QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
             config_path = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppConfigLocation)
             if not os.path.exists(config_path):
                 os.makedirs(config_path, exist_ok=True)
             # QSettings will use fallback paths if AppConfigLocation is tricky

        _settings_instance = QtCore.QSettings(config.APP_ORGANIZATION, config.APP_NAME)
        logger.info(f"QSettings initialized. Path: {_settings_instance.fileName()} Status: {_settings_instance.status().name}")
    return _settings_instance

def get_setting(key: str, default_override: Optional[Any] = None) -> Any:
    settings = _get_settings()
    default_value_from_map = DEFAULT_SETTINGS.get(key)

    effective_default = default_override if default_override is not None else default_value_from_map

    if effective_default is None and key not in DEFAULT_SETTINGS:
        # --- BEGIN MODIFICATION: Check if key starts with PROJECT_STATE_GROUP for string defaults ---
        # Handle cases like KEY_LAST_PROJECT_DIRECTORY which might not have a complex type default in map
        # but is expected to be a string.
        if key.startswith(PROJECT_STATE_GROUP + "/"): # If it's a project state key not in map
            effective_default = "" # Assume string default if not explicitly in DEFAULT_SETTINGS
            logger.debug(f"Key '{key}' not in DEFAULT_SETTINGS map, but is project state. Using empty string as default.")
        else: # --- END MODIFICATION ---
            logger.error(f"CRITICAL: No default defined anywhere for key '{key}'. This is a programming error.")
            return None 

    stored_value = settings.value(key)

    if stored_value is None:
        return effective_default

    # --- BEGIN MODIFICATION: Ensure expected_type is determined correctly, especially for new string keys ---
    expected_type = type(effective_default) if effective_default is not None else str
    if key == KEY_LAST_PROJECT_DIRECTORY and effective_default == "": # Explicitly handle if default was empty string
        expected_type = str
    # --- END MODIFICATION ---
    
    if expected_type is QtGui.QColor:
        color = QtGui.QColor(str(stored_value))
        if color.isValid():
            return color
        else:
            logger.warning(f"Invalid color string '{stored_value}' retrieved for key '{key}'. Returning effective default.")
            return effective_default 
    elif expected_type is float:
        try:
            return float(stored_value)
        except (ValueError, TypeError): 
            logger.warning(f"Cannot convert stored value '{stored_value}' to float for key '{key}'. Returning effective default.")
            return effective_default
    elif expected_type is int:
        try:
            return int(float(str(stored_value)))
        except (ValueError, TypeError):
            logger.warning(f"Cannot convert stored value '{stored_value}' to int for key '{key}'. Returning effective default.")
            return effective_default
    elif expected_type is bool:
        if isinstance(stored_value, str):
            if stored_value.lower() == 'true': return True
            if stored_value.lower() == 'false': return False
        try:
            return bool(int(float(str(stored_value))))
        except (ValueError, TypeError): 
            logger.warning(f"Could not convert stored value '{stored_value}' to bool via int for key '{key}'. Returning effective default.")
            return effective_default
    # --- BEGIN MODIFICATION: Add handling for simple string types ---
    elif expected_type is str:
        if isinstance(stored_value, str):
            return stored_value
        else:
            # Attempt to convert to string if it's not already, though QSettings usually stores strings.
            try:
                return str(stored_value)
            except Exception:
                logger.warning(f"Could not convert stored value '{stored_value}' to string for key '{key}'. Returning effective default (which is likely an empty string).")
                return effective_default # This will be "" for KEY_LAST_PROJECT_DIRECTORY if conversion fails
    # --- END MODIFICATION ---

    if isinstance(stored_value, expected_type):
        return stored_value
    else:
        logger.warning(f"Type mismatch for key '{key}'. Expected {expected_type}, got {type(stored_value)}. Value: '{stored_value}'. Returning effective default.")
        return effective_default


def set_setting(key: str, value: Any) -> None:
    settings = _get_settings()
    value_to_store = value

    if isinstance(value, QtGui.QColor):
        value_to_store = value.name() 
    elif isinstance(value, bool):
        value_to_store = "true" if value else "false"
    # --- BEGIN MODIFICATION: Ensure strings are stored as strings ---
    elif isinstance(value, str): # Explicitly handle strings
        pass # value_to_store is already correct
    # --- END MODIFICATION ---

    logger.debug(f"Saving setting '{key}' with value: {value_to_store} (Original type: {type(value)})")
    settings.setValue(key, value_to_store)
    settings.sync() 
    logger.debug(f"QSettings status after sync for '{key}': {settings.status().name}")
    if settings.status() != QtCore.QSettings.Status.NoError:
        logger.error(f"Error saving setting '{key}': {settings.status().name}")