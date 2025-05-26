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
        # --- NEW ATTRIBUTE ---
        self._is_loading_project: bool = False
        # --- END NEW ATTRIBUTE ---

        logger.info("ProjectManager initialized.")

    # --- NEW METHODS for managing project state ---
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
        # --- MODIFIED ---
        if self._is_loading_project and dirty is True:
            logger.debug("ProjectManager: Ignoring set_project_dirty(True) because project is loading.")
            return 
        # --- END MODIFIED ---

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
        # Explicitly set dirty to False, bypassing the _is_loading_project check in set_project_dirty
        if self._has_unsaved_changes is True: # Only change and emit if it was true
            self._has_unsaved_changes = False
            logger.info(f"Project dirty state set to: False (after load)")
            self.unsavedChangesStateChanged.emit(False)
        elif self._has_unsaved_changes is False:
             # If it's already false, ensure the signal still fires to update UI like window title
             # that might have been set to dirty by initial UI updates from default values.
            logger.info(f"Project dirty state remains: False (after load), ensuring UI sync.")
            self.unsavedChangesStateChanged.emit(False)

    def clear_project_state_for_close(self) -> None:
        """
        Resets the project file path and dirty flag, typically when closing a project.
        """
        self._set_current_project_filepath(None)
        self.set_project_dirty(False) # No unsaved changes for a non-existent/closed project
        logger.info("Project state (filepath, dirty flag) cleared for close.")
    # --- END NEW METHODS ---

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
            # Could add save_timestamp here if desired
        }

        # 2. Metadata
        metadata: Dict[str, Any] = {}

        # Video properties from MainWindow/VideoHandler
        if self._main_window_ref.video_handler and self._main_window_ref.video_handler.is_loaded:
            video_info = self._main_window_ref.video_handler.get_video_info()
            metadata[config.META_FILENAME] = video_info.get('filename', 'N/A')
            metadata[config.META_WIDTH] = video_info.get('width', 0)
            metadata[config.META_HEIGHT] = video_info.get('height', 0)
            metadata[config.META_FRAMES] = video_info.get('total_frames', 0)
            metadata[config.META_FPS] = video_info.get('fps', 0.0)
            metadata[config.META_DURATION] = video_info.get('duration_ms', 0.0)
        else: # Default values if no video is loaded (should ideally not happen when saving a project)
            metadata[config.META_FILENAME] = "N/A"
            metadata[config.META_WIDTH] = 0
            metadata[config.META_HEIGHT] = 0
            metadata[config.META_FRAMES] = 0
            metadata[config.META_FPS] = 0.0
            metadata[config.META_DURATION] = 0.0

        # CoordinateTransformer state
        coord_meta = self._coord_transformer.get_metadata() # Relies on CoordinateTransformer.get_metadata()
        metadata[config.META_COORD_SYSTEM_MODE] = coord_meta.get('mode', 'TOP_LEFT') # Default if not found
        metadata[config.META_COORD_ORIGIN_X_TL] = coord_meta.get('origin_x_tl', 0.0)
        metadata[config.META_COORD_ORIGIN_Y_TL] = coord_meta.get('origin_y_tl', 0.0)
        # Store the video_height that coord_transformer is currently using for its context
        # Ensure the key META_HEIGHT in metadata gets the value from coord_meta if available,
        # otherwise keeps the value set from video_info (which might be 0 if no video loaded)
        current_meta_height = metadata.get(config.META_HEIGHT, 0) # Get height already in metadata (from video_info)
        metadata[config.META_HEIGHT] = coord_meta.get('video_height', current_meta_height)


        # ScaleManager state
        metadata[config.META_SCALE_FACTOR_M_PER_PX] = self._scale_manager.get_scale_m_per_px() # Can be None
        metadata['display_in_meters'] = self._scale_manager.display_in_meters() # Store boolean preference
        
        defined_scale_line = self._scale_manager.get_defined_scale_line_data()
        if defined_scale_line:
            metadata[config.META_SCALE_LINE_P1X] = defined_scale_line[0]
            metadata[config.META_SCALE_LINE_P1Y] = defined_scale_line[1]
            metadata[config.META_SCALE_LINE_P2X] = defined_scale_line[2]
            metadata[config.META_SCALE_LINE_P2Y] = defined_scale_line[3]
        else: # Explicitly store N/A or omit if preferred not to store if not set
            metadata[config.META_SCALE_LINE_P1X] = "N/A"
            metadata[config.META_SCALE_LINE_P1Y] = "N/A"
            metadata[config.META_SCALE_LINE_P2X] = "N/A"
            metadata[config.META_SCALE_LINE_P2Y] = "N/A"

        # Data units for element point data being saved
        metadata[config.META_DATA_UNITS] = "px"

        # Relevant global settings from SettingsManager
        # Example:
        # For Feature 1 (UI Toggles):
        # Scale Panel Toggles
        if hasattr(self._main_window_ref, 'showScaleLineCheckBox') and self._main_window_ref.showScaleLineCheckBox is not None:
            metadata['ui_show_scale_line_checkbox'] = self._main_window_ref.showScaleLineCheckBox.isChecked()
        if hasattr(self._main_window_ref, 'scale_display_meters_checkbox') and self._main_window_ref.scale_display_meters_checkbox is not None:
            metadata['ui_scale_display_meters_checkbox'] = self._main_window_ref.scale_display_meters_checkbox.isChecked()
        if hasattr(self._main_window_ref, 'showScaleBarCheckBox') and self._main_window_ref.showScaleBarCheckBox is not None:
            metadata['ui_show_scale_bar_checkbox'] = self._main_window_ref.showScaleBarCheckBox.isChecked()

        # Coordinate Panel Toggles
        if hasattr(self._main_window_ref, 'showOriginCheckBox') and self._main_window_ref.showOriginCheckBox is not None:
            metadata['ui_show_origin_checkbox'] = self._main_window_ref.showOriginCheckBox.isChecked()
        
        # View Menu related (backed by SettingsManager, but we can snapshot their effective state for the project)
        # These reflect the *visual state at save time* for these specific project-level overrides,
        # separate from the user's global defaults saved by SettingsManager.
        # For META_SHOW_MEASUREMENT_LINE_LENGTHS, it's better to get this from where it's controlled
        # if a ViewMenuController action directly reflects this.
        # If it's just a setting, then getting from settings_manager is okay.
        if self._main_window_ref.view_menu_controller and \
           self._main_window_ref.view_menu_controller.viewShowMeasurementLineLengthsAction:
            metadata[config.META_SHOW_MEASUREMENT_LINE_LENGTHS] = self._main_window_ref.view_menu_controller.viewShowMeasurementLineLengthsAction.isChecked()
        else: # Fallback to the global setting if view controller/action not available
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
        # Add other global settings here as needed

        project_state['metadata'] = metadata

        # 3. Elements
        project_state['elements'] = self._element_manager.get_all_elements_for_project_save()

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
            project_data_dict = self.gather_project_state_dict() #
            
            from file_io import write_project_json_file
            write_project_json_file(filepath, project_data_dict)
            
            self.mark_project_as_saved(filepath) # Update path and clear dirty flag
            logger.info(f"Project successfully saved to {filepath}")
            return True
        except Exception as e: # Catch potential exceptions from gather_project_state_dict or write_project_json_file
            logger.error(f"Error saving project to {filepath}: {e}", exc_info=True)
            return False


    # NEW: Simpler method to just read project file data
    def load_project_file_data(self, filepath: str) -> Optional[Dict[str, Any]]:
        """
        Reads a project JSON file and returns its content as a dictionary.
        This is the first step of loading, done before video loading in MainWindow.
        """
        logger.info(f"ProjectManager: Reading project file data from: {filepath}")
        try:
            # Ensure file_io is imported if not already at the top of project_manager.py
            # from file_io import read_project_json_file
            loaded_state_dict = file_io.read_project_json_file(filepath) # Ensure file_io is imported
    
            if not loaded_state_dict:
                logger.error(f"ProjectManager: Failed to read or parse project file contents: {filepath}")
                return None
            logger.info(f"ProjectManager: Successfully read project file data from: {filepath}")
            return loaded_state_dict
        except FileNotFoundError: # Be specific about exceptions from read_project_json_file
            logger.error(f"ProjectManager: Project file not found during read: {filepath}", exc_info=True)
            raise # Re-raise to be caught by MainWindow
        except json.JSONDecodeError as e: # Be specific
            logger.error(f"ProjectManager: Error decoding JSON from project file '{filepath}' during read: {e}", exc_info=True)
            raise # Re-raise
        except Exception as e: # Catch-all for other unexpected errors from read_project_json_file
            logger.error(f"ProjectManager: Unexpected error reading project file '{filepath}': {e}", exc_info=True)
            raise # Re-raise


    def apply_project_state(self,
                            loaded_state_dict: Dict[str, Any],
                            # Video context provided by MainWindow after attempting to load video
                            actual_video_loaded_in_main: bool,
                            actual_video_width: int,
                            actual_video_height: int, # This is the height used for Y-inversion of Coordsys
                            actual_total_frames: int,
                            actual_fps: float
                            ) -> bool:
        # _is_loading_project is assumed to be True, set by MainWindow before calling this sequence
    
        logger.info("Applying loaded project data (settings and elements)...")
        project_metadata = loaded_state_dict.get('metadata', {})
        if not project_metadata:
            logger.error("Loaded project state is missing 'metadata' section. Cannot apply settings.")
            if self._main_window_ref.statusBar(): # Access MainWindow ref for status bar
                self._main_window_ref.statusBar().showMessage("Project load error: Missing metadata section.", 5000)
            return False
    
        # Use a local list for warnings specific to this application stage
        apply_warnings: List[str] = []
    
        # Video Metadata Consistency Check (warnings only)
        saved_video_filename_meta = project_metadata.get(config.META_FILENAME)
        saved_video_width_meta = project_metadata.get(config.META_WIDTH) # video width from project file meta
        saved_video_height_meta = project_metadata.get(config.META_HEIGHT) # video height from project file meta (for coord context)
        saved_frame_count_meta = project_metadata.get(config.META_FRAMES)
    
        if actual_video_loaded_in_main:
            # Video is actually loaded in MainWindow, compare against its live properties
            # Ensure self._main_window_ref.video_filepath is correctly set by _handle_video_loaded
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
            # Project specified a video, but MainWindow couldn't load it
            apply_warnings.append(f"Project metadata indicates video '{saved_video_filename_meta}', but it is not currently loaded in the application.")
        
        # Apply Coordinate System Settings
        coord_mode_str = project_metadata.get(config.META_COORD_SYSTEM_MODE)
        coord_origin_x_tl = project_metadata.get(config.META_COORD_ORIGIN_X_TL)
        coord_origin_y_tl = project_metadata.get(config.META_COORD_ORIGIN_Y_TL)
        
        # Ensure CoordTransformer uses the correct height (from loaded video, or project meta if video failed)
        # actual_video_height is passed from MainWindow and should be the definitive height for coord context.
        self._coord_transformer.set_video_height(actual_video_height) #
        
        loaded_coord_mode = CoordinateSystem.from_string(coord_mode_str) if coord_mode_str else CoordinateSystem.TOP_LEFT #
        self._coord_transformer.set_mode(loaded_coord_mode) # Emits signals if changed, guarded by _is_loading_project
        if loaded_coord_mode == CoordinateSystem.CUSTOM and coord_origin_x_tl is not None and coord_origin_y_tl is not None: #
            try:
                self._coord_transformer.set_custom_origin(float(coord_origin_x_tl), float(coord_origin_y_tl)) # Also emits
            except ValueError:
                apply_warnings.append("Invalid custom origin coordinates in project. Using default (0,0) for custom mode.")
                self._coord_transformer.set_custom_origin(0.0, 0.0) #
        
        # Apply Scale Settings
        scale_m_per_px_val = project_metadata.get(config.META_SCALE_FACTOR_M_PER_PX)
        if isinstance(scale_m_per_px_val, str) and scale_m_per_px_val.lower() == "n/a": scale_m_per_px_val = None
        elif scale_m_per_px_val is not None:
            try: scale_m_per_px_val = float(scale_m_per_px_val)
            except ValueError: scale_m_per_px_val = None; apply_warnings.append("Invalid scale factor in project. Scale not set.")
    
        p1x_str = project_metadata.get(config.META_SCALE_LINE_P1X); p1y_str = project_metadata.get(config.META_SCALE_LINE_P1Y)
        p2x_str = project_metadata.get(config.META_SCALE_LINE_P2X); p2y_str = project_metadata.get(config.META_SCALE_LINE_P2Y)
        parsed_scale_line_coords: Optional[Tuple[float,float,float,float]] = None
        if all(s not in [None, "N/A", ""] for s in [p1x_str, p1y_str, p2x_str, p2y_str]):
            try:
                parsed_scale_line_coords = (float(p1x_str), float(p1y_str), float(p2x_str), float(p2y_str))
            except (ValueError, TypeError): apply_warnings.append("Invalid scale line coordinate format. Defined line ignored.")
        
        if parsed_scale_line_coords:
            self._scale_manager.set_defined_scale_line(*parsed_scale_line_coords) # Emits if state changes
            self._scale_manager.set_scale(scale_m_per_px_val, called_from_line_definition=True) # Emits
        else:
            self._scale_manager.clear_defined_scale_line() # Emits if state changes
            self._scale_manager.set_scale(scale_m_per_px_val, called_from_line_definition=False) # Emits
        
        # Apply UI Toggle Settings from Project
        logger.debug("Applying UI toggle states from project metadata by updating SettingsManager and UI components...")
    
        # Scale Panel Toggles - These are set directly on MainWindow's checkboxes
        # Their toggled signals are connected to set_project_dirty, but _is_loading_project will guard this.
        # The controller's _on_..._toggled method should also be called to ensure consistency if the setChecked causes a visual change.
        
        ui_show_sl_val = bool(project_metadata.get('ui_show_scale_line_checkbox', False))
        if self._main_window_ref.showScaleLineCheckBox is not None:
            self._main_window_ref.showScaleLineCheckBox.blockSignals(True)
            self._main_window_ref.showScaleLineCheckBox.setChecked(ui_show_sl_val)
            self._main_window_ref.showScaleLineCheckBox.blockSignals(False)
            # Manually trigger controller's update logic if ScalePanelController exists
            if self._main_window_ref.scale_panel_controller:
                self._main_window_ref.scale_panel_controller._on_show_defined_scale_line_toggled(ui_show_sl_val)
    
        ui_disp_m_val = bool(project_metadata.get('ui_scale_display_meters_checkbox', False))
        self._scale_manager.set_display_in_meters(ui_disp_m_val) # This will emit scaleOrUnitChanged
        if self._main_window_ref.scale_display_meters_checkbox is not None:
            self._main_window_ref.scale_display_meters_checkbox.blockSignals(True)
            self._main_window_ref.scale_display_meters_checkbox.setChecked(self._scale_manager.display_in_meters())
            self._main_window_ref.scale_display_meters_checkbox.blockSignals(False)
    
        ui_show_sb_val = bool(project_metadata.get('ui_show_scale_bar_checkbox', False))
        if self._main_window_ref.showScaleBarCheckBox is not None:
            self._main_window_ref.showScaleBarCheckBox.blockSignals(True)
            self._main_window_ref.showScaleBarCheckBox.setChecked(ui_show_sb_val)
            self._main_window_ref.showScaleBarCheckBox.blockSignals(False)
            if self._main_window_ref.scale_panel_controller:
                self._main_window_ref.scale_panel_controller._on_show_scale_bar_toggled(ui_show_sb_val)
    
        # Coordinate Panel Toggles
        ui_show_origin_val = bool(project_metadata.get('ui_show_origin_checkbox', True))
        if self._main_window_ref.showOriginCheckBox is not None:
            self._main_window_ref.showOriginCheckBox.blockSignals(True)
            self._main_window_ref.showOriginCheckBox.setChecked(ui_show_origin_val)
            self._main_window_ref.showOriginCheckBox.blockSignals(False)
            if self._main_window_ref.coord_panel_controller:
                 self._main_window_ref.coord_panel_controller._on_toggle_show_origin(
                     QtCore.Qt.CheckState.Checked.value if ui_show_origin_val else QtCore.Qt.CheckState.Unchecked.value
                 )
        
        # View Menu / Global Settings (these update SettingsManager)
        show_lengths_val_str = project_metadata.get(config.META_SHOW_MEASUREMENT_LINE_LENGTHS) #
        if isinstance(show_lengths_val_str, bool): show_lengths_val = show_lengths_val_str
        elif isinstance(show_lengths_val_str, str): show_lengths_val = show_lengths_val_str.lower() == 'true'
        else: show_lengths_val = True # Default
        self._settings_manager.set_setting(config.META_SHOW_MEASUREMENT_LINE_LENGTHS, show_lengths_val) #
    
        for key_ui, key_setting_const in [ # Use the constants from settings_manager
            ('ui_view_show_filename', self._settings_manager.KEY_INFO_OVERLAY_SHOW_FILENAME),
            ('ui_view_show_time', self._settings_manager.KEY_INFO_OVERLAY_SHOW_TIME),
            ('ui_view_show_frame_number', self._settings_manager.KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER)
        ]:
            val = bool(project_metadata.get(key_ui, True)) # Default to True if not in project
            self._settings_manager.set_setting(key_setting_const, val)
    
    
        # Load Elements
        elements_to_load = loaded_state_dict.get('elements', [])
        
        # Use actual video parameters passed from MainWindow for element validation
        video_context_width_for_elements = actual_video_width
        video_context_height_for_elements = actual_video_height
        video_context_frames_for_elements = actual_total_frames
        video_context_fps_for_elements = actual_fps
    
        if video_context_width_for_elements <= 0 or video_context_height_for_elements <= 0 or video_context_frames_for_elements <= 0:
             apply_warnings.append("Video context for element validation is invalid (dimensions/frames are zero or negative). Point validation may be unreliable.")
        
        _success_elements, element_warnings = self._element_manager.load_elements_from_project_data( #
            elements_to_load,
            video_width=video_context_width_for_elements,
            video_height=video_context_height_for_elements, 
            video_frame_count=video_context_frames_for_elements,
            video_fps=video_context_fps_for_elements
        ) #
        apply_warnings.extend(element_warnings) #
        
        # Store warnings to be retrieved by MainWindow
        if hasattr(self._main_window_ref, '_project_load_warnings') and isinstance(self._main_window_ref._project_load_warnings, list):
            self._main_window_ref._project_load_warnings.extend(apply_warnings)
        else: # Fallback if attribute is missing or wrong type
            logger.warning("MainWindow missing '_project_load_warnings' list attribute. Load warnings not passed back.")
    
    
        logger.info("Project data application processed by ProjectManager.")
        return True


        return True