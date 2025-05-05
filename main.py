# main.py
"""
Entry point script for the PyroTracker application.

Initializes logging, sets up the QApplication instance (handling High DPI),
instantiates and shows the MainWindow, and starts the Qt event loop.
"""

import sys
import logging
# Import necessary types from typing module
from typing import Optional

from PySide6 import QtWidgets, QtCore

# Import application components AFTER basic logging is configured
import config
from main_window import MainWindow

# --- Basic Logging Setup ---
# Configure logging level and format
# Consider changing level to logging.INFO for release distribution
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Get the logger for this module
logger = logging.getLogger(__name__) # Use module-specific logger for consistency
logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION}")
# --------------------------


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
            # Use newer methods if available (PySide6 >= 6.4)
            try:
                QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
                    QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
                logger.debug("High DPI attributes set (PySide6 >= 6.4 method).")
            except AttributeError:
                # Fallback for older versions
                logger.warning("Using fallback High DPI settings (older PySide6?).")
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
            # --- End High DPI Handling ---

            app = QtWidgets.QApplication(sys.argv)
            logger.info("QApplication instance created.")
        else:
            logger.info("Reusing existing QApplication instance.")

        # Set application details (using constants from config)
        # Required for QSettings and helps identify the app.
        app.setApplicationName(config.APP_NAME)
        app.setOrganizationName(config.APP_ORGANIZATION)
        app.setApplicationVersion(config.APP_VERSION)
        logger.debug(f"Application details set: Name={config.APP_NAME}, Org={config.APP_ORGANIZATION}, Version={config.APP_VERSION}")

        # Instantiate and show the main window
        logger.debug("Instantiating MainWindow...")
        window = MainWindow()
        logger.debug("MainWindow instantiated.")
        window.show()
        logger.info("MainWindow shown.")

        # Start the Qt event loop
        logger.info("Starting Qt event loop...")
        exit_code = app.exec()
        logger.info(f"Qt event loop finished with exit code {exit_code}.")
        sys.exit(exit_code)

    except Exception as e:
        # Log any critical errors during startup
        logger.critical(f"An unhandled exception occurred during startup: {e}", exc_info=True)
        # Optionally show a simple error message box if Qt was initialized enough
        if app:
            error_box = QtWidgets.QMessageBox()
            error_box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
            error_box.setWindowTitle("Critical Error")
            error_box.setText(f"A critical error occurred:\n{e}\n\nPlease check the logs.")
            error_box.exec()
        sys.exit(1) # Exit with a non-zero status code indicates error