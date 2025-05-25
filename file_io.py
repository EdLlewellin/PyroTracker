# file_io.py
"""
Handles file input/output operations for PyroTracker, including
JSON project files and future data-only CSV exports.
"""
import csv
import os
import logging
import math
import json
from typing import List, Tuple, Dict, Any, TYPE_CHECKING, Optional

from PySide6 import QtWidgets, QtCore

import config
from coordinates import CoordinateSystem, CoordinateTransformer
from element_manager import ElementType

if TYPE_CHECKING:
    # from main_window import MainWindow # Not needed in this file directly now
    # from element_manager import ElementManager # Already imported ElementType
    from scale_manager import ScaleManager

logger = logging.getLogger(__name__)

# --- JSON Project File Handling ---

def write_project_json_file(filepath: str, project_data_dict: Dict[str, Any]) -> None:
    """
    Writes the project data dictionary to a JSON file.

    Args:
        filepath: The path to the JSON file to write.
        project_data_dict: The dictionary containing the complete project state.

    Raises:
        IOError: If there's an error writing the file.
        TypeError: If the data is not JSON serializable (should be caught earlier).
        Exception: For other unexpected errors.
    """
    logger.info(f"Writing project data to JSON file: {filepath}")
    try:
        with open(filepath, 'w', encoding='utf-8') as jsonfile:
            json.dump(project_data_dict, jsonfile, indent=2)
        logger.info(f"Project data successfully written to {filepath}")
    except (IOError, TypeError) as e:
        logger.error(f"Error writing JSON file '{filepath}': {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error writing JSON file '{filepath}': {e}", exc_info=True)
        raise

def read_project_json_file(filepath: str) -> Dict[str, Any]:
    """
    Reads a JSON project file and returns its content as a dictionary.

    Args:
        filepath: The path to the JSON project file.

    Returns:
        Dict[str, Any]: The loaded project data.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If there's a permission issue reading the file.
        json.JSONDecodeError: If the file is not valid JSON.
        Exception: For other unexpected errors.
    """
    logger.info(f"Reading project data from JSON file: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as jsonfile:
            project_data_dict = json.load(jsonfile)
        logger.info(f"Project data successfully read from {filepath}")
        return project_data_dict
    except FileNotFoundError:
        logger.error(f"JSON project file not found: {filepath}", exc_info=True)
        raise
    except PermissionError:
        logger.error(f"Permission denied reading JSON project file: {filepath}", exc_info=True)
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON project file '{filepath}': {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error reading JSON project file '{filepath}': {e}", exc_info=True)
        raise

# --- Unit Selection Dialog (Phase F.2, Step 2) ---
class UnitSelectionDialog(QtWidgets.QDialog):
    """
    A dialog for choosing export units (pixels or real-world units).
    """
    def __init__(self, is_scale_defined: bool, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Choose Export Units")
        self.setModal(True)
        self.setMinimumWidth(350)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(10)

        info_label = QtWidgets.QLabel("Select units for exported coordinate and length data:")
        self._layout.addWidget(info_label)

        self.pixel_radio = QtWidgets.QRadioButton("Pixel Coordinates (current display system)")
        self.pixel_radio.setToolTip(
            "Exports X, Y coordinates in pixels based on the currently active coordinate system "
            "(Top-Left, Bottom-Left, or Custom). Lengths for lines will also be in pixels."
        )
        self.pixel_radio.setChecked(True) # Default choice
        self._layout.addWidget(self.pixel_radio)

        self.meters_radio = QtWidgets.QRadioButton("Real-World Units (meters)")
        self.meters_radio.setToolTip(
            "Exports X, Y coordinates and lengths for lines in meters. "
            "Requires a scale to be defined."
        )
        self._layout.addWidget(self.meters_radio)

        if is_scale_defined:
            self.meters_radio.setEnabled(True)
        else:
            self.meters_radio.setEnabled(False)
            self.meters_radio.setToolTip(
                "Real-World Units (meters) - Disabled: No scale is currently defined."
            )
            self.pixel_radio.setChecked(True)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self._layout.addWidget(button_box)

        logger.debug(f"UnitSelectionDialog initialized. Scale defined: {is_scale_defined}")

    def get_selected_units(self) -> Optional[str]:
        """
        Returns the selected unit choice as a string ("pixels" or "meters"),
        or None if the dialog was cancelled.
        """
        if self.result() == QtWidgets.QDialog.DialogCode.Accepted:
            if self.meters_radio.isChecked() and self.meters_radio.isEnabled():
                return "meters"
            return "pixels"
        return None


# --- Data-Only CSV Export Function (Phase F.4) ---
# --- Data-Only CSV Export Function (Phase F.4) ---
def export_elements_to_simple_csv(filepath: str,
                                  elements_data: List[Dict[str, Any]], # This is List[ElementDictFromManager]
                                  element_type_exported: ElementType,
                                  desired_units: str,
                                  scale_manager: 'ScaleManager',
                                  coord_transformer: CoordinateTransformer) -> bool:
    """
    Exports track or line element data to a simple CSV file.

    Args:
        filepath: The path to save the CSV file.
        elements_data: List of element dictionaries (tracks or lines) from ElementManager.
                       The 'data' key in these dictionaries contains a list of PointData tuples.
        element_type_exported: The type of elements being exported (TRACK or MEASUREMENT_LINE).
        desired_units: "pixels" or "meters".
        scale_manager: Instance of ScaleManager for unit conversion.
        coord_transformer: Instance of CoordinateTransformer for coordinate system transformation.

    Returns:
        True if export was successful, False otherwise.
    """
    logger.info(f"Exporting {element_type_exported.name} data to CSV: {filepath} in units: {desired_units}")
    unit_suffix = "_m" if desired_units == "meters" else "_px"
    header: List[str] = []
    rows_to_write: List[List[Any]] = []

    try:
        if element_type_exported == ElementType.TRACK:
            header = ["track_id", "frame_index", "time_ms", f"x{unit_suffix}", f"y{unit_suffix}"]
            for el_dict in elements_data:
                element_id = el_dict.get('id', 'N/A')
                # el_dict['data'] is List[PointData], where PointData is Tuple[int, float, float, float]
                # PointData = (frame_idx, time_ms, x_tl_px, y_tl_px)
                for point_tuple in el_dict.get('data', []): # point_tuple is a PointData tuple
                    frame_idx, time_ms, x_tl_px, y_tl_px = point_tuple # Unpack the tuple
                    
                    x_cs_px, y_cs_px = coord_transformer.transform_point_for_display(x_tl_px, y_tl_px)

                    x_out, y_out = x_cs_px, y_cs_px
                    if desired_units == "meters":
                        scale_m_px = scale_manager.get_scale_m_per_px()
                        if scale_m_px:
                            x_out = x_cs_px * scale_m_px
                            y_out = y_cs_px * scale_m_px
                        else:
                            logger.warning("Attempting to export tracks in meters but no scale is set. Using pixels.")
                            x_out, y_out = x_cs_px, y_cs_px 

                    rows_to_write.append([
                        element_id,
                        frame_idx, # Already an int
                        f"{time_ms:.4f}",
                        f"{x_out:.4f}",
                        f"{y_out:.4f}"
                    ])
        elif element_type_exported == ElementType.MEASUREMENT_LINE:
            header = ["line_id", "definition_frame_index",
                      f"p1_x{unit_suffix}", f"p1_y{unit_suffix}",
                      f"p2_x{unit_suffix}", f"p2_y{unit_suffix}",
                      f"length{unit_suffix}", "angle_deg"]
            for el_dict in elements_data:
                element_id = el_dict.get('id', 'N/A')
                # el_dict['data'] is List[PointData]
                point_list_tuples = el_dict.get('data', []) 
                if len(point_list_tuples) == 2:
                    p1_tuple, p2_tuple = point_list_tuples[0], point_list_tuples[1]
                    
                    # Unpack PointData tuples
                    def_frame_idx, _, p1_x_tl_px, p1_y_tl_px = p1_tuple
                    _,         _, p2_x_tl_px, p2_y_tl_px = p2_tuple
                    # Note: Assuming time_ms from points isn't needed for line definition export,
                    # definition_frame_index is taken from the first point.

                    p1_x_cs_px, p1_y_cs_px = coord_transformer.transform_point_for_display(p1_x_tl_px, p1_y_tl_px)
                    p2_x_cs_px, p2_y_cs_px = coord_transformer.transform_point_for_display(p2_x_tl_px, p2_y_tl_px)

                    p1_x_out, p1_y_out = p1_x_cs_px, p1_y_cs_px
                    p2_x_out, p2_y_out = p2_x_cs_px, p2_y_cs_px
                    
                    dx_cs_px, dy_cs_px = p2_x_cs_px - p1_x_cs_px, p2_y_cs_px - p1_y_cs_px
                    pixel_length_cs = math.sqrt(dx_cs_px**2 + dy_cs_px**2)
                    length_out = pixel_length_cs

                    if desired_units == "meters":
                        scale_m_px = scale_manager.get_scale_m_per_px()
                        if scale_m_px:
                            p1_x_out = p1_x_cs_px * scale_m_px
                            p1_y_out = p1_y_cs_px * scale_m_px
                            p2_x_out = p2_x_cs_px * scale_m_px
                            p2_y_out = p2_y_cs_px * scale_m_px
                            length_out = pixel_length_cs * scale_m_px
                        else:
                            logger.warning(f"Attempting to export line {element_id} in meters but no scale is set. Using pixels.")

                    angle_rad = math.atan2(-dy_cs_px, dx_cs_px) 
                    angle_deg = math.degrees(angle_rad)
                    if angle_deg < 0: angle_deg += 360.0

                    rows_to_write.append([
                        element_id,
                        def_frame_idx,
                        f"{p1_x_out:.4f}", f"{p1_y_out:.4f}",
                        f"{p2_x_out:.4f}", f"{p2_y_out:.4f}",
                        f"{length_out:.4f}", f"{angle_deg:.2f}"
                    ])
                else:
                    logger.warning(f"Measurement line {element_id} does not have 2 points. Skipping for CSV export.")
        else:
            logger.error(f"Unsupported element type for CSV export: {element_type_exported}")
            return False

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if header:
                writer.writerow(header)
            writer.writerows(rows_to_write)
        
        logger.info(f"Successfully exported {len(rows_to_write)} data rows to {filepath}")
        return True

    except IOError as e:
        logger.error(f"IOError during CSV export to '{filepath}': {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error during CSV export to '{filepath}': {e}", exc_info=True)
        return False