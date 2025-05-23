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
        self._temp_scale_visuals_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 180)

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
        if not hasattr(self, '_scale_bar_widget') or not self._scale_bar_widget: # Keep this check
            logger.warning("_update_overlay_widget_positions called before scale bar widget created.")
            # return # Don't return yet, info overlay might still need update

        # --- NEW: Check for InfoOverlayWidget ---
        if not hasattr(self, '_info_overlay_widget') or not self._info_overlay_widget:
            logger.warning("_update_overlay_widget_positions called before info overlay widget created.")
            # return # Allow scale bar and buttons to update if info overlay is missing

        margin: int = 10
        vp_rect = self.viewport().rect() # Get viewport rect once
        vp_width: int = vp_rect.width()
        vp_height: int = vp_rect.height()

        # Position Overlay Buttons
        button_width: int = self.zoomInButton.width()
        button_height: int = self.zoomInButton.height()
        spacing: int = 5
        x_pos_buttons: int = vp_width - button_width - margin
        self.zoomInButton.move(x_pos_buttons, margin)
        self.zoomOutButton.move(x_pos_buttons, margin + button_height + spacing)
        self.resetViewButton.move(x_pos_buttons, margin + 2 * (button_height + spacing))

        # Position ScaleBarWidget
        if self._scale_bar_widget and self._scale_bar_widget.isVisible():
            sb_width: int = self._scale_bar_widget.width()
            sb_height: int = self._scale_bar_widget.height()
            x_pos_sb: int = vp_width - sb_width - margin
            y_pos_sb: int = vp_height - sb_height - margin
            self._scale_bar_widget.move(x_pos_sb, y_pos_sb)
            logger.debug(f"Scale bar positioned at ({x_pos_sb}, {y_pos_sb}), size: {self._scale_bar_widget.size()}")

        # --- NEW: Position and Resize InfoOverlayWidget ---
        if self._info_overlay_widget: # Check if it exists
            # The InfoOverlayWidget should span the entire viewport to draw in corners
            self._info_overlay_widget.setGeometry(vp_rect)
            if self._info_overlay_widget.isVisible(): # Ensure it repaints if visible
                self._info_overlay_widget.update()
            logger.debug(f"InfoOverlayWidget geometry set to viewport: {vp_rect}")
        # --- END NEW ---

    def _ensure_overlay_widgets_updated_on_show(self, buttons_visible: bool) -> None:
        if not hasattr(self, 'zoomInButton') or not self.zoomInButton:
             logger.warning("_ensure_overlay_widgets_updated_on_show called before overlay buttons created.")
             return

        logger.debug(f"Setting overlay buttons visible: {buttons_visible}")
        if buttons_visible:
            self._update_overlay_widget_positions() # This will now handle info_overlay_widget too
            self.zoomInButton.show()
            self.zoomOutButton.show()
            self.resetViewButton.show()
        else:
            self.zoomInButton.hide()
            self.zoomOutButton.hide()
            self.resetViewButton.hide()

        # ScaleBarWidget visibility and position are handled by its own logic
        # and _update_overlay_widget_positions if it's visible.

        # --- NEW: Handle InfoOverlayWidget visibility based on pixmap presence ---
        # The InfoOverlayWidget itself is made visible/hidden based on whether a pixmap is loaded,
        # its internal elements are toggled by settings.
        if self._info_overlay_widget:
            # Show if buttons are implies a pixmap is loaded; hide if buttons are hidden (no pixmap)
            if buttons_visible != self._info_overlay_widget.isVisible():
                 self._info_overlay_widget.setVisible(buttons_visible)
                 logger.debug(f"InfoOverlayWidget visibility set to: {buttons_visible}")
            if buttons_visible: # If becoming visible, ensure its position/size is correct
                self._update_overlay_widget_positions()
        # --- END NEW ---

    def _zoom(self, factor: float, mouse_viewport_pos: Optional[QtCore.QPoint] = None) -> None: # Keep mouse_viewport_pos for now, though not directly used in this version
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
            
            # Store the original anchor
            original_anchor = self.transformationAnchor()
            
            # Try to force Qt to re-evaluate the mouse position for AnchorUnderMouse
            # by temporarily changing the anchor.
            # This can sometimes clear cached anchor points.
            self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
            self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            # Ensure the viewport has a chance to process any pending events that might update mouse pos
            # QtWidgets.QApplication.processEvents() # Usually not needed and can cause other issues, but as a last resort for testing.

            logger.debug(f"Applying scale factor {actual_zoom_factor:.4f} (Target: {target_scale:.4f}) using AnchorUnderMouse.")
            self.scale(actual_zoom_factor, actual_zoom_factor)
            
            # No manual scrollbar adjustment here, rely purely on AnchorUnderMouse
            
            self.viewTransformChanged.emit()
        else:
            logger.debug("Target scale close to current scale or limits reached. No zoom applied.")



    @QtCore.Slot()
    def _zoomIn(self) -> None:
        logger.debug("Zoom In button clicked.")
        zoom_in_factor: float = 1.3
        viewport_center = self.viewport().rect().center() # Get current viewport center
        self._zoom(zoom_in_factor, viewport_center)

    @QtCore.Slot()
    def _zoomOut(self) -> None:
        logger.debug("Zoom Out button clicked.")
        zoom_out_factor: float = 1.0 / 1.3
        viewport_center = self.viewport().rect().center() # Get current viewport center
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

            self._ensure_overlay_widgets_updated_on_show(True) # This handles all overlays now
            if self._info_overlay_widget: # Ensure info overlay is visible
                self._info_overlay_widget.setVisible(True)

            if transform_changed_by_set_pixmap and not is_initial :
                # This condition was a bit complex, simplifying slightly: emit if a non-initial
                # setPixmap operation potentially changed the transform (either by restoring or resetting).
                self.viewTransformChanged.emit()
        else:
             logger.info("Invalid or null pixmap provided. Clearing scene rect and hiding buttons/overlays.")
             self.setSceneRect(QtCore.QRectF())
             self._min_scale = 0.01
             self._max_scale = config.MAX_ABS_SCALE
             self._ensure_overlay_widgets_updated_on_show(False) # Hides buttons
             if self._scale_bar_widget: # Explicitly hide scale bar
                self._scale_bar_widget.setVisible(False)
             if self._info_overlay_widget: # Explicitly hide info overlay
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
        """
        Draws the defined scale line, end markers (now potentially ticks), and length text
        onto the scene. The text is centered along the line's length and offset
        perpendicularly, placed on the side of the line closer to the image center.
        End markers are drawn as ticks if the preference is set.
        """
        if not self._scene or not line_data:
            logger.warning("Cannot draw persistent scale line: Scene or line_data missing.")
            return
        if not self.sceneRect().isValid() or self.sceneRect().isEmpty():
            logger.warning("Cannot draw persistent scale line: SceneRect is invalid or empty.")
            return

        p1x, p1y, p2x, p2y = line_data
        z_value = 12 # Or a configurable Z-value

        line_pen = QtGui.QPen(line_color, pen_width)
        line_pen.setCosmetic(True)
        line_pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap) # Use flat caps for precise line ends

        # 1. Draw Main Line
        line_item = QtWidgets.QGraphicsLineItem(p1x, p1y, p2x, p2y)
        line_item.setPen(line_pen)
        line_item.setZValue(z_value)
        self._scene.addItem(line_item)

        # --- NEW: Retrieve tick preferences ---
        show_ticks = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_SHOW_TICKS)
        tick_length_factor = settings_manager.get_setting(settings_manager.KEY_FEATURE_SCALE_LINE_TICK_LENGTH_FACTOR)
        
        # Calculate tick length based on pen_width and factor
        # The actual tick will be drawn half on each side of the main line's endpoint,
        # so the 'tick_length' here is the total length of the perpendicular tick line.
        tick_total_length = pen_width * tick_length_factor
        half_tick_length = tick_total_length / 2.0

        # 2. Draw End Ticks (if enabled)
        if show_ticks and tick_total_length > 0:
            dx = p2x - p1x
            dy = p2y - p1y
            line_length_for_norm = math.sqrt(dx*dx + dy*dy)

            if line_length_for_norm > 1e-6: # Avoid division by zero for zero-length lines
                # Normalized perpendicular vector (-dy/L, dx/L)
                norm_perp_dx = -dy / line_length_for_norm
                norm_perp_dy = dx / line_length_for_norm

                # Tick at point 1 (p1x, p1y)
                tick1_p1x = p1x + norm_perp_dx * half_tick_length
                tick1_p1y = p1y + norm_perp_dy * half_tick_length
                tick1_p2x = p1x - norm_perp_dx * half_tick_length
                tick1_p2y = p1y - norm_perp_dy * half_tick_length
                tick_item1 = QtWidgets.QGraphicsLineItem(tick1_p1x, tick1_p1y, tick1_p2x, tick1_p2y)
                tick_item1.setPen(line_pen) # Use the same pen as the main line
                tick_item1.setZValue(z_value)
                self._scene.addItem(tick_item1)

                # Tick at point 2 (p2x, p2y)
                tick2_p1x = p2x + norm_perp_dx * half_tick_length
                tick2_p1y = p2y + norm_perp_dy * half_tick_length
                tick2_p2x = p2x - norm_perp_dx * half_tick_length
                tick2_p2y = p2y - norm_perp_dy * half_tick_length
                tick_item2 = QtWidgets.QGraphicsLineItem(tick2_p1x, tick2_p1y, tick2_p2x, tick2_p2y)
                tick_item2.setPen(line_pen) # Use the same pen as the main line
                tick_item2.setZValue(z_value)
                self._scene.addItem(tick_item2)
        else:
            # Fallback or alternative: Draw simple dots/circles if ticks are disabled or zero length
            # This replaces the previous default circle markers if ticks are off
            # You might want to remove this if no end markers are desired when ticks are off.
            if not show_ticks: # Only draw circles if ticks are explicitly off
                 item_brush = QtGui.QBrush(line_color)
                 marker_radius = max(1.0, pen_width / 2.0) # Smaller, subtle dot
                 for px, py in [(p1x, p1y), (p2x, p2y)]:
                    dot_marker = QtWidgets.QGraphicsEllipseItem(px - marker_radius, py - marker_radius, 2 * marker_radius, 2 * marker_radius)
                    dot_marker.setPen(QtGui.QPen(line_color, 0.5)) # Very thin or no border
                    dot_marker.setBrush(item_brush)
                    dot_marker.setZValue(z_value)
                    self._scene.addItem(dot_marker)


        # 3. Prepare Text Item (largely unchanged)
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

        # 4. Line Properties for Text Placement (unchanged)
        line_mid_x = (p1x + p2x) / 2
        line_mid_y = (p1y + p2y) / 2
        # dx, dy, line_length already calculated if ticks were drawn, reuse or recalc if not
        if not (show_ticks and tick_total_length > 0 and line_length_for_norm > 1e-6) : # Recalculate if not done for ticks
            dx = p2x - p1x
            dy = p2y - p1y
            line_length = math.sqrt(dx*dx + dy*dy)
        else:
            line_length = line_length_for_norm # Reuse if calculated for ticks

        if line_length < 1e-6:
            # If line has no length, just place text at p1, perhaps with a small offset
            text_item.setPos(p1x + 2, p1y - text_height - 2) # Avoid covering point itself
            self._scene.addItem(text_item)
            logger.debug(f"Drew scale line text '{length_text}' for zero-length line at {text_item.pos()}.")
            return

        line_angle_rad = math.atan2(dy, dx)
        line_angle_deg = math.degrees(line_angle_rad)

        # 5. Initial Position & Rotation for Text (unchanged)
        initial_text_x = line_mid_x - (text_width / 2)
        initial_text_y = line_mid_y - (text_height / 2)
        text_item.setPos(initial_text_x, initial_text_y)

        text_rotation_deg = line_angle_deg
        if text_rotation_deg > 90: text_rotation_deg -= 180
        elif text_rotation_deg < -90: text_rotation_deg += 180
        text_item.setRotation(text_rotation_deg)

        # 6. Calculate Perpendicular Shift for Text (unchanged)
        desired_gap_pixels = 3
        shift_magnitude = (text_height / 2) + desired_gap_pixels
        
        perp_dx1 = -dy / line_length
        perp_dy1 = dx / line_length

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
             if item != self._pixmap_item and \
                item != self._temp_scale_marker1 and \
                item != self._temp_scale_marker2 and \
                item != self._temp_scale_line: # Don't remove temp scale items here
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

    # --- START OF NEW/MODIFIED CODE BLOCK FOR SET_INTERACTION_MODE ---
    def set_interaction_mode(self, mode: InteractionMode) -> None:
        """Sets the current interaction mode and updates the cursor."""
        if self._current_mode != mode:
            logger.info(f"Changing interaction mode from {self._current_mode.name} to {mode.name}")
            
            # If exiting a scale definition mode, clear temporary visuals
            if self._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END] and \
               mode == InteractionMode.NORMAL:
                self.clearTemporaryScaleVisuals()

            self._current_mode = mode
            
            # Update cursor based on mode
            if mode == InteractionMode.SET_ORIGIN:
                 self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            elif mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END]:
                 self.setCursor(QtCore.Qt.CursorShape.CrossCursor) # Use crosshair for scale line points
            else: # InteractionMode.NORMAL
                 self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        else:
             logger.debug(f"Interaction mode already set to {mode.name}")
    # --- END OF NEW/MODIFIED CODE BLOCK FOR SET_INTERACTION_MODE ---

    # --- START OF NEW METHODS FOR TEMPORARY SCALE VISUALS ---
    def _draw_temporary_scale_marker(self, scene_pos: QtCore.QPointF) -> QtWidgets.QGraphicsEllipseItem:
        """Draws a temporary marker at the given scene position."""
        marker_size = 6.0 # Diameter of the marker
        marker = QtWidgets.QGraphicsEllipseItem(
            scene_pos.x() - marker_size / 2,
            scene_pos.y() - marker_size / 2,
            marker_size, marker_size
        )
        marker.setPen(QtGui.QPen(self._temp_scale_visuals_color, 1.5))
        marker.setBrush(self._temp_scale_visuals_color)
        marker.setZValue(20) # Ensure it's above other overlays
        self._scene.addItem(marker)
        return marker


    def drawForeground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        super().drawForeground(painter, rect)

        # Red rectangle test (keep for now, but its interpretation changes if painter is pre-transformed)
        painter.save()
        painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.red, 2))
        painter.drawRect(10, 10, 50, 50)
        painter.restore()

        if self._current_mode == InteractionMode.SET_SCALE_LINE_END and \
           self._scale_line_point1_scene is not None:

            p1_scene = self._scale_line_point1_scene
            # These are your calculated logical viewport coordinates
            p1_viewport_mapped = self.mapFromScene(p1_scene)
            current_mouse_viewport_pos = self.viewport().mapFromGlobal(QtGui.QCursor.pos())

            # Your logging for these coordinates is useful here to confirm they are as expected.

            if self.viewport().rect().contains(current_mouse_viewport_pos): # Check if mouse is in viewport
                painter.save() # Save the painter's current (potentially problematic) state

                # *** CRITICAL STEP: Reset the painter's transform to identity ***
                # This ensures that the p1_viewport_mapped and current_mouse_viewport_pos
                # are drawn directly as logical viewport pixel coordinates without further transformation.
                painter.setTransform(QtGui.QTransform())

                # Now proceed with drawing
                pen = QtGui.QPen(self._temp_scale_visuals_color, 1.5)
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(p1_viewport_mapped, current_mouse_viewport_pos)

                # Diagnostic dots for P1
                painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.yellow, 3))
                painter.setBrush(QtCore.Qt.GlobalColor.yellow)
                painter.drawEllipse(p1_viewport_mapped, 3, 3)

                # Diagnostic dot for P2
                painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.cyan, 3))
                painter.setBrush(QtCore.Qt.GlobalColor.cyan)
                painter.drawEllipse(current_mouse_viewport_pos, 3, 3)
                
                painter.restore() # Restore the painter's original state (with its pre-existing transform)


    def clearTemporaryScaleVisuals(self) -> None:
        logger.debug("Clearing temporary scale visuals.")
        if self._temp_scale_marker1 and self._temp_scale_marker1.scene() == self._scene:
            self._scene.removeItem(self._temp_scale_marker1) # Remove from scene
            self._temp_scale_marker1 = None # Clear reference
    
        self._scale_line_point1_scene = None
        self._current_mouse_scene_pos = None # Ensure this is reset
    
        self.viewport().update() # Request repaint to clear foreground
        logger.debug("Temporary scale visuals cleared and state reset.")

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self._pixmap_item:
            super().wheelEvent(event)
            return

        modifiers: QtCore.Qt.KeyboardModifiers = event.modifiers()
        angle_delta: QtCore.QPoint = event.angleDelta()
        mouse_pos_in_viewport: QtCore.QPoint = event.position().toPoint() # Get mouse pos from event

        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            logger.debug(f"Ctrl+Scroll detected: Performing zoom at viewport pos {mouse_pos_in_viewport}.")
            scroll_amount: int = angle_delta.y()
            if scroll_amount == 0:
                event.ignore()
                return
            zoom_factor_base: float = 1.15
            if scroll_amount > 0:
                self._zoom(zoom_factor_base, mouse_pos_in_viewport) # Pass mouse_pos
            else:
                self._zoom(1.0 / zoom_factor_base, mouse_pos_in_viewport) # Pass mouse_pos
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

        # _update_overlay_widget_positions() will now handle sizing and positioning of InfoOverlayWidget
        self._update_overlay_widget_positions()
        
        if not view_reset_called: # Only emit if resetView() didn't already do it.
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
        """
        Returns the minimum scale factor for the view (fit to view).
        This corresponds to 100% zoom out.
        """
        # Ensure _min_scale is up-to-date if called before a pixmap is fully processed
        # or if the viewport changed without a pixmap update.
        if self._pixmap_item and self.sceneRect().isValid():
            self._calculate_zoom_limits() # Recalculate to be safe, though usually set on pixmap/resize
        return self._min_scale

    def get_max_view_scale(self) -> float:
        """
        Returns the maximum allowed scale factor for the view.
        """
        return self._max_scale

    # --- NEW METHODS for InfoOverlayWidget Interaction ---
    def set_info_overlay_video_data(self, filename: str, total_frames: int, total_duration_ms: float) -> None:
        """Passes static video data to the InfoOverlayWidget."""
        if self._info_overlay_widget:
            self._info_overlay_widget.update_video_info(filename, total_frames, total_duration_ms)
            if self._pixmap_item and not self._info_overlay_widget.isVisible():
                 self._info_overlay_widget.setVisible(True) # Ensure visible if video data is set
                 self._update_overlay_widget_positions() # Position it correctly

    def set_info_overlay_current_frame_time(self, frame_idx: int, time_ms: float) -> None:
        """Passes current frame/time data to the InfoOverlayWidget."""
        if self._info_overlay_widget:
            self._info_overlay_widget.update_current_frame_time(frame_idx, time_ms)
            # No need to change visibility here, paintEvent will handle if already visible

    def refresh_info_overlay_appearance(self) -> None:
        """Tells the InfoOverlayWidget to reload its appearance settings and repaint."""
        if self._info_overlay_widget:
            self._info_overlay_widget.update_appearance_from_settings()
            if self._info_overlay_widget.isVisible(): # Ensure repaint if visible
                self._info_overlay_widget.update()
            logger.debug("InfoOverlayWidget appearance refreshed.")
    # --- END NEW METHODS ---

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        button: QtCore.Qt.MouseButton = event.button()
        logger.debug(f"Mouse press event: Button={button}, Pos={event.pos()}, Mode={self._current_mode.name}")

        if button == QtCore.Qt.MouseButton.LeftButton and self._pixmap_item:
            # Check if click is within pixmap bounds
            scene_pos = self.mapToScene(event.pos())
            if self._pixmap_item.sceneBoundingRect().contains(scene_pos):
                self._left_button_press_pos = event.pos() # Store viewport press position for resolving click vs. pan
                self._is_potential_pan = True
                self._is_panning = False # Reset panning state for this new press
                
                # If in a line drawing mode, accept the event to handle in release/move
                if self._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END, InteractionMode.SET_ORIGIN]:
                    event.accept()
                    return
                # For NORMAL mode, also accept if we might start a pan or handle a click
                elif self._current_mode == InteractionMode.NORMAL:
                    event.accept()
                    return
            else:
                # Click outside pixmap, let base class handle or ignore
                logger.debug("Left click outside pixmap bounds.")
                # Reset potential pan if click is outside
                self._is_potential_pan = False
                self._left_button_press_pos = None
                # super().mousePressEvent(event) # Allow deselection etc. if scene configured for it
                return # Usually, we don't want unhandled clicks outside to do much

        super().mousePressEvent(event) # For other buttons or if no pixmap


    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        viewport_pos = event.pos()
        scene_x, scene_y = -1.0, -1.0
        current_scene_pos_for_move: Optional[QtCore.QPointF] = None

        if self._pixmap_item:
            current_scene_pos_for_move = self.mapToScene(viewport_pos)
            if self._pixmap_item.sceneBoundingRect().contains(current_scene_pos_for_move):
                scene_x, scene_y = current_scene_pos_for_move.x(), current_scene_pos_for_move.y()
            else: # Mouse is off the pixmap item
                current_scene_pos_for_move = None # Don't use off-image coords

        self.sceneMouseMoved.emit(scene_x, scene_y) # Emit regardless of pixmap containment for general cursor tracking

        # Handle Panning Initiation
        if self._is_potential_pan and self._left_button_press_pos is not None and \
           (event.buttons() & QtCore.Qt.MouseButton.LeftButton): # Ensure left button is still pressed
            distance_moved = (viewport_pos - self._left_button_press_pos).manhattanLength()
            if distance_moved >= config.DRAG_THRESHOLD:
                # Pan is allowed in these modes
                if self._current_mode in [InteractionMode.NORMAL, InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END, InteractionMode.SET_ORIGIN]:
                    logger.debug(f"Drag threshold ({config.DRAG_THRESHOLD}px) exceeded. Starting pan in mode {self._current_mode.name}.")
                    self._is_panning = True
                
                self._is_potential_pan = False # No longer a potential click, it's a pan
                if self._is_panning:
                    self._last_pan_point = viewport_pos
                    self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                    # If we start panning during line definition, clear dynamic line related state
                    if self._current_mode == InteractionMode.SET_SCALE_LINE_END:
                        self._current_mouse_scene_pos = None
                        self.viewport().update() # Erase dynamic line
                    event.accept()
                    return

        # Handle Active Panning
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
        
        # Handle Dynamic Line Drawing if not panning and in correct mode
        if not self._is_panning and \
           self._current_mode == InteractionMode.SET_SCALE_LINE_END and \
           self._scale_line_point1_scene is not None:
            
            if current_scene_pos_for_move is not None: # Mouse is over the pixmap
                if self._current_mouse_scene_pos != current_scene_pos_for_move:
                    self._current_mouse_scene_pos = current_scene_pos_for_move
                    self.viewport().update() # Schedule repaint for drawForeground
            else: # Mouse moved off pixmap
                if self._current_mouse_scene_pos is not None: # If it was previously on, clear it
                    self._current_mouse_scene_pos = None
                    self.viewport().update() # Schedule repaint to remove line
            # event.accept() # Accept if we handled it for line drawing
            # return # Avoid super call if we are managing this specific move event for line drawing

        super().mouseMoveEvent(event) # Call super for other cases or default handling


    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        button: QtCore.Qt.MouseButton = event.button()
        logger.debug(f"Mouse release: Button={button}, Mode={self._current_mode.name}, Panning={self._is_panning}, PotentialPan={self._is_potential_pan}")

        if button == QtCore.Qt.MouseButton.LeftButton:
            was_panning = self._is_panning
            is_click_intent = self._is_potential_pan # True if mouse didn't move enough to start a pan

            # Always reset panning states on left button release
            self._is_panning = False
            self._is_potential_pan = False
            current_cursor_shape = self.cursor().shape() # Preserve current cursor before changing

            if was_panning:
                logger.debug("Panning finished.")
                # Cursor will be reset based on mode below
            elif is_click_intent and self._pixmap_item and self._left_button_press_pos is not None:
                # It's a click action
                # Use the original press position mapped to scene for click accuracy
                click_scene_pos: QtCore.QPointF = self.mapToScene(self._left_button_press_pos)
                logger.debug(f"Click resolved at scene pos: ({click_scene_pos.x():.2f}, {click_scene_pos.y():.2f}) in mode {self._current_mode.name}")

                if self._pixmap_item.sceneBoundingRect().contains(click_scene_pos):
                    if self._current_mode == InteractionMode.SET_SCALE_LINE_START:
                        self.clearTemporaryScaleVisuals() # Clear previous marker/state
                        self._scale_line_point1_scene = click_scene_pos
                        self._temp_scale_marker1 = self._draw_temporary_scale_marker(self._scale_line_point1_scene)
                        self._current_mouse_scene_pos = click_scene_pos # Init for drawForeground
                        self.viewport().update() # Show marker and initial dynamic line (p1 to p1)
                        logger.info(f"Scale line point 1 set at scene: ({click_scene_pos.x():.2f}, {click_scene_pos.y():.2f})")
                        self.scaleLinePoint1Clicked.emit(click_scene_pos.x(), click_scene_pos.y())
                        # The controller is expected to change mode to SET_SCALE_LINE_END
                        event.accept()
                    
                    elif self._current_mode == InteractionMode.SET_SCALE_LINE_END:
                        if self._scale_line_point1_scene is not None:
                            final_p2_scene_pos = click_scene_pos 
                            logger.info(f"Scale line point 2 set at scene: ({final_p2_scene_pos.x():.2f}, {final_p2_scene_pos.y():.2f})")
                            self.scaleLinePoint2Clicked.emit(
                                self._scale_line_point1_scene.x(), self._scale_line_point1_scene.y(),
                                final_p2_scene_pos.x(), final_p2_scene_pos.y()
                            )
                            self._current_mouse_scene_pos = None # Stop dynamic drawing
                            self.viewport().update() # Erase dynamic line from foreground
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
                        super().mouseReleaseEvent(event) # Fallback for unhandled modes
                else: # Click was outside pixmap bounds
                    logger.debug("Click was outside pixmap bounds. Ignoring for point/line definition.")
                    # self.clearTemporaryScaleVisuals() # Optionally clear if definition was in progress
                    # self.set_interaction_mode(InteractionMode.NORMAL) # Optionally reset mode
                    super().mouseReleaseEvent(event)
            else: # Not a pan, not a resolved click (e.g., right click, or error in press state)
                super().mouseReleaseEvent(event)
            
            # Reset cursor based on the *current* mode, which might have been changed by a controller
            # reacting to an emitted signal from the click handling above.
            if self._current_mode == InteractionMode.NORMAL:
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            elif self._current_mode in [InteractionMode.SET_ORIGIN, InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END]:
                self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else: # Fallback
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            
            # Clean up press state variables
            self._left_button_press_pos = None
            self._last_pan_point = None
            
        else: # Other mouse buttons (not left button)
            super().mouseReleaseEvent(event)