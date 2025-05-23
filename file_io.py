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
    # MODIFIED: Import ElementType
    from element_manager import ElementManager, AllElementsForSaving, ElementData, ElementType
    from scale_manager import ScaleManager

# MODIFIED: Import ElementType here as well for module-level access if needed elsewhere,
# or specifically where it's used (as done in save_tracks_dialog).
# For robustness, and since it's used in the function signature type hint if TYPE_CHECKING is false,
# it's good practice to have it available at the module level.
from element_manager import ElementType


# Type alias for the raw point data structure read from CSV:
# (track_id, frame_idx, time_ms, x_in_file_system, y_in_file_system)
RawParsedData = Tuple[int, int, float, float, float]

# Get a logger for this module
logger = logging.getLogger(__name__)

# --- CSV Reading/Writing ---

def write_track_csv(filepath: str, metadata_dict: Dict[str, Any],
                    all_track_type_element_data: 'AllElementsForSaving',
                    coord_transformer: CoordinateTransformer,
                    scale_manager: 'ScaleManager',
                    main_window_parent: Optional['MainWindow'] = None) -> None:
    """
    Writes track data and associated metadata to a CSV file.
    Handles coordinate system transformation and optional scaling to meters.
    Includes defined scale line data if present.

    Args:
        filepath: The path to the CSV file to write.
        metadata_dict: A dictionary containing video metadata.
        all_track_type_element_data: A list of point lists, specifically for track-type elements,
                                     where each inner list represents points of a track
                                     (internal Top-Left pixel coordinates).
                                     The index of the outer list implies track_index (for ID generation).
        coord_transformer: The coordinate transformer for system transformations.
        scale_manager: The scale manager for unit transformations and scale metadata.
        main_window_parent: Optional parent MainWindow, needed for the precision warning dialog.
    """
    logger.info(f"Writing track data to CSV: {filepath}")

    save_in_meters = False
    actual_scale_to_save = scale_manager.get_scale_m_per_px()

    if scale_manager.display_in_meters() and actual_scale_to_save is not None and main_window_parent:
        reply = QtWidgets.QMessageBox.question(
            main_window_parent,
            "Confirm Save Units",
            "You are about to save track data in METERS. This may involve a loss of precision "
            "compared to saving in pixels.\n\nSaving in meters is useful for direct use in other software. "
            "It is recommended to also keep a version saved in pixels for archival or re-processing "
            "within PyroTracker.\n\nWould you like to save in METERS or save in PIXELS instead?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Yes
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            save_in_meters = True
            logger.info("User chose to save data in METERS.")
        elif reply == QtWidgets.QMessageBox.StandardButton.No:
            save_in_meters = False
            logger.info("User chose to save data in PIXELS instead.")
        else:
            logger.info("Track saving cancelled by user at precision warning.")
            status_bar = main_window_parent.statusBar()
            if status_bar:
                 status_bar.showMessage("Save cancelled.", 3000)
            return
    elif actual_scale_to_save is not None :
        save_in_meters = False
        logger.info("Defaulting to save data in PIXELS (display in meters was not active, no dialog, or scale not set for meters).")
    else:
        save_in_meters = False
        logger.info("No scale set. Saving data in PIXELS.")

    try:
        coord_meta = coord_transformer.get_metadata()
        coord_metadata_for_file = {
            config.META_COORD_SYSTEM_MODE: str(coord_transformer.mode),
            config.META_COORD_ORIGIN_X_TL: f"{coord_meta.get('origin_x_tl', 0.0):.4f}",
            config.META_COORD_ORIGIN_Y_TL: f"{coord_meta.get('origin_y_tl', 0.0):.4f}",
            config.META_HEIGHT: str(coord_transformer.video_height)
        }

        scale_metadata_for_file = {
            config.META_SCALE_FACTOR_M_PER_PX: f"{actual_scale_to_save:.8g}" if actual_scale_to_save is not None else "N/A",
            config.META_DATA_UNITS: "m" if save_in_meters else "px"
        }

        defined_line_data = scale_manager.get_defined_scale_line_data()
        defined_line_metadata = {}
        if defined_line_data:
            p1x, p1y, p2x, p2y = defined_line_data
            defined_line_metadata = {
                config.META_SCALE_LINE_P1X: f"{p1x:.4f}", config.META_SCALE_LINE_P1Y: f"{p1y:.4f}",
                config.META_SCALE_LINE_P2X: f"{p2x:.4f}", config.META_SCALE_LINE_P2Y: f"{p2y:.4f}",
            }
            logger.info(f"Including defined scale line data in CSV metadata: {defined_line_metadata}")
        else:
            defined_line_metadata = {
                config.META_SCALE_LINE_P1X: "N/A", config.META_SCALE_LINE_P1Y: "N/A",
                config.META_SCALE_LINE_P2X: "N/A", config.META_SCALE_LINE_P2Y: "N/A",
            }
            logger.info("No defined scale line data to include in CSV metadata.")

        video_metadata_str = {k: str(v) for k, v in metadata_dict.items()}
        full_metadata = {
            **video_metadata_str, **coord_metadata_for_file,
            **scale_metadata_for_file, **defined_line_metadata
        }
        full_metadata[config.META_APP_NAME] = config.APP_NAME
        full_metadata[config.META_APP_VERSION] = config.APP_VERSION

        logger.debug(f"Full metadata for saving: {full_metadata}")

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            written_keys = set()
            for key in config.EXPECTED_METADATA_KEYS:
                value_to_write = full_metadata.get(key)
                if value_to_write is not None:
                    writer.writerow([f"{config.CSV_METADATA_PREFIX}{key}: {value_to_write}"])
                    written_keys.add(key)
                else:
                    logger.warning(f"Expected metadata key '{key}' not found in full_metadata for saving. Writing as N/A.")
                    writer.writerow([f"{config.CSV_METADATA_PREFIX}{key}: N/A"])
                    written_keys.add(key)

            for key, value in full_metadata.items():
                if key not in written_keys:
                    logger.warning(f"Writing unexpected metadata key (not in EXPECTED_METADATA_KEYS): {key}")
                    writer.writerow([f"{config.CSV_METADATA_PREFIX}{key}: {value}"])

            writer.writerow(config.CSV_HEADER)

            points_written = 0
            for element_index, element_point_list_tl_px in enumerate(all_track_type_element_data):
                element_id_for_csv = element_index + 1 

                for point_data_tl_px in element_point_list_tl_px:
                    frame_idx, time_ms, x_tl_px, y_tl_px = point_data_tl_px
                    x_coord_sys_px, y_coord_sys_px = coord_transformer.transform_point_for_display(x_tl_px, y_tl_px)

                    x_to_write, y_to_write = x_coord_sys_px, y_coord_sys_px
                    if save_in_meters and actual_scale_to_save is not None:
                        x_to_write = x_coord_sys_px * actual_scale_to_save
                        y_to_write = y_coord_sys_px * actual_scale_to_save
                        writer.writerow([element_id_for_csv, frame_idx, f"{time_ms:.4f}", f"{x_to_write:.6f}", f"{y_to_write:.6f}"])
                    else:
                        writer.writerow([element_id_for_csv, frame_idx, f"{time_ms:.4f}", f"{x_to_write:.4f}", f"{y_to_write:.4f}"])
                    points_written += 1

            success_msg = f"Tracks successfully saved to {os.path.basename(filepath)} ({points_written} points, Units: {'meters' if save_in_meters else 'pixels'})"
            logger.info(success_msg)
            if main_window_parent:
                status_bar = main_window_parent.statusBar()
                if status_bar:
                     status_bar.showMessage(success_msg, 5000)

    except (IOError, PermissionError) as e:
        logger.error(f"Error writing CSV file '{filepath}': {e}", exc_info=True)
        if main_window_parent: QtWidgets.QMessageBox.critical(main_window_parent, "Save Error", f"Error writing file: {e}")
    except Exception as e:
        logger.error(f"Unexpected error writing CSV file '{filepath}': {e}", exc_info=True)
        if main_window_parent: QtWidgets.QMessageBox.critical(main_window_parent, "Save Error", f"An unexpected error occurred: {e}")

def read_track_csv(filepath: str) -> Tuple[Dict[str, str], List[RawParsedData]]:
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
                if not header_found and first_cell.startswith(config.CSV_METADATA_PREFIX):
                    if header_or_data_encountered:
                        msg = f"Invalid CSV: Metadata found after header or data line {line_num}."
                        logger.error(msg); raise ValueError(msg)
                    try:
                        meta_line: str = first_cell[len(config.CSV_METADATA_PREFIX):]
                        key, value = meta_line.split(':', 1)
                        key_strip, val_strip = key.strip(), value.strip()
                        metadata_dict[key_strip] = val_strip
                        logger.debug(f"Read metadata line {line_num}: {key_strip} = {val_strip}")
                    except ValueError:
                        logger.warning(f"Skipping malformed metadata line {line_num}: '{row}'")
                    continue
                header_or_data_encountered = True
                if not header_found:
                    normalized_row_header: List[str] = [h.strip().lower() for h in row]
                    normalized_expected_header: List[str] = [h.lower() for h in config.CSV_HEADER]
                    if normalized_row_header == normalized_expected_header:
                        logger.info(f"Found header row at line {line_num}: {row}")
                        header_found = True
                        continue
                    else:
                        if metadata_dict: msg = f"Invalid CSV: Expected header '{config.CSV_HEADER}' after metadata, found '{row}' at line {line_num}."
                        else: msg = f"Invalid CSV: Header row '{config.CSV_HEADER}' not found before data at line {line_num}."
                        logger.error(msg); raise ValueError(msg)
                if header_found:
                    expected_cols: int = len(config.CSV_HEADER)
                    if len(row) != expected_cols:
                        msg = f"Invalid CSV data: Expected {expected_cols} columns, found {len(row)} at line {line_num}: {row}"
                        logger.error(msg); raise ValueError(msg)
                    try:
                        element_id_from_file: int = int(row[0])
                        frame_idx: int = int(row[1])
                        time_ms: float = float(row[2])
                        x: float = float(row[3])
                        y: float = float(row[4])
                        if element_id_from_file <= 0: raise ValueError("element_id_from_file (track_id) must be positive")
                        if frame_idx < 0: raise ValueError("frame_index cannot be negative")
                        parsed_data.append((element_id_from_file, frame_idx, time_ms, x, y))
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
         raise
    except Exception as e:
         logger.error(f"Unexpected error reading CSV file '{filepath}': {e}", exc_info=True)
         raise
    logger.info(f"Successfully read {len(parsed_data)} data points and {len(metadata_dict)} metadata items from {filepath}.")
    return metadata_dict, parsed_data

# --- UI Interaction Functions ---

def save_tracks_dialog(main_window: 'MainWindow', element_manager: 'ElementManager',
                       coord_transformer: CoordinateTransformer,
                       scale_manager: 'ScaleManager') -> None:
    # This is where the ElementType import is needed
    from element_manager import ElementType # Import locally for this function

    if not main_window.video_loaded or not element_manager or not coord_transformer or not scale_manager or \
       not any(el['type'] == ElementType.TRACK for el in element_manager.elements):
        logger.warning("Save Tracks action ignored: Video not loaded, components unavailable, or no track-type elements exist.")
        status_bar = main_window.statusBar()
        if status_bar:
            status_bar.showMessage("No tracks to save.", 3000)
        return

    logger.info("Save Tracks action triggered.")
    base_video_name: str = os.path.splitext(os.path.basename(main_window.video_filepath))[0]
    suggested_filename: str = os.path.join(os.path.dirname(main_window.video_filepath), f"{base_video_name}_tracks.csv")
    save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
        main_window, "Save Tracks File", suggested_filename, "CSV Files (*.csv);;All Files (*)"
    )
    if not save_path:
        logger.info("Track saving cancelled by user.")
        status_bar = main_window.statusBar()
        if status_bar:
            status_bar.showMessage("Save cancelled.", 3000)
        return
    logger.info(f"User selected path for saving tracks: {save_path}")
    status_bar = main_window.statusBar()
    if status_bar:
        status_bar.showMessage(f"Saving tracks to {os.path.basename(save_path)}...")
    QtWidgets.QApplication.processEvents()
    try:
        video_metadata: Dict[str, Any] = {
            config.META_FILENAME: os.path.basename(main_window.video_filepath),
            config.META_WIDTH: main_window.frame_width,
            config.META_HEIGHT: main_window.frame_height,
            config.META_FRAMES: main_window.total_frames,
            config.META_FPS: main_window.fps,
            config.META_DURATION: main_window.total_duration_ms,
        }
        all_track_type_data_tl_px = element_manager.get_all_track_type_data_for_saving()
        write_track_csv(save_path, video_metadata, all_track_type_data_tl_px,
                        coord_transformer, scale_manager, main_window)
    except Exception as e:
        error_msg = f"Error saving tracks: {str(e)}"
        logger.exception(f"Error saving tracks to {save_path}")
        QtWidgets.QMessageBox.critical(main_window, "Save Error", error_msg)
        status_bar = main_window.statusBar()
        if status_bar:
            status_bar.showMessage("Error saving tracks. See log.", 5000)


def load_tracks_dialog(main_window: 'MainWindow', element_manager: 'ElementManager',
                       coord_transformer: CoordinateTransformer,
                       scale_manager: 'ScaleManager') -> None:
    if not main_window.video_loaded or not element_manager or not coord_transformer or not scale_manager:
        logger.warning("Load Tracks action ignored: Video not loaded or components unavailable.")
        status_bar = main_window.statusBar()
        if status_bar:
            status_bar.showMessage("Cannot load tracks: No video loaded.", 3000)
        return
    logger.info("Load Tracks action triggered.")

    if len(element_manager.elements) > 0:
        logger.debug("Existing elements found, confirming overwrite with user.")
        reply = QtWidgets.QMessageBox.question(
            main_window, "Confirm Load",
            "Loading a new track file will replace all current unsaved tracks.\n"
            "Are you sure you want to continue?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel)
        if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
            logger.info("Track loading cancelled by user (overwrite confirmation).")
            status_bar = main_window.statusBar()
            if status_bar:
                status_bar.showMessage("Load cancelled.", 3000)
            return
        logger.debug("User confirmed overwrite.")

    start_dir: str = os.path.dirname(main_window.video_filepath) if main_window.video_filepath else ""
    load_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        main_window, "Load Tracks File", start_dir, "CSV Files (*.csv);;All Files (*)"
    )
    if not load_path:
        logger.info("Track loading cancelled by user (file dialog).")
        status_bar = main_window.statusBar()
        if status_bar:
            status_bar.showMessage("Load cancelled.", 3000)
        return

    logger.info(f"User selected path for loading tracks: {load_path}")
    status_bar = main_window.statusBar()
    if status_bar:
        status_bar.showMessage(f"Loading tracks from {os.path.basename(load_path)}...")
    QtWidgets.QApplication.processEvents()

    warnings_list: List[str] = []
    try:
        loaded_metadata, parsed_data_raw_from_file = read_track_csv(load_path)
        logger.debug(f"Read {len(parsed_data_raw_from_file)} points from CSV with metadata: {loaded_metadata}")

        loaded_scale_str = loaded_metadata.get(config.META_SCALE_FACTOR_M_PER_PX)
        loaded_data_units = loaded_metadata.get(config.META_DATA_UNITS, "px").lower()
        loaded_scale_m_per_px: Optional[float] = None
        if loaded_scale_str and loaded_scale_str.lower() != "n/a":
            try:
                loaded_scale_m_per_px = float(loaded_scale_str)
                if loaded_scale_m_per_px <= 0:
                    warnings_list.append(f"Invalid scale factor '{loaded_scale_str}' in CSV. Scale ignored.")
                    loaded_scale_m_per_px = None
            except ValueError:
                warnings_list.append(f"Non-numeric scale factor '{loaded_scale_str}' in CSV. Scale ignored.")

        if loaded_data_units == "m" and loaded_scale_m_per_px is None:
            error_msg = (f"CSV data units are specified as 'meters' ({config.META_DATA_UNITS}: m), "
                         f"but a valid positive scale factor ({config.META_SCALE_FACTOR_M_PER_PX}) "
                         f"was not found or is invalid in the metadata.\n\nLoading aborted.")
            logger.error(error_msg + f" (Scale string from file was: '{loaded_scale_str}')")
            QtWidgets.QMessageBox.critical(main_window, "Load Error - Missing/Invalid Scale", error_msg)
            if main_window.statusBar(): main_window.statusBar().showMessage("Load failed: Missing/invalid scale for metric data.", 5000)
            return
        logger.info(f"Parsed scale from file: Factor={loaded_scale_m_per_px}, Units='{loaded_data_units}'")

        loaded_mode_str = loaded_metadata.get(config.META_COORD_SYSTEM_MODE)
        loaded_origin_x_str = loaded_metadata.get(config.META_COORD_ORIGIN_X_TL)
        loaded_origin_y_str = loaded_metadata.get(config.META_COORD_ORIGIN_Y_TL)
        loaded_height_str = loaded_metadata.get(config.META_HEIGHT)
        loaded_mode_enum = CoordinateSystem.TOP_LEFT
        loaded_origin_x = 0.0; loaded_origin_y = 0.0; loaded_video_height = 0

        if loaded_mode_str:
            mode = CoordinateSystem.from_string(loaded_mode_str)
            if mode: loaded_mode_enum = mode
            else: warnings_list.append(f"Invalid coordinate mode '{loaded_mode_str}' in CSV, using TOP_LEFT.")
        elif config.META_COORD_SYSTEM_MODE in config.EXPECTED_METADATA_KEYS:
             warnings_list.append("Coordinate mode missing in CSV metadata, assuming TOP_LEFT.")
        try:
            if loaded_origin_x_str and loaded_origin_x_str.lower() != "n/a": loaded_origin_x = float(loaded_origin_x_str)
            elif config.META_COORD_ORIGIN_X_TL in config.EXPECTED_METADATA_KEYS: warnings_list.append("Coord origin X missing/NA, assuming 0.")
            if loaded_origin_y_str and loaded_origin_y_str.lower() != "n/a": loaded_origin_y = float(loaded_origin_y_str)
            elif config.META_COORD_ORIGIN_Y_TL in config.EXPECTED_METADATA_KEYS: warnings_list.append("Coord origin Y missing/NA, assuming 0.")
        except (ValueError, TypeError):
            warnings_list.append("Invalid coord origin format in CSV, using (0,0)."); loaded_origin_x = 0.0; loaded_origin_y = 0.0

        if loaded_height_str and loaded_height_str.lower() != "n/a":
            try:
                parsed_height = int(loaded_height_str)
                if parsed_height > 0: loaded_video_height = parsed_height
                else: warnings_list.append(f"Invalid video height '{loaded_height_str}' in CSV. Using current video height."); loaded_video_height = main_window.frame_height
            except (ValueError, TypeError): warnings_list.append(f"Non-numeric video height '{loaded_height_str}' in CSV. Using current video height."); loaded_video_height = main_window.frame_height
        elif config.META_HEIGHT in config.EXPECTED_METADATA_KEYS:
            warnings_list.append(f"'{config.META_HEIGHT}' missing. Using current video height ({main_window.frame_height})."); loaded_video_height = main_window.frame_height
        else: loaded_video_height = main_window.frame_height

        if loaded_video_height <= 0 :
            warnings_list.append("Could not determine valid source video height. Using current video height as fallback if available, else 1.")
            loaded_video_height = main_window.frame_height if main_window.frame_height > 0 else 1

        loaded_origin_tl = (loaded_origin_x, loaded_origin_y)
        logger.info(f"Parsed coordinate system from file: Mode={loaded_mode_enum.name}, OriginTL={loaded_origin_tl}, SourceHeightForTransform={loaded_video_height}")

        p1x_str = loaded_metadata.get(config.META_SCALE_LINE_P1X)
        p1y_str = loaded_metadata.get(config.META_SCALE_LINE_P1Y)
        p2x_str = loaded_metadata.get(config.META_SCALE_LINE_P2X)
        p2y_str = loaded_metadata.get(config.META_SCALE_LINE_P2Y)
        loaded_scale_line_coords: Optional[Tuple[float,float,float,float]] = None
        if all(s and s.lower() != "n/a" for s in [p1x_str, p1y_str, p2x_str, p2y_str]):
            try:
                loaded_p1x = float(p1x_str); loaded_p1y = float(p1y_str)
                loaded_p2x = float(p2x_str); loaded_p2y = float(p2y_str)
                loaded_scale_line_coords = (loaded_p1x, loaded_p1y, loaded_p2x, loaded_p2y)
                logger.info(f"Parsed defined scale line data from CSV: {loaded_scale_line_coords}")
            except (ValueError, TypeError):
                warnings_list.append("Invalid format for defined scale line coordinates in CSV. Scale line ignored.")
                logger.warning(f"Failed to parse scale line coords: P1X='{p1x_str}', P1Y='{p1y_str}', P2X='{p2x_str}', P2Y='{p2y_str}'")
        elif any(s and s.lower() != "n/a" for s in [p1x_str, p1y_str, p2x_str, p2y_str]):
            warnings_list.append("Incomplete or partially N/A defined scale line coordinates in CSV. Scale line ignored.")
            logger.warning(f"Incomplete scale line coords: P1X='{p1x_str}', P1Y='{p1y_str}', P2X='{p2x_str}', P2Y='{p2y_str}'")

        mismatches: List[str] = []
        meta_checks = {config.META_FRAMES: main_window.total_frames, config.META_WIDTH: main_window.frame_width,
                       config.META_HEIGHT: main_window.frame_height, config.META_FPS: main_window.fps}
        for key, current_val in meta_checks.items():
            loaded_val_str = loaded_metadata.get(key)
            if loaded_val_str:
                try:
                    converter = type(current_val)
                    if converter is float and current_val == 0.0: loaded_typed = float(loaded_val_str)
                    elif converter is int and current_val == 0: loaded_typed = int(float(loaded_val_str))
                    else: loaded_typed = converter(loaded_val_str)
                    if isinstance(current_val, float):
                        if not math.isclose(loaded_typed, current_val, rel_tol=1e-3): mismatches.append(f"{key} (CSV: {loaded_typed} vs Video: {current_val})")
                    elif loaded_typed != current_val: mismatches.append(f"{key} (CSV: {loaded_typed} vs Video: {current_val})")
                except (ValueError, TypeError) as e: mismatches.append(f"{key} (type/value mismatch - CSV: '{loaded_val_str}' vs Video: {current_val}, Error: {e})")
            elif key in config.EXPECTED_METADATA_KEYS: logger.warning(f"Expected key '{key}' missing in CSV metadata for comparison.")
        if mismatches:
            mismatch_msg = "\n - ".join(mismatches); logger.warning(f"Metadata mismatch: {mismatch_msg}")
            reply = QtWidgets.QMessageBox.warning(main_window, "Metadata Mismatch",
                                                  f"Track file metadata may not match current video:\n - {mismatch_msg}\n\nLoad anyway?",
                                                  QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel, QtWidgets.QMessageBox.StandardButton.Cancel)
            if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
                logger.info("Load cancelled due to metadata mismatch.")
                if main_window.statusBar(): main_window.statusBar().showMessage("Load cancelled due to metadata mismatch.", 3000)
                return
            warnings_list.append("Proceeded despite metadata mismatch.")

        data_to_transform_to_internal_px: List[RawParsedData] = []
        for point_raw in parsed_data_raw_from_file:
            tid,fid,tms,x_file_sys,y_file_sys = point_raw; x_fspx, y_fspx = x_file_sys, y_file_sys
            if loaded_data_units == "m":
                if loaded_scale_m_per_px and loaded_scale_m_per_px > 0:
                    x_fspx = x_file_sys / loaded_scale_m_per_px; y_fspx = y_file_sys / loaded_scale_m_per_px
                else: warnings_list.append(f"Cannot convert point (T{tid},F{fid+1}) from meters: Invalid scale.")
            data_to_transform_to_internal_px.append((tid,fid,tms,x_fspx,y_fspx))
        
        transformed_to_internal_tl_px_data: List[RawParsedData] = []
        points_transformed = 0; points_transform_failed = 0
        num_points_to_transform = len(data_to_transform_to_internal_px)
        if num_points_to_transform > 1000 and main_window.statusBar(): main_window.statusBar().showMessage(f"Transforming {num_points_to_transform} points...", 0); QtWidgets.QApplication.processEvents()
        for p_data in data_to_transform_to_internal_px:
            tid,fid,tms,x_fspx,y_fspx = p_data
            try:
                xtl,ytl = coord_transformer.transform_point_to_internal(x_fspx, y_fspx, loaded_mode_enum, loaded_origin_tl, loaded_video_height)
                transformed_to_internal_tl_px_data.append((tid,fid,tms,xtl,ytl)); points_transformed += 1
            except Exception as e: warnings_list.append(f"Skipping point (T{tid},F{fid+1}) due to transformation error: {e}"); points_transform_failed+=1; logger.error(f"Point transform error for (T{tid},F{fid+1}): {e}", exc_info=False)
        if points_transform_failed > 0: QtWidgets.QMessageBox.warning(main_window, "Transform Warning", f"{points_transform_failed} point(s) skipped due to transformation error. See log.")

        success, load_warns = element_manager.load_tracks_from_data(
            transformed_to_internal_tl_px_data,
            main_window.frame_width, main_window.frame_height,
            main_window.total_frames, main_window.fps
        )
        warnings_list.extend(load_warns)
        if not success: raise ValueError(f"ElementManager load failed: {'; '.join(load_warns) or 'Unknown critical error'}")

        scale_manager.set_scale(loaded_scale_m_per_px, called_from_line_definition=bool(loaded_scale_line_coords))
        scale_manager.set_display_in_meters(True if loaded_data_units == "m" and loaded_scale_m_per_px else False)
        
        if loaded_scale_m_per_px is not None and loaded_scale_m_per_px > 0:
            if hasattr(main_window, 'showScaleBarCheckBox') and main_window.showScaleBarCheckBox:
                logger.info("CSV has a valid scale; attempting to check 'Show Scale Bar' checkbox.")
                main_window.showScaleBarCheckBox.setChecked(True)
            else:
                logger.warning("Could not find 'showScaleBarCheckBox' on main_window to auto-check it when loading tracks.")

        if loaded_scale_line_coords:
            scale_manager.set_defined_scale_line(*loaded_scale_line_coords)
        else:
            scale_manager.clear_defined_scale_line()
        
        coord_transformer.set_video_height(loaded_video_height) 
        coord_transformer.set_mode(loaded_mode_enum)
        if loaded_mode_enum == CoordinateSystem.CUSTOM: coord_transformer.set_custom_origin(loaded_origin_tl[0], loaded_origin_tl[1])
        
        main_window.coord_transformer = coord_transformer
        main_window.coord_transformer.set_video_height(main_window.frame_height) 

        if main_window.coord_panel_controller: main_window.coord_panel_controller.update_ui_display()
        if main_window.scale_panel_controller: main_window.scale_panel_controller.update_ui_from_manager()
        main_window._redraw_scene_overlay()

        if not warnings_list:
            if main_window.statusBar(): main_window.statusBar().showMessage(f"Tracks loaded from {os.path.basename(load_path)}", 5000)
            logger.info(f"Tracks loaded successfully from {load_path}")
        else:
            num_warns = len(warnings_list); warn_details = "\n - ".join(warnings_list[:5]);
            if num_warns > 5: warn_details += "\n - ... (see log)"
            QtWidgets.QMessageBox.warning(main_window, "Load Complete with Warnings", f"Tracks loaded from {os.path.basename(load_path)}, but {num_warns} issue(s) found:\n\n - {warn_details}\n\nPlease review and check log.")
            if main_window.statusBar(): main_window.statusBar().showMessage(f"Tracks loaded with {num_warns} warning(s) (see log).", 5000)
        main_window._update_ui_state()

    except (FileNotFoundError, PermissionError) as e:
         error_msg = f"Error loading tracks: {e}"; logger.error(error_msg, exc_info=False)
         QtWidgets.QMessageBox.critical(main_window, "Load Error", error_msg)
         if main_window.statusBar(): main_window.statusBar().showMessage("Error loading tracks: File access error.", 5000)
    except ValueError as e:
         error_msg = f"Error loading tracks: Invalid file format or data.\nDetails: {e}"; logger.error(f"ValueError: {e}", exc_info=False)
         QtWidgets.QMessageBox.critical(main_window, "Load Error", error_msg)
         if main_window.statusBar(): main_window.statusBar().showMessage("Error: Invalid format/data (see log).", 5000)
    except Exception as e:
        error_msg = f"An unexpected error occurred while loading tracks: {str(e)}"; logger.exception("Unexpected error during track loading")
        QtWidgets.QMessageBox.critical(main_window, "Load Error", error_msg)
        if main_window.statusBar(): main_window.statusBar().showMessage("Unexpected error loading tracks. See log.", 5000)