# interactive_image_view.py
import math
import logging
from typing import Optional, List
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

class InteractiveImageView(QtWidgets.QGraphicsView):
    """
    A customized QGraphicsView for displaying and interacting with video frames.

    Handles displaying a QPixmap, zooming (Ctrl+mouse wheel, overlay buttons),
    panning (left-click-drag), distinguishing clicks from pans based on movement
    threshold, and emitting signals for point clicks (`pointClicked`), modified
    clicks (`modifiedClick`), origin setting requests (`originSetRequest`),
    mouse movement over the scene (`sceneMouseMoved`), and frame stepping requests
    via normal mouse wheel scroll (`frameStepRequested`).

    Maintains the view's transformation (zoom/pan) state across frame changes
    after the initial frame load. Includes overlay buttons for zoom and view reset.
    """
    # --- Signals ---
    pointClicked = QtCore.Signal(float, float) # Standard click (scene coords)
    frameStepRequested = QtCore.Signal(int) # Emitted for normal mouse wheel scroll (+1/-1)
    modifiedClick = QtCore.Signal(float, float, QtCore.Qt.KeyboardModifiers) # Click with modifiers (scene coords, mods)
    originSetRequest = QtCore.Signal(float, float) # Emitted when clicking in Set Origin mode (scene coords)
    sceneMouseMoved = QtCore.Signal(float, float) # Emits scene (x, y) or (-1, -1) if off image
    viewTransformChanged = QtCore.Signal() # Emitted when zoom/pan changes view scale

    # --- Instance Variables ---
    _scene: QtWidgets.QGraphicsScene
    _pixmap_item: Optional[QtWidgets.QGraphicsPixmapItem] # The main video frame item
    _initial_load: bool # Flag for first pixmap load to auto-fit

    # Panning/Clicking state
    _is_panning: bool # True if currently panning (drag threshold exceeded)
    _is_potential_pan: bool # True between mouse press and exceeding drag threshold
    _left_button_press_pos: Optional[QtCore.QPoint] # Viewport pos where left button was pressed
    _last_pan_point: Optional[QtCore.QPoint] # Last viewport pos during panning

    # Zoom limits
    _min_scale: float # Minimum allowed zoom scale (calculated to fit view)
    _max_scale: float # Maximum allowed zoom scale (from config)

    # Overlay Buttons
    zoomInButton: QtWidgets.QPushButton
    zoomOutButton: QtWidgets.QPushButton
    resetViewButton: QtWidgets.QPushButton

    _current_mode: InteractionMode # Current interaction mode (Normal or Set Origin)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initializes the view, scene, interaction settings, overlay buttons, and scale bar."""
        super().__init__(parent)
        logger.info("Initializing InteractiveImageView...")

        # Internal Graphics Scene to hold the pixmap item and overlays
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = None
        logger.debug("Graphics scene created and set.")

        # State flags initialization
        self._initial_load = True
        self._is_panning = False
        self._is_potential_pan = False
        self._left_button_press_pos = None
        self._last_pan_point = None
        self._current_mode = InteractionMode.NORMAL
        logger.debug("Internal interaction state flags initialized.")

        # Zoom limits (calculated later based on pixmap)
        self._min_scale = 0.01 # Initial placeholder, recalculated on setPixmap
        self._max_scale = config.MAX_ABS_SCALE # Get max from config
        logger.debug(f"Initial zoom limits: min={self._min_scale}, max={self._max_scale}")

        # Configure view appearance and behaviour
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse) # Zoom relative to mouse
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter) # Keep center on resize
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(40, 40, 40))) # Dark background
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setMouseTracking(True) # Receive mouse move events even when no button is pressed
        logger.debug("View appearance and behavior configured.")

        # Create overlay buttons (Zoom In/Out, Fit)
        self._create_overlay_buttons()

        # Create the Scale Bar Widget (initially hidden)
        self._scale_bar_widget = ScaleBarWidget(self) # Parent to this view for positioning
        self._scale_bar_widget.setVisible(False) # Explicitly ensure it's hidden initially
        logger.debug("ScaleBarWidget created and initially hidden.")

        logger.info("InteractiveImageView initialization complete.")


    def _calculate_zoom_limits(self) -> None:
        """
        Calculates minimum allowed scale factor to fit the scene in the viewport.
        Maximum is fixed from config. Must be called after sceneRect is set.
        """
        # Ensure valid conditions for calculation
        if not self._pixmap_item or not self.sceneRect().isValid() or self.viewport().width() <= 0:
            logger.warning("Cannot calculate zoom limits: Invalid scene, pixmap, or viewport.")
            self._min_scale = 0.01 # Default fallback
            # Max scale is already set from config and doesn't depend on scene/viewport
            return

        scene_rect: QtCore.QRectF = self.sceneRect()
        vp_rect: QtCore.QRect = self.viewport().rect()
        logger.debug(f"Calculating min zoom limit. SceneRect: {scene_rect}, ViewportRect: {vp_rect}")

        # Minimum scale factor required to fit the entire scene within the viewport
        try:
            if scene_rect.width() <= 0 or scene_rect.height() <= 0:
                 raise ZeroDivisionError("Scene rectangle has zero width or height.")
            scale_x: float = vp_rect.width() / scene_rect.width()
            scale_y: float = vp_rect.height() / scene_rect.height()
            self._min_scale = min(scale_x, scale_y) # Scale to fit entirely
        except ZeroDivisionError:
             logger.warning("ZeroDivisionError calculating minimum scale, using fallback 0.01.")
             self._min_scale = 0.01 # Fallback

        # Sanity check calculated min scale
        if self._min_scale <= 0 or math.isnan(self._min_scale):
             logger.warning(f"Calculated minimum scale ({self._min_scale}) is invalid, using fallback 0.01.")
             self._min_scale = 0.01 # Fallback

        # Ensure min is not greater than max (can happen with very small viewports/large images)
        if self._min_scale > self._max_scale:
             logger.warning(f"Calculated minimum scale ({self._min_scale:.4f}) > max scale ({self._max_scale:.4f}). Adjusting max scale.")
             # Set max slightly larger than min to allow some minimal zoom-in
             self._max_scale = self._min_scale * 1.1
        logger.debug(f"Calculated zoom limits: min={self._min_scale:.4f}, max={self._max_scale:.4f}")


    def _create_overlay_buttons(self) -> None:
        """Creates and styles the overlay buttons."""
        logger.debug("Creating overlay buttons...")
        # Consistent styling for overlay buttons
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
        button_size = QtCore.QSize(30, 30) # Fixed size for overlay buttons

        # Zoom In Button
        self.zoomInButton = QtWidgets.QPushButton("+", self)
        self.zoomInButton.setFixedSize(button_size)
        self.zoomInButton.setToolTip("Zoom In (Ctrl+Scroll Up)")
        self.zoomInButton.setStyleSheet(button_style)
        self.zoomInButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoomInButton.clicked.connect(self._zoomIn)
        self.zoomInButton.hide()

        # Zoom Out Button
        self.zoomOutButton = QtWidgets.QPushButton("-", self)
        self.zoomOutButton.setFixedSize(button_size)
        self.zoomOutButton.setToolTip("Zoom Out (Ctrl+Scroll Down)")
        self.zoomOutButton.setStyleSheet(button_style)
        self.zoomOutButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoomOutButton.clicked.connect(self._zoomOut)
        self.zoomOutButton.hide()

        # Reset View / Fit Button
        self.resetViewButton = QtWidgets.QPushButton("⤢", self) # Unicode fit symbol
        self.resetViewButton.setFixedSize(button_size)
        self.resetViewButton.setToolTip("Fit Image to View (Reset Zoom/Pan)")
        self.resetViewButton.setStyleSheet(button_style)
        self.resetViewButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.resetViewButton.clicked.connect(self.resetView)
        self.resetViewButton.hide()
        logger.debug("Overlay buttons created.")


    def _update_overlay_widget_positions(self) -> None:
        """Positions the overlay buttons and scale bar in the viewport."""
        if not hasattr(self, 'zoomInButton') or not self.zoomInButton:
             logger.warning("_update_overlay_widget_positions called before overlay buttons created.")
             return
        if not hasattr(self, '_scale_bar_widget') or not self._scale_bar_widget:
            logger.warning("_update_overlay_widget_positions called before scale bar widget created.")
            return

        margin: int = 10 # Margin from viewport edges
        vp_width: int = self.viewport().width()
        vp_height: int = self.viewport().height()

        # --- Position Overlay Buttons (Top-Right) ---
        button_width: int = self.zoomInButton.width()
        button_height: int = self.zoomInButton.height()
        spacing: int = 5 # Spacing between buttons

        x_pos_buttons: int = vp_width - button_width - margin
        self.zoomInButton.move(x_pos_buttons, margin)
        self.zoomOutButton.move(x_pos_buttons, margin + button_height + spacing)
        self.resetViewButton.move(x_pos_buttons, margin + 2 * (button_height + spacing))

        # --- Position Scale Bar Widget (Bottom-Right) ---
        if self._scale_bar_widget.isVisible(): # Only position if it's supposed to be visible
            # The scale bar widget itself determines its own width and height via sizeHint/setFixedSize
            sb_width: int = self._scale_bar_widget.width()
            sb_height: int = self._scale_bar_widget.height()

            x_pos_sb: int = vp_width - sb_width - margin
            y_pos_sb: int = vp_height - sb_height - margin
            self._scale_bar_widget.move(x_pos_sb, y_pos_sb)
            logger.debug(f"Scale bar positioned at ({x_pos_sb}, {y_pos_sb}), size: {self._scale_bar_widget.size()}")


    def _ensure_overlay_widgets_updated_on_show(self, buttons_visible: bool) -> None:
        """
        Shows or hides the overlay buttons.
        Always updates overlay widget positions if buttons are being made visible.
        Scale bar visibility is managed separately.
        """
        if not hasattr(self, 'zoomInButton') or not self.zoomInButton:
             logger.warning("_ensure_overlay_widgets_updated_on_show called before overlay buttons created.")
             return

        logger.debug(f"Setting overlay buttons visible: {buttons_visible}")
        if buttons_visible:
            self._update_overlay_widget_positions() # Update positions before showing buttons
            self.zoomInButton.show()
            self.zoomOutButton.show()
            self.resetViewButton.show()
        else:
            self.zoomInButton.hide()
            self.zoomOutButton.hide()
            self.resetViewButton.hide()

        # Ensure scale bar position is also updated if it's visible
        if self._scale_bar_widget and self._scale_bar_widget.isVisible():
            self._update_overlay_widget_positions()


    def _zoom(self, factor: float) -> None:
        """Applies a relative zoom factor, respecting limits, anchored to the mouse position."""
        if not self._pixmap_item:
            logger.debug("_zoom called but no pixmap item exists.")
            return

        current_scale: float = self.transform().m11() # Get current horizontal scale
        logger.debug(f"Zoom requested with factor {factor:.3f}. Current scale: {current_scale:.4f}")

        # Calculate target scale, clamping between min and max limits
        target_scale: float
        if factor > 1.0: # Zooming in
            target_scale = min(current_scale * factor, self._max_scale)
        else: # Zooming out (factor < 1.0)
            target_scale = max(current_scale * factor, self._min_scale)
        logger.debug(f"Calculated target scale: {target_scale:.4f} (Min: {self._min_scale:.4f}, Max: {self._max_scale:.4f})")

        # Only apply scale if the target scale is meaningfully different from current
        if not math.isclose(target_scale, current_scale, rel_tol=1e-5):
            actual_zoom: float = target_scale / current_scale
            logger.debug(f"Applying scale factor {actual_zoom:.4f} (Target: {target_scale:.4f})")
            # Use AnchorUnderMouse set in __init__ to zoom relative to cursor
            self.scale(actual_zoom, actual_zoom)
            self.viewTransformChanged.emit() # <<< EMIT SIGNAL
        else:
            logger.debug("Target scale close to current scale or limits reached. No zoom applied.")


    @QtCore.Slot()
    def _zoomIn(self) -> None:
        """Slot for the Zoom In (+) button. Zooms in by a fixed factor."""
        logger.debug("Zoom In button clicked.")
        zoom_in_factor: float = 1.3 # Factor to increase scale by
        self._zoom(zoom_in_factor)


    @QtCore.Slot()
    def _zoomOut(self) -> None:
        """Slot for the Zoom Out (-) button. Zooms out by a fixed factor."""
        logger.debug("Zoom Out button clicked.")
        zoom_out_factor: float = 1.0 / 1.3 # Factor to decrease scale by
        self._zoom(zoom_out_factor)


    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        """
        Displays the given QPixmap in the view.

        Clears the scene, adds the new pixmap, sets the scene rectangle,
        recalculates zoom limits, and either resets the view to fit (on initial load)
        or attempts to restore the previous view transformation (zoom/pan).

        Args:
            pixmap: The QPixmap image to display.
        """
        logger.info(f"Setting pixmap. Is null: {pixmap.isNull()}. Size: {pixmap.size()}")
        current_transform: Optional[QtGui.QTransform] = None
        is_initial: bool = self._initial_load
        logger.debug(f"setPixmap called. Initial load flag: {is_initial}")

        if self._pixmap_item and self.sceneRect().isValid() and not is_initial:
            current_transform = self.transform()
            logger.debug(f"Stored previous transform: {current_transform}")

        logger.debug("Clearing graphics scene...")
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
                self.resetView() # This will emit viewTransformChanged
                self._initial_load = False
                transform_changed_by_set_pixmap = True # resetView emits it
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
                     self.resetView() # This will emit viewTransformChanged
                     transform_changed_by_set_pixmap = True # resetView emits it
            else:
                 logger.warning("No valid previous transform stored despite not being initial load. Resetting view.")
                 self.resetView() # This will emit viewTransformChanged
                 transform_changed_by_set_pixmap = True # resetView emits it

            self._ensure_overlay_widgets_updated_on_show(True) # Show overlay buttons
            if transform_changed_by_set_pixmap and not is_initial : # resetView emits, only emit if not initial and setTransform was used directly
                # If setTransform was called directly, explicitly emit. resetView handles its own emission.
                # This ensures the signal is sent if the transform was directly set.
                if not (current_transform is not None and math.isclose(clamped_scale, previous_scale, rel_tol=1e-5)): # i.e. if resetView was NOT called.
                    pass # resetView path already emits, avoid double emission
                else: # if setTransform was called
                    self.viewTransformChanged.emit()

        else:
             logger.info("Invalid or null pixmap provided. Clearing scene rect and hiding buttons.")
             self.setSceneRect(QtCore.QRectF())
             self._min_scale = 0.01
             self._max_scale = config.MAX_ABS_SCALE
             self._ensure_overlay_widgets_updated_on_show(False)
             # Hide scale bar if pixmap is removed
             if hasattr(self, '_scale_bar_widget') and self._scale_bar_widget:
                self._scale_bar_widget.setVisible(False)


        logger.debug("Resetting interaction state variables (pan/click).")
        self._is_panning = False
        self._is_potential_pan = False
        self._left_button_press_pos = None
        self._last_pan_point = None


    def resetInitialLoadFlag(self) -> None:
        """
        Resets the initial load flag. Called by MainWindow when a new video is
        loaded, ensuring the first frame of the new video fits the view.
        """
        logger.debug("Resetting initial load flag to True.")
        self._initial_load = True


    @QtCore.Slot()
    def resetView(self) -> None:
        """Resets zoom and pan to fit the entire image centered within the view."""
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
        self.viewTransformChanged.emit() # <<< EMIT SIGNAL
        logger.info("View reset complete.")


    def clearOverlay(self) -> None:
        """Removes all graphics items from the scene *except* the main pixmap item."""
        if not self._scene:
            logger.error("clearOverlay called but scene does not exist.")
            return
        logger.debug("Clearing overlay graphics items...")

        items_to_remove: List[QtWidgets.QGraphicsItem] = []
        # Iterate safely while potentially modifying the item list implicitly
        for item in self._scene.items():
             # Keep the main pixmap item, remove everything else
             if item != self._pixmap_item:
                 items_to_remove.append(item)

        num_removed: int = 0
        for item in items_to_remove:
            try:
                # Check scene ownership before removing
                if item.scene() == self._scene:
                     self._scene.removeItem(item)
                     num_removed += 1
            except Exception as e:
                # Catch potential issues during item removal
                logger.warning(f"Error removing overlay item {item} from scene: {e}", exc_info=False)
        logger.debug(f"Cleared {num_removed} overlay items.")

    def set_interaction_mode(self, mode: InteractionMode) -> None:
        """Sets the current interaction mode and updates the cursor."""
        if self._current_mode != mode:
            logger.info(f"Changing interaction mode from {self._current_mode.name} to {mode.name}")
            self._current_mode = mode
            # Update cursor based on mode
            if mode == InteractionMode.SET_ORIGIN:
                 self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else: # InteractionMode.NORMAL
                 self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        else:
             logger.debug(f"Interaction mode already set to {mode.name}")


    # --- Event Handling Methods ---

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """
        Handles mouse wheel scrolling.
        Normal Scroll (no/other modifier): Emits frameStepRequested signal.
        Ctrl+Scroll: Zooms the view in/out anchored at the mouse cursor.
        """
        if not self._pixmap_item:
             super().wheelEvent(event) # No image, pass to base class
             return

        modifiers: QtCore.Qt.KeyboardModifiers = event.modifiers()
        angle_delta: QtCore.QPoint = event.angleDelta() # Use angle delta for direction/step

        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            # --- Ctrl + Scroll: Zoom ---
            logger.debug("Ctrl+Scroll detected: Performing zoom.")
            scroll_amount: int = angle_delta.y()
            if scroll_amount == 0:
                 event.ignore() # No vertical scroll detected
                 return

            zoom_factor_base: float = 1.15 # Base factor for zooming per step
            if scroll_amount > 0: # Scroll Up/Away = Zoom In
                self._zoom(zoom_factor_base)
            else: # Scroll Down/Towards = Zoom Out
                self._zoom(1.0 / zoom_factor_base)

            event.accept() # Consume the event, zoom handled

        else:
            # --- Normal Scroll (or other modifiers): Frame Step ---
            logger.debug("Scroll detected (no/other modifier): Requesting frame step.")
            scroll_amount_y: int = angle_delta.y()
            if scroll_amount_y == 0:
                 event.ignore() # No vertical scroll detected
                 return

            # Scroll Up/Away = Previous Frame (-1), Scroll Down/Towards = Next Frame (+1)
            step: int = -1 if scroll_amount_y > 0 else 1
            logger.debug(f"Emitting frameStepRequested signal with step: {step}")
            self.frameStepRequested.emit(step)
            event.accept() # Consume the event, frame step requested


    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """
        Handles view resize events. Recalculates zoom limits, attempts to
        maintain view center/scale, and repositions overlay widgets.
        """
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
                 self.resetView() # This emits viewTransformChanged
                 view_reset_called = True
             else:
                 logger.debug("Previous scale still within new limits after resize. Re-centering.")
                 self.centerOn(previous_center)
                 # If only centered, but scale effectively changed due to aspect ratio, still emit.
                 # However, a simple centerOn doesn't change the transform's scale part.
                 # We need to ensure the signal is emitted if the view parameters affecting scale bar change.
                 # The explicit emission after _update_overlay_widget_positions covers this.

        elif self._pixmap_item and self.sceneRect().isValid():
             logger.debug("No valid previous state or pixmap, resetting view after resize.")
             self.resetView() # This emits viewTransformChanged
             view_reset_called = True

        self._update_overlay_widget_positions() # Position overlay buttons and potentially scale bar

        # If resetView wasn't called but the viewport dimensions changed,
        # the scale bar still needs to know to update, which viewTransformChanged handles.
        # Or, if only centered, still emit.
        if not view_reset_called:
            self.viewTransformChanged.emit()

        logger.debug("Resize event handling complete.")


    def set_scale_bar_visibility(self, visible: bool) -> None:
        """Shows or hides the scale bar widget and updates its position if showing."""
        if hasattr(self, '_scale_bar_widget') and self._scale_bar_widget:
            if visible and (not self._pixmap_item or not self.sceneRect().isValid()):
                logger.debug("Request to show scale bar, but no valid pixmap. Keeping hidden.")
                self._scale_bar_widget.setVisible(False)
                return

            if self._scale_bar_widget.isVisible() != visible:
                self._scale_bar_widget.setVisible(visible)
                logger.debug(f"Scale bar visibility set to: {visible}")
                if visible:
                    self._update_overlay_widget_positions() # Ensure it's positioned correctly
            elif visible: # Already visible, ensure position is updated (e.g. after initial video load)
                 self._update_overlay_widget_positions()


    def update_scale_bar_dimensions(self, m_per_px_scene: Optional[float]) -> None:
        """
        Updates the scale bar with the current scene-to-meter scale and view parameters.
        Called by MainWindow when the main scale (m/px) is set/changed or view transform changes.
        """
        if hasattr(self, '_scale_bar_widget') and self._scale_bar_widget:
            if not self._pixmap_item or not self.sceneRect().isValid(): # Cannot update if no image context
                self._scale_bar_widget.setVisible(False) # Ensure it's hidden
                return

            current_view_scale_factor = self.transform().m11() # Get current view zoom
            parent_view_width = self.viewport().width()

            self._scale_bar_widget.update_dimensions(
                m_per_px_scene,
                current_view_scale_factor,
                parent_view_width
            )
            # After updating dimensions, it might change its own size, so re-evaluate position
            if self._scale_bar_widget.isVisible():
                 self._update_overlay_widget_positions()

    def get_current_view_scale_factor(self) -> float:
        """Returns the current horizontal scale factor of the view's transform."""
        return self.transform().m11()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Handles mouse press events. Initiates potential panning (left button)
        or click detection on left mouse button press over a valid pixmap.
        """
        button: QtCore.Qt.MouseButton = event.button()
        logger.debug(f"Mouse press event: Button={button}, Pos={event.pos()}")

        # Only handle left clicks when a pixmap is loaded for panning/clicking
        if button == QtCore.Qt.MouseButton.LeftButton and self._pixmap_item:
            self._left_button_press_pos = event.pos() # Store viewport position
            self._is_potential_pan = True # Start assuming it *could* be a pan
            self._is_panning = False # Not panning yet
            logger.debug(f"Left mouse pressed at view pos: {self._left_button_press_pos}. Initiating potential pan/click.")
            event.accept() # Indicate we might handle this event chain
        else:
            # For other buttons or if no pixmap, pass to base class
            logger.debug("Non-left mouse button pressed or no pixmap, passing event to base class.")
            super().mousePressEvent(event)


    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Handles mouse movement. Emits scene coordinates if over the pixmap.
        Handles panning if left button is down and drag threshold exceeded.
        """
        viewport_pos = event.pos() # Current position in viewport coordinates

        # --- Emit Scene Coordinates ---
        scene_x, scene_y = -1.0, -1.0 # Default to off-image values
        if self._pixmap_item:
            scene_pos = self.mapToScene(viewport_pos)
            # Check if mouse is within the scene bounds defined by the pixmap
            if self._pixmap_item.sceneBoundingRect().contains(scene_pos):
                scene_x, scene_y = scene_pos.x(), scene_pos.y()
            # else: keep -1.0, -1.0 if outside pixmap bounds

        # Emit signal regardless of button state (uses values calculated above)
        self.sceneMouseMoved.emit(scene_x, scene_y)

        # --- Handle Panning ---
        # Check if we are in the initial phase after a left-click
        if self._is_potential_pan and self._left_button_press_pos is not None:
            distance_moved = (viewport_pos - self._left_button_press_pos).manhattanLength()
            # If drag threshold exceeded, switch to panning mode
            if distance_moved >= config.DRAG_THRESHOLD:
                logger.debug(f"Drag threshold ({config.DRAG_THRESHOLD}px) exceeded. Starting pan.")
                self._is_panning = True
                self._is_potential_pan = False # No longer potentially a click
                self._last_pan_point = viewport_pos
                self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return # Consume event, panning started

        # If we are actively panning, update scroll bars
        if self._is_panning and self._last_pan_point is not None:
            delta = viewport_pos - self._last_pan_point
            self._last_pan_point = viewport_pos
            # Adjust scroll bar values based on mouse delta
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
            event.accept() # Consume event, pan handled
            return # Don't call super if panning

        # If not panning or starting a pan, call base class (e.g., for tooltips)
        super().mouseMoveEvent(event)


    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Handles left mouse button release. Completes the pan action or emits
        the appropriate click signal if it was determined not to be a pan,
        considering the current interaction mode and modifier keys.
        """
        button: QtCore.Qt.MouseButton = event.button()
        logger.debug(f"Mouse release event: Button={button}, Pos={event.pos()}")

        if button == QtCore.Qt.MouseButton.LeftButton:
            if self._is_panning:
                # --- End Panning ---
                self._is_panning = False
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor) # Restore cursor
                logger.debug("Panning finished.")
                event.accept() # Consume event, pan completed
            elif self._is_potential_pan:
                # --- Fire Click Signal (Click occurred instead of pan) ---
                self._is_potential_pan = False # No longer a potential pan
                logger.debug("Potential pan resolved as a click.")
                # Ensure pixmap exists and we recorded the press position
                if self._pixmap_item and self._left_button_press_pos is not None:
                    # Map the *original press position* (viewport coords) to scene coordinates
                    scene_pos: QtCore.QPointF = self.mapToScene(self._left_button_press_pos)
                    logger.debug(f"Click mapped to scene pos: ({scene_pos.x():.3f}, {scene_pos.y():.3f})")

                    # Check if the click occurred within the bounds of the pixmap item
                    if self._pixmap_item.boundingRect().contains(scene_pos):
                        # --- Handle click based on current interaction mode ---
                        if self._current_mode == InteractionMode.SET_ORIGIN:
                            logger.info(f"Click in SET_ORIGIN mode. Emitting originSetRequest.")
                            self.originSetRequest.emit(scene_pos.x(), scene_pos.y())
                            # MainWindow will handle resetting mode back to NORMAL
                            event.accept() # Consume event, origin set request handled

                        elif self._current_mode == InteractionMode.NORMAL:
                            modifiers = event.modifiers()
                            # Emit specific signal based on modifiers
                            if (modifiers == QtCore.Qt.KeyboardModifier.ControlModifier or
                                modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier):
                                logger.info(f"Modified click detected with modifiers: {modifiers}. Emitting modifiedClick.")
                                self.modifiedClick.emit(scene_pos.x(), scene_pos.y(), modifiers)
                                event.accept() # Consume event, modified click handled
                            else: # No or other modifiers -> standard click
                                logger.info(f"Standard click detected. Emitting pointClicked.")
                                self.pointClicked.emit(scene_pos.x(), scene_pos.y())
                                event.accept() # Consume event, standard click handled
                        else:
                             # Should not happen with current modes
                             logger.warning(f"Click occurred in unhandled interaction mode: {self._current_mode.name}")
                             super().mouseReleaseEvent(event) # Fallback
                    else:
                        # Click was outside the image area
                        logger.debug("Click was outside pixmap bounds. Ignoring.")
                        super().mouseReleaseEvent(event) # Pass event to base class
                else:
                    # Should not happen if _is_potential_pan was true, but handle defensively
                    logger.debug("Click occurred but no pixmap loaded or press pos invalid. Ignoring.")
                    super().mouseReleaseEvent(event)
            else:
                 # Left button released, but wasn't panning or potentially panning (e.g., press outside pixmap)
                 logger.debug("Left mouse released, but was not in panning or potential pan state.")
                 super().mouseReleaseEvent(event)

            # Reset state variables after handling left button release
            logger.debug("Resetting pan/click state variables.")
            self._left_button_press_pos = None
            self._last_pan_point = None
            # Ensure cursor is correct after action (unless SET_ORIGIN mode is still active)
            if not self._is_panning:
                 if self._current_mode == InteractionMode.NORMAL:
                      self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                 elif self._current_mode == InteractionMode.SET_ORIGIN:
                      self.setCursor(QtCore.Qt.CursorShape.CrossCursor)

        else:
            # Other button released, pass to base class
            logger.debug("Non-left mouse button released, passing event to base class.")
            super().mouseReleaseEvent(event)