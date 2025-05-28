# kymograph_handler.py
"""
Handles the generation of kymograph data from a specified line in a video.
"""
import logging
from typing import TYPE_CHECKING, Optional, Tuple, List

import numpy as np
import cv2 # For color handling if needed, and potentially interpolation later

if TYPE_CHECKING:
    from video_handler import VideoHandler
    from element_manager import PointData # For line_points type hint

logger = logging.getLogger(__name__)

class KymographHandler:
    """
    Generates kymograph data (a 2D array of pixel values over time)
    along a user-defined line.
    """

    def __init__(self):
        logger.debug("KymographHandler initialized.")

    def generate_kymograph_data(self,
                                line_points_data: List['PointData'],
                                video_handler: 'VideoHandler') -> Optional[np.ndarray]:
        """
        Generates kymograph data for the given line over the full video duration.
        The kymograph's spatial axis will be ordered such that the second point
        clicked (P2) corresponds to the 'top' (or start) of the spatial axis,
        and the first point clicked (P1) corresponds to the 'bottom' (or end).

        Args:
            line_points_data: A list containing two PointData tuples,
                              representing the start (P1 - first click) and end (P2 - second click)
                              points of the measurement line. Each PointData is
                              (frame_index, time_ms, x_tl_px, y_tl_px).
                              The x and y coordinates are Top-Left pixel coordinates.
            video_handler: An instance of VideoHandler to access video frames.

        Returns:
            A NumPy array representing the kymograph (time x distance_along_line),
            or None if generation fails. The 'distance_along_line' dimension samples
            from P2 towards P1.
        """
        if not video_handler.is_loaded:
            logger.error("Cannot generate kymograph: Video not loaded.")
            return None

        if not line_points_data or len(line_points_data) != 2:
            logger.error("Cannot generate kymograph: Invalid line_points_data provided.")
            return None

        # P1 is the first point clicked by the user.
        # P2 is the second point clicked by the user.
        _f1, _t1, x1_p1, y1_p1 = line_points_data[0] # Coordinates of P1
        _f2, _t2, x2_p2, y2_p2 = line_points_data[1] # Coordinates of P2

        logger.info(f"Generating kymograph from line defined by P1:({x1_p1:.1f},{y1_p1:.1f}) and P2:({x2_p2:.1f},{y2_p2:.1f}) "
                    f"over {video_handler.total_frames} frames. Spatial axis will be P2 -> P1.")

        # Length calculation is based on the magnitude between P1 and P2
        length = int(np.round(np.sqrt((x2_p2 - x1_p1)**2 + (y2_p2 - y1_p1)**2)))
        if length == 0:
            logger.warning("Line length is zero. Cannot generate kymograph.")
            return None

        # Generate coordinates for points along the line, sampling FROM P2 TO P1.
        # This means the 0-th index along the spatial dimension of the kymograph
        # will correspond to P2, and the last index to P1.
        line_x_coords = np.linspace(x2_p2, x1_p1, length, dtype=float) # Start from P2.x, end at P1.x
        line_y_coords = np.linspace(y2_p2, y1_p1, length, dtype=float) # Start from P2.y, end at P1.y

        line_x_indices = np.round(line_x_coords).astype(int)
        line_y_indices = np.round(line_y_coords).astype(int)

        kymograph_strips: List[np.ndarray] = []
        num_channels = 0
        first_valid_frame_dtype = np.uint8 # Default dtype

        for frame_idx in range(video_handler.total_frames):
            raw_frame = video_handler.get_raw_frame_at_index(frame_idx)
            if raw_frame is None:
                logger.warning(f"Could not retrieve frame {frame_idx} for kymograph. Attempting to fill with zeros.")
                # If we can't get a frame, create an empty strip if possible
                if num_channels > 0 : # num_channels known from a previous frame
                    empty_strip_shape = (length, num_channels) if num_channels > 1 else (length,)
                    kymograph_strips.append(np.zeros(empty_strip_shape, dtype=first_valid_frame_dtype))
                # If num_channels is not yet known (e.g. first frame fails), we'll have to skip and might have issues stacking.
                # The stacking error handling below will attempt to manage this.
                continue

            if not kymograph_strips: # First successfully processed frame
                if len(raw_frame.shape) == 3:
                    num_channels = raw_frame.shape[2]
                else: # Grayscale
                    num_channels = 1
                first_valid_frame_dtype = raw_frame.dtype


            frame_height, frame_width = raw_frame.shape[:2]

            current_x_indices = np.clip(line_x_indices, 0, frame_width - 1)
            current_y_indices = np.clip(line_y_indices, 0, frame_height - 1)

            try:
                if num_channels > 1:
                    pixel_strip = raw_frame[current_y_indices, current_x_indices, :]
                else: # Grayscale
                    pixel_strip = raw_frame[current_y_indices, current_x_indices]
                kymograph_strips.append(pixel_strip)
            except IndexError as e:
                logger.error(f"IndexError accessing pixel data for frame {frame_idx}. Error: {e}")
                # Create an empty strip of the correct shape if num_channels is known
                if num_channels > 0:
                    empty_strip_shape = (length, num_channels) if num_channels > 1 else (length,)
                    kymograph_strips.append(np.zeros(empty_strip_shape, dtype=first_valid_frame_dtype))


            if (frame_idx + 1) % 100 == 0:
                logger.debug(f"Kymograph: Processed frame {frame_idx + 1}/{video_handler.total_frames}")

        if not kymograph_strips:
            logger.warning("No frames successfully processed for kymograph.")
            return None

        # Ensure all strips have the same shape before stacking
        # This is important if some frames failed and placeholder strips were added
        consistent_strips = []
        if kymograph_strips:
            expected_strip_shape = kymograph_strips[0].shape
            for i, strip in enumerate(kymograph_strips):
                if strip.shape == expected_strip_shape:
                    consistent_strips.append(strip)
                else:
                    logger.warning(f"Strip for frame index {i} (approx) has "
                                   f"shape {strip.shape}, expected {expected_strip_shape}. Filling with zeros.")
                    consistent_strips.append(np.zeros(expected_strip_shape, dtype=first_valid_frame_dtype))
        
        if not consistent_strips: # Should not happen if kymograph_strips was not empty
             logger.error("No consistent strips found to build kymograph.")
             return None

        try:
            kymograph_data = np.stack(consistent_strips, axis=0)
            logger.info(f"Kymograph data generated with shape: {kymograph_data.shape} (Time x Distance [P2->P1] x Channels)")
            return kymograph_data
        except ValueError as e:
            logger.error(f"Error stacking kymograph strips even after consistency check: {e}.")
            # Fallback already attempted in previous version, if it gets here, it's a more fundamental issue.
            return None


# if __name__ == '__main__':
#     # This is a placeholder for basic testing if you run this file directly.
#     # You would need to mock VideoHandler and provide sample line_points_data.
#     logging.basicConfig(level=logging.DEBUG)
#     logger.info("KymographHandler direct run test (requires manual setup).")

#     # --- Mock VideoHandler (very basic) ---
#     class MockVideoHandler:
#         def __init__(self, total_frames, width, height, is_color=True):
#             self.is_loaded = True
#             self.total_frames = total_frames
#             self._frame_width = width
#             self._frame_height = height
#             self.is_color = is_color
#             logger.info(f"MockVideoHandler: TF={total_frames}, W={width}, H={height}, Color={is_color}")


#         def get_raw_frame_at_index(self, frame_idx: int) -> Optional[np.ndarray]:
#             if 0 <= frame_idx < self.total_frames:
#                 # Create a dummy frame with a gradient
#                 intensity = int((frame_idx / self.total_frames) * 255)
#                 if self.is_color:
#                     frame = np.full((self._frame_height, self._frame_width, 3),
#                                      (intensity, (intensity + 50) % 255, (intensity + 100) % 255),
#                                      dtype=np.uint8)
#                 else:
#                     frame = np.full((self._frame_height, self._frame_width), intensity, dtype=np.uint8)

#                 # Add a diagonal line to the dummy frame to see if it's picked up by kymograph
#                 if self._frame_height > 10 and self._frame_width > 10:
#                      cv2.line(frame, (5,5 + frame_idx % 10), (self._frame_width - 5, self._frame_height - 5 - frame_idx %10), (0,0,255) if self.is_color else 255, 1)

#                 return frame
#             return None

#     # --- Example Usage ---
#     mock_video = MockVideoHandler(total_frames=50, width=100, height=80, is_color=True)
#     # Define a sample line (these are TL pixel coordinates)
#     # PointData format: (frame_definition_index, time_ms, x_tl_px, y_tl_px)
#     sample_line: List['PointData'] = [
#         (0, 0.0, 10.0, 10.0),  # p1: (x=10, y=10)
#         (0, 0.0, 90.0, 70.0)   # p2: (x=90, y=70)
#     ]

#     handler = KymographHandler()
#     kymo_data = handler.generate_kymograph_data(sample_line, mock_video)

#     if kymo_data is not None:
#         logger.info(f"Generated kymograph data with shape: {kymo_data.shape}")
#         logger.info(f"Data type: {kymo_data.dtype}")
#         # For testing, you might want to save this as an image if you have matplotlib or save with cv2
#         try:
#             if kymo_data.shape[0] > 0 and kymo_data.shape[1] > 0 : # Ensure non-empty
#                 # Normalize if not uint8 for display with cv2.imshow
#                 if kymo_data.dtype != np.uint8:
#                     if np.max(kymo_data) > 0: # Avoid division by zero
#                         display_data = (kymo_data / np.max(kymo_data) * 255).astype(np.uint8)
#                     else:
#                         display_data = kymo_data.astype(np.uint8)
#                 else:
#                     display_data = kymo_data

#                 cv2.imwrite("test_kymograph.png", display_data)
#                 logger.info("Test kymograph saved as test_kymograph.png (if OpenCV is available)")
#             else:
#                 logger.warning("Kymograph data is empty, cannot save test image.")

#         except ImportError:
#             logger.warning("matplotlib or OpenCV not available for saving test image.")
#         except Exception as e:
#             logger.error(f"Error saving test kymograph: {e}")
#     else:
#         logger.error("Kymograph generation failed.")