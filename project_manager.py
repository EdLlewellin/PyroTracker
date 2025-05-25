# project_manager.py
"""
Manages the overall project state, including orchestrating the saving
and loading of project files in JSON format.
"""
import logging
import json
import os
from typing import TYPE_CHECKING, Dict, Any, Optional, Tuple

import config # For APP_NAME, APP_VERSION, and metadata keys
from coordinates import CoordinateSystem # MODIFIED: Added this import

# Remove the commented-out line below if file_io.write_project_json_file exists
# from file_io import write_project_json_file 

if TYPE_CHECKING:
    from main_window import MainWindow
    from element_manager import ElementManager
    from scale_manager import ScaleManager
    from coordinate_transformer import CoordinateTransformer # This was already here, but CoordinateSystem was missing

    from settings_manager import SettingsManager 

logger = logging.getLogger(__name__)

class ProjectManager:
    def __init__(self,
                 element_manager: 'ElementManager',
                 scale_manager: 'ScaleManager',
                 coord_transformer: 'CoordinateTransformer',
                 settings_manager: 'SettingsManager', # Added SettingsManager
                 main_window_ref: 'MainWindow'):
        """
        Initializes the ProjectManager.

        Args:
            element_manager: Instance of ElementManager.
            scale_manager: Instance of ScaleManager.
            coord_transformer: Instance of CoordinateTransformer.
            settings_manager: Instance of SettingsManager.
            main_window_ref: Reference to the MainWindow instance.
        """
        self._element_manager = element_manager
        self._scale_manager = scale_manager
        self._coord_transformer = coord_transformer
        self._settings_manager = settings_manager # Store SettingsManager
        self._main_window_ref = main_window_ref
        logger.info("ProjectManager initialized.")

    def gather_project_state_dict(self) -> Dict[str, Any]:
        """
        Gathers all necessary data from various managers to create a comprehensive
        project state dictionary suitable for JSON serialization.

        Returns:
            Dict[str, Any]: The complete project state dictionary.
        """
        logger.debug("Gathering project state for saving...")
        project_state: Dict[str, Any] = {}

        # 1. Project Info [cite: 26]
        project_state['project_info'] = {
            'app_name': config.APP_NAME,
            'app_version': config.APP_VERSION,
            # Could add save_timestamp here if desired
        }

        # 2. Metadata [cite: 27, 28, 29, 30]
        metadata: Dict[str, Any] = {}

        # Video properties from MainWindow/VideoHandler [cite: 27]
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

        # CoordinateTransformer state [cite: 28]
        coord_meta = self._coord_transformer.get_metadata() # Relies on CoordinateTransformer.get_metadata()
        metadata[config.META_COORD_SYSTEM_MODE] = coord_meta.get('mode', 'TOP_LEFT') # Default if not found
        metadata[config.META_COORD_ORIGIN_X_TL] = coord_meta.get('origin_x_tl', 0.0)
        metadata[config.META_COORD_ORIGIN_Y_TL] = coord_meta.get('origin_y_tl', 0.0)
        # Store the video_height that coord_transformer is currently using for its context
        metadata[config.META_HEIGHT] = coord_meta.get('video_height', metadata[config.META_HEIGHT])


        # ScaleManager state [cite: 28]
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

        # Data units for element point data being saved [cite: 29]
        metadata[config.META_DATA_UNITS] = "px"

        # Relevant global settings from SettingsManager [cite: 30]
        # Example:
        metadata[config.META_SHOW_MEASUREMENT_LINE_LENGTHS] = self._settings_manager.get_setting(
            config.META_SHOW_MEASUREMENT_LINE_LENGTHS # Using the key directly from config
        )
        # Add other global settings here as needed

        project_state['metadata'] = metadata

        # 3. Elements [cite: 30]
        project_state['elements'] = self._element_manager.get_all_elements_for_project_save()

        logger.debug(f"Project state gathered. Top-level keys: {list(project_state.keys())}")
        return project_state

    def save_project(self, filepath: str) -> bool:
        """
        Gathers the current project state and writes it to a JSON file.

        Args:
            filepath: The path to save the JSON project file.

        Returns:
            bool: True if saving was successful, False otherwise.
        """
        logger.info(f"Attempting to save project to: {filepath}")
        try:
            project_data_dict = self.gather_project_state_dict() # [cite: 31]
            
            # This function will be defined in file_io.py in the next step [cite: 32]
            # For now, we can simulate its part of the logic here or just call it
            # Placeholder for the actual file writing:
            from file_io import write_project_json_file # Temporary import for structure
            write_project_json_file(filepath, project_data_dict)
            
            logger.info(f"Project successfully saved to {filepath}")
            return True
        except Exception as e: # Catch potential exceptions from gather_project_state_dict or write_project_json_file [cite: 32]
            logger.error(f"Error saving project to {filepath}: {e}", exc_info=True)
            # Consider emitting a signal or returning error message for MainWindow to display
            return False


    def load_project(self, filepath: str) -> bool:
        """
        Loads a project state from a JSON file and applies it.

        Args:
            filepath: The path to the JSON project file.

        Returns:
            bool: True if loading and applying the project was successful, False otherwise.
        """
        logger.info(f"Attempting to load project from: {filepath}")
        try:
            # Import here to avoid circular dependency at module level if ProjectManager is imported by file_io
            from file_io import read_project_json_file
            loaded_state_dict = read_project_json_file(filepath) # [cite: 48]
            
            if not loaded_state_dict: # Should be caught by read_project_json_file re-raising
                logger.error(f"Failed to read or parse project file: {filepath}")
                return False

            return self.apply_project_state(loaded_state_dict) # [cite: 49]
        except FileNotFoundError:
            logger.error(f"Project file not found: {filepath}")
            self._main_window_ref.statusBar().showMessage(f"Error: Project file not found: {os.path.basename(filepath)}", 5000)
            return False
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from project file: {filepath}")
            self._main_window_ref.statusBar().showMessage(f"Error: Invalid project file format: {os.path.basename(filepath)}", 5000)
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during project load: {e}", exc_info=True)
            self._main_window_ref.statusBar().showMessage(f"Error loading project: {str(e)}", 5000)
            return False

    def apply_project_state(self, loaded_state_dict: Dict[str, Any]) -> bool:
        """
        Applies the loaded project state (settings and elements) to the application's components.
        Assumes MainWindow has already prepared/reset managers as needed
        and that the correct video (if specified in project) is loaded and active.
        """
        logger.info("Applying loaded project data (settings and elements)...")
        
        project_metadata = loaded_state_dict.get('metadata', {})
        if not project_metadata:
            logger.error("Loaded project state is missing 'metadata' section. Cannot apply settings.")
            self._main_window_ref.statusBar().showMessage("Project load error: Missing metadata section.", 5000)
            return False

        warnings = []

        # --- Video Metadata Consistency Check (warnings only) ---
        saved_video_filename = project_metadata.get(config.META_FILENAME)
        saved_video_width = project_metadata.get(config.META_WIDTH)
        saved_video_height_for_coord_context = project_metadata.get(config.META_HEIGHT) 
        saved_frame_count = project_metadata.get(config.META_FRAMES)
        
        if self._main_window_ref.video_loaded:
            current_video_info = self._main_window_ref.video_handler.get_video_info()
            if saved_video_filename != "N/A" and saved_video_filename != current_video_info.get('filename'):
                warnings.append(f"Project's saved video filename ('{saved_video_filename}') differs from loaded ('{current_video_info.get('filename')}').")
            if saved_video_width is not None and saved_video_width != current_video_info.get('width'):
                warnings.append(f"Project video width ({saved_video_width}) mismatches loaded ({current_video_info.get('width')}).")
            if saved_video_height_for_coord_context is not None and saved_video_height_for_coord_context != current_video_info.get('height'):
                 warnings.append(f"Project metadata video height ({saved_video_height_for_coord_context}) for coordinate context mismatches loaded video height ({current_video_info.get('height')}).")
            if saved_frame_count is not None and saved_frame_count != current_video_info.get('total_frames'):
                warnings.append(f"Project frame count ({saved_frame_count}) mismatches loaded ({current_video_info.get('total_frames')}).")
        elif saved_video_filename != "N/A":
            warnings.append(f"Project metadata indicates video '{saved_video_filename}', but no video is currently active in the application.")
        
        # --- Apply Coordinate System Settings ---
        coord_mode_str = project_metadata.get(config.META_COORD_SYSTEM_MODE)
        coord_origin_x_tl = project_metadata.get(config.META_COORD_ORIGIN_X_TL)
        coord_origin_y_tl = project_metadata.get(config.META_COORD_ORIGIN_Y_TL)
        
        video_h_for_coord_transform = 1 
        if isinstance(saved_video_height_for_coord_context, (int, float)) and saved_video_height_for_coord_context > 0:
            video_h_for_coord_transform = int(saved_video_height_for_coord_context)
        elif self._main_window_ref.video_loaded and self._main_window_ref.frame_height > 0:
            video_h_for_coord_transform = self._main_window_ref.frame_height
            warnings.append(f"Using current video height ({video_h_for_coord_transform}px) for coordinate context as project metadata height was invalid/missing.")
        else:
            warnings.append(f"Invalid/missing video height in project for coordinate context and no video loaded. Using fallback height: {video_h_for_coord_transform}px.")
        
        self._coord_transformer.set_video_height(video_h_for_coord_transform) # [cite: 55]
        loaded_coord_mode = CoordinateSystem.from_string(coord_mode_str) if coord_mode_str else CoordinateSystem.TOP_LEFT # [cite: 55]
        self._coord_transformer.set_mode(loaded_coord_mode) # [cite: 55]
        if loaded_coord_mode == CoordinateSystem.CUSTOM and coord_origin_x_tl is not None and coord_origin_y_tl is not None:
            try:
                self._coord_transformer.set_custom_origin(float(coord_origin_x_tl), float(coord_origin_y_tl)) # [cite: 55]
            except ValueError:
                warnings.append("Invalid custom origin coordinates in project. Using default (0,0) for custom mode.")
                self._coord_transformer.set_custom_origin(0.0, 0.0) 
        
        # --- Apply Scale Settings --- [cite: 56]
        scale_m_per_px_val = project_metadata.get(config.META_SCALE_FACTOR_M_PER_PX)
        display_in_meters_val = project_metadata.get('display_in_meters', False)
        
        if isinstance(scale_m_per_px_val, str) and scale_m_per_px_val.lower() == "n/a":
            scale_m_per_px_val = None
        elif scale_m_per_px_val is not None:
            try: scale_m_per_px_val = float(scale_m_per_px_val)
            except ValueError: scale_m_per_px_val = None; warnings.append("Invalid scale factor in project. Scale not set from project.")

        p1x_str = project_metadata.get(config.META_SCALE_LINE_P1X); p1y_str = project_metadata.get(config.META_SCALE_LINE_P1Y)
        p2x_str = project_metadata.get(config.META_SCALE_LINE_P2X); p2y_str = project_metadata.get(config.META_SCALE_LINE_P2Y)
        
        parsed_scale_line_coords: Optional[Tuple[float,float,float,float]] = None
        if all(s not in [None, "N/A", ""] for s in [p1x_str, p1y_str, p2x_str, p2y_str]):
            try:
                p1x = float(p1x_str); p1y = float(p1y_str)
                p2x = float(p2x_str); p2y = float(p2y_str)
                parsed_scale_line_coords = (p1x,p1y,p2x,p2y)
            except (ValueError, TypeError):
                warnings.append("Invalid scale line coordinate format in project. Defined scale line ignored.")
        
        if parsed_scale_line_coords:
            self._scale_manager.set_defined_scale_line(*parsed_scale_line_coords)
            self._scale_manager.set_scale(scale_m_per_px_val, called_from_line_definition=True)
        else:
            self._scale_manager.clear_defined_scale_line()
            self._scale_manager.set_scale(scale_m_per_px_val, called_from_line_definition=False)
        self._scale_manager.set_display_in_meters(bool(display_in_meters_val))

        # --- Apply Other Global Settings --- [cite: 57]
        show_lengths_val_str = project_metadata.get(config.META_SHOW_MEASUREMENT_LINE_LENGTHS)
        if isinstance(show_lengths_val_str, bool): 
            show_lengths_val = show_lengths_val_str
        elif isinstance(show_lengths_val_str, str):
            show_lengths_val = show_lengths_val_str.lower() == 'true'
        else: 
            show_lengths_val = True 
            warnings.append(f"Setting '{config.META_SHOW_MEASUREMENT_LINE_LENGTHS}' missing or invalid in project. Defaulting to {show_lengths_val}.")
        self._settings_manager.set_setting(config.META_SHOW_MEASUREMENT_LINE_LENGTHS, show_lengths_val) # [cite: 57]
        
        # --- Load Elements ---
        elements_to_load = loaded_state_dict.get('elements', [])
        video_context_width = self._main_window_ref.frame_width if self._main_window_ref.video_loaded else (int(saved_video_width) if isinstance(saved_video_width, (int, float)) and saved_video_width > 0 else 0)
        video_context_height = self._main_window_ref.frame_height if self._main_window_ref.video_loaded else (int(saved_video_height_for_coord_context) if isinstance(saved_video_height_for_coord_context, (int, float)) and saved_video_height_for_coord_context > 0 else 0)
        video_context_frames = self._main_window_ref.total_frames if self._main_window_ref.video_loaded else (int(saved_frame_count) if isinstance(saved_frame_count, int) and saved_frame_count > 0 else 0)
        video_context_fps = self._main_window_ref.fps if self._main_window_ref.video_loaded else (float(project_metadata.get(config.META_FPS, 0.0)) if project_metadata.get(config.META_FPS) is not None else 0.0)

        if video_context_width <= 0 or video_context_height <= 0 or video_context_frames <= 0:
             warnings.append("Video context for element validation is invalid (dimensions/frames are zero or negative). Point validation may be unreliable.")
        
        success_elements, element_warnings = self._element_manager.load_elements_from_project_data(
            elements_to_load,
            video_width=video_context_width,
            video_height=video_context_height,
            video_frame_count=video_context_frames,
            video_fps=video_context_fps
        ) # [cite: 57]
        warnings.extend(element_warnings)
        
        if not success_elements:
            logger.error("ElementManager.load_elements_from_project_data reported failure.")
        
        logger.info("Project data application processed.")
        if warnings:
            final_warning_message = "Project loaded with the following notes/warnings:\n" + "\n".join([f"- {w}" for w in warnings])
            logger.warning(final_warning_message)
            self._main_window_ref._project_load_warnings = warnings 
        else:
             self._main_window_ref._project_load_warnings = [] 

        return True
