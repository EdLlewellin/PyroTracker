# interactive_image_view.py
import math
import logging
from typing import Optional, List, Tuple # Added Tuple
from enum import Enum, auto

from PySide6 import QtCore, QtGui, QtWidgets

import config
from scale_bar_widget import ScaleBarWidget
from info_overlay_widget import InfoOverlayWidget
import settings_manager

# Get a logger for this module
logger = logging.getLogger(__name__)

class InteractionMode(Enum):
    """Defines the possible interaction modes for the view."""
    NORMAL = auto()
    SET_ORIGIN = auto()
    SET_SCALE_LINE_START = auto()
    SET_SCALE_LINE_END = auto()

class InteractiveImageView(QtWidgets.QGraphicsView):
    """
    A customized QGraphicsView for displaying and interacting with video frames.
    """
    # --- Signals ---
    pointClicked = QtCore.Signal(float, float) 
    frameStepRequested = QtCore.Signal(int) 
    modifiedClick = QtCore.Signal(float, float, QtCore.Qt.KeyboardModifiers) 
    originSetRequest = QtCore.Signal(float, float) 
    sceneMouseMoved = QtCore.Signal(float, float) 
    viewTransformChanged = QtCore.Signal() 

    scaleLinePoint1Clicked = QtCore.Signal(float, float) 
    scaleLinePoint2Clicked = QtCore.Signal(float, float, float, float)

    _BASE_SNAP_ANGLES_DEG: List[float] = [0.0, 30.0, 45.0, 60.0, 90.0, 
                                          120.0, 135.0, 150.0, 180.0,
                                          -30.0, -45.0, -60.0, -90.0,
                                          -120.0, -135.0, -150.0] 
    _scene: QtWidgets.QGraphicsScene
    _pixmap_item: Optional[QtWidgets.QGraphicsPixmapItem] 
    _initial_load: bool 
    _is_panning: bool
    _is_potential_pan: bool
    _left_button_press_pos: Optional[QtCore.QPoint]
    _last_pan_point: Optional[QtCore.QPoint]
    _min_scale: float
    _max_scale: float
    zoomInButton: QtWidgets.QPushButton
    zoomOutButton: QtWidgets.QPushButton
    resetViewButton: QtWidgets.QPushButton
    _current_mode: InteractionMode
    _scale_bar_widget: ScaleBarWidget
    _info_overlay_widget: InfoOverlayWidget
    _scale_line_point1_scene: Optional[QtCore.QPointF]
    _current_mouse_scene_pos: Optional[QtCore.QPointF]
    _temp_scale_marker1: Optional[QtWidgets.QGraphicsEllipseItem]
    _temp_scale_visuals_color: QtGui.QColor
    _snap_angles_rad: List[float]
    _is_snapping_active: bool
    _snapped_angle_for_display_deg: float
    _snap_line_color: QtGui.QColor
    _snap_text_color: QtGui.QColor
    _snap_text_font: QtGui.QFont

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        logger.info("Initializing InteractiveImageView...")

        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = None
        logger.debug("Graphics scene created and set.")

        self._initial_load = True
        self._is_panning = False
        self._is_potential_pan = False
        self._left_button_press_pos = None
        self._last_pan_point = None
        self._current_mode = InteractionMode.NORMAL
        logger.debug("Internal interaction state flags initialized.")

        self._min_scale = 0.01
        self._max_scale = config.MAX_ABS_SCALE
        logger.debug(f"Initial zoom limits: min={self._min_scale}, max={self._max_scale}")

        self._scale_line_point1_scene = None
        self._current_mouse_scene_pos = None
        self._temp_scale_marker1 = None
        self._temp_scale_visuals_color = QtGui.QColor(0, 255, 0, 180) 

        self._snap_angles_rad = [math.radians(angle) for angle in self._BASE_SNAP_ANGLES_DEG]
        self._is_snapping_active = False
        self._snapped_angle_for_display_deg = 0.0
        
        snap_r = self._temp_scale_visuals_color.red()
        snap_g = self._temp_scale_visuals_color.green()
        snap_b = self._temp_scale_visuals_color.blue()
        self._snap_line_color = QtGui.QColor(snap_r, snap_g, snap_b, 255) 
        
        self._snap_text_color = QtGui.QColor(QtCore.Qt.GlobalColor.white)
        self._snap_text_font = QtGui.QFont()
        self._snap_text_font.setPointSize(8) 
        self._snap_text_font.setBold(True)

        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(40, 40, 40)))
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setMouseTracking(True)
        
        logger.debug("View appearance and behavior configured.")

        self._create_overlay_buttons()
        
        self._scale_bar_widget = ScaleBarWidget(self)
        self._scale_bar_widget.setVisible(False)
        logger.debug("ScaleBarWidget created and initially hidden.")

        self._info_overlay_widget = InfoOverlayWidget(self)
        self._info_overlay_widget.setVisible(False) 
        logger.debug("InfoOverlayWidget created and initially hidden.")

        logger.info("InteractiveImageView initialization complete.")

    @staticmethod
    def _calculate_text_label_transform(
        p1: QtCore.QPointF,
        p2: QtCore.QPointF,
        text_rect: QtCore.QRectF,
        scene_bounding_rect: QtCore.QRectF,
        desired_gap_pixels: float = 3.0
    ) -> Tuple[QtCore.QPointF, float]:
        """
        Calculates the position and rotation for a text label associated with a line.

        Args:
            p1: Starting point of the line (scene coordinates).
            p2: Ending point of the line (scene coordinates).
            text_rect: The bounding rectangle of the text to be placed.
                       Its width and height are used for calculations.
            scene_bounding_rect: The bounding rectangle of the overall scene/image,
                                 used to determine the center for perpendicular shifting.
            desired_gap_pixels: The desired gap between the line and the text label.

        Returns:
            A tuple containing:
                - QPointF: The calculated top-left position for the text_rect.
                - float: The calculated rotation angle in degrees for the text.
        """
        text_width = text_rect.width()
        text_height = text_rect.height()

        line_mid_x = (p1.x() + p2.x()) / 2.0
        line_mid_y = (p1.y() + p2.y()) / 2.0

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        line_length = math.sqrt(dx * dx + dy * dy)

        if line_length < 1e-6:  # Handle zero-length or very short lines
            # Position text slightly offset from p1, no rotation
            return QtCore.QPointF(p1.x() + 2, p1.y() - text_height - 2), 0.0

        line_angle_rad = math.atan2(dy, dx)
        line_angle_deg = math.degrees(line_angle_rad)

        # Initial position: text centered with line midpoint, before rotation and shift
        initial_pos_x = line_mid_x - (text_width / 2.0)
        initial_pos_y = line_mid_y - (text_height / 2.0)

        # Rotation for the text to align with the line
        text_rotation_deg = line_angle_deg
        if text_rotation_deg > 90:
            text_rotation_deg -= 180
        elif text_rotation_deg < -90:
            text_rotation_deg += 180

        # Calculate perpendicular shift
        # Shift text away from the line, towards the center of the scene_bounding_rect
        shift_magnitude = (text_height / 2.0) + desired_gap_pixels
        
        # Normalized perpendicular vector to the line
        perp_dx = -dy / line_length
        perp_dy = dx / line_length

        img_center_x = scene_bounding_rect.center().x()
        img_center_y = scene_bounding_rect.center().y()

        # Test positions on both sides of the line
        test_pos1_x = line_mid_x + perp_dx * shift_magnitude
        test_pos1_y = line_mid_y + perp_dy * shift_magnitude
        dist_sq1 = (test_pos1_x - img_center_x)**2 + (test_pos1_y - img_center_y)**2
        
        test_pos2_x = line_mid_x - perp_dx * shift_magnitude
        test_pos2_y = line_mid_y - perp_dy * shift_magnitude
        dist_sq2 = (test_pos2_x - img_center_x)**2 + (test_pos2_y - img_center_y)**2

        final_shift_dx = perp_dx
        final_shift_dy = perp_dy
        if dist_sq2 < dist_sq1: # Shift in the other direction if it's closer to image center
            final_shift_dx = -perp_dx
            final_shift_dy = -perp_dy
            
        total_offset_x = final_shift_dx * shift_magnitude
        total_offset_y = final_shift_dy * shift_magnitude
        
        # The final position is the initial centered position plus the shift
        final_pos = QtCore.QPointF(initial_pos_x + total_offset_x, initial_pos_y + total_offset_y)

        return final_pos, text_rotation_deg

    def _calculate_zoom_limits(self) -> None:
        if not self._pixmap_item or not self.sceneRect().isValid() or self.viewport().width() <= 0:
            logger.warning("Cannot calculate zoom limits: Invalid scene, pixmap, or viewport.")
            self._min_scale = 0.01
            return

        scene_rect: QtCore.QRectF = self.sceneRect()
        vp_rect: QtCore.QRect = self.viewport().rect()
        logger.debug(f"Calculating min zoom limit. SceneRect: {scene_rect}, ViewportRect: {vp_rect}")

        try:
            if scene_rect.width() <= 0 or scene_rect.height() <= 0:
                 raise ZeroDivisionError("Scene rectangle has zero width or height.")
            scale_x: float = vp_rect.width() / scene_rect.width()
            scale_y: float = vp_rect.height() / scene_rect.height()
            self._min_scale = min(scale_x, scale_y)
        except ZeroDivisionError:
             logger.warning("ZeroDivisionError calculating minimum scale, using fallback 0.01.")
             self._min_scale = 0.01

        if self._min_scale <= 0 or math.isnan(self._min_scale):
             logger.warning(f"Calculated minimum scale ({self._min_scale}) is invalid, using fallback 0.01.")
             self._min_scale = 0.01

        if self._min_scale > self._max_scale:
             logger.warning(f"Calculated minimum scale ({self._min_scale:.4f}) > max scale ({self._max_scale:.4f}). Adjusting max scale.")
             self._max_scale = self._min_scale * 1.1
        logger.debug(f"Calculated zoom limits: min={self._min_scale:.4f}, max={self._max_scale:.4f}")

    def _create_overlay_buttons(self) -> None:
        logger.debug("Creating overlay buttons...")
        button_style: str = """
            QPushButton {
                background-color: rgba(80, 80, 80, 180); color: white;
                border: 1px solid rgba(150, 150, 150, 180); border-radius: 3px;
                font-weight: bold; font-size: 14pt; padding: 0px;
            }
            QPushButton:hover { background-color: rgba(100, 100, 100, 200); }
            QPushButton:pressed { background-color: rgba(60, 60, 60, 200); }
            QPushButton:disabled {
                 background-color: rgba(80, 80, 80, 100); color: rgba(200, 200, 200, 100);
                 border: 1px solid rgba(150, 150, 150, 100);
            }
        """
        button_size = QtCore.QSize(30, 30)

        self.zoomInButton = QtWidgets.QPushButton("+", self)
        self.zoomInButton.setFixedSize(button_size)
        self.zoomInButton.setToolTip("Zoom In (Ctrl+Scroll Up)")
        self.zoomInButton.setStyleSheet(button_style)
        self.zoomInButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoomInButton.clicked.connect(self._zoomIn)
        self.zoomInButton.hide()

        self.zoomOutButton = QtWidgets.QPushButton("-", self)
        self.zoomOutButton.setFixedSize(button_size)
        self.zoomOutButton.setToolTip("Zoom Out (Ctrl+Scroll Down)")
        self.zoomOutButton.setStyleSheet(button_style)
        self.zoomOutButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoomOutButton.clicked.connect(self._zoomOut)
        self.zoomOutButton.hide()

        self.resetViewButton = QtWidgets.QPushButton("⤢", self)
        self.resetViewButton.setFixedSize(button_size)
        self.resetViewButton.setToolTip("Fit Image to View (Reset Zoom/Pan)")
        self.resetViewButton.setStyleSheet(button_style)
        self.resetViewButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.resetViewButton.clicked.connect(self.resetView)
        self.resetViewButton.hide()
        logger.debug("Overlay buttons created.")

    def _update_overlay_widget_positions(self) -> None:
        if not hasattr(self, 'zoomInButton') or not self.zoomInButton:
             logger.warning("_update_overlay_widget_positions called before overlay buttons created.")
             return
        if not hasattr(self, '_scale_bar_widget') or not self._scale_bar_widget:
            logger.warning("_update_overlay_widget_positions called before scale bar widget created.")

        if not hasattr(self, '_info_overlay_widget') or not self._info_overlay_widget:
            logger.warning("_update_overlay_widget_positions called before info overlay widget created.")

        margin: int = 10
        vp_rect = self.viewport().rect()
        vp_width: int = vp_rect.width()
        vp_height: int = vp_rect.height()

        button_width: int = self.zoomInButton.width()
        button_height: int = self.zoomInButton.height()
        spacing: int = 5
        x_pos_buttons: int = vp_width - button_width - margin
        self.zoomInButton.move(x_pos_buttons, margin)
        self.zoomOutButton.move(x_pos_buttons, margin + button_height + spacing)
        self.resetViewButton.move(x_pos_buttons, margin + 2 * (button_height + spacing))

        if self._scale_bar_widget and self._scale_bar_widget.isVisible():
            sb_width: int = self._scale_bar_widget.width()
            sb_height: int = self._scale_bar_widget.height()
            x_pos_sb: int = vp_width - sb_width - margin
            y_pos_sb: int = vp_height - sb_height - margin
            self._scale_bar_widget.move(x_pos_sb, y_pos_sb)
            logger.debug(f"Scale bar positioned at ({x_pos_sb}, {y_pos_sb}), size: {self._scale_bar_widget.size()}")

        if self._info_overlay_widget:
            self._info_overlay_widget.setGeometry(vp_rect)
            if self._info_overlay_widget.isVisible():
                self._info_overlay_widget.update()
            logger.debug(f"InfoOverlayWidget geometry set to viewport: {vp_rect}")
                
    def _ensure_overlay_widgets_updated_on_show(self, buttons_visible: bool) -> None:
        if not hasattr(self, 'zoomInButton') or not self.zoomInButton:
             logger.warning("_ensure_overlay_widgets_updated_on_show called before overlay buttons created.")
             return

        logger.debug(f"Setting overlay buttons visible: {buttons_visible}")
        if buttons_visible:
            self._update_overlay_widget_positions()
            self.zoomInButton.show()
            self.zoomOutButton.show()
            self.resetViewButton.show()
        else:
            self.zoomInButton.hide()
            self.zoomOutButton.hide()
            self.resetViewButton.hide()

        if self._info_overlay_widget:
            if buttons_visible != self._info_overlay_widget.isVisible():
                 self._info_overlay_widget.setVisible(buttons_visible)
                 logger.debug(f"InfoOverlayWidget visibility set to: {buttons_visible}")
            if buttons_visible:
                self._update_overlay_widget_positions()

    def _zoom(self, factor: float, mouse_viewport_pos: Optional[QtCore.QPoint] = None) -> None:
        if not self._pixmap_item:
            logger.debug("_zoom called but no pixmap item exists.")
            return

        current_scale: float = self.transform().m11()
        logger.debug(f"Zoom requested with factor {factor:.3f}. Current scale: {current_scale:.4f}, mouse_viewport_pos: {mouse_viewport_pos}")

        target_scale: float
        if factor > 1.0:
            target_scale = min(current_scale * factor, self._max_scale)
        else:
            target_scale = max(current_scale * factor, self._min_scale)
        
        logger.debug(f"Calculated target scale: {target_scale:.4f} (Min: {self._min_scale:.4f}, Max: {self._max_scale:.4f})")

        if not math.isclose(target_scale, current_scale, rel_tol=1e-5):
            actual_zoom_factor: float = target_scale / current_scale
            
            original_anchor = self.transformationAnchor()
            self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
            self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)

            logger.debug(f"Applying scale factor {actual_zoom_factor:.4f} (Target: {target_scale:.4f}) using AnchorUnderMouse.")
            self.scale(actual_zoom_factor, actual_zoom_factor)
            
            self.viewTransformChanged.emit()
        else:
            logger.debug("Target scale close to current scale or limits reached. No zoom applied.")

    @QtCore.Slot()
    def _zoomIn(self) -> None:
        logger.debug("Zoom In button clicked.")
        zoom_in_factor: float = 1.3
        viewport_center = self.viewport().rect().center()
        self._zoom(zoom_in_factor, viewport_center)

    @QtCore.Slot()
    def _zoomOut(self) -> None:
        logger.debug("Zoom Out button clicked.")
        zoom_out_factor: float = 1.0 / 1.3
        viewport_center = self.viewport().rect().center()
        self._zoom(zoom_out_factor, viewport_center)

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        logger.info(f"Setting pixmap. Is null: {pixmap.isNull()}. Size: {pixmap.size()}")
        current_transform: Optional[QtGui.QTransform] = None
        is_initial: bool = self._initial_load
        logger.debug(f"setPixmap called. Initial load flag: {is_initial}")

        if self._pixmap_item and self.sceneRect().isValid() and not is_initial:
            current_transform = self.transform()
            logger.debug(f"Stored previous transform: {current_transform}")

        logger.debug("Clearing graphics scene...")
        self.clearTemporaryScaleVisuals()
        self._scene.clear()
        self._pixmap_item = None
        logger.debug("Graphics scene cleared.")

        if pixmap and not pixmap.isNull():
            logger.debug("Adding new pixmap item to scene.")
            self._pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
            self._pixmap_item.setTransformationMode(QtCore.Qt.TransformationMode.SmoothTransformation)
            self._scene.addItem(self._pixmap_item)

            new_scene_rect: QtCore.QRectF = QtCore.QRectF(pixmap.rect())
            self.setSceneRect(new_scene_rect)
            logger.debug(f"Scene rect set to: {new_scene_rect}")

            self._calculate_zoom_limits()

            transform_changed_by_set_pixmap = False
            if is_initial:
                logger.info("Initial pixmap load, resetting view to fit.")
                self.resetView()
                self._initial_load = False
                transform_changed_by_set_pixmap = True
            elif current_transform is not None:
                logger.info("Attempting to restore previous view transform.")
                previous_scale: float = current_transform.m11()
                clamped_scale: float = max(self._min_scale, min(previous_scale, self._max_scale))
                if math.isclose(clamped_scale, previous_scale, rel_tol=1e-5):
                     self.setTransform(current_transform)
                     logger.debug("Previous transform restored.")
                     transform_changed_by_set_pixmap = True
                else:
                     logger.warning(f"Previous transform scale ({previous_scale:.4f}) outside new limits [{self._min_scale:.4f}, {self._max_scale:.4f}]. Resetting view.")
                     self.resetView()
                     transform_changed_by_set_pixmap = True
            else:
                 logger.warning("No valid previous transform stored despite not being initial load. Resetting view.")
                 self.resetView()
                 transform_changed_by_set_pixmap = True

            self._ensure_overlay_widgets_updated_on_show(True)
            if self._info_overlay_widget:
                self._info_overlay_widget.setVisible(True)

            if transform_changed_by_set_pixmap and not is_initial :
                self.viewTransformChanged.emit()
        else:
             logger.info("Invalid or null pixmap provided. Clearing scene rect and hiding buttons/overlays.")
             self.setSceneRect(QtCore.QRectF())
             self._min_scale = 0.01
             self._max_scale = config.MAX_ABS_SCALE
             self._ensure_overlay_widgets_updated_on_show(False)
             if self._scale_bar_widget:
                self._scale_bar_widget.setVisible(False)
             if self._info_overlay_widget:
                self._info_overlay_widget.setVisible(False)

        logger.debug("Resetting interaction state variables (pan/click).")
        self._is_panning = False
        self._is_potential_pan = False
        self._left_button_press_pos = None
        self._last_pan_point = None

    def resetInitialLoadFlag(self) -> None:
        logger.debug("Resetting initial load flag to True.")
        self._initial_load = True

    @QtCore.Slot()
    def resetView(self) -> None:
        logger.info("Resetting view (fit image).")
        if not self._pixmap_item or not self.sceneRect().isValid():
            logger.warning("Cannot reset view: No valid pixmap item or scene rect.")
            return

        self.resetTransform()
        logger.debug(f"Applying minimum scale: {self._min_scale:.4f}")
        self.scale(self._min_scale, self._min_scale)

        scene_center: QtCore.QPointF = self.sceneRect().center()
        logger.debug(f"Centering view on scene center: {scene_center}")
        self.centerOn(scene_center)
        self.viewTransformChanged.emit()
        logger.info("View reset complete.")

    def draw_persistent_scale_line(self,
                                   line_data: Tuple[float, float, float, float],
                                   length_text: str,
                                   line_color: QtGui.QColor,
                                   text_color: QtGui.QColor,
                                   font_size: int,
                                   pen_width: float):
        if not self._scene or not line_data:
            logger.warning("Cannot draw persistent scale line: Scene or line_data missing.")
            return
        if not self.sceneRect().isValid() or self.sceneRect().isEmpty():
            logger.warning("Cannot draw persistent scale line: SceneRect is invalid or empty.")
            return

        p1x, p1y, p2x, p2y = line_data
        z_value = 12 # Ensure text is drawn above line and ticks if they have same z_value

        line_pen = QtGui.QPen(line_color, pen_width)
        line_pen.setCosmetic(True)
        line_pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)

        line_item = QtWidgets.QGraphicsLineItem(p1x, p1y, p2x, p2y)
        line_item.setPen(line_pen)
        line_item.setZValue(z_value -1) # Draw line slightly behind text and ticks
        self._scene.addItem(line_item)

        show_ticks = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_SHOW_TICKS)
        tick_length_factor = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR)
        
        tick_total_length = pen_width * tick_length_factor
        half_tick_length = tick_total_length / 2.0

        if show_ticks and tick_total_length > 0:
            dx = p2x - p1x
            dy = p2y - p1y
            line_length_for_norm = math.sqrt(dx*dx + dy*dy)

            if line_length_for_norm > 1e-6:
                norm_perp_dx = -dy / line_length_for_norm
                norm_perp_dy = dx / line_length_for_norm

                tick1_p1x = p1x + norm_perp_dx * half_tick_length
                tick1_p1y = p1y + norm_perp_dy * half_tick_length
                tick1_p2x = p1x - norm_perp_dx * half_tick_length
                tick1_p2y = p1y - norm_perp_dy * half_tick_length
                tick_item1 = QtWidgets.QGraphicsLineItem(tick1_p1x, tick1_p1y, tick1_p2x, tick1_p2y)
                tick_item1.setPen(line_pen)
                tick_item1.setZValue(z_value) # Ticks at same level as text
                self._scene.addItem(tick_item1)

                tick2_p1x = p2x + norm_perp_dx * half_tick_length
                tick2_p1y = p2y + norm_perp_dy * half_tick_length
                tick2_p2x = p2x - norm_perp_dx * half_tick_length
                tick2_p2y = p2y - norm_perp_dy * half_tick_length
                tick_item2 = QtWidgets.QGraphicsLineItem(tick2_p1x, tick2_p1y, tick2_p2x, tick2_p2y)
                tick_item2.setPen(line_pen)
                tick_item2.setZValue(z_value)
                self._scene.addItem(tick_item2)
        elif not show_ticks: # Draw dots if ticks are disabled
            item_brush = QtGui.QBrush(line_color)
            marker_radius = max(1.0, pen_width / 2.0) # Ensure radius is at least 1
            for px, py in [(p1x, p1y), (p2x, p2y)]:
                dot_marker = QtWidgets.QGraphicsEllipseItem(px - marker_radius, py - marker_radius, 2 * marker_radius, 2 * marker_radius)
                dot_marker.setPen(QtGui.QPen(line_color, 0.5)) # Thin border for dot
                dot_marker.setBrush(item_brush)
                dot_marker.setZValue(z_value) # Dots at same level as text
                self._scene.addItem(dot_marker)

        # --- Text Item Creation and Styling ---
        text_item = QtWidgets.QGraphicsSimpleTextItem(length_text)
        text_item.setBrush(QtGui.QBrush(text_color))
        font = text_item.font() # Get default font
        font.setPointSize(font_size)
        text_item.setFont(font)
        text_item.setZValue(z_value) # Text on top

        # --- Use the new static method for position and rotation ---
        text_pos, text_rot_deg = InteractiveImageView._calculate_text_label_transform(
            QtCore.QPointF(p1x, p1y),
            QtCore.QPointF(p2x, p2y),
            text_item.boundingRect(), # Pass the text's own bounding rect
            self.sceneRect()          # Pass the view's current sceneRect
        )
        
        text_item.setPos(text_pos)
        # QGraphicsSimpleTextItem does not have setTransformOriginPoint directly.
        # Rotation is around its (0,0) which is its top-left.
        # If precise center rotation is needed, QGraphicsTextItem is more flexible,
        # or manual adjustment of pos after rotation.
        # For now, simple rotation:
        if abs(text_rot_deg) > 1e-3 : # Only set rotation if it's meaningful
             # To rotate around center, we'd typically translate, rotate, translate back.
             # Or, setTransformOriginPoint if using QGraphicsObject.
             # For QGraphicsSimpleTextItem, setPos effectively sets the top-left.
             # If we rotate, it rotates around this top-left.
             # To achieve center rotation:
             # 1. Calculate center of text_item.boundingRect(): text_item.boundingRect().center()
             # 2. Set transform origin to this center: text_item.setTransformOriginPoint(center_x, center_y)
             # 3. Set position to text_pos (which was calculated for top-left)
             # 4. Set rotation.
             # However, _calculate_text_label_transform already provides the TOP-LEFT position (text_pos)
             # and a rotation (text_rot_deg) that assumes the text item's local (0,0) is its top-left.
             # The rotation should be applied *before* the final shift if the shift is in global coords,
             # or the shift should be calculated in the rotated frame.
             # The _calculate_text_label_transform returns the final top-left position *after* considering the shift.
             # So, we set position, then set transform origin for rotation, then rotate.
            text_center_x = text_item.boundingRect().width() / 2.0
            text_center_y = text_item.boundingRect().height() / 2.0
            text_item.setTransformOriginPoint(text_center_x, text_center_y)
            text_item.setRotation(text_rot_deg)

        self._scene.addItem(text_item)
        logger.debug(f"Drew scale line text '{length_text}'. Final Pos: {text_item.pos()}, Rotation: {text_rot_deg:.1f}")

    def clearOverlay(self) -> None:
        if not self._scene:
            logger.error("clearOverlay called but scene does not exist.")
            return
        logger.debug("Clearing overlay graphics items...")

        items_to_remove: List[QtWidgets.QGraphicsItem] = []
        for item in self._scene.items():
             has_marker2 = hasattr(self, '_temp_scale_marker2')
             has_line = hasattr(self, '_temp_scale_line')
             
             is_marker2 = has_marker2 and item == self._temp_scale_marker2
             is_line = has_line and item == self._temp_scale_line

             if item != self._pixmap_item and \
                item != self._temp_scale_marker1 and \
                not is_marker2 and \
                not is_line:
                 items_to_remove.append(item)

        num_removed: int = 0
        for item in items_to_remove:
            try:
                if item.scene() == self._scene: # Ensure item still belongs to this scene
                     self._scene.removeItem(item)
                     num_removed += 1
            except Exception as e: # General exception if removeItem fails for some reason
                logger.warning(f"Error removing overlay item {item} from scene: {e}", exc_info=False)
        logger.debug(f"Cleared {num_removed} overlay items (excluding temp scale visuals).")


    def set_interaction_mode(self, mode: InteractionMode) -> None:
        if self._current_mode != mode:
            logger.info(f"Changing interaction mode from {self._current_mode.name} to {mode.name}")
            
            if self._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END] and \
               mode == InteractionMode.NORMAL:
                self.clearTemporaryScaleVisuals()

            self._current_mode = mode
            
            if mode == InteractionMode.SET_ORIGIN:
                 self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            elif mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END]:
                 self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else: # InteractionMode.NORMAL
                 self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        else:
             logger.debug(f"Interaction mode already set to {mode.name}")

    def _draw_temporary_scale_marker(self, scene_pos: QtCore.QPointF) -> QtWidgets.QGraphicsEllipseItem:
        # Define the desired diameter of the marker in screen pixels
        screen_pixel_diameter = 6.0 
        radius = screen_pixel_diameter / 2.0

        # Create the ellipse centered at (0,0) in its local coordinates.
        # This local geometry will be rendered as screen pixels.
        marker = QtWidgets.QGraphicsEllipseItem(-radius, -radius, screen_pixel_diameter, screen_pixel_diameter)
        
        # Set the marker's position in the scene.
        marker.setPos(scene_pos) 

        # Crucial step: Make the item ignore view transformations for its rendering.
        marker.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        
        # Pen width will now also be in screen pixels. A thin line is usually best.
        pen = QtGui.QPen(self._temp_scale_visuals_color, 1.0) 
        # pen.setCosmetic(True) # Cosmetic pen is less critical when ItemIgnoresTransformations is true for simple shapes
        marker.setPen(pen)
        marker.setBrush(self._temp_scale_visuals_color)
        marker.setZValue(20) # Ensure it's on top
        
        # Add to scene (if not already handled by a specific logic flow,
        # though typically this method is called when adding it)
        if marker.scene() != self._scene: # Avoid re-adding if it was somehow already there
            self._scene.addItem(marker)
            
        return marker
    def drawForeground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        super().drawForeground(painter, rect)

        if self._current_mode == InteractionMode.SET_SCALE_LINE_END and \
           self._scale_line_point1_scene is not None and \
           self._current_mouse_scene_pos is not None: 

            p1_scene = self._scale_line_point1_scene
            p2_scene = self._current_mouse_scene_pos 

            p1_viewport = self.mapFromScene(p1_scene)
            p2_viewport = self.mapFromScene(p2_scene)

            painter.save()
            painter.setTransform(QtGui.QTransform()) 

            pen = QtGui.QPen()
            pen.setWidth(1) 

            if self._is_snapping_active:
                pen.setColor(self._snap_line_color)
                pen.setStyle(QtCore.Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.drawLine(p1_viewport, p2_viewport)

                painter.setFont(self._snap_text_font)
                painter.setPen(self._snap_text_color)
                angle_string = f"{self._snapped_angle_for_display_deg:.0f}°"
                
                text_rect = painter.fontMetrics().boundingRect(angle_string)
                text_offset_x = 10 
                text_offset_y = -text_rect.height() / 2 
                
                if p2_viewport.x() < p1_viewport.x():
                    text_offset_x = -text_rect.width() - 10
                
                text_pos = QtCore.QPointF(p2_viewport.x() + text_offset_x, 
                                         p2_viewport.y() + text_offset_y + text_rect.height()) 

                bg_rect = text_rect.translated(text_pos.x(), text_pos.y() - text_rect.height() + painter.fontMetrics().ascent() - 2) 
                bg_rect.adjust(-2, -1, 2, 1)
                painter.setBrush(QtGui.QColor(0,0,0,120))
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.drawRoundedRect(bg_rect, 2, 2)
                
                painter.setPen(self._snap_text_color) 
                painter.drawText(text_pos, angle_string)

            else: 
                pen.setColor(self._temp_scale_visuals_color)
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(p1_viewport, p2_viewport)
            
            painter.restore()

    def clearTemporaryScaleVisuals(self) -> None:
        logger.debug("Clearing temporary scale visuals and snap state.")
        if self._temp_scale_marker1 and self._temp_scale_marker1.scene() == self._scene:
            self._scene.removeItem(self._temp_scale_marker1)
            self._temp_scale_marker1 = None
    
        self._scale_line_point1_scene = None
        self._current_mouse_scene_pos = None # Reset current mouse scene pos used by drawForeground
        
        self._is_snapping_active = False # Reset snap state
        self._snapped_angle_for_display_deg = 0.0
    
        self.viewport().update() 
        logger.debug("Temporary scale visuals and snap state cleared.")

    def _get_closest_snap_angle(self, current_angle_rad: float) -> float:
        if not self._snap_angles_rad:
            return current_angle_rad 

        min_diff = float('inf')
        closest_angle = current_angle_rad

        for snap_angle_rad in self._snap_angles_rad:
            diff = abs(current_angle_rad - snap_angle_rad)
            if diff > math.pi:
                diff = 2 * math.pi - diff
            
            if diff < min_diff:
                min_diff = diff
                closest_angle = snap_angle_rad
        
        return closest_angle

    def _calculate_orthogonally_constrained_snap_point(self, 
                                                       p1: QtCore.QPointF, 
                                                       cursor_pos: QtCore.QPointF, 
                                                       snapped_angle_rad: float) -> QtCore.QPointF:
        x1, y1 = p1.x(), p1.y()
        cx, cy = cursor_pos.x(), cursor_pos.y()

        epsilon = 1e-9
        if abs(snapped_angle_rad - 0.0) < epsilon or abs(snapped_angle_rad - math.pi) < epsilon or abs(snapped_angle_rad + math.pi) < epsilon : 
            return QtCore.QPointF(cx, y1)
        if abs(snapped_angle_rad - math.pi/2) < epsilon or abs(snapped_angle_rad + math.pi/2) < epsilon: 
            return QtCore.QPointF(x1, cy)

        cos_theta = math.cos(snapped_angle_rad)
        sin_theta = math.sin(snapped_angle_rad)

        t_to_vertical_boundary = float('inf')
        if abs(cos_theta) > epsilon: 
            t_candidate_v = (cx - x1) / cos_theta
            if t_candidate_v >= -epsilon: 
                 t_to_vertical_boundary = t_candidate_v

        t_to_horizontal_boundary = float('inf')
        if abs(sin_theta) > epsilon: 
            t_candidate_h = (cy - y1) / sin_theta
            if t_candidate_h >= -epsilon: 
                 t_to_horizontal_boundary = t_candidate_h
        
        final_t = 0.0 
        
        valid_ts = []
        if t_to_vertical_boundary != float('inf'):
            valid_ts.append(t_to_vertical_boundary)
        if t_to_horizontal_boundary != float('inf'):
            valid_ts.append(t_to_horizontal_boundary)

        if not valid_ts: 
             if math.isclose(x1, cx) and math.isclose(y1, cy):
                final_t = 0.0
             else: 
                logger.warning(f"Snap calc: No valid t for angle {math.degrees(snapped_angle_rad)}, P1({x1},{y1}), C({cx},{cy})")
                return cursor_pos 
        else:
            final_t = min(t for t in valid_ts if t >= -epsilon)

        snapped_p2_x = x1 + final_t * cos_theta
        snapped_p2_y = y1 + final_t * sin_theta
        
        return QtCore.QPointF(snapped_p2_x, snapped_p2_y)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self._pixmap_item:
            super().wheelEvent(event)
            return

        modifiers: QtCore.Qt.KeyboardModifiers = event.modifiers()
        angle_delta: QtCore.QPoint = event.angleDelta()
        mouse_pos_in_viewport: QtCore.QPoint = event.position().toPoint()

        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            logger.debug(f"Ctrl+Scroll detected: Performing zoom at viewport pos {mouse_pos_in_viewport}.")
            scroll_amount: int = angle_delta.y()
            if scroll_amount == 0:
                event.ignore()
                return
            zoom_factor_base: float = 1.15
            if scroll_amount > 0:
                self._zoom(zoom_factor_base, mouse_pos_in_viewport)
            else:
                self._zoom(1.0 / zoom_factor_base, mouse_pos_in_viewport)
            event.accept()
        elif self._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END]:
            logger.debug(f"Wheel event ignored (frame stepping disabled) during {self._current_mode.name} mode.")
            event.accept()
        else: 
            logger.debug("Scroll detected (no/other modifier): Requesting frame step.")
            scroll_amount_y: int = angle_delta.y()
            if scroll_amount_y == 0:
                event.ignore()
                return
            step: int = -1 if scroll_amount_y > 0 else 1 
            logger.debug(f"Emitting frameStepRequested signal with step: {step}")
            self.frameStepRequested.emit(step)
            event.accept()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        logger.debug(f"Resize event detected. New viewport size: {event.size()}")
        previous_transform: Optional[QtGui.QTransform] = None
        previous_center: Optional[QtCore.QPointF] = None
        if self._pixmap_item and self.sceneRect().isValid():
            previous_transform = self.transform()
            previous_center = self.mapToScene(self.viewport().rect().center())

        super().resizeEvent(event)
        self._calculate_zoom_limits()

        view_reset_called = False
        if previous_transform and previous_center and self._pixmap_item and self.sceneRect().isValid():
             current_scale: float = previous_transform.m11()
             clamped_scale: float = max(self._min_scale, min(current_scale, self._max_scale))

             if not math.isclose(clamped_scale, current_scale, rel_tol=1e-5):
                 logger.warning(f"Previous scale {current_scale:.4f} is outside new limits [{self._min_scale:.4f}, {self._max_scale:.4f}] after resize. Resetting view.")
                 self.resetView()
                 view_reset_called = True
             else:
                 logger.debug("Previous scale still within new limits after resize. Re-centering.")
                 self.centerOn(previous_center)
        elif self._pixmap_item and self.sceneRect().isValid():
             logger.debug("No valid previous state or pixmap, resetting view after resize.")
             self.resetView()
             view_reset_called = True

        self._update_overlay_widget_positions()
        
        if not view_reset_called:
            self.viewTransformChanged.emit()
        logger.debug("Resize event handling complete.")

    def set_scale_bar_visibility(self, visible: bool) -> None:
        if hasattr(self, '_scale_bar_widget') and self._scale_bar_widget:
            if visible and (not self._pixmap_item or not self.sceneRect().isValid()):
                logger.debug("Request to show scale bar, but no valid pixmap. Keeping hidden.")
                self._scale_bar_widget.setVisible(False)
                return

            if self._scale_bar_widget.isVisible() != visible:
                self._scale_bar_widget.setVisible(visible)
                logger.debug(f"Scale bar visibility set to: {visible}")
                if visible:
                    self._update_overlay_widget_positions()
            elif visible: # Ensure position is updated even if visibility state didn't change
                 self._update_overlay_widget_positions()

    def update_scale_bar_dimensions(self, m_per_px_scene: Optional[float]) -> None:
        if hasattr(self, '_scale_bar_widget') and self._scale_bar_widget:
            if not self._pixmap_item or not self.sceneRect().isValid(): # No video/image loaded
                self._scale_bar_widget.setVisible(False)
                return

            current_view_scale_factor = self.transform().m11() # This is the scale of the view itself
            parent_view_width = self.viewport().width()

            self._scale_bar_widget.update_dimensions(
                m_per_px_scene,
                current_view_scale_factor,
                parent_view_width
            )
            if self._scale_bar_widget.isVisible(): # If update_dimensions made it visible, or it was already
                 self._update_overlay_widget_positions()

    def get_current_view_scale_factor(self) -> float:
        return self.transform().m11()

    def get_min_view_scale(self) -> float:
        # Ensure limits are up-to-date if called externally before setPixmap
        if self._pixmap_item and self.sceneRect().isValid():
            self._calculate_zoom_limits() 
        return self._min_scale
    
    def get_max_view_scale(self) -> float:
        return self._max_scale

    def set_info_overlay_video_data(self, filename: str, total_frames: int, total_duration_ms: float) -> None:
        if self._info_overlay_widget:
            self._info_overlay_widget.update_video_info(filename, total_frames, total_duration_ms)
            if self._pixmap_item and not self._info_overlay_widget.isVisible(): # Show it if pixmap is loaded
                 self._info_overlay_widget.setVisible(True)
                 self._update_overlay_widget_positions() # Ensure position is correct

    def set_info_overlay_current_frame_time(self, frame_idx: int, time_ms: float) -> None:
        if self._info_overlay_widget:
            self._info_overlay_widget.update_current_frame_time(frame_idx, time_ms)

    def refresh_info_overlay_appearance(self) -> None:
        if self._info_overlay_widget:
            self._info_overlay_widget.update_appearance_from_settings()
            if self._info_overlay_widget.isVisible(): # Only update (repaint) if visible
                self._info_overlay_widget.update() 
            logger.debug("InfoOverlayWidget appearance refreshed.")

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        button: QtCore.Qt.MouseButton = event.button()
        logger.debug(f"Mouse press event: Button={button}, Pos={event.pos()}, Mode={self._current_mode.name}")

        if button == QtCore.Qt.MouseButton.LeftButton and self._pixmap_item:
            scene_pos = self.mapToScene(event.pos())
            if self._pixmap_item.sceneBoundingRect().contains(scene_pos):
                self._left_button_press_pos = event.pos()
                self._is_potential_pan = True
                self._is_panning = False # Reset panning flag
                
                # Accept the event to prevent further processing if we intend to handle it
                if self._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END, InteractionMode.SET_ORIGIN, InteractionMode.NORMAL]:
                    event.accept()
                    return # Important to return here so base class doesn't also process
            else:
                logger.debug("Left click outside pixmap bounds.")
                self._is_potential_pan = False # Not a potential pan if outside
                self._left_button_press_pos = None # Clear press position
                return # Let base class handle if desired, or just ignore

        super().mousePressEvent(event) # Call base for other buttons or if not handled

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        viewport_pos = event.pos()
        scene_x, scene_y = -1.0, -1.0
        current_scene_pos_for_move: Optional[QtCore.QPointF] = None 

        if self._pixmap_item:
            current_scene_pos_for_move = self.mapToScene(viewport_pos)
            if self._pixmap_item.sceneBoundingRect().contains(current_scene_pos_for_move):
                scene_x, scene_y = current_scene_pos_for_move.x(), current_scene_pos_for_move.y()
            else:
                current_scene_pos_for_move = None 

        self.sceneMouseMoved.emit(scene_x, scene_y) 

        if self._is_potential_pan and self._left_button_press_pos is not None and \
           (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
            distance_moved = (viewport_pos - self._left_button_press_pos).manhattanLength()
            if distance_moved >= config.DRAG_THRESHOLD:
                if self._current_mode in [InteractionMode.NORMAL, InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END, InteractionMode.SET_ORIGIN]:
                    logger.debug(f"Drag threshold ({config.DRAG_THRESHOLD}px) exceeded. Starting pan in mode {self._current_mode.name}.")
                    self._is_panning = True
                
                self._is_potential_pan = False 
                if self._is_panning:
                    self._last_pan_point = viewport_pos
                    self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                    if self._current_mode == InteractionMode.SET_SCALE_LINE_END:
                        self._current_mouse_scene_pos = None 
                        self.viewport().update()
                    event.accept()
                    return

        if self._is_panning and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
            if self._last_pan_point is not None:
                delta = viewport_pos - self._last_pan_point
                self._last_pan_point = viewport_pos
                h_bar = self.horizontalScrollBar()
                v_bar = self.verticalScrollBar()
                if h_bar: h_bar.setValue(h_bar.value() - delta.x())
                if v_bar: v_bar.setValue(v_bar.value() - delta.y())
                self.viewTransformChanged.emit()
            event.accept()
            return
        
        if not self._is_panning and \
           self._current_mode == InteractionMode.SET_SCALE_LINE_END and \
           self._scale_line_point1_scene is not None:
            
            raw_cursor_scene_pos = self.mapToScene(viewport_pos)
            p1 = self._scale_line_point1_scene
            p2_target_for_line: QtCore.QPointF

            if QtWidgets.QApplication.keyboardModifiers() == QtCore.Qt.KeyboardModifier.ShiftModifier:
                self._is_snapping_active = True
                dx = raw_cursor_scene_pos.x() - p1.x()
                dy = raw_cursor_scene_pos.y() - p1.y()
                
                if math.isclose(dx, 0) and math.isclose(dy, 0): 
                    snapped_angle_rad = 0.0 
                    p2_target_for_line = p1 
                else:
                    current_angle_rad = math.atan2(dy, dx)
                    snapped_angle_rad = self._get_closest_snap_angle(current_angle_rad)
                    p2_target_for_line = self._calculate_orthogonally_constrained_snap_point(
                        p1, raw_cursor_scene_pos, snapped_angle_rad
                    )
                self._snapped_angle_for_display_deg = math.degrees(snapped_angle_rad)
            else: 
                self._is_snapping_active = False
                p2_target_for_line = raw_cursor_scene_pos
            
            if self._current_mouse_scene_pos != p2_target_for_line:
                self._current_mouse_scene_pos = p2_target_for_line
                self.viewport().update() 
            
        super().mouseMoveEvent(event) 

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        button: QtCore.Qt.MouseButton = event.button()
        logger.debug(f"Mouse release: Button={button}, Mode={self._current_mode.name}, Panning={self._is_panning}, PotentialPan={self._is_potential_pan}")

        if button == QtCore.Qt.MouseButton.LeftButton:
            was_panning = self._is_panning
            is_click_intent = self._is_potential_pan 

            self._is_panning = False
            self._is_potential_pan = False 

            if was_panning:
                logger.debug("Panning finished.")
            elif is_click_intent and self._pixmap_item and self._left_button_press_pos is not None:
                final_click_scene_pos: QtCore.QPointF
                if self._current_mode == InteractionMode.SET_SCALE_LINE_END and \
                   self._scale_line_point1_scene is not None and \
                   self._current_mouse_scene_pos is not None:
                    final_click_scene_pos = self._current_mouse_scene_pos 
                else:
                    final_click_scene_pos = self.mapToScene(self._left_button_press_pos)

                logger.debug(f"Click resolved at scene pos: ({final_click_scene_pos.x():.2f}, {final_click_scene_pos.y():.2f}) in mode {self._current_mode.name}")

                # Allow click if on pixmap OR if ending a scale line (which can end off-pixmap)
                click_is_valid_target = self._pixmap_item.sceneBoundingRect().contains(final_click_scene_pos) or \
                                        (self._current_mode == InteractionMode.SET_SCALE_LINE_END and self._scale_line_point1_scene is not None)

                if click_is_valid_target:
                    if self._current_mode == InteractionMode.SET_SCALE_LINE_START:
                        self.clearTemporaryScaleVisuals() 
                        self._scale_line_point1_scene = final_click_scene_pos
                        self._temp_scale_marker1 = self._draw_temporary_scale_marker(self._scale_line_point1_scene)
                        self.viewport().update() 
                        logger.info(f"Scale line point 1 set at scene: ({final_click_scene_pos.x():.2f}, {final_click_scene_pos.y():.2f})")
                        self.scaleLinePoint1Clicked.emit(final_click_scene_pos.x(), final_click_scene_pos.y())
                        event.accept()
                    
                    elif self._current_mode == InteractionMode.SET_SCALE_LINE_END:
                        if self._scale_line_point1_scene is not None:
                            logger.info(f"Scale line point 2 set at scene: ({final_click_scene_pos.x():.2f}, {final_click_scene_pos.y():.2f})")
                            self.scaleLinePoint2Clicked.emit(
                                self._scale_line_point1_scene.x(), self._scale_line_point1_scene.y(),
                                final_click_scene_pos.x(), final_click_scene_pos.y()
                            )
                        else:
                            logger.warning("SET_SCALE_LINE_END click but _scale_line_point1_scene is None.")
                        event.accept()

                    elif self._current_mode == InteractionMode.SET_ORIGIN:
                        logger.info(f"Click in SET_ORIGIN mode. Emitting originSetRequest.")
                        self.originSetRequest.emit(final_click_scene_pos.x(), final_click_scene_pos.y())
                        event.accept()

                    elif self._current_mode == InteractionMode.NORMAL:
                        modifiers = event.modifiers()
                        if (modifiers == QtCore.Qt.KeyboardModifier.ControlModifier or
                            modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier):
                            logger.info(f"Modified click with modifiers: {modifiers}.")
                            self.modifiedClick.emit(final_click_scene_pos.x(), final_click_scene_pos.y(), modifiers)
                        else:
                            logger.info(f"Standard point click.")
                            self.pointClicked.emit(final_click_scene_pos.x(), final_click_scene_pos.y())
                        event.accept()
                    else:
                        super().mouseReleaseEvent(event)
                else: 
                    logger.debug("Click was outside pixmap bounds and not ending a scale line. Ignoring for point/line definition.")
                    if self._is_snapping_active:
                        self._is_snapping_active = False
                        self.viewport().update() 
                    super().mouseReleaseEvent(event)
            else: 
                if self._is_snapping_active:
                    self._is_snapping_active = False
                    self.viewport().update()
                super().mouseReleaseEvent(event)
            
            if self._current_mode == InteractionMode.NORMAL:
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            elif self._current_mode in [InteractionMode.SET_ORIGIN, InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END]:
                self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            
            self._left_button_press_pos = None
            self._last_pan_point = None
            
        else: 
            super().mouseReleaseEvent(event)