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

    # --- Placeholder for future transformation methods ---
    def transform_value_for_display(self, value_px: float) -> Tuple[float, str]:
        """
        Transforms a pixel value to the current display unit (px or m).
        Returns the transformed value and the unit string.
        (To be fully implemented in the next phase)
        """
        if self._display_in_meters and self._scale_m_per_px is not None:
            # return value_px * self._scale_m_per_px, "m" # Actual transformation
            return value_px, "m (scaled)" # Placeholder
        return value_px, "px"

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