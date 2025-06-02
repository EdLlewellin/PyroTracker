# project_manager.py
"""
Manages the overall project state, including orchestrating the saving
and loading of project files in JSON format.
"""
import logging
import json
import os
from typing import TYPE_CHECKING, Dict, Any, Optional, Tuple, List

# Import PySide6 QtCore for signals
from PySide6 import QtCore

import config # For APP_NAME, APP_VERSION, and metadata keys
from coordinates import CoordinateSystem
import file_io

if TYPE_CHECKING:
    from main_window import MainWindow
    from element_manager import ElementManager
    from scale_manager import ScaleManager
    from coordinate_transformer import CoordinateTransformer
    from settings_manager import SettingsManager
    # --- Add ScaleAnalysisView for type hinting ---
    from scale_analysis_view import ScaleAnalysisView


logger = logging.getLogger(__name__)

class ProjectManager(QtCore.QObject):
    unsavedChangesStateChanged = QtCore.Signal(bool)

    def __init__(self,
                 element_manager: 'ElementManager',
                 scale_manager: 'ScaleManager',
                 coord_transformer: 'CoordinateTransformer',
                 settings_manager: 'SettingsManager',
                 main_window_ref: 'MainWindow'):
        super().__init__()
        self._element_manager = element_manager
        self._scale_manager = scale_manager
        self._coord_transformer = coord_transformer
        self._settings_manager = settings_manager
        self._main_window_ref = main_window_ref

        self._current_project_filepath: Optional[str] = None
        self._has_unsaved_changes: bool = False
        self._is_loading_project: bool = False

        logger.info("ProjectManager initialized.")

    def get_current_project_filepath(self) -> Optional[str]:
        """Returns the file path of the currently open project, if any."""
        return self._current_project_filepath

    def _set_current_project_filepath(self, filepath: Optional[str]) -> None:
        """Sets the current project file path."""
        self._current_project_filepath = filepath
        logger.info(f"Current project file path set to: {filepath}")

    def project_has_unsaved_changes(self) -> bool:
        """Returns True if there are unsaved changes, False otherwise."""
        return self._has_unsaved_changes

    def set_project_dirty(self, dirty: bool = True) -> None:
        """
        Sets the project's dirty state (unsaved changes).
        Emits unsavedChangesStateChanged signal if the state changes.
        Ignores attempts to set dirty if _is_loading_project is True,
        unless explicitly setting to False.
        """
        if self._is_loading_project and dirty is True:
            logger.debug("ProjectManager: Ignoring set_project_dirty(True) because project is loading.")
            return

        if self._has_unsaved_changes != dirty:
            self._has_unsaved_changes = dirty
            logger.info(f"Project dirty state set to: {dirty}")
            self.unsavedChangesStateChanged.emit(self._has_unsaved_changes)

    def mark_project_as_saved(self, filepath: str) -> None:
        """
        Called after a successful save operation. Updates the current file path
        and clears the dirty flag.
        """
        self._set_current_project_filepath(filepath)
        self.set_project_dirty(False)

    def mark_project_as_loaded(self, filepath: str) -> None:
        """
        Called after successfully loading a project. Updates the current file path
        and clears the dirty flag.
        """
        self._set_current_project_filepath(filepath)
        if self._has_unsaved_changes is True:
            self._has_unsaved_changes = False
            logger.info(f"Project dirty state set to: False (after load)")
            self.unsavedChangesStateChanged.emit(False)
        elif self._has_unsaved_changes is False:
            logger.info(f"Project dirty state remains: False (after load), ensuring UI sync.")
            self.unsavedChangesStateChanged.emit(False)

    def clear_project_state_for_close(self) -> None:
        """
        Resets the project file path and dirty flag, typically when closing a project.
        """
        self._set_current_project_filepath(None)
        self.set_project_dirty(False)
        logger.info("Project state (filepath, dirty flag) cleared for close.")

    def gather_project_state_dict(self) -> Dict[str, Any]:
        """
        Gathers all necessary data from various managers to create a comprehensive
        project state dictionary suitable for JSON serialization.

        Returns:
            Dict[str, Any]: The complete project state dictionary.
        """
        logger.debug("Gathering project state for saving...")
        project_state: Dict[str, Any] = {}

        # 1. Project Info
        project_state['project_info'] = {
            'app_name': config.APP_NAME,
            'app_version': config.APP_VERSION,
        }

        # 2. Metadata (unchanged)
        metadata: Dict[str, Any] = {}
        if self._main_window_ref.video_handler and self._main_window_ref.video_handler.is_loaded:
            video_info = self._main_window_ref.video_handler.get_video_info()
            metadata[config.META_FILENAME] = video_info.get('filename', 'N/A')
            metadata[config.META_WIDTH] = video_info.get('width', 0)
            metadata[config.META_HEIGHT] = video_info.get('height', 0)
            metadata[config.META_FRAMES] = video_info.get('total_frames', 0)
            metadata[config.META_FPS] = video_info.get('fps', 0.0)
            metadata[config.META_DURATION] = video_info.get('duration_ms', 0.0)
        else:
            metadata[config.META_FILENAME] = "N/A"; metadata[config.META_WIDTH] = 0
            metadata[config.META_HEIGHT] = 0; metadata[config.META_FRAMES] = 0
            metadata[config.META_FPS] = 0.0; metadata[config.META_DURATION] = 0.0

        coord_meta = self._coord_transformer.get_metadata()
        metadata[config.META_COORD_SYSTEM_MODE] = coord_meta.get('mode', 'TOP_LEFT')
        metadata[config.META_COORD_ORIGIN_X_TL] = coord_meta.get('origin_x_tl', 0.0)
        metadata[config.META_COORD_ORIGIN_Y_TL] = coord_meta.get('origin_y_tl', 0.0)
        current_meta_height = metadata.get(config.META_HEIGHT, 0)
        metadata[config.META_HEIGHT] = coord_meta.get('video_height', current_meta_height)

        metadata[config.META_SCALE_FACTOR_M_PER_PX] = self._scale_manager.get_scale_m_per_px()
        metadata['display_in_meters'] = self._scale_manager.display_in_meters()
        defined_scale_line = self._scale_manager.get_defined_scale_line_data()
        if defined_scale_line:
            metadata[config.META_SCALE_LINE_P1X], metadata[config.META_SCALE_LINE_P1Y], \
            metadata[config.META_SCALE_LINE_P2X], metadata[config.META_SCALE_LINE_P2Y] = defined_scale_line
        else:
            metadata[config.META_SCALE_LINE_P1X] = metadata[config.META_SCALE_LINE_P1Y] = \
            metadata[config.META_SCALE_LINE_P2X] = metadata[config.META_SCALE_LINE_P2Y] = "N/A"
        metadata[config.META_DATA_UNITS] = "px"

        if hasattr(self._main_window_ref, 'showScaleLineCheckBox') and self._main_window_ref.showScaleLineCheckBox is not None:
            metadata['ui_show_scale_line_checkbox'] = self._main_window_ref.showScaleLineCheckBox.isChecked()
        if hasattr(self._main_window_ref, 'scale_display_meters_checkbox') and self._main_window_ref.scale_display_meters_checkbox is not None:
            metadata['ui_scale_display_meters_checkbox'] = self._main_window_ref.scale_display_meters_checkbox.isChecked()
        if hasattr(self._main_window_ref, 'showScaleBarCheckBox') and self._main_window_ref.showScaleBarCheckBox is not None:
            metadata['ui_show_scale_bar_checkbox'] = self._main_window_ref.showScaleBarCheckBox.isChecked()
        if hasattr(self._main_window_ref, 'showOriginCheckBox') and self._main_window_ref.showOriginCheckBox is not None:
            metadata['ui_show_origin_checkbox'] = self._main_window_ref.showOriginCheckBox.isChecked()

        if self._main_window_ref.view_menu_controller and \
           self._main_window_ref.view_menu_controller.viewShowMeasurementLineLengthsAction:
            metadata[config.META_SHOW_MEASUREMENT_LINE_LENGTHS] = self._main_window_ref.view_menu_controller.viewShowMeasurementLineLengthsAction.isChecked()
        else:
            metadata[config.META_SHOW_MEASUREMENT_LINE_LENGTHS] = self._settings_manager.get_setting(
                config.META_SHOW_MEASUREMENT_LINE_LENGTHS
            )
        if self._main_window_ref.view_menu_controller:
            if self._main_window_ref.view_menu_controller.viewShowFilenameAction:
                 metadata['ui_view_show_filename'] = self._main_window_ref.view_menu_controller.viewShowFilenameAction.isChecked()
            if self._main_window_ref.view_menu_controller.viewShowTimeAction:
                 metadata['ui_view_show_time'] = self._main_window_ref.view_menu_controller.viewShowTimeAction.isChecked()
            if self._main_window_ref.view_menu_controller.viewShowFrameNumberAction:
                 metadata['ui_view_show_frame_number'] = self._main_window_ref.view_menu_controller.viewShowFrameNumberAction.isChecked()
        project_state['metadata'] = metadata

        # 3. Elements (unchanged)
        project_state['elements'] = self._element_manager.get_all_elements_for_project_save()

        # --- NEW: 4. Scale Analysis State ---
        scale_analysis_state_data: Dict[str, Any] = {}
        if self._main_window_ref.scale_analysis_view:
            sav: 'ScaleAnalysisView' = self._main_window_ref.scale_analysis_view
            
            # Convert integer keys of checkbox states to strings for JSON
            json_compatible_checkbox_states = {str(k): v for k, v in sav.track_global_scale_checkbox_states.items()}
            scale_analysis_state_data['track_global_scale_checkbox_states'] = json_compatible_checkbox_states
            
            scale_analysis_state_data['calculated_global_mean_scale'] = sav.calculated_global_mean_scale
            scale_analysis_state_data['calculated_global_std_dev'] = sav.calculated_global_std_dev
            scale_analysis_state_data['num_tracks_for_global_scale'] = sav.num_tracks_for_global_scale
            
            if sav.show_constrained_fits_checkbox:
                scale_analysis_state_data['show_constrained_fits_checkbox_state'] = sav.show_constrained_fits_checkbox.isChecked()
            else:
                scale_analysis_state_data['show_constrained_fits_checkbox_state'] = False # Default if checkbox doesn't exist
        else:
            logger.warning("ScaleAnalysisView not found on MainWindow, cannot gather its state for saving.")
            # Provide default empty/null structure if view is not available
            scale_analysis_state_data['track_global_scale_checkbox_states'] = {}
            scale_analysis_state_data['calculated_global_mean_scale'] = None
            scale_analysis_state_data['calculated_global_std_dev'] = None
            scale_analysis_state_data['num_tracks_for_global_scale'] = 0
            scale_analysis_state_data['show_constrained_fits_checkbox_state'] = False

        project_state['scale_analysis_state'] = scale_analysis_state_data
        # --- END NEW ---

        logger.debug(f"Project state gathered. Top-level keys: {list(project_state.keys())}")
        return project_state

    def save_project(self, filepath: str) -> bool:
        """
        Gathers the current project state and writes it to a JSON file.
        Also updates the current project path and clears the dirty flag on success.

        Args:
            filepath: The path to save the JSON project file.

        Returns:
            bool: True if saving was successful, False otherwise.
        """
        logger.info(f"Attempting to save project to: {filepath}")
        try:
            project_data_dict = self.gather_project_state_dict()
            file_io.write_project_json_file(filepath, project_data_dict) # Use module directly
            self.mark_project_as_saved(filepath)
            logger.info(f"Project successfully saved to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error saving project to {filepath}: {e}", exc_info=True)
            return False

    def load_project_file_data(self, filepath: str) -> Optional[Dict[str, Any]]:
        """
        Reads a project JSON file and returns its content as a dictionary.
        """
        logger.info(f"ProjectManager: Reading project file data from: {filepath}")
        try:
            loaded_state_dict = file_io.read_project_json_file(filepath)
            if not loaded_state_dict:
                logger.error(f"ProjectManager: Failed to read or parse project file contents: {filepath}")
                return None
            logger.info(f"ProjectManager: Successfully read project file data from: {filepath}")
            return loaded_state_dict
        except FileNotFoundError:
            logger.error(f"ProjectManager: Project file not found during read: {filepath}", exc_info=True)
            raise
        except json.JSONDecodeError as e:
            logger.error(f"ProjectManager: Error decoding JSON from project file '{filepath}' during read: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"ProjectManager: Unexpected error reading project file '{filepath}': {e}", exc_info=True)
            raise

    def apply_project_state(self,
                            loaded_state_dict: Dict[str, Any],
                            actual_video_loaded_in_main: bool,
                            actual_video_width: int,
                            actual_video_height: int,
                            actual_total_frames: int,
                            actual_fps: float
                            ) -> bool:
        self._is_loading_project = True # Set flag at the beginning of apply
        logger.info("Applying loaded project data (settings, elements, and scale analysis state)...")
        project_metadata = loaded_state_dict.get('metadata', {})
        if not project_metadata:
            logger.error("Loaded project state is missing 'metadata' section. Cannot apply settings.")
            if self._main_window_ref.statusBar():
                self._main_window_ref.statusBar().showMessage("Project load error: Missing metadata section.", 5000)
            self._is_loading_project = False # Reset flag on early exit
            return False

        apply_warnings: List[str] = []

        # Video Metadata Consistency Check (unchanged)
        saved_video_filename_meta = project_metadata.get(config.META_FILENAME)
        saved_video_width_meta = project_metadata.get(config.META_WIDTH)
        saved_video_height_meta = project_metadata.get(config.META_HEIGHT)
        saved_frame_count_meta = project_metadata.get(config.META_FRAMES)

        if actual_video_loaded_in_main:
            current_video_filename = os.path.basename(self._main_window_ref.video_filepath) if self._main_window_ref.video_filepath else "N/A"
            if saved_video_filename_meta != "N/A" and saved_video_filename_meta != current_video_filename:
                apply_warnings.append(f"Project's saved video filename ('{saved_video_filename_meta}') differs from loaded ('{current_video_filename}').")
            if saved_video_width_meta is not None and saved_video_width_meta != actual_video_width:
                apply_warnings.append(f"Project video width meta ({saved_video_width_meta}) mismatches loaded ({actual_video_width}).")
            if saved_video_height_meta is not None and saved_video_height_meta != actual_video_height:
                 apply_warnings.append(f"Project video height meta for coords ({saved_video_height_meta}) mismatches loaded video height ({actual_video_height}).")
            if saved_frame_count_meta is not None and saved_frame_count_meta != actual_total_frames:
                apply_warnings.append(f"Project frame count meta ({saved_frame_count_meta}) mismatches loaded ({actual_total_frames}).")
        elif saved_video_filename_meta and saved_video_filename_meta != "N/A":
            apply_warnings.append(f"Project metadata indicates video '{saved_video_filename_meta}', but it is not currently loaded in the application.")

        # Apply Coordinate System Settings (unchanged)
        coord_mode_str = project_metadata.get(config.META_COORD_SYSTEM_MODE)
        coord_origin_x_tl = project_metadata.get(config.META_COORD_ORIGIN_X_TL)
        coord_origin_y_tl = project_metadata.get(config.META_COORD_ORIGIN_Y_TL)
        self._coord_transformer.set_video_height(actual_video_height)
        loaded_coord_mode = CoordinateSystem.from_string(coord_mode_str) if coord_mode_str else CoordinateSystem.TOP_LEFT
        self._coord_transformer.set_mode(loaded_coord_mode)
        if loaded_coord_mode == CoordinateSystem.CUSTOM and coord_origin_x_tl is not None and coord_origin_y_tl is not None:
            try: self._coord_transformer.set_custom_origin(float(coord_origin_x_tl), float(coord_origin_y_tl))
            except ValueError: apply_warnings.append("Invalid custom origin coords. Using default."); self._coord_transformer.set_custom_origin(0.0, 0.0)

        # Apply Scale Settings (unchanged)
        scale_m_per_px_val = project_metadata.get(config.META_SCALE_FACTOR_M_PER_PX)
        if isinstance(scale_m_per_px_val, str) and scale_m_per_px_val.lower() == "n/a": scale_m_per_px_val = None
        elif scale_m_per_px_val is not None:
            try: scale_m_per_px_val = float(scale_m_per_px_val)
            except ValueError: scale_m_per_px_val = None; apply_warnings.append("Invalid scale factor. Not set.")
        p1x_str = project_metadata.get(config.META_SCALE_LINE_P1X); p1y_str = project_metadata.get(config.META_SCALE_LINE_P1Y)
        p2x_str = project_metadata.get(config.META_SCALE_LINE_P2X); p2y_str = project_metadata.get(config.META_SCALE_LINE_P2Y)
        parsed_scale_line_coords: Optional[Tuple[float,float,float,float]] = None
        if all(s not in [None, "N/A", ""] for s in [p1x_str, p1y_str, p2x_str, p2y_str]):
            try: parsed_scale_line_coords = (float(p1x_str), float(p1y_str), float(p2x_str), float(p2y_str))
            except (ValueError, TypeError): apply_warnings.append("Invalid scale line coords. Ignored.")
        if parsed_scale_line_coords:
            self._scale_manager.set_defined_scale_line(*parsed_scale_line_coords)
            self._scale_manager.set_scale(scale_m_per_px_val, called_from_line_definition=True)
        else:
            self._scale_manager.clear_defined_scale_line()
            self._scale_manager.set_scale(scale_m_per_px_val, called_from_line_definition=False)

        # Apply UI Toggle Settings (unchanged for most part, added type safety)
        logger.debug("Applying UI toggle states from project metadata...")
        def get_bool_from_meta(key: str, default: bool) -> bool:
            val = project_metadata.get(key, default)
            if isinstance(val, bool): return val
            if isinstance(val, str): return val.lower() == 'true'
            return default

        ui_show_sl_val = get_bool_from_meta('ui_show_scale_line_checkbox', False)
        if self._main_window_ref.showScaleLineCheckBox is not None:
            self._main_window_ref.showScaleLineCheckBox.setChecked(ui_show_sl_val)
            if self._main_window_ref.scale_panel_controller: self._main_window_ref.scale_panel_controller._on_show_defined_scale_line_toggled(ui_show_sl_val)

        ui_disp_m_val = get_bool_from_meta('ui_scale_display_meters_checkbox', False)
        self._scale_manager.set_display_in_meters(ui_disp_m_val)
        if self._main_window_ref.scale_display_meters_checkbox is not None:
            self._main_window_ref.scale_display_meters_checkbox.setChecked(self._scale_manager.display_in_meters())

        ui_show_sb_val = get_bool_from_meta('ui_show_scale_bar_checkbox', False)
        if self._main_window_ref.showScaleBarCheckBox is not None:
            self._main_window_ref.showScaleBarCheckBox.setChecked(ui_show_sb_val)
            if self._main_window_ref.scale_panel_controller: self._main_window_ref.scale_panel_controller._on_show_scale_bar_toggled(ui_show_sb_val)

        ui_show_origin_val = get_bool_from_meta('ui_show_origin_checkbox', True)
        if self._main_window_ref.showOriginCheckBox is not None:
            self._main_window_ref.showOriginCheckBox.setChecked(ui_show_origin_val)
            if self._main_window_ref.coord_panel_controller: self._main_window_ref.coord_panel_controller._on_toggle_show_origin(QtCore.Qt.CheckState.Checked.value if ui_show_origin_val else QtCore.Qt.CheckState.Unchecked.value)
        
        show_lengths_val = get_bool_from_meta(config.META_SHOW_MEASUREMENT_LINE_LENGTHS, True)
        self._settings_manager.set_setting(config.META_SHOW_MEASUREMENT_LINE_LENGTHS, show_lengths_val)
        for key_ui, key_setting_const in [
            ('ui_view_show_filename', self._settings_manager.KEY_INFO_OVERLAY_SHOW_FILENAME),
            ('ui_view_show_time', self._settings_manager.KEY_INFO_OVERLAY_SHOW_TIME),
            ('ui_view_show_frame_number', self._settings_manager.KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER)
        ]:
            self._settings_manager.set_setting(key_setting_const, get_bool_from_meta(key_ui, True))

        # Load Elements (unchanged)
        elements_to_load = loaded_state_dict.get('elements', [])
        video_context_width_for_elements = actual_video_width
        video_context_height_for_elements = actual_video_height
        video_context_frames_for_elements = actual_total_frames
        video_context_fps_for_elements = actual_fps
        if video_context_width_for_elements <= 0 or video_context_height_for_elements <= 0 or video_context_frames_for_elements <= 0:
             apply_warnings.append("Video context for element validation is invalid. Point validation may be unreliable.")
        _success_elements, element_warnings = self._element_manager.load_elements_from_project_data(
            elements_to_load, video_context_width_for_elements, video_context_height_for_elements,
            video_context_frames_for_elements, video_context_fps_for_elements
        )
        apply_warnings.extend(element_warnings)

        # --- NEW: Apply Scale Analysis State ---
        loaded_scale_analysis_state = loaded_state_dict.get('scale_analysis_state')
        if loaded_scale_analysis_state and isinstance(loaded_scale_analysis_state, dict) and self._main_window_ref.scale_analysis_view:
            sav: 'ScaleAnalysisView' = self._main_window_ref.scale_analysis_view
            
            # Checkbox states for tracks used in global scale
            cb_states_str_keys = loaded_scale_analysis_state.get('track_global_scale_checkbox_states', {})
            sav.track_global_scale_checkbox_states = {int(k): v for k, v in cb_states_str_keys.items() if isinstance(v, bool)}
            
            sav.calculated_global_mean_scale = loaded_scale_analysis_state.get('calculated_global_mean_scale')
            if not isinstance(sav.calculated_global_mean_scale, (float, int, type(None))): sav.calculated_global_mean_scale = None # Ensure None if invalid type
            
            sav.calculated_global_std_dev = loaded_scale_analysis_state.get('calculated_global_std_dev')
            if not isinstance(sav.calculated_global_std_dev, (float, int, type(None))): sav.calculated_global_std_dev = None

            sav.num_tracks_for_global_scale = loaded_scale_analysis_state.get('num_tracks_for_global_scale', 0)
            if not isinstance(sav.num_tracks_for_global_scale, int): sav.num_tracks_for_global_scale = 0
            
            show_constrained_state = loaded_scale_analysis_state.get('show_constrained_fits_checkbox_state', False)
            if sav.show_constrained_fits_checkbox:
                 sav.show_constrained_fits_checkbox.setChecked(show_constrained_state if isinstance(show_constrained_state, bool) else False)
            
            # Note: selected_track_id_for_plot is not being restored per user request.

            # After setting these, ScaleAnalysisView needs to update its UI
            # This might happen via populate_tracks_table and other update methods in ScaleAnalysisView,
            # which should be called after all project state is applied in MainWindow.
            logger.info("Scale analysis state data applied to ScaleAnalysisView attributes.")
        elif loaded_scale_analysis_state:
            logger.warning("ScaleAnalysisView not available, cannot apply loaded scale analysis state.")
        # --- END NEW ---

        if hasattr(self._main_window_ref, '_project_load_warnings') and isinstance(self._main_window_ref._project_load_warnings, list):
            self._main_window_ref._project_load_warnings.extend(apply_warnings)
        else:
            logger.warning("MainWindow missing '_project_load_warnings' list attribute. Load warnings not passed back.")

        # self._is_loading_project will be reset by MainWindow after all UI updates
        logger.info("Project data application processed by ProjectManager.")
        return True