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

# Type alias for the raw point data structure read from CSV:
# (track_id, frame_idx, time_ms, x_in_file_system, y_in_file_system)
RawParsedData = Tuple[int, int, float, float, float]

# Get a logger for this module
logger = logging.getLogger(__name__)

# --- CSV Reading/Writing ---

def write_track_csv(filepath: str, metadata_dict: Dict[str, Any],
                    all_tracks_data: 'AllTracksData',
                    coord_transformer: CoordinateTransformer) -> None:
    """
    Writes track data and associated metadata to a CSV file, transforming
    coordinates to the format specified by the CoordinateTransformer.

    Args:
        filepath: The path to the CSV file to write.
        metadata_dict: A dictionary containing video metadata.
        all_tracks_data: A list where each element is a list of point data tuples
                         for a track (MUST be in internal Top-Left coordinates).
        coord_transformer: The coordinate transformer instance defining the output format.

    Raises:
        IOError, PermissionError, Exception: If writing fails.
    """
    logger.info(f"Writing track data to CSV: {filepath}")
    try:
        # Get coordinate system metadata from the transformer
        coord_metadata = {
            config.META_COORD_SYSTEM_MODE: str(coord_transformer.mode),
            config.META_COORD_ORIGIN_X_TL: coord_transformer.get_metadata().get("origin_x_tl", 0.0),
            config.META_COORD_ORIGIN_Y_TL: coord_transformer.get_metadata().get("origin_y_tl", 0.0),
            config.META_HEIGHT: coord_transformer.video_height # Use META_HEIGHT key
        }
        # Combine video metadata with coordinate metadata and app info
        full_metadata = {**metadata_dict, **coord_metadata}
        full_metadata[config.META_APP_NAME] = config.APP_NAME
        full_metadata[config.META_APP_VERSION] = config.APP_VERSION

        logger.debug(f"Full metadata for saving: {full_metadata}")

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Write metadata section (using EXPECTED_METADATA_KEYS for preferred order)
            written_keys = set()
            for key in config.EXPECTED_METADATA_KEYS:
                if key in full_metadata:
                    value = full_metadata[key]
                    writer.writerow([f"{config.CSV_METADATA_PREFIX}{key}: {value}"])
                    written_keys.add(key)
                else:
                    # Log if an expected key is somehow missing
                    logger.warning(f"Expected metadata key '{key}' not found in metadata dictionary for saving.")

            # Write any extra keys not in the expected list (defensive programming)
            for key, value in full_metadata.items():
                if key not in written_keys:
                    logger.warning(f"Writing unexpected metadata key: {key}")
                    writer.writerow([f"{config.CSV_METADATA_PREFIX}{key}: {value}"])

            # Write Header row
            logger.debug(f"Writing header: {config.CSV_HEADER}")
            writer.writerow(config.CSV_HEADER)

            # Write Data rows (transformed coordinates)
            points_written: int = 0
            for track_index, track_points in enumerate(all_tracks_data):
                track_id: int = track_index + 1 # Use 1-based ID
                for point_data in track_points:
                    # Points from TrackManager are internal Top-Left
                    frame_idx, time_ms, x_tl, y_tl = point_data
                    # Transform to the display/save coordinate system
                    x_display, y_display = coord_transformer.transform_point_for_display(x_tl, y_tl)
                    # Format floats for consistent output
                    writer.writerow([track_id, frame_idx, f"{time_ms:.4f}", f"{x_display:.4f}", f"{y_display:.4f}"])
                    points_written += 1
            logger.info(f"Successfully wrote {points_written} points for {len(all_tracks_data)} tracks to {filepath}")
    except (IOError, PermissionError) as e:
        logger.error(f"Error writing CSV file '{filepath}': {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error writing CSV file '{filepath}': {e}", exc_info=True)
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
                       coord_transformer: CoordinateTransformer) -> None:
    """
    Handles the 'File -> Save Tracks As...' action logic.

    Gets filename via dialog, collects metadata (including coord system),
    retrieves internal TL track data, calls write_track_csv to transform and write.

    Args:
        main_window: The main application window instance.
        track_manager: The track manager instance holding the data.
        coord_transformer: The coordinate transformer defining the output format.
    """
    if not main_window.video_loaded or not track_manager or not coord_transformer or len(track_manager.tracks) == 0:
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
        all_tracks_data_tl: 'AllTracksData' = track_manager.get_all_track_data()
        logger.debug(f"Gathered {len(all_tracks_data_tl)} tracks (internal TL) for saving.")

        # Call the writing function, passing the current main transformer
        # write_track_csv handles getting coord metadata and transforming points
        write_track_csv(save_path, video_metadata, all_tracks_data_tl, coord_transformer)

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
                       coord_transformer: CoordinateTransformer) -> None:
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
    if not main_window.video_loaded or not track_manager or not coord_transformer:
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
        loaded_metadata, parsed_data_raw = read_track_csv(load_path)
        logger.debug(f"Read {len(parsed_data_raw)} points from CSV with metadata: {loaded_metadata}")

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

        # --- Transform loaded points to Internal Top-Left format ---
        transformed_parsed_data: List[RawParsedData] = []
        points_transformed = 0
        points_transform_failed = 0
        logger.info(f"Transforming {len(parsed_data_raw)} loaded points to internal TL format using file's coordinate system...")
        for point_raw in parsed_data_raw:
            track_id, frame_idx, time_ms, x_loaded, y_loaded = point_raw
            try:
                # Use the main transformer's method with the LOADED system parameters
                x_tl, y_tl = coord_transformer.transform_point_to_internal(
                    x_loaded, y_loaded,
                    loaded_mode_enum, loaded_origin_tl, loaded_video_height
                )
                transformed_parsed_data.append((track_id, frame_idx, time_ms, x_tl, y_tl))
                points_transformed += 1
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
            transformed_parsed_data, # Data is now x_tl, y_tl
            main_window.frame_width, main_window.frame_height,
            main_window.total_frames, main_window.fps
        )
        warnings_list.extend(load_warnings) # Combine any warnings from track manager load

        if not success:
            # If TrackManager load failed, raise an error to be caught below
            raise ValueError(f"TrackManager failed to load data: {'; '.join(load_warnings) or 'Unknown reason'}")

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