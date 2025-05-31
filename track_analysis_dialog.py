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
        super().__init__(parent_main_window)
        self.setWindowTitle(f"Track Analysis - ID: {track_element_copy.get('id', 'N/A')}")
        self.setModal(True) # [cite: 15]

        self.track_element = track_element_copy # [cite: 19]
        self.video_fps = video_fps
        self.video_height = video_height
        self.parent_main_window_ref = parent_main_window

        self.plot_data_y_vs_t: List[Tuple[float, float]] = []

        # --- Phase 2: Instance variables for fitting ---
        self.current_g_value_ms2: float = 9.80665 # Default g in m/s^2 [cite: 35]
        self.fit_coeffs: Optional[Tuple[float, float, float]] = None # A, B, C
        self.fit_r_squared: Optional[float] = None
        self.fit_derived_scale_m_per_px: Optional[float] = None
        
        self.fitted_curve_item: Optional[pg.PlotDataItem] = None # For the fitted parabola line
        # --- End Phase 2 instance variables ---

        self.setMinimumSize(700, 550)
        if parent_main_window:
             parent_size = parent_main_window.size()
             self.resize(int(parent_size.width() * 0.6), int(parent_size.height() * 0.7))
        else:
            self.resize(800, 600)

        self._setup_ui() # This will now include new widgets

        if PYQTGRAPH_AVAILABLE:
            self._prepare_and_plot_data()
            self._update_results_display() # Initialize results display to N/A
        else:
            self._show_pyqtgraph_unavailable_message()

        logger.info(f"TrackAnalysisDialog initialized for Track ID: {self.track_element.get('id', 'N/A')}")


    def _setup_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(10) # Add some spacing between major sections

        # --- Top section for Track ID and Fit Controls ---
        controls_group_box = QtWidgets.QGroupBox("Analysis Controls")
        controls_layout = QtWidgets.QHBoxLayout(controls_group_box)

        track_id_str = self.track_element.get('id', 'N/A')
        self.track_id_label = QtWidgets.QLabel(f"<b>Track ID: {track_id_str}</b>") # [cite: 20]
        controls_layout.addWidget(self.track_id_label)
        controls_layout.addStretch(1)

        controls_layout.addWidget(QtWidgets.QLabel("g (m/s²):"))
        self.g_input_lineedit = QtWidgets.QLineEdit(str(self.current_g_value_ms2)) # [cite: 35]
        self.g_input_lineedit.setValidator(QtGui.QDoubleValidator(0.001, 1000.0, 5, self)) # Positive float for g [cite: 35]
        self.g_input_lineedit.setToolTip("Gravitational acceleration (default: 9.80665 m/s²)")
        self.g_input_lineedit.setMaximumWidth(80)
        controls_layout.addWidget(self.g_input_lineedit)

        self.fit_parabola_button = QtWidgets.QPushButton("Fit Parabola") # [cite: 35]
        self.fit_parabola_button.setToolTip("Fit a parabola to the selected y(t) data points")
        controls_layout.addWidget(self.fit_parabola_button)
        
        main_layout.addWidget(controls_group_box)


        # --- Main plot area ---
        if PYQTGRAPH_AVAILABLE and pg is not None:
            self.plot_widget = pg.PlotWidget() # [cite: 20]
            self.plot_widget.setBackground('w')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            
            # Scatter plot for original data points
            self.scatter_plot_item = pg.ScatterPlotItem(pen=None, symbol='o', symbolBrush='b', size=8)
            self.plot_widget.addItem(self.scatter_plot_item)

            # Plot item for the fitted curve (initially no data)
            self.fitted_curve_item = pg.PlotDataItem(pen=pg.mkPen('r', width=2)) # [cite: 42, 43]
            self.plot_widget.addItem(self.fitted_curve_item)
            
            main_layout.addWidget(self.plot_widget, stretch=1)
        else:
            self.fallback_label = QtWidgets.QLabel(
                "PyQtGraph library is not installed. Plotting is unavailable.\n"
                "Please install it (e.g., 'pip install pyqtgraph') and restart."
            )
            self.fallback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.fallback_label.setWordWrap(True)
            main_layout.addWidget(self.fallback_label, stretch=1)


        # --- Results Display Area --- [cite: 36]
        results_group_box = QtWidgets.QGroupBox("Fit Results")
        results_layout = QtWidgets.QFormLayout(results_group_box)
        results_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows) #
        results_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight) #

        self.coeff_A_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Coefficient A (px/s²):", self.coeff_A_label)
        self.coeff_B_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Coefficient B (px/s):", self.coeff_B_label)
        self.coeff_C_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Coefficient C (px):", self.coeff_C_label)
        
        results_layout.addRow(QtWidgets.QLabel("---")) # Visual separator

        self.derived_scale_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Derived Scale (m/px):", self.derived_scale_label)
        self.r_squared_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("R² (Goodness of Fit):", self.r_squared_label)

        main_layout.addWidget(results_group_box)
        
        # Dialog buttons
        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close) # [cite: 21]
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        # Connect signals for Phase 2
        if PYQTGRAPH_AVAILABLE:
            self.fit_parabola_button.clicked.connect(self._fit_parabola) # [cite: 44]
            # Connect g_input QLineEdit editingFinished to _fit_parabola [cite: 45]
            # Alternatively, _fit_parabola can just read the current value when button is clicked.
            # Let's go with the button click re-reading g for simplicity now.
            # self.g_input_lineedit.editingFinished.connect(self._fit_parabola)

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

    def _fit_parabola(self) -> None: # [cite: 34, 37]
        if not PYQTGRAPH_AVAILABLE or not self.plot_data_y_vs_t:
            logger.warning("Cannot fit parabola: PyQtGraph not available or no data points.")
            self.fit_coeffs = None
            self.fit_derived_scale_m_per_px = None
            self.fit_r_squared = None
            self._update_results_display()
            self._plot_fitted_curve() # Clears the curve if no fit
            return

        try:
            g_val_text = self.g_input_lineedit.text()
            self.current_g_value_ms2 = float(g_val_text) # [cite: 38]
            if self.current_g_value_ms2 <= 0:
                raise ValueError("g value must be positive.")
        except ValueError:
            logger.warning(f"Invalid g value: '{self.g_input_lineedit.text()}'. Using default {self.current_g_value_ms2}.")
            self.g_input_lineedit.setText(str(self.current_g_value_ms2)) # Revert to last valid g
            # Optionally show a message box
            QtWidgets.QMessageBox.warning(self, "Invalid Input", f"Value for 'g' must be a positive number. Using previous value: {self.current_g_value_ms2:.5f} m/s².")


        times_s = np.array([item[0] for item in self.plot_data_y_vs_t])
        y_pixels_plot = np.array([item[1] for item in self.plot_data_y_vs_t])

        if len(times_s) < 3: # Need at least 3 points for a quadratic fit
            logger.warning("Cannot fit parabola: Less than 3 data points available.")
            self.fit_coeffs = None
            self.fit_derived_scale_m_per_px = None
            self.fit_r_squared = None
        else:
            try:
                coeffs = np.polyfit(times_s, y_pixels_plot, 2) # [cite: 38]
                self.fit_coeffs = (coeffs[0], coeffs[1], coeffs[2]) # A, B, C [cite: 38]

                # Calculate derived scale Sm/px = -0.5 * g / A [cite: 34, 39]
                A_px_s2 = self.fit_coeffs[0]
                if abs(A_px_s2) < 1e-9: # Avoid division by zero or near-zero [cite: 39]
                    logger.warning("Coefficient A is near zero, cannot derive scale.")
                    self.fit_derived_scale_m_per_px = None
                else:
                    self.fit_derived_scale_m_per_px = -0.5 * self.current_g_value_ms2 / A_px_s2 # [cite: 39]
                
                # Calculate R-squared [cite: 40]
                y_fit = np.polyval(self.fit_coeffs, times_s) # [cite: 40]
                ss_res = np.sum((y_pixels_plot - y_fit)**2) # [cite: 40]
                ss_tot = np.sum((y_pixels_plot - np.mean(y_pixels_plot))**2) # [cite: 40]
                if abs(ss_tot) < 1e-9: # Avoid division by zero if all y_plot points are the same
                    self.fit_r_squared = 1.0 if ss_res < 1e-9 else 0.0 # Perfect fit or no variance
                else:
                    self.fit_r_squared = 1 - (ss_res / ss_tot) # [cite: 40]
                
                logger.info(f"Fit complete: A={self.fit_coeffs[0]:.3g}, B={self.fit_coeffs[1]:.3g}, C={self.fit_coeffs[2]:.3g}, Scale={self.fit_derived_scale_m_per_px if self.fit_derived_scale_m_per_px else 'N/A'}, R2={self.fit_r_squared:.4f}")

            except np.linalg.LinAlgError as e:
                logger.error(f"Linear algebra error during polyfit: {e}")
                self.fit_coeffs = None
                self.fit_derived_scale_m_per_px = None
                self.fit_r_squared = None
            except Exception as e:
                logger.exception(f"Unexpected error during parabola fitting: {e}")
                self.fit_coeffs = None
                self.fit_derived_scale_m_per_px = None
                self.fit_r_squared = None

        self._update_results_display() # [cite: 41]
        self._plot_fitted_curve()    # [cite: 41]

    def _plot_fitted_curve(self) -> None: # [cite: 42]
        if not PYQTGRAPH_AVAILABLE or self.fitted_curve_item is None:
            return

        if self.fit_coeffs and self.plot_data_y_vs_t:
            times_s = np.array([item[0] for item in self.plot_data_y_vs_t])
            if len(times_s) > 0:
                # Generate points for the curve over the time range of the data
                t_curve = np.linspace(min(times_s), max(times_s), 100) # 100 points for a smooth curve
                y_curve = np.polyval(self.fit_coeffs, t_curve) # [cite: 41]
                self.fitted_curve_item.setData(x=t_curve, y=y_curve) # [cite: 43]
            else:
                self.fitted_curve_item.clear() # No data points to define range
        else:
            self.fitted_curve_item.clear() # No fit coefficients, clear the curve

    def _update_results_display(self) -> None: # [cite: 44]
        if self.fit_coeffs:
            self.coeff_A_label.setText(f"{self.fit_coeffs[0]:.4g}")
            self.coeff_B_label.setText(f"{self.fit_coeffs[1]:.4g}")
            self.coeff_C_label.setText(f"{self.fit_coeffs[2]:.4g}")
        else:
            self.coeff_A_label.setText("N/A")
            self.coeff_B_label.setText("N/A")
            self.coeff_C_label.setText("N/A")

        if self.fit_derived_scale_m_per_px is not None:
            self.derived_scale_label.setText(f"{self.fit_derived_scale_m_per_px:.6g}")
        else:
            self.derived_scale_label.setText("N/A")

        if self.fit_r_squared is not None:
            self.r_squared_label.setText(f"{self.fit_r_squared:.4f}")
        else:
            self.r_squared_label.setText("N/A")

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