# video_handler.py
"""
Manages video loading, playback, navigation, and frame extraction
for the PyroTracker application using OpenCV and QTimer.
"""
import cv2 # type: ignore
import numpy as np
import logging
import os
from typing import Optional, Dict, Any

from PySide6 import QtCore, QtGui

# Get a logger for this module
logger = logging.getLogger(__name__)

class VideoHandler(QtCore.QObject):
    """
    Handles video operations: loading, releasing, playback, navigation, frame conversion.

    Uses OpenCV (cv2) for video file interaction and QTimer for timed playback.
    Provides signals to communicate video state changes and new frames to the UI.

    Signals:
        videoLoaded (dict): Emitted successfully opening a video. The dict contains
                            video properties like 'filepath', 'filename', 'total_frames',
                            'fps', 'width', 'height', 'duration_ms'.
        videoLoadFailed (str): Emitted if opening a video fails, carrying an error message.
        frameChanged (QtGui.QPixmap, int): Emitted when a new frame is ready for display,
                                           providing the frame pixmap and its 0-based index.
        playbackStateChanged (bool): Emitted when playback starts (True) or stops (False).
    """
    # --- Signals ---
    videoLoaded = QtCore.Signal(dict)
    videoLoadFailed = QtCore.Signal(str)
    frameChanged = QtCore.Signal(QtGui.QPixmap, int)
    playbackStateChanged = QtCore.Signal(bool)

    # --- Internal State Variables ---
    _video_capture: Optional[cv2.VideoCapture] = None # OpenCV video capture object
    _play_timer: QtCore.QTimer # Timer for triggering frame advances during playback
    # Video properties
    _video_filepath: str = ""
    _total_frames: int = 0
    _fps: float = 0.0
    _frame_width: int = 0
    _frame_height: int = 0
    _total_duration_ms: float = 0.0
    # Playback/Navigation state
    _current_frame_index: int = -1 # 0-based index of the currently displayed/processed frame
    _is_playing: bool = False # True if the playback timer is active
    _is_loaded: bool = False # True if a video is successfully loaded

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        """Initializes the VideoHandler and its playback timer."""
        super().__init__(parent)
        logger.info("Initializing VideoHandler...")
        self._play_timer = QtCore.QTimer(self)
        # Use PreciseTimer for potentially smoother playback timing
        self._play_timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self._play_timer.timeout.connect(self._advance_frame)
        logger.info("VideoHandler initialized.")

    # --- Public Methods ---

    def open_video(self, filepath: str) -> bool:
        """
        Opens a video file using OpenCV, extracts its properties, and prepares for playback/navigation.

        Releases any previously opened video first. Emits `videoLoaded` on success
        (after displaying the first frame) or `videoLoadFailed` on error.

        Args:
            filepath: The path to the video file.

        Returns:
            True if the video was opened successfully, False otherwise.
        """
        logger.info(f"Attempting to open video: {filepath}")
        self.release_video() # Ensure any previous video is closed

        try:
            # Attempt to open the video file with OpenCV
            cap = cv2.VideoCapture(filepath)
            if not cap or not cap.isOpened():
                raise IOError(f"Cannot open video file via OpenCV: {filepath}")

            # Retrieve video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.debug(f"Raw video properties: Frames={total_frames}, FPS={fps}, Size={frame_width}x{frame_height}")

            # Validate properties
            if total_frames <= 0 or frame_width <= 0 or frame_height <= 0:
                cap.release() # Release capture before raising error
                raise ValueError("Video file reports invalid dimensions or zero/negative frames.")

            # Handle potential invalid FPS value from video metadata
            if fps <= 0:
                logger.warning(f"Video FPS reported as {fps}. Using fallback FPS=30 for calculations.")
                fps = 30.0 # Use a sensible default

            # Store validated properties and set state
            self._video_capture = cap
            self._video_filepath = filepath
            self._total_frames = total_frames
            self._fps = fps
            self._frame_width = frame_width
            self._frame_height = frame_height
            self._total_duration_ms = (self._total_frames / self._fps) * 1000 if self._fps > 0 else 0.0
            self._is_loaded = True
            self._current_frame_index = -1 # Mark as not yet on a specific frame

            # Set timer interval based on FPS for playback
            if self._fps > 0:
                timer_interval: int = int(1000 / self._fps) # Milliseconds per frame
                self._play_timer.setInterval(max(1, timer_interval)) # Ensure interval > 0
                logger.debug(f"Playback timer interval set to {self._play_timer.interval()} ms.")
            else:
                logger.warning("Cannot set playback timer interval due to invalid FPS.")

            # Get info dict AFTER setting internal state but BEFORE emitting first frame
            video_info = self.get_video_info()
            logger.info(f"Video loaded successfully: '{os.path.basename(filepath)}'. Emitting videoLoaded.")
            self.videoLoaded.emit(video_info) # Signal success *before* first frame signal

            # Read and display the first frame (frame 0)
            self._read_and_emit_frame(0)
            return True

        except (IOError, ValueError, cv2.error, Exception) as e:
            # Catch potential OpenCV errors, file errors, value errors
            error_msg = f"Error opening video '{os.path.basename(filepath)}': {str(e)}"
            logger.error(error_msg, exc_info=True) # Log full traceback for debugging
            self.release_video() # Clean up any partially opened resources
            self.videoLoadFailed.emit(error_msg) # Signal failure
            return False

    def release_video(self) -> None:
        """Releases the OpenCV video capture resource and resets internal state."""
        logger.info("Releasing video resources...")
        self.stop_playback() # Ensure timer is stopped first
        if self._video_capture:
            try:
                self._video_capture.release()
                logger.debug("cv2.VideoCapture released.")
            except Exception as e:
                logger.error(f"Exception during cv2.VideoCapture release: {e}", exc_info=True)
        # Reset all state variables
        self._video_capture = None
        self._video_filepath = ""
        self._total_frames = 0
        self._fps = 0.0
        self._frame_width = 0
        self._frame_height = 0
        self._total_duration_ms = 0.0
        self._current_frame_index = -1
        self._is_playing = False
        self._is_loaded = False
        logger.info("Video resources released and state reset.")

    def get_video_info(self) -> Dict[str, Any]:
        """Returns a dictionary containing key properties of the loaded video."""
        if not self._is_loaded:
            logger.warning("get_video_info called but no video is loaded.")
            return {}
        # Return a snapshot of the current video state
        return {
            "filepath": self._video_filepath,
            "filename": os.path.basename(self._video_filepath),
            "total_frames": self._total_frames,
            "fps": self._fps,
            "width": self._frame_width,
            "height": self._frame_height,
            "duration_ms": self._total_duration_ms,
            "current_frame": self._current_frame_index, # Note: May be -1 briefly after load
            "is_loaded": self._is_loaded,
        }

    def get_metadata_dictionary(self) -> Dict[str, Any]:
        """
        Retrieves readily available video metadata using OpenCV properties
        and internal state for display (e.g., in a dialog).

        Returns:
            A dictionary containing metadata key-value pairs. Returns an
            empty dictionary if no video is loaded.
        """
        if not self._is_loaded or not self._video_capture:
            logger.warning("get_metadata_dictionary called but no video loaded.")
            return {}

        logger.debug("Retrieving metadata dictionary...")
        metadata = {}

        # Basic Info (tracked internally)
        metadata["File Path"] = self._video_filepath
        metadata["Duration (ms)"] = f"{self._total_duration_ms:.2f}" if self._total_duration_ms >= 0 else "N/A"
        metadata["Total Frames"] = self._total_frames
        metadata["Frame Width"] = self._frame_width
        metadata["Frame Height"] = self._frame_height
        metadata["FPS"] = f"{self._fps:.3f}" if self._fps > 0 else "N/A"

        # Info directly from OpenCV get() (can be unreliable)
        try:
            # FourCC Codec Identifier
            fourcc_int = int(self._video_capture.get(cv2.CAP_PROP_FOURCC))
            if fourcc_int != 0:
                # Decode the integer into a 4-character string
                fourcc_code = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])
                fourcc_code = "".join(filter(str.isprintable, fourcc_code)).strip() # Clean up
                metadata["FourCC Codec"] = fourcc_code if fourcc_code else "N/A"
            else:
                 metadata["FourCC Codec"] = "N/A"

            # Video Bitrate (Often unreliable)
            bitrate = self._video_capture.get(cv2.CAP_PROP_BITRATE)
            metadata["Bitrate (bps)"] = f"{int(bitrate)}" if bitrate > 0 else "N/A"

            # Add more CAP_PROP_ lookups here if needed

        except Exception as e:
            logger.error(f"Error retrieving specific OpenCV properties: {e}", exc_info=False)
            # Add placeholder values if errors occurred during retrieval
            if "FourCC Codec" not in metadata: metadata["FourCC Codec"] = "Error"
            if "Bitrate (bps)" not in metadata: metadata["Bitrate (bps)"] = "Error"

        logger.debug(f"Generated metadata dictionary: {metadata}")
        return metadata

    def seek_frame(self, frame_index: int) -> None:
        """
        Seeks to and displays a specific frame index. Stops playback if active.
        Clamps the index if it's out of bounds.
        """
        if not self._is_loaded:
            logger.warning("seek_frame called but no video loaded.")
            return

        # Clamp frame index to valid range [0, total_frames - 1]
        clamped_index = max(0, min(frame_index, self._total_frames - 1))
        if clamped_index != frame_index:
            logger.warning(f"seek_frame: Index {frame_index} out of bounds [0, {self._total_frames-1}]. Clamping to {clamped_index}.")
            frame_index = clamped_index

        # Stop playback before seeking manually
        if self._is_playing:
            self.stop_playback()

        # Only read and emit if the target frame is different from the current one
        if frame_index != self._current_frame_index:
            logger.debug(f"Seeking to frame {frame_index}")
            self._read_and_emit_frame(frame_index)
        else:
            logger.debug(f"Seek requested to current frame ({frame_index}), no operation needed.")

    def next_frame(self) -> None:
        """Advances to the next frame, if possible. Stops playback if active."""
        if not self._is_loaded: return
        target_frame = self._current_frame_index + 1
        if target_frame < self._total_frames:
            logger.debug("Moving to next frame.")
            if self._is_playing: self.stop_playback() # Stop playback on manual step
            self._read_and_emit_frame(target_frame)
        else:
            logger.debug("Already at the last frame.")

    def previous_frame(self) -> None:
        """Moves to the previous frame, if possible. Stops playback if active."""
        if not self._is_loaded: return
        target_frame = self._current_frame_index - 1
        if target_frame >= 0:
            logger.debug("Moving to previous frame.")
            if self._is_playing: self.stop_playback() # Stop playback on manual step
            self._read_and_emit_frame(target_frame)
        else:
            logger.debug("Already at the first frame.")

    def toggle_playback(self) -> None:
        """Toggles the video playback state (play/pause)."""
        if not self._is_loaded:
            logger.warning("Cannot toggle playback: No video loaded.")
            return
        if self._fps <= 0:
             logger.warning("Cannot toggle playback: Video FPS is invalid (<= 0).")
             return

        if self._is_playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self) -> None:
        """Starts video playback using the QTimer from the current frame."""
        if not self._is_loaded:
            logger.warning("Cannot start playback: No video loaded.")
            return
        if self._is_playing:
            logger.debug("Playback already active.")
            return
        if self._fps <= 0 or not self._play_timer.interval() > 0:
             logger.warning("Cannot start playback: Invalid FPS or timer interval.")
             return

        logger.info("Starting video playback.")
        # If starting at the very last frame, wrap around to the beginning
        if self._current_frame_index >= self._total_frames - 1:
            logger.debug("Playback start requested at end of video, wrapping to beginning (frame 0).")
            # Seek to frame 0; _read_and_emit_frame updates _current_frame_index
            self._read_and_emit_frame(0)
            # If read failed for frame 0, don't start playback
            if self._current_frame_index != 0:
                 logger.error("Failed to seek to frame 0 when wrapping playback. Aborting start.")
                 return

        # Set state and start timer
        self._is_playing = True
        self._play_timer.start()
        logger.debug("Playback timer started.")
        self.playbackStateChanged.emit(True) # Notify UI

    def stop_playback(self) -> None:
        """Stops the video playback timer."""
        if not self._is_playing:
            return # Already stopped
        logger.info("Stopping video playback.")
        self._is_playing = False
        self._play_timer.stop()
        logger.debug("Playback timer stopped.")
        self.playbackStateChanged.emit(False) # Notify UI

    def get_raw_frame_at_index(self, frame_index: int) -> Optional[np.ndarray]:
        """
        Reads and returns the raw OpenCV frame (np.ndarray) at the specified index
        without updating the current playback state or emitting GUI signals.

        This is intended for operations like video export that need direct frame access.

        Args:
            frame_index: The 0-based index of the frame to retrieve.

        Returns:
            The raw video frame as a NumPy array (BGR format), or None if the frame
            cannot be read (e.g., index out of bounds, video not loaded, read error).
        """
        logger.debug(f"get_raw_frame_at_index called for frame {frame_index}.")
        return self._read_raw_frame_from_video(frame_index)

    # --- Internal Helper Methods ---

    def _read_raw_frame_from_video(self, frame_index: int) -> Optional[np.ndarray]:
        """
        Internal helper to seek to a specific frame and read it as a raw OpenCV frame.
        Does not update _current_frame_index or emit signals.

        Args:
            frame_index: 0-based index of the frame to read.

        Returns:
            The raw OpenCV frame (np.ndarray) or None if read fails or video not ready.
        """
        if not self._video_capture or not self._is_loaded:
            logger.warning(f"_read_raw_frame_from_video({frame_index}) called but video capture not ready.")
            return None
        # Ensure index is valid
        if not (0 <= frame_index < self._total_frames):
             logger.error(f"Internal error: _read_raw_frame_from_video called with invalid index {frame_index} for video with {self._total_frames} frames.")
             return None

        logger.debug(f"Reading raw frame {frame_index} via seek...")
        # Seek using OpenCV's frame property
        # It's crucial that this doesn't advance the main playback _current_frame_index
        current_capture_pos = self._video_capture.get(cv2.CAP_PROP_POS_FRAMES)
        seek_success = self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index))

        if not seek_success:
            # Log warning but attempt read anyway, might still work or be close enough
            logger.warning(f"Seek to raw frame {frame_index} using CAP_PROP_POS_FRAMES failed (might be inaccurate).")
            # Attempt to restore original position if seek failed, though this might not be perfect
            self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, float(current_capture_pos -1 if current_capture_pos > 0 else 0))


        # Read the frame after seeking
        ret: bool; frame: Optional[np.ndarray]
        ret, frame_data = self._video_capture.read()

        # After reading, try to restore the capture position to what it was before this call,
        # so that normal playback/seeking is not affected by this out-of-sequence read.
        # This is important if CAP_PROP_POS_FRAMES actually moved the main read head.
        # Subtract 1 because .read() advances the position.
        # If the original read was also a .read(), then current_capture_pos was already the *next* frame.
        # If original position was set by .set(), it might be the frame itself.
        # A robust way is to rely on the VideoHandler's own _current_frame_index for GUI playback.
        # For raw reading, we assume the user of get_raw_frame_at_index will manage their own iteration.
        # The safest approach here for a utility function is to ensure it doesn't permanently alter the state
        # used by GUI playback. So, restore the capture position to where it *would* be for the GUI's _current_frame_index.
        # However, if _video_capture.set modifies a shared read pointer, this is tricky.
        # For now, let's assume set/read for this specific function is isolated enough,
        # or that the main GUI's next seek will correctly position it.
        # A more robust solution might involve opening a separate VideoCapture instance for export,
        # but that adds complexity.
        # Given OpenCV's behavior, .set then .read is usually how one gets a specific frame.
        # The impact on subsequent .read() calls in _advance_frame needs care.
        # The _current_frame_index of the VideoHandler itself is NOT changed by this method.

        if ret and frame_data is not None:
            logger.debug(f"Successfully read raw frame {frame_index}.")
            return frame_data
        else:
            logger.warning(f"Failed to read raw frame {frame_index} after seeking (ret={ret}).")
            return None


    @QtCore.Slot()
    def _advance_frame(self) -> None:
        """
        Slot connected to the playback timer's timeout. Reads the next frame
        and emits it. Stops playback on error or end of video.
        """
        # Safety checks
        if not self._is_playing or not self._video_capture or not self._is_loaded:
            logger.warning("_advance_frame called unexpectedly. Stopping playback.")
            if self._play_timer.isActive(): self.stop_playback()
            return

        # Read the next frame directly from the capture stream
        # For playback, we rely on sequential reads which OpenCV handles efficiently.
        # We don't need to explicitly .set(CAP_PROP_POS_FRAMES) for each frame in playback.
        ret: bool; frame_data: Optional[np.ndarray]
        ret, frame_data = self._video_capture.read()

        if ret and frame_data is not None:
            # Successfully read frame. The frame read corresponds to the frame *after* _current_frame_index.
            next_frame_index = self._current_frame_index + 1

            # Check if we have gone past the last valid frame index
            if next_frame_index >= self._total_frames:
                logger.info("Playback reached end of video.")
                self.stop_playback()
                # Don't update index or emit frame if past the end; _current_frame_index remains on the last valid frame displayed.
                return

            # Update index *before* emitting the new frame
            self._current_frame_index = next_frame_index

            # Convert and emit the new frame
            q_pixmap = self._convert_cv_to_qpixmap(frame_data)
            if not q_pixmap.isNull():
                self.frameChanged.emit(q_pixmap, self._current_frame_index)
            else:
                logger.warning(f"Failed to convert frame {self._current_frame_index} during playback.")
                # Consider stopping playback if conversion fails repeatedly?
        else:
            # Failed to read frame (likely end of stream or error)
            logger.warning("Playback stopped: End of stream reached or error reading next frame during _advance_frame.")
            self.stop_playback()
            # _current_frame_index already reflects the last successfully displayed frame.

    def _read_and_emit_frame(self, frame_index: int) -> None:
        """
        Internal helper to seek to a specific frame, read it, convert it,
        update the internal state, and emit the `frameChanged` signal.
        Used for GUI updates (e.g., seeking).
        """
        frame_data = self._read_raw_frame_from_video(frame_index)

        if frame_data is not None:
            # Successfully read the frame. Update state *before* emitting.
            self._current_frame_index = frame_index # Update the main current_frame_index
            q_pixmap = self._convert_cv_to_qpixmap(frame_data)
            if not q_pixmap.isNull():
                logger.debug(f"Successfully read/converted frame {frame_index} for GUI. Emitting frameChanged.")
                self.frameChanged.emit(q_pixmap, frame_index)
            else:
                logger.warning(f"Failed to convert frame {frame_index} to QPixmap after reading for GUI.")
        else:
            # Failed to read the frame after seeking
            logger.warning(f"Failed to read frame {frame_index} for GUI in _read_and_emit_frame.")
            # Do not update _current_frame_index if read fails.

    def _convert_cv_to_qpixmap(self, cv_img: np.ndarray) -> QtGui.QPixmap:
        """
        Converts an OpenCV image (numpy array BGR, BGRA, or Grayscale) into a QPixmap.

        Args:
            cv_img: The OpenCV image (numpy ndarray).

        Returns:
            A QPixmap representation of the image, or an empty QPixmap on error.
        """
        try:
            if cv_img is None:
                logger.warning("Attempted to convert None image to QPixmap.")
                return QtGui.QPixmap()

            height, width = cv_img.shape[:2]
            channels = cv_img.shape[2] if len(cv_img.shape) == 3 else 1
            bytes_per_line: int = cv_img.strides[0] # Get stride from numpy array
            q_img: Optional[QtGui.QImage] = None

            # Create QImage based on number of channels
            if channels == 1: # Grayscale
                img_format = QtGui.QImage.Format.Format_Grayscale8
                cv_img_copy = np.require(cv_img, np.uint8, 'C') # Ensure C-contiguous uint8
                q_img = QtGui.QImage(cv_img_copy.data, width, height, bytes_per_line, img_format)
            elif channels == 3: # BGR (OpenCV default)
                img_format = QtGui.QImage.Format.Format_RGB888
                rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB) # Convert BGR to RGB
                rgb_img_copy = np.require(rgb_img, np.uint8, 'C')
                q_img = QtGui.QImage(rgb_img_copy.data, width, height, bytes_per_line, img_format)
            elif channels == 4: # BGRA
                img_format = QtGui.QImage.Format.Format_RGBA8888
                rgba_img = cv2.cvtColor(cv_img, cv2.COLOR_BGRA2RGBA) # Convert BGRA to RGBA
                rgba_img_copy = np.require(rgba_img, np.uint8, 'C')
                q_img = QtGui.QImage(rgba_img_copy.data, width, height, bytes_per_line, img_format)
            else:
                logger.error(f"Unsupported number of image channels ({channels}) for conversion.")
                return QtGui.QPixmap()

            if q_img is None or q_img.isNull():
                logger.error("QImage creation failed during conversion.")
                return QtGui.QPixmap()

            # Create QPixmap from QImage. Use .copy() to ensure QPixmap owns the data.
            return QtGui.QPixmap.fromImage(q_img.copy())

        except cv2.error as e:
            logger.error(f"OpenCV error during image conversion: {e}", exc_info=False) # Less verbose traceback for cv errors
            return QtGui.QPixmap()
        except Exception as e:
            # Catch any other unexpected errors during conversion
            logger.exception(f"Unexpected error converting OpenCV frame to QPixmap: {e}")
            return QtGui.QPixmap()

    # --- Properties ---
    # Provide read-only access to key state variables via properties

    @property
    def is_loaded(self) -> bool:
        """Returns True if a video is currently loaded, False otherwise."""
        return self._is_loaded

    @property
    def current_frame_index(self) -> int:
        """Returns the index (0-based) of the currently displayed frame."""
        return self._current_frame_index

    @property
    def total_frames(self) -> int:
        """Returns the total number of frames in the loaded video."""
        return self._total_frames

    @property
    def fps(self) -> float:
        """Returns the frames per second (FPS) of the loaded video."""
        return self._fps

    @property
    def frame_width(self) -> int:
        """Returns the width of the video frames in pixels."""
        return self._frame_width

    @property
    def frame_height(self) -> int:
        """Returns the height of the video frames in pixels."""
        return self._frame_height