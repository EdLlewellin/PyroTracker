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

        Args:
            line_points_data: A list containing two PointData tuples,
                              representing the start (p1) and end (p2) points
                              of the measurement line. Each PointData is
                              (frame_index, time_ms, x_tl_px, y_tl_px).
                              The x and y coordinates are Top-Left pixel coordinates.
            video_handler: An instance of VideoHandler to access video frames.

        Returns:
            A NumPy array representing the kymograph (time x distance_along_line),
            or None if generation fails (e.g., video not loaded, invalid line).
            The pixel values will depend on whether the video is color or grayscale.
            For color videos, it will likely be (time, distance_along_line, channels).
        """
        if not video_handler.is_loaded:
            logger.error("Cannot generate kymograph: Video not loaded.")
            return None

        if not line_points_data or len(line_points_data) != 2:
            logger.error("Cannot generate kymograph: Invalid line_points_data provided.")
            return None

        # Extract start and end points (Top-Left pixel coordinates)
        # The frame_index and time_ms from line_points_data refer to the frame
        # on which the line was defined, not relevant for kymograph pixel extraction across all frames.
        _f1, _t1, x1, y1 = line_points_data[0]
        _f2, _t2, x2, y2 = line_points_data[1]

        logger.info(f"Generating kymograph from line ({x1:.1f},{y1:.1f}) to ({x2:.1f},{y2:.1f}) "
                    f"over {video_handler.total_frames} frames.")

        # Determine the number of points to sample along the line.
        # This defines the 'width' of the kymograph (distance axis).
        # For simplicity, sample one point for each pixel unit of length.
        length = int(np.round(np.sqrt((x2 - x1)**2 + (y2 - y1)**2)))
        if length == 0:
            logger.warning("Line length is zero. Cannot generate kymograph.")
            return None

        # Generate coordinates for points along the line
        line_x_coords = np.linspace(x1, x2, length, dtype=float)
        line_y_coords = np.linspace(y1, y2, length, dtype=float)

        # Round to nearest integer coordinates for pixel extraction (simplest method)
        # Ensure coordinates stay within image bounds later.
        line_x_indices = np.round(line_x_coords).astype(int)
        line_y_indices = np.round(line_y_coords).astype(int)

        kymograph_strips: List[np.ndarray] = []
        num_channels = 0

        for frame_idx in range(video_handler.total_frames):
            raw_frame = video_handler.get_raw_frame_at_index(frame_idx)
            if raw_frame is None:
                logger.warning(f"Could not retrieve frame {frame_idx} for kymograph. Skipping.")
                # Could fill with black/zeros or stop. For now, skip and kymograph will be shorter.
                # For a more robust approach, one might pre-allocate kymograph_data and fill.
                continue

            if frame_idx == 0: # Determine number of channels from the first valid frame
                if len(raw_frame.shape) == 3:
                    num_channels = raw_frame.shape[2]
                else: # Grayscale
                    num_channels = 1

            frame_height, frame_width = raw_frame.shape[:2]

            # Clamp coordinates to be within frame boundaries
            current_x_indices = np.clip(line_x_indices, 0, frame_width - 1)
            current_y_indices = np.clip(line_y_indices, 0, frame_height - 1)

            # Extract pixels. For color images, raw_frame[y, x] gives the (B,G,R) tuple.
            # For grayscale, it gives the intensity.
            try:
                if num_channels > 1:
                    pixel_strip = raw_frame[current_y_indices, current_x_indices, :]
                else: # Grayscale
                    pixel_strip = raw_frame[current_y_indices, current_x_indices]
                kymograph_strips.append(pixel_strip)
            except IndexError as e:
                logger.error(f"IndexError accessing pixel data for frame {frame_idx} at line coordinates. "
                             f"Line coords may extend beyond frame boundaries despite clipping. Error: {e}")
                # Decide how to handle: skip frame, add empty strip, etc.
                # For now, let's create an empty strip of the correct shape if num_channels is known
                if num_channels > 0:
                    empty_strip_shape = (length, num_channels) if num_channels > 1 else (length,)
                    kymograph_strips.append(np.zeros(empty_strip_shape, dtype=raw_frame.dtype))
                else: # Cannot determine dtype or channels yet, skip.
                    logger.warning(f"Cannot create empty strip for frame {frame_idx} as num_channels not yet determined.")


            if (frame_idx + 1) % 100 == 0: # Log progress every 100 frames
                logger.debug(f"Kymograph: Processed frame {frame_idx + 1}/{video_handler.total_frames}")

        if not kymograph_strips:
            logger.warning("No frames processed for kymograph.")
            return None

        try:
            kymograph_data = np.stack(kymograph_strips, axis=0)
            # Shape will be (num_frames_processed, num_points_along_line) for grayscale
            # or (num_frames_processed, num_points_along_line, num_channels) for color.
            logger.info(f"Kymograph data generated with shape: {kymograph_data.shape}")
            return kymograph_data
        except ValueError as e:
            # This might happen if strips have inconsistent shapes, e.g., if some frames failed
            # and weren't replaced by correctly shaped empty strips.
            logger.error(f"Error stacking kymograph strips: {e}. This might be due to inconsistent frame data.")
            num_valid_strips = len(kymograph_strips)
            first_strip_shape = kymograph_strips[0].shape if num_valid_strips > 0 else (length, num_channels) if num_channels > 0 else (length,)
            
            # Attempt to create a placeholder array and fill it
            logger.info(f"Attempting to create kymograph data by filling a pre-allocated array of shape: ({video_handler.total_frames},) + {first_strip_shape}")
            try:
                final_shape = (video_handler.total_frames,) + first_strip_shape
                final_dtype = kymograph_strips[0].dtype if num_valid_strips > 0 else np.uint8
                kymograph_data_filled = np.zeros(final_shape, dtype=final_dtype)
                
                # This assumes kymograph_strips corresponds to frame_idx if some were skipped.
                # A more robust way would be to store (frame_idx, strip) and fill accordingly.
                # For now, this is a simpler recovery.
                for i, strip in enumerate(kymograph_strips):
                    if i < video_handler.total_frames and strip.shape == first_strip_shape:
                        kymograph_data_filled[i] = strip
                    else:
                        logger.warning(f"Skipping strip {i} during fill due to shape mismatch or index out of bounds.")
                logger.info(f"Kymograph data (filled) generated with shape: {kymograph_data_filled.shape}")
                return kymograph_data_filled
            except Exception as fill_e:
                logger.error(f"Critical error creating/filling kymograph data array: {fill_e}")
                return None


if __name__ == '__main__':
    # This is a placeholder for basic testing if you run this file directly.
    # You would need to mock VideoHandler and provide sample line_points_data.
    logging.basicConfig(level=logging.DEBUG)
    logger.info("KymographHandler direct run test (requires manual setup).")

    # --- Mock VideoHandler (very basic) ---
    class MockVideoHandler:
        def __init__(self, total_frames, width, height, is_color=True):
            self.is_loaded = True
            self.total_frames = total_frames
            self._frame_width = width
            self._frame_height = height
            self.is_color = is_color
            logger.info(f"MockVideoHandler: TF={total_frames}, W={width}, H={height}, Color={is_color}")


        def get_raw_frame_at_index(self, frame_idx: int) -> Optional[np.ndarray]:
            if 0 <= frame_idx < self.total_frames:
                # Create a dummy frame with a gradient
                intensity = int((frame_idx / self.total_frames) * 255)
                if self.is_color:
                    frame = np.full((self._frame_height, self._frame_width, 3),
                                     (intensity, (intensity + 50) % 255, (intensity + 100) % 255),
                                     dtype=np.uint8)
                else:
                    frame = np.full((self._frame_height, self._frame_width), intensity, dtype=np.uint8)

                # Add a diagonal line to the dummy frame to see if it's picked up by kymograph
                if self._frame_height > 10 and self._frame_width > 10:
                     cv2.line(frame, (5,5 + frame_idx % 10), (self._frame_width - 5, self._frame_height - 5 - frame_idx %10), (0,0,255) if self.is_color else 255, 1)

                return frame
            return None

    # --- Example Usage ---
    mock_video = MockVideoHandler(total_frames=50, width=100, height=80, is_color=True)
    # Define a sample line (these are TL pixel coordinates)
    # PointData format: (frame_definition_index, time_ms, x_tl_px, y_tl_px)
    sample_line: List['PointData'] = [
        (0, 0.0, 10.0, 10.0),  # p1: (x=10, y=10)
        (0, 0.0, 90.0, 70.0)   # p2: (x=90, y=70)
    ]

    handler = KymographHandler()
    kymo_data = handler.generate_kymograph_data(sample_line, mock_video)

    if kymo_data is not None:
        logger.info(f"Generated kymograph data with shape: {kymo_data.shape}")
        logger.info(f"Data type: {kymo_data.dtype}")
        # For testing, you might want to save this as an image if you have matplotlib or save with cv2
        try:
            if kymo_data.shape[0] > 0 and kymo_data.shape[1] > 0 : # Ensure non-empty
                # Normalize if not uint8 for display with cv2.imshow
                if kymo_data.dtype != np.uint8:
                    if np.max(kymo_data) > 0: # Avoid division by zero
                        display_data = (kymo_data / np.max(kymo_data) * 255).astype(np.uint8)
                    else:
                        display_data = kymo_data.astype(np.uint8)
                else:
                    display_data = kymo_data

                cv2.imwrite("test_kymograph.png", display_data)
                logger.info("Test kymograph saved as test_kymograph.png (if OpenCV is available)")
            else:
                logger.warning("Kymograph data is empty, cannot save test image.")

        except ImportError:
            logger.warning("matplotlib or OpenCV not available for saving test image.")
        except Exception as e:
            logger.error(f"Error saving test kymograph: {e}")
    else:
        logger.error("Kymograph generation failed.")