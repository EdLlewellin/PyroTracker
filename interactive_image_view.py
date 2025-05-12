# interactive_image_view.py
import math
import logging
from typing import Optional, List, Tuple # Added Tuple
from enum import Enum, auto

from PySide6 import QtCore, QtGui, QtWidgets

import config
from scale_bar_widget import ScaleBarWidget

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

    # --- NEW INSTANCE VARIABLES FOR SCALE LINE DEFINITION ---
    _scale_line_point1_scene: Optional[QtCore.QPointF] = None
    _temp_scale_marker1: Optional[QtWidgets.QGraphicsEllipseItem] = None
    _temp_scale_marker2: Optional[QtWidgets.QGraphicsEllipseItem] = None
    _temp_scale_line: Optional[QtWidgets.QGraphicsLineItem] = None
    _temp_scale_visuals_color: QtGui.QColor = QtGui.QColor("lime") # Color for temp scale markers/line


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

        # --- INITIALIZE NEW SCALE LINE VARIABLES ---
        self._scale_line_point1_scene = None
        self._temp_scale_marker1 = None
        self._temp_scale_marker2 = None
        self._temp_scale_line = None
        # Consider making this color configurable via config.py or settings_manager later
        self._temp_scale_visuals_color = QtGui.QColor(0, 255, 0, 180) # Bright green, slightly transparent

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
            return

        margin: int = 10
        vp_width: int = self.viewport().width()
        vp_height: int = self.viewport().height()

        button_width: int = self.zoomInButton.width()
        button_height: int = self.zoomInButton.height()
        spacing: int = 5

        x_pos_buttons: int = vp_width - button_width - margin
        self.zoomInButton.move(x_pos_buttons, margin)
        self.zoomOutButton.move(x_pos_buttons, margin + button_height + spacing)
        self.resetViewButton.move(x_pos_buttons, margin + 2 * (button_height + spacing))

        if self._scale_bar_widget.isVisible():
            sb_width: int = self._scale_bar_widget.width()
            sb_height: int = self._scale_bar_widget.height()
            x_pos_sb: int = vp_width - sb_width - margin
            y_pos_sb: int = vp_height - sb_height - margin
            self._scale_bar_widget.move(x_pos_sb, y_pos_sb)
            logger.debug(f"Scale bar positioned at ({x_pos_sb}, {y_pos_sb}), size: {self._scale_bar_widget.size()}")


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

        if self._scale_bar_widget and self._scale_bar_widget.isVisible():
            self._update_overlay_widget_positions()


    def _zoom(self, factor: float) -> None:
        if not self._pixmap_item:
            logger.debug("_zoom called but no pixmap item exists.")
            return

        current_scale: float = self.transform().m11()
        logger.debug(f"Zoom requested with factor {factor:.3f}. Current scale: {current_scale:.4f}")

        target_scale: float
        if factor > 1.0:
            target_scale = min(current_scale * factor, self._max_scale)
        else:
            target_scale = max(current_scale * factor, self._min_scale)
        logger.debug(f"Calculated target scale: {target_scale:.4f} (Min: {self._min_scale:.4f}, Max: {self._max_scale:.4f})")

        if not math.isclose(target_scale, current_scale, rel_tol=1e-5):
            actual_zoom: float = target_scale / current_scale
            logger.debug(f"Applying scale factor {actual_zoom:.4f} (Target: {target_scale:.4f})")
            self.scale(actual_zoom, actual_zoom)
            self.viewTransformChanged.emit()
        else:
            logger.debug("Target scale close to current scale or limits reached. No zoom applied.")


    @QtCore.Slot()
    def _zoomIn(self) -> None:
        logger.debug("Zoom In button clicked.")
        zoom_in_factor: float = 1.3
        self._zoom(zoom_in_factor)


    @QtCore.Slot()
    def _zoomOut(self) -> None:
        logger.debug("Zoom Out button clicked.")
        zoom_out_factor: float = 1.0 / 1.3
        self._zoom(zoom_out_factor)


    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        logger.info(f"Setting pixmap. Is null: {pixmap.isNull()}. Size: {pixmap.size()}")
        current_transform: Optional[QtGui.QTransform] = None
        is_initial: bool = self._initial_load
        logger.debug(f"setPixmap called. Initial load flag: {is_initial}")

        if self._pixmap_item and self.sceneRect().isValid() and not is_initial:
            current_transform = self.transform()
            logger.debug(f"Stored previous transform: {current_transform}")

        logger.debug("Clearing graphics scene...")
        self.clearTemporaryScaleVisuals() # Clear any temp scale line before clearing scene
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
            if transform_changed_by_set_pixmap and not is_initial :
                if not (current_transform is not None and math.isclose(clamped_scale, previous_scale, rel_tol=1e-5)):
                    pass
                else:
                    self.viewTransformChanged.emit()
        else:
             logger.info("Invalid or null pixmap provided. Clearing scene rect and hiding buttons.")
             self.setSceneRect(QtCore.QRectF())
             self._min_scale = 0.01
             self._max_scale = config.MAX_ABS_SCALE
             self._ensure_overlay_widgets_updated_on_show(False)
             if hasattr(self, '_scale_bar_widget') and self._scale_bar_widget:
                self._scale_bar_widget.setVisible(False)

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

    def _draw_temporary_scale_line(self, p1: QtCore.QPointF, p2: QtCore.QPointF) -> QtWidgets.QGraphicsLineItem:
        """Draws or updates the temporary scale line between two scene points."""
        if self._temp_scale_line:
            self._temp_scale_line.setLine(p1.x(), p1.y(), p2.x(), p2.y())
        else:
            line = QtWidgets.QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            pen = QtGui.QPen(self._temp_scale_visuals_color, 1.5)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            line.setPen(pen)
            line.setZValue(19) # Below markers but above tracks
            self._scene.addItem(line)
            self._temp_scale_line = line
        return self._temp_scale_line

    def clearTemporaryScaleVisuals(self) -> None:
        """Removes all temporary scale definition visuals from the scene."""
        logger.debug("Clearing temporary scale visuals.")
        if self._temp_scale_marker1 and self._temp_scale_marker1.scene() == self._scene:
            self._scene.removeItem(self._temp_scale_marker1)
            self._temp_scale_marker1 = None
        if self._temp_scale_marker2 and self._temp_scale_marker2.scene() == self._scene:
            self._scene.removeItem(self._temp_scale_marker2)
            self._temp_scale_marker2 = None
        if self._temp_scale_line and self._temp_scale_line.scene() == self._scene:
            self._scene.removeItem(self._temp_scale_line)
            self._temp_scale_line = None
        self._scale_line_point1_scene = None # Reset stored first point
    # --- END OF NEW METHODS FOR TEMPORARY SCALE VISUALS ---

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self._pixmap_item:
             super().wheelEvent(event)
             return
        
        # --- MODIFICATION: Disable wheel scroll for frame stepping if defining scale line ---
        if self._current_mode == InteractionMode.SET_SCALE_LINE_END:
            logger.debug("Wheel event ignored during SET_SCALE_LINE_END mode.")
            event.accept()
            return
        # --- END MODIFICATION ---

        modifiers: QtCore.Qt.KeyboardModifiers = event.modifiers()
        angle_delta: QtCore.QPoint = event.angleDelta()

        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            logger.debug("Ctrl+Scroll detected: Performing zoom.")
            scroll_amount: int = angle_delta.y()
            if scroll_amount == 0:
                 event.ignore()
                 return
            zoom_factor_base: float = 1.15
            if scroll_amount > 0:
                self._zoom(zoom_factor_base)
            else:
                self._zoom(1.0 / zoom_factor_base)
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
            logger.debug(f"Stored previous transform: {previous_transform}")
            logger.debug(f"Stored previous scene center: {previous_center}")

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

    # --- START OF MODIFIED MOUSEPRESSEVENT ---
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        button: QtCore.Qt.MouseButton = event.button()
        logger.debug(f"Mouse press event: Button={button}, Pos={event.pos()}, Mode={self._current_mode.name}")

        if button == QtCore.Qt.MouseButton.LeftButton and self._pixmap_item:
            scene_pos = self.mapToScene(event.pos())

            if not self._pixmap_item.sceneBoundingRect().contains(scene_pos):
                logger.debug("Left click outside pixmap bounds. Ignoring for special modes.")
                super().mousePressEvent(event) # Allow standard behavior (e.g. deselecting scene items)
                return

            if self._current_mode == InteractionMode.SET_SCALE_LINE_START:
                self.clearTemporaryScaleVisuals() # Clear any previous attempts
                self._scale_line_point1_scene = scene_pos
                self._temp_scale_marker1 = self._draw_temporary_scale_marker(self._scale_line_point1_scene)
                logger.info(f"Scale line point 1 set at scene: ({scene_pos.x():.2f}, {scene_pos.y():.2f})")
                self.scaleLinePoint1Clicked.emit(scene_pos.x(), scene_pos.y())
                # Mode will be changed to SET_SCALE_LINE_END by the controller
                event.accept()
            elif self._current_mode == InteractionMode.SET_SCALE_LINE_END:
                # This click defines the second point
                if self._scale_line_point1_scene is not None:
                    self._temp_scale_marker2 = self._draw_temporary_scale_marker(scene_pos)
                    self._draw_temporary_scale_line(self._scale_line_point1_scene, scene_pos) # Finalize line
                    logger.info(f"Scale line point 2 set at scene: ({scene_pos.x():.2f}, {scene_pos.y():.2f})")
                    self.scaleLinePoint2Clicked.emit(
                        self._scale_line_point1_scene.x(), self._scale_line_point1_scene.y(),
                        scene_pos.x(), scene_pos.y()
                    )
                    # Controller will reset mode to NORMAL after dialog
                else:
                    logger.warning("SET_SCALE_LINE_END mode but point1 is not set. Resetting to START.")
                    # This case should ideally be prevented by controller logic, but as a fallback:
                    self.set_interaction_mode(InteractionMode.SET_SCALE_LINE_START) # Go back to expecting first point
                event.accept()
            else: # NORMAL or SET_ORIGIN modes
                self._left_button_press_pos = event.pos()
                self._is_potential_pan = True
                self._is_panning = False
                logger.debug(f"Left mouse pressed at view pos: {self._left_button_press_pos} in mode {self._current_mode.name}. Potential pan/click.")
                event.accept()
        else:
            logger.debug("Non-left mouse button pressed or no pixmap, passing event to base class.")
            super().mousePressEvent(event)
    # --- END OF MODIFIED MOUSEPRESSEVENT ---

    # --- START OF MODIFIED MOUSEMOVEEVENT ---
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        viewport_pos = event.pos()
        scene_x, scene_y = -1.0, -1.0
        current_scene_pos: Optional[QtCore.QPointF] = None

        if self._pixmap_item:
            current_scene_pos = self.mapToScene(viewport_pos)
            if self._pixmap_item.sceneBoundingRect().contains(current_scene_pos):
                scene_x, scene_y = current_scene_pos.x(), current_scene_pos.y()

        self.sceneMouseMoved.emit(scene_x, scene_y)

        # --- Handle dynamic drawing for SET_SCALE_LINE_END mode ---
        if self._current_mode == InteractionMode.SET_SCALE_LINE_END and \
           self._scale_line_point1_scene is not None and current_scene_pos is not None:
            self._draw_temporary_scale_line(self._scale_line_point1_scene, current_scene_pos)
            event.accept()
            return # Consume event, dynamic line drawing handled

        # --- Handle Panning (existing logic) ---
        if self._is_potential_pan and self._left_button_press_pos is not None:
            distance_moved = (viewport_pos - self._left_button_press_pos).manhattanLength()
            if distance_moved >= config.DRAG_THRESHOLD:
                if self._current_mode == InteractionMode.NORMAL: # Only allow panning in NORMAL mode
                    logger.debug(f"Drag threshold ({config.DRAG_THRESHOLD}px) exceeded. Starting pan.")
                    self._is_panning = True
                    self.clearTemporaryScaleVisuals() # Cancel scale definition if pan starts
                else:
                    logger.debug(f"Drag threshold exceeded but not in NORMAL mode. Potential click.")

                self._is_potential_pan = False # Resolved from potential
                if self._is_panning: # Check again if we actually started panning
                    self._last_pan_point = viewport_pos
                    self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
        
        if self._is_panning and self._last_pan_point is not None: # Panning is active
            delta = viewport_pos - self._last_pan_point
            self._last_pan_point = viewport_pos
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
            event.accept()
            return

        super().mouseMoveEvent(event)
    # --- END OF MODIFIED MOUSEMOVEEVENT ---

    # --- START OF MODIFIED MOUSERELEASEEVENT ---
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        button: QtCore.Qt.MouseButton = event.button()
        logger.debug(f"Mouse release event: Button={button}, Pos={event.pos()}, Mode={self._current_mode.name}")

        if button == QtCore.Qt.MouseButton.LeftButton:
            if self._is_panning:
                self._is_panning = False
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                logger.debug("Panning finished.")
                event.accept()
            elif self._is_potential_pan and self._current_mode != InteractionMode.SET_SCALE_LINE_START and self._current_mode != InteractionMode.SET_SCALE_LINE_END:
                # This was a click in NORMAL or SET_ORIGIN mode
                self._is_potential_pan = False
                logger.debug(f"Potential pan resolved as a click in mode {self._current_mode.name}.")
                if self._pixmap_item and self._left_button_press_pos is not None:
                    scene_pos: QtCore.QPointF = self.mapToScene(self._left_button_press_pos)
                    logger.debug(f"Click mapped to scene pos: ({scene_pos.x():.3f}, {scene_pos.y():.3f})")

                    if self._pixmap_item.boundingRect().contains(scene_pos):
                        if self._current_mode == InteractionMode.SET_ORIGIN:
                            logger.info(f"Click in SET_ORIGIN mode. Emitting originSetRequest.")
                            self.originSetRequest.emit(scene_pos.x(), scene_pos.y())
                            event.accept()
                        elif self._current_mode == InteractionMode.NORMAL:
                            modifiers = event.modifiers()
                            if (modifiers == QtCore.Qt.KeyboardModifier.ControlModifier or
                                modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier):
                                logger.info(f"Modified click detected with modifiers: {modifiers}. Emitting modifiedClick.")
                                self.modifiedClick.emit(scene_pos.x(), scene_pos.y(), modifiers)
                                event.accept()
                            else:
                                logger.info(f"Standard click detected. Emitting pointClicked.")
                                self.pointClicked.emit(scene_pos.x(), scene_pos.y())
                                event.accept()
                        # No 'else' for SET_SCALE modes here, as their clicks are handled in mousePressEvent
                    else:
                        logger.debug("Click was outside pixmap bounds. Ignoring.")
                        super().mouseReleaseEvent(event)
                else:
                    logger.debug("Click occurred but no pixmap loaded or press pos invalid. Ignoring.")
                    super().mouseReleaseEvent(event)
            elif self._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END]:
                # Clicks for these modes are fully handled in mousePressEvent.
                # This block ensures the event is accepted if it was a scale-setting click.
                # _is_potential_pan would be false if a scale click was already processed in press.
                logger.debug(f"Mouse release in mode {self._current_mode.name}. Click logic handled in press.")
                event.accept() # Accept to prevent further processing by base class if it was a scale click.
            else:
                 logger.debug("Left mouse released, but was not in panning or relevant potential click state.")
                 super().mouseReleaseEvent(event)

            # Reset pan state variables after handling left button release
            self._is_potential_pan = False # Always reset this
            self._left_button_press_pos = None
            self._last_pan_point = None
            
            # Update cursor based on current mode (it might have been changed by controller)
            if not self._is_panning: # Ensure not mid-pan (should be false here anyway)
                 if self._current_mode == InteractionMode.NORMAL:
                      self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                 elif self._current_mode == InteractionMode.SET_ORIGIN:
                      self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
                 elif self._current_mode in [InteractionMode.SET_SCALE_LINE_START, InteractionMode.SET_SCALE_LINE_END]:
                      self.setCursor(QtCore.Qt.CursorShape.CrossCursor)

        else: # Other mouse buttons
            logger.debug("Non-left mouse button released, passing event to base class.")
            super().mouseReleaseEvent(event)
    # --- END OF MODIFIED MOUSERELEASEEVENT ---