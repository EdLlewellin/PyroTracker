# kymograph_dialog.py
"""
Dialog window for displaying a generated kymograph using PyQtGraph.
"""
import logging
import sys
from typing import TYPE_CHECKING, Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import cv2 # For BGR to RGB conversion

# Attempt to import pyqtgraph
try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    pg = None # Placeholder
    PYQTGRAPH_AVAILABLE = False
    logging.warning("PyQtGraph not found. Kymograph display will be basic or unavailable.")

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

class KymographDisplayDialog(QtWidgets.QDialog):
    """
    A dialog to display the generated kymograph image using PyQtGraph.ImageView.
    """

    def __init__(self,
                 kymograph_data: np.ndarray, # Shape: (time_frames, distance_pixels, [channels])
                 line_id: int,
                 video_filename: str,
                 # --- Parameters for axis calibration and labeling ---
                 total_line_distance: float, # Actual length of the line in chosen units
                 distance_units: str,        # e.g., "px" or "m"
                 total_video_duration_seconds: float, # For time axis calibration
                 # total_frames: int, # Also useful for time axis if preferring frame numbers
                 parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        
        self.kymograph_data_raw = kymograph_data # Store raw (time, distance, [ch])
        self.line_id = line_id
        self.video_filename = video_filename
        
        self.total_line_distance = total_line_distance
        self.distance_units = distance_units
        self.total_video_duration_seconds = total_video_duration_seconds
        # self.total_frames = total_frames

        self.setWindowTitle(f"Kymograph - Line {self.line_id} ({self.video_filename})")
        
        if parent:
            parent_size = parent.size()
            initial_width = int(parent_size.width() * 0.7)
            initial_height = int(parent_size.height() * 0.6)
            self.resize(initial_width, initial_height)
        else:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                self.resize(int(screen_geometry.width() * 0.6), int(screen_geometry.height() * 0.6))
            else:
                self.resize(800, 600)

        self.setMinimumSize(500, 400)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        self._setup_ui()
        if PYQTGRAPH_AVAILABLE:
            self._display_kymograph_with_pyqtgraph()
        else:
            self._show_pyqtgraph_unavailable_message()
        
        logger.debug(f"KymographDisplayDialog initialized for Line ID {self.line_id}.")

    def _setup_ui(self) -> None:
        """Creates and arranges the UI elements within the dialog."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        if PYQTGRAPH_AVAILABLE and pg is not None:
            # --- Kymograph Display Area using PyQtGraph ImageView ---
            # ImageView itself is a QWidget
            self.imageView = pg.ImageView(self) # levelMode='mono' could be useful for single channel float data
            # To allow the kymograph image to stretch to the view's aspect ratio:
            self.imageView.view.setAspectLocked(lock=False)
            
            main_layout.addWidget(self.imageView, 1) # Give it stretch factor 1
        else:
            # Fallback if PyQtGraph is not available
            self.fallback_label = QtWidgets.QLabel(
                "PyQtGraph library is not installed.\n"
                "Kymograph display requires PyQtGraph for advanced features.\n"
                "Please install it (e.g., 'pip install pyqtgraph') and restart."
            )
            self.fallback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.fallback_label.setWordWrap(True)
            main_layout.addWidget(self.fallback_label, 1)

        # --- Dialog Buttons ---
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        # For QDialog, connecting QDialogButtonBox.accepted/rejected to self.accept/self.reject is typical
        # For a "Close" button, it usually triggers reject.
        button_box.rejected.connect(self.reject) 
        main_layout.addWidget(button_box)

    def _show_pyqtgraph_unavailable_message(self):
        logger.error("PyQtGraph is not available for KymographDisplayDialog.")
        # The fallback label is already added in _setup_ui

    def _display_kymograph_with_pyqtgraph(self) -> None:
        """
        Processes the NumPy kymograph data and displays it using PyQtGraph.ImageView,
        with calibrated axes.
        """
        if not PYQTGRAPH_AVAILABLE or self.imageView is None:
            logger.error("Attempted to display with PyQtGraph, but it's not available or ImageView not initialized.")
            return

        if self.kymograph_data_raw is None:
            logger.error("No kymograph data to display.")
            self.imageView.clear()
            if pg and hasattr(self.imageView, 'addItem'): # Check if addItem is available
                try:
                    # ImageView's addItem adds to its internal ViewBox/scene
                    self.imageView.addItem(pg.TextItem("Error: No kymograph data.", color='r'))
                except Exception as e_text:
                    logger.error(f"Could not add error text to ImageView: {e_text}")
            return

        data_raw = self.kymograph_data_raw
        
        if data_raw.ndim == 2: # Grayscale
            data_for_pg_image = data_raw.T 
        elif data_raw.ndim == 3: # Color
            data_for_pg_image = data_raw.transpose(1, 0, 2)
        else:
            logger.error(f"Unsupported kymograph data dimension: {data_raw.ndim}")
            self.imageView.clear()
            if pg and hasattr(self.imageView, 'addItem'):
                try:
                    self.imageView.addItem(pg.TextItem(f"Error: Unsupported data dim {data_raw.ndim}.", color='r'))
                except Exception as e_text:
                    logger.error(f"Could not add error text to ImageView: {e_text}")
            return

        num_distance_pixels = data_for_pg_image.shape[0]
        num_time_frames = data_for_pg_image.shape[1]

        time_start_val = 0.0
        time_scale_val = self.total_video_duration_seconds / num_time_frames if num_time_frames > 0 else 1.0

        distance_start_val = 0.0
        distance_scale_val = self.total_line_distance / num_distance_pixels if num_distance_pixels > 0 else 1.0

        final_image_data_for_pg = data_for_pg_image
        if data_for_pg_image.ndim == 3 and data_for_pg_image.shape[2] == 3:
            if data_for_pg_image.dtype != np.uint8:
                if np.max(data_for_pg_image) > np.min(data_for_pg_image):
                    img_norm = 255 * (data_for_pg_image - np.min(data_for_pg_image)) / (np.max(data_for_pg_image) - np.min(data_for_pg_image))
                else:
                    img_norm = np.zeros_like(data_for_pg_image)
                img_u8 = img_norm.astype(np.uint8)
            else:
                img_u8 = data_for_pg_image
            final_image_data_for_pg = cv2.cvtColor(img_u8, cv2.COLOR_BGR2RGB)
        elif data_for_pg_image.ndim == 2:
             if data_for_pg_image.dtype != np.uint8:
                if np.max(data_for_pg_image) > np.min(data_for_pg_image):
                    img_norm = 255 * (data_for_pg_image - np.min(data_for_pg_image)) / (np.max(data_for_pg_image) - np.min(data_for_pg_image))
                else:
                    img_norm = np.zeros_like(data_for_pg_image)
                final_image_data_for_pg = img_norm.astype(np.uint8)
             else:
                final_image_data_for_pg = data_for_pg_image
        
        self.imageView.setImage(
            final_image_data_for_pg,
            # For ImageView, pos and scale are applied to the ImageItem it creates.
            # These define how the image data maps to the scene coordinates handled by the ViewBox.
            # The axes will then reflect these scene coordinates.
            # To make the axes directly show time and distance values, ensure your scale
            # here translates pixel indices to these real-world values.
            # Note: PyQtGraph ImageView by default orients the image with (0,0) at top-left.
            # If your 'final_image_data_for_pg' has (distance, time), then 'distance' is rows (y)
            # and 'time' is columns (x).
            # pos=[x0, y0] refers to the coordinate of the corner pixel (0,0) of the image.
            # scale=[sx, sy] refers to the size of each pixel in x and y.
            pos=[time_start_val, distance_start_val],       # Time for X-axis, Distance for Y-axis
            scale=[time_scale_val, distance_scale_val]    # s/px for X, dist_unit/px for Y
        )

        # --- Set Axis Labels ---
        # Access the PlotItem from ImageView using .plotItem or .getPlotItem() if available
        # For newer PyQtGraph versions, plotItem is a direct attribute.
        # For older ones, getPlotItem() was used. Current standard is .plotItem.
        # If self.imageView is indeed a pg.ImageView, it has a 'plotItem' attribute.
        if hasattr(self.imageView, 'plotItem') and self.imageView.plotItem is not None:
            plot_item = self.imageView.plotItem
        elif hasattr(self.imageView, 'getPlotItem'): # Fallback for potentially older API style
             plot_item = self.imageView.getPlotItem()
        else:
            logger.error("Could not get PlotItem from ImageView to set labels.")
            return

        plot_item.setLabel('bottom', "Time", units="s")
        plot_item.setLabel('left', "Distance from Line Start (P2)", units=self.distance_units)
        
        # Ensure the aspect lock is off AFTER setting the image if setImage resets it.
        # This is often done once in _setup_ui, but doesn't hurt to re-affirm if needed.
        if hasattr(self.imageView, 'view') and self.imageView.view is not None :
             self.imageView.view.setAspectLocked(lock=False)


        logger.info(f"Kymograph displayed with PyQtGraph. Time axis scale: {time_scale_val:.3e} s/px, Distance axis scale: {distance_scale_val:.3e} {self.distance_units}/px.")

if __name__ == '__main__':
    # Ensure QApplication instance exists for QGuiApplication.primaryScreen()
    app = QtWidgets.QApplication.instance() 
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    if not PYQTGRAPH_AVAILABLE:
        print("PyQtGraph is not installed. Please install it to run this test/dialog.")
        sys.exit(1)

    # Dummy data for testing
    dummy_time_frames = 150
    dummy_distance_pixels = 200
    
    # KymographHandler produces (time, distance, [channels])
    # Color example (BGR)
    dummy_kymo_color_raw = np.zeros((dummy_time_frames, dummy_distance_pixels, 3), dtype=np.uint8)
    for t_idx in range(dummy_time_frames):
        for d_idx in range(dummy_distance_pixels):
            dummy_kymo_color_raw[t_idx, d_idx, 0] = (t_idx * 255 // dummy_time_frames) % 256 # Blue gradient over time
            dummy_kymo_color_raw[t_idx, d_idx, 1] = (d_idx * 255 // dummy_distance_pixels) % 256 # Green gradient over distance
            if (t_idx + d_idx) % 50 < 5 : # Some diagonal features
                 dummy_kymo_color_raw[t_idx, d_idx, 2] = 255 # Red

    # Grayscale example
    # dummy_kymo_gray_raw = np.zeros((dummy_time_frames, dummy_distance_pixels), dtype=np.uint8)
    # for t_idx in range(dummy_time_frames):
    #     for d_idx in range(dummy_distance_pixels):
    #         dummy_kymo_gray_raw[t_idx, d_idx] = (t_idx + d_idx) % 256


    dialog = KymographDisplayDialog(
        kymograph_data=dummy_kymo_color_raw, # or dummy_kymo_gray_raw
        line_id=1,
        video_filename="test_video.mp4",
        total_line_distance=10.5, # Example total distance in meters
        distance_units="m",
        total_video_duration_seconds=float(dummy_time_frames / 30.0), # Assuming 30 FPS
        # total_frames=dummy_time_frames,
        parent=None
    )
    dialog.show()
    sys.exit(app.exec())