# scale_analysis_view.py
"""
Provides the ScaleAnalysisView class, a QWidget for displaying multi-track
y(t) data, analysis summaries, and fitting controls.
"""
import logging
import copy 
import math # Added for Phase 2 custom zoom
import numpy as np
from typing import TYPE_CHECKING, Optional, Dict, List 

from PySide6 import QtCore, QtGui, QtWidgets

from element_manager import ElementType, DEFAULT_ANALYSIS_STATE

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
        # Requirement 2: Default drag to PanMode
        self._default_mouse_mode = self.PanMode # Store default mode
        self.setMouseMode(self._default_mouse_mode) # Set PanMode as default
        self._is_temp_rect_mode = False # Flag to track if RectMode is temporarily active

    def wheelEvent(self, ev, axis=None): # ev is QGraphicsSceneWheelEvent
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        
        zoom_factor_increment = 1.1
        # User confirmed ev.delta() < 0 is zoom in for them
        if ev.delta() < 0: 
            s = zoom_factor_increment
        else: 
            s = 1.0 / zoom_factor_increment
        
        center = self.mapToView(ev.pos()) 

        # --- BEGIN MODIFICATION: Swap default scroll and Ctrl+scroll behavior ---
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier: # Ctrl + Wheel: Zoom X only
            self.scaleBy((s, 1), center=center)
        elif modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier: # Shift + Wheel: Zoom Y only
            self.scaleBy((1, s), center=center)
        else: # Default wheel: Zoom X and Y
            self.scaleBy((s, s), center=center)
        # --- END MODIFICATION ---
        ev.accept()

    def mousePressEvent(self, ev):
        # Requirement 2: Ctrl+Drag for Zoom Box
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if ev.button() == QtCore.Qt.MouseButton.LeftButton and \
           modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            # If Ctrl is pressed with Left Button, switch to RectMode for this drag
            self.setMouseMode(self.RectMode)
            self._is_temp_rect_mode = True
            logger.debug("CustomZoomViewBox: Switched to RectMode for Ctrl+Drag.")
        
        super().mousePressEvent(ev) # Call super to handle the press event with the current mode

    def mouseReleaseEvent(self, ev):
        # Call super first to complete any ongoing action (like RectMode zoom)
        super().mouseReleaseEvent(ev)

        # Requirement 2: Revert to PanMode if temporary RectMode was active
        if self._is_temp_rect_mode:
            if ev.button() == QtCore.Qt.MouseButton.LeftButton or not ev.buttons(): # Check if left button was released or no buttons pressed
                self.setMouseMode(self._default_mouse_mode) # Revert to default PanMode
                self._is_temp_rect_mode = False
                logger.debug("CustomZoomViewBox: Reverted to PanMode after Ctrl+Drag.")

    # mouseDragEvent is not overridden here; we rely on super().mouseDragEvent
    # to respect the mouseMode set in mousePressEvent.


class ScaleAnalysisView(QtWidgets.QWidget):
    """
    A QWidget that provides an interface for analyzing multiple tracks,
    viewing their y(t) data, and deriving scale via parabolic fits.
    """

    def __init__(self, main_window_ref: 'MainWindow', parent: Optional[QtWidgets.QWidget] = None) -> None: 
        super().__init__(parent)
        self.main_window_ref = main_window_ref 
        
        self.main_yt_plot: Optional[pg.PlotWidget] = None
        self.analysis_tracks_table: Optional[QtWidgets.QTableWidget] = None

        self.track_plot_items: Dict[int, Dict[str, pg.PlotDataItem | pg.ScatterPlotItem]] = {} # [cite: 54]
        self.current_selected_track_id_for_plot: Optional[int] = None # [cite: 55]
        
        # Predefined list of colors for track plots
        self._plot_colors: List[QtGui.QColor] = [
            QtGui.QColor("blue"),
            QtGui.QColor("red"),
            QtGui.QColor("green"), # Standard green can sometimes be light; darkgreen is an alternative
            QtGui.QColor("purple"),
            QtGui.QColor("darkorange"), # Darker than 'orange'
            QtGui.QColor("teal"),       # Good dark cyan-like color
            QtGui.QColor("brown"),
            QtGui.QColor("darkgoldenrod"), # A darker, more visible yellow/gold
            QtGui.QColor("magenta"),    # Can be okay, darkMagenta is darker
            QtGui.QColor("darkcyan"),
            QtGui.QColor("darkblue"),
            QtGui.QColor("darkred"),
            QtGui.QColor("darkgreen"),
            QtGui.QColor("darkmagenta"),
            QtGui.QColor("olive"),
            QtGui.QColor("maroon"),
            QtGui.QColor("indigo"),      # Dark purple-blue
            QtGui.QColor(128, 0, 128), # Explicit purple (if "purple" is too light)
            QtGui.QColor(0, 100, 0),   # Explicit dark green
            QtGui.QColor(139, 69, 19)  # SaddleBrown
        ]

        self._setup_ui()

        if self.main_window_ref and self.main_window_ref.element_manager:
            self.main_window_ref.element_manager.elementListChanged.connect(self.populate_tracks_table)
            logger.debug("ScaleAnalysisView: Connected elementListChanged to populate_tracks_table.")
        else:
            logger.warning("ScaleAnalysisView: Could not connect elementListChanged; MainWindow or ElementManager not available.")

        logger.info("ScaleAnalysisView initialized.")

    def _setup_ui(self) -> None: 
        """Sets up the main UI layout and sub-widgets for the scale analysis view."""
        main_layout = QtWidgets.QHBoxLayout(self) 

        left_main_area_widget = QtWidgets.QWidget()
        left_main_area_layout = QtWidgets.QVBoxLayout(left_main_area_widget) 
        left_main_area_layout.setContentsMargins(0, 0, 0, 0)
        left_main_area_layout.setSpacing(5)

        if PYQTGRAPH_AVAILABLE and pg is not None:
            # --- BEGIN MODIFICATION: Use CustomZoomViewBox ---
            view_box = CustomZoomViewBox() #
            self.main_yt_plot = pg.PlotWidget(viewBox=view_box) #
            # --- END MODIFICATION ---
            self.main_yt_plot.setBackground('w') 
            self.main_yt_plot.showGrid(x=True, y=True, alpha=0.3) 
            self.main_yt_plot.setLabel('left', "Vertical Position (px, bottom-up)") 
            self.main_yt_plot.setLabel('bottom', "Time (s)") 
            if self.main_yt_plot.getViewBox():
                 self.main_yt_plot.getViewBox().setAspectLocked(lock=False) # [cite: 55]
            left_main_area_layout.addWidget(self.main_yt_plot, stretch=3) 
        else:
            self.main_yt_plot_placeholder = QtWidgets.QLabel(
                "PyQtGraph is not available. Main y(t) plot cannot be displayed."
            )
            self.main_yt_plot_placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.main_yt_plot_placeholder.setStyleSheet("background-color: lightGray;")
            left_main_area_layout.addWidget(self.main_yt_plot_placeholder, stretch=3)

        self.ancillary_global_groupbox = QtWidgets.QGroupBox("Diagnostic Plots & Global Scale") 
        ancillary_global_layout = QtWidgets.QVBoxLayout(self.ancillary_global_groupbox)
        placeholder_label_ancillary = QtWidgets.QLabel(
            "Ancillary plots and global scale results will appear here." 
        )
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

        self.single_track_groupbox = QtWidgets.QGroupBox("Selected Track Details & Fit Controls") 
        single_track_layout = QtWidgets.QVBoxLayout(self.single_track_groupbox)
        placeholder_label_single_track = QtWidgets.QLabel(
            "Select a track from the table to view/edit its analysis." 
        )
        placeholder_label_single_track.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        single_track_layout.addWidget(placeholder_label_single_track)
        self.single_track_groupbox.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        right_panel_layout.addWidget(self.single_track_groupbox, stretch=3) 

        main_layout.addWidget(right_panel_widget, stretch=1)

        if self.analysis_tracks_table:
            self.analysis_tracks_table.itemSelectionChanged.connect(self._on_analysis_table_selection_changed) 

    def _setup_analysis_tracks_table(self) -> None:
        """Configures the properties and columns of the analysis_tracks_table."""
        if not self.analysis_tracks_table:
            return
            
        column_headers = [ 
            "ID", "Fit Pts", "Fit Scale (m/px)", "R²"
        ]
        self.analysis_tracks_table.setColumnCount(len(column_headers))
        self.analysis_tracks_table.setHorizontalHeaderLabels(column_headers)

        self.analysis_tracks_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers) 
        self.analysis_tracks_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows) 
        self.analysis_tracks_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection) 
        self.analysis_tracks_table.setAlternatingRowColors(True) 
        self.analysis_tracks_table.verticalHeader().setVisible(False) 
        
        header = self.analysis_tracks_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # ID
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)     # Fit Pts
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)         # Fit Scale (m/px)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # R²
        
        self.analysis_tracks_table.setColumnWidth(1, 70)

    # --- BEGIN MODIFICATION: New method for Phase 2 ---
    def _get_plot_color_for_track(self, track_id: int) -> QtGui.QColor: # [cite: 62]
        """Gets a consistent color for a track based on its ID or cycles through predefined colors."""
        if not self._plot_colors: # Fallback if list is empty
            return QtGui.QColor("black")
        # Simple cycling for now, could be more sophisticated (e.g., hash track_id)
        color = self._plot_colors[track_id % len(self._plot_colors)]
        return color
    # --- END MODIFICATION ---

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

            if not track_data:
                continue

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
            
            scatter_item = pg.ScatterPlotItem(
                x=times_s, y=y_pixels_plot,
                symbol='o', size=symbol_size,
                brush=symbol_brush, pen=None,
                data=track_id 
            )
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
                    if t_min < t_max:
                        t_for_curve_plot = np.linspace(t_min, t_max, 100)
                else: 
                    if len(times_s) > 1:
                        t_for_curve_plot = np.linspace(min(times_s), max(times_s), 100)
                    elif len(times_s) == 1:
                        t_for_curve_plot = np.array([times_s[0]])

                if t_for_curve_plot is not None and len(t_for_curve_plot) > 0:
                    y_curve = np.polyval(coeffs, t_for_curve_plot) 
                    
                    curve_pen_width = 3 if is_selected_track else 1.5 
                    curve_color = QtGui.QColor(track_color)
                    if not is_selected_track: curve_color.setAlpha(120)

                    fit_curve_item = pg.PlotDataItem(x=t_for_curve_plot, y=y_curve, pen=pg.mkPen(curve_color, width=curve_pen_width)) 
                    self.main_yt_plot.addItem(fit_curve_item) 
                    self.track_plot_items[track_id]['fit_curve'] = fit_curve_item 
        
        # --- MODIFICATION: Removed autoRange from here ---
        # self.main_yt_plot.autoRange(padding=0.05) 
        logger.debug("Main y(t) plot updated with all tracks.")

    def populate_tracks_table(self) -> None: 
        """
        Refreshes the self.analysis_tracks_table with data from ElementManager.
        """
        logger.debug("ScaleAnalysisView: populate_tracks_table called.") 
        if not self.analysis_tracks_table:
            logger.warning("analysis_tracks_table is None, cannot populate.")
            return
            
        self.analysis_tracks_table.setRowCount(0) 

        if not PYQTGRAPH_AVAILABLE: 
            return

        if not (self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler): 
            logger.warning("ElementManager or VideoHandler not available in populate_tracks_table.")
            return

        tracks = [ 
            el for el in self.main_window_ref.element_manager.elements 
            if el.get('type') == ElementType.TRACK
        ]

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
                
                potentially_fittable_points = [
                    p for p in track_data if p[0] not in excluded_frames
                ]
                
                num_fitted_pts = 0
                if time_range_s and self.main_window_ref.video_handler.fps > 0:
                    min_t_fit, max_t_fit = time_range_s
                    points_in_time_range_and_not_excluded = [
                        p for p in potentially_fittable_points 
                        if min_t_fit <= (p[1] / 1000.0) <= max_t_fit
                    ]
                    num_fitted_pts = len(points_in_time_range_and_not_excluded)
                else: 
                    num_fitted_pts = len(potentially_fittable_points)
                
                fit_pts_str = f"{num_fitted_pts}/{total_points_in_track}"
            elif track_data: 
                fit_pts_str = f"-/{total_points_in_track}"
            else: 
                fit_pts_str = "-/0"
            
            r_squared = fit_results.get('r_squared') 
            r_squared_str = f"{r_squared:.4f}" if r_squared is not None else "N/A" 
            
            derived_scale = fit_results.get('derived_scale_m_per_px') 
            fit_scale_str = f"{derived_scale:.6g}" if derived_scale is not None else "N/A" 

            self.analysis_tracks_table.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(str(track_id)))
            self.analysis_tracks_table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(fit_pts_str))
            self.analysis_tracks_table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(fit_scale_str))
            self.analysis_tracks_table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(r_squared_str))
            
            id_item = self.analysis_tracks_table.item(row_idx, 0)
            if id_item: 
                id_item.setData(QtCore.Qt.ItemDataRole.UserRole, track_id)

        for r in range(self.analysis_tracks_table.rowCount()):
            item_id = self.analysis_tracks_table.item(r, 0)
            if item_id: item_id.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            
            item_fit_pts = self.analysis_tracks_table.item(r, 1)
            if item_fit_pts: item_fit_pts.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            item_fit_scale = self.analysis_tracks_table.item(r, 2)
            if item_fit_scale: item_fit_scale.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

            item_r_sq = self.analysis_tracks_table.item(r, 3)
            if item_r_sq: item_r_sq.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        
        logger.info(f"Populated analysis_tracks_table with {len(tracks)} tracks.")
        self._update_main_yt_plot()
        # --- BEGIN MODIFICATION: Call autoRange here ---
        if self.main_yt_plot and (self.track_plot_items or not tracks): # AutoRange if plot has items, or clear title if no tracks
            if not tracks: # If no tracks, ensure title is cleared as well
                self.main_yt_plot.setTitle("No tracks to plot")
            self.main_yt_plot.autoRange(padding=0.05)
            logger.debug("Called autoRange on main_yt_plot after populating tracks table.")
        # --- END MODIFICATION ---

    def update_on_project_or_video_change(self, is_project_or_video_loaded: bool) -> None: 
        """
        Updates the view when a project is loaded/closed or video changes.
        """
        logger.debug(f"ScaleAnalysisView: update_on_project_or_video_change called. Loaded: {is_project_or_video_loaded}") 
        if is_project_or_video_loaded: 
            self.populate_tracks_table() 
        else: 
            if self.analysis_tracks_table:
                self.analysis_tracks_table.setRowCount(0) 
            if PYQTGRAPH_AVAILABLE and hasattr(self, 'main_yt_plot') and self.main_yt_plot is not None:
                self.main_yt_plot.clear() 
                self.main_yt_plot.setTitle("")
            self.track_plot_items.clear()
            self.current_selected_track_id_for_plot = None

        self.setEnabled(is_project_or_video_loaded and PYQTGRAPH_AVAILABLE)


    @QtCore.Slot()
    def _on_analysis_table_selection_changed(self) -> None: 
        """
        Handles selection changes in the analysis_tracks_table.
        """
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
            self._update_main_yt_plot() # This will redraw with new highlighting, but not auto-range

    @QtCore.Slot(object, list) 
    def _on_main_yt_plot_point_clicked(self, scatter_plot_item: pg.ScatterPlotItem, spot_items: List[pg.SpotItem]) -> None: 
        if not spot_items or not self.analysis_tracks_table:
            return
        
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