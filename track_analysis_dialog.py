# track_analysis_dialog.py
"""
Dialog window for displaying and analyzing y(t) data for a single track.
"""
import logging
import sys
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Tuple

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    pg = None
    PYQTGRAPH_AVAILABLE = False
    logging.warning("PyQtGraph not found. Track analysis plotting will be unavailable.")

if TYPE_CHECKING:
    from main_window import MainWindow # For type hinting parent_main_window
    # PointData might be useful if we pass raw points directly, but currently expect processed
    # from element_manager import PointData


logger = logging.getLogger(__name__)

class TrackAnalysisDialog(QtWidgets.QDialog):
    """
    Dialog for analyzing a single track's y(t) data and fitting a parabola.
    """

    def __init__(self,
                 track_element_copy: Dict[str, Any],
                 video_fps: float,
                 video_height: int,
                 parent_main_window: 'MainWindow'):
        super().__init__(parent_main_window) # Parent is the MainWindow
        self.setWindowTitle(f"Track Analysis - ID: {track_element_copy.get('id', 'N/A')}")
        self.setModal(True) # Start as modal for simplicity [cite: 15]

        self.track_element = track_element_copy # Store the copy [cite: 19]
        self.video_fps = video_fps
        self.video_height = video_height
        self.parent_main_window_ref = parent_main_window # Store reference if needed later

        self.plot_data_y_vs_t: List[Tuple[float, float]] = [] # To store (time_s, y_plot)

        # Initial size - can be adjusted
        self.setMinimumSize(700, 550)
        if parent_main_window:
             parent_size = parent_main_window.size()
             self.resize(int(parent_size.width() * 0.6), int(parent_size.height() * 0.7))
        else:
            self.resize(800, 600)


        self._setup_ui()

        if PYQTGRAPH_AVAILABLE:
            self._prepare_and_plot_data() # [cite: 22]
        else:
            self._show_pyqtgraph_unavailable_message()

        logger.info(f"TrackAnalysisDialog initialized for Track ID: {self.track_element.get('id', 'N/A')}")

    def _setup_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)

        # Top section for Track ID and placeholders
        top_info_layout = QtWidgets.QHBoxLayout()
        track_id_str = self.track_element.get('id', 'N/A')
        self.track_id_label = QtWidgets.QLabel(f"<b>Track ID: {track_id_str}</b>") # [cite: 20]
        top_info_layout.addWidget(self.track_id_label)
        top_info_layout.addStretch()
        # Placeholder for future controls [cite: 21]
        # self.placeholder_label_controls = QtWidgets.QLabel("Future Fit Controls Area")
        # top_info_layout.addWidget(self.placeholder_label_controls)
        main_layout.addLayout(top_info_layout)

        # Main plot area
        if PYQTGRAPH_AVAILABLE and pg is not None:
            self.plot_widget = pg.PlotWidget() # [cite: 20]
            self.scatter_plot_item = pg.ScatterPlotItem()
            self.plot_widget.addItem(self.scatter_plot_item)
            self.plot_widget.setBackground('w') # White background for better contrast
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            main_layout.addWidget(self.plot_widget, stretch=1)
        else:
            self.fallback_label = QtWidgets.QLabel(
                "PyQtGraph library is not installed. Plotting is unavailable.\n"
                "Please install it (e.g., 'pip install pyqtgraph') and restart."
            )
            self.fallback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.fallback_label.setWordWrap(True)
            main_layout.addWidget(self.fallback_label, stretch=1)


        # Placeholder for results display [cite: 21]
        # self.placeholder_label_results = QtWidgets.QLabel("Future Fit Results Area")
        # main_layout.addWidget(self.placeholder_label_results)

        # Dialog buttons
        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close) # [cite: 21]
        self.button_box.rejected.connect(self.reject) # Close button triggers reject
        main_layout.addWidget(self.button_box)

    def _show_pyqtgraph_unavailable_message(self):
        logger.error("PyQtGraph is not available for TrackAnalysisDialog.")
        # The fallback_label in _setup_ui will be visible.

    def _prepare_and_plot_data(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not hasattr(self, 'plot_widget'):
            logger.warning("Cannot prepare/plot data: PyQtGraph not available or plot_widget missing.")
            return

        track_point_data_list = self.track_element.get('data', []) # List of PointData tuples
        # analysis_state = self.track_element.get('analysis_state', {}) # [cite: 22] - Will use later

        self.plot_data_y_vs_t.clear()

        if not track_point_data_list:
            logger.warning(f"No point data found for track ID: {self.track_element.get('id')}")
            self.plot_widget.setTitle("No data to plot")
            return

        for point_data_tuple in track_point_data_list:
            # PointData is (frame_index, time_ms, x_tl_px, y_tl_px)
            _frame_idx, time_ms, _x_tl_px, y_tl_px = point_data_tuple
            
            t_seconds = time_ms / 1000.0 # [cite: 23]
            y_plot = float(self.video_height) - y_tl_px # y_plot = video_height - y_TL [cite: 6, 23]
            
            self.plot_data_y_vs_t.append((t_seconds, y_plot)) # [cite: 24]

        if not self.plot_data_y_vs_t:
            self.plot_widget.setTitle(f"Track {self.track_element.get('id', 'N/A')} - No valid points for y(t) plot")
            return

        # Prepare data for pyqtgraph scatter plot
        times_s = np.array([item[0] for item in self.plot_data_y_vs_t])
        y_pixels_plot = np.array([item[1] for item in self.plot_data_y_vs_t])

        self.scatter_plot_item.setData(x=times_s, y=y_pixels_plot, pen=None, symbol='o', symbolBrush='b', size=8) # [cite: 24]
        
        # Set plot labels and title
        self.plot_widget.setLabel('bottom', "Time (s)") # [cite: 25]
        self.plot_widget.setLabel('left', "Vertical Position (px, bottom-up)") # [cite: 6, 25]
        self.plot_widget.setTitle(f"Track {self.track_element.get('id', 'N/A')} - Vertical Position vs. Time")
        
        # Auto-range axes
        self.plot_widget.autoRange()
        logger.info(f"Plotted {len(self.plot_data_y_vs_t)} points for track ID: {self.track_element.get('id')}")


if __name__ == '__main__':
    # Basic test for the dialog
    if not PYQTGRAPH_AVAILABLE:
        print("PyQtGraph is required to run this test script effectively.")
        # Show a simple message box if Qt is available
        app_instance = QtWidgets.QApplication.instance()
        if not app_instance:
            app_instance = QtWidgets.QApplication(sys.argv)
        
        error_box = QtWidgets.QMessageBox()
        error_box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
        error_box.setText("PyQtGraph is not installed. This test dialog requires PyQtGraph for plotting.")
        error_box.setWindowTitle("Dependency Missing")
        error_box.exec()
        sys.exit(1)

    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    # Mock data for testing
    mock_track_element = {
        'id': 101,
        'type': 'TRACK', # Using string for simplicity in mock
        'name': "Test Track 101",
        'data': [
            (0, 0.0, 50.0, 180.0),      # frame, time_ms, x_tl_px, y_tl_px
            (1, 40.0, 52.0, 170.0),
            (2, 80.0, 55.0, 162.0),
            (3, 120.0, 58.0, 156.0),
            (4, 160.0, 60.0, 152.0),
            (5, 200.0, 62.0, 150.0), # Approx. zenith
            (6, 240.0, 63.0, 151.0),
            (7, 280.0, 64.0, 155.0),
            (8, 320.0, 65.0, 161.0),
            (9, 360.0, 65.0, 169.0),
            (10, 400.0, 64.0, 179.0),
        ],
        'visibility_mode': 'INCREMENTAL',
        'analysis_state': { # Mocked default analysis state
            'fit_settings': {'g_value_ms2': 9.80665, 'time_range_s': None, 'excluded_point_frames': []},
            'fit_results': {'coefficients_poly2': None, 'r_squared': None, 'derived_scale_m_per_px': None, 'is_applied_to_project': False}
        }
    }
    mock_video_fps = 25.0
    mock_video_height = 200 # px

    # Mock MainWindow (very basic, only for parent reference if dialog needs it)
    class MockMainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.element_manager = None # Dialog doesn't use these directly for phase 1 plot
            self.video_handler = None
            self.scale_manager = None


    mock_main_window = MockMainWindow()

    dialog = TrackAnalysisDialog(mock_track_element, mock_video_fps, mock_video_height, mock_main_window)
    dialog.show() # Use show() for modeless, or exec() for modal

    sys.exit(app.exec())