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

# --- NEW KEYS for Feature Scale Line Ticks ---
KEY_FEATURE_SCALE_LINE_SHOW_TICKS = f"{SCALES_GROUP}/featureScaleLineShowTicks"
KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR = f"{SCALES_GROUP}/featureScaleLineTickLengthFactor"

# --- REVISED/NEW KEYS for Main Scale Bar Appearance ---
KEY_SCALE_BAR_RECT_HEIGHT = f"{SCALES_GROUP}/scaleBarRectHeight" # Renamed and clarified
KEY_SCALE_BAR_TEXT_FONT_SIZE = f"{SCALES_GROUP}/scaleBarTextFontSize"
# KEY_SCALE_BAR_BORDER_THICKNESS can be added if user wants to control border separately later.
# For now, it's a constant in scale_bar_widget.py or can be 1px by default.


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
    KEY_FEATURE_SCALE_LINE_WIDTH: 1.5,   # Float

    KEY_FEATURE_SCALE_LINE_SHOW_TICKS: True,
    KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR: 3.0,

    # --- REVISED Defaults for Main Scale Bar ---
    KEY_SCALE_BAR_RECT_HEIGHT: 4,       # Integer (height of the bar itself)
    KEY_SCALE_BAR_TEXT_FONT_SIZE: 10,   # Integer (point size)
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
             pass


        _settings_instance = QtCore.QSettings(config.APP_ORGANIZATION, config.APP_NAME)
        logger.info(f"QSettings initialized. Path: {_settings_instance.fileName()} Status: {_settings_instance.status().name}")
    return _settings_instance

def get_setting(key: str, default_override: Optional[Any] = None) -> Any:
    settings = _get_settings()
    default_value_from_map = DEFAULT_SETTINGS.get(key)

    effective_default = default_override if default_override is not None else default_value_from_map

    if effective_default is None and key not in DEFAULT_SETTINGS:
        logger.error(f"CRITICAL: No default defined anywhere for key '{key}'. This is a programming error.")
        return None

    stored_value = settings.value(key)

    if stored_value is None:
        logger.debug(f"Setting key '{key}' not found in QSettings or stored as None. Returning effective default: {effective_default}")
        return effective_default

    expected_type = type(effective_default)

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

    logger.debug(f"Saving setting '{key}' with value: {value_to_store} (Original type: {type(value)})")
    settings.setValue(key, value_to_store)
    settings.sync()
    logger.debug(f"QSettings status after sync for '{key}': {settings.status().name}")
    if settings.status() != QtCore.QSettings.Status.NoError:
        logger.error(f"Error saving setting '{key}': {settings.status().name}")