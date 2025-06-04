# logging_config_utils.py
"""
Utilities for configuring and managing logging for the PyroTracker application.

This module provides functions to determine default log paths, set up
the Python logging system based on saved application settings, and a dialog
class for users to configure these logging settings.
"""
import logging
import os
import sys
from typing import Optional, Any, Dict

from PySide6 import QtCore, QtGui, QtWidgets

import settings_manager
import config

# Module-level reference to the custom file handler, to allow removing it later.
_custom_file_handler: Optional[logging.FileHandler] = None

# Standard logging levels mapping
LOGGING_LEVELS_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
LOGGING_LEVELS_MAP_REVERSE = {v: k for k, v in LOGGING_LEVELS_MAP.items()}

def get_default_log_path() -> str:
    """
    Determines and returns the default absolute path for the log file. [cite: 7]

    The log file (e.g., PyroTracker.log) will be placed in the same directory
    as the executable if bundled, or next to the main script if run from source.
    
    Returns:
        str: The absolute default path for the log file.
    """
    log_filename = f"{config.APP_NAME}.log"
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in a PyInstaller bundle
        application_path = os.path.dirname(sys.executable)
    else:
        # Running as a normal Python script
        application_path = os.path.abspath(os.path.dirname(sys.argv[0]))
    default_path = os.path.join(application_path, log_filename)
    logging.debug(f"Default log path determined: {default_path}")
    return default_path

def setup_logging_from_settings() -> None:
    """
    Configures the Python root logger based on settings from settings_manager.py. [cite: 8]

    This includes setting the overall logging level, managing a file handler
    (if enabled), and ensuring a console handler is present and its level is
    also set according to settings. [cite: 9, 11, 12, 74]
    If file logging is enabled, it determines the actual log file path (using
    the saved path or get_default_log_path() if the saved path is empty [cite: 13]),
    creates a new logging.FileHandler in overwrite mode ('w')[cite: 14], adds it to
    the root logger[cite: 15], and saves the determined path back to settings_manager
    if the original setting was empty[cite: 15].
    It also manages a module-level reference to any custom FileHandler to ensure
    it can be removed/closed before creating a new one. [cite: 10]
    """
    global _custom_file_handler
    logger_instance = logging.getLogger()

    logging_enabled = settings_manager.get_setting(settings_manager.KEY_LOGGING_ENABLED)
    log_file_path_setting = settings_manager.get_setting(settings_manager.KEY_LOGGING_FILE_PATH)
    log_level_str = settings_manager.get_setting(settings_manager.KEY_LOGGING_LEVEL)
    log_level = LOGGING_LEVELS_MAP.get(log_level_str.upper(), logging.INFO)

    logger_instance.setLevel(log_level)

    console_handler_exists = False
    for handler in logger_instance.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(log_level)
            console_handler_exists = True
            logging.debug(f"Updated existing StreamHandler level to {log_level_str}.")
            break
    if not console_handler_exists:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(formatter)
        logger_instance.addHandler(console_handler)
        logging.debug(f"Added new StreamHandler with level {log_level_str}.")

    if _custom_file_handler is not None:
        logging.debug(f"Removing existing custom file handler for: {_custom_file_handler.baseFilename}")
        logger_instance.removeHandler(_custom_file_handler)
        _custom_file_handler.close()
        _custom_file_handler = None

    if logging_enabled:
        actual_log_file_path = log_file_path_setting
        if not actual_log_file_path or not os.path.isabs(actual_log_file_path):
            actual_log_file_path = get_default_log_path()
            if not log_file_path_setting:
                settings_manager.set_setting(settings_manager.KEY_LOGGING_FILE_PATH, actual_log_file_path)
                logging.debug(f"Saved determined default log path to settings: {actual_log_file_path}")
        try:
            log_dir = os.path.dirname(actual_log_file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
                logging.info(f"Created log directory: {log_dir}")

            file_handler = logging.FileHandler(actual_log_file_path, mode='w', encoding='utf-8')
            file_handler.setLevel(log_level)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            file_handler.setFormatter(formatter)
            logger_instance.addHandler(file_handler)
            _custom_file_handler = file_handler
            logging.info(f"File logging enabled to '{actual_log_file_path}' with level {log_level_str}.") # [cite: 16]
        except Exception as e:
            logging.error(f"Failed to set up file logging to '{actual_log_file_path}': {e}", exc_info=True)
    else:
        logging.info("File logging is disabled in settings.")

def shutdown_logging() -> None:
    """
    Safely shuts down the custom file logger, if one was configured.
    This should be called before application exit to ensure log files are closed.
    """
    global _custom_file_handler
    logger_instance = logging.getLogger() # Get the root logger

    if _custom_file_handler is not None:
        logging.info(f"Shutting down custom file handler for: {_custom_file_handler.baseFilename}")
        try:
            logger_instance.removeHandler(_custom_file_handler)
            _custom_file_handler.close()
        except Exception as e:
            # Use a basic print here as logging might be shutting down
            print(f"ERROR: Exception during logging shutdown: {e}", file=sys.stderr)
        finally:
            _custom_file_handler = None
    else:
        logging.info("No custom file handler to shut down.")

class LoggingSettingsDialog(QtWidgets.QDialog):
    """
    Dialog for users to configure application logging settings, including
    enabling/disabling file logging, setting the log file path, and
    choosing the logging level.
    """
    dialog_settings_cache: Dict[str, Any] # Stores settings loaded into dialog for change detection [cite: 42]

    def _level_str_to_combobox_index(self, level_str: str) -> int: # [cite: 36]
        """Converts a logging level string (e.g., "INFO") to its corresponding QComboBox index."""
        try:
            return list(LOGGING_LEVELS_MAP.keys()).index(level_str.upper())
        except ValueError:
            logging.warning(f"Unknown logging level string '{level_str}'. Defaulting to INFO index.")
            return list(LOGGING_LEVELS_MAP.keys()).index("INFO")

    def _combobox_index_to_level_str(self, index: int) -> str: # [cite: 36]
        """Converts a QComboBox index to its corresponding logging level string."""
        try:
            return list(LOGGING_LEVELS_MAP.keys())[index]
        except IndexError:
            logging.warning(f"Invalid QComboBox index '{index}'. Defaulting to INFO string.")
            return "INFO"

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        """
        Initializes the LoggingSettingsDialog. [cite: 22]

        Args:
            parent: The parent widget, if any.
        """
        super().__init__(parent)
        self.setWindowTitle("Logging Settings") # [cite: 22]
        self.setMinimumSize(500, 350) # [cite: 22]
        self.setModal(True) # [cite: 22]
        self.dialog_settings_cache = {} # [cite: 42]
        self._setup_ui()
        self._connect_signals()
        self._load_settings_into_dialog() # [cite: 37]

    def _setup_ui(self) -> None:
        """Creates and arranges the UI elements within the dialog."""
        main_layout = QtWidgets.QVBoxLayout(self)

        self.enable_file_logging_checkbox = QtWidgets.QCheckBox("Enable logging to file") # [cite: 23]
        main_layout.addWidget(self.enable_file_logging_checkbox)

        self.file_settings_groupbox = QtWidgets.QGroupBox("File Settings") # [cite: 24]
        file_settings_layout = QtWidgets.QVBoxLayout(self.file_settings_groupbox)

        path_layout = QtWidgets.QHBoxLayout()
        self.current_log_path_display = QtWidgets.QLineEdit() # [cite: 24]
        self.current_log_path_display.setReadOnly(True)
        self.current_log_path_display.setToolTip("Current path for the log file.")
        path_layout.addWidget(self.current_log_path_display)
        self.change_location_button = QtWidgets.QPushButton("Change Location...") # [cite: 25]
        self.change_location_button.setToolTip("Select a new location and filename for the log file.")
        path_layout.addWidget(self.change_location_button)
        file_settings_layout.addLayout(path_layout)

        action_buttons_layout = QtWidgets.QHBoxLayout()
        self.open_log_folder_button = QtWidgets.QPushButton("Open Log Folder") # [cite: 25]
        self.open_log_folder_button.setToolTip("Open the directory containing the log file.")
        action_buttons_layout.addWidget(self.open_log_folder_button)
        self.reset_to_default_button = QtWidgets.QPushButton("Reset to Default") # [cite: 25]
        self.reset_to_default_button.setToolTip("Reset the log file path to its default location.")
        action_buttons_layout.addWidget(self.reset_to_default_button)
        action_buttons_layout.addStretch()
        file_settings_layout.addLayout(action_buttons_layout)
        main_layout.addWidget(self.file_settings_groupbox)

        logging_level_groupbox = QtWidgets.QGroupBox("Logging Level") # [cite: 25]
        logging_level_layout = QtWidgets.QHBoxLayout(logging_level_groupbox)
        logging_level_layout.addWidget(QtWidgets.QLabel("Set logging level for file and console:"))
        self.log_level_combobox = QtWidgets.QComboBox() # [cite: 25]
        self.log_level_combobox.addItems(LOGGING_LEVELS_MAP.keys())
        self.log_level_combobox.setToolTip("Select the minimum severity level for messages to be logged.")
        logging_level_layout.addWidget(self.log_level_combobox)
        logging_level_layout.addStretch()
        main_layout.addWidget(logging_level_groupbox)

        main_layout.addStretch()

        self.dialog_button_box = QtWidgets.QDialogButtonBox( # [cite: 26]
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Apply
        )
        main_layout.addWidget(self.dialog_button_box)

    def _connect_signals(self) -> None:
        """Connects UI element signals to their respective handler slots."""
        self.enable_file_logging_checkbox.toggled.connect(self.file_settings_groupbox.setEnabled) # [cite: 27]

        self.dialog_button_box.accepted.connect(self._handle_ok) # [cite: 28]
        self.dialog_button_box.rejected.connect(self.reject) # [cite: 28]
        apply_button = self.dialog_button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Apply)
        if apply_button:
            apply_button.clicked.connect(self._handle_apply) # [cite: 28]

        self.change_location_button.clicked.connect(self._browse_for_log_file) # [cite: 29]
        self.reset_to_default_button.clicked.connect(self._reset_log_path_to_default) # [cite: 29]
        self.open_log_folder_button.clicked.connect(self._open_log_folder) # [cite: 68]

    def _load_settings_into_dialog(self) -> None: # [cite: 37]
        """
        Loads current logging settings from settings_manager into the dialog's UI controls
        and caches these values for change detection. [cite: 38, 39, 40, 41, 42]
        """
        logging.debug("Loading settings into LoggingSettingsDialog.")
        enabled = settings_manager.get_setting(settings_manager.KEY_LOGGING_ENABLED)
        current_path = settings_manager.get_setting(settings_manager.KEY_LOGGING_FILE_PATH)
        level_str = settings_manager.get_setting(settings_manager.KEY_LOGGING_LEVEL)

        self.enable_file_logging_checkbox.setChecked(enabled)

        display_path = current_path
        if not current_path:
            display_path = get_default_log_path()
        self.current_log_path_display.setText(display_path)

        level_index = self._level_str_to_combobox_index(level_str)
        self.log_level_combobox.setCurrentIndex(level_index)

        self.open_log_folder_button.setEnabled(bool(display_path))

        self.dialog_settings_cache = {
            settings_manager.KEY_LOGGING_ENABLED: enabled,
            settings_manager.KEY_LOGGING_FILE_PATH: current_path,
            settings_manager.KEY_LOGGING_LEVEL: level_str,
        }
        logging.debug(f"Dialog settings cache populated: {self.dialog_settings_cache}")

    @QtCore.Slot()
    def _browse_for_log_file(self) -> None: # [cite: 47]
        """Opens a file dialog allowing the user to select a new log file path and name."""
        current_path = self.current_log_path_display.text()
        start_dir = os.path.dirname(current_path) if current_path and os.path.isdir(os.path.dirname(current_path)) else get_default_log_path()
        suggested_filename = os.path.basename(current_path) if current_path and not os.path.isdir(current_path) else f"{config.APP_NAME}.log"

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName( # [cite: 48]
            self, "Select Log File Location",
            os.path.join(os.path.dirname(start_dir), suggested_filename),
            "Log Files (*.log);;Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.current_log_path_display.setText(file_path) # [cite: 49]
            self.open_log_folder_button.setEnabled(True) # [cite: 49]
            logging.info(f"User selected new log file path: {file_path}")

    @QtCore.Slot()
    def _reset_log_path_to_default(self) -> None: # [cite: 50]
        """Resets the displayed log file path to the application's default location."""
        default_path = get_default_log_path() # [cite: 50]
        self.current_log_path_display.setText(default_path) # [cite: 51]
        self.open_log_folder_button.setEnabled(True) # [cite: 51]
        logging.info(f"Log path reset to default: {default_path}")

    def _apply_settings_from_dialog(self) -> bool: # [cite: 52]
        """
        Validates current dialog values, saves them if changed, and reconfigures logging.

        Reads settings from UI controls[cite: 53], validates them (e.g., path not empty if enabled,
        path accessible and not a directory [cite: 54, 55]), and shows a warning on
        validation failure[cite: 56]. If settings changed from cached values, they are
        saved via settings_manager[cite: 57], live logging is reconfigured by calling
        setup_logging_from_settings()[cite: 58], and the dialog UI/cache is refreshed[cite: 59, 60].

        Returns:
            bool: True if settings were successfully processed or no changes were made,
                  False if there was a validation error. [cite: 61]
        """
        new_enabled = self.enable_file_logging_checkbox.isChecked()
        new_path = self.current_log_path_display.text().strip()
        new_level_str = self._combobox_index_to_level_str(self.log_level_combobox.currentIndex())

        if new_enabled and not new_path:
            QtWidgets.QMessageBox.warning(self, "Validation Error", "Log file path cannot be empty when file logging is enabled.")
            return False

        if new_enabled and new_path:
            if os.path.isdir(new_path):
                QtWidgets.QMessageBox.warning(self, "Validation Error", f"The specified log path is a directory:\n{new_path}\nPlease provide a file name.")
                return False
            log_dir = os.path.dirname(new_path)
            if log_dir and not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except Exception as e:
                    QtWidgets.QMessageBox.warning(self, "Validation Error", f"Cannot create log directory:\n{log_dir}\nError: {e}")
                    return False
            if log_dir and not os.access(log_dir, os.W_OK):
                QtWidgets.QMessageBox.warning(self, "Validation Error", f"Log directory is not writable:\n{log_dir}")
                return False
        
        settings_changed = (
            new_enabled != self.dialog_settings_cache.get(settings_manager.KEY_LOGGING_ENABLED) or
            new_path != (self.dialog_settings_cache.get(settings_manager.KEY_LOGGING_FILE_PATH) or get_default_log_path() if not self.dialog_settings_cache.get(settings_manager.KEY_LOGGING_FILE_PATH) else self.dialog_settings_cache.get(settings_manager.KEY_LOGGING_FILE_PATH)) or
            new_level_str != self.dialog_settings_cache.get(settings_manager.KEY_LOGGING_LEVEL)
        )

        if settings_changed:
            logging.info("Logging settings changed by user. Applying...")
            settings_manager.set_setting(settings_manager.KEY_LOGGING_ENABLED, new_enabled)
            settings_manager.set_setting(settings_manager.KEY_LOGGING_FILE_PATH, new_path if new_enabled else "")
            settings_manager.set_setting(settings_manager.KEY_LOGGING_LEVEL, new_level_str)
            setup_logging_from_settings()
            self._load_settings_into_dialog() # Refreshes cache and UI from potentially resolved settings
            logging.info("Logging settings applied successfully.")
        else:
            logging.info("No changes detected in logging settings.")
        return True

    @QtCore.Slot()
    def _handle_ok(self) -> None: # [cite: 62]
        """Handles the OK button click: applies settings and closes the dialog if successful."""
        if self._apply_settings_from_dialog():
            self.accept()

    @QtCore.Slot()
    def _handle_apply(self) -> None: # [cite: 63]
        """Handles the Apply button click: applies settings and keeps the dialog open."""
        self._apply_settings_from_dialog()

    @QtCore.Slot()
    def _open_log_folder(self) -> None: # [cite: 68]
        """Opens the directory containing the currently displayed log file path in the system's file manager."""
        log_file_path = self.current_log_path_display.text().strip() # [cite: 68]

        if not log_file_path:
            QtWidgets.QMessageBox.information(self, "Open Log Folder", "Log file path is not set.") # [cite: 70]
            return

        log_folder_path = os.path.dirname(log_file_path) # [cite: 69]

        if not os.path.isdir(log_folder_path):
            is_default_path_root = False
            try:
                default_log_dir = os.path.dirname(get_default_log_path())
                if os.path.abspath(log_folder_path) == os.path.abspath(default_log_dir):
                    is_default_path_root = True
            except Exception:
                pass 

            if is_default_path_root:
                try:
                    os.makedirs(log_folder_path, exist_ok=True)
                    logging.info(f"Created missing log directory for opening: {log_folder_path}")
                except Exception as e:
                    QtWidgets.QMessageBox.warning(self, "Open Log Folder", f"Could not create or access log folder:\n{log_folder_path}\nError: {e}") # [cite: 70]
                    logging.error(f"Error creating/accessing log folder '{log_folder_path}': {e}")
                    return
            else: 
                QtWidgets.QMessageBox.warning(self, "Open Log Folder", f"Log folder does not exist:\n{log_folder_path}") # [cite: 70]
                logging.warning(f"Cannot open log folder, directory does not exist: {log_folder_path}")
                return
        
        url = QtCore.QUrl.fromLocalFile(log_folder_path) # [cite: 69]
        if not QtGui.QDesktopServices.openUrl(url): # [cite: 69]
            QtWidgets.QMessageBox.warning(self, "Open Log Folder", f"Could not open log folder:\n{log_folder_path}") # [cite: 70]
            logging.error(f"Failed to open log folder using QDesktopServices: {log_folder_path}")
        else:
            logging.info(f"Requested to open log folder: {log_folder_path}")

    def _open_log_folder_placeholder(self) -> None:
        # This method is no longer called as its connection was updated.
        # It can be safely removed.
        logging.debug("LoggingSettingsDialog: _open_log_folder_placeholder called (should be removed).")