# kymograph_handler.py
"""
Handles the generation of kymograph data from a specified line in a video.
"""
import logging
from typing import TYPE_CHECKING, Optional, Tuple, List

import numpy as np
import cv2 # For color handling if needed, and potentially interpolation later
from PySide6 import QtCore # Added for signals

if TYPE_CHECKING:
    from video_handler import VideoHandler
    from element_manager import PointData # For line_points type hint

logger = logging.getLogger(__name__)

class KymographHandler(QtCore.QObject): # Inherit from QObject for signals
    """
    Generates kymograph data (a 2D array of pixel values over time)
    along a user-defined line.
    """
    # --- Phase 2: Add Signals ---
    kymographGenerationStarted = QtCore.Signal()
    kymographGenerationProgress = QtCore.Signal(str, int, int)  # message, current_value, max_value
    kymographGenerationFinished = QtCore.Signal(object, str)    # kymo_data_np (np.ndarray | None), status_message

    def __init__(self, parent: Optional[QtCore.QObject] = None): # Added parent for QObject
        super().__init__(parent) # Call QObject constructor
        logger.debug("KymographHandler initialized.")

    def generate_kymograph_data(self,
                                line_points_data: List['PointData'],
                                video_handler: 'VideoHandler',
                                start_frame_idx: int, # New parameter
                                end_frame_idx: int    # New parameter
                                ) -> Optional[np.ndarray]: # Return type will be handled by signal
        """
        Generates kymograph data for the given line over the specified frame range.
        The kymograph's spatial axis will be ordered such that the second point
        clicked (P2) corresponds to the 'top' (or start) of the spatial axis,
        and the first point clicked (P1) corresponds to the 'bottom' (or end).

        Args:
            line_points_data: A list containing two PointData tuples for the line.
            video_handler: An instance of VideoHandler to access video frames.
            start_frame_idx: The 0-based starting frame index for kymograph generation.
            end_frame_idx: The 0-based ending frame index (inclusive) for kymograph generation.

        Emits:
            kymographGenerationStarted: When generation begins.
            kymographGenerationProgress: Periodically during generation.
            kymographGenerationFinished: When generation completes or fails,
                                         with the kymograph data (or None) and a message.
        Returns:
            This method will emit results via signals. The direct return type is
            kept for compatibility but the primary way to get data is via the signal.
            Returns None if initial checks fail before starting the loop.
        """
        self.kymographGenerationStarted.emit()

        if not video_handler.is_loaded:
            logger.error("Cannot generate kymograph: Video not loaded.")
            self.kymographGenerationFinished.emit(None, "Error: Video not loaded.")
            return None

        if not line_points_data or len(line_points_data) != 2:
            logger.error("Cannot generate kymograph: Invalid line_points_data provided.")
            self.kymographGenerationFinished.emit(None, "Error: Invalid line data.")
            return None

        if not (0 <= start_frame_idx <= end_frame_idx < video_handler.total_frames):
            err_msg = f"Invalid frame range: Start={start_frame_idx}, End={end_frame_idx}, Total={video_handler.total_frames}"
            logger.error(err_msg)
            self.kymographGenerationFinished.emit(None, f"Error: {err_msg}")
            return None

        num_frames_to_process = (end_frame_idx - start_frame_idx) + 1

        _f1, _t1, x1_p1, y1_p1 = line_points_data[0] # P1
        _f2, _t2, x2_p2, y2_p2 = line_points_data[1] # P2

        logger.info(f"Generating kymograph from line P1:({x1_p1:.1f},{y1_p1:.1f}) to P2:({x2_p2:.1f},{y2_p2:.1f}) "
                    f"for frames {start_frame_idx} to {end_frame_idx} ({num_frames_to_process} frames). Spatial axis P2 -> P1.")

        length = int(np.round(np.sqrt((x2_p2 - x1_p1)**2 + (y2_p2 - y1_p1)**2)))
        if length == 0:
            logger.warning("Line length is zero. Cannot generate kymograph.")
            self.kymographGenerationFinished.emit(None, "Error: Line length is zero.")
            return None

        line_x_coords = np.linspace(x2_p2, x1_p1, length, dtype=float)
        line_y_coords = np.linspace(y2_p2, y1_p1, length, dtype=float)
        line_x_indices = np.round(line_x_coords).astype(int)
        line_y_indices = np.round(line_y_coords).astype(int)

        kymograph_strips: List[np.ndarray] = []
        num_channels = 0
        first_valid_frame_dtype = np.uint8
        processed_frames_count = 0

        for frame_idx in range(start_frame_idx, end_frame_idx + 1):
            # Cancellation check could be added here if MainWindow passes a flag
            # For now, assuming synchronous processing and relying on MainWindow to manage the dialog.

            raw_frame = video_handler.get_raw_frame_at_index(frame_idx)
            processed_frames_count += 1
            progress_message = f"Processing frame {processed_frames_count}/{num_frames_to_process} (Video frame {frame_idx + 1})"
            self.kymographGenerationProgress.emit(progress_message, processed_frames_count, num_frames_to_process)


            if raw_frame is None:
                logger.warning(f"Could not retrieve frame {frame_idx} for kymograph. Filling with zeros.")
                if num_channels > 0:
                    empty_strip_shape = (length, num_channels) if num_channels > 1 else (length,)
                    kymograph_strips.append(np.zeros(empty_strip_shape, dtype=first_valid_frame_dtype))
                continue

            if not kymograph_strips or (num_channels == 0 and not kymograph_strips): # First successfully processed frame in this run
                if len(raw_frame.shape) == 3:
                    num_channels = raw_frame.shape[2]
                else:
                    num_channels = 1
                first_valid_frame_dtype = raw_frame.dtype

            frame_height, frame_width = raw_frame.shape[:2]
            current_x_indices = np.clip(line_x_indices, 0, frame_width - 1)
            current_y_indices = np.clip(line_y_indices, 0, frame_height - 1)

            try:
                if num_channels > 1:
                    pixel_strip = raw_frame[current_y_indices, current_x_indices, :]
                else:
                    pixel_strip = raw_frame[current_y_indices, current_x_indices]
                kymograph_strips.append(pixel_strip)
            except IndexError as e:
                logger.error(f"IndexError accessing pixel data for frame {frame_idx}. Error: {e}")
                if num_channels > 0:
                    empty_strip_shape = (length, num_channels) if num_channels > 1 else (length,)
                    kymograph_strips.append(np.zeros(empty_strip_shape, dtype=first_valid_frame_dtype))

        if not kymograph_strips:
            logger.warning("No frames successfully processed for kymograph.")
            self.kymographGenerationFinished.emit(None, "Error: No frames processed.")
            return None

        consistent_strips = []
        if kymograph_strips: # Should always be true if we didn't return None above
            expected_strip_shape = kymograph_strips[0].shape
            for i, strip in enumerate(kymograph_strips):
                if strip.shape == expected_strip_shape:
                    consistent_strips.append(strip)
                else:
                    logger.warning(f"Strip for processed frame index {i} has shape {strip.shape}, expected {expected_strip_shape}. Filling with zeros.")
                    consistent_strips.append(np.zeros(expected_strip_shape, dtype=first_valid_frame_dtype))
        
        if not consistent_strips:
             logger.error("No consistent strips found to build kymograph.")
             self.kymographGenerationFinished.emit(None, "Error: Failed to prepare kymograph data strips.")
             return None

        try:
            kymograph_data = np.stack(consistent_strips, axis=0)
            success_msg = f"Kymograph data generated ({kymograph_data.shape[0]} time points, {kymograph_data.shape[1]} spatial points)."
            logger.info(success_msg)
            self.kymographGenerationFinished.emit(kymograph_data, success_msg)
            return kymograph_data # Still return for potential direct use, though signal is primary
        except ValueError as e:
            err_msg = f"Error stacking kymograph strips: {e}"
            logger.error(err_msg)
            self.kymographGenerationFinished.emit(None, f"Error: {err_msg}")
            return None