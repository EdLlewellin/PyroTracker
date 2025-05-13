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

SCALES_GROUP = "scales_visuals" # New group for scale-related visuals
KEY_SCALE_BAR_COLOR = f"{SCALES_GROUP}/scaleBarColor"
KEY_FEATURE_SCALE_LINE_COLOR = f"{SCALES_GROUP}/featureScaleLineColor"
KEY_FEATURE_SCALE_LINE_TEXT_COLOR = f"{SCALES_GROUP}/featureScaleLineTextColor"
KEY_FEATURE_SCALE_LINE_TEXT_SIZE = f"{SCALES_GROUP}/featureScaleLineTextSize"
KEY_FEATURE_SCALE_LINE_WIDTH = f"{SCALES_GROUP}/featureScaleLineWidth"


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
    KEY_FEATURE_SCALE_LINE_TEXT_SIZE: 18, # Integer
    KEY_FEATURE_SCALE_LINE_WIDTH: 1.5   # Float
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
             # This fallback might not be ideal for all platforms but aids headless/test scenarios
             # This os import was missing in the version I reviewed previously.
             import os # Ensure os is imported if not already at the top
             QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
             config_path = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppConfigLocation)
             if not os.path.exists(config_path): # This check is good
                 os.makedirs(config_path, exist_ok=True) # This is also good
             # The problem is likely here:
             # QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QStandardPaths.StandardLocation.AppConfigLocation, config.APP_NAME)
             # setPath is usually for defining where *custom formats* look for files,
             # not usually for setting the path for the standard INI format based on AppConfigLocation.
             # QSettings constructor usually handles this better with org/app names.
             # Let's simplify the fallback to be more standard if no QCoreApplication.instance() exists.
             # This fallback is tricky and often indicates a problem with how the app is launched
             # or if settings_manager is used too early.
             # For now, if app is None, we'll just let QSettings try to use its defaults,
             # which might write to a less predictable location on some systems without org/app name.
             # The proper fix is ensuring QCoreApplication.instance() exists and has org/app names.
             pass # Let the QSettings constructor handle it if app is None.


        _settings_instance = QtCore.QSettings(config.APP_ORGANIZATION, config.APP_NAME)
        logger.info(f"QSettings initialized. Path: {_settings_instance.fileName()} Status: {_settings_instance.status().name}")
    return _settings_instance

def get_setting(key: str, default_override: Optional[Any] = None) -> Any:
    settings = _get_settings()
    default_value_from_map = DEFAULT_SETTINGS.get(key)

    # Determine the ultimate default value to use if the setting isn't found or is invalid
    effective_default = default_override if default_override is not None else default_value_from_map

    if effective_default is None and key not in DEFAULT_SETTINGS:
        logger.error(f"CRITICAL: No default defined anywhere for key '{key}'. This is a programming error.")
        return None # Or raise an error

    stored_value = settings.value(key)

    if stored_value is None: # Key does not exist in settings file, or was stored as None.
        logger.debug(f"Setting key '{key}' not found in QSettings or stored as None. Returning effective default: {effective_default}")
        return effective_default # Return the well-typed default

    # Now, 'stored_value' is what was actually in QSettings.
    # 'effective_default' tells us the type we expect.
    expected_type = type(effective_default)

    if expected_type is QtGui.QColor:
        # QSettings stores colors as strings (e.g., "#RRGGBB" or name like "red")
        # if set_setting saved color.name().
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
            # QSettings might store numbers as strings or float, so robust conversion:
            return int(float(str(stored_value)))
        except (ValueError, TypeError):
            logger.warning(f"Cannot convert stored value '{stored_value}' to int for key '{key}'. Returning effective default.")
            return effective_default
    elif expected_type is bool:
        # QSettings can store bools as 'true'/'false' strings, or 0/1.
        if isinstance(stored_value, str):
            if stored_value.lower() == 'true': return True
            if stored_value.lower() == 'false': return False
        try:
            return bool(int(stored_value)) # Handles 0 or 1
        except (ValueError, TypeError):
             # Fallback to direct bool conversion, though this can be risky for arbitrary strings
            logger.warning(f"Attempting direct bool conversion for '{stored_value}' for key '{key}'.")
            try:
                return bool(stored_value) # This will be True for most non-empty strings
            except: # Should not happen for basic types QSettings stores
                logger.warning(f"Direct bool conversion failed for '{stored_value}' for key '{key}'. Returning effective default.")
                return effective_default
    
    # If no specific type conversion matched, but 'stored_value' is not None.
    # Check if its type already matches the expected type.
    if isinstance(stored_value, expected_type):
        return stored_value
    else:
        # This case means the stored type is unexpected and not handled by conversions above.
        logger.warning(f"Type mismatch for key '{key}'. Expected {expected_type}, got {type(stored_value)}. Value: '{stored_value}'. Returning effective default.")
        return effective_default

def set_setting(key: str, value: Any) -> None:
    settings = _get_settings()
    value_to_store = value
    if isinstance(value, QtGui.QColor):
        value_to_store = value.name() # Stores as #RRGGBB or color name

    logger.debug(f"Saving setting '{key}' with value: {value_to_store} (Original type: {type(value)})")
    settings.setValue(key, value_to_store)
    settings.sync() 
    logger.debug(f"QSettings status after sync for '{key}': {settings.status().name}")
    if settings.status() != QtCore.QSettings.Status.NoError:
        logger.error(f"Error saving setting '{key}': {settings.status().name}")