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
from single_track_fit_widget import SingleTrackFitWidget # Ensure this is imported

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

    def __init__(self, main_window_ref: 'MainWindow', parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.main_window_ref = main_window_ref
        
        self.main_yt_plot: Optional[pg.PlotWidget] = None
        self.analysis_tracks_table: Optional[QtWidgets.QTableWidget] = None
        self.single_track_fit_widget: Optional[SingleTrackFitWidget] = None

        self.scale_vs_time_plot: Optional[pg.PlotWidget] = None
        self.scale_vs_centroid_x_plot: Optional[pg.PlotWidget] = None
        self.scale_vs_centroid_y_plot: Optional[pg.PlotWidget] = None
        self.scale_vs_radial_pos_plot: Optional[pg.PlotWidget] = None
        self.scale_histogram_plot: Optional[pg.PlotWidget] = None
        self.scale_cdf_plot: Optional[pg.PlotWidget] = None
        
        # For storing plot items if needed for dynamic updates beyond color/size
        self.track_plot_items: Dict[int, Dict[str, pg.PlotDataItem | pg.ScatterPlotItem]] = {}
        self.current_selected_track_id_for_plot: Optional[int] = None
        self._do_not_autorange_main_plot_on_next_update: bool = False
        
        self._plot_colors: List[QtGui.QColor] = [
            QtGui.QColor("blue"), QtGui.QColor("red"), QtGui.QColor("green"),
            QtGui.QColor("purple"), QtGui.QColor("darkorange"), QtGui.QColor("teal"),
            QtGui.QColor("brown"), QtGui.QColor("darkgoldenrod"), QtGui.QColor("magenta"),
            QtGui.QColor("darkcyan"), QtGui.QColor("darkblue"), QtGui.QColor("darkred"),
            QtGui.QColor("darkgreen"), QtGui.QColor("darkmagenta"), QtGui.QColor("olive"),
            QtGui.QColor("maroon"), QtGui.QColor("indigo"), QtGui.QColor(128, 0, 128),
            QtGui.QColor(0, 100, 0), QtGui.QColor(139, 69, 19)
        ]

        self.track_global_scale_checkbox_states: Dict[int, bool] = {}
        self.calculated_global_mean_scale: Optional[float] = None
        self.calculated_global_std_dev: Optional[float] = None
        self.num_tracks_for_global_scale: int = 0

        self.calculate_global_scale_button: Optional[QtWidgets.QPushButton] = None
        self.mean_global_scale_label: Optional[QtWidgets.QLabel] = None
        self.std_dev_global_scale_label: Optional[QtWidgets.QLabel] = None
        self.n_tracks_global_scale_label: Optional[QtWidgets.QLabel] = None
        self.apply_global_scale_button: Optional[QtWidgets.QPushButton] = None
        self.show_constrained_fits_checkbox: Optional[QtWidgets.QCheckBox] = None
        
        # Splitters for resizable panels
        self.top_level_splitter: Optional[QtWidgets.QSplitter] = None
        self.left_panel_splitter: Optional[QtWidgets.QSplitter] = None
        self.bottom_left_splitter: Optional[QtWidgets.QSplitter] = None
        self.right_panel_splitter: Optional[QtWidgets.QSplitter] = None
        self.ancillary_global_splitter: Optional[QtWidgets.QSplitter] = None


        self._setup_ui()
        self._connect_signals()

        if self.main_window_ref and self.main_window_ref.element_manager:
            self.main_window_ref.element_manager.elementListChanged.connect(self.populate_tracks_table)
        else:
            logger.warning("ScaleAnalysisView: Could not connect elementListChanged; MainWindow or ElementManager not available.")

        logger.info("ScaleAnalysisView initialized.")

    def _setup_ui(self) -> None:
        # Top-level splitter (Left/Right panels)
        self.top_level_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_layout = QtWidgets.QHBoxLayout(self) # Main layout for ScaleAnalysisView widget itself
        main_layout.addWidget(self.top_level_splitter)
        main_layout.setContentsMargins(0,0,0,0)

        # --- Left Panel Container (Main Y(t) plot and bottom area with ancillary plots + global scale) ---
        left_panel_container_widget = QtWidgets.QWidget()
        self.left_panel_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, left_panel_container_widget)
        left_panel_outer_layout = QtWidgets.QVBoxLayout(left_panel_container_widget)
        left_panel_outer_layout.setContentsMargins(0,0,0,0)
        left_panel_outer_layout.addWidget(self.left_panel_splitter)

        # Top part of the left panel: Main y(t) Plot
        if PYQTGRAPH_AVAILABLE and pg is not None:
            view_box = pg.ViewBox()
            self.main_yt_plot = pg.PlotWidget(viewBox=view_box)
            self.main_yt_plot.setBackground('w')
            self.main_yt_plot.showGrid(x=True, y=True, alpha=0.3)
            
            axis_pen_main = pg.mkPen(color='k', width=1)
            text_color_main = 'k' 
            label_style = {'color': text_color_main, 'font-size': '10pt'}
            self.main_yt_plot.getAxis('left').setPen(axis_pen_main)
            self.main_yt_plot.getAxis('left').setTextPen(axis_pen_main) 
            self.main_yt_plot.getAxis('bottom').setPen(axis_pen_main)
            self.main_yt_plot.getAxis('bottom').setTextPen(axis_pen_main) 
            self.main_yt_plot.getAxis('left').setLabel(text="Vertical Position (px, bottom-up)", units="px", **label_style)
            self.main_yt_plot.getAxis('bottom').setLabel(text="Time (s)", units="s", **label_style)
            self.main_yt_plot.setTitle("") # Title is dynamic, set in _update_main_yt_plot

            self.left_panel_splitter.addWidget(self.main_yt_plot)
        else:
            self.main_yt_plot_placeholder = QtWidgets.QLabel("PyQtGraph is not available. Main y(t) plot cannot be displayed.")
            self.main_yt_plot_placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.main_yt_plot_placeholder.setStyleSheet("background-color: lightGray;")
            self.left_panel_splitter.addWidget(self.main_yt_plot_placeholder)

        # Bottom part of the left panel: Ancillary plots and Global Scale, now with a splitter
        bottom_area_widget = QtWidgets.QWidget() 
        bottom_area_layout = QtWidgets.QHBoxLayout(bottom_area_widget)
        bottom_area_layout.setContentsMargins(0,0,0,0) 
        bottom_area_layout.setSpacing(0) # Splitter handle provides separation

        # Create the horizontal splitter for ancillary plots and global scale panel
        self.ancillary_global_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal) # NEW

        # Widget for the 2x3 grid of ancillary plots
        diagnostic_plots_widget = QtWidgets.QWidget() 
        ancillary_plots_container_layout = QtWidgets.QGridLayout(diagnostic_plots_widget)
        ancillary_plots_container_layout.setContentsMargins(6, 6, 6, 6) 
        ancillary_plots_container_layout.setSpacing(5)
        diagnostic_plots_widget.setMinimumHeight(200) 
        diagnostic_plots_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        if PYQTGRAPH_AVAILABLE and pg is not None:
            plot_widgets_config = [
                ("scale_vs_time_plot", "Average Fit Time (s)", "Fit Scale (m/px)"),
                ("scale_vs_centroid_x_plot", "Centroid X (px, BL)", "Fit Scale (m/px)"),
                ("scale_histogram_plot", "Fit Scale (m/px)", "Frequency"),
                ("scale_vs_centroid_y_plot", "Centroid Y (px, BL)", "Fit Scale (m/px)"),
                ("scale_vs_radial_pos_plot", "Radial Distance from Image Center (px)", "Fit Scale (m/px)"),
                ("scale_cdf_plot", "Fit Scale (m/px)", "CDF")
            ]
            plot_positions = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
            
            axis_pen_ancillary = pg.mkPen(color='k', width=1)
            text_color_ancillary = 'k' 
            label_style_ancillary = {'color': text_color_ancillary, 'font-size': '9pt'}

            for i, (attr_name, x_label, y_label) in enumerate(plot_widgets_config):
                plot_widget = pg.PlotWidget()
                plot_widget.setBackground('w')
                plot_widget.showGrid(x=True, y=True, alpha=0.3)

                plot_widget.getAxis('left').setPen(axis_pen_ancillary)
                plot_widget.getAxis('left').setTextPen(axis_pen_ancillary) 
                plot_widget.getAxis('bottom').setPen(axis_pen_ancillary)
                plot_widget.getAxis('bottom').setTextPen(axis_pen_ancillary) 
                plot_widget.getAxis('top').setPen(axis_pen_ancillary) 
                plot_widget.getAxis('right').setPen(axis_pen_ancillary)
                
                plot_widget.setLabel('left', y_label, **label_style_ancillary)
                plot_widget.setLabel('bottom', x_label, **label_style_ancillary)
                plot_widget.setTitle("") 
                plot_widget.setMinimumSize(150, 100)
                setattr(self, attr_name, plot_widget)
                ancillary_plots_container_layout.addWidget(plot_widget, plot_positions[i][0], plot_positions[i][1])
        else: 
            placeholder_label_ancillary = QtWidgets.QLabel("PyQtGraph not available. Ancillary plots disabled.")
            placeholder_label_ancillary.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            ancillary_plots_container_layout.addWidget(placeholder_label_ancillary, 0, 0, 2, 3)
        
        self.ancillary_global_splitter.addWidget(diagnostic_plots_widget) # Add plot grid to splitter

        # Global Scale GroupBox
        self.global_scale_groupbox = QtWidgets.QGroupBox("Global Scale")
        global_scale_main_v_layout = QtWidgets.QVBoxLayout(self.global_scale_groupbox)
        global_scale_form_layout = QtWidgets.QFormLayout()
        self.mean_global_scale_label = QtWidgets.QLabel("N/A")
        global_scale_form_layout.addRow("Mean (m/px):", self.mean_global_scale_label)
        self.std_dev_global_scale_label = QtWidgets.QLabel("N/A")
        global_scale_form_layout.addRow("Std Dev (m/px):", self.std_dev_global_scale_label)
        self.n_tracks_global_scale_label = QtWidgets.QLabel("0")
        global_scale_form_layout.addRow("N Tracks Used:", self.n_tracks_global_scale_label)
        global_scale_main_v_layout.addLayout(global_scale_form_layout)
        self.calculate_global_scale_button = QtWidgets.QPushButton("Calculate Global Scale")
        self.calculate_global_scale_button.setEnabled(False)
        global_scale_main_v_layout.addWidget(self.calculate_global_scale_button)
        self.apply_global_scale_button = QtWidgets.QPushButton("Apply Global Scale to Project")
        self.apply_global_scale_button.setEnabled(False)
        global_scale_main_v_layout.addWidget(self.apply_global_scale_button)
        self.show_constrained_fits_checkbox = QtWidgets.QCheckBox("Show Fits Constrained by Global Scale")
        self.show_constrained_fits_checkbox.setEnabled(False)
        global_scale_main_v_layout.addWidget(self.show_constrained_fits_checkbox)
        global_scale_main_v_layout.addStretch(1)
        
        self.ancillary_global_splitter.addWidget(self.global_scale_groupbox) # Add global scale panel to splitter
        
        # Set initial sizes and stretch factors for the new splitter
        # These values are examples; adjust them as needed.
        self.ancillary_global_splitter.setStretchFactor(0, 2) # Give plot grid more space
        self.ancillary_global_splitter.setStretchFactor(1, 1) # Global scale panel less space
        # Optionally set initial sizes: self.ancillary_global_splitter.setSizes([initial_plot_width, initial_global_scale_width])

        bottom_area_layout.addWidget(self.ancillary_global_splitter) # Add the new splitter to the layout
        
        self.left_panel_splitter.addWidget(bottom_area_widget) 
        self.left_panel_splitter.setSizes([int(self.height() * 0.6), int(self.height() * 0.4)]) 

        # --- Right Panel Container (Track Table and Single Track Fit Widget) ---
        right_panel_container_widget = QtWidgets.QWidget()
        self.right_panel_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, right_panel_container_widget)
        right_panel_outer_layout = QtWidgets.QVBoxLayout(right_panel_container_widget)
        right_panel_outer_layout.setContentsMargins(5,0,0,0) 
        right_panel_outer_layout.addWidget(self.right_panel_splitter)

        self.analysis_tracks_table = QtWidgets.QTableWidget()
        self._setup_analysis_tracks_table() # Assumes this method is defined
        self.right_panel_splitter.addWidget(self.analysis_tracks_table)

        single_track_details_widget = QtWidgets.QWidget() 
        single_track_outer_layout = QtWidgets.QVBoxLayout(single_track_details_widget)
        single_track_outer_layout.setContentsMargins(0,6,0,0) 
        single_track_outer_layout.setSpacing(0)

        self.single_track_fit_widget = SingleTrackFitWidget(main_window_ref=self.main_window_ref, parent_view=self)
        single_track_outer_layout.addWidget(self.single_track_fit_widget)
        
        single_track_details_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        self.right_panel_splitter.addWidget(single_track_details_widget)
        
        self.right_panel_splitter.setSizes([int(self.height() * 0.35), int(self.height() * 0.65)])

        self.top_level_splitter.addWidget(left_panel_container_widget)
        self.top_level_splitter.addWidget(right_panel_container_widget)
        # Adjust initial sizes if needed due to wider ancillary plot area
        self.top_level_splitter.setSizes([int(self.width() * 0.70), int(self.width() * 0.30)])

    def _connect_signals(self) -> None:
        if self.analysis_tracks_table:
            self.analysis_tracks_table.itemSelectionChanged.connect(self._on_analysis_table_selection_changed)
        
        if self.single_track_fit_widget:
            self.single_track_fit_widget.analysisSettingsToBeSaved.connect(self._handle_save_track_analysis)
            self.single_track_fit_widget.scaleToBeApplied.connect(self._handle_apply_track_scale)
        
        # --- BEGIN MODIFICATION: Connect signals for Phase 5 UI elements ---
        if self.calculate_global_scale_button:
            self.calculate_global_scale_button.clicked.connect(self._calculate_global_scale)
        if self.apply_global_scale_button:
            self.apply_global_scale_button.clicked.connect(self._apply_calculated_global_scale)
        if self.show_constrained_fits_checkbox:
            self.show_constrained_fits_checkbox.toggled.connect(self._toggle_constrained_fits_display)
        # --- END MODIFICATION ---

    def _setup_analysis_tracks_table(self) -> None:
        if not self.analysis_tracks_table:
            return
        column_headers = ["Apply", "ID", "Fit Pts", "Fit Scale (m/px)", "R²", "Applied"]
        self.analysis_tracks_table.setColumnCount(len(column_headers))
        self.analysis_tracks_table.setHorizontalHeaderLabels(column_headers)
        self.analysis_tracks_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.analysis_tracks_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.analysis_tracks_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.analysis_tracks_table.setAlternatingRowColors(True)
        self.analysis_tracks_table.verticalHeader().setVisible(False)
        header = self.analysis_tracks_table.horizontalHeader()

        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)  # Use for Global
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)  # ID
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)     # Fit Pts
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)         # Fit Scale
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)  # R²
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)  # Applied
        self.analysis_tracks_table.setColumnWidth(2, 70) 


    def _get_plot_color_for_track(self, track_id: int) -> QtGui.QColor:
        if not self._plot_colors:
            return QtGui.QColor("black")
        color = self._plot_colors[track_id % len(self._plot_colors)]
        return color

    def _update_main_yt_plot(self) -> None:
        if not PYQTGRAPH_AVAILABLE or not self.main_yt_plot:
            return
        logger.debug(f"ScaleAnalysisView: Updating main_yt_plot. Selected track for highlight: {self.current_selected_track_id_for_plot}")
        
        plot_item = self.main_yt_plot.getPlotItem()
        if not plot_item:
            logger.error("Could not get PlotItem from main_yt_plot.")
            return

        plot_item.clear() 
        self.track_plot_items.clear()

        axis_pen_main = pg.mkPen(color='k', width=1)
        text_color_main = 'k'
        label_style = {'color': text_color_main, 'font-size': '10pt'}

        plot_item.getAxis('left').setPen(axis_pen_main)
        plot_item.getAxis('left').setTextPen(axis_pen_main)
        plot_item.getAxis('bottom').setPen(axis_pen_main)
        plot_item.getAxis('bottom').setTextPen(axis_pen_main)
        plot_item.getAxis('left').setLabel(text="Vertical Position (px, bottom-up)", units="px", **label_style)
        plot_item.getAxis('bottom').setLabel(text="Time (s)", units="s", **label_style)
        
        # Initial title setting, will be refined based on data
        plot_item.setTitle("") 

        if not (self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler and self.main_window_ref.video_handler.is_loaded):
            logger.warning("Cannot update main_yt_plot: ElementManager or VideoHandler not available/loaded.")
            plot_item.setTitle('<span style="color: black;">No video loaded or data available</span>')
            plot_item.getViewBox().autoRange() # Ensure plot is refreshed even if empty
            return
        
        video_height = self.main_window_ref.video_handler.frame_height
        if video_height <= 0:
            logger.warning("Cannot plot y(t): Video height is invalid.")
            plot_item.setTitle('<span style="color: black;">Invalid video height for y(t) plot</span>')
            plot_item.getViewBox().autoRange()
            return

        tracks = [el for el in self.main_window_ref.element_manager.elements if el.get('type') == ElementType.TRACK]
        if not tracks:
            plot_item.setTitle('<span style="color: black;">No tracks to plot</span>')
            plot_item.getViewBox().autoRange()
            return
        
        # Point 1: Set a descriptive title if there are tracks
        plot_item.setTitle('<span style="color: black;">Tracks y(t) - Select track in table to highlight</span>')
        
        show_constrained = self.show_constrained_fits_checkbox.isChecked() if self.show_constrained_fits_checkbox else False
        global_project_scale = self.main_window_ref.scale_manager.get_scale_m_per_px() if self.main_window_ref.scale_manager else None
        can_show_constrained = show_constrained and global_project_scale is not None and self.single_track_fit_widget is not None

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
            plot_item.addItem(scatter_item)
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
                    curve_color_obj = QtGui.QColor(track_color) 
                    if not is_selected_track and not can_show_constrained: 
                        curve_color_obj.setAlpha(120)
                    
                    individual_fit_pen = pg.mkPen(curve_color_obj, width=curve_pen_width)
                    if can_show_constrained: 
                        individual_fit_pen.setStyle(QtCore.Qt.PenStyle.DotLine)
                        individual_fit_pen.setWidthF(curve_pen_width * 0.75)

                    fit_curve_item = pg.PlotDataItem(x=t_for_curve_plot, y=y_curve, pen=individual_fit_pen) 
                    plot_item.addItem(fit_curve_item) 
                    self.track_plot_items[track_id]['fit_curve'] = fit_curve_item 
            
            if can_show_constrained and self.single_track_fit_widget is not None and global_project_scale is not None:
                fit_settings = analysis_state.get('fit_settings', {})
                excluded_frames_for_track = fit_settings.get('excluded_point_frames', [])
                time_range_s_for_track = fit_settings.get('time_range_s', None)

                points_for_constrained_fit_calc = []
                for p_idx, p_data in enumerate(track_data):
                    p_frame, p_time_ms, _, _ = p_data
                    if p_frame in excluded_frames_for_track: continue
                    p_time_s = p_time_ms / 1000.0
                    if time_range_s_for_track:
                        if not (time_range_s_for_track[0] <= p_time_s <= time_range_s_for_track[1]):
                            continue
                    points_for_constrained_fit_calc.append(p_data)
                
                if len(points_for_constrained_fit_calc) >= 2: 
                    g_val = self.single_track_fit_widget.current_g_value_ms2 
                    constrained_A = -0.5 * g_val / global_project_scale 
                    constrained_times_s = np.array([p[1]/1000.0 for p in points_for_constrained_fit_calc])
                    constrained_y_plot_transformed = np.array([
                        (video_height - p[3]) - constrained_A * (p[1]/1000.0)**2 
                        for p in points_for_constrained_fit_calc
                    ])
                    
                    try:
                        constrained_B_C = np.polyfit(constrained_times_s, constrained_y_plot_transformed, 1)
                        constrained_B, constrained_C = constrained_B_C[0], constrained_B_C[1]
                        
                        t_constrained_curve_plot: Optional[np.ndarray] = None
                        if time_range_s_for_track:
                            tc_min, tc_max = time_range_s_for_track
                            if tc_min < tc_max: t_constrained_curve_plot = np.linspace(tc_min, tc_max, 100)
                        elif len(constrained_times_s) > 1:
                             t_constrained_curve_plot = np.linspace(min(constrained_times_s), max(constrained_times_s), 100)
                        elif len(constrained_times_s) == 1:
                             t_constrained_curve_plot = np.array([constrained_times_s[0]])

                        if t_constrained_curve_plot is not None and len(t_constrained_curve_plot) > 0:
                            y_constrained_curve = constrained_A * t_constrained_curve_plot**2 + constrained_B * t_constrained_curve_plot + constrained_C 
                            
                            constrained_pen_color = QtGui.QColor(track_color)
                            constrained_pen = pg.mkPen(constrained_pen_color, width=2, style=QtCore.Qt.PenStyle.DashLine) 
                            if is_selected_track:
                                constrained_pen.setWidthF(3.5) 
                            else:
                                constrained_pen_color.setAlpha(150) 
                                constrained_pen.setColor(constrained_pen_color)

                            constrained_curve_item = pg.PlotDataItem(x=t_constrained_curve_plot, y=y_constrained_curve, pen=constrained_pen)
                            plot_item.addItem(constrained_curve_item) 
                            if track_id not in self.track_plot_items: self.track_plot_items[track_id] = {} 
                            self.track_plot_items[track_id]['constrained_fit_curve'] = constrained_curve_item
                    except np.linalg.LinAlgError:
                        logger.warning(f"Track {track_id}: LinAlgError during constrained fit. Skipping constrained line.")
                    except Exception as e_constr:
                        logger.warning(f"Track {track_id}: Error plotting constrained fit: {e_constr}")

        if self._do_not_autorange_main_plot_on_next_update:
            logger.debug("Skipping autoRange for main_yt_plot due to direct plot click flag.")
            self._do_not_autorange_main_plot_on_next_update = False # Reset the flag
        else:
            if plot_item and plot_item.getViewBox(): # Ensure plot_item and its viewBox exist
                plot_item.getViewBox().autoRange(padding=0.05)

        logger.debug("Main y(t) plot updated with all tracks.")


    def populate_tracks_table(self) -> None:
        logger.debug("ScaleAnalysisView: populate_tracks_table called.")
        if not self.analysis_tracks_table:
            logger.warning("analysis_tracks_table is None, cannot populate.")
            return
        
        self.analysis_tracks_table.setRowCount(0) # Clear existing rows before repopulating

        if not PYQTGRAPH_AVAILABLE:
            logger.warning("PyQtGraph not available, table population might be limited or affect dependent plots.")
            # Decide if you want to return or allow table to populate without plot updates
            # For now, let it proceed to populate table at least.

        if not (self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler):
            logger.warning("ElementManager or VideoHandler not available in populate_tracks_table.")
            self._update_main_yt_plot() # Still try to clear/update plots
            self._update_ancillary_plots()
            self._update_global_scale_buttons_enabled_state()
            return

        tracks = [el for el in self.main_window_ref.element_manager.elements if el.get('type') == ElementType.TRACK]
        self.analysis_tracks_table.setRowCount(len(tracks))

        for row_idx, track_element in enumerate(tracks):
            track_id = track_element.get('id', -1)
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
                    points_in_time_range_and_not_excluded = [
                        p for p in potentially_fittable_points if min_t_fit <= (p[1] / 1000.0) <= max_t_fit
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
            
            # --- Column 0: "Use for Global" Checkbox ---
            use_for_global_checkbox = QtWidgets.QCheckBox()
            use_for_global_checkbox.setChecked(self.track_global_scale_checkbox_states.get(track_id, False))
            use_for_global_checkbox.setProperty("track_id", track_id)
            use_for_global_checkbox.stateChanged.connect(
                lambda state, tid=track_id: self._on_global_scale_checkbox_changed(state, tid)
            )

            # --- Start of adapted centering logic for checkbox ---
            checkbox_indicator_width = 18  # Approximate visual width of a checkbox indicator
            use_for_global_checkbox.setMinimumWidth(checkbox_indicator_width)
            # Let checkbox take preferred height, but fixed width for its core visual part
            use_for_global_checkbox.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, 
                                                  QtWidgets.QSizePolicy.Policy.Preferred)

            checkbox_widget_container = QtWidgets.QWidget()
            checkbox_layout = QtWidgets.QHBoxLayout(checkbox_widget_container)
            checkbox_layout.setContentsMargins(0, 0, 0, 0) # No internal margins for the layout itself
            checkbox_layout.setSpacing(0)

            checkbox_layout.addStretch(1) # Flexible space to the left
            checkbox_layout.addWidget(use_for_global_checkbox)
            checkbox_layout.addStretch(1) # Flexible space to the right
            
            # Define a minimum sensible width for the container to ensure checkbox isn't squished
            # This width allows for the checkbox indicator + some padding managed by stretches.
            # The column's ResizeToContents will use the container's sizeHint.
            effective_padding_each_side = 3 # Small visual padding
            container_min_width = checkbox_indicator_width + (2 * effective_padding_each_side)
            
            checkbox_height_hint = use_for_global_checkbox.sizeHint().height()
            if checkbox_height_hint <= 0: # Fallback if sizeHint is unusual
                checkbox_height_hint = checkbox_indicator_width + 4 # Indicator + small vertical padding
            
            checkbox_widget_container.setMinimumSize(container_min_width, checkbox_height_hint)
            # Policy.Minimum allows it to be larger if column is wider, but respects its minimum.
            checkbox_widget_container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, 
                                                    QtWidgets.QSizePolicy.Policy.Preferred)
            # --- End of adapted centering logic ---
            
            self.analysis_tracks_table.setCellWidget(row_idx, 0, checkbox_widget_container)

            # --- Other columns ---
            id_item = QtWidgets.QTableWidgetItem(str(track_id))
            id_item.setData(QtCore.Qt.ItemDataRole.UserRole, track_id)
            self.analysis_tracks_table.setItem(row_idx, 1, id_item)

            self.analysis_tracks_table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(fit_pts_str))
            self.analysis_tracks_table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(fit_scale_str))
            self.analysis_tracks_table.setItem(row_idx, 4, QtWidgets.QTableWidgetItem(r_squared_str))
            
            is_applied = fit_results.get('is_applied_to_project', False)
            applied_str = "Yes" if is_applied else "No"
            applied_item = QtWidgets.QTableWidgetItem(applied_str)
            self.analysis_tracks_table.setItem(row_idx, 5, applied_item)

        # Set text alignment for relevant columns
        for r in range(self.analysis_tracks_table.rowCount()):
            for c_idx, alignment in [(1, QtCore.Qt.AlignmentFlag.AlignCenter),  # ID
                                     (2, QtCore.Qt.AlignmentFlag.AlignCenter),  # Fit Pts
                                     (3, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter),  # Fit Scale
                                     (4, QtCore.Qt.AlignmentFlag.AlignCenter),  # R²
                                     (5, QtCore.Qt.AlignmentFlag.AlignCenter)]: # Applied
                item = self.analysis_tracks_table.item(r, c_idx)
                if item:
                    item.setTextAlignment(alignment)
        
        logger.info(f"Populated analysis_tracks_table with {len(tracks)} tracks.")
        self._update_main_yt_plot() # Refresh main plot as track data/selection might implicitly change
        
        # Ensure main plot is autoranged correctly after potential data changes
        if self.main_yt_plot:
            if not tracks and PYQTGRAPH_AVAILABLE: # Check PYQTGRAPH_AVAILABLE here too
                self.main_yt_plot.setTitle('<span style="color: black;">No tracks to plot</span>')
            self.main_yt_plot.autoRange(padding=0.05)
        
        self._update_ancillary_plots() # Refresh ancillary plots
        self._update_global_scale_buttons_enabled_state() # Update button states

    def update_on_project_or_video_change(self, is_project_or_video_loaded: bool) -> None:
        logger.debug(f"ScaleAnalysisView: update_on_project_or_video_change called. Loaded: {is_project_or_video_loaded}")
        if is_project_or_video_loaded:
            self.track_global_scale_checkbox_states.clear()
            self.populate_tracks_table() 
        else:
            if self.analysis_tracks_table: self.analysis_tracks_table.setRowCount(0)
            if PYQTGRAPH_AVAILABLE and hasattr(self, 'main_yt_plot') and self.main_yt_plot is not None:
                self.main_yt_plot.clear(); self.main_yt_plot.setTitle("")
            self.track_plot_items.clear()
            self.current_selected_track_id_for_plot = None
            if self.single_track_fit_widget:
                self.single_track_fit_widget.clear_and_disable()
            self._clear_all_ancillary_plots()
            self.calculated_global_mean_scale = None
            self.calculated_global_std_dev = None
            self.num_tracks_for_global_scale = 0
            if self.mean_global_scale_label: self.mean_global_scale_label.setText("N/A")
            if self.std_dev_global_scale_label: self.std_dev_global_scale_label.setText("N/A")
            if self.n_tracks_global_scale_label: self.n_tracks_global_scale_label.setText("0")
            self.track_global_scale_checkbox_states.clear()

        self.setEnabled(is_project_or_video_loaded and PYQTGRAPH_AVAILABLE)
        self._update_global_scale_buttons_enabled_state()
        if self.show_constrained_fits_checkbox:
            self.show_constrained_fits_checkbox.setEnabled(is_project_or_video_loaded and PYQTGRAPH_AVAILABLE and self.main_window_ref.scale_manager.get_scale_m_per_px() is not None)
    
    @QtCore.Slot(int, int)
    def _on_global_scale_checkbox_changed(self, state: int, track_id: int) -> None:
        is_checked = (state == QtCore.Qt.CheckState.Checked.value)
        self.track_global_scale_checkbox_states[track_id] = is_checked
        logger.debug(f"Track ID {track_id} 'Use for Global' checkbox state changed to: {is_checked}")
        self._update_global_scale_buttons_enabled_state()

    @QtCore.Slot()
    def _calculate_global_scale(self) -> None: 
        logger.info("Calculate Global Scale button clicked.")
        if not self.main_window_ref or not self.main_window_ref.element_manager:
            return

        scales_to_average = []
        for track_id, use_for_global in self.track_global_scale_checkbox_states.items():
            if use_for_global:
                track_element = next((el for el in self.main_window_ref.element_manager.elements if el.get('id') == track_id and el.get('type') == ElementType.TRACK), None)
                if track_element:
                    analysis_state = track_element.get('analysis_state', {})
                    fit_results = analysis_state.get('fit_results', {})
                    derived_scale = fit_results.get('derived_scale_m_per_px')
                    if derived_scale is not None and derived_scale > 0: 
                        scales_to_average.append(derived_scale)
        
        if scales_to_average:
            self.calculated_global_mean_scale = float(np.mean(scales_to_average)) 
            self.calculated_global_std_dev = float(np.std(scales_to_average)) if len(scales_to_average) > 1 else 0.0 
            self.num_tracks_for_global_scale = len(scales_to_average) 
            logger.info(f"Global scale calculated: Mean={self.calculated_global_mean_scale:.6g}, "
                        f"StdDev={self.calculated_global_std_dev:.6g}, N={self.num_tracks_for_global_scale}")
        else: 
            self.calculated_global_mean_scale = None
            self.calculated_global_std_dev = None
            self.num_tracks_for_global_scale = 0
            logger.info("No tracks selected or no valid derived scales for global calculation.")

        self._update_global_scale_display_labels() 
        self._update_global_scale_buttons_enabled_state() 

    @QtCore.Slot()
    def _apply_calculated_global_scale(self) -> None: 
        if self.calculated_global_mean_scale is None or not (self.main_window_ref and self.main_window_ref.scale_manager and self.main_window_ref.element_manager):
            logger.warning("Apply Global Scale clicked, but no valid calculated scale or managers missing.")
            QtWidgets.QMessageBox.warning(self, "Apply Scale Error", "No valid global scale has been calculated to apply.")
            return

        reply = QtWidgets.QMessageBox.question( 
            self, "Apply Global Scale to Project",
            f"Apply calculated global scale ({self.calculated_global_mean_scale:.6g} m/px, from {self.num_tracks_for_global_scale} tracks) "
            "to the entire project?\nThis will override any existing project scale and clear any manually drawn scale line.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            scale_source_desc = f"Global Fit ({self.num_tracks_for_global_scale} tracks)" 
            self.main_window_ref.scale_manager.set_scale(self.calculated_global_mean_scale, source_description=scale_source_desc) 
            
            for el in self.main_window_ref.element_manager.elements:
                if el.get('type') == ElementType.TRACK:
                    el_id = el.get('id')
                    current_analysis_state = el.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
                    current_analysis_state['fit_results']['is_applied_to_project'] = False 
                    self.main_window_ref.element_manager.update_track_analysis_state(el_id, current_analysis_state)
            
            self.populate_tracks_table() 
            if self.main_window_ref.statusBar():
                self.main_window_ref.statusBar().showMessage(f"Global scale ({self.calculated_global_mean_scale:.6g} m/px) applied to project.", 5000)
            
            if self.show_constrained_fits_checkbox:
                self.show_constrained_fits_checkbox.setEnabled(True)
            self._update_main_yt_plot() 

    @QtCore.Slot(bool)
    def _toggle_constrained_fits_display(self, checked: bool) -> None: 
        logger.info(f"'Show Fits Constrained by Global Scale' toggled to: {checked}")
        self._update_main_yt_plot() 
    
    def _update_global_scale_display_labels(self) -> None:
        if self.mean_global_scale_label:
            self.mean_global_scale_label.setText(f"{self.calculated_global_mean_scale:.6g}" if self.calculated_global_mean_scale is not None else "N/A")
        if self.std_dev_global_scale_label:
            self.std_dev_global_scale_label.setText(f"{self.calculated_global_std_dev:.2g}" if self.calculated_global_std_dev is not None else "N/A")
        if self.n_tracks_global_scale_label:
            self.n_tracks_global_scale_label.setText(str(self.num_tracks_for_global_scale))

    def _update_global_scale_buttons_enabled_state(self) -> None:
        can_calculate = any(self.track_global_scale_checkbox_states.values())
        if self.calculate_global_scale_button:
            self.calculate_global_scale_button.setEnabled(can_calculate and PYQTGRAPH_AVAILABLE and self.main_window_ref.video_handler.is_loaded)
        
        can_apply = self.calculated_global_mean_scale is not None
        if self.apply_global_scale_button:
            self.apply_global_scale_button.setEnabled(can_apply and PYQTGRAPH_AVAILABLE and self.main_window_ref.video_handler.is_loaded)
            
        can_show_constrained = PYQTGRAPH_AVAILABLE and self.main_window_ref.video_handler.is_loaded and \
                               (self.main_window_ref.scale_manager.get_scale_m_per_px() is not None)
        if self.show_constrained_fits_checkbox:
            self.show_constrained_fits_checkbox.setEnabled(can_show_constrained)
            if not can_show_constrained and self.show_constrained_fits_checkbox.isChecked():
                self.show_constrained_fits_checkbox.setChecked(False)


    # --- END MODIFICATION ---

    @QtCore.Slot()
    def _on_analysis_table_selection_changed(self) -> None: 
        if not self.analysis_tracks_table: return
        selected_items = self.analysis_tracks_table.selectedItems()
        newly_selected_track_id: Optional[int] = None

        if selected_items:
            selected_row = self.analysis_tracks_table.row(selected_items[0])
            # ID is now in column 1
            id_item = self.analysis_tracks_table.item(selected_row, 1) 
            if id_item:
                track_id_data = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(track_id_data, int):
                    newly_selected_track_id = track_id_data 
        
        if self.current_selected_track_id_for_plot != newly_selected_track_id:
            self.current_selected_track_id_for_plot = newly_selected_track_id 
            self._update_main_yt_plot() 

        if self.single_track_fit_widget and self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler:
            if newly_selected_track_id is not None:
                track_to_load = None
                for el in self.main_window_ref.element_manager.elements:
                    if el.get('id') == newly_selected_track_id and el.get('type') == ElementType.TRACK:
                        track_to_load = el
                        break
                if track_to_load:
                    self.single_track_fit_widget.load_track_data(
                        copy.deepcopy(track_to_load),
                        self.main_window_ref.video_handler.fps,
                        self.main_window_ref.video_handler.frame_height
                    )
                else:
                    self.single_track_fit_widget.clear_and_disable()
            else:
                self.single_track_fit_widget.clear_and_disable()


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
            id_item = self.analysis_tracks_table.item(r, 1) # ID is in column 1
            if id_item:
                table_track_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole) 
                if table_track_id == clicked_track_id:
                    current_selected_row = -1
                    if self.analysis_tracks_table.selectedItems():
                        current_selected_row = self.analysis_tracks_table.currentRow()
                    
                    if current_selected_row != r:
                        # --- MODIFICATION: Set flag before changing table selection ---
                        self._do_not_autorange_main_plot_on_next_update = True
                        logger.debug("Setting _do_not_autorange_main_plot_on_next_update = True due to main_yt_plot click.")
                        # --- END MODIFICATION ---
                        self.analysis_tracks_table.selectRow(r)
                    else:
                        # If already selected, and user clicks again on the plot,
                        # we still might want to prevent autorange if _update_main_yt_plot is called.
                        # However, selectRow won't emit selectionChanged if already selected.
                        # The highlight update path is through _on_analysis_table_selection_changed.
                        # If the row is already selected, this method effectively does nothing more,
                        # and the highlight state (which triggers _update_main_yt_plot) doesn't change.
                        # This is fine, as no plot update means no unwanted autorange.
                        logger.debug(f"Row {r} for track ID {clicked_track_id} is already selected.")
                    break

    def _get_track_fit_summary_data(self, track_element: Dict) -> Optional[Dict]:
        if not (self.main_window_ref and self.main_window_ref.video_handler and self.main_window_ref.video_handler.is_loaded):
            logger.warning("_get_track_fit_summary_data: Video not loaded, cannot calculate summary.")
            return None

        track_id = track_element.get('id')
        analysis_state = track_element.get('analysis_state', {})
        fit_results = analysis_state.get('fit_results', {})
        fit_settings = analysis_state.get('fit_settings', {})
        track_data = track_element.get('data', [])

        derived_scale = fit_results.get('derived_scale_m_per_px')
        coefficients = fit_results.get('coefficients_poly2')

        if derived_scale is None or coefficients is None or not track_data:
            logger.debug(f"Track ID {track_id}: No valid derived scale, coefficients, or no track data. Skipping summary.")
            return None

        excluded_frames = fit_settings.get('excluded_point_frames', [])
        time_range_s_setting = fit_settings.get('time_range_s', None)

        fitted_points_info = [] 

        for point_tuple in track_data:
            frame_idx, time_ms, x_tl_px, y_tl_px = point_tuple
            if frame_idx in excluded_frames:
                continue
            
            time_s = time_ms / 1000.0
            if time_range_s_setting:
                min_t, max_t = time_range_s_setting
                if not (min_t <= time_s <= max_t):
                    continue
            
            fitted_points_info.append((time_s, x_tl_px, y_tl_px))

        if not fitted_points_info:
            logger.debug(f"Track ID {track_id}: No points remained after filtering for exclusion and time range. Skipping summary.")
            return None

        times_s_fitted = np.array([p[0] for p in fitted_points_info])
        x_tl_px_fitted_avg = float(np.mean(np.array([p[1] for p in fitted_points_info])))
        y_tl_px_fitted_avg = float(np.mean(np.array([p[2] for p in fitted_points_info])))

        avg_time_s = float(np.mean(times_s_fitted))
        
        # Point 3: Transform centroid to Bottom-Left coordinates for plotting
        video_h = self.main_window_ref.video_handler.frame_height
        centroid_x_plot_px = x_tl_px_fitted_avg # X is the same for TL and BL display
        centroid_y_plot_px = video_h - y_tl_px_fitted_avg if video_h > 0 else y_tl_px_fitted_avg # Y is inverted

        video_width = self.main_window_ref.video_handler.frame_width
        center_x_px = video_width / 2.0
        center_y_px = video_h / 2.0 # Use video_h for consistency with plot y-axis

        # Radial position calculation should use consistent coordinate system for dx, dy
        # If centroid_x_plot_px, centroid_y_plot_px are now effectively BL (for y),
        # ensure center_x_px, center_y_px are also considered in that frame or use TL for radial.
        # For simplicity, let's use TL for radial distance as it's an absolute distance.
        radial_pos_px = math.sqrt((x_tl_px_fitted_avg - center_x_px)**2 + (y_tl_px_fitted_avg - center_y_px)**2)


        summary = {
            'track_id': track_id,
            'derived_scale': derived_scale,
            'avg_time_s': avg_time_s,
            'centroid_x_px': centroid_x_plot_px, # This is now BL-x for plot
            'centroid_y_px': centroid_y_plot_px, # This is now BL-y for plot
            'radial_pos_px': radial_pos_px
        }
        logger.debug(f"Track ID {track_id}: Fit summary calculated (Centroid for plot is BL): {summary}")
        return summary

    def _clear_all_ancillary_plots(self) -> None:
        """Clears all data from the ancillary plots."""
        ancillary_plots = [
            self.scale_vs_time_plot, self.scale_vs_centroid_x_plot,
            self.scale_vs_centroid_y_plot, self.scale_vs_radial_pos_plot,
            self.scale_histogram_plot, self.scale_cdf_plot # New plots added
        ]
        for plot in ancillary_plots:
            if plot:
                plot.clear() 
        logger.debug("Cleared all ancillary plots.")

    def _update_ancillary_plots(self) -> None:
        if not PYQTGRAPH_AVAILABLE:
            return
        
        logger.debug("ScaleAnalysisView: Updating ancillary diagnostic plots.")
        self._clear_all_ancillary_plots()

        if not (self.main_window_ref and self.main_window_ref.element_manager):
            logger.warning("Cannot update ancillary plots: ElementManager not available.")
            for plot in [self.scale_vs_time_plot, self.scale_vs_centroid_x_plot,
                         self.scale_vs_centroid_y_plot, self.scale_vs_radial_pos_plot,
                         self.scale_histogram_plot, self.scale_cdf_plot]:
                if plot: plot.autoRange()
            return

        fit_summaries: List[Dict] = []
        for track_element in self.main_window_ref.element_manager.elements:
            if track_element.get('type') == ElementType.TRACK:
                summary = self._get_track_fit_summary_data(track_element)
                if summary and summary.get('derived_scale') is not None:
                    fit_summaries.append(summary)
        
        if not fit_summaries:
            logger.debug("No valid fit summaries to display in ancillary plots.")
            for plot in [self.scale_vs_time_plot, self.scale_vs_centroid_x_plot,
                         self.scale_vs_centroid_y_plot, self.scale_vs_radial_pos_plot,
                         self.scale_histogram_plot, self.scale_cdf_plot]:
                if plot: plot.autoRange()
            return
        
        track_ids_all = [s['track_id'] for s in fit_summaries]
        scales_all = np.array([s['derived_scale'] for s in fit_summaries])
        avg_times = np.array([s['avg_time_s'] for s in fit_summaries])
        centroid_xs = np.array([s['centroid_x_px'] for s in fit_summaries])
        centroid_ys = np.array([s['centroid_y_px'] for s in fit_summaries])
        radial_positions = np.array([s['radial_pos_px'] for s in fit_summaries])

        point_brushes_all = [self._get_plot_color_for_track(tid) for tid in track_ids_all]

        # Existing scatter plots
        if self.scale_vs_time_plot:
            scatter_time = pg.ScatterPlotItem(x=avg_times, y=scales_all, data=track_ids_all,
                                              symbol='o', size=8, brush=point_brushes_all)
            scatter_time.sigClicked.connect(self._on_ancillary_plot_point_clicked)
            self.scale_vs_time_plot.addItem(scatter_time)
            self.scale_vs_time_plot.autoRange()

        if self.scale_vs_centroid_x_plot:
            scatter_cx = pg.ScatterPlotItem(x=centroid_xs, y=scales_all, data=track_ids_all,
                                            symbol='o', size=8, brush=point_brushes_all)
            scatter_cx.sigClicked.connect(self._on_ancillary_plot_point_clicked)
            self.scale_vs_centroid_x_plot.addItem(scatter_cx)
            self.scale_vs_centroid_x_plot.autoRange()

        if self.scale_vs_centroid_y_plot:
            scatter_cy = pg.ScatterPlotItem(x=centroid_ys, y=scales_all, data=track_ids_all,
                                            symbol='o', size=8, brush=point_brushes_all)
            scatter_cy.sigClicked.connect(self._on_ancillary_plot_point_clicked)
            self.scale_vs_centroid_y_plot.addItem(scatter_cy)
            self.scale_vs_centroid_y_plot.autoRange()

        if self.scale_vs_radial_pos_plot:
            scatter_rad = pg.ScatterPlotItem(x=radial_positions, y=scales_all, data=track_ids_all,
                                             symbol='o', size=8, brush=point_brushes_all)
            scatter_rad.sigClicked.connect(self._on_ancillary_plot_point_clicked)
            self.scale_vs_radial_pos_plot.addItem(scatter_rad)
            self.scale_vs_radial_pos_plot.autoRange()
            
        # Histogram Plot
        if self.scale_histogram_plot and len(scales_all) > 0:
            num_bins = min(max(5, int(np.sqrt(len(scales_all)))), 20)
            hist_counts, bin_edges = np.histogram(scales_all, bins=num_bins)
            bin_width = bin_edges[1] - bin_edges[0] if len(bin_edges) > 1 else 1.0
            bar_item = pg.BarGraphItem(x=bin_edges[:-1], height=hist_counts, width=bin_width * 0.9, brush='cornflowerblue')
            self.scale_histogram_plot.addItem(bar_item)
            self.scale_histogram_plot.autoRange()

        # --- MODIFIED CDF Plot with separate line and scatter items ---
        if self.scale_cdf_plot and len(scales_all) > 0:
            combined_scale_trackid = sorted(zip(scales_all, track_ids_all), key=lambda pair: pair[0])
            
            sorted_individual_scales = np.array([pair[0] for pair in combined_scale_trackid])
            track_ids_for_cdf_points = [pair[1] for pair in combined_scale_trackid]

            y_cdf_individual = np.arange(1, len(sorted_individual_scales) + 1) / len(sorted_individual_scales)

            # 1. Create PlotDataItem for the dot-to-dot line
            # Using a neutral color like gray for the line to let point colors stand out.
            connecting_line_pen = pg.mkPen(color=(150, 150, 150, 200), width=1.5, style=QtCore.Qt.PenStyle.DotLine)
            cdf_line_item = pg.PlotDataItem(
                x=sorted_individual_scales,
                y=y_cdf_individual,
                pen=connecting_line_pen,
                # stepMode can be used for a more traditional ECDF step plot if desired,
                # but for dot-to-dot, direct plotting is fine.
            )
            self.scale_cdf_plot.addItem(cdf_line_item)

            # 2. Create ScatterPlotItem for the clickable, colored points
            cdf_point_brushes = [self._get_plot_color_for_track(tid) for tid in track_ids_for_cdf_points]
            cdf_scatter_points_item = pg.ScatterPlotItem(
                x=sorted_individual_scales, 
                y=y_cdf_individual, 
                data=track_ids_for_cdf_points,  # Store track_id with each point
                symbol='o', 
                size=8,                         # Use 'size' instead of 'symbolSize' for ScatterPlotItem
                pen=None,                       # No connecting pen for the scatter item itself
                brush=cdf_point_brushes         # Use per-track colors for symbol fill
            )
            cdf_scatter_points_item.sigClicked.connect(self._on_ancillary_plot_point_clicked)
            self.scale_cdf_plot.addItem(cdf_scatter_points_item)
            
            # Range setting
            self.scale_cdf_plot.setYRange(0, 1.05, padding=0)
            if len(sorted_individual_scales) > 0:
                min_x_cdf = min(sorted_individual_scales)
                max_x_cdf = max(sorted_individual_scales)
                if min_x_cdf == max_x_cdf:
                    padding_cdf = 0.1 * abs(min_x_cdf) if abs(min_x_cdf) > 1e-9 else 0.1
                    self.scale_cdf_plot.setXRange(min_x_cdf - padding_cdf, max_x_cdf + padding_cdf, padding=0)
                else:
                    self.scale_cdf_plot.setXRange(min_x_cdf, max_x_cdf, padding=0.05)
            else:
                self.scale_cdf_plot.autoRange()
        # --- END MODIFIED CDF Plot ---

        logger.debug(f"Updated ancillary plots with {len(fit_summaries)} data points, including histogram and CDF.")


    @QtCore.Slot(object, list)
    def _on_ancillary_plot_point_clicked(self, plot_item: pg.ScatterPlotItem, points: List[pg.SpotItem]) -> None: 
        if not points or not self.analysis_tracks_table: 
            logger.debug("Ancillary plot click ignored: No points clicked or table not available.")
            return

        clicked_spot = points[0]
        track_id_from_plot_point = clicked_spot.data() 

        if track_id_from_plot_point is None:
            logger.warning("Clicked point on ancillary plot has no associated track_id data.")
            return

        if not isinstance(track_id_from_plot_point, int):
            logger.warning(f"Clicked point on ancillary plot has non-integer track_id data: {track_id_from_plot_point}")
            return
            
        logger.debug(f"Ancillary plot point clicked. Track ID from point data: {track_id_from_plot_point}")

        found_row = -1
        for r in range(self.analysis_tracks_table.rowCount()):
            # --- BEGIN MODIFICATION: Column index for ID is now 1 ---
            id_item = self.analysis_tracks_table.item(r, 1) # ID is in column 1
            # --- END MODIFICATION ---
            if id_item:
                table_track_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole) 
                if table_track_id == track_id_from_plot_point:
                    found_row = r
                    break
        
        if found_row != -1:
            logger.debug(f"Found track ID {track_id_from_plot_point} in table at row {found_row}. Selecting row.")
            current_selected_row = -1
            if self.analysis_tracks_table.selectedItems():
                current_selected_row = self.analysis_tracks_table.currentRow()
            
            if current_selected_row != found_row:
                self.analysis_tracks_table.selectRow(found_row)
            else:
                logger.debug(f"Row {found_row} for track ID {track_id_from_plot_point} is already selected.")
        else:
            logger.warning(f"Could not find track ID {track_id_from_plot_point} in analysis_tracks_table.")

    @QtCore.Slot(int, dict)
    def _handle_save_track_analysis(self, track_id: int, analysis_state_dict: Dict) -> None:
        logger.info(f"ScaleAnalysisView: Received request to save analysis for Track ID {track_id}.")
        if self.main_window_ref and self.main_window_ref.element_manager:
            success = self.main_window_ref.element_manager.update_track_analysis_state(track_id, analysis_state_dict)
            if success:
                logger.info(f"Analysis state for Track ID {track_id} updated in ElementManager.")
                self.populate_tracks_table() 
                self._update_main_yt_plot() 
                if self.main_window_ref.statusBar():
                    self.main_window_ref.statusBar().showMessage(f"Analysis for Track {track_id} saved.", 3000)
            else:
                logger.error(f"Failed to update analysis state for Track ID {track_id} in ElementManager.")
                QtWidgets.QMessageBox.warning(self, "Save Error", f"Could not save analysis for Track {track_id}.")
        else:
            logger.error("Cannot save track analysis: MainWindow or ElementManager not available.")

    @QtCore.Slot(int, float)
    def _handle_apply_track_scale(self, track_id: int, derived_scale: float) -> None:
        logger.info(f"ScaleAnalysisView: Received request to apply scale {derived_scale:.6g} m/px from Track ID {track_id}.")
        if not (self.main_window_ref and self.main_window_ref.scale_manager and self.main_window_ref.element_manager):
            logger.error("Cannot apply track scale: Core managers not available.")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Apply Scale to Project",
            f"Apply derived scale ({derived_scale:.6g} m/px) from Track {track_id} to the entire project?\n"
            "This will override any existing project scale and clear any manually drawn scale line.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            scale_source_desc = f"Track {track_id} Parabolic Fit"
            self.main_window_ref.scale_manager.set_scale(derived_scale, source_description=scale_source_desc)
            
            for el in self.main_window_ref.element_manager.elements:
                if el.get('type') == ElementType.TRACK:
                    el_id = el.get('id')
                    current_analysis_state = el.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
                    current_analysis_state['fit_results']['is_applied_to_project'] = (el_id == track_id)
                    self.main_window_ref.element_manager.update_track_analysis_state(el_id, current_analysis_state)
            
            self.populate_tracks_table() 
            self._update_main_yt_plot() 
            if self.main_window_ref.statusBar():
                self.main_window_ref.statusBar().showMessage(f"Scale from Track {track_id} applied to project.", 5000)
        else:
            logger.info("User cancelled applying scale from track to project.")