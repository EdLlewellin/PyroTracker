# video_handler.py
"""
Manages video loading, playback, navigation, and frame extraction
for the PyroTracker application using OpenCV and QTimer.
"""
import cv2 # type: ignore
import numpy as np
import logging
import os
import re # Added for time parsing
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
        logger.info(f"Attempting to open video: {filepath}")
        self.release_video() 

        try:
            cap = cv2.VideoCapture(filepath)
            if not cap or not cap.isOpened():
                raise IOError(f"Cannot open video file via OpenCV: {filepath}")

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.debug(f"Raw video properties: Frames={total_frames}, FPS={fps}, Size={frame_width}x{frame_height}")

            if total_frames <= 0 or frame_width <= 0 or frame_height <= 0:
                cap.release() 
                raise ValueError("Video file reports invalid dimensions or zero/negative frames.")

            if fps <= 0:
                logger.warning(f"Video FPS reported as {fps}. Using fallback FPS=30 for calculations.")
                fps = 30.0 

            self._video_capture = cap
            self._video_filepath = filepath
            self._total_frames = total_frames
            self._fps = fps
            self._frame_width = frame_width
            self._frame_height = frame_height
            self._total_duration_ms = (self._total_frames / self._fps) * 1000 if self._fps > 0 else 0.0
            self._is_loaded = True
            self._current_frame_index = -1 

            if self._fps > 0:
                timer_interval: int = int(1000 / self._fps) 
                self._play_timer.setInterval(max(1, timer_interval)) 
                logger.debug(f"Playback timer interval set to {self._play_timer.interval()} ms.")
            else:
                logger.warning("Cannot set playback timer interval due to invalid FPS.")

            video_info = self.get_video_info()
            logger.info(f"Video loaded successfully: '{os.path.basename(filepath)}'. Emitting videoLoaded.")
            self.videoLoaded.emit(video_info) 

            self._read_and_emit_frame(0)
            return True

        except (IOError, ValueError, cv2.error, Exception) as e:
            error_msg = f"Error opening video '{os.path.basename(filepath)}': {str(e)}"
            logger.error(error_msg, exc_info=True) 
            self.release_video() 
            self.videoLoadFailed.emit(error_msg) 
            return False

    def release_video(self) -> None:
        logger.info("Releasing video resources...")
        self.stop_playback() 
        if self._video_capture:
            try:
                self._video_capture.release()
                logger.debug("cv2.VideoCapture released.")
            except Exception as e:
                logger.error(f"Exception during cv2.VideoCapture release: {e}", exc_info=True)
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
        if not self._is_loaded:
            logger.warning("get_video_info called but no video is loaded.")
            return {}
        return {
            "filepath": self._video_filepath,
            "filename": os.path.basename(self._video_filepath),
            "total_frames": self._total_frames,
            "fps": self._fps,
            "width": self._frame_width,
            "height": self._frame_height,
            "duration_ms": self._total_duration_ms,
            "current_frame": self._current_frame_index, 
            "is_loaded": self._is_loaded,
        }

    def get_metadata_dictionary(self) -> Dict[str, Any]:
        if not self._is_loaded or not self._video_capture:
            logger.warning("get_metadata_dictionary called but no video loaded.")
            return {}
        logger.debug("Retrieving metadata dictionary...")
        metadata = {}
        metadata["File Path"] = self._video_filepath
        metadata["Duration (ms)"] = f"{self._total_duration_ms:.2f}" if self._total_duration_ms >= 0 else "N/A"
        metadata["Total Frames"] = self._total_frames
        metadata["Frame Width"] = self._frame_width
        metadata["Frame Height"] = self._frame_height
        metadata["FPS"] = f"{self._fps:.3f}" if self._fps > 0 else "N/A"
        try:
            fourcc_int = int(self._video_capture.get(cv2.CAP_PROP_FOURCC))
            if fourcc_int != 0:
                fourcc_code = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])
                fourcc_code = "".join(filter(str.isprintable, fourcc_code)).strip() 
                metadata["FourCC Codec"] = fourcc_code if fourcc_code else "N/A"
            else:
                 metadata["FourCC Codec"] = "N/A"
            bitrate = self._video_capture.get(cv2.CAP_PROP_BITRATE)
            metadata["Bitrate (bps)"] = f"{int(bitrate)}" if bitrate > 0 else "N/A"
        except Exception as e:
            logger.error(f"Error retrieving specific OpenCV properties: {e}", exc_info=False)
            if "FourCC Codec" not in metadata: metadata["FourCC Codec"] = "Error"
            if "Bitrate (bps)" not in metadata: metadata["Bitrate (bps)"] = "Error"
        logger.debug(f"Generated metadata dictionary: {metadata}")
        return metadata

    def seek_frame(self, frame_index: int) -> None:
        if not self._is_loaded:
            logger.warning("seek_frame called but no video loaded.")
            return
        clamped_index = max(0, min(frame_index, self._total_frames - 1))
        if clamped_index != frame_index:
            logger.warning(f"seek_frame: Index {frame_index} out of bounds [0, {self._total_frames-1}]. Clamping to {clamped_index}.")
            frame_index = clamped_index
        if self._is_playing:
            self.stop_playback()
        if frame_index != self._current_frame_index:
            logger.debug(f"Seeking to frame {frame_index}")
            self._read_and_emit_frame(frame_index)
        else:
            logger.debug(f"Seek requested to current frame ({frame_index}), no operation needed.")

    def next_frame(self) -> None:
        if not self._is_loaded: return
        target_frame = self._current_frame_index + 1
        if target_frame < self._total_frames:
            logger.debug("Moving to next frame.")
            if self._is_playing: self.stop_playback() 
            self._read_and_emit_frame(target_frame)
        else:
            logger.debug("Already at the last frame.")

    def previous_frame(self) -> None:
        if not self._is_loaded: return
        target_frame = self._current_frame_index - 1
        if target_frame >= 0:
            logger.debug("Moving to previous frame.")
            if self._is_playing: self.stop_playback() 
            self._read_and_emit_frame(target_frame)
        else:
            logger.debug("Already at the first frame.")

    def toggle_playback(self) -> None:
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
        if self._current_frame_index >= self._total_frames - 1:
            logger.debug("Playback start requested at end of video, wrapping to beginning (frame 0).")
            self._read_and_emit_frame(0)
            if self._current_frame_index != 0:
                 logger.error("Failed to seek to frame 0 when wrapping playback. Aborting start.")
                 return
        self._is_playing = True
        self._play_timer.start()
        logger.debug("Playback timer started.")
        self.playbackStateChanged.emit(True) 

    def stop_playback(self) -> None:
        if not self._is_playing:
            return 
        logger.info("Stopping video playback.")
        self._is_playing = False
        self._play_timer.stop()
        logger.debug("Playback timer stopped.")
        self.playbackStateChanged.emit(False) 

    def get_raw_frame_at_index(self, frame_index: int) -> Optional[np.ndarray]:
        logger.debug(f"get_raw_frame_at_index called for frame {frame_index}.")
        return self._read_raw_frame_from_video(frame_index)

    # --- NEW Helper Method: Parse time string to milliseconds ---
    def parse_time_to_ms(self, time_str: str) -> Optional[float]:
        """
        Parses a time string (e.g., "MM:SS.mmm", "SS.mmm", "S.m") into milliseconds.

        Args:
            time_str: The time string to parse.

        Returns:
            The time in milliseconds as a float, or None if parsing fails.
        """
        if not self._is_loaded:
            logger.warning("Cannot parse time string: No video loaded.")
            return None

        time_str = time_str.strip()
        total_ms: Optional[float] = None

        # Try MM:SS.mmm format
        match_mm_ss_mmm = re.fullmatch(r"(\d+):([0-5]?\d)\.?(\d{1,3})?", time_str)
        if match_mm_ss_mmm:
            try:
                minutes = int(match_mm_ss_mmm.group(1))
                seconds = int(match_mm_ss_mmm.group(2))
                milliseconds_str = match_mm_ss_mmm.group(3)
                milliseconds = 0
                if milliseconds_str:
                    if len(milliseconds_str) == 1: milliseconds = int(milliseconds_str) * 100
                    elif len(milliseconds_str) == 2: milliseconds = int(milliseconds_str) * 10
                    else: milliseconds = int(milliseconds_str)
                
                if 0 <= seconds < 60 and 0 <= milliseconds < 1000:
                    total_ms = (minutes * 60 + seconds) * 1000 + milliseconds
            except ValueError:
                logger.debug(f"Could not parse MM:SS.mmm from '{time_str}' due to ValueError.")
                total_ms = None # Ensure it's reset if parsing part fails

        # Try SS.mmm or S.m format if MM:SS.mmm failed or wasn't matched
        if total_ms is None:
            match_ss_mmm = re.fullmatch(r"(\d+)\.?(\d{1,3})?", time_str)
            if match_ss_mmm:
                try:
                    seconds_part = int(match_ss_mmm.group(1))
                    milliseconds_str = match_ss_mmm.group(2)
                    milliseconds = 0
                    if milliseconds_str:
                        if len(milliseconds_str) == 1: milliseconds = int(milliseconds_str) * 100
                        elif len(milliseconds_str) == 2: milliseconds = int(milliseconds_str) * 10
                        else: milliseconds = int(milliseconds_str)
                    
                    if 0 <= milliseconds < 1000 : # Seconds part can be large
                         total_ms = seconds_part * 1000 + milliseconds
                except ValueError:
                    logger.debug(f"Could not parse SS.mmm from '{time_str}' due to ValueError.")
                    total_ms = None # Ensure it's reset
        
        if total_ms is not None:
            if 0 <= total_ms <= self._total_duration_ms:
                return total_ms
            else:
                logger.warning(f"Parsed time {total_ms}ms is outside video duration [0, {self._total_duration_ms}ms].")
                return None # Out of bounds
        
        logger.warning(f"Failed to parse time string: '{time_str}'")
        return None

    # --- NEW Helper Method: Convert time (ms) to nearest frame index ---
    def time_ms_to_frame_index(self, time_ms: float) -> Optional[int]:
        """
        Converts a time in milliseconds to the nearest valid frame index.

        Args:
            time_ms: The time in milliseconds.

        Returns:
            The nearest 0-based frame index, or None if video not loaded or FPS is invalid.
        """
        if not self._is_loaded or self._fps <= 0:
            logger.warning("Cannot convert time to frame: Video not loaded or invalid FPS.")
            return None

        if not (0 <= time_ms <= self._total_duration_ms):
            logger.warning(f"Time {time_ms}ms is outside video duration. Cannot convert to frame index.")
            return None

        frame_float = (time_ms / 1000.0) * self._fps
        frame_index = round(frame_float) # Find nearest frame

        # Clamp to valid frame range [0, total_frames - 1]
        clamped_frame_index = max(0, min(int(frame_index), self._total_frames - 1))
        
        logger.debug(f"Converted {time_ms:.3f}ms to frame_float={frame_float:.3f}, rounded_index={frame_index}, clamped_index={clamped_frame_index}")
        return clamped_frame_index

    # --- Internal Helper Methods ---
    def _read_raw_frame_from_video(self, frame_index: int) -> Optional[np.ndarray]:
        if not self._video_capture or not self._is_loaded:
            logger.warning(f"_read_raw_frame_from_video({frame_index}) called but video capture not ready.")
            return None
        if not (0 <= frame_index < self._total_frames):
             logger.error(f"Internal error: _read_raw_frame_from_video called with invalid index {frame_index} for video with {self._total_frames} frames.")
             return None
        logger.debug(f"Reading raw frame {frame_index} via seek...")
        current_capture_pos = self._video_capture.get(cv2.CAP_PROP_POS_FRAMES)
        seek_success = self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index))
        if not seek_success:
            logger.warning(f"Seek to raw frame {frame_index} using CAP_PROP_POS_FRAMES failed (might be inaccurate).")
            self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, float(current_capture_pos -1 if current_capture_pos > 0 else 0))
        ret: bool; frame_data: Optional[np.ndarray]
        ret, frame_data = self._video_capture.read()
        if ret and frame_data is not None:
            logger.debug(f"Successfully read raw frame {frame_index}.")
            return frame_data
        else:
            logger.warning(f"Failed to read raw frame {frame_index} after seeking (ret={ret}).")
            return None

    @QtCore.Slot()
    def _advance_frame(self) -> None:
        if not self._is_playing or not self._video_capture or not self._is_loaded:
            logger.warning("_advance_frame called unexpectedly. Stopping playback.")
            if self._play_timer.isActive(): self.stop_playback()
            return
        ret: bool; frame_data: Optional[np.ndarray]
        ret, frame_data = self._video_capture.read()
        if ret and frame_data is not None:
            next_frame_index = self._current_frame_index + 1
            if next_frame_index >= self._total_frames:
                logger.info("Playback reached end of video.")
                self.stop_playback()
                return
            self._current_frame_index = next_frame_index
            q_pixmap = self._convert_cv_to_qpixmap(frame_data)
            if not q_pixmap.isNull():
                self.frameChanged.emit(q_pixmap, self._current_frame_index)
            else:
                logger.warning(f"Failed to convert frame {self._current_frame_index} during playback.")
        else:
            logger.warning("Playback stopped: End of stream reached or error reading next frame during _advance_frame.")
            self.stop_playback()

    def _read_and_emit_frame(self, frame_index: int) -> None:
        frame_data = self._read_raw_frame_from_video(frame_index)
        if frame_data is not None:
            self._current_frame_index = frame_index 
            q_pixmap = self._convert_cv_to_qpixmap(frame_data)
            if not q_pixmap.isNull():
                logger.debug(f"Successfully read/converted frame {frame_index} for GUI. Emitting frameChanged.")
                self.frameChanged.emit(q_pixmap, frame_index)
            else:
                logger.warning(f"Failed to convert frame {frame_index} to QPixmap after reading for GUI.")
        else:
            logger.warning(f"Failed to read frame {frame_index} for GUI in _read_and_emit_frame.")

    def _convert_cv_to_qpixmap(self, cv_img: np.ndarray) -> QtGui.QPixmap:
        try:
            if cv_img is None:
                logger.warning("Attempted to convert None image to QPixmap.")
                return QtGui.QPixmap()
            height, width = cv_img.shape[:2]
            channels = cv_img.shape[2] if len(cv_img.shape) == 3 else 1
            bytes_per_line: int = cv_img.strides[0] 
            q_img: Optional[QtGui.QImage] = None
            if channels == 1: 
                img_format = QtGui.QImage.Format.Format_Grayscale8
                cv_img_copy = np.require(cv_img, np.uint8, 'C') 
                q_img = QtGui.QImage(cv_img_copy.data, width, height, bytes_per_line, img_format)
            elif channels == 3: 
                img_format = QtGui.QImage.Format.Format_RGB888
                rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB) 
                rgb_img_copy = np.require(rgb_img, np.uint8, 'C')
                q_img = QtGui.QImage(rgb_img_copy.data, width, height, bytes_per_line, img_format)
            elif channels == 4: 
                img_format = QtGui.QImage.Format.Format_RGBA8888
                rgba_img = cv2.cvtColor(cv_img, cv2.COLOR_BGRA2RGBA) 
                rgba_img_copy = np.require(rgba_img, np.uint8, 'C')
                q_img = QtGui.QImage(rgba_img_copy.data, width, height, bytes_per_line, img_format)
            else:
                logger.error(f"Unsupported number of image channels ({channels}) for conversion.")
                return QtGui.QPixmap()
            if q_img is None or q_img.isNull():
                logger.error("QImage creation failed during conversion.")
                return QtGui.QPixmap()
            return QtGui.QPixmap.fromImage(q_img.copy())
        except cv2.error as e:
            logger.error(f"OpenCV error during image conversion: {e}", exc_info=False) 
            return QtGui.QPixmap()
        except Exception as e:
            logger.exception(f"Unexpected error converting OpenCV frame to QPixmap: {e}")
            return QtGui.QPixmap()

    # --- Properties ---
    @property
    def is_loaded(self) -> bool:
        return self._is_loaded
    @property
    def current_frame_index(self) -> int:
        return self._current_frame_index
    @property
    def total_frames(self) -> int:
        return self._total_frames
    @property
    def fps(self) -> float:
        return self._fps
    @property
    def frame_width(self) -> int:
        return self._frame_width
    @property
    def frame_height(self) -> int:
        return self._frame_height
    @property
    def total_duration_ms(self) -> float:
        return self._total_duration_ms