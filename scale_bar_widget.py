# scale_bar_widget.py
"""
Custom QWidget for displaying a dynamic scale bar on the InteractiveImageView.
"""
import logging
import math
import config # For ROUND_NUMBER_SEQUENCE etc.
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

import settings_manager

logger = logging.getLogger(__name__)

# --- Default/Fallback Constants for Scale Bar Appearance ---
# These are used if settings are not available or as initial defaults before settings load.
DEFAULT_SCALE_BAR_RECT_HEIGHT = 4  # Default height of the scale bar rectangle in pixels
DEFAULT_SCALE_BAR_FONT_SIZE_PT = 10 # Default font size for the text
FALLBACK_SCALE_BAR_BORDER_THICKNESS = 1 # Thickness of the border around the rectangle (currently not a setting)
SCALE_BAR_TEXT_MARGIN_BOTTOM = 2 # Space between text and top of scale bar rectangle
SCALE_BAR_DEFAULT_TARGET_FRACTION_OF_VIEW_WIDTH = 0.15
SCALE_BAR_MIN_PIXEL_WIDTH = 50
SCALE_BAR_MAX_PIXEL_WIDTH = 300

class ScaleBarWidget(QtWidgets.QWidget):
    _m_per_px_scene: Optional[float]
    _view_scale_factor: float
    _parent_view_width: int
    _bar_pixel_length: float
    _bar_text_label: str
    _text_width: int
    _text_height: int # Height of the text itself based on current font

    # Appearance attributes driven by settings
    _bar_color: QtGui.QColor
    _text_color: QtGui.QColor # Typically same as bar_color
    _border_color: QtGui.QColor # Currently fixed, could be a setting
    _current_font_size_pt: int
    _current_bar_rect_height: int

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setVisible(False)

        self._m_per_px_scene = None
        self._view_scale_factor = 1.0
        self._parent_view_width = 0
        self._bar_pixel_length = 0.0
        self._bar_text_label = ""
        self._text_width = 0
        self._text_height = 0
        
        # Initialize appearance from settings
        self._border_color = QtGui.QColor("black") # Fixed for now
        self.update_appearance_from_settings() # Load color, font size, bar height

        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        # Initial height calculation relies on settings loaded by update_appearance_from_settings
        self.setFixedHeight(self._calculate_widget_height())
        logger.debug(f"ScaleBarWidget initialized. Font: {self.font().family()} {self.font().pointSize()}pt, BarHeight: {self._current_bar_rect_height}px")

    def update_appearance_from_settings(self) -> None:
        """
        Updates the scale bar's appearance (color, font size, bar height)
        based on current values from settings_manager.
        """
        logger.debug("ScaleBarWidget: Updating appearance from settings.")
        # Get Color
        bar_color_setting = settings_manager.get_setting(settings_manager.KEY_SCALE_BAR_COLOR)
        if isinstance(bar_color_setting, QtGui.QColor) and bar_color_setting.isValid():
            self._bar_color = bar_color_setting
        elif isinstance(bar_color_setting, str):
            self._bar_color = QtGui.QColor(bar_color_setting)
            if not self._bar_color.isValid():
                self._bar_color = QtGui.QColor("white") # Fallback
        else:
            self._bar_color = QtGui.QColor("white") # Fallback
        self._text_color = self._bar_color # Text color matches bar color

        # Get Font Size
        self._current_font_size_pt = settings_manager.get_setting(settings_manager.KEY_SCALE_BAR_TEXT_FONT_SIZE)
        if not isinstance(self._current_font_size_pt, int) or self._current_font_size_pt <= 0:
            logger.warning(f"Invalid font size '{self._current_font_size_pt}' from settings. Using default.")
            self._current_font_size_pt = DEFAULT_SCALE_BAR_FONT_SIZE_PT
        
        current_font = self.font()
        current_font.setPointSize(self._current_font_size_pt)
        self.setFont(current_font) # Set widget's font
        self.font_metrics = QtGui.QFontMetrics(current_font) # Update font metrics

        # Get Bar Rectangle Height
        self._current_bar_rect_height = settings_manager.get_setting(settings_manager.KEY_SCALE_BAR_RECT_HEIGHT)
        if not isinstance(self._current_bar_rect_height, int) or self._current_bar_rect_height <= 0:
            logger.warning(f"Invalid bar rect height '{self._current_bar_rect_height}' from settings. Using default.")
            self._current_bar_rect_height = DEFAULT_SCALE_BAR_RECT_HEIGHT
        
        # Recalculate text dimensions and widget height as font/bar height might have changed
        if self._bar_text_label: # Re-measure text if a label exists
            text_rect = self.font_metrics.boundingRect(self._bar_text_label)
            self._text_width = text_rect.width()
            self._text_height = text_rect.height()

        new_widget_height = self._calculate_widget_height()
        if self.height() != new_widget_height:
            self.setFixedHeight(new_widget_height)
            logger.debug(f"ScaleBarWidget height set to {new_widget_height}px due to settings change.")

        if self.isVisible():
            self.update() # Trigger repaint

    def _calculate_widget_height(self) -> int:
        """Calculates the total height needed for the widget based on current font and bar height."""
        # self._text_height is based on current font_metrics (updated in update_appearance_from_settings)
        # self._current_bar_rect_height is from settings
        return self._text_height + SCALE_BAR_TEXT_MARGIN_BOTTOM + self._current_bar_rect_height + 2 * FALLBACK_SCALE_BAR_BORDER_THICKNESS

    def update_dimensions(self,
                          m_per_px_scene: Optional[float],
                          view_scale_factor: float,
                          parent_view_width: int) -> None:
        logger.debug(f"ScaleBarWidget update_dimensions: m/px_scene={m_per_px_scene}, view_scale={view_scale_factor}, view_width={parent_view_width}")
        visibility_changed = (self._m_per_px_scene is None and m_per_px_scene is not None) or \
                             (self._m_per_px_scene is not None and m_per_px_scene is None)

        self._m_per_px_scene = m_per_px_scene
        self._view_scale_factor = max(0.0001, view_scale_factor)
        self._parent_view_width = parent_view_width

        if self._m_per_px_scene is None or self._view_scale_factor <= 0:
            if self.isVisible(): # Only log if visibility actually changes
                logger.debug("Scale bar becoming hidden (no scene scale or invalid view scale).")
            self.setVisible(False)
            self._bar_pixel_length = 0
            self._bar_text_label = ""
        else:
            self._calculate_bar_length_and_label() # This updates _bar_pixel_length, _bar_text_label, _text_width, _text_height
            
            should_be_visible = self._bar_pixel_length > 0
            if self.isVisible() != should_be_visible:
                self.setVisible(should_be_visible)
                visibility_changed = True
                logger.debug(f"Scale bar visibility changed to: {should_be_visible}")

            if self.isVisible(): # If it's supposed to be visible
                required_widget_height = self._calculate_widget_height()
                if self.height() != required_widget_height:
                    self.setFixedHeight(required_widget_height)
                
                required_widget_width = int(max(self._bar_pixel_length + 2 * FALLBACK_SCALE_BAR_BORDER_THICKNESS, self._text_width))
                self.setFixedWidth(max(10, required_widget_width))
                self.update()
            elif visibility_changed: # Became hidden
                self.update() # Ensure it's cleared if it was visible and now isn't


    def _format_length_value(self, length_meters: float) -> str:
        if length_meters == 0:
            return "0 m"
        if abs(length_meters) >= config.SCIENTIFIC_NOTATION_UPPER_THRESHOLD or \
           (abs(length_meters) > 0 and abs(length_meters) <= config.SCIENTIFIC_NOTATION_LOWER_THRESHOLD) :
            return f"{length_meters:.1e}"
        for factor, singular_abbr, plural_abbr in config.UNIT_PREFIXES:
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
        if self._m_per_px_scene is None or self._view_scale_factor <= 0 or self._parent_view_width <= 0:
            self._bar_pixel_length = 0; self._bar_text_label = ""; self._text_width = 0; self._text_height = 0
            return

        m_per_view_pixel = self._m_per_px_scene / self._view_scale_factor
        target_bar_display_width_px = self._parent_view_width * SCALE_BAR_DEFAULT_TARGET_FRACTION_OF_VIEW_WIDTH
        target_bar_display_width_px = max(SCALE_BAR_MIN_PIXEL_WIDTH,
                                         min(target_bar_display_width_px, SCALE_BAR_MAX_PIXEL_WIDTH))
        target_real_world_length_m = target_bar_display_width_px * m_per_view_pixel

        if target_real_world_length_m <= 0:
            self._bar_pixel_length = 0; self._bar_text_label = ""; self._text_width = 0; self._text_height = 0
            return

        power_of_10 = 10.0 ** math.floor(math.log10(target_real_world_length_m))
        best_length_m = power_of_10 * config.ROUND_NUMBER_SEQUENCE[0]
        for R_val in config.ROUND_NUMBER_SEQUENCE:
            current_test_length_m = power_of_10 * R_val
            if current_test_length_m <= target_real_world_length_m * 1.05: # Allow slight overshoot
                best_length_m = current_test_length_m
            else:
                break
        if target_real_world_length_m < power_of_10 * config.ROUND_NUMBER_SEQUENCE[0] * 0.75 and power_of_10 > 1e-9 : # Avoid excessive shrinking
             power_of_10_smaller = power_of_10 / 10.0
             if power_of_10_smaller * config.ROUND_NUMBER_SEQUENCE[-1] > 1e-9: # ensure positive length
                best_length_m = power_of_10_smaller * config.ROUND_NUMBER_SEQUENCE[-1]


        chosen_real_world_length_m = best_length_m
        final_bar_pixel_length = chosen_real_world_length_m / m_per_view_pixel

        if final_bar_pixel_length < SCALE_BAR_MIN_PIXEL_WIDTH / 2.0:
             self._bar_pixel_length = 0; self._bar_text_label = ""
             logger.debug(f"Calculated scale bar pixel length {final_bar_pixel_length:.1f} too small, hiding bar.")
        else:
            self._bar_pixel_length = final_bar_pixel_length
            self._bar_text_label = self._format_length_value(chosen_real_world_length_m)
            logger.debug(f"Scale bar: Real length={chosen_real_world_length_m:.3g} m, Text='{self._bar_text_label}', Pixel length={self._bar_pixel_length:.1f} px")
        
        # Update text dimensions based on current font (set in update_appearance_from_settings)
        text_rect = self.font_metrics.boundingRect(self._bar_text_label)
        self._text_width = text_rect.width()
        self._text_height = text_rect.height() # This is height of the text itself

    def minimumSizeHint(self) -> QtCore.QSize:
        width = int(max(self._bar_pixel_length + 2 * FALLBACK_SCALE_BAR_BORDER_THICKNESS, self._text_width))
        height = self._calculate_widget_height()
        return QtCore.QSize(max(10, width), height)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSizeHint()

    def set_bar_color(self, color: QtGui.QColor) -> None: # Kept for direct color changes if needed by MainWindow
        if color.isValid():
            self._bar_color = color
            self._text_color = color
            if self.isVisible():
                self.update()
            logger.debug(f"ScaleBarWidget color set directly to: {color.name()}")


    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if not self.isVisible() or self._bar_pixel_length <= 0:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        current_font = self.font() # Font is already set by update_appearance_from_settings
        painter.setFont(current_font) # Ensure painter uses the widget's current font

        widget_width = self.width()
        # widget_height is self.height(), managed by setFixedHeight

        # --- Draw Text ---
        # self._text_height is already calculated based on current font.
        text_x = (widget_width - self._text_width) / 2.0
        # Position text baseline correctly. text_y is the y-coordinate for drawText's QPointF,
        # which refers to the bottom-left of the text's bounding box if not aligned.
        # For alignment, it's simpler to use the full height of the text from font_metrics.
        text_baseline_y = float(self._text_height) # Y position for the baseline of the text
        painter.setPen(self._text_color)
        # Using QPointF for potentially fractional positions for better centering.
        # Draw text such that its bounding box top is at 0, then the bar is below it.
        painter.drawText(QtCore.QPointF(text_x, text_baseline_y - self.font_metrics.descent()), self._bar_text_label)


        # --- Draw Scale Bar Rectangle ---
        bar_start_x = (widget_width - self._bar_pixel_length) / 2.0
        # Bar is positioned below the text and its margin
        bar_top_y = float(self._text_height + SCALE_BAR_TEXT_MARGIN_BOTTOM + FALLBACK_SCALE_BAR_BORDER_THICKNESS)

        bar_rect = QtCore.QRectF(
            bar_start_x,
            bar_top_y,
            self._bar_pixel_length,
            float(self._current_bar_rect_height) # Use the setting for bar height
        )

        painter.setBrush(self._bar_color)
        # Border thickness is currently fixed, but pen width uses it.
        pen = QtGui.QPen(self._border_color, FALLBACK_SCALE_BAR_BORDER_THICKNESS)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(bar_rect)
        painter.end()

# Example Usage (unchanged, but will now reflect new settings if defaults are modified)
if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    dummy_view = QtWidgets.QGraphicsView()
    dummy_view.setWindowTitle("Dummy Parent View")
    dummy_view.resize(800, 600)
    scale_bar = ScaleBarWidget(parent=dummy_view)
    test_window = QtWidgets.QWidget()
    test_layout = QtWidgets.QVBoxLayout(test_window)
    test_window.setWindowTitle("Scale Bar Test Controls")
    m_per_px_input = QtWidgets.QLineEdit("0.1")
    view_scale_input = QtWidgets.QLineEdit("1.0")
    view_width_input = QtWidgets.QLineEdit(str(dummy_view.width()))
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
            if mpp is not None and mpp <= 0: mpp = None
            margin = 10
            scale_bar.update_dimensions(mpp, vs, vw) # This will now use settings for height/font
            if scale_bar.isVisible():
                # Re-fetch widget width/height after update_dimensions as it might change
                current_bar_width = scale_bar.width()
                current_bar_height = scale_bar.height()
                x_pos = dummy_view.viewport().width() - current_bar_width - margin
                y_pos = dummy_view.viewport().height() - current_bar_height - margin
                scale_bar.move(x_pos, y_pos)
                logger.debug(f"Moved scale_bar to ({x_pos}, {y_pos}), size: {scale_bar.size()}")
        except ValueError as e:
            logger.error(f"Invalid input for test: {e}")
            scale_bar.setVisible(False)
    update_button.clicked.connect(on_update)
    test_layout.addWidget(update_button)
    test_window.show()
    def dummy_view_resized_event(event): # Capture the event argument
        QtWidgets.QGraphicsView.resizeEvent(dummy_view, event) # Call base class method
        view_width_input.setText(str(dummy_view.viewport().width()))
        on_update()
    dummy_view.resizeEvent = dummy_view_resized_event
    dummy_view.show()
    on_update()
    sys.exit(app.exec())