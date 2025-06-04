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

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
    pg.setConfigOption('useOpenGL', False)
    pg.setConfigOption('enableExperimental', False)
except ImportError:
    pg = None 
    PYQTGRAPH_AVAILABLE = False
    logging.warning("PyQtGraph not found. Kymograph display will be basic or unavailable.")

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

class KymographDisplayDialog(QtWidgets.QDialog):
    """
    A dialog to display the generated kymograph image using PyQtGraph.ImageView.
    Visual X-axis will represent Time.
    Visual Y-axis will represent Distance.
    """

    def __init__(self,
                 kymograph_data: np.ndarray, # Expected raw shape: (time_frames, distance_pixels, [channels])
                 line_id: int,
                 video_filename: str,
                 total_line_distance: float, 
                 distance_units: str,        
                 total_video_duration_seconds: float,
                 total_frames_in_kymo: int, 
                 num_distance_points_in_kymo: int,
                 parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        
        self.kymograph_data_raw = kymograph_data 
        self.line_id = line_id
        self.video_filename = video_filename
        
        self.total_line_distance = total_line_distance
        self.distance_units = distance_units
        self.total_video_duration_seconds = total_video_duration_seconds
        self.num_time_frames_in_kymo = total_frames_in_kymo
        self.num_distance_points_in_kymo = num_distance_points_in_kymo

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
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        if PYQTGRAPH_AVAILABLE and pg is not None:
            # Create a PlotWidget first for more control over axes
            self.plotWidget = pg.PlotWidget(self)
            self.imageItem = pg.ImageItem()
            self.plotWidget.addItem(self.imageItem)
            
            # Ensure the image item stretches by controlling its ViewBox
            self.plotWidget.getViewBox().setAspectLocked(lock=False)
            
            # Hide default ImageView UI elements if we were using ImageView directly
            # For PlotWidget, these aren't present unless added.
            # If using ImageView:
            # self.imageView.ui.histogram.hide()
            # self.imageView.ui.roiBtn.hide()
            # self.imageView.ui.menuBtn.hide()

            main_layout.addWidget(self.plotWidget, 1)
        else:
            self.fallback_label = QtWidgets.QLabel(
                "PyQtGraph library is not installed. Kymograph display requires PyQtGraph.\n"
                "Please install it (e.g., 'pip install pyqtgraph') and restart."
            )
            self.fallback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.fallback_label.setWordWrap(True)
            main_layout.addWidget(self.fallback_label, 1)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _show_pyqtgraph_unavailable_message(self):
        logger.error("PyQtGraph is not available for KymographDisplayDialog.")


    def _display_kymograph_with_pyqtgraph(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not hasattr(self, 'plotWidget') or self.plotWidget is None:
            logger.error("PyQtGraph not available or PlotWidget not initialized.")
            return
        if self.kymograph_data_raw is None:
            logger.error("No kymograph data to display.");
            self.plotWidget.clear() # Clear any existing items like error messages
            if pg: self.plotWidget.addItem(pg.TextItem("Error: No kymograph data.", color='r'))
            return

        # Raw data from KymographHandler: (N_time, N_dist, [channels])
        # Hypothesis: ImageItem in PlotWidget context effectively maps axis 0 to X, axis 1 to Y.
        # Therefore, we do NOT transpose the raw data.
        data_raw = self.kymograph_data_raw
        image_for_display = data_raw # No transpose

        if image_for_display.ndim not in [2, 3]:
            logger.error(f"Unsupported kymograph data dimension: {image_for_display.ndim}"); self.plotWidget.clear(); return

        # With image_for_display as (N_time, N_dist, ...):
        # image_for_display.shape[0] is N_time (should map to X-axis width)
        # image_for_display.shape[1] is N_dist (should map to Y-axis height)
        img_width_time_pixels = image_for_display.shape[0] # N_time
        img_height_dist_pixels = image_for_display.shape[1] # N_dist

        # --- Axis Calibration ---
        # X-axis (Time)
        time_axis_start_val = 0.0
        # Time pixels are along the first dimension of image_for_display (original time dim)
        time_pixel_size_on_x_axis = self.total_video_duration_seconds / img_width_time_pixels if img_width_time_pixels > 0 else 1.0
        total_time_span_on_x_axis = img_width_time_pixels * time_pixel_size_on_x_axis

        # Y-axis (Distance)
        distance_axis_start_val = 0.0 # P2 (second click, start of kymo distance profile) is at 0 distance
        # Distance pixels are along the second dimension of image_for_display (original distance dim)
        distance_pixel_size_on_y_axis = self.total_line_distance / img_height_dist_pixels if img_height_dist_pixels > 0 else 1.0
        total_distance_span_on_y_axis = img_height_dist_pixels * distance_pixel_size_on_y_axis

        # Prepare image data for display (normalize type, BGR->RGB if color)
        final_image_data_pg = image_for_display
        if final_image_data_pg.ndim == 3 and final_image_data_pg.shape[2] == 3:
            img_to_convert = final_image_data_pg
            if final_image_data_pg.dtype != np.uint8:
                m, M = np.min(img_to_convert), np.max(img_to_convert)
                img_to_convert = ((255 * (img_to_convert - m) / (M - m)) if M > m else np.zeros_like(img_to_convert)).astype(np.uint8)
            final_image_data_pg = cv2.cvtColor(np.ascontiguousarray(img_to_convert), cv2.COLOR_BGR2RGB)
        elif final_image_data_pg.ndim == 2:
             img_to_convert = final_image_data_pg
             if final_image_data_pg.dtype != np.uint8:
                m, M = np.min(img_to_convert), np.max(img_to_convert)
                img_to_convert = ((255 * (img_to_convert - m) / (M - m)) if M > m else np.zeros_like(img_to_convert)).astype(np.uint8)
             final_image_data_pg = img_to_convert

        self.imageItem.setImage(final_image_data_pg, autoLevels=True)

        self.imageItem.setRect(QtCore.QRectF(
            time_axis_start_val,
            distance_axis_start_val,
            total_time_span_on_x_axis,
            total_distance_span_on_y_axis
        ))

        plot_item = self.plotWidget.getPlotItem()
        if plot_item:
            plot_item.getViewBox().invertY(True)
            plot_item.showAxes(True, showValues=True, size=20)
            plot_item.setLabel('bottom', "Time", units="s")
            plot_item.setLabel('left', "Distance from P2", units=self.distance_units)
            plot_item.getViewBox().setLimits(
                xMin=time_axis_start_val, xMax=time_axis_start_val + total_time_span_on_x_axis,
                yMin=distance_axis_start_val, yMax=distance_axis_start_val + total_distance_span_on_y_axis
            )
            plot_item.getViewBox().autoRange(padding=0.01)
            plot_item.getViewBox().setAspectLocked(lock=False)

        logger.info(f"Kymograph displayed. X-axis (Time) from {time_axis_start_val:.2f} to {time_axis_start_val+total_time_span_on_x_axis:.2f} s. "
                    f"Y-axis (Distance) from {distance_axis_start_val:.2f} to {distance_axis_start_val+total_distance_span_on_y_axis:.2f} {self.distance_units}.")

if __name__ == '__main__':
    app = QtWidgets.QApplication.instance() 
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    if not PYQTGRAPH_AVAILABLE:
        print("PyQtGraph is not installed. Please install it to run this test/dialog.")
        QtWidgets.QMessageBox.critical(None, "Missing Dependency", "PyQtGraph is required for kymograph display. Please install it.")
        sys.exit(1)

    dummy_time_frames = 150
    dummy_distance_pixels = 200
    
    dummy_kymo_color_raw = np.zeros((dummy_time_frames, dummy_distance_pixels, 3), dtype=np.uint8)
    for t_idx in range(dummy_time_frames):
        for d_idx in range(dummy_distance_pixels):
            dummy_kymo_color_raw[t_idx, d_idx, 0] = (t_idx * 100 // dummy_time_frames + d_idx * 155 // dummy_distance_pixels) % 256 
            dummy_kymo_color_raw[t_idx, d_idx, 1] = (d_idx * 255 // dummy_distance_pixels) % 256 
            if (t_idx + d_idx*2) % 70 < 8 :
                 dummy_kymo_color_raw[t_idx, d_idx, 2] = 255 

    dialog = KymographDisplayDialog(
        kymograph_data=dummy_kymo_color_raw,
        line_id=1,
        video_filename="test_video.mp4",
        total_line_distance=12.5, 
        distance_units="m",
        total_video_duration_seconds=float(dummy_time_frames / 25.0), 
        total_frames_in_kymo=dummy_time_frames,
        num_distance_points_in_kymo=dummy_distance_pixels,
        parent=None
    )
    dialog.show()
    sys.exit(app.exec())