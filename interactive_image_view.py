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
    NORMAL = auto()       # Standard panning, track clicking, point adding
    SET_ORIGIN = auto()   # Next click sets the coordinate system origin
    # --- NEW INTERACTION MODES ---
    SET_SCALE_LINE_START = auto() # Next click sets the first point of the scale line
    SET_SCALE_LINE_END = auto()   # Next click sets the second point of the scale line

class InteractiveImageView(QtWidgets.QGraphicsView):
    """
    A customized QGraphicsView for displaying and interacting with video frames.
    # ... (rest of the docstring can remain mostly the same) ...
    """
    # --- Signals ---
    pointClicked = QtCore.Signal(float, float) # Standard click (scene coords)
    frameStepRequested = QtCore.Signal(int) # Emitted for normal mouse wheel scroll (+1/-1)
    modifiedClick = QtCore.Signal(float, float, QtCore.Qt.KeyboardModifiers) # Click with modifiers (scene coords, mods)
    originSetRequest = QtCore.Signal(float, float) # Emitted when clicking in Set Origin mode (scene coords)
    sceneMouseMoved = QtCore.Signal(float, float) # Emits scene (x, y) or (-1, -1) if off image
    viewTransformChanged = QtCore.Signal() # Emitted when zoom/pan changes view scale

    # --- NEW SIGNALS FOR SCALE LINE DEFINITION ---
    scaleLinePoint1Clicked = QtCore.Signal(float, float) # scene_x, scene_y of the first point
    scaleLinePoint2Clicked = QtCore.Signal(float, float, float, float) # x1, y1, x2, y2 of the line

    # --- Instance Variables ---
    _scene: QtWidgets.QGraphicsScene
    _pixmap_item: Optional[QtWidgets.QGraphicsPixmapItem] # The main video frame item
    _initial_load: bool # Flag for first pixmap load to auto-fit

    # Panning/Clicking state
    _is_panning: bool
    _is_potential_pan: bool
    _left_button_press_pos: Optional[QtCore.QPoint]
    _last_pan_point: Optional[QtCore.QPoint]

    # Zoom limits
    _min_scale: float
    _max_scale: float

    # Overlay Buttons
    zoomInButton: QtWidgets.QPushButton
    zoomOutButton: QtWidgets.QPushButton
    resetViewButton: QtWidgets.QPushButton

    _current_mode: InteractionMode
    _scale_bar_widget: ScaleBarWidget
    _info_overlay_widget: InfoOverlayWidget


    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initializes the view, scene, interaction settings, overlay buttons, and scale bar."""
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

        # --- INITIALIZE NEW SCALE LINE VARIABLES ---
        self._scale_line_point1_scene: Optional[QtCore.QPointF] = None
        self._current_mouse_scene_pos: Optional[QtCore.QPointF] = None
        self._temp_scale_marker1: Optional[QtWidgets.QGraphicsEllipseItem] = None
        self._temp_scale_visuals_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 180) # Green, slightly transparent

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
        
        # Initialize ScaleBarWidget
        self._scale_bar_widget = ScaleBarWidget(self)
        self._scale_bar_widget.setVisible(False)
        logger.debug("ScaleBarWidget created and initially hidden.")

        # --- NEW: Initialize InfoOverlayWidget ---
        self._info_overlay_widget = InfoOverlayWidget(self)
        self._info_overlay_widget.setVisible(False) # Will be shown when video loads
        logger.debug("InfoOverlayWidget created and initially hidden.")
        # --- END NEW ---

        logger.info("InteractiveImageView initialization complete.")


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
        z_value = 12

        line_pen = QtGui.QPen(line_color, pen_width)
        line_pen.setCosmetic(True)
        line_pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)

        line_item = QtWidgets.QGraphicsLineItem(p1x, p1y, p2x, p2y)
        line_item.setPen(line_pen)
        line_item.setZValue(z_value)
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
                tick_item1.setZValue(z_value)
                self._scene.addItem(tick_item1)

                tick2_p1x = p2x + norm_perp_dx * half_tick_length
                tick2_p1y = p2y + norm_perp_dy * half_tick_length
                tick2_p2x = p2x - norm_perp_dx * half_tick_length
                tick2_p2y = p2y - norm_perp_dy * half_tick_length
                tick_item2 = QtWidgets.QGraphicsLineItem(tick2_p1x, tick2_p1y, tick2_p2x, tick2_p2y)
                tick_item2.setPen(line_pen)
                tick_item2.setZValue(z_value)
                self._scene.addItem(tick_item2)
        else:
            if not show_ticks:
                 item_brush = QtGui.QBrush(line_color)
                 marker_radius = max(1.0, pen_width / 2.0)
                 for px, py in [(p1x, p1y), (p2x, p2y)]:
                    dot_marker = QtWidgets.QGraphicsEllipseItem(px - marker_radius, py - marker_radius, 2 * marker_radius, 2 * marker_radius)
                    dot_marker.setPen(QtGui.QPen(line_color, 0.5))
                    dot_marker.setBrush(item_brush)
                    dot_marker.setZValue(z_value)
                    self._scene.addItem(dot_marker)

        text_item = QtWidgets.QGraphicsSimpleTextItem(length_text)
        text_item.setBrush(QtGui.QBrush(text_color))
        font = text_item.font()
        font.setPointSize(font_size)
        text_item.setFont(font)
        text_item.setZValue(z_value)

        local_text_rect = text_item.boundingRect()
        text_width = local_text_rect.width()
        text_height = local_text_rect.height()

        text_item.setTransformOriginPoint(text_width / 2, text_height / 2)

        line_mid_x = (p1x + p2x) / 2
        line_mid_y = (p1y + p2y) / 2
        
        dx_text_place = p2x - p1x # Use a different variable name to avoid conflict if line_length_for_norm wasn't set
        dy_text_place = p2y - p1y
        line_length_text_place = math.sqrt(dx_text_place*dx_text_place + dy_text_place*dy_text_place)


        if line_length_text_place < 1e-6:
            text_item.setPos(p1x + 2, p1y - text_height - 2)
            self._scene.addItem(text_item)
            logger.debug(f"Drew scale line text '{length_text}' for zero-length line at {text_item.pos()}.")
            return

        line_angle_rad = math.atan2(dy_text_place, dx_text_place)
        line_angle_deg = math.degrees(line_angle_rad)

        initial_text_x = line_mid_x - (text_width / 2)
        initial_text_y = line_mid_y - (text_height / 2)
        text_item.setPos(initial_text_x, initial_text_y)

        text_rotation_deg = line_angle_deg
        if text_rotation_deg > 90: text_rotation_deg -= 180
        elif text_rotation_deg < -90: text_rotation_deg += 180
        text_item.setRotation(text_rotation_deg)

        desired_gap_pixels = 3
        shift_magnitude = (text_height / 2) + desired_gap_pixels
        
        perp_dx1 = -dy_text_place / line_length_text_place
        perp_dy1 = dx_text_place / line_length_text_place

        img_center = self.sceneRect().center()
        
        test_pos1_x = line_mid_x + perp_dx1 * shift_magnitude
        test_pos1_y = line_mid_y + perp_dy1 * shift_magnitude
        dist_sq1 = (test_pos1_x - img_center.x())**2 + (test_pos1_y - img_center.y())**2
        
        test_pos2_x = line_mid_x - perp_dx1 * shift_magnitude
        test_pos2_y = line_mid_y - perp_dy1 * shift_magnitude
        dist_sq2 = (test_pos2_x - img_center.x())**2 + (test_pos2_y - img_center.y())**2

        shift_direction_dx = perp_dx1
        shift_direction_dy = perp_dy1
        if dist_sq2 < dist_sq1:
            shift_direction_dx = -perp_dx1
            shift_direction_dy = -perp_dy1
            
        shift_x = shift_direction_dx * shift_magnitude
        shift_y = shift_direction_dy * shift_magnitude

        text_item.moveBy(shift_x, shift_y)
        
        self._scene.addItem(text_item)
        logger.debug(f"Drew scale line text '{length_text}'. Final Pos: {text_item.pos()}, Shift: ({shift_x:.1f}, {shift_y:.1f}), Ticks shown: {show_ticks}")


    def clearOverlay(self) -> None:
        if not self._scene:
            logger.error("clearOverlay called but scene does not exist.")
            return
        logger.debug("Clearing overlay graphics items...")

        items_to_remove: List[QtWidgets.QGraphicsItem] = []
        for item in self._scene.items():
             # Check for _temp_scale_marker2 and _temp_scale_line attributes before comparing
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
                if item.scene() == self._scene:
                     self._scene.removeItem(item)
                     num_removed += 1
            except Exception as e:
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
        marker_size = 6.0
        marker = QtWidgets.QGraphicsEllipseItem(
            scene_pos.x() - marker_size / 2,
            scene_pos.y() - marker_size / 2,
            marker_size, marker_size
        )
        marker.setPen(QtGui.QPen(self._temp_scale_visuals_color, 1.5))
        marker.setBrush(self._temp_scale_visuals_color)
        marker.setZValue(20)
        self._scene.addItem(marker)
        return marker

    def drawForeground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        super().drawForeground(painter, rect)

        if self._current_mode == InteractionMode.SET_SCALE_LINE_END and \
           self._scale_line_point1_scene is not None:

            p1_scene = self._scale_line_point1_scene
            p1_viewport_mapped = self.mapFromScene(p1_scene)
            current_mouse_viewport_pos = self.viewport().mapFromGlobal(QtGui.QCursor.pos())

            if self.viewport().rect().contains(current_mouse_viewport_pos):
                painter.save()
                painter.setTransform(QtGui.QTransform()) # Ensure identity transform

                pen = QtGui.QPen(self._temp_scale_visuals_color, 1.5)
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(p1_viewport_mapped, current_mouse_viewport_pos)
                
                painter.restore()

    def clearTemporaryScaleVisuals(self) -> None:
        logger.debug("Clearing temporary scale visuals.")
        if self._temp_scale_marker1 and self._temp_scale_marker1.scene() == self._scene:
            self._scene.removeItem(self._temp_scale_marker1)
            self._temp_scale_marker1 = None
    
        self._scale_line_point1_scene = None
        self._current_mouse_scene_pos = None
    
        self.viewport().update()
        logger.debug("Temporary scale visuals cleared and state reset.")

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
            elif visible:
                 self._update_overlay_widget_positions()

    def update_scale_bar_dimensions(self, m_per_px_scene: Optional[float]) -> None:
        if hasattr(self, '_scale_bar_widget') and self._scale_bar_widget:
            if not self._pixmap_item or not self.sceneRect().isValid():
                self._scale_bar_widget.setVisible(False)
                return

            current_view_scale_factor = self.transform().m11()
            parent_view_width = self.viewport().width()

            self._scale_bar_widget.update_dimensions(
                m_per_px_scene,
                current_view_scale_factor,
                parent_view_width
            )
            if self._scale_bar_widget.isVisible():
                 self._update_overlay_widget_positions()

    def get_current_view_scale_factor(self) -> float:
        return self.transform().m11()

    def get_min_view_scale(self) -> float:
        if self._pixmap_item and self.sceneRect().isValid():
            self._calculate_zoom_limits()
        return self._min_scale

    def get_max_view_scale(self) -> float:
        return self._max_scale

    def set_info_overlay_video_data(self, filename: str, total_frames: int, total_duration_ms: float) -> None:
        if self._info_overlay_widget:
            self._info_overlay_widget.update_video_info(filename, total_frames, total_duration_ms)
            if self._pixmap_item and not self._info_overlay_widget.isVisible():
                 self._info_overlay_widget.setVisible(True)
                 self._update_overlay_widget_positions()

    def set_info_overlay_current_frame_time(self, frame_idx: int, time_ms: float) -> None:
        if self._info_overlay_widget:
            self._info_overlay_widget.update_current_frame_time(frame_idx, time_ms)

    def refresh_info_overlay_appearance(self) -> None:
        if self._info_overlay_widget:
            self._info_overlay_widget.update_appearance_from_settings()
            if self._info_overlay_widget.isVisible():
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
                self._is_panning = False
                
                if self._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END, InteractionMode.SET_ORIGIN, InteractionMode.NORMAL]:
                    event.accept()
                    return
            else:
                logger.debug("Left click outside pixmap bounds.")
                self._is_potential_pan = False
                self._left_button_press_pos = None
                return

        super().mousePressEvent(event)

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
            
            if current_scene_pos_for_move is not None:
                if self._current_mouse_scene_pos != current_scene_pos_for_move:
                    self._current_mouse_scene_pos = current_scene_pos_for_move
                    self.viewport().update()
            else:
                if self._current_mouse_scene_pos is not None:
                    self._current_mouse_scene_pos = None
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
                click_scene_pos: QtCore.QPointF = self.mapToScene(self._left_button_press_pos)
                logger.debug(f"Click resolved at scene pos: ({click_scene_pos.x():.2f}, {click_scene_pos.y():.2f}) in mode {self._current_mode.name}")

                if self._pixmap_item.sceneBoundingRect().contains(click_scene_pos):
                    if self._current_mode == InteractionMode.SET_SCALE_LINE_START:
                        self.clearTemporaryScaleVisuals()
                        self._scale_line_point1_scene = click_scene_pos
                        self._temp_scale_marker1 = self._draw_temporary_scale_marker(self._scale_line_point1_scene)
                        self._current_mouse_scene_pos = click_scene_pos
                        self.viewport().update()
                        logger.info(f"Scale line point 1 set at scene: ({click_scene_pos.x():.2f}, {click_scene_pos.y():.2f})")
                        self.scaleLinePoint1Clicked.emit(click_scene_pos.x(), click_scene_pos.y())
                        event.accept()
                    
                    elif self._current_mode == InteractionMode.SET_SCALE_LINE_END:
                        if self._scale_line_point1_scene is not None:
                            final_p2_scene_pos = click_scene_pos 
                            logger.info(f"Scale line point 2 set at scene: ({final_p2_scene_pos.x():.2f}, {final_p2_scene_pos.y():.2f})")
                            self.scaleLinePoint2Clicked.emit(
                                self._scale_line_point1_scene.x(), self._scale_line_point1_scene.y(),
                                final_p2_scene_pos.x(), final_p2_scene_pos.y()
                            )
                            self._current_mouse_scene_pos = None
                            self.viewport().update()
                        else:
                            logger.warning("SET_SCALE_LINE_END click but _scale_line_point1_scene is None.")
                        event.accept()

                    elif self._current_mode == InteractionMode.SET_ORIGIN:
                        logger.info(f"Click in SET_ORIGIN mode. Emitting originSetRequest.")
                        self.originSetRequest.emit(click_scene_pos.x(), click_scene_pos.y())
                        event.accept()

                    elif self._current_mode == InteractionMode.NORMAL:
                        modifiers = event.modifiers()
                        if (modifiers == QtCore.Qt.KeyboardModifier.ControlModifier or
                            modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier):
                            logger.info(f"Modified click with modifiers: {modifiers}.")
                            self.modifiedClick.emit(click_scene_pos.x(), click_scene_pos.y(), modifiers)
                        else:
                            logger.info(f"Standard point click.")
                            self.pointClicked.emit(click_scene_pos.x(), click_scene_pos.y())
                        event.accept()
                    else:
                        super().mouseReleaseEvent(event)
                else:
                    logger.debug("Click was outside pixmap bounds. Ignoring for point/line definition.")
                    super().mouseReleaseEvent(event)
            else:
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