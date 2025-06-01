# scale_analysis_view.py
"""
Provides the ScaleAnalysisView class, a QWidget for displaying multi-track
y(t) data, analysis summaries, and fitting controls.
"""
import logging
import copy 
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
            self.main_yt_plot = pg.PlotWidget() 
            self.main_yt_plot.setBackground('w') 
            self.main_yt_plot.showGrid(x=True, y=True, alpha=0.3) 
            self.main_yt_plot.setLabel('left', "Vertical Position (px, bottom-up)") 
            self.main_yt_plot.setLabel('bottom', "Time (s)") 
            if self.main_yt_plot.getViewBox():
                 self.main_yt_plot.getViewBox().setAspectLocked(lock=False) 
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
        
        # --- BEGIN MODIFICATION: Update column headers ---
        column_headers = [ 
            "ID", "Fitted Pts", "Fit Scale (m/px)", "R²"
        ]
        # --- END MODIFICATION ---
        self.analysis_tracks_table.setColumnCount(len(column_headers))
        self.analysis_tracks_table.setHorizontalHeaderLabels(column_headers)

        self.analysis_tracks_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers) 
        self.analysis_tracks_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows) 
        self.analysis_tracks_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection) 
        self.analysis_tracks_table.setAlternatingRowColors(True) 
        self.analysis_tracks_table.verticalHeader().setVisible(False) 
        
        header = self.analysis_tracks_table.horizontalHeader()
        # --- BEGIN MODIFICATION: Update resize modes for new columns ---
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # ID
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)     # Fit Pts
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)         # Fit Scale (m/px)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # R²
        
        # Set initial column widths for interactive columns if needed
        self.analysis_tracks_table.setColumnWidth(1, 70)  # Fit Pts
        # Fit Scale will stretch
        # --- END MODIFICATION ---


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
            fit_pts_str = "N/A" # Default

            # --- BEGIN MODIFICATION: Adjust "Fit Pts" display based on actual fit ---
            # Check if a fit has been performed (e.g., by presence of coefficients)
            # coefficients_poly2 will be None if no fit or if it failed and was cleared.
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
            elif track_data: # Track has data, but no fit results stored
                fit_pts_str = f"-/{total_points_in_track}"
            else: # No track data
                fit_pts_str = "-/0"
            # --- END MODIFICATION ---
            
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

        self.setEnabled(is_project_or_video_loaded and PYQTGRAPH_AVAILABLE)


    @QtCore.Slot()
    def _on_analysis_table_selection_changed(self) -> None: 
        """
        Handles selection changes in the analysis_tracks_table.
        """
        if not self.analysis_tracks_table: return
            
        selected_items = self.analysis_tracks_table.selectedItems()
        if not selected_items:
            logger.debug("ScaleAnalysisView: Track selection cleared in table.")
            return

        selected_row = self.analysis_tracks_table.row(selected_items[0])
        id_item = self.analysis_tracks_table.item(selected_row, 0) 
        
        if id_item:
            track_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if track_id is not None:
                logger.debug(f"ScaleAnalysisView: Track ID {track_id} selected in table. (Further actions in Phase 2/3)")