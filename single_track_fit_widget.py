# single_track_fit_widget.py
"""
Reusable QWidget for displaying and interactively fitting y(t) data
for a single track.
"""
import logging
import copy
import math # Ensure math is imported
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Tuple

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from element_manager import DEFAULT_ANALYSIS_STATE # For default g value

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    pg = None
    PYQTGRAPH_AVAILABLE = False
    logging.warning(
        "PyQtGraph not found. SingleTrackFitWidget plotting will be unavailable."
    )

if TYPE_CHECKING:
    from main_window import MainWindow
    from scale_analysis_view import ScaleAnalysisView # For parent_view type hint

logger = logging.getLogger(__name__)

class SingleTrackFitWidget(QtWidgets.QWidget):
    """
    A widget that encapsulates the UI and logic for analyzing a single track's
    y(t) data, including plotting, interactive point exclusion, time range
    selection, and parabolic fitting.
    """

    analysisSettingsToBeSaved = QtCore.Signal(int, dict)
    scaleToBeApplied = QtCore.Signal(int, float)

    def __init__(self,
                 main_window_ref: 'MainWindow',
                 parent_view: 'ScaleAnalysisView',
                 parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.main_window_ref = main_window_ref
        self.parent_view_ref = parent_view

        self.track_id: Optional[int] = None
        self.track_element_copy: Optional[Dict[str, Any]] = None
        self.video_fps: float = 0.0
        self.video_height: int = 0

        self.plot_data_y_vs_t: List[Tuple[float, float]] = []
        self.all_points_original_indices: List[int] = [] 
        self.raw_frame_indices_for_plotted_points: List[int] = [] 
        self.included_point_indices_mask: List[bool] = []
        self.fit_time_range_s: Optional[Tuple[float, float]] = None

        self.current_g_value_ms2: float = DEFAULT_ANALYSIS_STATE['fit_settings']['g_value_ms2']
        self.fit_coeffs: Optional[Tuple[float, float, float]] = None
        self.fit_r_squared: Optional[float] = None
        self.fit_derived_scale_m_per_px: Optional[float] = None

        self.plot_widget: Optional[pg.PlotWidget] = None
        self.scatter_plot_item: Optional[pg.ScatterPlotItem] = None
        self.fitted_curve_item: Optional[pg.PlotDataItem] = None
        self.linear_region_item: Optional[pg.LinearRegionItem] = None

        self.track_id_label: Optional[QtWidgets.QLabel] = None
        self.g_input_lineedit: Optional[QtWidgets.QLineEdit] = None
        self.refit_button: Optional[QtWidgets.QPushButton] = None

        self.coeff_A_label: Optional[QtWidgets.QLabel] = None
        self.derived_scale_label: Optional[QtWidgets.QLabel] = None
        self.r_squared_label: Optional[QtWidgets.QLabel] = None
        
        self.save_analysis_button: Optional[QtWidgets.QPushButton] = None
        self.apply_scale_button: Optional[QtWidgets.QPushButton] = None
        self.reset_fit_settings_button: Optional[QtWidgets.QPushButton] = None

        self._setup_ui()
        self._connect_signals()

        self.clear_and_disable()
        logger.info("SingleTrackFitWidget initialized.")

    def _setup_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        controls_group_box = QtWidgets.QGroupBox("Fit Configuration")
        controls_layout = QtWidgets.QHBoxLayout(controls_group_box)
        self.track_id_label = QtWidgets.QLabel("<b>Track ID: N/A</b>")
        controls_layout.addWidget(self.track_id_label)
        controls_layout.addStretch(1)
        controls_layout.addWidget(QtWidgets.QLabel("g (m/s²):"))
        self.g_input_lineedit = QtWidgets.QLineEdit(str(self.current_g_value_ms2))
        self.g_input_lineedit.setValidator(QtGui.QDoubleValidator(0.001, 1000.0, 5, self))
        self.g_input_lineedit.setToolTip("Gravitational acceleration (default: 9.80665 m/s²)")
        self.g_input_lineedit.setMaximumWidth(80)
        controls_layout.addWidget(self.g_input_lineedit)
        self.refit_button = QtWidgets.QPushButton("Re-Fit Selected Track")
        self.refit_button.setToolTip("Fit/Re-fit parabola to the currently selected data range and points")
        controls_layout.addWidget(self.refit_button)
        main_layout.addWidget(controls_group_box)

        if PYQTGRAPH_AVAILABLE and pg is not None:
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('w')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setLabel('bottom', "Time (s)")
            self.plot_widget.setLabel('left', "Vertical Position (px, bottom-up)")
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
            fallback_label = QtWidgets.QLabel("PyQtGraph library is not available. Plotting is disabled.")
            fallback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            fallback_label.setWordWrap(True)
            main_layout.addWidget(fallback_label, stretch=1)

        results_group_box = QtWidgets.QGroupBox("Fit Results")
        results_layout = QtWidgets.QFormLayout(results_group_box)
        results_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        results_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.coeff_A_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Coefficient A (px/s²):", self.coeff_A_label)
        self.derived_scale_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("Derived Scale (m/px):", self.derived_scale_label)
        self.r_squared_label = QtWidgets.QLabel("N/A")
        results_layout.addRow("R² (Goodness of Fit):", self.r_squared_label)
        main_layout.addWidget(results_group_box)

        action_buttons_layout = QtWidgets.QHBoxLayout()
        self.reset_fit_settings_button = QtWidgets.QPushButton("Reset Fit Settings")
        self.reset_fit_settings_button.setToolTip("Reset time range and point exclusions to default (all points, full time range).")
        action_buttons_layout.addWidget(self.reset_fit_settings_button)
        action_buttons_layout.addStretch()
        self.save_analysis_button = QtWidgets.QPushButton("Save Analysis for This Track")
        self.save_analysis_button.setToolTip("Save the current fit settings (g, time range, excluded points) and results to this track.")
        action_buttons_layout.addWidget(self.save_analysis_button)
        self.apply_scale_button = QtWidgets.QPushButton("Apply Scale from This Track to Project")
        self.apply_scale_button.setToolTip("Apply the currently derived scale (m/px) from this track to the entire project.")
        action_buttons_layout.addWidget(self.apply_scale_button)
        main_layout.addLayout(action_buttons_layout)

    def _connect_signals(self) -> None:
        if PYQTGRAPH_AVAILABLE:
            if self.refit_button:
                self.refit_button.clicked.connect(self._on_refit_button_clicked)
            if self.g_input_lineedit:
                self.g_input_lineedit.editingFinished.connect(self._on_g_value_changed)
            if self.scatter_plot_item:
                self.scatter_plot_item.sigClicked.connect(self._on_point_clicked)
            if self.linear_region_item:
                self.linear_region_item.sigRegionChangeFinished.connect(self._on_time_range_changed)
        
        if self.save_analysis_button:
            self.save_analysis_button.clicked.connect(self._on_save_analysis_button_clicked)
        if self.apply_scale_button:
            self.apply_scale_button.clicked.connect(self._on_apply_scale_button_clicked)
        if self.reset_fit_settings_button:
            self.reset_fit_settings_button.clicked.connect(self._on_reset_fit_settings_button_clicked)

    def load_track_data(self,
                        track_element_copy: Dict[str, Any],
                        video_fps: float,
                        video_height: int) -> None:
        logger.info(f"SingleTrackFitWidget: Loading data for Track ID {track_element_copy.get('id')}")
        self.track_element_copy = copy.deepcopy(track_element_copy)
        self.track_id = self.track_element_copy.get('id')
        self.video_fps = video_fps
        self.video_height = video_height

        if self.track_id_label:
            self.track_id_label.setText(f"<b>Track ID: {self.track_id or 'N/A'}</b>")

        analysis_state = self.track_element_copy.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
        fit_settings = analysis_state.get('fit_settings', DEFAULT_ANALYSIS_STATE['fit_settings'])
        
        self.current_g_value_ms2 = fit_settings.get('g_value_ms2', DEFAULT_ANALYSIS_STATE['fit_settings']['g_value_ms2'])
        if self.g_input_lineedit:
            self.g_input_lineedit.setText(str(self.current_g_value_ms2))

        initial_excluded_frames = fit_settings.get('excluded_point_frames', [])
        initial_fit_time_range_s = fit_settings.get('time_range_s', None)

        track_point_data_list = self.track_element_copy.get('data', [])
        self.plot_data_y_vs_t.clear()
        self.all_points_original_indices.clear()
        self.raw_frame_indices_for_plotted_points.clear()

        if not track_point_data_list:
            logger.warning(f"No point data found for track ID: {self.track_id}")
            if self.plot_widget: self.plot_widget.setTitle("No data to plot")
            self.clear_and_disable()
            if self.track_id_label: self.track_id_label.setText(f"<b>Track ID: {self.track_id or 'N/A'} (No Data)</b>")
            return

        for original_idx, point_data_tuple in enumerate(track_point_data_list):
            frame_idx, time_ms, _x_tl_px, y_tl_px = point_data_tuple
            t_seconds = time_ms / 1000.0
            y_plot = float(self.video_height) - y_tl_px
            self.plot_data_y_vs_t.append((t_seconds, y_plot))
            self.all_points_original_indices.append(original_idx)
            self.raw_frame_indices_for_plotted_points.append(frame_idx)

        if not self.plot_data_y_vs_t:
            if self.plot_widget: self.plot_widget.setTitle(f"Track {self.track_id} - No valid points")
            self.clear_and_disable()
            if self.track_id_label: self.track_id_label.setText(f"<b>Track ID: {self.track_id or 'N/A'} (No Valid Pts)</b>")
            return

        self.included_point_indices_mask = [True] * len(self.plot_data_y_vs_t)
        for i, plotted_point_frame_idx in enumerate(self.raw_frame_indices_for_plotted_points):
            if plotted_point_frame_idx in initial_excluded_frames:
                self.included_point_indices_mask[i] = False
        
        times_s_all = np.array([item[0] for item in self.plot_data_y_vs_t])
        min_t_data, max_t_data = min(times_s_all), max(times_s_all)

        if initial_fit_time_range_s:
            min_t_init = max(min_t_data, initial_fit_time_range_s[0])
            max_t_init = min(max_t_data, initial_fit_time_range_s[1])
            self.fit_time_range_s = (min_t_init, max_t_init) if min_t_init < max_t_init else (min_t_data, max_t_data)
        else:
            self.fit_time_range_s = (min_t_data, max_t_data)

        if self.linear_region_item and self.fit_time_range_s:
             self.linear_region_item.setRegion(self.fit_time_range_s)
             self.linear_region_item.setVisible(True)
        
        self._update_point_visuals() # This sets the scatter data

        # Don't call autoRange here yet, _fit_parabola will do it after curve is also plotted
        if self.plot_widget:
            self.plot_widget.setLabel('bottom', "Time (s)")
            self.plot_widget.setLabel('left', "Vertical Position (px, bottom-up)")
            self.plot_widget.setTitle(f"Track {self.track_id} y(t) (Shift+Click to Exclude)")
            # self.plot_widget.autoRange() # Moved to end of _fit_parabola

        self._fit_parabola()

        if self.g_input_lineedit: self.g_input_lineedit.setEnabled(True)
        if self.refit_button: self.refit_button.setEnabled(True)
        if self.save_analysis_button: self.save_analysis_button.setEnabled(True)
        if self.apply_scale_button: self.apply_scale_button.setEnabled(True)
        if self.reset_fit_settings_button: self.reset_fit_settings_button.setEnabled(True)
        self.setEnabled(True)

    def _fit_parabola(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not self.plot_data_y_vs_t:
            logger.warning("Cannot fit parabola: PyQtGraph not available or no data points.")
            self.fit_coeffs = None; self.fit_derived_scale_m_per_px = None; self.fit_r_squared = None
            self._update_results_display()
            if self.fitted_curve_item: self.fitted_curve_item.clear()
            # --- BEGIN MODIFICATION ---
            if self.plot_widget: self.plot_widget.autoRange(padding=0.05) #
            # --- END MODIFICATION ---
            return

        try:
            if self.g_input_lineedit:
                g_val_text = self.g_input_lineedit.text()
                self.current_g_value_ms2 = float(g_val_text)
                if self.current_g_value_ms2 <= 0:
                    raise ValueError("g value must be positive.")
        except ValueError:
            if self.g_input_lineedit:
                self.g_input_lineedit.setText(str(DEFAULT_ANALYSIS_STATE['fit_settings']['g_value_ms2']))
            self.current_g_value_ms2 = DEFAULT_ANALYSIS_STATE['fit_settings']['g_value_ms2']
            logger.warning(f"Invalid g value. Using default {self.current_g_value_ms2}.")
            self.fit_coeffs = None; self.fit_derived_scale_m_per_px = None; self.fit_r_squared = None
            self._update_results_display()
            if self.fitted_curve_item: self.fitted_curve_item.clear()
            # --- BEGIN MODIFICATION ---
            if self.plot_widget: self.plot_widget.autoRange(padding=0.05) #
            # --- END MODIFICATION ---
            return

        filtered_times_s = []
        filtered_y_pixels_plot = []
        if self.fit_time_range_s:
            min_t, max_t = self.fit_time_range_s
            for i, (t_s, y_plot) in enumerate(self.plot_data_y_vs_t):
                if self.included_point_indices_mask[i] and min_t <= t_s <= max_t:
                    filtered_times_s.append(t_s)
                    filtered_y_pixels_plot.append(y_plot)
        
        times_s_to_fit = np.array(filtered_times_s)
        y_pixels_to_fit = np.array(filtered_y_pixels_plot)

        if len(times_s_to_fit) < 3:
            logger.warning(f"Cannot fit parabola: Only {len(times_s_to_fit)} points selected for fitting.")
            self.fit_coeffs = None; self.fit_derived_scale_m_per_px = None; self.fit_r_squared = None
        else:
            try:
                coeffs = np.polyfit(times_s_to_fit, y_pixels_to_fit, 2)
                self.fit_coeffs = (coeffs[0], coeffs[1], coeffs[2])
                A_px_s2 = self.fit_coeffs[0]
                self.fit_derived_scale_m_per_px = -0.5 * self.current_g_value_ms2 / A_px_s2 if abs(A_px_s2) > 1e-9 else None
                
                y_fit_filtered = np.polyval(self.fit_coeffs, times_s_to_fit)
                ss_res = np.sum((y_pixels_to_fit - y_fit_filtered)**2)
                ss_tot = np.sum((y_pixels_to_fit - np.mean(y_pixels_to_fit))**2)
                self.fit_r_squared = 1 - (ss_res / ss_tot) if abs(ss_tot) > 1e-9 else (1.0 if ss_res < 1e-9 else 0.0)
                logger.info(f"Fit: A={A_px_s2:.3g}, Scale={self.fit_derived_scale_m_per_px if self.fit_derived_scale_m_per_px else 'N/A'}, R2={self.fit_r_squared:.4f}")
            except Exception as e:
                logger.exception(f"Error during fitting: {e}")
                self.fit_coeffs = None; self.fit_derived_scale_m_per_px = None; self.fit_r_squared = None

        self._update_results_display()
        self._plot_fitted_curve()
        # --- BEGIN MODIFICATION ---
        if self.plot_widget:
            self.plot_widget.autoRange(padding=0.05) # Add padding for better visuals
            logger.debug("Called autoRange at the end of _fit_parabola.")
        # --- END MODIFICATION ---


    def _plot_fitted_curve(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not self.fitted_curve_item: return

        if self.fit_coeffs and self.plot_data_y_vs_t:
            plot_times = []
            if self.fit_time_range_s:
                min_t_plot, max_t_plot = self.fit_time_range_s
                if min_t_plot <= max_t_plot:
                    plot_times = [min_t_plot, max_t_plot]
            
            if not plot_times and self.plot_data_y_vs_t:
                all_t = [p[0] for p in self.plot_data_y_vs_t]
                if all_t: plot_times = [min(all_t), max(all_t)]

            if plot_times:
                t_start, t_end = plot_times
                t_curve = np.linspace(t_start, t_end, 200) if t_start < t_end else np.array([t_start])
                y_curve = np.polyval(self.fit_coeffs, t_curve)
                self.fitted_curve_item.setData(x=t_curve, y=y_curve)
            else:
                self.fitted_curve_item.clear()
        else:
            self.fitted_curve_item.clear()

    def _update_results_display(self) -> None:
        if self.coeff_A_label:
            self.coeff_A_label.setText(f"{self.fit_coeffs[0]:.4g}" if self.fit_coeffs else "N/A")
        if self.derived_scale_label:
            self.derived_scale_label.setText(f"{self.fit_derived_scale_m_per_px:.6g}" if self.fit_derived_scale_m_per_px is not None else "N/A")
        if self.r_squared_label:
            self.r_squared_label.setText(f"{self.fit_r_squared:.4f}" if self.fit_r_squared is not None else "N/A")

    def _update_point_visuals(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not self.scatter_plot_item or not self.plot_data_y_vs_t:
            return
        spots = []
        for i, (t_s, y_plot) in enumerate(self.plot_data_y_vs_t):
            brush_color = 'b' if self.included_point_indices_mask[i] else QtGui.QColor(150, 150, 150, 150)
            symbol_char = 'o' if self.included_point_indices_mask[i] else 'x'
            symbol_size = 8 if self.included_point_indices_mask[i] else 6
            spots.append({'pos': (t_s, y_plot), 'data': i, 
                          'brush': pg.mkBrush(brush_color), 'symbol': symbol_char, 'size': symbol_size,
                          'pen': None if self.included_point_indices_mask[i] else pg.mkPen(150,150,150)})
        self.scatter_plot_item.setData(spots)

    def _get_current_analysis_state_dict(self) -> Dict[str, Any]:
        excluded_frames_list: List[int] = []
        track_data_points = []
        if self.track_element_copy and 'data' in self.track_element_copy:
            track_data_points = self.track_element_copy.get('data', [])

        for i, is_included in enumerate(self.included_point_indices_mask):
            if not is_included and i < len(self.raw_frame_indices_for_plotted_points):
                excluded_frames_list.append(self.raw_frame_indices_for_plotted_points[i])
        
        current_g = self.current_g_value_ms2
        
        is_applied = False
        if self.track_element_copy and 'analysis_state' in self.track_element_copy:
            is_applied = self.track_element_copy['analysis_state'].get('fit_results', {}).get('is_applied_to_project', False)

        state_dict = {
            'fit_settings': {
                'g_value_ms2': current_g,
                'time_range_s': self.fit_time_range_s,
                'excluded_point_frames': sorted(list(set(excluded_frames_list)))
            },
            'fit_results': {
                'coefficients_poly2': self.fit_coeffs,
                'r_squared': self.fit_r_squared,
                'derived_scale_m_per_px': self.fit_derived_scale_m_per_px,
                'is_applied_to_project': is_applied
            }
        }
        return state_dict

    @QtCore.Slot()
    def _on_refit_button_clicked(self) -> None:
        logger.debug("Re-Fit button clicked.")
        self._fit_parabola()

    @QtCore.Slot()
    def _on_g_value_changed(self) -> None:
        if self.g_input_lineedit:
            try:
                new_g = float(self.g_input_lineedit.text())
                if new_g > 0:
                    if abs(self.current_g_value_ms2 - new_g) > 1e-6:
                        self.current_g_value_ms2 = new_g
                        logger.info(f"User changed g value to: {self.current_g_value_ms2} m/s^2. Re-fitting advised.")
                else: 
                    self.g_input_lineedit.setText(str(self.current_g_value_ms2))
            except ValueError: 
                self.g_input_lineedit.setText(str(self.current_g_value_ms2))

    @QtCore.Slot()
    def _on_save_analysis_button_clicked(self) -> None:
        if self.track_id is not None:
            current_state = self._get_current_analysis_state_dict()
            if self.track_element_copy and 'analysis_state' in self.track_element_copy:
                 original_is_applied = self.track_element_copy['analysis_state'].get('fit_results', {}).get('is_applied_to_project', False)
                 current_state['fit_results']['is_applied_to_project'] = original_is_applied
            else:
                 current_state['fit_results']['is_applied_to_project'] = False
            self.analysisSettingsToBeSaved.emit(self.track_id, current_state)
            logger.info(f"Emitted analysisSettingsToBeSaved for Track ID {self.track_id}.")
        else:
            logger.warning("Save Analysis clicked but no track_id is set.")

    @QtCore.Slot()
    def _on_apply_scale_button_clicked(self) -> None:
        if self.track_id is not None and self.fit_derived_scale_m_per_px is not None and self.fit_derived_scale_m_per_px > 0:
            self.scaleToBeApplied.emit(self.track_id, self.fit_derived_scale_m_per_px)
            logger.info(f"Emitted scaleToBeApplied for Track ID {self.track_id} with scale {self.fit_derived_scale_m_per_px}.")
        else:
            logger.warning("Apply Scale clicked, but no valid derived scale or track_id.")
            QtWidgets.QMessageBox.warning(self, "Apply Scale Error", "No valid scale has been derived from the current fit for this track.")

    @QtCore.Slot()
    def _on_reset_fit_settings_button_clicked(self) -> None:
        logger.info(f"Reset Fit Settings button clicked for Track ID {self.track_id}.")
        if not self.track_element_copy or not self.plot_data_y_vs_t:
            return

        self.included_point_indices_mask = [True] * len(self.plot_data_y_vs_t)
        
        times_s_all = np.array([item[0] for item in self.plot_data_y_vs_t])
        if len(times_s_all) > 0:
            self.fit_time_range_s = (min(times_s_all), max(times_s_all))
            if self.linear_region_item:
                self.linear_region_item.setRegion(self.fit_time_range_s)
        else:
            self.fit_time_range_s = None
            if self.linear_region_item:
                self.linear_region_item.setRegion((0,0))
                self.linear_region_item.setVisible(False)
        
        self._update_point_visuals()
        self._fit_parabola()
        logger.debug("Fit settings reset and re-fitted.")
        
    @QtCore.Slot(object, list)
    def _on_point_clicked(self, scatter_plot_item: pg.ScatterPlotItem, clicked_points: List[pg.SpotItem]) -> None:
        if not clicked_points: return
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if not (modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier): return

        clicked_spot = clicked_points[0]
        point_data_index = clicked_spot.data()

        if point_data_index is not None and 0 <= point_data_index < len(self.included_point_indices_mask):
            self.included_point_indices_mask[point_data_index] = not self.included_point_indices_mask[point_data_index]
            self._update_point_visuals()
            self._fit_parabola()
        else:
            logger.warning(f"Clicked point has invalid data index: {point_data_index}")

    @QtCore.Slot(object)
    def _on_time_range_changed(self, region_item: pg.LinearRegionItem) -> None:
        if self.linear_region_item is None: return
        current_region = self.linear_region_item.getRegion()
        if self.fit_time_range_s is None or \
           abs(current_region[0] - self.fit_time_range_s[0]) > 1e-6 or \
           abs(current_region[1] - self.fit_time_range_s[1]) > 1e-6:
            self.fit_time_range_s = (current_region[0], current_region[1])
            logger.info(f"Fit time range changed to: {self.fit_time_range_s[0]:.3f}s - {self.fit_time_range_s[1]:.3f}s")
            self._fit_parabola()

    def clear_and_disable(self) -> None:
        logger.info("SingleTrackFitWidget: Clearing data and disabling.")
        self.track_id = None
        self.track_element_copy = None
        self.plot_data_y_vs_t.clear()
        self.all_points_original_indices.clear()
        self.raw_frame_indices_for_plotted_points.clear()
        self.included_point_indices_mask.clear()
        self.fit_time_range_s = None
        self.fit_coeffs = None
        self.fit_r_squared = None
        self.fit_derived_scale_m_per_px = None
        self.current_g_value_ms2 = DEFAULT_ANALYSIS_STATE['fit_settings']['g_value_ms2']

        if self.track_id_label: self.track_id_label.setText("<b>Track ID: N/A</b>")
        if self.g_input_lineedit: self.g_input_lineedit.setText(str(self.current_g_value_ms2))

        if self.plot_widget:
            if self.scatter_plot_item: self.scatter_plot_item.clear()
            if self.fitted_curve_item: self.fitted_curve_item.clear()
            if self.linear_region_item: self.linear_region_item.setRegion((0,0)); self.linear_region_item.setVisible(False)
            self.plot_widget.setTitle("No track selected for analysis")
            # --- BEGIN MODIFICATION ---
            self.plot_widget.autoRange(padding=0.05) # Ensure view resets
            # --- END MODIFICATION ---


        if self.coeff_A_label: self.coeff_A_label.setText("N/A")
        if self.derived_scale_label: self.derived_scale_label.setText("N/A")
        if self.r_squared_label: self.r_squared_label.setText("N/A")

        if self.g_input_lineedit: self.g_input_lineedit.setEnabled(False)
        if self.refit_button: self.refit_button.setEnabled(False)
        if self.save_analysis_button: self.save_analysis_button.setEnabled(False)
        if self.apply_scale_button: self.apply_scale_button.setEnabled(False)
        if self.reset_fit_settings_button: self.reset_fit_settings_button.setEnabled(False)
        
        self.setEnabled(False)