# kymograph_dialog.py
"""
Dialog window for displaying a generated kymograph.
"""
import logging
from typing import TYPE_CHECKING, Optional
import sys

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import cv2 # For BGR to RGB conversion

if TYPE_CHECKING:
    pass # No specific type hints needed from other project files for this basic dialog

logger = logging.getLogger(__name__)

class KymographDisplayDialog(QtWidgets.QDialog):
    """
    A dialog to display the generated kymograph image.
    """

    def __init__(self,
                 kymograph_data: np.ndarray,
                 line_id: int,
                 video_filename: str,
                 y_axis_label: str,
                 x_axis_label: str,
                 parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        
        self.kymograph_data = kymograph_data
        self.line_id = line_id
        self.video_filename = video_filename
        self.y_axis_label_str = y_axis_label
        self.x_axis_label_str = x_axis_label
        self._kymograph_pixmap_item: Optional[QtWidgets.QGraphicsPixmapItem] = None

        self.setWindowTitle(f"Kymograph - Line {self.line_id} ({self.video_filename})")
        
        # Initial Sizing Strategy:
        # Aim for a decent size, e.g., a fraction of the primary screen or parent if available.
        # The kymograph will stretch to this.
        if parent:
            parent_size = parent.size()
            initial_width = int(parent_size.width() * 0.7)
            initial_height = int(parent_size.height() * 0.6)
            self.resize(initial_width, initial_height)
        else:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                self.resize(int(screen_geometry.width() * 0.5), int(screen_geometry.height() * 0.5))
            else:
                self.resize(800, 600) # Fallback default size

        self.setMinimumSize(400, 300) # A smaller minimum if user resizes aggressively
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        self._setup_ui()
        self._display_kymograph_image()
        
        logger.debug(f"KymographDisplayDialog initialized for Line ID {self.line_id}.")

    def _setup_ui(self) -> None:
        """Creates and arranges the UI elements within the dialog."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Kymograph Display Area ---
        self.kymograph_view = QtWidgets.QGraphicsView()
        self.kymograph_scene = QtWidgets.QGraphicsScene(self)
        self.kymograph_view.setScene(self.kymograph_scene)
        self.kymograph_view.setBackgroundBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.lightGray))
        self.kymograph_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False) # Usually off for pixel data
        self.kymograph_view.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        self.kymograph_view.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        # Basic panning for now
        self.kymograph_view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        
        main_layout.addWidget(self.kymograph_view, 1) # Give it stretch factor 1

        # --- Axis Labels (simple text labels below the view for now) ---
        axis_info_layout = QtWidgets.QHBoxLayout()
        
        self.x_axis_label_widget = QtWidgets.QLabel(f"X-Axis: {self.x_axis_label_str}")
        self.x_axis_label_widget.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.x_axis_label_widget.setWordWrap(True)
        axis_info_layout.addWidget(self.x_axis_label_widget)
        
        self.y_axis_label_widget = QtWidgets.QLabel(f"Y-Axis: {self.y_axis_label_str}")
        self.y_axis_label_widget.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.y_axis_label_widget.setWordWrap(True)
        # To simulate a Y-axis label, we could put it in a separate QVBoxLayout on the side,
        # but for simplicity, placing it next to the X-axis label for now.
        # For a true vertical label, a custom paint or a transformed QGraphicsTextItem is needed.
        # As a simple approach, we can add it to the layout like the X-axis label.
        # It will appear horizontal, but describe the vertical dimension of the image.
        axis_info_layout.addWidget(self.y_axis_label_widget)

        main_layout.addLayout(axis_info_layout)


        # --- Dialog Buttons ---
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        button_box.accepted.connect(self.accept) # QDialogButtonBox.Ok maps to accept
        button_box.rejected.connect(self.reject) # QDialogButtonBox.Close maps to reject
        
        # Ensure "Close" actually calls reject() if it's the only button
        close_button = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Close)
        if close_button:
            # If only a "Close" button is present, its clicked signal might not directly call reject unless hooked up.
            # However, QDialogButtonBox usually handles this for standard buttons.
            # If problems, uncomment: close_button.clicked.connect(self.reject)
            pass

        main_layout.addWidget(button_box)

    def _display_kymograph_image(self) -> None:
        """Converts the NumPy kymograph data to QPixmap and displays it,
           stretching to fill the view."""
        if self.kymograph_data is None:
            logger.error("No kymograph data to display.")
            self.kymograph_scene.clear()
            error_text = self.kymograph_scene.addText("Error: No kymograph data.")
            error_text.setDefaultTextColor(QtCore.Qt.GlobalColor.red)
            return

        data = self.kymograph_data
        
        if data.ndim == 2: # Grayscale
            data_for_image = data.T 
        elif data.ndim == 3: # Color
            data_for_image = data.transpose(1, 0, 2)
        else:
            logger.error(f"Unsupported kymograph data dimension: {data.ndim}")
            self.kymograph_scene.clear()
            error_text = self.kymograph_scene.addText(f"Error: Unsupported data dim {data.ndim}.")
            error_text.setDefaultTextColor(QtCore.Qt.GlobalColor.red)
            return

        height, width = data_for_image.shape[0], data_for_image.shape[1]
        q_image: Optional[QtGui.QImage] = None
        
        try:
            # ... (NumPy to QImage conversion logic remains the same as before) ...
            if data_for_image.ndim == 2 or (data_for_image.ndim == 3 and data_for_image.shape[2] == 1): # Grayscale
                if data_for_image.dtype != np.uint8:
                    if np.max(data_for_image) > np.min(data_for_image):
                        img_norm = 255 * (data_for_image - np.min(data_for_image)) / (np.max(data_for_image) - np.min(data_for_image))
                    else:
                        img_norm = np.zeros_like(data_for_image)
                    img_u8 = img_norm.astype(np.uint8)
                else:
                    img_u8 = data_for_image
                if img_u8.ndim == 3 and img_u8.shape[2] == 1: img_u8 = img_u8.squeeze(axis=2)
                bytes_per_line = img_u8.strides[0]
                q_image = QtGui.QImage(img_u8.data, width, height, bytes_per_line, QtGui.QImage.Format.Format_Grayscale8)
            
            elif data_for_image.ndim == 3 and data_for_image.shape[2] == 3: # Color (BGR from OpenCV)
                if data_for_image.dtype != np.uint8:
                    if np.max(data_for_image) > np.min(data_for_image):
                        img_norm = 255 * (data_for_image - np.min(data_for_image)) / (np.max(data_for_image) - np.min(data_for_image))
                    else:
                        img_norm = np.zeros_like(data_for_image)
                    img_u8 = img_norm.astype(np.uint8)
                else:
                    img_u8 = data_for_image
                rgb_image = cv2.cvtColor(img_u8, cv2.COLOR_BGR2RGB)
                rgb_image_contiguous = np.require(rgb_image, np.uint8, 'C')
                bytes_per_line = rgb_image_contiguous.strides[0]
                q_image = QtGui.QImage(rgb_image_contiguous.data, width, height, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
            else:
                logger.error(f"Unsupported kymograph data shape for QImage: {data_for_image.shape}")
                self.kymograph_scene.clear()
                self.kymograph_scene.addText("Error: Bad kymograph data shape.").setDefaultTextColor(QtCore.Qt.GlobalColor.red)
                return

            if q_image and not q_image.isNull():
                pixmap = QtGui.QPixmap.fromImage(q_image.copy()) 
                self.kymograph_scene.clear() 
                self._kymograph_pixmap_item = self.kymograph_scene.addPixmap(pixmap)
                # Important: Set sceneRect to the pixmap's bounding rect BEFORE calling fitInView
                # This defines the coordinate system of the scene based on the pixmap.
                self.kymograph_scene.setSceneRect(self._kymograph_pixmap_item.boundingRect())
                # MODIFIED: Use IgnoreAspectRatio to stretch the kymograph
                self.kymograph_view.fitInView(self._kymograph_pixmap_item, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio)
                # Dialog resize logic removed from here, handled by __init__ and resizeEvent
            else:
                logger.error("Failed to create QImage or QPixmap from kymograph data.")
                self.kymograph_scene.clear()
                self.kymograph_scene.addText("Error displaying kymograph (conversion failed).").setDefaultTextColor(QtCore.Qt.GlobalColor.red)

        except Exception as e:
            logger.exception(f"Error converting/displaying kymograph data: {e}")
            self.kymograph_scene.clear()
            error_text_item = self.kymograph_scene.addText(f"Error displaying kymograph:\n{e}")
            error_text_item.setDefaultTextColor(QtCore.Qt.GlobalColor.red) 

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Handles mouse wheel events for zooming the kymograph view."""
        if not self.kymograph_view or not self._kymograph_pixmap_item:
            super().wheelEvent(event)
            return

        modifiers = event.modifiers()
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier: # Zoom with Ctrl+Scroll
            angle_delta = event.angleDelta().y()
            if angle_delta == 0:
                event.ignore()
                return

            zoom_factor_base = 1.15
            if angle_delta > 0: # Scroll up
                self.kymograph_view.scale(zoom_factor_base, zoom_factor_base)
            else: # Scroll down
                self.kymograph_view.scale(1.0 / zoom_factor_base, 1.0 / zoom_factor_base)
            event.accept()
        else:
            super().wheelEvent(event) # Pass to base class for other scroll behaviors

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """Handles dialog resize events to refit the kymograph view."""
        super().resizeEvent(event) # Call base class implementation
        if self.kymograph_view and self._kymograph_pixmap_item and self._kymograph_pixmap_item.scene() == self.kymograph_scene:
            # Ensure sceneRect is based on the pixmap if it hasn't changed,
            # or if it has, _display_kymograph_image should have updated it.
            # Forcing it here again might be redundant if _kymograph_pixmap_item never changes after creation.
            # self.kymograph_scene.setSceneRect(self._kymograph_pixmap_item.boundingRect())
            
            # Refit the view, stretching the kymograph to the new view dimensions
            self.kymograph_view.fitInView(self._kymograph_pixmap_item, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio)
        logger.debug(f"KymographDialog resized to: {event.size().width()}x{event.size().height()}")

if __name__ == '__main__':
    # Basic test for the dialog
    app = QtWidgets.QApplication(sys.argv)
    
    # Create dummy kymograph data (time x distance)
    # For example, 50 frames (time) by 100 pixels (distance)
    # Grayscale
    # dummy_kymo_gray = np.random.randint(0, 256, (50, 100), dtype=np.uint8)
    # for i in range(50): dummy_kymo_gray[i, i:i+10] = 255 # Add a diagonal line
    
    # Color
    dummy_kymo_color = np.zeros((50, 100, 3), dtype=np.uint8) # BGR
    for i in range(50):
        dummy_kymo_color[i, i:i+20, 0] = 200 # Blue component
        dummy_kymo_color[i, (i+10):(i+30)%100, 1] = 150 # Green component
        dummy_kymo_color[i, (i+20):(i+40)%100, 2] = 250 # Red component

    dialog = KymographDisplayDialog(
        kymograph_data=dummy_kymo_color, # Or dummy_kymo_gray
        line_id=1,
        video_filename="test_video.mp4",
        y_axis_label="Distance (100 px)",
        x_axis_label="Time (50 frames, 00:01.667)",
        parent=None
    )
    dialog.show()
    sys.exit(app.exec())