# file_io.py
"""
Handles file input/output operations for PyroTracker, specifically
reading and writing track data to CSV files, including user interaction
via file dialogs and message boxes.
"""
import csv
import os
import logging
import math
from typing import List, Tuple, Dict, Any, TYPE_CHECKING, Optional

from PySide6 import QtWidgets, QtCore

import config
# Import coordinate system components
from coordinates import CoordinateSystem, CoordinateTransformer

# Use TYPE_CHECKING to avoid circular import issues for type hints
if TYPE_CHECKING:
    from main_window import MainWindow
    from track_manager import TrackManager, AllTracksData, Track
    from scale_manager import ScaleManager

# Type alias for the raw point data structure read from CSV:
# (track_id, frame_idx, time_ms, x_in_file_system, y_in_file_system)
RawParsedData = Tuple[int, int, float, float, float]

# Get a logger for this module
logger = logging.getLogger(__name__)

# --- CSV Reading/Writing ---

def write_track_csv(filepath: str, metadata_dict: Dict[str, Any],
                    all_tracks_data: 'AllTracksData', # This is internal TL pixel data
                    coord_transformer: CoordinateTransformer,
                    scale_manager: 'ScaleManager', # +++ NEW PARAMETER +++
                    main_window_parent: Optional['MainWindow'] = None) -> None: # +++ NEW Optional parent for dialog +++
    """
    Writes track data and associated metadata to a CSV file.
    Handles coordinate system transformation and optional scaling to meters.

    Args:
        filepath: The path to the CSV file to write.
        metadata_dict: A dictionary containing video metadata.
        all_tracks_data: A list of tracks (internal Top-Left pixel coordinates).
        coord_transformer: The coordinate transformer for system transformations.
        scale_manager: The scale manager for unit transformations and scale metadata.
        main_window_parent: Optional parent MainWindow, needed for the precision warning dialog.
    """
    logger.info(f"Writing track data to CSV: {filepath}")

    # --- Determine Save Units and Handle Precision Warning ---
    save_in_meters = False
    actual_scale_to_save = scale_manager.get_scale_m_per_px() # This is m/px

    if scale_manager.display_in_meters() and actual_scale_to_save is not None and main_window_parent:
        reply = QtWidgets.QMessageBox.question(
            main_window_parent,
            "Confirm Save Units",
            "You are about to save track data in METERS. This may involve a loss of precision "
            "compared to saving in pixels.\n\nSaving in meters is useful for direct use in other software. "
            "It is recommended to also keep a version saved in pixels for archival or re-processing "
            "within PyroTracker.\n\nWould you like to save in METERS or save in PIXELS instead?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Yes  # Default to Yes (Save in Meters)
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes: # Save in Meters
            save_in_meters = True
            logger.info("User chose to save data in METERS.")
        elif reply == QtWidgets.QMessageBox.StandardButton.No: # Save in Pixels
            save_in_meters = False
            logger.info("User chose to save data in PIXELS instead.")
        else: # Cancel
            logger.info("Track saving cancelled by user at precision warning.")
            if hasattr(main_window_parent, 'statusBar'):
                 main_window_parent.statusBar.showMessage("Save cancelled.", 3000)
            return # Abort saving
    elif actual_scale_to_save is not None : # No dialog, but scale is set (e.g. display_in_meters was false)
        # Default to saving in pixels if display_in_meters is false, even if scale is set
        save_in_meters = False # Or make this configurable if desired
        logger.info("Defaulting to save data in PIXELS (display in meters was not active or no dialog).")
    else: # No scale set
        save_in_meters = False # Must save in pixels
        logger.info("No scale set. Saving data in PIXELS.")

    try:
        # Get coordinate system metadata
        coord_metadata = {
            config.META_COORD_SYSTEM_MODE: str(coord_transformer.mode),
            config.META_COORD_ORIGIN_X_TL: coord_transformer.get_metadata().get("origin_x_tl", 0.0),
            config.META_COORD_ORIGIN_Y_TL: coord_transformer.get_metadata().get("origin_y_tl", 0.0),
            config.META_HEIGHT: coord_transformer.video_height
        }

        # Get scale metadata
        scale_metadata = {
            config.META_SCALE_FACTOR_M_PER_PX: f"{actual_scale_to_save:.8g}" if actual_scale_to_save is not None else "N/A",
            config.META_DATA_UNITS: "m" if save_in_meters else "px"
        }

        full_metadata = {**metadata_dict, **coord_metadata, **scale_metadata} # Add scale metadata
        full_metadata[config.META_APP_NAME] = config.APP_NAME
        full_metadata[config.META_APP_VERSION] = config.APP_VERSION
        logger.debug(f"Full metadata for saving: {full_metadata}")

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            written_keys = set()
            for key in config.EXPECTED_METADATA_KEYS: # Now includes scale keys
                if key in full_metadata:
                    value = full_metadata[key]
                    writer.writerow([f"{config.CSV_METADATA_PREFIX}{key}: {value}"])
                    written_keys.add(key)
                else:
                    logger.warning(f"Expected metadata key '{key}' not found for saving.")
            
            for key, value in full_metadata.items():
                if key not in written_keys:
                    logger.warning(f"Writing unexpected metadata key: {key}")
                    writer.writerow([f"{config.CSV_METADATA_PREFIX}{key}: {value}"])

            writer.writerow(config.CSV_HEADER) # Header is always px/m agnostic

            points_written = 0
            for track_index, track_points_tl_px in enumerate(all_tracks_data):
                track_id = track_index + 1
                for point_data_tl_px in track_points_tl_px:
                    frame_idx, time_ms, x_tl_px, y_tl_px = point_data_tl_px
                    
                    # 1. Transform to the chosen *coordinate system* (still in pixels)
                    x_coord_sys_px, y_coord_sys_px = coord_transformer.transform_point_for_display(x_tl_px, y_tl_px)

                    x_to_write = x_coord_sys_px
                    y_to_write = y_coord_sys_px

                    # 2. If saving in meters, apply scale transformation
                    if save_in_meters and actual_scale_to_save is not None:
                        x_to_write = x_coord_sys_px * actual_scale_to_save
                        y_to_write = y_coord_sys_px * actual_scale_to_save
                        # Use appropriate precision for meters
                        writer.writerow([track_id, frame_idx, f"{time_ms:.4f}", f"{x_to_write:.6f}", f"{y_to_write:.6f}"])
                    else:
                        # Save in pixels with pixel precision
                        writer.writerow([track_id, frame_idx, f"{time_ms:.4f}", f"{x_to_write:.4f}", f"{y_to_write:.4f}"])
                    points_written += 1
            
            success_msg = f"Tracks successfully saved to {os.path.basename(filepath)} (Units: {'meters' if save_in_meters else 'pixels'})"
            logger.info(success_msg)
            if main_window_parent and hasattr(main_window_parent, 'statusBar'):
                 main_window_parent.statusBar.showMessage(success_msg, 5000)

    except (IOError, PermissionError) as e:
        logger.error(f"Error writing CSV file '{filepath}': {e}", exc_info=True)
        if main_window_parent: QtWidgets.QMessageBox.critical(main_window_parent, "Save Error", f"Error writing file: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error writing CSV file '{filepath}': {e}", exc_info=True)
        if main_window_parent: QtWidgets.QMessageBox.critical(main_window_parent, "Save Error", f"An unexpected error occurred: {e}")
        raise


def read_track_csv(filepath: str) -> Tuple[Dict[str, str], List[RawParsedData]]:
    """
    Reads track data and metadata (including coordinate system info) from a CSV file.

    Args:
        filepath: The path to the CSV file to read.

    Returns:
        A tuple containing:
        - metadata_dict: Dictionary of metadata key-value pairs found.
        - parsed_data: List of raw point data tuples (track_id, frame_idx, time_ms, x, y)
                       as read from the file (coordinates are in the file's saved system).

    Raises:
        FileNotFoundError, PermissionError, ValueError, Exception: If reading fails or format is invalid.
    """
    logger.info(f"Reading track data from CSV: {filepath}")
    metadata_dict: Dict[str, str] = {}
    parsed_data: List[RawParsedData] = []
    try:
        with open(filepath, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            line_num: int = 0
            header_found: bool = False
            header_or_data_encountered: bool = False

            logger.debug("Starting CSV read loop...")
            for row in reader:
                line_num += 1
                if not row:
                    logger.debug(f"Skipping empty line {line_num}.")
                    continue

                first_cell: str = row[0].strip()

                # Parse Metadata Lines (includes coord system keys if present)
                if not header_found and first_cell.startswith(config.CSV_METADATA_PREFIX):
                    if header_or_data_encountered:
                        msg = f"Invalid CSV: Metadata found after header or data line {line_num}."
                        logger.error(msg); raise ValueError(msg)
                    try:
                        meta_line: str = first_cell[len(config.CSV_METADATA_PREFIX):]
                        key, value = meta_line.split(':', 1)
                        key_strip, val_strip = key.strip(), value.strip()
                        metadata_dict[key_strip] = val_strip # Store all found metadata
                        logger.debug(f"Read metadata line {line_num}: {key_strip} = {val_strip}")
                    except ValueError:
                        logger.warning(f"Skipping malformed metadata line {line_num}: '{row}'")
                    continue

                header_or_data_encountered = True

                # Check for Header Row
                if not header_found:
                    normalized_row_header: List[str] = [h.strip().lower() for h in row]
                    normalized_expected_header: List[str] = [h.lower() for h in config.CSV_HEADER]
                    if normalized_row_header == normalized_expected_header:
                        logger.info(f"Found header row at line {line_num}: {row}")
                        header_found = True
                        continue
                    else:
                        # Header is mandatory before data
                        if metadata_dict:
                            msg = f"Invalid CSV: Expected header '{config.CSV_HEADER}' after metadata, found '{row}' at line {line_num}."
                        else:
                            msg = f"Invalid CSV: Header row '{config.CSV_HEADER}' not found before data at line {line_num}."
                        logger.error(msg); raise ValueError(msg)

                # Parse Data Rows (coordinates are in the file's saved system)
                if header_found:
                    expected_cols: int = len(config.CSV_HEADER)
                    if len(row) != expected_cols:
                        msg = f"Invalid CSV data: Expected {expected_cols} columns, found {len(row)} at line {line_num}: {row}"
                        logger.error(msg); raise ValueError(msg)
                    try:
                        track_id: int = int(row[0])
                        frame_idx: int = int(row[1])
                        time_ms: float = float(row[2])
                        x: float = float(row[3]) # This is x_display (in file's system)
                        y: float = float(row[4]) # This is y_display (in file's system)
                        if track_id <= 0: raise ValueError("track_id must be positive")
                        if frame_idx < 0: raise ValueError("frame_index cannot be negative")
                        parsed_data.append((track_id, frame_idx, time_ms, x, y))
                    except ValueError as ve:
                        msg = f"Invalid CSV data: Error parsing numeric value at line {line_num}: {row} - {ve}"
                        logger.error(msg); raise ValueError(msg)

            logger.debug("Finished reading CSV file.")
            if not header_found:
                msg = f"Invalid CSV: Header row '{config.CSV_HEADER}' not found."
                logger.error(msg); raise ValueError(msg)
            if not parsed_data and metadata_dict:
                 logger.warning(f"CSV file '{filepath}' contained metadata but no track data points.")
            elif not parsed_data and not metadata_dict:
                 logger.warning(f"CSV file '{filepath}' appears to be empty or contain only a header.")

    except (FileNotFoundError, PermissionError, ValueError) as e:
         logger.error(f"Error reading CSV file '{filepath}': {e}", exc_info=False)
         raise # Re-raise specific handled errors
    except Exception as e:
         logger.error(f"Unexpected error reading CSV file '{filepath}': {e}", exc_info=True)
         raise # Re-raise unexpected errors

    logger.info(f"Successfully read {len(parsed_data)} data points and {len(metadata_dict)} metadata items from {filepath}.")
    return metadata_dict, parsed_data

# --- UI Interaction Functions ---

def save_tracks_dialog(main_window: 'MainWindow', track_manager: 'TrackManager',
                       coord_transformer: CoordinateTransformer,
                       scale_manager: 'ScaleManager') -> None:
    """
    Handles the 'File -> Save Tracks As...' action logic.

    Gets filename via dialog, collects metadata (including coord system),
    retrieves internal TL track data, calls write_track_csv to transform and write.

    Args:
        main_window: The main application window instance.
        track_manager: The track manager instance holding the data.
        coord_transformer: The coordinate transformer defining the output format.
    """
    if not main_window.video_loaded or not track_manager or not coord_transformer or not scale_manager or len(track_manager.tracks) == 0:
        logger.warning("Save Tracks action ignored: Video not loaded, components unavailable, or no tracks exist.")
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage("No tracks to save.", 3000)
        return
    logger.info("Save Tracks action triggered.")

    # Suggest filename based on video name
    base_video_name: str = os.path.splitext(os.path.basename(main_window.video_filepath))[0]
    suggested_filename: str = os.path.join(os.path.dirname(main_window.video_filepath), f"{base_video_name}_tracks.csv")
    logger.debug(f"Suggested save filename: {suggested_filename}")

    save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
        main_window, "Save Tracks File", suggested_filename, "CSV Files (*.csv);;All Files (*)"
    )
    if not save_path:
        logger.info("Track saving cancelled by user.")
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage("Save cancelled.", 3000)
        return

    logger.info(f"User selected path for saving tracks: {save_path}")
    if hasattr(main_window, 'statusBar'):
        main_window.statusBar.showMessage(f"Saving tracks to {os.path.basename(save_path)}...")
        QtWidgets.QApplication.processEvents() # Ensure UI updates

    try:
        # Collect VIDEO metadata from main window
        video_metadata: Dict[str, Any] = {
            config.META_FILENAME: os.path.basename(main_window.video_filepath),
            config.META_WIDTH: main_window.frame_width,
            config.META_HEIGHT: main_window.frame_height,
            config.META_FRAMES: main_window.total_frames,
            config.META_FPS: main_window.fps,
            config.META_DURATION: main_window.total_duration_ms,
        }
        # Get INTERNAL (Top-Left) track data from track manager
        all_tracks_data_tl_px = track_manager.get_all_track_data()
        logger.debug(f"Gathered {len(all_tracks_data_tl_px)} tracks (internal TL) for saving.")

        # Call the writing function, passing the current main transformer
        # write_track_csv handles getting coord metadata and transforming points
        write_track_csv(save_path, video_metadata, all_tracks_data_tl_px,
                        coord_transformer, scale_manager, main_window) # Pass main_window here

        if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage(f"Tracks successfully saved to {os.path.basename(save_path)}", 5000)
        logger.info(f"Tracks successfully saved to {save_path}")

    except Exception as e:
        error_msg = f"Error saving tracks: {str(e)}"
        logger.exception(f"Error saving tracks to {save_path}")
        QtWidgets.QMessageBox.critical(main_window, "Save Error", error_msg)
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage("Error saving tracks. See log.", 5000)

def load_tracks_dialog(main_window: 'MainWindow', track_manager: 'TrackManager',
                       coord_transformer: CoordinateTransformer,
                       scale_manager: 'ScaleManager') -> None:
    """
    Handles the 'File -> Load Tracks...' action logic.

    Gets filename via dialog, confirms overwrite, reads CSV, validates metadata,
    transforms loaded points back to internal TL format based on loaded coord metadata,
    loads TL points into TrackManager, and updates main window's coord_transformer state & UI.

    Args:
        main_window: The main application window instance.
        track_manager: The track manager instance to load data into.
        coord_transformer: The main coordinate transformer instance (to be updated on success).
    """
    if not main_window.video_loaded or not track_manager or not coord_transformer or not scale_manager: # Added scale_manager check
        logger.warning("Load Tracks action ignored: Video not loaded or components unavailable.")
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage("Cannot load tracks: No video loaded.", 3000)
        return
    logger.info("Load Tracks action triggered.")

    # Confirm overwrite if tracks exist
    if len(track_manager.tracks) > 0:
        logger.debug("Existing tracks found, confirming overwrite with user.")
        reply = QtWidgets.QMessageBox.question(
            main_window, "Confirm Load",
            "Loading a new track file will replace all current unsaved tracks.\n"
            "Are you sure you want to continue?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel)
        if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
            logger.info("Track loading cancelled by user (overwrite confirmation).")
            if hasattr(main_window, 'statusBar'):
                main_window.statusBar.showMessage("Load cancelled.", 3000)
            return
        logger.debug("User confirmed overwrite.")

    # Get file path from user
    start_dir: str = os.path.dirname(main_window.video_filepath) if main_window.video_filepath else ""
    load_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        main_window, "Load Tracks File", start_dir, "CSV Files (*.csv);;All Files (*)"
    )
    if not load_path:
        logger.info("Track loading cancelled by user (file dialog).")
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage("Load cancelled.", 3000)
        return

    logger.info(f"User selected path for loading tracks: {load_path}")
    if hasattr(main_window, 'statusBar'):
        main_window.statusBar.showMessage(f"Loading tracks from {os.path.basename(load_path)}...")
        QtWidgets.QApplication.processEvents() # Ensure UI updates

    warnings_list: List[str] = []
    try:
        # Read raw data and all metadata (incl. coord system)
        loaded_metadata, parsed_data_raw_from_file = read_track_csv(load_path) # x,y here are as per file
        logger.debug(f"Read {len(parsed_data_raw_from_file)} points from CSV with metadata: {loaded_metadata}")

        # --- Parse Scale Metadata (before coordinate system for transformation order) ---
        loaded_scale_str = loaded_metadata.get(config.META_SCALE_FACTOR_M_PER_PX)
        loaded_data_units = loaded_metadata.get(config.META_DATA_UNITS, "px").lower() # Default to "px"
        
        loaded_scale_m_per_px: Optional[float] = None
        if loaded_scale_str and loaded_scale_str != "N/A":
            try:
                loaded_scale_m_per_px = float(loaded_scale_str)
                if loaded_scale_m_per_px <= 0:
                    warnings_list.append(f"Invalid scale factor '{loaded_scale_str}' in CSV. Scale ignored.")
                    loaded_scale_m_per_px = None
            except ValueError:
                warnings_list.append(f"Non-numeric scale factor '{loaded_scale_str}' in CSV. Scale ignored.")
        
        if loaded_data_units == "m" and loaded_scale_m_per_px is None:
            warnings_list.append("CSV data units are 'm' but no valid scale factor found. Treating coordinates as pixels.")
            loaded_data_units = "px" # Fallback

        logger.info(f"Parsed scale from file: Factor={loaded_scale_m_per_px}, Units='{loaded_data_units}'")

        # --- Parse Coordinate System Metadata from loaded file ---
        loaded_mode_str = loaded_metadata.get(config.META_COORD_SYSTEM_MODE)
        loaded_origin_x_str = loaded_metadata.get(config.META_COORD_ORIGIN_X_TL)
        loaded_origin_y_str = loaded_metadata.get(config.META_COORD_ORIGIN_Y_TL)
        loaded_height_str = loaded_metadata.get(config.META_HEIGHT)

        loaded_mode_enum = CoordinateSystem.TOP_LEFT # Default mode
        loaded_origin_x = 0.0
        loaded_origin_y = 0.0
        loaded_video_height = 0 # Default height

        # Parse Mode
        if loaded_mode_str:
            mode = CoordinateSystem.from_string(loaded_mode_str)
            if mode:
                loaded_mode_enum = mode
            else:
                warnings_list.append(f"Invalid coordinate mode '{loaded_mode_str}' in CSV, using TOP_LEFT.")
        elif config.META_COORD_SYSTEM_MODE in config.EXPECTED_METADATA_KEYS:
            warnings_list.append("Coordinate mode missing in CSV metadata, assuming TOP_LEFT.")

        # Parse Origin (TL coordinates)
        try:
            if loaded_origin_x_str is not None: loaded_origin_x = float(loaded_origin_x_str)
            elif config.META_COORD_ORIGIN_X_TL in config.EXPECTED_METADATA_KEYS:
                warnings_list.append("Coordinate origin X missing in CSV metadata, assuming 0.")
            if loaded_origin_y_str is not None: loaded_origin_y = float(loaded_origin_y_str)
            elif config.META_COORD_ORIGIN_Y_TL in config.EXPECTED_METADATA_KEYS:
                warnings_list.append("Coordinate origin Y missing in CSV metadata, assuming 0.")
        except (ValueError, TypeError):
            warnings_list.append("Invalid coordinate origin format in CSV, using (0,0).")
            loaded_origin_x = 0.0; loaded_origin_y = 0.0

        # Parse Video Height (used for transformation context)
        try:
             if loaded_height_str is not None:
                 parsed_height = int(loaded_height_str)
                 if parsed_height > 0:
                     loaded_video_height = parsed_height
                 else:
                     warnings_list.append(f"Invalid video height '{loaded_height_str}' in CSV. Using current video height for transformation.")
                     # Use current video height as fallback if file height invalid/zero
                     loaded_video_height = main_window.frame_height if main_window.frame_height > 0 else 1
             elif config.META_HEIGHT in config.EXPECTED_METADATA_KEYS:
                 warnings_list.append(f"Video height missing in CSV. Using current video height ({main_window.frame_height}) for transformation.")
                 loaded_video_height = main_window.frame_height if main_window.frame_height > 0 else 1 # Need a positive value
        except (ValueError, TypeError):
             warnings_list.append(f"Invalid video height format '{loaded_height_str}' in CSV. Using current video height for transformation.")
             loaded_video_height = main_window.frame_height if main_window.frame_height > 0 else 1
        # --- End Coordinate System Parsing ---

        loaded_origin_tl = (loaded_origin_x, loaded_origin_y)
        logger.info(f"Parsed coordinate system from file: Mode={loaded_mode_enum.name}, OriginTL={loaded_origin_tl}, SourceHeight={loaded_video_height}")

        # --- Perform Video Metadata Mismatch Check ---
        mismatches: List[str] = []
        meta_checks: Dict[str, Any] = {
            config.META_FRAMES: main_window.total_frames,
            config.META_WIDTH: main_window.frame_width,
            config.META_HEIGHT: main_window.frame_height,
            config.META_FPS: main_window.fps,
        }
        for key, current_value in meta_checks.items():
             loaded_value_str: Optional[str] = loaded_metadata.get(key)
             if loaded_value_str is not None:
                 try:
                     type_converter = type(current_value)
                     # Handle case where current_value might be 0 (int or float)
                     if type_converter == float and current_value == 0: type_converter = float
                     elif type_converter == int and current_value == 0: type_converter = int

                     loaded_value_typed = type_converter(loaded_value_str)

                     if isinstance(current_value, float):
                         if not math.isclose(loaded_value_typed, current_value, rel_tol=1e-3):
                              mismatches.append(f"{key} (CSV: {loaded_value_typed:.2f} vs Video: {current_value:.2f})")
                     elif loaded_value_typed != current_value:
                         mismatches.append(f"{key} (CSV: {loaded_value_typed} vs Video: {current_value})")
                 except (ValueError, TypeError) as e:
                      logger.warning(f"Metadata check failed for key '{key}'. Could not convert CSV value '{loaded_value_str}' to type {type(current_value)}. Error: {e}")
                      mismatches.append(f"{key} (type mismatch - CSV: '{loaded_value_str}' vs Video: {current_value})")
             elif key in config.EXPECTED_METADATA_KEYS:
                 logger.warning(f"Metadata check: Expected key '{key}' missing in loaded CSV file.")
        if mismatches:
            mismatch_str: str = "\n - ".join(mismatches)
            logger.warning(f"Metadata mismatch detected: {mismatch_str}")
            reply = QtWidgets.QMessageBox.warning(
                main_window, "Metadata Mismatch",
                f"The track file's metadata may not match the current video:\n"
                f"Potential Mismatches:\n - {mismatch_str}\n\nLoad anyway?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Cancel)
            if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
                logger.info("Track loading cancelled due to metadata mismatch.")
                if hasattr(main_window, 'statusBar'):
                    main_window.statusBar.showMessage("Load cancelled due to metadata mismatch.", 3000)
                return
            else:
                warnings_list.append("Proceeded despite potential metadata mismatch.")

        data_to_transform_to_internal_px: List[RawParsedData] = []

        logger.info(f"Converting {len(parsed_data_raw_from_file)} points from file units/system to file system pixels...")
        for point_raw_from_file in parsed_data_raw_from_file:
            track_id, frame_idx, time_ms, x_file, y_file = point_raw_from_file
            
            x_file_coord_sys_px = x_file
            y_file_coord_sys_px = y_file

            # If file data was in meters, convert to pixels *within the file's coordinate system*
            if loaded_data_units == "m" and loaded_scale_m_per_px is not None: # Scale must be valid
                x_file_coord_sys_px = x_file / loaded_scale_m_per_px
                y_file_coord_sys_px = y_file / loaded_scale_m_per_px
            
            data_to_transform_to_internal_px.append(
                (track_id, frame_idx, time_ms, x_file_coord_sys_px, y_file_coord_sys_px)
            )


        # --- Transform points (now in file's system pixels) to Internal Top-Left pixels ---
        transformed_to_internal_tl_px_data: List[RawParsedData] = []
        points_transformed = 0
        points_transform_failed = 0
        logger.info(f"Transforming {len(data_to_transform_to_internal_px)} points (in file system pixels) to internal TL pixels...")
        # Status bar message for potentially long transformation
        num_points_to_transform = len(data_to_transform_to_internal_px)
        if num_points_to_transform > 1000: # Threshold for showing message, adjust as needed
            if hasattr(main_window, 'statusBar'):
                main_window.statusBar.showMessage(f"Transforming {num_points_to_transform} points to internal system...", 0) # Persistent
                QtWidgets.QApplication.processEvents() # Ensure UI updates
        for point_to_transform in data_to_transform_to_internal_px:
            track_id, frame_idx, time_ms, x_fspx, y_fspx = point_to_transform # fspx = file system pixels
            try:
                x_tl, y_tl = coord_transformer.transform_point_to_internal(
                    x_fspx, y_fspx,
                    loaded_mode_enum, loaded_origin_tl, loaded_video_height
                )
                transformed_to_internal_tl_px_data.append((track_id, frame_idx, time_ms, x_tl, y_tl))
                points_transformed += 1 # Ensure points_transformed is initialized
            except Exception as transform_err:
                msg = f"Skipping point (Track {track_id}, Frame {frame_idx+1}) due to transformation error: {transform_err}"
                logger.error(msg, exc_info=False) # Log error, but don't show traceback unless necessary
                warnings_list.append(msg)
                points_transform_failed += 1
        logger.info(f"Transformation complete: {points_transformed} success, {points_transform_failed} failed.")
        if points_transform_failed > 0:
             QtWidgets.QMessageBox.warning(main_window, "Transformation Warning",
                                           f"{points_transform_failed} point(s) could not be transformed to the internal system. See log for details.")

        # --- Load the TRANSFORMED (Top-Left) data into TrackManager ---
        logger.debug("Passing TRANSFORMED (internal TL) data to TrackManager.load_tracks_from_data...")
        success: bool
        load_warnings: List[str]
        success, load_warnings = track_manager.load_tracks_from_data(
            transformed_to_internal_tl_px_data, # Data is now x_tl_px, y_tl_px
            main_window.frame_width, main_window.frame_height,
            main_window.total_frames, main_window.fps
        )
        warnings_list.extend(load_warnings) # Combine any warnings from track manager load

        if not success:
            # If TrackManager load failed, raise an error to be caught below
            raise ValueError(f"TrackManager failed to load data: {'; '.join(load_warnings) or 'Unknown reason'}")
        if success: # Only update scale manager if main load was successful
            # --- Update main ScaleManager state and UI ---
            logger.info("Load successful, updating main ScaleManager state and UI...")
            scale_manager.set_scale(loaded_scale_m_per_px)
            scale_manager.set_display_in_meters(True if loaded_data_units == "m" and loaded_scale_m_per_px is not None else False)

        # --- Update main coordinate transformer state and UI if load succeeded ---
        logger.info("Load successful, updating main coordinate transformer state and UI...")
        # Set the transformer's state to match the loaded file
        # Ensure video height is set first for correct origin calculation in BL mode
        coord_transformer.set_video_height(loaded_video_height) # Use height parsed from file (or fallback)
        coord_transformer.set_mode(loaded_mode_enum)
        # Set custom origin (as TL) only if the loaded mode was CUSTOM
        if loaded_mode_enum == CoordinateSystem.CUSTOM:
             coord_transformer.set_custom_origin(loaded_origin_tl[0], loaded_origin_tl[1])
        # Update UI display (radio buttons, label, etc.) via MainWindow method
        if hasattr(main_window, '_update_coordinate_ui_display'):
             main_window._update_coordinate_ui_display()
        logger.info("Coordinate system state updated to match loaded file.")

        # Explicitly trigger redraw AFTER transformer and UI display are updated.
        if hasattr(main_window, '_redraw_scene_overlay'):
            logger.debug("Explicitly triggering scene overlay redraw after successful load and UI update.")
            main_window._redraw_scene_overlay()

        # --- Report final status and warnings ---
        if not warnings_list:
            if hasattr(main_window, 'statusBar'):
                main_window.statusBar.showMessage(f"Tracks successfully loaded from {os.path.basename(load_path)}", 5000)
            logger.info(f"Tracks loaded successfully from {load_path}")
        else:
            num_warnings: int = len(warnings_list)
            logger.warning(f"Track loading completed with {num_warnings} warning(s).")
            # Show a summary of warnings in a message box
            warning_details: str = "\n - ".join(warnings_list[:5]) # Show first 5
            if num_warnings > 5: warning_details += "\n - ... (and more, see log)"
            QtWidgets.QMessageBox.warning(
                main_window, "Load Complete with Warnings",
                f"Tracks loaded from {os.path.basename(load_path)}, "
                f"but {num_warnings} potential issue(s) were found:\n\n"
                f" - {warning_details}\n\nPlease review loaded tracks and check log for details.",
                QtWidgets.QMessageBox.StandardButton.Ok)
            if hasattr(main_window, 'statusBar'):
                main_window.statusBar.showMessage(f"Tracks loaded with {num_warnings} warning(s) (see log).", 5000)

        # Update overall UI state (e.g., enable save button)
        if hasattr(main_window, '_update_ui_state'):
             main_window._update_ui_state()

    # --- Exception Handling for Load ---
    except (FileNotFoundError, PermissionError) as e:
         error_msg = f"Error loading tracks: {e}"
         logger.error(error_msg, exc_info=False)
         QtWidgets.QMessageBox.critical(main_window, "Load Error", error_msg)
         if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage(f"Error loading tracks: File access error.", 5000)
    except ValueError as e: # Catches format/parsing errors from read_track_csv or TrackManager load
         error_msg = f"Error loading tracks: Invalid file format or data.\nDetails: {e}"
         logger.error(f"ValueError during track loading: {e}", exc_info=False) # Don't need full traceback for format errors
         QtWidgets.QMessageBox.critical(main_window, "Load Error", error_msg)
         if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage("Error loading tracks: Invalid format/data (see log).", 5000)
    except Exception as e: # Catch unexpected errors
        error_msg = f"An unexpected error occurred while loading tracks: {str(e)}"
        logger.exception("Unexpected error during track loading") # Log full traceback
        QtWidgets.QMessageBox.critical(main_window, "Load Error", error_msg)
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar.showMessage("Unexpected error loading tracks. See log.", 5000)