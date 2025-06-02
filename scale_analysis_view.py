# scale_analysis_view.py
"""
Provides the ScaleAnalysisView class, a QWidget for displaying multi-track
y(t) data, analysis summaries, and fitting controls.
"""
import logging
import copy
import math
import numpy as np
from typing import TYPE_CHECKING, Optional, Dict, List, Any # Added Any

from PySide6 import QtCore, QtGui, QtWidgets

from element_manager import ElementType, DEFAULT_ANALYSIS_STATE
from single_track_fit_widget import SingleTrackFitWidget

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
        main_layout = QtWidgets.QHBoxLayout(self) 
        main_layout.addWidget(self.top_level_splitter)
        main_layout.setContentsMargins(0,0,0,0)

        left_panel_container_widget = QtWidgets.QWidget()
        self.left_panel_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, left_panel_container_widget)
        left_panel_outer_layout = QtWidgets.QVBoxLayout(left_panel_container_widget)
        left_panel_outer_layout.setContentsMargins(0,0,0,0)
        left_panel_outer_layout.addWidget(self.left_panel_splitter)

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
            self.main_yt_plot.setTitle("")
            self.left_panel_splitter.addWidget(self.main_yt_plot)
        else:
            self.main_yt_plot_placeholder = QtWidgets.QLabel("PyQtGraph is not available. Main y(t) plot cannot be displayed.")
            self.main_yt_plot_placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.main_yt_plot_placeholder.setStyleSheet("background-color: lightGray;")
            self.left_panel_splitter.addWidget(self.main_yt_plot_placeholder)

        bottom_area_widget = QtWidgets.QWidget() 
        bottom_area_layout = QtWidgets.QHBoxLayout(bottom_area_widget)
        bottom_area_layout.setContentsMargins(0,0,0,0) 
        bottom_area_layout.setSpacing(0)

        self.ancillary_global_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

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
                plot_widget.setBackground('w'); plot_widget.showGrid(x=True, y=True, alpha=0.3)
                plot_widget.getAxis('left').setPen(axis_pen_ancillary); plot_widget.getAxis('left').setTextPen(axis_pen_ancillary) 
                plot_widget.getAxis('bottom').setPen(axis_pen_ancillary); plot_widget.getAxis('bottom').setTextPen(axis_pen_ancillary) 
                plot_widget.getAxis('top').setPen(axis_pen_ancillary); plot_widget.getAxis('right').setPen(axis_pen_ancillary)
                plot_widget.setLabel('left', y_label, **label_style_ancillary); plot_widget.setLabel('bottom', x_label, **label_style_ancillary)
                plot_widget.setTitle(""); plot_widget.setMinimumSize(150, 100)
                setattr(self, attr_name, plot_widget)
                ancillary_plots_container_layout.addWidget(plot_widget, plot_positions[i][0], plot_positions[i][1])
        else: 
            placeholder_label_ancillary = QtWidgets.QLabel("PyQtGraph not available. Ancillary plots disabled.")
            placeholder_label_ancillary.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            ancillary_plots_container_layout.addWidget(placeholder_label_ancillary, 0, 0, 2, 3)
        self.ancillary_global_splitter.addWidget(diagnostic_plots_widget)

        self.global_scale_groupbox = QtWidgets.QGroupBox("Global Scale")
        global_scale_main_v_layout = QtWidgets.QVBoxLayout(self.global_scale_groupbox)
        global_scale_main_v_layout.setContentsMargins(6, 6, 6, 6); global_scale_main_v_layout.setSpacing(8)
        global_scale_form_layout = QtWidgets.QFormLayout()
        global_scale_form_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        global_scale_form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        global_scale_form_layout.setHorizontalSpacing(10); global_scale_form_layout.setVerticalSpacing(5)
        self.mean_global_scale_label = QtWidgets.QLabel("N/A")
        global_scale_form_layout.addRow("Mean (m/px):", self.mean_global_scale_label)
        self.std_dev_global_scale_label = QtWidgets.QLabel("N/A")
        global_scale_form_layout.addRow("Std Dev (m/px):", self.std_dev_global_scale_label)
        self.n_tracks_global_scale_label = QtWidgets.QLabel("0")
        global_scale_form_layout.addRow("N Tracks Used:", self.n_tracks_global_scale_label)
        global_scale_main_v_layout.addLayout(global_scale_form_layout)
        self.calculate_global_scale_button = QtWidgets.QPushButton("Calculate Global Scale")
        self.calculate_global_scale_button.setToolTip("Calculate mean scale from tracks checked in the 'Use' column.")
        self.calculate_global_scale_button.setEnabled(False)
        global_scale_main_v_layout.addWidget(self.calculate_global_scale_button)
        self.apply_global_scale_button = QtWidgets.QPushButton("Apply Global Scale to Project")
        self.apply_global_scale_button.setToolTip("Apply the calculated mean global scale to the entire project.")
        self.apply_global_scale_button.setEnabled(False)
        global_scale_main_v_layout.addWidget(self.apply_global_scale_button)
        self.show_constrained_fits_checkbox = QtWidgets.QCheckBox("Show Fits Constrained by Global Scale")
        self.show_constrained_fits_checkbox.setToolTip("On the main Y(t) plot, show how tracks fit parabolas constrained by the current project scale.")
        self.show_constrained_fits_checkbox.setEnabled(False)
        global_scale_main_v_layout.addWidget(self.show_constrained_fits_checkbox)
        global_scale_main_v_layout.addStretch(1)
        self.ancillary_global_splitter.addWidget(self.global_scale_groupbox)
        self.ancillary_global_splitter.setStretchFactor(0, 2); self.ancillary_global_splitter.setStretchFactor(1, 1)
        bottom_area_layout.addWidget(self.ancillary_global_splitter)
        self.left_panel_splitter.addWidget(bottom_area_widget) 
        self.left_panel_splitter.setSizes([int(self.height() * 0.6), int(self.height() * 0.4)]) 

        right_panel_container_widget = QtWidgets.QWidget()
        self.right_panel_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, right_panel_container_widget)
        right_panel_outer_layout = QtWidgets.QVBoxLayout(right_panel_container_widget)
        right_panel_outer_layout.setContentsMargins(5,0,0,0) 
        right_panel_outer_layout.addWidget(self.right_panel_splitter)
        self.analysis_tracks_table = QtWidgets.QTableWidget()
        self._setup_analysis_tracks_table()
        self.right_panel_splitter.addWidget(self.analysis_tracks_table)
        single_track_details_widget = QtWidgets.QWidget() 
        single_track_outer_layout = QtWidgets.QVBoxLayout(single_track_details_widget)
        single_track_outer_layout.setContentsMargins(0,6,0,0); single_track_outer_layout.setSpacing(0)
        self.single_track_fit_widget = SingleTrackFitWidget(main_window_ref=self.main_window_ref, parent_view=self)
        single_track_outer_layout.addWidget(self.single_track_fit_widget)
        single_track_details_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        self.right_panel_splitter.addWidget(single_track_details_widget)
        self.right_panel_splitter.setSizes([int(self.height() * 0.35), int(self.height() * 0.65)])
        self.top_level_splitter.addWidget(left_panel_container_widget)
        self.top_level_splitter.addWidget(right_panel_container_widget)
        self.top_level_splitter.setSizes([int(self.width() * 0.70), int(self.width() * 0.30)])

    def _connect_signals(self) -> None:
        if self.analysis_tracks_table:
            self.analysis_tracks_table.itemSelectionChanged.connect(self._on_analysis_table_selection_changed)
        if self.single_track_fit_widget:
            self.single_track_fit_widget.analysisSettingsToBeSaved.connect(self._handle_save_track_analysis)
            self.single_track_fit_widget.scaleToBeApplied.connect(self._handle_apply_track_scale)
        if self.calculate_global_scale_button:
            self.calculate_global_scale_button.clicked.connect(self._calculate_global_scale)
        if self.apply_global_scale_button:
            self.apply_global_scale_button.clicked.connect(self._apply_calculated_global_scale)
        if self.show_constrained_fits_checkbox:
            self.show_constrained_fits_checkbox.toggled.connect(self._toggle_constrained_fits_display)

    def _setup_analysis_tracks_table(self) -> None:
        if not self.analysis_tracks_table: return
        column_headers = ["Use", "ID", "Fit Pts", "Fit Scale (m/px)", "R²", "Applied"]
        self.analysis_tracks_table.setColumnCount(len(column_headers))
        self.analysis_tracks_table.setHorizontalHeaderLabels(column_headers)
        self.analysis_tracks_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.analysis_tracks_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.analysis_tracks_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.analysis_tracks_table.setAlternatingRowColors(True)
        self.analysis_tracks_table.verticalHeader().setVisible(False)
        header = self.analysis_tracks_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.analysis_tracks_table.setColumnWidth(2, 70)
        header.model().setHeaderData(0, QtCore.Qt.Orientation.Horizontal, "Check to include this track's fit in global scale calculations.", QtCore.Qt.ItemDataRole.ToolTipRole)

    def set_scale_analysis_data_from_project(self, data: Dict[str, Any]) -> None:
        """
        Sets the internal state of the ScaleAnalysisView from loaded project data.
        This method is called by ProjectManager after loading a project file.
        """
        logger.info("ScaleAnalysisView: Setting state from loaded project data.")
        
        # Ensure main_window_ref and project_manager are available before setting dirty
        can_set_dirty = self.main_window_ref and hasattr(self.main_window_ref, 'project_manager') and self.main_window_ref.project_manager is not None

        loaded_checkbox_states = data.get('track_global_scale_checkbox_states', {})
        self.track_global_scale_checkbox_states = {
            int(k): v for k, v in loaded_checkbox_states.items() if isinstance(v, bool)
        }
        logger.debug(f"Loaded track_global_scale_checkbox_states: {self.track_global_scale_checkbox_states}")

        loaded_mean_scale = data.get('calculated_global_mean_scale')
        if isinstance(loaded_mean_scale, (float, int)):
            self.calculated_global_mean_scale = float(loaded_mean_scale)
        elif loaded_mean_scale is None:
            self.calculated_global_mean_scale = None
        else:
            logger.warning(f"Invalid type for 'calculated_global_mean_scale' from project: {type(loaded_mean_scale)}. Resetting to None.")
            self.calculated_global_mean_scale = None
        logger.debug(f"Loaded calculated_global_mean_scale: {self.calculated_global_mean_scale}")

        loaded_std_dev = data.get('calculated_global_std_dev')
        if isinstance(loaded_std_dev, (float, int)):
            self.calculated_global_std_dev = float(loaded_std_dev)
        elif loaded_std_dev is None:
            self.calculated_global_std_dev = None
        else:
            logger.warning(f"Invalid type for 'calculated_global_std_dev' from project: {type(loaded_std_dev)}. Resetting to None.")
            self.calculated_global_std_dev = None
        logger.debug(f"Loaded calculated_global_std_dev: {self.calculated_global_std_dev}")
            
        loaded_num_tracks = data.get('num_tracks_for_global_scale', 0)
        if isinstance(loaded_num_tracks, int):
            self.num_tracks_for_global_scale = loaded_num_tracks
        else:
            logger.warning(f"Invalid type for 'num_tracks_for_global_scale' from project: {type(loaded_num_tracks)}. Resetting to 0.")
            self.num_tracks_for_global_scale = 0
        logger.debug(f"Loaded num_tracks_for_global_scale: {self.num_tracks_for_global_scale}")

        loaded_show_constrained_state = data.get('show_constrained_fits_checkbox_state', False)
        if self.show_constrained_fits_checkbox:
            # Block signals to prevent _toggle_constrained_fits_display from re-triggering project dirty
            self.show_constrained_fits_checkbox.blockSignals(True)
            self.show_constrained_fits_checkbox.setChecked(loaded_show_constrained_state if isinstance(loaded_show_constrained_state, bool) else False)
            self.show_constrained_fits_checkbox.blockSignals(False)
        logger.debug(f"Loaded show_constrained_fits_checkbox_state: {self.show_constrained_fits_checkbox.isChecked() if self.show_constrained_fits_checkbox else 'N/A'}")
        
        # selected_track_id_for_plot is intentionally not restored based on user request.

        logger.debug("ScaleAnalysisView: Internal state updated from project data. Triggering UI refreshes.")
        
        # Trigger UI updates. These should be robust to potentially incomplete data.
        self.populate_tracks_table() 
        self._update_global_scale_display_labels()
        self._update_global_scale_buttons_enabled_state() 
        # _update_main_yt_plot and _update_ancillary_plots are called by populate_tracks_table if tracks exist
        # but call them explicitly if no tracks to ensure plots clear/update based on global scale potentially
        if not (self.main_window_ref and self.main_window_ref.element_manager and \
                any(el.get('type') == ElementType.TRACK for el in self.main_window_ref.element_manager.elements)):
            self._update_main_yt_plot()
            self._update_ancillary_plots()

        # After all internal state and UI is set from loaded project data,
        # if the main window's project manager exists, set the project as clean.
        # This is typically handled by ProjectManager.mark_project_as_loaded(),
        # but this explicit call ensures it if set_scale_analysis_data_from_project
        # is the last step in applying project-specific view states.
        # However, it's better if ProjectManager itself manages the dirty state after all apply steps.
        # For now, we assume ProjectManager handles the overall dirty state after load.

    def _get_plot_color_for_track(self, track_id: int) -> QtGui.QColor:
        # Unchanged
        if not self._plot_colors:
            return QtGui.QColor("black")
        color = self._plot_colors[track_id % len(self._plot_colors)]
        return color

    def _update_main_yt_plot(self) -> None:
        # Unchanged from current state
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
        plot_item.setTitle("")

        if not (self.main_window_ref and self.main_window_ref.element_manager and
                self.main_window_ref.video_handler and self.main_window_ref.video_handler.is_loaded and
                self.main_window_ref.scale_manager): 
            logger.warning("Cannot update main_yt_plot: Core components not available/loaded.")
            plot_item.setTitle('<span style="color: black;">No video loaded or data available</span>')
            plot_item.getViewBox().autoRange()
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

        plot_item.setTitle('<span style="color: black;">Tracks y(t) - Select track in table to highlight</span>')

        show_constrained = self.show_constrained_fits_checkbox.isChecked() if self.show_constrained_fits_checkbox else False
        global_project_scale = self.main_window_ref.scale_manager.get_scale_m_per_px()
        g_val_for_constrained_fit = DEFAULT_ANALYSIS_STATE['fit_settings']['g_value_ms2']
        if self.single_track_fit_widget and self.single_track_fit_widget.g_input_lineedit:
            try:
                g_val_for_constrained_fit = float(self.single_track_fit_widget.g_input_lineedit.text())
                if g_val_for_constrained_fit <=0:
                    g_val_for_constrained_fit = DEFAULT_ANALYSIS_STATE['fit_settings']['g_value_ms2']
            except ValueError: pass 

        can_show_constrained = show_constrained and global_project_scale is not None and global_project_scale > 0

        for track_element in tracks:
            track_id = track_element.get('id')
            track_data = track_element.get('data', [])
            analysis_state = track_element.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
            if not track_data: continue

            times_s_all_points = np.array([p[1] / 1000.0 for p in track_data])
            y_pixels_tl_all_points = np.array([p[3] for p in track_data])
            y_pixels_plot_all_points = video_height - y_pixels_tl_all_points
            track_color = self._get_plot_color_for_track(track_id)
            is_selected_track = (track_id == self.current_selected_track_id_for_plot)
            symbol_size = 10 if is_selected_track else 7
            symbol_brush_color = QtGui.QColor(track_color)
            if not is_selected_track: symbol_brush_color.setAlpha(100)

            scatter_item = pg.ScatterPlotItem(x=times_s_all_points, y=y_pixels_plot_all_points,
                                              symbol='o', size=symbol_size,
                                              brush=symbol_brush_color, pen=None, data=track_id)
            scatter_item.sigClicked.connect(self._on_main_yt_plot_point_clicked)
            plot_item.addItem(scatter_item)
            if track_id not in self.track_plot_items: self.track_plot_items[track_id] = {}
            self.track_plot_items[track_id]['scatter'] = scatter_item

            fit_results = analysis_state.get('fit_results', {})
            individual_coeffs = fit_results.get('coefficients_poly2')
            if individual_coeffs and len(individual_coeffs) == 3:
                fit_settings = analysis_state.get('fit_settings', {})
                time_range_s_individual_fit = fit_settings.get('time_range_s')
                t_for_individual_curve: Optional[np.ndarray] = None
                if time_range_s_individual_fit:
                    t_min, t_max = time_range_s_individual_fit
                    if t_min < t_max: t_for_individual_curve = np.linspace(t_min, t_max, 100)
                elif len(times_s_all_points) > 1: t_for_individual_curve = np.linspace(min(times_s_all_points), max(times_s_all_points), 100)
                elif len(times_s_all_points) == 1: t_for_individual_curve = np.array([times_s_all_points[0]])

                if t_for_individual_curve is not None and len(t_for_individual_curve) > 0:
                    y_individual_curve = np.polyval(individual_coeffs, t_for_individual_curve)
                    individual_fit_pen_color = QtGui.QColor(track_color)
                    individual_fit_pen_width = 3 if is_selected_track else 1.5
                    individual_fit_pen_style = QtCore.Qt.PenStyle.SolidLine
                    if can_show_constrained: 
                        individual_fit_pen_style = QtCore.Qt.PenStyle.DotLine
                        individual_fit_pen_width *= 0.75
                    if not is_selected_track and not can_show_constrained : 
                         individual_fit_pen_color.setAlpha(120)
                    individual_fit_pen = pg.mkPen(individual_fit_pen_color, width=individual_fit_pen_width, style=individual_fit_pen_style)
                    individual_fit_curve_item = pg.PlotDataItem(x=t_for_individual_curve, y=y_individual_curve, pen=individual_fit_pen)
                    plot_item.addItem(individual_fit_curve_item)
                    self.track_plot_items[track_id]['fit_curve'] = individual_fit_curve_item

            if can_show_constrained and global_project_scale is not None : 
                fit_settings = analysis_state.get('fit_settings', {})
                excluded_frames_for_track = fit_settings.get('excluded_point_frames', [])
                time_range_s_for_track = fit_settings.get('time_range_s', None)
                points_for_constrained_fit_calc_times = []
                points_for_constrained_fit_calc_y_plot = []
                for p_idx, p_data_tuple in enumerate(track_data):
                    p_frame_idx, p_time_ms, _, p_y_tl_px = p_data_tuple
                    if p_frame_idx in excluded_frames_for_track: continue
                    p_time_s = p_time_ms / 1000.0
                    if time_range_s_for_track:
                        if not (time_range_s_for_track[0] <= p_time_s <= time_range_s_for_track[1]): continue
                    points_for_constrained_fit_calc_times.append(p_time_s)
                    points_for_constrained_fit_calc_y_plot.append(video_height - p_y_tl_px)
                if len(points_for_constrained_fit_calc_times) >= 2:
                    constrained_A = -0.5 * g_val_for_constrained_fit / global_project_scale
                    np_times = np.array(points_for_constrained_fit_calc_times)
                    np_y_plot_values = np.array(points_for_constrained_fit_calc_y_plot)
                    transformed_y_for_linear_fit = np_y_plot_values - constrained_A * (np_times**2)
                    try:
                        constrained_B_C_coeffs = np.polyfit(np_times, transformed_y_for_linear_fit, 1)
                        constrained_B, constrained_C = constrained_B_C_coeffs[0], constrained_B_C_coeffs[1]
                        t_constrained_curve_plot: Optional[np.ndarray] = None
                        if time_range_s_for_track:
                            tc_min, tc_max = time_range_s_for_track
                            if tc_min < tc_max: t_constrained_curve_plot = np.linspace(tc_min, tc_max, 100)
                        elif len(np_times) > 1: t_constrained_curve_plot = np.linspace(min(np_times), max(np_times), 100)
                        elif len(np_times) == 1: t_constrained_curve_plot = np.array([np_times[0]])
                        if t_constrained_curve_plot is not None and len(t_constrained_curve_plot) > 0:
                            y_constrained_curve = constrained_A * t_constrained_curve_plot**2 + constrained_B * t_constrained_curve_plot + constrained_C
                            constrained_pen_color = QtGui.QColor(track_color)
                            constrained_pen_width = 3.0 if is_selected_track else 2.0
                            if not is_selected_track: constrained_pen_color.setAlpha(180)
                            constrained_pen = pg.mkPen(constrained_pen_color, width=constrained_pen_width, style=QtCore.Qt.PenStyle.DashLine)
                            constrained_curve_item = pg.PlotDataItem(x=t_constrained_curve_plot, y=y_constrained_curve, pen=constrained_pen)
                            plot_item.addItem(constrained_curve_item)
                            if track_id not in self.track_plot_items: self.track_plot_items[track_id] = {}
                            self.track_plot_items[track_id]['constrained_fit_curve'] = constrained_curve_item
                    except (np.linalg.LinAlgError, ValueError) as fit_err: logger.warning(f"Track {track_id}: Error during constrained fit calc: {fit_err}")
                    except Exception as e_constr: logger.warning(f"Track {track_id}: Unexpected error plotting constrained fit: {e_constr}")
        if self._do_not_autorange_main_plot_on_next_update:
            logger.debug("Skipping autoRange for main_yt_plot due to direct plot click flag.")
            self._do_not_autorange_main_plot_on_next_update = False
        else:
            if plot_item.getViewBox(): plot_item.getViewBox().autoRange(padding=0.05)
        logger.debug("Main y(t) plot updated.")

    def populate_tracks_table(self) -> None:
        # Method body unchanged except for the checkbox setChecked line
        logger.debug("ScaleAnalysisView: populate_tracks_table called.")
        if not self.analysis_tracks_table:
            logger.warning("analysis_tracks_table is None, cannot populate.")
            return
        self.analysis_tracks_table.setRowCount(0)
        if not PYQTGRAPH_AVAILABLE:
            logger.warning("PyQtGraph not available, table population might be limited or affect dependent plots.")
        if not (self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler):
            logger.warning("ElementManager or VideoHandler not available in populate_tracks_table.")
            self._update_main_yt_plot(); self._update_ancillary_plots(); self._update_global_scale_buttons_enabled_state()
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
                    points_in_time_range_and_not_excluded = [p for p in potentially_fittable_points if min_t_fit <= (p[1] / 1000.0) <= max_t_fit]
                    num_fitted_pts = len(points_in_time_range_and_not_excluded)
                else: num_fitted_pts = len(potentially_fittable_points)
                fit_pts_str = f"{num_fitted_pts}/{total_points_in_track}"
            elif track_data: fit_pts_str = f"-/{total_points_in_track}"
            else: fit_pts_str = "-/0"
            r_squared = fit_results.get('r_squared')
            r_squared_str = f"{r_squared:.4f}" if r_squared is not None else "N/A"
            derived_scale = fit_results.get('derived_scale_m_per_px')
            fit_scale_str = f"{derived_scale:.6g}" if derived_scale is not None else "N/A"
            use_for_global_checkbox = QtWidgets.QCheckBox()
            use_for_global_checkbox.setChecked(self.track_global_scale_checkbox_states.get(track_id, False)) # MODIFIED
            use_for_global_checkbox.setProperty("track_id", track_id)
            use_for_global_checkbox.stateChanged.connect(lambda state, tid=track_id: self._on_global_scale_checkbox_changed(state, tid))
            use_for_global_checkbox.setEnabled(derived_scale is not None and derived_scale > 0)
            use_for_global_checkbox.setToolTip("Include this track's derived scale in global average calculation (if scale is valid).")
            checkbox_indicator_width = 18
            use_for_global_checkbox.setMinimumWidth(checkbox_indicator_width)
            use_for_global_checkbox.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
            checkbox_widget_container = QtWidgets.QWidget()
            checkbox_layout = QtWidgets.QHBoxLayout(checkbox_widget_container)
            checkbox_layout.setContentsMargins(0,0,0,0); checkbox_layout.setSpacing(0)
            checkbox_layout.addStretch(1); checkbox_layout.addWidget(use_for_global_checkbox); checkbox_layout.addStretch(1)
            effective_padding_each_side = 3
            container_min_width = checkbox_indicator_width + (2 * effective_padding_each_side)
            checkbox_height_hint = use_for_global_checkbox.sizeHint().height()
            if checkbox_height_hint <= 0: checkbox_height_hint = checkbox_indicator_width + 4
            checkbox_widget_container.setMinimumSize(container_min_width, checkbox_height_hint)
            checkbox_widget_container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Preferred)
            self.analysis_tracks_table.setCellWidget(row_idx, 0, checkbox_widget_container)
            id_item = QtWidgets.QTableWidgetItem(str(track_id)); id_item.setData(QtCore.Qt.ItemDataRole.UserRole, track_id)
            self.analysis_tracks_table.setItem(row_idx, 1, id_item)
            self.analysis_tracks_table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(fit_pts_str))
            self.analysis_tracks_table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(fit_scale_str))
            self.analysis_tracks_table.setItem(row_idx, 4, QtWidgets.QTableWidgetItem(r_squared_str))
            is_applied = fit_results.get('is_applied_to_project', False)
            applied_str = "Yes" if is_applied else "No"
            applied_item = QtWidgets.QTableWidgetItem(applied_str)
            self.analysis_tracks_table.setItem(row_idx, 5, applied_item)
        for r in range(self.analysis_tracks_table.rowCount()):
            for c_idx, alignment in [(1, QtCore.Qt.AlignmentFlag.AlignCenter), (2, QtCore.Qt.AlignmentFlag.AlignCenter),
                                     (3, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter),
                                     (4, QtCore.Qt.AlignmentFlag.AlignCenter), (5, QtCore.Qt.AlignmentFlag.AlignCenter)]:
                item = self.analysis_tracks_table.item(r, c_idx)
                if item: item.setTextAlignment(alignment)
        logger.info(f"Populated analysis_tracks_table with {len(tracks)} tracks.")
        self._update_main_yt_plot()
        if self.main_yt_plot:
            if not tracks and PYQTGRAPH_AVAILABLE: self.main_yt_plot.setTitle('<span style="color: black;">No tracks to plot</span>')
            self.main_yt_plot.autoRange(padding=0.05)
        self._update_ancillary_plots(); self._update_global_scale_buttons_enabled_state()

    def update_on_project_or_video_change(self, is_project_or_video_loaded: bool) -> None:
        logger.debug(f"ScaleAnalysisView: update_on_project_or_video_change called. Loaded: {is_project_or_video_loaded}")
        
        if not is_project_or_video_loaded:
            # Full reset if no project or video is loaded
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
        else:
            # Video/Project IS loaded.
            # Refresh the table and plots based on current ElementManager and internal states.
            # If a project was just loaded, set_scale_analysis_data_from_project would have
            # already populated self.track_global_scale_checkbox_states,
            # self.calculated_global_mean_scale, etc.
            # If it's a new video load (no project), these attributes would be in their default
            # (cleared) state from the call to update_on_project_or_video_change(False) during _release_video,
            # followed by scale_manager.reset() etc.
            self.populate_tracks_table()
            self._update_global_scale_display_labels() 
            # Other updates like _update_ancillary_plots are implicitly called by populate_tracks_table

        self.setEnabled(is_project_or_video_loaded and PYQTGRAPH_AVAILABLE)
        self._update_global_scale_buttons_enabled_state()
        if self.show_constrained_fits_checkbox:
            self.show_constrained_fits_checkbox.setEnabled(
                is_project_or_video_loaded and PYQTGRAPH_AVAILABLE and 
                self.main_window_ref and self.main_window_ref.scale_manager and 
                self.main_window_ref.scale_manager.get_scale_m_per_px() is not None
            )
    
    @QtCore.Slot(int, int)
    def _on_global_scale_checkbox_changed(self, state: int, track_id: int) -> None:
        is_checked = (state == QtCore.Qt.CheckState.Checked.value)
        if self.track_global_scale_checkbox_states.get(track_id) != is_checked:
            self.track_global_scale_checkbox_states[track_id] = is_checked
            logger.debug(f"Track ID {track_id} 'Use for Global' checkbox state changed to: {is_checked}")
            self._update_global_scale_buttons_enabled_state()
            if self.main_window_ref and hasattr(self.main_window_ref, 'project_manager') and self.main_window_ref.project_manager:
                self.main_window_ref.project_manager.set_project_dirty(True)

    @QtCore.Slot()
    def _calculate_global_scale(self) -> None:
        logger.info("Calculate Global Scale button clicked.")
        if not self.main_window_ref or not self.main_window_ref.element_manager:
            logger.warning("Cannot calculate global scale: MainWindow or ElementManager not available.")
            return

        old_mean = self.calculated_global_mean_scale
        old_std = self.calculated_global_std_dev
        old_n = self.num_tracks_for_global_scale

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
        self._update_ancillary_plots()
        logger.info("Called _update_ancillary_plots after global scale calculation.")

        # Check if calculated values changed, then set dirty
        changed = not (old_mean == self.calculated_global_mean_scale and \
                       old_std == self.calculated_global_std_dev and \
                       old_n == self.num_tracks_for_global_scale)
        
        if changed and self.main_window_ref and hasattr(self.main_window_ref, 'project_manager') and self.main_window_ref.project_manager:
            self.main_window_ref.project_manager.set_project_dirty(True)


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
            # set_scale in ScaleManager will emit scaleOrUnitChanged if scale actually changes,
            # which in turn will trigger set_project_dirty in MainWindow.
            self.main_window_ref.scale_manager.set_scale(
                self.calculated_global_mean_scale,
                source_description=scale_source_desc,
                std_dev=self.calculated_global_std_dev
            )            
            
            # ElementManager.update_track_analysis_state also triggers elementListChanged,
            # which MainWindow connects to set_project_dirty.
            for el in self.main_window_ref.element_manager.elements:
                if el.get('type') == ElementType.TRACK:
                    el_id = el.get('id')
                    current_analysis_state = el.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
                    if 'fit_results' not in current_analysis_state:
                        current_analysis_state['fit_results'] = copy.deepcopy(DEFAULT_ANALYSIS_STATE['fit_results'])
                    current_analysis_state['fit_results']['is_applied_to_project'] = False
                    self.main_window_ref.element_manager.update_track_analysis_state(el_id, current_analysis_state)
            
            self.populate_tracks_table()
            if self.main_window_ref.statusBar():
                self.main_window_ref.statusBar().showMessage(f"Global scale ({self.calculated_global_mean_scale:.6g} m/px) applied to project.", 5000)
            
            if self.show_constrained_fits_checkbox:
                self.show_constrained_fits_checkbox.setEnabled(True) # It becomes relevant now
            self._update_main_yt_plot()

            # Explicitly set dirty, as the combination of changes here is a significant project modification.
            if self.main_window_ref and hasattr(self.main_window_ref, 'project_manager') and self.main_window_ref.project_manager:
                self.main_window_ref.project_manager.set_project_dirty(True)
        else:
            logger.info("User cancelled applying global scale to project.")

    @QtCore.Slot(bool)
    def _toggle_constrained_fits_display(self, checked: bool) -> None:
        logger.info(f"'Show Fits Constrained by Global Scale' toggled to: {checked}")
        self._do_not_autorange_main_plot_on_next_update = True
        logger.debug("Setting _do_not_autorange_main_plot_on_next_update = True for constrained fits toggle.")
        self._update_main_yt_plot()
        if self.main_window_ref and hasattr(self.main_window_ref, 'project_manager') and self.main_window_ref.project_manager:
            self.main_window_ref.project_manager.set_project_dirty(True)
    
    def _update_global_scale_display_labels(self) -> None: 
        # Unchanged
        if self.mean_global_scale_label: self.mean_global_scale_label.setText(f"{self.calculated_global_mean_scale:.6g}" if self.calculated_global_mean_scale is not None else "N/A")
        if self.std_dev_global_scale_label: self.std_dev_global_scale_label.setText(f"{self.calculated_global_std_dev:.2g}" if self.calculated_global_std_dev is not None else "N/A")
        if self.n_tracks_global_scale_label: self.n_tracks_global_scale_label.setText(str(self.num_tracks_for_global_scale))

    def _update_global_scale_buttons_enabled_state(self) -> None:
        # Unchanged
        can_calculate = any(self.track_global_scale_checkbox_states.values())
        video_loaded_and_pyqtgraph = PYQTGRAPH_AVAILABLE and self.main_window_ref and self.main_window_ref.video_handler and self.main_window_ref.video_handler.is_loaded
        if self.calculate_global_scale_button: self.calculate_global_scale_button.setEnabled(can_calculate and video_loaded_and_pyqtgraph)
        can_apply = self.calculated_global_mean_scale is not None
        if self.apply_global_scale_button: self.apply_global_scale_button.setEnabled(can_apply and video_loaded_and_pyqtgraph)
        can_show_constrained = video_loaded_and_pyqtgraph and (self.main_window_ref.scale_manager is not None and self.main_window_ref.scale_manager.get_scale_m_per_px() is not None)
        if self.show_constrained_fits_checkbox:
            self.show_constrained_fits_checkbox.setEnabled(can_show_constrained)
            if not can_show_constrained and self.show_constrained_fits_checkbox.isChecked(): self.show_constrained_fits_checkbox.setChecked(False)

    @QtCore.Slot()
    def _on_analysis_table_selection_changed(self) -> None: 
        # Unchanged
        if not self.analysis_tracks_table: return
        selected_items = self.analysis_tracks_table.selectedItems(); newly_selected_track_id: Optional[int] = None
        if selected_items:
            selected_row = self.analysis_tracks_table.row(selected_items[0])
            id_item = self.analysis_tracks_table.item(selected_row, 1) 
            if id_item:
                track_id_data = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(track_id_data, int): newly_selected_track_id = track_id_data 
        if self.current_selected_track_id_for_plot != newly_selected_track_id:
            self.current_selected_track_id_for_plot = newly_selected_track_id 
            self._update_main_yt_plot() 
        if self.single_track_fit_widget and self.main_window_ref and self.main_window_ref.element_manager and self.main_window_ref.video_handler:
            if newly_selected_track_id is not None:
                track_to_load = next((el for el in self.main_window_ref.element_manager.elements if el.get('id') == newly_selected_track_id and el.get('type') == ElementType.TRACK), None)
                if track_to_load: self.single_track_fit_widget.load_track_data(copy.deepcopy(track_to_load), self.main_window_ref.video_handler.fps, self.main_window_ref.video_handler.frame_height)
                else: self.single_track_fit_widget.clear_and_disable()
            else: self.single_track_fit_widget.clear_and_disable()

    @QtCore.Slot(object, list) 
    def _on_main_yt_plot_point_clicked(self, scatter_plot_item: pg.ScatterPlotItem, spot_items: List[pg.SpotItem]) -> None: 
        # Unchanged
        if not spot_items or not self.analysis_tracks_table: return
        clicked_spot_data = spot_items[0].data() 
        if not isinstance(clicked_spot_data, int): logger.warning(f"Clicked spot has non-integer data: {clicked_spot_data}"); return
        clicked_track_id = clicked_spot_data; logger.debug(f"Point clicked on main_yt_plot for track ID: {clicked_track_id}")
        for r in range(self.analysis_tracks_table.rowCount()):
            id_item = self.analysis_tracks_table.item(r, 1)
            if id_item and id_item.data(QtCore.Qt.ItemDataRole.UserRole) == clicked_track_id:
                current_selected_row = self.analysis_tracks_table.currentRow() if self.analysis_tracks_table.selectedItems() else -1
                if current_selected_row != r:
                    self._do_not_autorange_main_plot_on_next_update = True
                    logger.debug("Setting _do_not_autorange_main_plot_on_next_update = True due to main_yt_plot click.")
                    self.analysis_tracks_table.selectRow(r)
                else: logger.debug(f"Row {r} for track ID {clicked_track_id} is already selected.")
                break

    def _get_track_fit_summary_data(self, track_element: Dict) -> Optional[Dict]:
        # Unchanged from current state
        if not (self.main_window_ref and self.main_window_ref.video_handler and self.main_window_ref.video_handler.is_loaded):
            logger.warning("_get_track_fit_summary_data: Video not loaded, cannot calculate summary.")
            return None
        track_id = track_element.get('id'); analysis_state = track_element.get('analysis_state', {}); fit_results = analysis_state.get('fit_results', {}); fit_settings = analysis_state.get('fit_settings', {}); track_data = track_element.get('data', [])
        derived_scale = fit_results.get('derived_scale_m_per_px'); coefficients = fit_results.get('coefficients_poly2')
        if derived_scale is None or coefficients is None or not track_data: logger.debug(f"Track ID {track_id}: No valid derived scale, coefficients, or no track data. Skipping summary."); return None
        excluded_frames = fit_settings.get('excluded_point_frames', []); time_range_s_setting = fit_settings.get('time_range_s', None)
        fitted_points_info = [] 
        for point_tuple in track_data:
            frame_idx, time_ms, x_tl_px, y_tl_px = point_tuple
            if frame_idx in excluded_frames: continue
            time_s = time_ms / 1000.0
            if time_range_s_setting and not (time_range_s_setting[0] <= time_s <= time_range_s_setting[1]): continue
            fitted_points_info.append((time_s, x_tl_px, y_tl_px))
        if not fitted_points_info: logger.debug(f"Track ID {track_id}: No points remained after filtering. Skipping summary."); return None
        times_s_fitted = np.array([p[0] for p in fitted_points_info]); x_tl_px_fitted_avg = float(np.mean(np.array([p[1] for p in fitted_points_info]))); y_tl_px_fitted_avg = float(np.mean(np.array([p[2] for p in fitted_points_info])))
        avg_time_s = float(np.mean(times_s_fitted))
        video_h = self.main_window_ref.video_handler.frame_height; centroid_x_plot_px = x_tl_px_fitted_avg; centroid_y_plot_px = video_h - y_tl_px_fitted_avg if video_h > 0 else y_tl_px_fitted_avg
        video_width = self.main_window_ref.video_handler.frame_width; center_x_px = video_width / 2.0; center_y_px = video_h / 2.0
        radial_pos_px = math.sqrt((x_tl_px_fitted_avg - center_x_px)**2 + (y_tl_px_fitted_avg - center_y_px)**2)
        summary = {'track_id': track_id, 'derived_scale': derived_scale, 'avg_time_s': avg_time_s, 'centroid_x_px': centroid_x_plot_px, 'centroid_y_px': centroid_y_plot_px, 'radial_pos_px': radial_pos_px}
        logger.debug(f"Track ID {track_id}: Fit summary calculated (Centroid for plot is BL): {summary}"); return summary

    def _clear_all_ancillary_plots(self) -> None:
        # Unchanged
        ancillary_plots = [self.scale_vs_time_plot, self.scale_vs_centroid_x_plot, self.scale_vs_centroid_y_plot, self.scale_vs_radial_pos_plot, self.scale_histogram_plot, self.scale_cdf_plot]
        for plot in ancillary_plots:
            if plot: plot.clear() 
        logger.debug("Cleared all ancillary plots.")

    def _update_ancillary_plots(self) -> None:
        if not PYQTGRAPH_AVAILABLE:
            return

        logger.debug("ScaleAnalysisView: Updating ancillary plots with full-span Mean/SD.")
        self._clear_all_ancillary_plots()

        if not (self.main_window_ref and self.main_window_ref.element_manager):
            logger.warning("Cannot update ancillary plots: ElementManager not available.")
            for plot_attr_name in ["scale_vs_time_plot", "scale_vs_centroid_x_plot",
                                   "scale_vs_centroid_y_plot", "scale_vs_radial_pos_plot",
                                   "scale_histogram_plot", "scale_cdf_plot"]:
                plot_widget = getattr(self, plot_attr_name, None)
                if plot_widget: plot_widget.autoRange()
            return

        fit_summaries: List[Dict] = []
        for track_element in self.main_window_ref.element_manager.elements:
            if track_element.get('type') == ElementType.TRACK:
                summary = self._get_track_fit_summary_data(track_element)
                if summary and summary.get('derived_scale') is not None:
                    fit_summaries.append(summary)

        if not fit_summaries:
            logger.debug("No valid fit summaries for ancillary plots.")
            for plot_attr_name in ["scale_vs_time_plot", "scale_vs_centroid_x_plot",
                                   "scale_vs_centroid_y_plot", "scale_vs_radial_pos_plot",
                                   "scale_histogram_plot", "scale_cdf_plot"]:
                plot_widget = getattr(self, plot_attr_name, None)
                if plot_widget: plot_widget.autoRange()
            return

        track_ids_all = [s['track_id'] for s in fit_summaries]
        scales_all = np.array([s['derived_scale'] for s in fit_summaries])
        avg_times = np.array([s['avg_time_s'] for s in fit_summaries])
        centroid_xs = np.array([s['centroid_x_px'] for s in fit_summaries])
        centroid_ys = np.array([s['centroid_y_px'] for s in fit_summaries])
        radial_positions = np.array([s['radial_pos_px'] for s in fit_summaries])
        point_brushes_all = [self._get_plot_color_for_track(tid) for tid in track_ids_all]

        mean_scale = self.calculated_global_mean_scale
        std_dev_scale = self.calculated_global_std_dev
        plot_mean_sd_visuals = mean_scale is not None and std_dev_scale is not None

        global_mean_pen = pg.mkPen(color='black', width=2, style=QtCore.Qt.PenStyle.SolidLine)
        global_sd_line_pen = pg.mkPen(color=(80, 80, 80, 200), width=1, style=QtCore.Qt.PenStyle.DashLine)
        global_sd_band_brush = QtGui.QBrush(QtGui.QColor(150, 150, 150, 50)) 

        scatter_plot_configs = [
            (self.scale_vs_time_plot, avg_times, "scale vs time"),
            (self.scale_vs_centroid_x_plot, centroid_xs, "scale vs centroid x"),
            (self.scale_vs_centroid_y_plot, centroid_ys, "scale vs centroid y"),
            (self.scale_vs_radial_pos_plot, radial_positions, "scale vs radial pos")
        ]

        for plot_widget, x_data_array, plot_name_for_log in scatter_plot_configs:
            if plot_widget:
                plot_item = plot_widget.getPlotItem()
                if not plot_item: continue
                logger.debug(f"Populating {plot_name_for_log} with full-span mean/SD overlays.")
                items_to_add = []
                if len(x_data_array) > 0:
                    scatter_item = pg.ScatterPlotItem(x=x_data_array, y=scales_all, data=track_ids_all,
                                                      symbol='o', size=8, brush=point_brushes_all, pen=None)
                    scatter_item.setZValue(0)
                    # --- MODIFICATION: Connect to the correct existing handler ---
                    scatter_item.sigClicked.connect(self._on_main_yt_plot_point_clicked) 
                    # --- END MODIFICATION ---
                    items_to_add.append(scatter_item)

                if plot_mean_sd_visuals and mean_scale is not None and std_dev_scale is not None:
                    if std_dev_scale > 0:
                        sd_region_horizontal = pg.LinearRegionItem(
                            values=[mean_scale - std_dev_scale, mean_scale + std_dev_scale],
                            orientation='horizontal', brush=global_sd_band_brush,
                            pen=pg.mkPen(None), movable=False, bounds=None )
                        sd_region_horizontal.setZValue(-20); items_to_add.append(sd_region_horizontal)
                    sd_upper_line = pg.InfiniteLine(pos=(mean_scale + std_dev_scale), angle=0, pen=global_sd_line_pen, movable=False)
                    sd_lower_line = pg.InfiniteLine(pos=(mean_scale - std_dev_scale), angle=0, pen=global_sd_line_pen, movable=False)
                    sd_upper_line.setZValue(-15); sd_lower_line.setZValue(-15)
                    items_to_add.append(sd_upper_line); items_to_add.append(sd_lower_line)
                    mean_line_horizontal = pg.InfiniteLine(pos=mean_scale, angle=0, pen=global_mean_pen, movable=False)
                    mean_line_horizontal.setZValue(-10); items_to_add.append(mean_line_horizontal)
                for item in items_to_add: plot_item.addItem(item)
                plot_widget.autoRange()

        if self.scale_histogram_plot and len(scales_all) > 0:
            logger.debug("Updating scale histogram plot with mean/SD (vertical).")
            plot_item_hist = self.scale_histogram_plot.getPlotItem()
            if plot_item_hist:
                items_hist = []
                num_bins = min(max(5, int(np.sqrt(len(scales_all)))), 20)
                hist_counts, bin_edges = np.histogram(scales_all, bins=num_bins)
                bin_width = bin_edges[1] - bin_edges[0] if len(bin_edges) > 1 else 1.0
                bar_item = pg.BarGraphItem(x=bin_edges[:-1], height=hist_counts, width=bin_width * 0.9, brush='cornflowerblue')
                bar_item.setZValue(0); items_hist.append(bar_item)
                if plot_mean_sd_visuals and mean_scale is not None and std_dev_scale is not None:
                    if std_dev_scale > 0:
                        sd_region_hist = pg.LinearRegionItem(
                            values=[mean_scale - std_dev_scale, mean_scale + std_dev_scale],
                            orientation='vertical', brush=global_sd_band_brush, pen=pg.mkPen(None), movable=False)
                        sd_region_hist.setZValue(-20); items_hist.append(sd_region_hist)
                    sd_plus_line_hist = pg.InfiniteLine(pos=mean_scale + std_dev_scale, angle=90, pen=global_sd_line_pen, movable=False)
                    sd_minus_line_hist = pg.InfiniteLine(pos=mean_scale - std_dev_scale, angle=90, pen=global_sd_line_pen, movable=False)
                    sd_plus_line_hist.setZValue(-15); sd_minus_line_hist.setZValue(-15)
                    items_hist.append(sd_plus_line_hist); items_hist.append(sd_minus_line_hist)
                    mean_line_hist = pg.InfiniteLine(pos=mean_scale, angle=90, pen=global_mean_pen, movable=False)
                    mean_line_hist.setZValue(-10); items_hist.append(mean_line_hist)
                for item in items_hist: plot_item_hist.addItem(item)
                self.scale_histogram_plot.autoRange()

        if self.scale_cdf_plot and len(scales_all) > 0:
            logger.debug("Updating scale CDF plot with mean/SD (vertical).")
            plot_item_cdf = self.scale_cdf_plot.getPlotItem()
            if plot_item_cdf:
                items_cdf = []
                combined_scale_trackid = sorted(zip(scales_all, track_ids_all), key=lambda pair: pair[0])
                sorted_individual_scales = np.array([pair[0] for pair in combined_scale_trackid])
                track_ids_for_cdf_points = [pair[1] for pair in combined_scale_trackid]
                y_cdf_individual = np.arange(1, len(sorted_individual_scales) + 1) / len(sorted_individual_scales)
                connecting_line_pen = pg.mkPen(color=(150, 150, 150, 200), width=1.5, style=QtCore.Qt.PenStyle.DotLine)
                cdf_line_item = pg.PlotDataItem(x=sorted_individual_scales, y=y_cdf_individual, pen=connecting_line_pen)
                cdf_line_item.setZValue(0); items_cdf.append(cdf_line_item)
                cdf_point_brushes = [self._get_plot_color_for_track(tid) for tid in track_ids_for_cdf_points]
                cdf_scatter_points_item = pg.ScatterPlotItem(x=sorted_individual_scales, y=y_cdf_individual,
                                                             data=track_ids_for_cdf_points, symbol='o', size=8,
                                                             pen=None, brush=cdf_point_brushes)
                cdf_scatter_points_item.setZValue(1)
                # --- MODIFICATION: Connect to the correct existing handler ---
                cdf_scatter_points_item.sigClicked.connect(self._on_main_yt_plot_point_clicked)
                # --- END MODIFICATION ---
                items_cdf.append(cdf_scatter_points_item)
                if plot_mean_sd_visuals and mean_scale is not None and std_dev_scale is not None:
                    if std_dev_scale > 0:
                        sd_region_cdf = pg.LinearRegionItem(
                            values=[mean_scale - std_dev_scale, mean_scale + std_dev_scale],
                            orientation='vertical', brush=global_sd_band_brush, pen=pg.mkPen(None), movable=False)
                        sd_region_cdf.setZValue(-20); items_cdf.append(sd_region_cdf)
                    sd_plus_line_cdf = pg.InfiniteLine(pos=mean_scale + std_dev_scale, angle=90, pen=global_sd_line_pen, movable=False)
                    sd_minus_line_cdf = pg.InfiniteLine(pos=mean_scale - std_dev_scale, angle=90, pen=global_sd_line_pen, movable=False)
                    sd_plus_line_cdf.setZValue(-15); sd_minus_line_cdf.setZValue(-15)
                    items_cdf.append(sd_plus_line_cdf); items_cdf.append(sd_minus_line_cdf)
                    mean_line_cdf = pg.InfiniteLine(pos=mean_scale, angle=90, pen=global_mean_pen, movable=False)
                    mean_line_cdf.setZValue(-10); items_cdf.append(mean_line_cdf)
                for item in items_cdf: plot_item_cdf.addItem(item)
                self.scale_cdf_plot.setYRange(0, 1.05, padding=0)
                if len(sorted_individual_scales) > 0:
                    min_x_cdf, max_x_cdf = min(sorted_individual_scales), max(sorted_individual_scales)
                    padding_cdf_val = 0.05 * (max_x_cdf - min_x_cdf) if max_x_cdf > min_x_cdf else 0.1 * abs(min_x_cdf) if abs(min_x_cdf) > 1e-9 else 0.1
                    self.scale_cdf_plot.setXRange(min_x_cdf - padding_cdf_val, max_x_cdf + padding_cdf_val)
                else: self.scale_cdf_plot.autoRange()
        logger.debug("Finished updating ancillary plots with full-span Mean/SD and harmonized SD lines.")

    @QtCore.Slot(int, dict)
    def _handle_save_track_analysis(self, track_id: int, analysis_state_dict: Dict) -> None:
        # Unchanged
        logger.info(f"ScaleAnalysisView: Received request to save analysis for Track ID {track_id}.")
        if self.main_window_ref and self.main_window_ref.element_manager:
            success = self.main_window_ref.element_manager.update_track_analysis_state(track_id, analysis_state_dict)
            if success:
                logger.info(f"Analysis state for Track ID {track_id} updated in ElementManager.")
                self.populate_tracks_table(); self._update_main_yt_plot() 
                if self.main_window_ref.statusBar(): self.main_window_ref.statusBar().showMessage(f"Analysis for Track {track_id} saved.", 3000)
            else:
                logger.error(f"Failed to update analysis state for Track ID {track_id} in ElementManager.")
                QtWidgets.QMessageBox.warning(self, "Save Error", f"Could not save analysis for Track {track_id}.")
        else: logger.error("Cannot save track analysis: MainWindow or ElementManager not available.")

    @QtCore.Slot(int, float)
    def _handle_apply_track_scale(self, track_id: int, derived_scale: float) -> None:
        # Unchanged
        logger.info(f"ScaleAnalysisView: Received request to apply scale {derived_scale:.6g} m/px from Track ID {track_id}.")
        if not (self.main_window_ref and self.main_window_ref.scale_manager and self.main_window_ref.element_manager):
            logger.error("Cannot apply track scale: Core managers not available."); return
        reply = QtWidgets.QMessageBox.question(self, "Apply Scale to Project",
            f"Apply derived scale ({derived_scale:.6g} m/px) from Track {track_id} to the entire project?\nThis will override any existing project scale and clear any manually drawn scale line.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No, QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            scale_source_desc = f"Track {track_id} Parabolic Fit"
            self.main_window_ref.scale_manager.set_scale(derived_scale, source_description=scale_source_desc)
            for el in self.main_window_ref.element_manager.elements:
                if el.get('type') == ElementType.TRACK:
                    el_id = el.get('id'); current_analysis_state = el.get('analysis_state', copy.deepcopy(DEFAULT_ANALYSIS_STATE))
                    current_analysis_state['fit_results']['is_applied_to_project'] = (el_id == track_id)
                    self.main_window_ref.element_manager.update_track_analysis_state(el_id, current_analysis_state)
            self.populate_tracks_table(); self._update_main_yt_plot() 
            if self.main_window_ref.statusBar(): self.main_window_ref.statusBar().showMessage(f"Scale from Track {track_id} applied to project.", 5000)
        else: logger.info("User cancelled applying scale from track to project.")

    # --- NEW METHOD for ProjectManager to set state ---
    def set_scale_analysis_data_from_project(self, data: Dict[str, Any]) -> None:
        """
        Sets the internal state of the ScaleAnalysisView from loaded project data.
        This method is called by ProjectManager after loading a project file.
        """
        logger.info("ScaleAnalysisView: Setting state from loaded project data.")
        self.track_global_scale_checkbox_states = {
            int(k): v for k, v in data.get('track_global_scale_checkbox_states', {}).items() if isinstance(v, bool)
        }
        
        self.calculated_global_mean_scale = data.get('calculated_global_mean_scale')
        if not isinstance(self.calculated_global_mean_scale, (float, int, type(None))):
            logger.warning(f"Invalid type for 'calculated_global_mean_scale' from project: {type(self.calculated_global_mean_scale)}. Resetting to None.")
            self.calculated_global_mean_scale = None
            
        self.calculated_global_std_dev = data.get('calculated_global_std_dev')
        if not isinstance(self.calculated_global_std_dev, (float, int, type(None))):
            logger.warning(f"Invalid type for 'calculated_global_std_dev' from project: {type(self.calculated_global_std_dev)}. Resetting to None.")
            self.calculated_global_std_dev = None

        self.num_tracks_for_global_scale = data.get('num_tracks_for_global_scale', 0)
        if not isinstance(self.num_tracks_for_global_scale, int):
            logger.warning(f"Invalid type for 'num_tracks_for_global_scale' from project: {type(self.num_tracks_for_global_scale)}. Resetting to 0.")
            self.num_tracks_for_global_scale = 0

        show_constrained_state = data.get('show_constrained_fits_checkbox_state', False)
        if self.show_constrained_fits_checkbox:
            self.show_constrained_fits_checkbox.setChecked(show_constrained_state if isinstance(show_constrained_state, bool) else False)
        
        # selected_track_id_for_plot is intentionally not restored based on user request.
        # self.current_selected_track_id_for_plot = data.get('selected_track_id_for_plot') 
        # if not isinstance(self.current_selected_track_id_for_plot, (int, type(None))):
        #     self.current_selected_track_id_for_plot = None

        logger.debug("ScaleAnalysisView: Internal state updated from project data. Triggering UI refreshes.")
        
        # Trigger UI updates. These should be robust to potentially incomplete data.
        self.populate_tracks_table() # This will use the loaded checkbox states
        self._update_global_scale_display_labels()
        self._update_global_scale_buttons_enabled_state() 
        # _update_main_yt_plot and _update_ancillary_plots are called by populate_tracks_table
        
        # If a track was previously selected for analysis, and it still exists, re-select it.
        # (This part is skipped based on user request to not save selected track)
        # if self.current_selected_track_id_for_plot is not None and self.analysis_tracks_table:
        #     found_row = -1
        #     for r in range(self.analysis_tracks_table.rowCount()):
        #         id_item = self.analysis_tracks_table.item(r, 1) # ID column
        #         if id_item and id_item.data(QtCore.Qt.ItemDataRole.UserRole) == self.current_selected_track_id_for_plot:
        #             found_row = r; break
        #     if found_row != -1:
        #         self.analysis_tracks_table.selectRow(found_row)
        #     else: # Previously selected track no longer exists or table empty
        #         self.current_selected_track_id_for_plot = None 
        #         if self.single_track_fit_widget: self.single_track_fit_widget.clear_and_disable()
        # elif self.single_track_fit_widget: # No track was selected, ensure fit widget is clear
        #      self.single_track_fit_widget.clear_and_disable()