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
# Using a 'group/key' format for organization within QSettings
VISUALS_GROUP = "visuals"
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
# Add other settings keys here using the same pattern if needed

# --- Define Default Values ---
# Provides fallback values if a setting isn't found or is invalid.
# Note: Some defaults reference config.py, creating a dependency.
# Alternatively, copy the literal values from config.py here for full independence.
DEFAULT_SETTINGS = {
    KEY_ACTIVE_MARKER_COLOR: QtGui.QColor("yellow"),
    KEY_ACTIVE_LINE_COLOR: QtGui.QColor("yellow"),
    KEY_ACTIVE_CURRENT_MARKER_COLOR: QtGui.QColor("red"),
    KEY_INACTIVE_MARKER_COLOR: QtGui.QColor("blue"),
    KEY_INACTIVE_LINE_COLOR: QtGui.QColor("blue"),
    KEY_INACTIVE_CURRENT_MARKER_COLOR: QtGui.QColor("cyan"),
    KEY_MARKER_SIZE: config.DEFAULT_MARKER_SIZE, # Default: 5.0 (from config)
    KEY_LINE_WIDTH: config.DEFAULT_LINE_WIDTH,   # Default: 1.0 (from config)
    KEY_ORIGIN_MARKER_COLOR: QtGui.QColor(config.DEFAULT_ORIGIN_MARKER_COLOR_STR), # Create QColor from config string
    KEY_ORIGIN_MARKER_SIZE: config.DEFAULT_ORIGIN_MARKER_SIZE # Default from config
}

# Singleton instance of QSettings
_settings_instance: Optional[QtCore.QSettings] = None

def _get_settings() -> QtCore.QSettings:
    """
    Initializes and returns the singleton QSettings instance.
    Ensures organization and application names are set for QSettings.
    """
    global _settings_instance
    if _settings_instance is None:
        # Set org/app names if not already set (needed by QSettings)
        app = QtCore.QCoreApplication.instance()
        if app: # Check if QCoreApplication exists
             if not QtCore.QCoreApplication.organizationName():
                 QtCore.QCoreApplication.setOrganizationName(config.APP_ORGANIZATION)
             if not QtCore.QCoreApplication.applicationName():
                 QtCore.QCoreApplication.setApplicationName(config.APP_NAME)
        else:
             # This case should ideally not happen in a running Qt app,
             # but useful for testing or if run standalone.
             logger.warning("QCoreApplication instance not found. Setting fallback names for QSettings.")
             # Set directly if no app instance (less ideal)
             QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat) # Or another preferred format
             QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppConfigLocation))


        _settings_instance = QtCore.QSettings(
            config.APP_ORGANIZATION, config.APP_NAME
        )
        logger.info(f"QSettings initialized. Path: {_settings_instance.fileName()}")
    return _settings_instance

def get_setting(key: str, default_override: Optional[Any] = None) -> Any:
    """
    Retrieves a setting value for the given key, attempting type conversion
    based on the default value's type.

    Args:
        key: The unique key for the setting (e.g., "visuals/markerSize").
        default_override: If provided, this value is used as the default instead
                          of the one in DEFAULT_SETTINGS.

    Returns:
        The retrieved setting value, converted to the expected type if possible,
        or the appropriate default value if the setting is not found or
        conversion fails.
    """
    settings = _get_settings()

    # Determine the default value to use
    if default_override is not None:
        default_value = default_override
    elif key in DEFAULT_SETTINGS:
        default_value = DEFAULT_SETTINGS[key]
    else:
        default_value = None # No default defined for this key

    # Retrieve the raw value from QSettings
    # Pass the determined default_value to QSettings.value() as its fallback
    value = settings.value(key, defaultValue=default_value)

    # --- Type Conversion Logic ---
    # Attempt conversion only if we have a defined default value to infer the type from
    # and the loaded value isn't already the correct type or None.
    if default_value is not None and value is not None:
        expected_type = type(default_value)

        # 1. Handle QColor conversion (stored as string name)
        if expected_type is QtGui.QColor and not isinstance(value, QtGui.QColor):
            try:
                # QColor() constructor can handle color names (e.g., '#ffffff', 'red')
                loaded_color = QtGui.QColor(value)
                if loaded_color.isValid():
                    value = loaded_color
                else:
                    logger.warning(f"Invalid QColor value '{value}' loaded for key '{key}'. Using default: {default_value.name()}")
                    value = default_value # Fallback to default
            except Exception as e: # Catch potential errors during QColor creation
                logger.warning(f"Error converting loaded value '{value}' to QColor for key '{key}': {e}. Using default: {default_value.name()}")
                value = default_value # Fallback to default

        # 2. Handle Float conversion (stored possibly as string or int)
        elif expected_type is float and not isinstance(value, float):
            try:
                value = float(value) # Attempt conversion
            except (ValueError, TypeError):
                logger.warning(f"Invalid float value '{value}' loaded for key '{key}'. Using default: {default_value}")
                value = default_value # Fallback to default

        # 3. Handle Int conversion (example, currently unused)
        # elif expected_type is int and not isinstance(value, int):
        #     try:
        #         value = int(value)
        #     except (ValueError, TypeError):
        #         logger.warning(f"Invalid int value '{value}' loaded for key '{key}'. Using default: {default_value}")
        #         value = default_value

        # Add more type handlers (e.g., bool) here if needed.
        # For bool, consider checking for 'true'/'false' strings if stored that way.

    elif value is None and default_value is not None:
        # If settings.value() returned None but we have a default, use the default.
        # This happens if the key didn't exist in the settings file.
        value = default_value

    elif default_value is None and value is not None:
        # If we loaded a value but have no default defined, we can't perform
        # type conversion reliably. Log a warning.
        logger.warning(f"Setting '{key}' has value '{value}' but no default defined in DEFAULT_SETTINGS. Returning raw value.")

    # Debug log can be useful during development
    # logger.debug(f"Retrieved setting '{key}': {value} (Type: {type(value)})")
    return value

def set_setting(key: str, value: Any) -> None:
    """
    Saves a setting value for the given key using QSettings.

    Args:
        key: The unique key for the setting.
        value: The value to save. QSettings handles basic types, others
               might need conversion (e.g., QColor is often saved as name string).
    """
    settings = _get_settings()
    logger.debug(f"Setting setting '{key}' to value: {value} (Type: {type(value)})")
    settings.setValue(key, value)
    # Explicit sync is usually not needed; QSettings handles saving.
    # settings.sync()

# --- Optional Signal for Settings Changes ---
# Useful if parts of the UI need to react immediately to changes from Preferences.
# class SettingsSignalEmitter(QtCore.QObject):
#     settingChanged = QtCore.Signal(str) # Emits the key that changed
#
# settings_emitter = SettingsSignalEmitter()
#
# # Modified set_setting to emit the signal:
# def set_setting_with_signal(key: str, value: Any) -> None:
#     settings = _get_settings()
#     logger.debug(f"Setting setting '{key}' to: {value}")
#     settings.setValue(key, value)
#     # settings.sync() # Optional explicit save
#     settings_emitter.settingChanged.emit(key) # Notify listeners
# --- End Optional Signal ---