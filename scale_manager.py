# scale_manager.py
"""
Manages scale factor, display units, and performs scale transformations.
"""
import logging
from typing import Optional, Tuple
from PySide6 import QtCore

logger = logging.getLogger(__name__)

class ScaleManager(QtCore.QObject):
    """
    Manages the current scale factor (meters per pixel) and preferred display units.
    Provides methods to set the scale, get the scale, and (eventually) transform values.
    """
    # Signal to notify when the scale or display unit changes,
    # prompting UI updates for displayed values.
    scaleOrUnitChanged = QtCore.Signal()

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._scale_m_per_px: Optional[float] = None
        self._display_in_meters: bool = False
        logger.debug("ScaleManager initialized.")

    def set_scale(self, m_per_px: Optional[float]) -> None:
        """
        Sets the scale factor in meters per pixel.
        If None, scale is considered unset.
        """
        if m_per_px is not None and m_per_px <= 0:
            logger.warning(f"Attempted to set invalid scale: {m_per_px}. Scale not set.")
            new_scale = None
        else:
            new_scale = m_per_px

        if self._scale_m_per_px != new_scale:
            self._scale_m_per_px = new_scale
            logger.info(f"Scale set to: {self._scale_m_per_px} m/px.")
            if self._scale_m_per_px is None:
                # If scale is removed, force display back to pixels
                self.set_display_in_meters(False)
            self.scaleOrUnitChanged.emit()

    def get_scale_m_per_px(self) -> Optional[float]:
        """Returns the current scale in meters per pixel, or None if not set."""
        return self._scale_m_per_px

    def set_display_in_meters(self, display_meters: bool) -> None:
        """Sets whether to display values in meters."""
        # Only allow setting to meters if a scale is actually set
        if display_meters and self._scale_m_per_px is None:
            logger.warning("Cannot set display to meters: No scale is set. Forcing to pixels.")
            effective_display_meters = False
        else:
            effective_display_meters = display_meters

        if self._display_in_meters != effective_display_meters:
            self._display_in_meters = effective_display_meters
            logger.info(f"Display units set to: {'meters' if self._display_in_meters else 'pixels'}.")
            self.scaleOrUnitChanged.emit()

    def display_in_meters(self) -> bool:
        """Returns True if values should be displayed in meters, False for pixels."""
        return self._display_in_meters

    def get_reciprocal_scale_px_per_m(self) -> Optional[float]:
        """Calculates and returns pixels per meter, or None if scale is not set."""
        if self._scale_m_per_px is not None and self._scale_m_per_px > 0:
            return 1.0 / self._scale_m_per_px
        return None

    def transform_value_for_display(self, value_px: float) -> Tuple[float, str]:
        """
        Transforms a pixel value to the current display unit (px or m).
        Returns the transformed value and the unit string.
        """
        unit_str = "px"
        transformed_value = value_px

        if self._display_in_meters and self._scale_m_per_px is not None and self._scale_m_per_px > 0:
            try:
                transformed_value = value_px * self._scale_m_per_px
                unit_str = "m"
            except TypeError:
                logger.error(f"TypeError during scaling. Value: {value_px}, Scale: {self._scale_m_per_px}")
                # Fallback to pixels
                transformed_value = value_px
                unit_str = "px"
        
        # Apply rounding based on unit
        if unit_str == "m":
            # For meters, 4 decimal places (0.1 mm precision) seems reasonable
            return round(transformed_value, 4), unit_str
        else:
            # For pixels, typically 2-3 decimal places is sufficient if they are floats
            return round(transformed_value, 3), unit_str

    def get_transformed_coordinates_for_display(self, x_px: float, y_px: float) -> Tuple[float, float, str]:
        """
        Transforms pixel coordinates (x,y) to the current display unit.
        Returns (transformed_x, transformed_y, unit_string).
        """
        # Default to pixels
        unit_str = "px"
        display_x = x_px
        display_y = y_px

        if self._display_in_meters and self._scale_m_per_px is not None and self._scale_m_per_px > 0:
            try:
                display_x = x_px * self._scale_m_per_px
                display_y = y_px * self._scale_m_per_px
                unit_str = "m"
            except TypeError:
                logger.error(f"TypeError during coordinate scaling. Values: ({x_px}, {y_px}), Scale: {self._scale_m_per_px}")
                # Fallback to pixels
                display_x = x_px
                display_y = y_px
                unit_str = "px"
        
        # Apply rounding based on unit
        if unit_str == "m":
            return round(display_x, 4), round(display_y, 4), unit_str
        else:
            return round(display_x, 3), round(display_y, 3), unit_str

    def get_display_unit_short(self) -> str:
        """Returns 'm' or 'px' based on current display setting."""
        return "m" if self._display_in_meters and self._scale_m_per_px is not None else "px"

    def reset(self) -> None:
        """Resets the scale and display unit to defaults."""
        logger.debug("Resetting ScaleManager.")
        changed = self._scale_m_per_px is not None or self._display_in_meters
        self._scale_m_per_px = None
        self._display_in_meters = False # Default to pixels
        if changed:
            self.scaleOrUnitChanged.emit()