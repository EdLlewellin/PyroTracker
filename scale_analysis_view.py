# scale_analysis_view.py
"""
Provides the ScaleAnalysisView class, a QWidget for displaying multi-track
y(t) data, analysis summaries, and fitting controls.
"""
import logging
import copy
import math
import numpy as np
from typing import TYPE_CHECKING, Optional, Dict, List

from PySide6 import QtCore, QtGui, QtWidgets

from element_manager import ElementType, DEFAULT_ANALYSIS_STATE

# --- BEGIN MODIFICATION: Import SingleTrackFitWidget ---
from single_track_fit_widget import SingleTrackFitWidget # [cite: 98]
# --- END MODIFICATION ---

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    pg = None
    PYQTGRAPH_AVAILABLE = False
    logging.warning(
        "PyQtGraph not found. Scale analysis plotting will be basic or unavailable."
    )

if TYPE_CHECKING:
    from main_window import MainWindow

logger = logging.getLogger(__name__)

class CustomZoomViewBox(pg.ViewBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._default_mouse_mode = self.PanMode
        self.setMouseMode(self._default_mouse_mode)
        self._is_temp_rect_mode = False

    def wheelEvent(self, ev, axis=None):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        zoom_factor_increment = 1.1
        if ev.delta() < 0:
            s = zoom_factor_increment
        else:
            s = 1.0 / zoom_factor_increment
        center = self.mapToView(ev.pos())
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.scaleBy((s, 1), center=center)
        elif modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:
            self.scaleBy((1, s), center=center)
        else:
            self.scaleBy((s, s), center=center)
        ev.accept()

    def mousePressEvent(self, ev):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if ev.button() == QtCore.Qt.MouseButton.LeftButton and \
           modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.setMouseMode(self.RectMode)
            self._is_temp_rect_mode = True
            logger.debug("CustomZoomViewBox: Switched to RectMode for Ctrl+Drag.")
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if self._is_temp_rect_mode:
            if ev.button() == QtCore.Qt.MouseButton.LeftButton or not ev.buttons():
                self.setMouseMode(self._default_mouse_mode)
                self._is_temp_rect_mode = False
                logger.debug("CustomZoomViewBox: Reverted to PanMode after Ctrl+Drag.")


class ScaleAnalysisView(QtWidgets.QWidget):
    def __init__(self, main_window_ref: 'MainWindow', parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.main_window_ref = main_window_ref
        
        self.main_yt_plot: Optional[pg.PlotWidget] = None
        self.analysis_tracks_table: Optional[QtWidgets.QTableWidget] = None
        # --- BEGIN MODIFICATION: Add attribute for SingleTrackFitWidget ---
        self.single_track_fit_widget: Optional[SingleTrackFitWidget] = None # [cite: 98]
        # --- END MODIFICATION ---

        self.track_plot_items: Dict[int, Dict[str, pg.PlotDataItem | pg.ScatterPlotItem]] = {}
        self.current_selected_track_id_for_plot: Optional[int] = None
        
        self._plot_colors: List[QtGui.QColor] = [
            QtGui.QColor("blue"), QtGui.QColor("red"), QtGui.QColor("green"),
            QtGui.QColor("purple"), QtGui.QColor("darkorange"), QtGui.QColor("teal"),
            QtGui.QColor("brown"), QtGui.QColor("darkgoldenrod"), QtGui.QColor("magenta"),
            QtGui.QColor("darkcyan"), QtGui.QColor("darkblue"), QtGui.QColor("darkred"),
            QtGui.QColor("darkgreen"), QtGui.QColor("darkmagenta"), QtGui.QColor("olive"),
            QtGui.QColor("maroon"), QtGui.QColor("indigo"), QtGui.QColor(128, 0, 128),
            QtGui.QColor(0, 100, 0), QtGui.QColor(139, 69, 19)
        ]

        self._setup_ui()
        self._connect_signals() # Added a separate method for signal connections

        if self.main_window_ref and self.main_window_ref.element_manager:
            self.main_window_ref.element_manager.elementListChanged.connect(self.populate_tracks_table)
            logger.debug("ScaleAnalysisView: Connected elementListChanged to populate_tracks_table.")
        else:
            logger.warning("ScaleAnalysisView: Could not connect elementListChanged; MainWindow or ElementManager not available.")

        logger.info("ScaleAnalysisView initialized.")

    def _setup_ui(self) -> None:
        main_layout = QtWidgets.QHBoxLayout(self)

        left_main_area_widget = QtWidgets.QWidget()
        left_main_area_layout = QtWidgets.QVBoxLayout(left_main_area_widget)
        left_main_area_layout.setContentsMargins(0, 0, 0, 0)
        left_main_area_layout.setSpacing(5)

        if PYQTGRAPH_AVAILABLE and pg is not None:
            view_box = CustomZoomViewBox()
            self.main_yt_plot = pg.PlotWidget(viewBox=view_box)
            self.main_yt_plot.setBackground('w')
            self.main_yt_plot.showGrid(x=True, y=True, alpha=0.3)
            self.main_yt_plot.setLabel('left', "Vertical Position (px, bottom-up)")
            self.main_yt_plot.setLabel('bottom', "Time (s)")
            if self.main_yt_plot.getViewBox():
                 self.main_yt_plot.getViewBox().setAspectLocked(lock=False)
            left_main_area_layout.addWidget(self.main_yt_plot, stretch=3)
        else:
            self.main_yt_plot_placeholder = QtWidgets.QLabel("PyQtGraph is not available. Main y(t) plot cannot be displayed.")
            self.main_yt_plot_placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.main_yt_plot_placeholder.setStyleSheet("background-color: lightGray;")
            left_main_area_layout.addWidget(self.main_yt_plot_placeholder, stretch=3)

        self.ancillary_global_groupbox = QtWidgets.QGroupBox("Diagnostic Plots & Global Scale")
        ancillary_global_layout = QtWidgets.QVBoxLayout(self.ancillary_global_groupbox)
        placeholder_label_ancillary = QtWidgets.QLabel("Ancillary plots and global scale results will appear here.")
        placeholder_label_ancillary.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        ancillary_global_layout.addWidget(placeholder_label_ancillary)
        self.ancillary_global_groupbox.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        left_main_area_layout.addWidget(self.ancillary_global_groupbox, stretch=1)
        main_layout.addWidget(left_main_area_widget, stretch=3)

        right_panel_widget = QtWidgets.QWidget()
        right_panel_layout = QtWidgets.QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(5,0,0,0)
        right_panel_layout.setSpacing(5)
        
        self.analysis_tracks_table = QtWidgets.QTableWidget()
        self._setup_analysis_tracks_table()
        right_panel_layout.addWidget(self.analysis_tracks_table, stretch=2)

        self.single_track_groupbox = QtWidgets.QGroupBox("Selected Track Details & Fit Controls") # [cite: 19]
        single_track_outer_layout = QtWidgets.QVBoxLayout(self.single_track_groupbox) # Use an outer layout for margins
        single_track_outer_layout.setContentsMargins(6,6,6,6) # Standard group box margins
        single_track_outer_layout.setSpacing(0) # Outer layout has no spacing, inner widget handles it

        # --- BEGIN MODIFICATION: Instantiate and add SingleTrackFitWidget ---
        self.single_track_fit_widget = SingleTrackFitWidget(main_window_ref=self.main_window_ref, parent_view=self) # [cite: 98]
        # Replace the placeholder label with the actual widget
        # Remove old placeholder_label_single_track if it was added to single_track_layout
        # Check if single_track_groupbox already has a layout; if so, add widget to it.
        # If not, set a new layout and add. For robustness:
        existing_layout = self.single_track_groupbox.layout()
        if existing_layout:
            # Clear existing items (e.g., the placeholder label)
            while existing_layout.count():
                child = existing_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            existing_layout.addWidget(self.single_track_fit_widget) # [cite: 99]
        else: # Should not happen if _setup_ui followed plan, but defensive
            new_single_track_layout = QtWidgets.QVBoxLayout()
            new_single_track_layout.addWidget(self.single_track_fit_widget)
            self.single_track_groupbox.setLayout(new_single_track_layout)
        # --- END MODIFICATION ---
        
        self.single_track_groupbox.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        right_panel_layout.addWidget(self.single_track_groupbox, stretch=3)
        main_layout.addWidget(right_panel_widget, stretch=1)

    # --- BEGIN MODIFICATION: New method for connecting signals ---
    def _connect_signals(self) -> None:
        """Connects signals for UI elements within this view."""
        if self.analysis_tracks_table:
            self.analysis_tracks_table.itemSelectionChanged.connect(self._on_analysis_table_selection_changed)
        
        if self.single_track_fit_widget: # [cite: 107]
            self.single_track_fit_widget.analysisSettingsToBeSaved.connect(self._handle_save_track_analysis)
            self.single_track_fit_widget.scaleToBeApplied.connect(self._handle_apply_track_scale)
    # --- END MODIFICATION ---

    def _setup_analysis_tracks_table(self) -> None:
        if not self.analysis_tracks_table:
            return
        column_headers = ["ID", "Fit Pts", "Fit Scale (m/px)", "R²"]
        self.analysis_tracks_table.setColumnCount(len(column_headers))
        self.analysis_tracks_table.setHorizontalHeaderLabels(column_headers)
        self.analysis_tracks_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.analysis_tracks_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.analysis_tracks_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.analysis_tracks_table.setAlternatingRowColors(True)
        self.analysis_tracks_table.verticalHeader().setVisible(False)
        header = self.analysis_tracks_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.analysis_tracks_table.setColumnWidth(1, 70)

    def _get_plot_color_for_track(self, track_id: int) -> QtGui.QColor:
        if not self._plot_colors:
            return QtGui.QColor("black")
        color = self._plot_colors[track_id % len(self._plot_colors)]
        return color

    def _update_main_yt_plot(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not self.main_yt_plot:
            return
        logger.debug(f"ScaleAnalysisView: Updating main_yt_plot. Selected track for highlight: {self.current_selected_track_id_for_plot}")
        self.main_yt_plot.clear()
        self.track_plot_items.clear()

        if not (self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler and self.main_window_ref.video_handler.is_loaded):
            logger.warning("Cannot update main_yt_plot: ElementManager or VideoHandler not available/loaded.")
            self.main_yt_plot.setTitle("No video loaded or data available")
            return
        
        video_height = self.main_window_ref.video_handler.frame_height
        if video_height <= 0:
            logger.warning("Cannot plot y(t): Video height is invalid.")
            self.main_yt_plot.setTitle("Invalid video height for y(t) plot")
            return

        tracks = [el for el in self.main_window_ref.element_manager.elements if el.get('type') == ElementType.TRACK]
        if not tracks:
            self.main_yt_plot.setTitle("No tracks to plot")
            return
        
        self.main_yt_plot.setTitle("Tracks y(t) - Select track in table to highlight")

        for track_element in tracks:
            track_id = track_element.get('id')
            track_data = track_element.get('data', [])
            analysis_state = track_element.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))

            if not track_data: continue

            times_s = np.array([p[1] / 1000.0 for p in track_data])
            y_pixels_tl = np.array([p[3] for p in track_data])
            y_pixels_plot = video_height - y_pixels_tl

            track_color = self._get_plot_color_for_track(track_id)
            is_selected_track = (track_id == self.current_selected_track_id_for_plot)

            symbol_size = 10 if is_selected_track else 7
            symbol_brush = track_color
            if not is_selected_track:
                dimmed_color = QtGui.QColor(track_color)
                dimmed_color.setAlpha(100)
                symbol_brush = dimmed_color
            
            scatter_item = pg.ScatterPlotItem(x=times_s, y=y_pixels_plot, symbol='o', size=symbol_size,
                                              brush=symbol_brush, pen=None, data=track_id)
            scatter_item.sigClicked.connect(self._on_main_yt_plot_point_clicked)
            self.main_yt_plot.addItem(scatter_item)
            if track_id not in self.track_plot_items: self.track_plot_items[track_id] = {}
            self.track_plot_items[track_id]['scatter'] = scatter_item

            fit_results = analysis_state.get('fit_results', {})
            coeffs = fit_results.get('coefficients_poly2')
            if coeffs and len(coeffs) == 3:
                fit_settings = analysis_state.get('fit_settings', {})
                time_range_s_fit = fit_settings.get('time_range_s')
                
                t_for_curve_plot: Optional[np.ndarray] = None
                if time_range_s_fit:
                    t_min, t_max = time_range_s_fit
                    if t_min < t_max: t_for_curve_plot = np.linspace(t_min, t_max, 100)
                else:
                    if len(times_s) > 1: t_for_curve_plot = np.linspace(min(times_s), max(times_s), 100)
                    elif len(times_s) == 1: t_for_curve_plot = np.array([times_s[0]])

                if t_for_curve_plot is not None and len(t_for_curve_plot) > 0:
                    y_curve = np.polyval(coeffs, t_for_curve_plot)
                    curve_pen_width = 3 if is_selected_track else 1.5
                    curve_color = QtGui.QColor(track_color)
                    if not is_selected_track: curve_color.setAlpha(120)
                    fit_curve_item = pg.PlotDataItem(x=t_for_curve_plot, y=y_curve, pen=pg.mkPen(curve_color, width=curve_pen_width))
                    self.main_yt_plot.addItem(fit_curve_item)
                    self.track_plot_items[track_id]['fit_curve'] = fit_curve_item
        logger.debug("Main y(t) plot updated with all tracks.")

    def populate_tracks_table(self) -> None:
        logger.debug("ScaleAnalysisView: populate_tracks_table called.")
        if not self.analysis_tracks_table:
            logger.warning("analysis_tracks_table is None, cannot populate.")
            return
        self.analysis_tracks_table.setRowCount(0)
        if not PYQTGRAPH_AVAILABLE: return
        if not (self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler):
            logger.warning("ElementManager or VideoHandler not available in populate_tracks_table.")
            return

        tracks = [el for el in self.main_window_ref.element_manager.elements if el.get('type') == ElementType.TRACK]
        self.analysis_tracks_table.setRowCount(len(tracks))

        for row_idx, track_element in enumerate(tracks):
            track_id = track_element.get('id', "N/A")
            analysis_state = track_element.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
            fit_settings = analysis_state.get('fit_settings', DEFAULT_ANALYSIS_STATE['fit_settings'])
            fit_results = analysis_state.get('fit_results', DEFAULT_ANALYSIS_STATE['fit_results'])
            track_data = track_element.get('data', [])
            total_points_in_track = len(track_data)
            fit_pts_str = "N/A"

            if fit_results.get('coefficients_poly2') is not None and track_data:
                excluded_frames = fit_settings.get('excluded_point_frames', [])
                time_range_s = fit_settings.get('time_range_s', None)
                potentially_fittable_points = [p for p in track_data if p[0] not in excluded_frames]
                num_fitted_pts = 0
                if time_range_s and self.main_window_ref.video_handler.fps > 0:
                    min_t_fit, max_t_fit = time_range_s
                    points_in_time_range_and_not_excluded = [p for p in potentially_fittable_points if min_t_fit <= (p[1] / 1000.0) <= max_t_fit]
                    num_fitted_pts = len(points_in_time_range_and_not_excluded)
                else:
                    num_fitted_pts = len(potentially_fittable_points)
                fit_pts_str = f"{num_fitted_pts}/{total_points_in_track}"
            elif track_data: fit_pts_str = f"-/{total_points_in_track}"
            else: fit_pts_str = "-/0"
            
            r_squared = fit_results.get('r_squared')
            r_squared_str = f"{r_squared:.4f}" if r_squared is not None else "N/A"
            derived_scale = fit_results.get('derived_scale_m_per_px')
            fit_scale_str = f"{derived_scale:.6g}" if derived_scale is not None else "N/A"

            self.analysis_tracks_table.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(str(track_id)))
            self.analysis_tracks_table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(fit_pts_str))
            self.analysis_tracks_table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(fit_scale_str))
            self.analysis_tracks_table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(r_squared_str))
            
            id_item = self.analysis_tracks_table.item(row_idx, 0)
            if id_item: id_item.setData(QtCore.Qt.ItemDataRole.UserRole, track_id)

        for r in range(self.analysis_tracks_table.rowCount()):
            for c_idx, alignment in [(0, QtCore.Qt.AlignmentFlag.AlignCenter), 
                                     (1, QtCore.Qt.AlignmentFlag.AlignCenter), 
                                     (2, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter), 
                                     (3, QtCore.Qt.AlignmentFlag.AlignCenter)]:
                item = self.analysis_tracks_table.item(r, c_idx)
                if item: item.setTextAlignment(alignment)
        
        logger.info(f"Populated analysis_tracks_table with {len(tracks)} tracks.")
        self._update_main_yt_plot()
        if self.main_yt_plot and (self.track_plot_items or not tracks):
            if not tracks: self.main_yt_plot.setTitle("No tracks to plot")
            self.main_yt_plot.autoRange(padding=0.05)
            logger.debug("Called autoRange on main_yt_plot after populating tracks table.")

    def update_on_project_or_video_change(self, is_project_or_video_loaded: bool) -> None:
        logger.debug(f"ScaleAnalysisView: update_on_project_or_video_change called. Loaded: {is_project_or_video_loaded}")
        if is_project_or_video_loaded:
            self.populate_tracks_table()
        else:
            if self.analysis_tracks_table: self.analysis_tracks_table.setRowCount(0)
            if PYQTGRAPH_AVAILABLE and hasattr(self, 'main_yt_plot') and self.main_yt_plot is not None:
                self.main_yt_plot.clear(); self.main_yt_plot.setTitle("")
            self.track_plot_items.clear()
            self.current_selected_track_id_for_plot = None
            # --- BEGIN MODIFICATION: Clear SingleTrackFitWidget ---
            if self.single_track_fit_widget: # [cite: 100] (implicitly, as part of resetting the view)
                self.single_track_fit_widget.clear_and_disable()
            # --- END MODIFICATION ---
        self.setEnabled(is_project_or_video_loaded and PYQTGRAPH_AVAILABLE)

    @QtCore.Slot()
    def _on_analysis_table_selection_changed(self) -> None: # [cite: 101]
        if not self.analysis_tracks_table: return
        selected_items = self.analysis_tracks_table.selectedItems()
        newly_selected_track_id: Optional[int] = None

        if selected_items:
            selected_row = self.analysis_tracks_table.row(selected_items[0])
            id_item = self.analysis_tracks_table.item(selected_row, 0)
            if id_item:
                track_id_data = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(track_id_data, int):
                    newly_selected_track_id = track_id_data
        
        if self.current_selected_track_id_for_plot != newly_selected_track_id:
            self.current_selected_track_id_for_plot = newly_selected_track_id
            logger.debug(f"ScaleAnalysisView: Selected track for plot highlight changed to ID: {self.current_selected_track_id_for_plot}")
            self._update_main_yt_plot() 

        # --- BEGIN MODIFICATION: Load data into SingleTrackFitWidget ---
        if self.single_track_fit_widget and self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler: # [cite: 101]
            if newly_selected_track_id is not None:
                track_to_load = None
                for el in self.main_window_ref.element_manager.elements:
                    if el.get('id') == newly_selected_track_id and el.get('type') == ElementType.TRACK:
                        track_to_load = el # [cite: 102]
                        break
                if track_to_load:
                    self.single_track_fit_widget.load_track_data( # [cite: 102]
                        copy.deepcopy(track_to_load), # Pass a copy
                        self.main_window_ref.video_handler.fps,
                        self.main_window_ref.video_handler.frame_height
                    )
                else: # Should not happen if table is synced with element_manager
                    self.single_track_fit_widget.clear_and_disable()
            else: # No track selected in table
                self.single_track_fit_widget.clear_and_disable() # [cite: 100]
        # --- END MODIFICATION ---


    @QtCore.Slot(object, list)
    def _on_main_yt_plot_point_clicked(self, scatter_plot_item: pg.ScatterPlotItem, spot_items: List[pg.SpotItem]) -> None:
        if not spot_items or not self.analysis_tracks_table: return
        clicked_spot_data = spot_items[0].data()
        if not isinstance(clicked_spot_data, int):
            logger.warning(f"Clicked spot has non-integer data: {clicked_spot_data}")
            return
        clicked_track_id = clicked_spot_data
        logger.debug(f"Point clicked on main_yt_plot for track ID: {clicked_track_id}")
        for r in range(self.analysis_tracks_table.rowCount()):
            id_item = self.analysis_tracks_table.item(r, 0)
            if id_item and id_item.data(QtCore.Qt.ItemDataRole.UserRole) == clicked_track_id:
                if not self.analysis_tracks_table.item(r,0).isSelected():
                    self.analysis_tracks_table.selectRow(r)
                break
    
    # --- BEGIN MODIFICATION: Slots to handle signals from SingleTrackFitWidget ---
    @QtCore.Slot(int, dict)
    def _handle_save_track_analysis(self, track_id: int, analysis_state_dict: Dict) -> None: # [cite: 103]
        logger.info(f"ScaleAnalysisView: Received request to save analysis for Track ID {track_id}.")
        if self.main_window_ref and self.main_window_ref.element_manager:
            success = self.main_window_ref.element_manager.update_track_analysis_state(track_id, analysis_state_dict) # [cite: 103]
            if success:
                logger.info(f"Analysis state for Track ID {track_id} updated in ElementManager.")
                self.populate_tracks_table() # [cite: 104]
                self._update_main_yt_plot()  # [cite: 104]
                # Optionally, provide user feedback via status bar or message box
                if self.main_window_ref.statusBar():
                    self.main_window_ref.statusBar().showMessage(f"Analysis for Track {track_id} saved.", 3000)
            else:
                logger.error(f"Failed to update analysis state for Track ID {track_id} in ElementManager.")
                QtWidgets.QMessageBox.warning(self, "Save Error", f"Could not save analysis for Track {track_id}.")
        else:
            logger.error("Cannot save track analysis: MainWindow or ElementManager not available.")

    @QtCore.Slot(int, float)
    def _handle_apply_track_scale(self, track_id: int, derived_scale: float) -> None: # [cite: 103]
        logger.info(f"ScaleAnalysisView: Received request to apply scale {derived_scale:.6g} m/px from Track ID {track_id}.")
        if not (self.main_window_ref and self.main_window_ref.scale_manager and self.main_window_ref.element_manager):
            logger.error("Cannot apply track scale: Core managers not available.")
            return

        reply = QtWidgets.QMessageBox.question( # [cite: 105]
            self, "Apply Scale to Project",
            f"Apply derived scale ({derived_scale:.6g} m/px) from Track {track_id} to the entire project?\n"
            "This will override any existing project scale and clear any manually drawn scale line.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            scale_source_desc = f"Track {track_id} Parabolic Fit" # More details could be added from fit_settings['g_value_ms2']
            self.main_window_ref.scale_manager.set_scale(derived_scale, source_description=scale_source_desc) # [cite: 105]
            
            # Update is_applied_to_project flags for all tracks [cite: 106]
            for el in self.main_window_ref.element_manager.elements:
                if el.get('type') == ElementType.TRACK:
                    el_id = el.get('id')
                    current_analysis_state = el.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
                    current_analysis_state['fit_results']['is_applied_to_project'] = (el_id == track_id)
                    self.main_window_ref.element_manager.update_track_analysis_state(el_id, current_analysis_state)
            
            self.populate_tracks_table() # [cite: 107]
            self._update_main_yt_plot() # [cite: 107]
            if self.main_window_ref.statusBar():
                self.main_window_ref.statusBar().showMessage(f"Scale from Track {track_id} applied to project.", 5000)
        else:
            logger.info("User cancelled applying scale from track to project.")
    # --- END MODIFICATION ---