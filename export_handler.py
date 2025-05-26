# export_handler.py
"""
Handles video and image sequence exporting with overlays for PyroTracker.
"""
import logging
import os
import math
from enum import Enum, auto # Added Enum
from typing import Optional, TYPE_CHECKING, Tuple, List, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets
import cv2 # type: ignore
import numpy as np

import config
import settings_manager # For accessing visual settings
import graphics_utils

# Conditional imports for type checking to avoid circular dependencies
if TYPE_CHECKING:
    from main_window import MainWindow # For QProgressDialog parent and style access
    from video_handler import VideoHandler
    from element_manager import ElementManager
    from scale_manager import ScaleManager
    from coordinate_transformer import CoordinateTransformer
    from interactive_image_view import InteractiveImageView
    from scale_bar_widget import ScaleBarWidget


logger = logging.getLogger(__name__)

# --- NEW: Enum for Export Resolution Mode ---
class ExportResolutionMode(Enum):
    """Defines the resolution modes for exporting frames/videos."""
    VIEWPORT = auto()       # Export at the current viewport resolution and aspect ratio
    ORIGINAL_VIDEO = auto() # Export at the original video resolution and aspect ratio

class ExportHandler(QtCore.QObject):
    """
    Manages the logic for exporting video frames with overlays, either as
    a new video file or as individual image files.
    """

    exportStarted = QtCore.Signal()
    exportProgress = QtCore.Signal(str, int, int) # message, current_value, max_value
    exportFinished = QtCore.Signal(bool, str) # success (bool), message (str)

    _main_window: Optional['MainWindow']
    _video_handler: 'VideoHandler'
    _element_manager: 'ElementManager'
    _scale_manager: 'ScaleManager'
    _coord_transformer: 'CoordinateTransformer'
    _image_view: 'InteractiveImageView'

    def __init__(self,
                 video_handler: 'VideoHandler',
                 element_manager: 'ElementManager',
                 scale_manager: 'ScaleManager',
                 coord_transformer: 'CoordinateTransformer',
                 image_view: 'InteractiveImageView',
                 main_window: Optional['MainWindow'] = None,
                 parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._video_handler = video_handler
        self._element_manager = element_manager
        self._scale_manager = scale_manager
        self._coord_transformer = coord_transformer
        self._image_view = image_view
        self._main_window = main_window
        logger.debug("ExportHandler initialized.")

    def format_length_value_for_line(self, length_meters: float) -> str:
        if length_meters == 0:
            return "0 m"
        if abs(length_meters) >= config.SCIENTIFIC_NOTATION_UPPER_THRESHOLD or \
           (abs(length_meters) > 0 and abs(length_meters) <= config.SCIENTIFIC_NOTATION_LOWER_THRESHOLD):
            return f"{length_meters:.2e}"
        for factor, singular_abbr, plural_abbr_or_none in config.UNIT_PREFIXES:
            if abs(length_meters) >= factor * 0.99:
                value_in_unit = length_meters / factor
                if factor >= 1.0:
                    precision = 2 if abs(value_in_unit) < 10 else 1 if abs(value_in_unit) < 100 else 0
                elif factor >= 1e-3:
                    precision = 1 if abs(value_in_unit) < 100 else 0
                else:
                    precision = 0
                if precision > 0 and value_in_unit == math.floor(value_in_unit):
                    if abs(value_in_unit) >= 10 : precision = 0
                formatted_value = f"{value_in_unit:.{precision}f}"
                unit_to_display = plural_abbr_or_none if plural_abbr_or_none and abs(float(formatted_value)) != 1.0 else singular_abbr
                return f"{formatted_value} {unit_to_display}"
        return f"{length_meters:.3f} m"


    def _render_overlays_on_painter(self,
                                   painter: QtGui.QPainter,
                                   current_frame_index: int, # This is the original video frame index
                                   export_qimage_rect: QtCore.QRectF, # The target QImage's full rectangle
                                   visible_scene_rect: QtCore.QRectF, # The portion of the scene visible in the export view
                                   export_mode: ExportResolutionMode
                                   ) -> None:
        if not self._element_manager or not self._coord_transformer or \
           not self._scale_manager or not self._image_view or \
           not self._main_window or not self._video_handler:
            logger.error("Overlay rendering skipped: one or more required managers/views are missing.")
            return

        # Save painter state to restore after drawing scene-based overlays
        painter.save()

        # Set up painter for scene-based overlays (tracks, origin, defined scale line)
        if not visible_scene_rect.isEmpty():
            painter.setWindow(visible_scene_rect.toRect())
            painter.setViewport(export_qimage_rect.toRect())
        else:
            logger.warning("Visible scene rect is empty for export. Overlay scaling might be incorrect.")
            painter.setWindow(export_qimage_rect.toRect())
            painter.setViewport(export_qimage_rect.toRect())

        marker_sz = float(settings_manager.get_setting(settings_manager.KEY_MARKER_SIZE))
        track_elements = self._element_manager.get_visual_elements(current_frame_index, self._scale_manager)
        pens = {
            config.STYLE_MARKER_ACTIVE_CURRENT: self._main_window.pen_marker_active_current,
            config.STYLE_MARKER_ACTIVE_OTHER: self._main_window.pen_marker_active_other,
            config.STYLE_MARKER_INACTIVE_CURRENT: self._main_window.pen_marker_inactive_current,
            config.STYLE_MARKER_INACTIVE_OTHER: self._main_window.pen_marker_inactive_other,
            config.STYLE_LINE_ACTIVE: self._main_window.pen_line_active,
            config.STYLE_LINE_INACTIVE: self._main_window.pen_line_inactive,
            config.STYLE_MEASUREMENT_LINE_NORMAL: self._main_window.pen_measurement_line_normal,
            config.STYLE_MEASUREMENT_LINE_ACTIVE: self._main_window.pen_measurement_line_active,
        }
        for el in track_elements:
            el_type = el.get('type')
            style_key = el.get('style')
            pen_to_use = pens.get(style_key)

            if el_type == 'marker' and el.get('pos'):
                if not pen_to_use:
                    logger.warning(f"ExportHandler: No pen for marker style '{style_key}'. Skipping.")
                    continue
                x, y = el['pos']
                graphics_utils.draw_marker_on_painter(painter, QtCore.QPointF(x,y), marker_sz, pen_to_use)
            elif el_type == 'line' and el.get('p1') and el.get('p2'):
                if not pen_to_use:
                    logger.warning(f"ExportHandler: No pen for line style '{style_key}'. Skipping.")
                    continue
                p1_coords, p2_coords = el['p1'], el['p2']
                graphics_utils.draw_line_on_painter(painter, QtCore.QPointF(p1_coords[0], p1_coords[1]), QtCore.QPointF(p2_coords[0], p2_coords[1]), pen_to_use)
            elif el_type == 'text' and el.get('label_type') == 'measurement_line_length':
                text_string = el.get('text')
                line_p1_coords_tuple = el.get('line_p1')
                line_p2_coords_tuple = el.get('line_p2')
                font_size_pt = el.get('font_size')
                q_color = el.get('color')

                if not all([text_string, line_p1_coords_tuple, line_p2_coords_tuple,
                            isinstance(font_size_pt, int), isinstance(q_color, QtGui.QColor)]):
                    logger.warning(f"ExportHandler: Incomplete data for measurement line text label ID {el.get('element_id')}. Skipping.")
                    continue
                
                p1_scene = QtCore.QPointF(line_p1_coords_tuple[0], line_p1_coords_tuple[1])
                p2_scene = QtCore.QPointF(line_p2_coords_tuple[0], line_p2_coords_tuple[1])

                current_export_font = QtGui.QFont()
                current_export_font.setPointSize(font_size_pt)
                font_metrics = QtGui.QFontMetrics(current_export_font)
                text_bounding_rect_local = font_metrics.boundingRect(text_string)
                
                text_pos_scene, text_rot_deg = graphics_utils.calculate_line_label_transform(
                    p1_scene,
                    p2_scene,
                    text_bounding_rect_local,
                    visible_scene_rect 
                )

                painter.save()
                try:
                    painter.translate(text_pos_scene.x() + text_bounding_rect_local.width() / 2.0,
                                      text_pos_scene.y() + text_bounding_rect_local.height() / 2.0)
                    painter.rotate(text_rot_deg)
                    
                    painter.setFont(current_export_font)
                    painter.setPen(q_color)
                    
                    painter.drawText(QtCore.QPointF(-text_bounding_rect_local.width() / 2.0,
                                                     -text_bounding_rect_local.height() / 2.0 + font_metrics.ascent()),
                                     text_string)
                finally:
                    painter.restore()

        if self._main_window.coord_panel_controller and self._main_window.coord_panel_controller.get_show_origin_marker_status():
            origin_sz = float(settings_manager.get_setting(settings_manager.KEY_ORIGIN_MARKER_SIZE))
            ox, oy = self._coord_transformer.get_current_origin_tl()
            r_orig = origin_sz / 2.0
            origin_pen = QtGui.QPen(self._main_window.pen_origin_marker) 
            origin_pen.setCosmetic(True)
            painter.setPen(origin_pen)
            painter.setBrush(self._main_window.pen_origin_marker.color())
            painter.drawEllipse(QtCore.QRectF(ox - r_orig, oy - r_orig, origin_sz, origin_sz))

        # MODIFIED: Use graphics_utils for defined scale line
        if self._main_window.showScaleLineCheckBox and self._main_window.showScaleLineCheckBox.isChecked() and \
           self._scale_manager and self._scale_manager.has_defined_scale_line():
            line_data_tuple = self._scale_manager.get_defined_scale_line_data()
            scale_m_per_px = self._scale_manager.get_scale_m_per_px()
            if line_data_tuple and scale_m_per_px is not None and scale_m_per_px > 0:
                p1x, p1y, p2x, p2y = line_data_tuple
                
                line_clr = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_COLOR)
                text_clr = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_COLOR)
                font_sz = int(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TEXT_SIZE))
                pen_w = float(settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_WIDTH))
                show_ticks = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_SHOW_TICKS)
                tick_factor = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR)

                dx = p2x - p1x
                dy = p2y - p1y
                pix_len = math.sqrt(dx*dx + dy*dy)
                meter_len = pix_len * scale_m_per_px
                len_text = self.format_length_value_for_line(meter_len)
                
                defined_line_pen = QtGui.QPen(line_clr, pen_w)
                # Cosmetic is handled within the graphics_utils drawing functions

                context_rect_for_label = QtCore.QRectF(0,0, float(self._video_handler.frame_width), float(self._video_handler.frame_height)) \
                                         if export_mode == ExportResolutionMode.ORIGINAL_VIDEO else visible_scene_rect

                graphics_utils.draw_defined_scale_display_on_painter(
                    painter=painter,
                    p1x=p1x, p1y=p1y, p2x=p2x, p2y=p2y,
                    length_text=len_text,
                    line_pen=defined_line_pen, # Pass the configured QPen
                    text_color=text_clr,
                    font_size=font_sz,
                    show_ticks=show_ticks,
                    tick_length_factor=tick_factor,
                    scene_context_rect=context_rect_for_label
                )
        
        painter.restore() 

        painter.save()
        painter.setWindow(export_qimage_rect.toRect())
        painter.setViewport(export_qimage_rect.toRect())

        if self._main_window.showScaleBarCheckBox and self._main_window.showScaleBarCheckBox.isChecked() and \
           self._scale_manager and self._scale_manager.get_scale_m_per_px() is not None and \
           hasattr(self._image_view, '_scale_bar_widget') and self._image_view._scale_bar_widget:
            
            sb_widget: 'ScaleBarWidget' = self._image_view._scale_bar_widget
            parent_width_for_sb_calc: int
            effective_view_scale_for_sb_calc: float

            if export_mode == ExportResolutionMode.ORIGINAL_VIDEO:
                parent_width_for_sb_calc = self._video_handler.frame_width
                effective_view_scale_for_sb_calc = 1.0 
            else: 
                parent_width_for_sb_calc = int(export_qimage_rect.width())
                if visible_scene_rect.width() > 0 and visible_scene_rect.height() > 0:
                    effective_view_scale_x = export_qimage_rect.width() / visible_scene_rect.width()
                    effective_view_scale_y = export_qimage_rect.height() / visible_scene_rect.height()
                    effective_view_scale_for_sb_calc = min(effective_view_scale_x, effective_view_scale_y)
                else: 
                    effective_view_scale_for_sb_calc = 1.0 

            sb_widget.update_dimensions( 
                m_per_px_scene=self._scale_manager.get_scale_m_per_px(),
                view_scale_factor=effective_view_scale_for_sb_calc,
                parent_view_width=parent_width_for_sb_calc
            )

            if sb_widget.isVisible() and sb_widget.get_current_bar_pixel_length() > 0:
                sb_bar_len_px = sb_widget.get_current_bar_pixel_length()
                sb_text = sb_widget.get_current_bar_text_label()
                sb_bar_color = sb_widget.get_current_bar_color()
                sb_text_color = sb_widget.get_current_text_color()
                sb_border_color = sb_widget.get_current_border_color()
                sb_font = sb_widget.get_current_font()
                painter_sb_font_metrics = QtGui.QFontMetrics(sb_font)
                
                sb_rect_h_px = sb_widget.get_current_bar_rect_height()
                sb_text_margin_bottom = sb_widget.get_text_margin_bottom()
                sb_border_thickness_px = sb_widget.get_border_thickness()
                sb_text_w_px, sb_text_h_px_overall = sb_widget.get_text_dimensions()

                margin = 10
                overall_sb_width = int(max(sb_bar_len_px + 2 * sb_border_thickness_px, sb_text_w_px))
                overall_sb_height = sb_text_h_px_overall + sb_text_margin_bottom + sb_rect_h_px + 2 * sb_border_thickness_px
                sb_x_offset = export_qimage_rect.width() - overall_sb_width - margin
                sb_y_offset = export_qimage_rect.height() - overall_sb_height - margin
                
                painter.save()
                painter.translate(sb_x_offset, sb_y_offset)
                painter.setFont(sb_font)
                painter.setPen(sb_text_color)
                text_x_local = (overall_sb_width - sb_text_w_px) / 2.0
                text_baseline_y_local = float(painter_sb_font_metrics.ascent())
                painter.drawText(QtCore.QPointF(text_x_local, text_baseline_y_local), sb_text)
                
                bar_start_x_local = (overall_sb_width - sb_bar_len_px) / 2.0
                bar_top_y_local = float(sb_text_h_px_overall + sb_text_margin_bottom + sb_border_thickness_px)
                bar_rect_local = QtCore.QRectF(bar_start_x_local, bar_top_y_local, sb_bar_len_px, float(sb_rect_h_px))
                
                current_scale_bar_pen = QtGui.QPen(sb_border_color, sb_border_thickness_px)
                current_scale_bar_pen.setCosmetic(True)
                painter.setPen(current_scale_bar_pen)
                painter.setBrush(sb_bar_color)
                painter.drawRect(bar_rect_local)
                painter.restore()

        margin = 5
        if settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_FILENAME):
            filename_text = self._video_handler.get_video_info().get("filename", "N/A")
            if filename_text != "N/A":
                font_size = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_FILENAME_FONT_SIZE)
                color = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_FILENAME_COLOR)
                font = QtGui.QFont()
                font.setPointSize(font_size)
                painter.setFont(font)
                painter.setPen(color)
                fm = QtGui.QFontMetrics(font)
                elided_text = fm.elidedText(filename_text, QtCore.Qt.TextElideMode.ElideMiddle, export_qimage_rect.width() - 2 * margin)
                painter.drawText(QtCore.QPointF(export_qimage_rect.left() + margin, export_qimage_rect.top() + margin + fm.ascent()), elided_text)

        total_frames_str = str(self._video_handler.total_frames) if self._video_handler.total_frames > 0 else "-"
        current_frame_str = str(current_frame_index + 1) if current_frame_index >= 0 else "-"
        frame_display_text = f"Frame: {current_frame_str} / {total_frames_str}"
        current_time_ms_val = (current_frame_index / self._video_handler.fps) * 1000 if self._video_handler.fps > 0 else 0.0
        total_time_ms_val = self._video_handler.total_duration_ms
        time_display_text = f"Time: {self._format_time_for_export(current_time_ms_val)} / {self._format_time_for_export(total_time_ms_val)}"

        y_pos_frame = export_qimage_rect.bottom() - margin
        if settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_FRAME_NUMBER):
            font_size = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_FRAME_NUMBER_FONT_SIZE)
            color = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_FRAME_NUMBER_COLOR)
            font = QtGui.QFont(); font.setPointSize(font_size)
            painter.setFont(font); painter.setPen(color)
            fm = QtGui.QFontMetrics(font)
            painter.drawText(QtCore.QPointF(export_qimage_rect.left() + margin, y_pos_frame), frame_display_text)
            y_pos_frame -= (fm.height() + margin / 2)

        if settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_SHOW_TIME):
            font_size = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_TIME_FONT_SIZE)
            color = settings_manager.get_setting(settings_manager.KEY_INFO_OVERLAY_TIME_COLOR)
            font = QtGui.QFont(); font.setPointSize(font_size)
            painter.setFont(font); painter.setPen(color)
            painter.drawText(QtCore.QPointF(export_qimage_rect.left() + margin, y_pos_frame), time_display_text)
        
        painter.restore()


    @QtCore.Slot(str, str, str, ExportResolutionMode, int, int) # Added start_frame_idx, end_frame_idx
    def export_video_with_overlays(self, 
                                   save_path: str, 
                                   chosen_fourcc_str: str, 
                                   chosen_extension_dot: str, 
                                   export_mode: ExportResolutionMode,
                                   start_frame_idx: int, # 0-based
                                   end_frame_idx: int    # 0-based
                                   ) -> None:
        logger.info(f"ExportHandler: Starting video export to {save_path} with FourCC {chosen_fourcc_str}, "
                    f"Mode: {export_mode.name}, Frames: {start_frame_idx}-{end_frame_idx}")
        self.exportStarted.emit()

        if not self._video_handler or not self._video_handler.is_loaded or \
           not self._image_view or not self._element_manager or \
           not self._scale_manager or not self._coord_transformer or not self._main_window:
            logger.error("ExportHandler: Core component(s) missing for video export.")
            self.exportFinished.emit(False, "Internal error: Core components missing.")
            return

        # Validate frame range against total video frames
        if not (0 <= start_frame_idx < self._video_handler.total_frames and
                0 <= end_frame_idx < self._video_handler.total_frames and
                start_frame_idx <= end_frame_idx):
            err_msg = (f"Invalid frame range for export: Start={start_frame_idx}, End={end_frame_idx}. "
                       f"Video has {self._video_handler.total_frames} frames (0-indexed).")
            logger.error(f"ExportHandler: {err_msg}")
            self.exportFinished.emit(False, err_msg)
            return
            
        try:
            export_width: int
            export_height: int
            visible_scene_rect_for_export: QtCore.QRectF

            if export_mode == ExportResolutionMode.ORIGINAL_VIDEO:
                export_width = self._video_handler.frame_width
                export_height = self._video_handler.frame_height
                visible_scene_rect_for_export = QtCore.QRectF(0, 0, float(export_width), float(export_height))
            else: # VIEWPORT mode
                viewport_size = self._image_view.viewport().size()
                export_width = viewport_size.width()
                export_height = viewport_size.height()
                # Get the scene rect corresponding to the current viewport for rendering
                visible_scene_rect_for_export = self._image_view.mapToScene(self._image_view.viewport().rect()).boundingRect()


            if export_width <= 0 or export_height <= 0:
                err_msg = f"Invalid export dimensions ({export_width}x{export_height})."
                logger.error(f"ExportHandler: {err_msg}")
                self.exportFinished.emit(False, err_msg)
                return

            fourcc = cv2.VideoWriter_fourcc(*chosen_fourcc_str)
            video_fps_for_export = self._video_handler.fps if self._video_handler.fps > 0 else 30.0
            video_writer = cv2.VideoWriter(save_path, fourcc, video_fps_for_export, (export_width, export_height))

            if not video_writer.isOpened():
                error_detail = (f"Could not open video writer for:\n{save_path}\n\n"
                                f"Using FourCC: '{chosen_fourcc_str}' for extension '{chosen_extension_dot}'.\n"
                                f"This may indicate a missing codec or an incompatible format/codec pair.")
                logger.error(f"ExportHandler: VideoWriter failed to open. {error_detail}")
                self.exportFinished.emit(False, error_detail)
                return

            # Calculate number of frames in the clip for progress reporting
            num_frames_in_clip = (end_frame_idx - start_frame_idx) + 1
            export_cancelled = False
            
            processed_clip_frames = 0 # Counter for frames processed in the current clip export

            for original_frame_idx in range(start_frame_idx, end_frame_idx + 1):
                if self._main_window._export_progress_dialog and self._main_window._export_progress_dialog.wasCanceled():
                    export_cancelled = True
                    break
                
                # Progress is based on the clip's frame count
                progress_msg = (f"Processing original frame {original_frame_idx + 1} "
                                f"(Clip frame {processed_clip_frames + 1}/{num_frames_in_clip})")
                self.exportProgress.emit(progress_msg, processed_clip_frames, num_frames_in_clip)
                QtWidgets.QApplication.processEvents()

                raw_cv_frame = self._video_handler.get_raw_frame_at_index(original_frame_idx)
                source_qimage_for_drawing: Optional[QtGui.QImage] = None
                if raw_cv_frame is not None:
                    h_raw, w_raw = raw_cv_frame.shape[:2]
                    channels_raw = raw_cv_frame.shape[2] if len(raw_cv_frame.shape) == 3 else 1
                    try:
                        if channels_raw == 3: 
                            contig_raw_cv_frame = np.require(raw_cv_frame, requirements=['C_CONTIGUOUS'])
                            rgb_frame_data = cv2.cvtColor(contig_raw_cv_frame, cv2.COLOR_BGR2RGB)
                            source_qimage_for_drawing = QtGui.QImage(rgb_frame_data.data, w_raw, h_raw, rgb_frame_data.strides[0], QtGui.QImage.Format.Format_RGB888).copy()
                        elif channels_raw == 1: 
                            contig_raw_cv_frame = np.require(raw_cv_frame, requirements=['C_CONTIGUOUS'])
                            source_qimage_for_drawing = QtGui.QImage(contig_raw_cv_frame.data, w_raw, h_raw, contig_raw_cv_frame.strides[0], QtGui.QImage.Format.Format_Grayscale8).copy()
                        
                        if source_qimage_for_drawing is not None and source_qimage_for_drawing.isNull():
                            source_qimage_for_drawing = None
                    except Exception as e_conv:
                        logger.error(f"Frame {original_frame_idx}: Error during raw_cv_frame to QImage conversion: {e_conv}", exc_info=True)
                        source_qimage_for_drawing = None
                
                if source_qimage_for_drawing is None:
                    logger.warning(f"Frame {original_frame_idx}: Using fallback black QImage for drawing.")
                    source_qimage_for_drawing = QtGui.QImage(export_width, export_height, QtGui.QImage.Format.Format_RGB888)
                    source_qimage_for_drawing.fill(QtCore.Qt.GlobalColor.black)

                export_canvas_qimage = QtGui.QImage(export_width, export_height, QtGui.QImage.Format.Format_RGB888)
                export_canvas_qimage.fill(QtCore.Qt.GlobalColor.black) 
                painter = QtGui.QPainter(export_canvas_qimage)
                painter.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.TextAntialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)

                target_export_qimage_rect = QtCore.QRectF(export_canvas_qimage.rect())
                
                painter.drawImage(target_export_qimage_rect, source_qimage_for_drawing, visible_scene_rect_for_export)
                
                # Pass the original_frame_idx for overlay rendering logic
                self._render_overlays_on_painter(painter, original_frame_idx, target_export_qimage_rect, visible_scene_rect_for_export, export_mode)
                painter.end()

                if export_canvas_qimage.format() != QtGui.QImage.Format.Format_RGB888:
                    export_canvas_qimage = export_canvas_qimage.convertToFormat(QtGui.QImage.Format.Format_RGB888)

                temp_width = export_canvas_qimage.width()
                temp_height = export_canvas_qimage.height()
                ptr = export_canvas_qimage.constBits()
                cv_export_frame_rgb = np.empty((temp_height, temp_width, 3), dtype=np.uint8)
                bytes_per_qimage_line = export_canvas_qimage.bytesPerLine()
                bytes_per_cv_line = temp_width * 3

                for i in range(temp_height):
                    line_start_offset_in_buffer = i * bytes_per_qimage_line
                    pixel_data_for_line = ptr[line_start_offset_in_buffer : line_start_offset_in_buffer + bytes_per_cv_line]
                    if len(pixel_data_for_line) == bytes_per_cv_line:
                        cv_export_frame_rgb[i] = np.frombuffer(pixel_data_for_line, dtype=np.uint8).reshape((temp_width, 3))
                    else:
                        logger.error(f"Export Video Frame {original_frame_idx}, Line {i}: Size mismatch. Filling line with black.")
                        cv_export_frame_rgb[i] = 0 

                cv_export_frame_bgr = cv2.cvtColor(cv_export_frame_rgb, cv2.COLOR_RGB2BGR)
                video_writer.write(cv_export_frame_bgr)
                processed_clip_frames += 1


            video_writer.release()
            # Ensure final progress update if not cancelled
            if not export_cancelled:
                 self.exportProgress.emit("Finalizing...", num_frames_in_clip, num_frames_in_clip)

            if export_cancelled:
                if os.path.exists(save_path):
                    try: os.remove(save_path); logger.info(f"Removed cancelled export file: {save_path}")
                    except OSError as e_rem: logger.warning(f"Could not remove cancelled export file {save_path}: {e_rem}")
                self.exportFinished.emit(False, "Video export cancelled by user.")
            else:
                self.exportFinished.emit(True, f"Video export complete: {os.path.basename(save_path)}")
        
        except Exception as e:
            logger.exception("ExportHandler: An error occurred during video export.")
            self.exportFinished.emit(False, f"Export error: {str(e)}")
        finally:
            if 'video_writer' in locals() and video_writer.isOpened(): # type: ignore
                video_writer.release()

    @QtCore.Slot(str, ExportResolutionMode)
    def export_current_frame_to_png(self, save_path: str, export_mode: ExportResolutionMode) -> None:
        logger.info(f"ExportHandler: Starting PNG export to {save_path}, Mode: {export_mode.name}")
        self.exportStarted.emit() # Although quick, emit for consistency if progress dialog is managed externally

        if not self._video_handler or not self._video_handler.is_loaded or self._video_handler.current_frame_index < 0 or \
           not self._image_view or not self._element_manager or \
           not self._scale_manager or not self._coord_transformer or not self._main_window:
            logger.error("ExportHandler: Core component(s) missing for frame export.")
            self.exportFinished.emit(False, "Internal error: Core components missing or no frame selected.")
            return

        current_frame_idx = self._video_handler.current_frame_index

        try:
            export_width: int
            export_height: int
            visible_scene_rect_for_export: QtCore.QRectF

            if export_mode == ExportResolutionMode.ORIGINAL_VIDEO:
                export_width = self._video_handler.frame_width
                export_height = self._video_handler.frame_height
                visible_scene_rect_for_export = QtCore.QRectF(0, 0, float(export_width), float(export_height))
            else: # VIEWPORT mode
                viewport_size = self._image_view.viewport().size()
                export_width = viewport_size.width()
                export_height = viewport_size.height()
                visible_scene_rect_for_export = self._image_view.mapToScene(self._image_view.viewport().rect()).boundingRect()
            
            if export_width <= 0 or export_height <= 0:
                self.exportFinished.emit(False, f"Invalid export dimensions ({export_width}x{export_height}).")
                return

            raw_cv_frame = self._video_handler.get_raw_frame_at_index(current_frame_idx)
            source_qimage_for_drawing: Optional[QtGui.QImage] = None
            if raw_cv_frame is not None:
                h_raw, w_raw = raw_cv_frame.shape[:2]
                channels_raw = raw_cv_frame.shape[2] if len(raw_cv_frame.shape) == 3 else 1
                try:
                    if channels_raw == 3: 
                        contig_raw_cv_frame = np.require(raw_cv_frame, requirements=['C_CONTIGUOUS'])
                        rgb_frame_data = cv2.cvtColor(contig_raw_cv_frame, cv2.COLOR_BGR2RGB)
                        source_qimage_for_drawing = QtGui.QImage(rgb_frame_data.data, w_raw, h_raw, rgb_frame_data.strides[0], QtGui.QImage.Format.Format_RGB888).copy()
                    elif channels_raw == 1: 
                        contig_raw_cv_frame = np.require(raw_cv_frame, requirements=['C_CONTIGUOUS'])
                        source_qimage_for_drawing = QtGui.QImage(contig_raw_cv_frame.data, w_raw, h_raw, contig_raw_cv_frame.strides[0], QtGui.QImage.Format.Format_Grayscale8).copy()
                    
                    if source_qimage_for_drawing is not None and source_qimage_for_drawing.isNull():
                        source_qimage_for_drawing = None
                except Exception as e_conv:
                    logger.error(f"Frame {current_frame_idx}: Error converting raw_cv_frame: {e_conv}", exc_info=True)
                    source_qimage_for_drawing = None

            if source_qimage_for_drawing is None:
                logger.warning(f"Frame {current_frame_idx}: Using fallback black QImage for PNG export.")
                source_qimage_for_drawing = QtGui.QImage(export_width, export_height, QtGui.QImage.Format.Format_RGB888)
                source_qimage_for_drawing.fill(QtCore.Qt.GlobalColor.black)

            export_canvas_qimage = QtGui.QImage(export_width, export_height, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            export_canvas_qimage.fill(QtCore.Qt.transparent) 
            painter = QtGui.QPainter(export_canvas_qimage)
            painter.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.TextAntialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
            
            target_export_qimage_rect = QtCore.QRectF(export_canvas_qimage.rect())
            painter.drawImage(target_export_qimage_rect, source_qimage_for_drawing, visible_scene_rect_for_export)

            self._render_overlays_on_painter(painter, current_frame_idx, target_export_qimage_rect, visible_scene_rect_for_export, export_mode)
            painter.end()

            if export_canvas_qimage.save(save_path, "PNG"):
                # For single frame, progress can be considered complete immediately
                self.exportProgress.emit(f"Saved {os.path.basename(save_path)}", 1, 1)
                self.exportFinished.emit(True, f"Frame saved to {os.path.basename(save_path)}")
            else:
                self.exportFinished.emit(False, f"Could not save image to {os.path.basename(save_path)}")

        except Exception as e:
            logger.exception("ExportHandler: An error occurred during frame export.")
            self.exportFinished.emit(False, f"Frame export error: {str(e)}")


    def _format_time_for_export(self, ms: float) -> str:
        """Formats time in milliseconds to MM:SS.mmm string for export overlays."""
        if ms < 0: return "--:--.---"
        try:
            s, mils = divmod(ms, 1000)
            m, s_rem = divmod(int(s), 60)
            return f"{m:02d}:{s_rem:02d}.{int(mils):03d}"
        except Exception:
            logger.error(f"Error formatting time {ms} for export.", exc_info=True)
            return "--:--.---"