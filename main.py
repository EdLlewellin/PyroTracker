# main.py
"""
Entry point script for the PyroTracker application.

Initializes logging, sets up the QApplication instance (handling High DPI),
instantiates and shows the MainWindow, and starts the Qt event loop.
"""

import sys
import logging
import os
# Import necessary types from typing module
from typing import Optional

from PySide6 import QtWidgets, QtCore
import resources_rc

# Import application components AFTER basic logging is configured
import config
from main_window import MainWindow
import logging_config_utils
from logging_config_utils import shutdown_logging

# --- Basic Logging Setup ---
# Configure logging level and format
# This initial setup is for very early messages.
# The full configuration will be applied by setup_logging_from_settings().
logging.basicConfig(
    level=logging.DEBUG, # Keep DEBUG for initial startup, setup_logging_from_settings will override
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s', # Simplified format for initial
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)] # Ensure it goes to console [cite: 17]
)
# Get the logger for this module
logger = logging.getLogger(__name__) # Use module-specific logger for consistency
logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION} (initial log setup)")
# --------------------------

# --- Determine base directory for resource loading ---
# This logic correctly determines the base directory whether running from source
# or as a PyInstaller bundle.
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running in a PyInstaller bundle
    basedir = sys._MEIPASS
    logger.info(f"Running in PyInstaller bundle. Basedir: {basedir}")
else:
    # Running as a normal Python script
    basedir = os.path.dirname(os.path.abspath(__file__))
    logger.info(f"Running from source. Basedir: {basedir}")
# --- END Determine base directory ---


# Standard Python entry point check
if __name__ == "__main__":

    # Type hint for the application instance
    app: Optional[QtWidgets.QApplication] = None

    # Create or retrieve the QApplication instance
    try:
        app = QtWidgets.QApplication.instance()
        if app is None:
            logger.debug("No existing QApplication found, creating a new one.")
            # --- High DPI Handling ---
            try:
                QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
                    QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
                logger.debug("High DPI attributes set (PySide6 >= 6.4 method).")
            except AttributeError:
                logger.warning("Using fallback High DPI settings (older PySide6?).")
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
            # --- End High DPI Handling ---

            app = QtWidgets.QApplication(sys.argv)
            logger.info("QApplication instance created.")
        else:
            logger.info("Reusing existing QApplication instance.")

        app.setApplicationName(config.APP_NAME)
        app.setOrganizationName(config.APP_ORGANIZATION)
        app.setApplicationVersion(config.APP_VERSION)
        logger.debug(f"Application details set: Name={config.APP_NAME}, Org={config.APP_ORGANIZATION}, Version={config.APP_VERSION}")

        # --- BEGIN MODIFICATION: Apply full logging configuration ---
        # Call setup_logging_from_settings() after QApplication is initialized
        # and QSettings can be reliably accessed by settings_manager.
        logging_config_utils.setup_logging_from_settings() # [cite: 18]
        logger.info(f"{config.APP_NAME} v{config.APP_VERSION} started with full logging configuration.") # Re-log start with full config
        # --- END MODIFICATION ---

        # --- Load External Stylesheet ---
        qss_file_path = ":/collapsible_panel.qss" # NEW WAY
        
        try:
            # Use QFile to read from resources
            qss_file = QtCore.QFile(qss_file_path)
            if qss_file.open(QtCore.QIODevice.OpenModeFlag.ReadOnly | QtCore.QIODevice.OpenModeFlag.Text):
                stylesheet_content = QtCore.QTextStream(qss_file).readAll()
                qss_file.close()
                app.setStyleSheet(stylesheet_content)
                logger.info(f"Loaded stylesheet from resource: {qss_file_path}")
            else:
                logger.warning(f"Could not open stylesheet from resource: {qss_file_path}. Error: {qss_file.errorString()}")
        except FileNotFoundError:
            logger.warning(f"Stylesheet file not found: {qss_file_path}. Using default styles for panels.")
        except Exception as e:
            logger.error(f"Error loading stylesheet {qss_file_path}: {e}")

        logger.debug("Instantiating MainWindow...")
        window = MainWindow()
        logger.debug("MainWindow instantiated.")
        window.show()
        logger.info("MainWindow shown.")

        logger.info("Starting Qt event loop...")
        exit_code = app.exec()
        logger.info(f"Qt event loop finished with exit code {exit_code}.")
        sys.exit(exit_code)

    except Exception as e:
        logger.critical(f"An unhandled exception occurred during startup: {e}", exc_info=True)
        if app:
            error_box = QtWidgets.QMessageBox()
            error_box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
            error_box.setWindowTitle("Critical Error")
            error_box.setText(f"A critical error occurred:\n{e}\n\nPlease check the logs.")
            error_box.exec()
    finally:
        logger.info("Application is preparing to exit. Shutting down logging.")
        shutdown_logging()
        sys.exit(1)