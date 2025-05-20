# info_overlay_widget.py
"""
Custom QWidget for displaying informational text overlays (filename, time, frame number)
on the InteractiveImageView.
"""
import logging
from typing import Optional, Dict, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

import settings_manager # To get appearance settings

logger = logging.getLogger(__name__)

# Define keys for the different text elements this widget will manage
ELEMENT_FILENAME = "filename"
ELEMENT_TIME = "time"
ELEMENT_FRAME_NUMBER = "frame_number"

class InfoOverlayWidget(QtWidgets.QWidget):
    """
    A widget that draws informational text overlays (filename, time, frame number)
    fixed to the viewport corners.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        # Make the widget transparent for mouse events, so clicks pass through to the view
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setVisible(False) # Initially hidden, shown when video loads

        # Internal state for the data to display
        self._filename: str = ""
        self._current_time_ms: float = 0.0
        self._total_time_ms: float = 0.0
        self._current_frame_idx: int = -1
        self._total_frames: int = 0

        # Internal state for appearance - these will be loaded from settings_manager
        self._visibility: Dict[str, bool] = {
            ELEMENT_FILENAME: True,
            ELEMENT_TIME: True,
            ELEMENT_FRAME_NUMBER: True,
        }
        self._colors: Dict[str, QtGui.QColor] = {
            ELEMENT_FILENAME: QtGui.QColor("white"),
            ELEMENT_TIME: QtGui.QColor("white"),
            ELEMENT_FRAME_NUMBER: QtGui.QColor("white"),
        }
        self._font_sizes: Dict[str, int] = {
            ELEMENT_FILENAME: 10,
            ELEMENT_TIME: 10,
            ELEMENT_FRAME_NUMBER: 10,
        }
        self._fonts: Dict[str, QtGui.QFont] = {} # Cache for QFont objects

        self.update_appearance_from_settings() # Load initial appearance
        logger.debug("InfoOverlayWidget initialized.")

    def _format_time_display(self, current_ms: float, total_ms: float) -> str:
        """Formats time for display (current / total)."""
        def _ms_to_str(ms: float) -> str:
            if ms < 0: return "--:--.---"
            try:
                s, mils = divmod(ms, 1000)
                m, s_rem = divmod(int(s), 60)
                return f"{m:02d}:{s_rem:02d}.{int(mils):03d}"
            except Exception:
                return "--:--.---"
        return f"Time: {_ms_to_str(current_ms)} / {_ms_to_str(total_ms)}"

    def _format_frame_display(self, current_idx: int, total_count: int) -> str:
        """Formats frame number for display (current / total)."""
        cur = str(current_idx + 1) if current_idx >= 0 else "-"
        tot = str(total_count) if total_count > 0 else "-"
        return f"Frame: {cur} / {tot}"

    # --- Public methods to update data ---
    def update_video_info(self, filename: str, total_frames: int, total_duration_ms: float) -> None:
        """Sets static video information like filename and totals."""
        self._filename = filename
        self._total_frames = total_frames
        self._total_time_ms = total_duration_ms
        if self.isVisible():
            self.update() # Trigger repaint
        logger.debug(f"InfoOverlayWidget: Video info updated - File: {filename}, Frames: {total_frames}, Duration: {total_duration_ms}ms")

    def update_current_frame_time(self, frame_idx: int, time_ms: float) -> None:
        """Updates the current frame index and time."""
        self._current_frame_idx = frame_idx
        self._current_time_ms = time_ms
        if self.isVisible():
            self.update() # Trigger repaint

    # --- Public methods to update appearance ---
    def update_appearance_from_settings(self) -> None:
        """Loads visibility, colors, and font sizes from SettingsManager and updates fonts."""
        logger.debug("InfoOverlayWidget: Updating appearance from settings.")
        # Visibility
        self._visibility[ELEMENT_FILENAME] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_FILENAME)
        self._visibility[ELEMENT_TIME] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_TIME)
        self._visibility[ELEMENT_FRAME_NUMBER] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER)

        # Colors
        self._colors[ELEMENT_FILENAME] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_FILENAME_COLOR)
        self._colors[ELEMENT_TIME] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_TIME_COLOR)
        self._colors[ELEMENT_FRAME_NUMBER] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_FRAME_NUMBER_COLOR)

        # Font Sizes
        self._font_sizes[ELEMENT_FILENAME] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_FILENAME_FONT_SIZE)
        self._font_sizes[ELEMENT_TIME] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_TIME_FONT_SIZE)
        self._font_sizes[ELEMENT_FRAME_NUMBER] = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_FRAME_NUMBER_FONT_SIZE)

        # Update QFont objects
        for key in [ELEMENT_FILENAME, ELEMENT_TIME, ELEMENT_FRAME_NUMBER]:
            font = QtGui.QFont() # Start with a default font
            font.setPointSize(self._font_sizes[key])
            self._fonts[key] = font

        if self.isVisible():
            self.update() # Trigger repaint if visible

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paints the visible text overlays."""
        if not self.isVisible():
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)

        widget_rect = self.rect() # The viewport area this widget covers
        margin = 5 # Small margin from the edges

        # 1. Filename (Top-Left)
        if self._visibility[ELEMENT_FILENAME] and self._filename:
            painter.setFont(self._fonts[ELEMENT_FILENAME])
            painter.setPen(self._colors[ELEMENT_FILENAME])
            # For multiline filenames, use boundingRect to get needed height
            fm = QtGui.QFontMetrics(self._fonts[ELEMENT_FILENAME])
            text_option = QtGui.QTextOption(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
            text_option.setWrapMode(QtGui.QTextOption.WrapMode.NoWrap) # Or WordWrap if preferred

            # Simple elide for very long filenames if they overflow significantly
            elided_filename = fm.elidedText(self._filename, QtCore.Qt.TextElideMode.ElideRight, widget_rect.width() - 2 * margin)

            filename_rect = QtCore.QRectF(
                widget_rect.left() + margin,
                widget_rect.top() + margin,
                widget_rect.width() - 2 * margin, # Max width
                fm.height() + 2  # Height for one line
            )
            painter.drawText(filename_rect, elided_filename, text_option)


        # Prepare text for Time and Frame Number
        time_str = self._format_time_display(self._current_time_ms, self._total_time_ms)
        frame_str = self._format_frame_display(self._current_frame_idx, self._total_frames)

        # 2. Time (Bottom-Left)
        if self._visibility[ELEMENT_TIME]:
            painter.setFont(self._fonts[ELEMENT_TIME])
            painter.setPen(self._colors[ELEMENT_TIME])
            fm_time = QtGui.QFontMetrics(self._fonts[ELEMENT_TIME])
            time_text_height = fm_time.height()
            time_pos_x = widget_rect.left() + margin
            time_pos_y = widget_rect.bottom() - margin # Baseline for text
            painter.drawText(QtCore.QPointF(time_pos_x, time_pos_y), time_str)

        # 3. Frame Number (Bottom-Left, below or next to Time)
        # For simplicity, let's place Frame Number below Time if both are visible.
        # If only Frame is visible, it takes Time's spot.
        if self._visibility[ELEMENT_FRAME_NUMBER]:
            painter.setFont(self._fonts[ELEMENT_FRAME_NUMBER])
            painter.setPen(self._colors[ELEMENT_FRAME_NUMBER])
            fm_frame = QtGui.QFontMetrics(self._fonts[ELEMENT_FRAME_NUMBER])
            frame_text_height = fm_frame.height()
            frame_pos_x = widget_rect.left() + margin
            frame_pos_y = widget_rect.bottom() - margin

            if self._visibility[ELEMENT_TIME]: # If time is also visible, draw frame below it
                fm_time_height = QtGui.QFontMetrics(self._fonts[ELEMENT_TIME]).height()
                frame_pos_y = widget_rect.bottom() - margin - fm_time_height - (margin / 2) # Position below time

            painter.drawText(QtCore.QPointF(frame_pos_x, frame_pos_y), frame_str)

        painter.end()

    # --- Convenience for ExportHandler (Optional) ---
    def render_to_painter(self, painter: QtGui.QPainter, target_rect: QtCore.QRectF) -> None:
        """
        Renders the currently configured and visible overlays onto an external QPainter
        within the specified target_rect (which represents the export canvas).
        This method mirrors the logic of paintEvent but for an external painter.
        """
        if not self.isVisible(): # Check overall widget visibility first (though may not be used by export)
            # For export, we rely on individual element visibility from settings.
            pass

        original_font = painter.font()
        original_pen = painter.pen()

        margin = 5 # Consistent margin

        # 1. Filename (Top-Left)
        if self._visibility[ELEMENT_FILENAME] and self._filename:
            painter.setFont(self._fonts[ELEMENT_FILENAME])
            painter.setPen(self._colors[ELEMENT_FILENAME])
            fm = QtGui.QFontMetrics(self._fonts[ELEMENT_FILENAME])
            elided_filename = fm.elidedText(self._filename, QtCore.Qt.TextElideMode.ElideRight, target_rect.width() - 2 * margin)
            filename_rect = QtCore.QRectF(
                target_rect.left() + margin,
                target_rect.top() + margin,
                target_rect.width() - 2 * margin,
                fm.height() + 2
            )
            painter.drawText(filename_rect, elided_filename, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)

        time_str = self._format_time_display(self._current_time_ms, self._total_time_ms)
        frame_str = self._format_frame_display(self._current_frame_idx, self._total_frames)

        # 2. Time (Bottom-Left)
        if self._visibility[ELEMENT_TIME]:
            painter.setFont(self._fonts[ELEMENT_TIME])
            painter.setPen(self._colors[ELEMENT_TIME])
            fm_time = QtGui.QFontMetrics(self._fonts[ELEMENT_TIME])
            time_pos_x = target_rect.left() + margin
            time_pos_y = target_rect.bottom() - margin # Baseline for text
            painter.drawText(QtCore.QPointF(time_pos_x, time_pos_y), time_str)

        # 3. Frame Number (Bottom-Left, below or next to Time)
        if self._visibility[ELEMENT_FRAME_NUMBER]:
            painter.setFont(self._fonts[ELEMENT_FRAME_NUMBER])
            painter.setPen(self._colors[ELEMENT_FRAME_NUMBER])
            fm_frame = QtGui.QFontMetrics(self._fonts[ELEMENT_FRAME_NUMBER])
            frame_pos_x = target_rect.left() + margin
            frame_pos_y = target_rect.bottom() - margin

            if self._visibility[ELEMENT_TIME]:
                fm_time_height = QtGui.QFontMetrics(self._fonts[ELEMENT_TIME]).height()
                frame_pos_y = target_rect.bottom() - margin - fm_time_height - (margin / 2)
            painter.drawText(QtCore.QPointF(frame_pos_x, frame_pos_y), frame_str)

        # Restore painter's original state if needed, though for export it might be managed externally.
        painter.setFont(original_font)
        painter.setPen(original_pen)