# scale_bar_widget.py
"""
Custom QWidget for displaying a dynamic scale bar on the InteractiveImageView.
"""
import logging
import math
import config
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

# --- Constants for Scale Bar Appearance (can be moved to config.py later if desired) ---
SCALE_BAR_RECT_HEIGHT = 4  # Height of the scale bar rectangle in pixels
SCALE_BAR_BORDER_THICKNESS = 1 # Thickness of the border around the rectangle
SCALE_BAR_TEXT_MARGIN_BOTTOM = 2 # Space between text and top of scale bar rectangle
SCALE_BAR_DEFAULT_TARGET_FRACTION_OF_VIEW_WIDTH = 0.15 # Try to make bar ~15% of view width
SCALE_BAR_MIN_PIXEL_WIDTH = 50  # Minimum pixel width for the bar to be meaningful
SCALE_BAR_MAX_PIXEL_WIDTH = 300 # Maximum pixel width to avoid being too intrusive

class ScaleBarWidget(QtWidgets.QWidget):
    """
    A widget that draws a scale bar with a text label indicating its real-world length.
    The bar's pixel length dynamically adjusts to view zoom, while its represented
    real-world length aims for a "round number".
    """

    _m_per_px_scene: Optional[float] # Meters per pixel at 1x zoom (scene coordinates)
    _view_scale_factor: float        # Current zoom factor of the InteractiveImageView
    _parent_view_width: int          # Current width of the parent InteractiveImageView

    # Calculated properties for drawing
    _bar_pixel_length: float
    _bar_text_label: str
    _text_width: int
    _text_height: int

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents) # Pass mouse events through
        self.setVisible(False) # Initially hidden

        self._m_per_px_scene = None
        self._view_scale_factor = 1.0
        self._parent_view_width = 0 # Needs to be updated by parent

        self._bar_pixel_length = 0.0
        self._bar_text_label = ""
        self._text_width = 0
        self._text_height = 0

        # Basic appearance (can be customized further if needed)
        self.font_metrics = QtGui.QFontMetrics(self.font()) # Use default widget font for now
        self._bar_color = QtGui.QColor(QtCore.Qt.GlobalColor.white)
        self._border_color = QtGui.QColor(QtCore.Qt.GlobalColor.black)
        self._text_color = QtGui.QColor(QtCore.Qt.GlobalColor.white) # Text color, consider contrast

        # Set size policy to allow it to adapt if parent uses it in a layout (though we'll position manually)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._calculate_widget_height())


    def _calculate_widget_height(self) -> int:
        """Calculates the total height needed for the widget (text + margin + bar)."""
        text_h = self.font_metrics.height()
        return text_h + SCALE_BAR_TEXT_MARGIN_BOTTOM + SCALE_BAR_RECT_HEIGHT + 2 * SCALE_BAR_BORDER_THICKNESS

    def update_dimensions(self,
                          m_per_px_scene: Optional[float],
                          view_scale_factor: float,
                          parent_view_width: int) -> None:
        """
        Updates the scale bar's internal parameters based on the current
        scene scale, view zoom, and parent view width.
        This will trigger a recalculation of the bar's length and label,
        and a repaint.

        Args:
            m_per_px_scene: The current scale in meters per physical pixel of the scene (at 1x zoom).
                           If None, the scale bar will not be displayed.
            view_scale_factor: The current zoom factor of the InteractiveImageView.
            parent_view_width: The current width of the parent InteractiveImageView in pixels.
        """
        logger.debug(f"ScaleBarWidget update_dimensions: m/px_scene={m_per_px_scene}, view_scale={view_scale_factor}, view_width={parent_view_width}")
        visibility_changed = (self._m_per_px_scene is None and m_per_px_scene is not None) or \
                             (self._m_per_px_scene is not None and m_per_px_scene is None)

        self._m_per_px_scene = m_per_px_scene
        self._view_scale_factor = max(0.0001, view_scale_factor) # Avoid division by zero or negative
        self._parent_view_width = parent_view_width

        if self._m_per_px_scene is None or self._view_scale_factor <= 0:
            self.setVisible(False)
            self._bar_pixel_length = 0
            self._bar_text_label = ""
            logger.debug("Scale bar hidden (no scene scale or invalid view scale).")
        else:
            self._calculate_bar_length_and_label()
            if not self.isVisible() and self._bar_pixel_length > 0:
                self.setVisible(True)
                visibility_changed = True # Became visible
            elif self.isVisible() and self._bar_pixel_length == 0:
                 self.setVisible(False)
                 visibility_changed = True # Became hidden

            if self.isVisible() or visibility_changed:
                # Adjust widget size to fit new content
                required_width = int(max(self._bar_pixel_length + 2 * SCALE_BAR_BORDER_THICKNESS, self._text_width))
                self.setFixedWidth(max(10, required_width)) # Ensure a minimum width
                self.update() # Trigger repaint

    def _format_length_value(self, length_meters: float) -> str:
        """
        Formats a given length in meters into a human-readable string
        with appropriate units (km, m, cm, mm, µm, nm) or scientific notation.
        Uses constants from config.py.
        """
        if length_meters == 0:
            return "0 m"

        if abs(length_meters) >= config.SCIENTIFIC_NOTATION_UPPER_THRESHOLD or \
           (abs(length_meters) > 0 and abs(length_meters) <= config.SCIENTIFIC_NOTATION_LOWER_THRESHOLD) :
            return f"{length_meters:.1e}"

        for factor, singular_abbr, plural_abbr in config.UNIT_PREFIXES: # Use config.UNIT_PREFIXES
            if abs(length_meters) >= factor * 0.99:
                value_in_unit = length_meters / factor
                if factor >= 1.0:
                    precision = 2 if abs(value_in_unit) < 10 else 1 if abs(value_in_unit) < 100 else 0
                elif factor >= 1e-3:
                    precision = 1 if abs(value_in_unit) < 100 else 0
                else:
                    precision = 0
                if abs(value_in_unit) >= 1 and value_in_unit == math.floor(value_in_unit) and precision > 0:
                     if abs(value_in_unit) > 10 : precision = 0
                formatted_value = f"{value_in_unit:.{precision}f}"
                unit_to_display = plural_abbr if plural_abbr and abs(value_in_unit) != 1.0 else singular_abbr
                return f"{formatted_value} {unit_to_display}"
        return f"{length_meters:.2f} m"

    def _calculate_bar_length_and_label(self) -> None:
        """
        Calculates the optimal real-world length for the scale bar to represent,
        its corresponding pixel length on screen, and the text label.
        Updates _bar_pixel_length and _bar_text_label.
        Uses ROUND_NUMBER_SEQUENCE from config.py.
        """
        if self._m_per_px_scene is None or self._view_scale_factor <= 0 or self._parent_view_width <= 0:
            self._bar_pixel_length = 0
            self._bar_text_label = ""
            return

        m_per_view_pixel = self._m_per_px_scene / self._view_scale_factor
        target_bar_display_width_px = self._parent_view_width * SCALE_BAR_DEFAULT_TARGET_FRACTION_OF_VIEW_WIDTH
        target_bar_display_width_px = max(SCALE_BAR_MIN_PIXEL_WIDTH,
                                         min(target_bar_display_width_px, SCALE_BAR_MAX_PIXEL_WIDTH))
        target_real_world_length_m = target_bar_display_width_px * m_per_view_pixel

        if target_real_world_length_m <= 0:
            self._bar_pixel_length = 0
            self._bar_text_label = ""
            return

        power_of_10 = 10.0 ** math.floor(math.log10(target_real_world_length_m))
        # Use config.ROUND_NUMBER_SEQUENCE
        best_length_m = power_of_10 * config.ROUND_NUMBER_SEQUENCE[0]
        for R in config.ROUND_NUMBER_SEQUENCE: # Use config.ROUND_NUMBER_SEQUENCE
            current_test_length_m = power_of_10 * R
            if current_test_length_m <= target_real_world_length_m * 1.05:
                best_length_m = current_test_length_m
            else:
                break
        # Use config.ROUND_NUMBER_SEQUENCE
        if target_real_world_length_m < power_of_10 * config.ROUND_NUMBER_SEQUENCE[0] * 0.75 and power_of_10 > 1e-9:
             power_of_10_smaller = power_of_10 / 10.0
             best_length_m = power_of_10_smaller * config.ROUND_NUMBER_SEQUENCE[-1] # Use config.ROUND_NUMBER_SEQUENCE

        chosen_real_world_length_m = best_length_m
        final_bar_pixel_length = chosen_real_world_length_m / m_per_view_pixel

        if final_bar_pixel_length < SCALE_BAR_MIN_PIXEL_WIDTH / 2.0:
             self._bar_pixel_length = 0
             self._bar_text_label = ""
             logger.debug(f"Calculated scale bar pixel length {final_bar_pixel_length:.1f} too small, hiding bar.")
        else:
            self._bar_pixel_length = final_bar_pixel_length
            self._bar_text_label = self._format_length_value(chosen_real_world_length_m)
            logger.debug(f"Scale bar: Real length={chosen_real_world_length_m:.3g} m, Text='{self._bar_text_label}', Pixel length={self._bar_pixel_length:.1f} px")

        text_rect = self.font_metrics.boundingRect(self._bar_text_label)
        self._text_width = text_rect.width()
        self._text_height = text_rect.height()


    def minimumSizeHint(self) -> QtCore.QSize:
        """Provides a minimum size hint for layout purposes (though we position manually)."""
        width = int(max(self._bar_pixel_length + 2 * SCALE_BAR_BORDER_THICKNESS, self._text_width))
        height = self._calculate_widget_height()
        return QtCore.QSize(max(10, width), height)

    def sizeHint(self) -> QtCore.QSize:
        """Provides a preferred size hint."""
        return self.minimumSizeHint()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paints the scale bar and its label."""
        if not self.isVisible() or self._bar_pixel_length <= 0:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        widget_width = self.width()
        widget_height = self.height() # Fixed height

        # --- Draw Text ---
        # Position text centered horizontally, above the bar
        text_x = (widget_width - self._text_width) / 2
        text_y = self._text_height # Baseline or top of text
        painter.setPen(self._text_color)
        painter.drawText(QtCore.QPointF(text_x, text_y - self.font_metrics.descent()), self._bar_text_label)


        # --- Draw Scale Bar Rectangle ---
        # Position bar centered horizontally, below the text
        bar_start_x = (widget_width - self._bar_pixel_length) / 2
        bar_top_y = self._text_height + SCALE_BAR_TEXT_MARGIN_BOTTOM + SCALE_BAR_BORDER_THICKNESS

        bar_rect = QtCore.QRectF(
            bar_start_x,
            bar_top_y,
            self._bar_pixel_length,
            SCALE_BAR_RECT_HEIGHT
        )

        painter.setBrush(self._bar_color)
        pen = QtGui.QPen(self._border_color, SCALE_BAR_BORDER_THICKNESS)
        pen.setCosmetic(True) # Ensure border thickness is consistent regardless of painter scale
        painter.setPen(pen)
        painter.drawRect(bar_rect)

        # For debugging bounding box
        # painter.setPen(QtGui.QColor("red"))
        # painter.drawRect(self.rect().adjusted(0,0,-1,-1))

        painter.end()

# --- Example Usage (for testing the widget standalone) ---
if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)

    # Create a dummy parent view for context
    dummy_view = QtWidgets.QGraphicsView()
    dummy_view.setWindowTitle("Dummy Parent View")
    dummy_view.resize(800, 600)

    scale_bar = ScaleBarWidget(parent=dummy_view) # Parent it to the dummy view

    # --- Controls for testing ---
    test_window = QtWidgets.QWidget()
    test_layout = QtWidgets.QVBoxLayout(test_window)
    test_window.setWindowTitle("Scale Bar Test Controls")

    m_per_px_input = QtWidgets.QLineEdit("0.1") # Initial m/px_scene
    view_scale_input = QtWidgets.QLineEdit("1.0") # Initial view_scale_factor
    view_width_input = QtWidgets.QLineEdit(str(dummy_view.width())) # Initial parent_view_width

    test_layout.addWidget(QtWidgets.QLabel("Meters per Scene Pixel (at 1x zoom):"))
    test_layout.addWidget(m_per_px_input)
    test_layout.addWidget(QtWidgets.QLabel("View Scale Factor (Zoom):"))
    test_layout.addWidget(view_scale_input)
    test_layout.addWidget(QtWidgets.QLabel("Parent View Width (pixels):"))
    test_layout.addWidget(view_width_input)

    update_button = QtWidgets.QPushButton("Update Scale Bar")

    def on_update():
        try:
            mpp = float(m_per_px_input.text()) if m_per_px_input.text() else None
            vs = float(view_scale_input.text())
            vw = int(view_width_input.text())

            if mpp is not None and mpp <= 0: mpp = None # Treat non-positive as None

            # Position the scale bar at bottom right of dummy_view
            margin = 10
            bar_width_hint = scale_bar.sizeHint().width()
            bar_height_hint = scale_bar.sizeHint().height()

            # Update dimensions which also triggers internal calculations and visibility
            scale_bar.update_dimensions(mpp, vs, vw)

            # Only position if visible after update
            if scale_bar.isVisible():
                x_pos = dummy_view.viewport().width() - scale_bar.width() - margin
                y_pos = dummy_view.viewport().height() - scale_bar.height() - margin
                scale_bar.move(x_pos, y_pos)
                logger.debug(f"Moved scale_bar to ({x_pos}, {y_pos}), size: {scale_bar.size()}")

        except ValueError as e:
            logger.error(f"Invalid input for test: {e}")
            scale_bar.setVisible(False) # Hide on error

    update_button.clicked.connect(on_update)
    test_layout.addWidget(update_button)
    test_window.show()

    # Connect resize of dummy_view to update scale bar (specifically view width and position)
    def dummy_view_resized():
        view_width_input.setText(str(dummy_view.viewport().width())) # Update control
        on_update() # Re-calculate and re-position

    dummy_view.resizeEvent = lambda event: (
        QtWidgets.QGraphicsView.resizeEvent(dummy_view, event),
        dummy_view_resized()
    )

    dummy_view.show()
    on_update() # Initial update and positioning

    sys.exit(app.exec())