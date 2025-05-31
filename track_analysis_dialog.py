# track_analysis_dialog.py
"""
Dialog window for displaying and analyzing y(t) data for a single track.
"""
import logging
import sys
import math
import copy
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Tuple

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from element_manager import DEFAULT_ANALYSIS_STATE, ElementType

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

    analysisSettingsSaved = QtCore.Signal(int, dict) # track_id, new_analysis_state

    def __init__(self,
                 track_element_copy: Dict[str, Any],
                 video_fps: float,
                 video_height: int,
                 parent_main_window: 'MainWindow'):
        super().__init__(parent_main_window)
        
        self.track_element = track_element_copy # Store the copy
        self.track_id = self.track_element.get('id', -1) # Store track ID for convenience
        self.setWindowTitle(f"Track Analysis - ID: {self.track_id}")
        self.setModal(True)

        self.video_fps = video_fps
        self.video_height = video_height
        self.parent_main_window_ref = parent_main_window

        self.plot_data_y_vs_t: List[Tuple[float, float]] = [] 

        # --- Load initial settings from track_element['analysis_state'] ---
        initial_analysis_state = self.track_element.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE)) # Use DEFAULT_ANALYSIS_STATE from element_manager
        fit_settings = initial_analysis_state.get('fit_settings', DEFAULT_ANALYSIS_STATE['fit_settings'])

        self.current_g_value_ms2: float = fit_settings.get('g_value_ms2', 9.80665)
        self.fit_coeffs: Optional[Tuple[float, float, float]] = None
        self.fit_r_squared: Optional[float] = None
        self.fit_derived_scale_m_per_px: Optional[float] = None
        
        self.fitted_curve_item: Optional[pg.PlotDataItem] = None
        self.scatter_plot_item: Optional[pg.ScatterPlotItem] = None

        self.all_points_original_indices: List[int] = []
        self.included_point_indices_mask: List[bool] = []
        
        # Load initial time range (will be applied in _prepare_and_plot_data)
        self.initial_fit_time_range_s: Optional[Tuple[float, float]] = fit_settings.get('time_range_s', None)
        self.fit_time_range_s: Optional[Tuple[float, float]] = None # Will be set by LinearRegionItem or initial data

        self.linear_region_item: Optional[pg.LinearRegionItem] = None
        
        # Load initial excluded points (will be applied in _prepare_and_plot_data)
        self.initial_excluded_point_frames: List[int] = fit_settings.get('excluded_point_frames', [])
        # --- End Load initial settings ---

        self.setMinimumSize(700, 600) # Slightly increased height for new buttons
        if parent_main_window:
             parent_size = parent_main_window.size()
             self.resize(int(parent_size.width() * 0.7), int(parent_size.height() * 0.8))
        else:
            self.resize(800, 700)

        self._setup_ui()

        if PYQTGRAPH_AVAILABLE:
            self._prepare_and_plot_data() # This will now use initial_excluded_point_frames and initial_fit_time_range_s
            
            # Attempt an initial fit if data is present after preparation
            if self.plot_data_y_vs_t:
                logger.debug(f"Track {self.track_id}: Performing initial fit based on loaded/default analysis settings.")
                self._fit_parabola()
            else:
                self._update_results_display()
        else:
            self._show_pyqtgraph_unavailable_message()

        logger.info(f"TrackAnalysisDialog initialized for Track ID: {self.track_id}")

    def _setup_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(10)

        controls_group_box = QtWidgets.QGroupBox("Analysis Controls")
        controls_layout = QtWidgets.QHBoxLayout(controls_group_box)

        self.track_id_label = QtWidgets.QLabel(f"<b>Track ID: {self.track_id}</b>")
        controls_layout.addWidget(self.track_id_label)
        controls_layout.addStretch(1)

        controls_layout.addWidget(QtWidgets.QLabel("g (m/s²):"))
        self.g_input_lineedit = QtWidgets.QLineEdit(str(self.current_g_value_ms2)) # Use loaded/default g
        self.g_input_lineedit.setValidator(QtGui.QDoubleValidator(0.001, 1000.0, 5, self))
        self.g_input_lineedit.setToolTip("Gravitational acceleration (default: 9.80665 m/s²)")
        self.g_input_lineedit.setMaximumWidth(80)
        controls_layout.addWidget(self.g_input_lineedit)

        self.fit_parabola_button = QtWidgets.QPushButton("Re-Fit Parabola")
        self.fit_parabola_button.setToolTip("Fit/Re-fit parabola to the currently selected data range and points")
        controls_layout.addWidget(self.fit_parabola_button)
        
        main_layout.addWidget(controls_group_box)

        if PYQTGRAPH_AVAILABLE and pg is not None:
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('w')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            
            self.scatter_plot_item = pg.ScatterPlotItem()
            self.plot_widget.addItem(self.scatter_plot_item)

            self.fitted_curve_item = pg.PlotDataItem(pen=pg.mkPen('r', width=2))
            self.plot_widget.addItem(self.fitted_curve_item)

            self.linear_region_item = pg.LinearRegionItem(orientation='vertical',
                                                          brush=QtGui.QColor(0, 0, 255, 50),
                                                          hoverBrush=QtGui.QColor(0, 0, 255, 70),
                                                          movable=True)
            self.linear_region_item.setZValue(-10)
            self.plot_widget.addItem(self.linear_region_item)
            
            main_layout.addWidget(self.plot_widget, stretch=1)
        else:
            self.fallback_label = QtWidgets.QLabel(
                "PyQtGraph library is not installed. Plotting is unavailable.\n"
                "Please install it (e.g., 'pip install pyqtgraph') and restart."
            )
            self.fallback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.fallback_label.setWordWrap(True)
            main_layout.addWidget(self.fallback_label, stretch=1)

        results_group_box = QtWidgets.QGroupBox("Fit Results")
        results_layout = QtWidgets.QFormLayout(results_group_box)
        results_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        results_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        self.coeff_A_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Coefficient A (px/s²):", self.coeff_A_label)
        self.coeff_B_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Coefficient B (px/s):", self.coeff_B_label)
        self.coeff_C_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Coefficient C (px):", self.coeff_C_label)
        results_layout.addRow(QtWidgets.QLabel("---"))
        self.derived_scale_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Derived Scale (m/px):", self.derived_scale_label)
        self.r_squared_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("R² (Goodness of Fit):", self.r_squared_label)
        main_layout.addWidget(results_group_box)

        # --- Phase 4: Action Buttons ---
        action_buttons_layout = QtWidgets.QHBoxLayout()
        self.save_analysis_button = QtWidgets.QPushButton("Save Analysis Settings for Track") # [cite: 68]
        self.save_analysis_button.setToolTip("Save the current fit settings (g, time range, excluded points) and results to this track.")
        action_buttons_layout.addWidget(self.save_analysis_button)

        self.apply_scale_button = QtWidgets.QPushButton("Apply This Scale to Project") # [cite: 68]
        self.apply_scale_button.setToolTip("Apply the currently derived scale (m/px) to the entire project.")
        action_buttons_layout.addWidget(self.apply_scale_button)
        main_layout.addLayout(action_buttons_layout)
        # --- End Phase 4 ---
        
        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        if PYQTGRAPH_AVAILABLE:
            self.fit_parabola_button.clicked.connect(self._fit_parabola)
            if self.scatter_plot_item:
                self.scatter_plot_item.sigClicked.connect(self._on_point_clicked)
            if self.linear_region_item:
                self.linear_region_item.sigRegionChangeFinished.connect(self._on_time_range_changed)
            # --- Phase 4: Connect new buttons ---
            self.save_analysis_button.clicked.connect(self._save_analysis_settings) #
            self.apply_scale_button.clicked.connect(self._apply_scale_to_project)   #
            # --- End Phase 4 ---

    def _show_pyqtgraph_unavailable_message(self):
        logger.error("PyQtGraph is not available for TrackAnalysisDialog.")
        # The fallback_label in _setup_ui will be visible.

    def _prepare_and_plot_data(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not hasattr(self, 'plot_widget') or self.scatter_plot_item is None:
            logger.warning("Cannot prepare/plot data: PyQtGraph not available or plot_widget/scatter_plot_item missing.")
            return

        track_point_data_list = self.track_element.get('data', [])
        self.plot_data_y_vs_t.clear()
        self.all_points_original_indices.clear() # This stores the index within track_point_data_list for each plotted point
        
        raw_frame_indices_for_plotted_points: List[int] = [] # Store raw frame index for matching with excluded_point_frames

        if not track_point_data_list:
            logger.warning(f"No point data found for track ID: {self.track_id}")
            self.plot_widget.setTitle("No data to plot")
            return

        for original_idx, point_data_tuple in enumerate(track_point_data_list):
            frame_idx, time_ms, _x_tl_px, y_tl_px = point_data_tuple
            t_seconds = time_ms / 1000.0
            y_plot = float(self.video_height) - y_tl_px
            self.plot_data_y_vs_t.append((t_seconds, y_plot))
            self.all_points_original_indices.append(original_idx)
            raw_frame_indices_for_plotted_points.append(frame_idx)


        if not self.plot_data_y_vs_t:
            self.plot_widget.setTitle(f"Track {self.track_id} - No valid points for y(t) plot")
            return

        # Initialize point inclusion mask based on loaded excluded_point_frames [cite: 76]
        self.included_point_indices_mask = [True] * len(self.plot_data_y_vs_t)
        for i, plotted_point_frame_idx in enumerate(raw_frame_indices_for_plotted_points):
            if plotted_point_frame_idx in self.initial_excluded_point_frames:
                self.included_point_indices_mask[i] = False
        
        times_s_all = np.array([item[0] for item in self.plot_data_y_vs_t])
        if len(times_s_all) > 0:
            # Use initial_fit_time_range_s if available, otherwise full data range
            min_t_data, max_t_data = min(times_s_all), max(times_s_all)
            if self.initial_fit_time_range_s: # [cite: 76]
                # Ensure loaded range is within actual data bounds
                min_t_init = max(min_t_data, self.initial_fit_time_range_s[0])
                max_t_init = min(max_t_data, self.initial_fit_time_range_s[1])
                if min_t_init < max_t_init: # Valid stored range
                    self.fit_time_range_s = (min_t_init, max_t_init)
                else: # Stored range invalid for current data, fallback to full
                    self.fit_time_range_s = (min_t_data, max_t_data)
            else: # No initial range stored, use full data range
                self.fit_time_range_s = (min_t_data, max_t_data)

            if self.linear_region_item and self.fit_time_range_s:
                 self.linear_region_item.setRegion(self.fit_time_range_s)
                 self.linear_region_item.setVisible(True)
        else: # No data points
            self.fit_time_range_s = None
            if self.linear_region_item:
                self.linear_region_item.setRegion((0,0))
                self.linear_region_item.setVisible(False)

        self._update_point_visuals()
        
        self.plot_widget.setLabel('bottom', "Time (s)")
        self.plot_widget.setLabel('left', "Vertical Position (px, bottom-up)")
        self.plot_widget.setTitle(f"Track {self.track_id} - Vertical Position (Shift+Click to Exclude Points)")
        
        self.plot_widget.autoRange()
        logger.info(f"Plotted {len(self.plot_data_y_vs_t)} points for track ID: {self.track_id}. Initial exclusion mask set from loaded settings.")

    def _fit_parabola(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not self.plot_data_y_vs_t:
            logger.warning("Cannot fit parabola: PyQtGraph not available or no data points.")
            # Clear previous fit results if any
            self.fit_coeffs = None
            self.fit_derived_scale_m_per_px = None
            self.fit_r_squared = None
            self._update_results_display()
            if self.fitted_curve_item: self.fitted_curve_item.clear()
            return

        try:
            g_val_text = self.g_input_lineedit.text()
            self.current_g_value_ms2 = float(g_val_text)
            if self.current_g_value_ms2 <= 0:
                raise ValueError("g value must be positive.")
        except ValueError:
            logger.warning(f"Invalid g value: '{self.g_input_lineedit.text()}'. Using previous/default {self.current_g_value_ms2}.")
            self.g_input_lineedit.setText(str(self.current_g_value_ms2))
            QtWidgets.QMessageBox.warning(self, "Invalid Input", f"Value for 'g' must be a positive number. Using {self.current_g_value_ms2:.5f} m/s².")
            # Do not proceed with fit if g is invalid from user input
            self.fit_coeffs = None; self.fit_derived_scale_m_per_px = None; self.fit_r_squared = None
            self._update_results_display(); 
            if self.fitted_curve_item: self.fitted_curve_item.clear()
            return


        # --- Phase 3: Filter data for fitting ---
        filtered_times_s = []
        filtered_y_pixels_plot = []

        if self.fit_time_range_s: # Ensure time range is set
            min_t, max_t = self.fit_time_range_s
            for i, (t_s, y_plot) in enumerate(self.plot_data_y_vs_t):
                if self.included_point_indices_mask[i] and min_t <= t_s <= max_t: #
                    filtered_times_s.append(t_s)
                    filtered_y_pixels_plot.append(y_plot)
        
        times_s_to_fit = np.array(filtered_times_s)
        y_pixels_to_fit = np.array(filtered_y_pixels_plot)
        # --- End Phase 3 Filter ---

        if len(times_s_to_fit) < 3: # Need at least 3 points for a quadratic fit [cite: 61]
            logger.warning(f"Cannot fit parabola: Only {len(times_s_to_fit)} points selected/in range for fitting.")
            self.fit_coeffs = None
            self.fit_derived_scale_m_per_px = None
            self.fit_r_squared = None
        else:
            try:
                coeffs = np.polyfit(times_s_to_fit, y_pixels_to_fit, 2)
                self.fit_coeffs = (coeffs[0], coeffs[1], coeffs[2]) 

                A_px_s2 = self.fit_coeffs[0]
                if abs(A_px_s2) < 1e-9: 
                    logger.warning("Coefficient A is near zero, cannot derive scale.")
                    self.fit_derived_scale_m_per_px = None
                else:
                    self.fit_derived_scale_m_per_px = -0.5 * self.current_g_value_ms2 / A_px_s2
                
                y_fit_filtered = np.polyval(self.fit_coeffs, times_s_to_fit)
                ss_res = np.sum((y_pixels_to_fit - y_fit_filtered)**2)
                ss_tot = np.sum((y_pixels_to_fit - np.mean(y_pixels_to_fit))**2)
                if abs(ss_tot) < 1e-9:
                    self.fit_r_squared = 1.0 if ss_res < 1e-9 else 0.0 
                else:
                    self.fit_r_squared = 1 - (ss_res / ss_tot)
                
                logger.info(f"Fit complete (on {len(times_s_to_fit)} points): A={self.fit_coeffs[0]:.3g}, B={self.fit_coeffs[1]:.3g}, C={self.fit_coeffs[2]:.3g}, Scale={self.fit_derived_scale_m_per_px if self.fit_derived_scale_m_per_px else 'N/A'}, R2={self.fit_r_squared:.4f}")

            except np.linalg.LinAlgError as e:
                logger.error(f"Linear algebra error during polyfit: {e}")
                self.fit_coeffs = None; self.fit_derived_scale_m_per_px = None; self.fit_r_squared = None
            except Exception as e:
                logger.exception(f"Unexpected error during parabola fitting: {e}")
                self.fit_coeffs = None; self.fit_derived_scale_m_per_px = None; self.fit_r_squared = None

        self._update_results_display()
        self._plot_fitted_curve() # This will use times_s_to_fit for its range if fit is valid

    def _plot_fitted_curve(self) -> None:
        if not PYQTGRAPH_AVAILABLE or self.fitted_curve_item is None:
            return

        if self.fit_coeffs and self.plot_data_y_vs_t:
            # Determine the time range for plotting the curve
            # Use the currently selected fit_time_range_s if available and valid
            # Otherwise, use the range of all available data points
            
            times_for_curve_range = []
            if self.fit_time_range_s: # Time range from LinearRegionItem
                min_t_plot, max_t_plot = self.fit_time_range_s
                if min_t_plot < max_t_plot: # Ensure valid range
                    times_for_curve_range = [min_t_plot, max_t_plot]

            # Fallback to actual data range if filtered range is not good or not set
            if not times_for_curve_range and self.plot_data_y_vs_t:
                all_times_s = [item[0] for item in self.plot_data_y_vs_t]
                if all_times_s:
                    times_for_curve_range = [min(all_times_s), max(all_times_s)]
            
            if times_for_curve_range:
                t_curve_start, t_curve_end = times_for_curve_range
                if t_curve_start == t_curve_end : # Avoid linspace error for single point range
                    if len(self.plot_data_y_vs_t) > 0: # Use first point's time if available
                         t_curve = np.array([self.plot_data_y_vs_t[0][0]])
                    else: # No data, clear curve
                         self.fitted_curve_item.clear()
                         return
                else:
                    t_curve = np.linspace(t_curve_start, t_curve_end, 200) # More points for smoother curve

                y_curve = np.polyval(self.fit_coeffs, t_curve)
                self.fitted_curve_item.setData(x=t_curve, y=y_curve)
            else: # No valid range to plot curve
                self.fitted_curve_item.clear()
        else: # No fit coefficients, clear the curve
            self.fitted_curve_item.clear()

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

    def _update_point_visuals(self) -> None: #
        if not PYQTGRAPH_AVAILABLE or self.scatter_plot_item is None or not self.plot_data_y_vs_t:
            return

        spots = []
        for i, (t_s, y_plot) in enumerate(self.plot_data_y_vs_t):
            if self.included_point_indices_mask[i]:
                # Included point: blue, normal size
                spots.append({'pos': (t_s, y_plot), 'data': i, 'size': 8, 'symbol': 'o', 'brush': pg.mkBrush('b'), 'pen': None})
            else:
                # Excluded point: light gray, smaller size, cross symbol
                spots.append({'pos': (t_s, y_plot), 'data': i, 'size': 6, 'symbol': 'x', 'brush': pg.mkBrush(150, 150, 150, 150), 'pen': pg.mkPen(150,150,150)})
        
        self.scatter_plot_item.setData(spots)


    def _get_current_analysis_state_dict(self) -> Dict[str, Any]: # [cite: 70]
        """
        Collects the current analysis settings and results into a dictionary.
        """
        excluded_frames_list: List[int] = []
        track_data_points = self.track_element.get('data', [])

        for i, is_included in enumerate(self.included_point_indices_mask):
            if not is_included and i < len(self.all_points_original_indices):
                original_point_data_index = self.all_points_original_indices[i]
                if original_point_data_index < len(track_data_points):
                    # track_data_points is a list of PointData tuples (frame_idx, time_ms, x_tl_px, y_tl_px)
                    excluded_frames_list.append(track_data_points[original_point_data_index][0])
        
        # Ensure g_input_lineedit value is up-to-date
        try:
            current_g_from_input = float(self.g_input_lineedit.text())
            if current_g_from_input > 0:
                self.current_g_value_ms2 = current_g_from_input
        except ValueError:
            logger.warning("Could not parse g value from input when getting analysis state, using internal value.")
            # self.current_g_value_ms2 remains unchanged

        state_dict = {
            'fit_settings': {
                'g_value_ms2': self.current_g_value_ms2,
                'time_range_s': self.fit_time_range_s, # Already a tuple (min_t, max_t) or None
                'excluded_point_frames': sorted(list(set(excluded_frames_list))) # Store unique, sorted frame indices
            },
            'fit_results': {
                'coefficients_poly2': self.fit_coeffs,
                'r_squared': self.fit_r_squared,
                'derived_scale_m_per_px': self.fit_derived_scale_m_per_px,
                # is_applied_to_project will be handled by the calling context (e.g., _apply_scale_to_project)
                # For just saving settings, we can fetch it from the original track element's state
                'is_applied_to_project': self.track_element.get('analysis_state', {}).get('fit_results', {}).get('is_applied_to_project', False)
            }
        }
        return state_dict


    @QtCore.Slot(object, object) # For pyqtgraph's sigClicked (plot, points)
    def _on_point_clicked(self, scatter_plot_item: pg.ScatterPlotItem, clicked_points: List[pg.SpotItem]) -> None: #
        if not clicked_points:
            return
        
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if not (modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier): # [cite: 55]
            logger.debug("Point clicked without Shift modifier. No exclusion action.")
            return

        clicked_spot = clicked_points[0] # Process first clicked point
        point_original_idx = clicked_spot.data() # Retrieve original index stored in point's data [cite: 55]

        if point_original_idx is not None and 0 <= point_original_idx < len(self.included_point_indices_mask):
            # Toggle inclusion state [cite: 56]
            self.included_point_indices_mask[point_original_idx] = not self.included_point_indices_mask[point_original_idx]
            logger.info(f"Point at original index {point_original_idx} (t={clicked_spot.pos().x():.2f}s) "
                        f"toggled to {'included' if self.included_point_indices_mask[point_original_idx] else 'excluded'}.")
            
            self._update_point_visuals() # Update visuals [cite: 56]
            self._fit_parabola()         # Trigger re-fit [cite: 50, 56]
        else:
            logger.warning(f"Clicked point has invalid original index: {point_original_idx}")

    @QtCore.Slot(object) # For pyqtgraph's sigRegionChangeFinished (region_item)
    def _on_time_range_changed(self, region_item: pg.LinearRegionItem) -> None: #
        if self.linear_region_item is None: return
        
        current_region = self.linear_region_item.getRegion() #
        self.fit_time_range_s = (current_region[0], current_region[1]) #
        logger.info(f"Fit time range changed to: {self.fit_time_range_s[0]:.3f}s - {self.fit_time_range_s[1]:.3f}s")
        
        self._fit_parabola() # Trigger re-fit [cite: 50, 59]

    @QtCore.Slot()
    def _save_analysis_settings(self) -> None: # [cite: 71]
        """Saves the current analysis settings and results to the track element in ElementManager."""
        if self.track_id == -1:
            logger.error("Cannot save analysis settings: Track ID is invalid.")
            QtWidgets.QMessageBox.warning(self, "Save Error", "Invalid track identifier. Cannot save settings.")
            return

        current_state_to_save = self._get_current_analysis_state_dict()
        
        # Update the 'is_applied_to_project' field from the original track_element's analysis_state
        # because this button doesn't change that flag.
        original_analysis_state = self.track_element.get('analysis_state', DEFAULT_ANALYSIS_STATE)
        current_state_to_save['fit_results']['is_applied_to_project'] = original_analysis_state.get('fit_results', {}).get('is_applied_to_project', False)

        logger.info(f"Saving analysis settings for Track ID {self.track_id}: {current_state_to_save}")
        
        success = self.parent_main_window_ref.element_manager.update_track_analysis_state(
            self.track_id,
            current_state_to_save
        )

        if success:
            # Also update the local copy of track_element so subsequent saves in this dialog session use the latest
            self.track_element['analysis_state'] = copy.deepcopy(current_state_to_save)
            QtWidgets.QMessageBox.information(self, "Settings Saved", f"Analysis settings and results saved for Track {self.track_id}.")
            self.analysisSettingsSaved.emit(self.track_id, current_state_to_save) # Emit signal
        else:
            QtWidgets.QMessageBox.warning(self, "Save Error", f"Could not save analysis settings for Track {self.track_id}.")

    @QtCore.Slot()
    def _apply_scale_to_project(self) -> None: # [cite: 72]
        """Applies the currently derived scale to the global ScaleManager."""
        if self.fit_derived_scale_m_per_px is not None and self.fit_derived_scale_m_per_px > 0:
            reply = QtWidgets.QMessageBox.question(
                self, "Apply Scale to Project",
                f"Apply derived scale ({self.fit_derived_scale_m_per_px:.6g} m/px) to the entire project?\n"
                "This will override any existing project scale and clear any manually drawn scale line.",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                # Set the global scale
                scale_source_desc = f"Track {self.track_id} Parabolic Fit (g={self.current_g_value_ms2:.3f} m/s²)"
                self.parent_main_window_ref.scale_manager.set_scale(
                    self.fit_derived_scale_m_per_px,
                    called_from_line_definition=False, # This will clear any existing defined line
                    source_description=scale_source_desc
                )
                
                # Update this track's analysis_state to mark it as applied
                current_state_for_this_track = self._get_current_analysis_state_dict()
                current_state_for_this_track['fit_results']['is_applied_to_project'] = True
                self.parent_main_window_ref.element_manager.update_track_analysis_state(
                    self.track_id,
                    current_state_for_this_track
                )
                # Update local copy
                self.track_element['analysis_state'] = copy.deepcopy(current_state_for_this_track)


                # Mark all OTHER tracks as not applied
                for i, el in enumerate(self.parent_main_window_ref.element_manager.elements):
                    if el.get('type') == ElementType.TRACK and el.get('id') != self.track_id:
                        other_track_state = el.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
                        other_track_state['fit_results']['is_applied_to_project'] = False
                        self.parent_main_window_ref.element_manager.update_track_analysis_state(
                            el.get('id'),
                            other_track_state
                        )
                
                QtWidgets.QMessageBox.information(self, "Scale Applied",
                                                  f"Scale {self.fit_derived_scale_m_per_px:.6g} m/px applied to project.\n"
                                                  "Analysis settings for this track also saved.")
                self.analysisSettingsSaved.emit(self.track_id, current_state_for_this_track) # Signal that this track's settings were effectively saved
                self.accept() # Optionally close dialog after applying scale
            else:
                logger.info("User cancelled applying scale to project.")
        else:
            QtWidgets.QMessageBox.warning(self, "Apply Scale Error",
                                          "No valid scale derived from the current fit to apply.")


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