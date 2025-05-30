# scale_manager.py
"""
Manages scale factor, display units, and performs scale transformations.
Also stores information about a user-defined scale line, if set.
"""
import logging
from typing import Optional, Tuple
from PySide6 import QtCore

logger = logging.getLogger(__name__)

class ScaleManager(QtCore.QObject):
    """
    Manages the current scale factor (meters per pixel), preferred display units,
    and the data for a user-defined scale line.
    Provides methods to set the scale, get the scale, and transform values.
    """
    # Signal to notify when the scale, display unit, or defined scale line state changes,
    # prompting UI updates.
    scaleOrUnitChanged = QtCore.Signal()

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._scale_m_per_px: Optional[float] = None
        self._display_in_meters: bool = False
        # --- NEW: Store defined scale line points (scene coordinates) ---
        # Format: (p1x, p1y, p2x, p2y) or None if not set
        self._defined_scale_line_data: Optional[Tuple[float, float, float, float]] = None
        logger.debug("ScaleManager initialized.")

    def set_scale(self, m_per_px: Optional[float], called_from_line_definition: bool = False) -> None:
        """
        Sets the scale factor in meters per pixel.
        If None, scale is considered unset.
        Optionally clears defined scale line data if not called from line definition process.

        Args:
            m_per_px: The scale factor, or None to clear.
            called_from_line_definition: Internal flag to prevent clearing the defined
                                          line when setting scale *from* that line.
        """
        if m_per_px is not None and m_per_px <= 0:
            logger.warning(f"Attempted to set invalid scale: {m_per_px}. Scale not set.")
            new_scale = None
        else:
            new_scale = m_per_px

        scale_changed = (self._scale_m_per_px != new_scale)

        if scale_changed:
            self._scale_m_per_px = new_scale
            logger.info(f"Scale factor set to: {self._scale_m_per_px} m/px.") # Existing log

            if self._scale_m_per_px is None: # Scale is being cleared
                # These methods will emit scaleOrUnitChanged if they cause a relevant state change.
                self.set_display_in_meters(False)
                self.clear_defined_scale_line()
            else: # Scale is being set to a new valid value
                if not called_from_line_definition:
                    # If setting scale manually, and not as part of defining a line,
                    # any previously defined line (which might now be inconsistent) should be cleared.
                    # clear_defined_scale_line() will emit if it actually removes a defined line.
                    self.clear_defined_scale_line()
                # If called_from_line_definition is True, set_defined_scale_line() would be called
                # elsewhere and would handle its own emission if the line data changed.

            # Explicitly emit the signal if the core scale value has changed.
            # This ensures that listeners are notified of the scale change itself,
            # even if helper methods like clear_defined_scale_line didn't emit
            # (e.g., because there was no line to clear).
            self.scaleOrUnitChanged.emit()
            logger.debug("Emitted scaleOrUnitChanged due to scale_changed=True in set_scale.")

        # No 'else' needed; if scale_changed is False, no action or signal is necessary from here.

    # --- Convenience overload for setting scale internally ---
    def _set_scale_from_line_definition(self, m_per_px: Optional[float]) -> None:
        """Internal method to set scale factor when defined by line, avoids clearing line data."""
        self.set_scale(m_per_px, called_from_line_definition=True)

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

    # --- NEW: Methods for managing the defined scale line ---

    def set_defined_scale_line(self, p1x: float, p1y: float, p2x: float, p2y: float) -> None:
        """
        Stores the coordinates of the line used to define the scale.
        Rounds coordinates for storage. Emits scaleOrUnitChanged if the
        presence state changes (from None to having data).
        """
        # Round coordinates to maintain reasonable precision for storage/comparison
        new_data = (round(p1x, 3), round(p1y, 3), round(p2x, 3), round(p2y, 3))
        if self._defined_scale_line_data != new_data:
            was_none = self._defined_scale_line_data is None
            self._defined_scale_line_data = new_data
            logger.info(f"Stored defined scale line data: {self._defined_scale_line_data}")
            # Emit only if state changed from None to having data, as this affects the checkbox availability
            if was_none:
                self.scaleOrUnitChanged.emit()

    def clear_defined_scale_line(self) -> None:
        """
        Clears the stored defined scale line data.
        Emits scaleOrUnitChanged if the state changes (from having data to None).
        """
        if self._defined_scale_line_data is not None:
            logger.info("Clearing defined scale line data.")
            self._defined_scale_line_data = None
            # Emit signal because the state relevant to the 'Show scale line' checkbox changed
            self.scaleOrUnitChanged.emit()

    def has_defined_scale_line(self) -> bool:
        """Returns True if a scale line has been defined and stored."""
        return self._defined_scale_line_data is not None

    def get_defined_scale_line_data(self) -> Optional[Tuple[float, float, float, float]]:
        """Returns the stored scale line points (p1x, p1y, p2x, p2y), or None."""
        # Tuple is immutable, so no need to return a copy
        return self._defined_scale_line_data

    # --- End NEW Methods ---

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

    def get_transformed_coordinates_for_display(self, x_px: float, y_px: float, force_meters: bool = False) -> Tuple[float, float, str]:
        """
        Transforms pixel coordinates (x,y) to the display unit or forced meters.
        Returns (transformed_x, transformed_y, unit_string).
        """
        unit_str = "px"
        display_x = x_px
        display_y = y_px

        should_convert_to_meters = (self._display_in_meters or force_meters)

        if should_convert_to_meters and self._scale_m_per_px is not None and self._scale_m_per_px > 0:
            try:
                display_x = x_px * self._scale_m_per_px
                display_y = y_px * self._scale_m_per_px
                unit_str = "m"
            except TypeError:
                logger.error(f"TypeError during coordinate scaling. Values: ({x_px}, {y_px}), Scale: {self._scale_m_per_px}")
                display_x = x_px # Fallback
                display_y = y_px # Fallback
                unit_str = "px"

        # Apply rounding based on actual unit of display_x, display_y
        if unit_str == "m":
            # For meters, 4 decimal places (e.g., 0.0001 m = 0.1 mm)
            return round(display_x, 4), round(display_y, 4), unit_str
        else:
            # For pixels, 2 decimal places
            return round(display_x, 2), round(display_y, 2), unit_str

    def get_display_unit_short(self) -> str:
        """Returns 'm' or 'px' based on current display setting."""
        return "m" if self._display_in_meters and self._scale_m_per_px is not None else "px"

    def reset(self) -> None:
        """Resets the scale, display unit, and defined scale line to defaults."""
        logger.debug("Resetting ScaleManager.")
        # Check if *any* state that affects UI is changing before emitting signal
        scale_was_set = self._scale_m_per_px is not None
        was_displaying_meters = self._display_in_meters
        line_was_defined = self.has_defined_scale_line()

        state_changed = scale_was_set or was_displaying_meters or line_was_defined

        self._scale_m_per_px = None
        self._display_in_meters = False # Default to pixels
        # Don't call clear_defined_scale_line directly here to avoid double signal emission
        # if state_changed is True anyway. Just set the attribute.
        self._defined_scale_line_data = None

        # Emit signal only if scale, units, or line state *actually* changed
        if state_changed:
             self.scaleOrUnitChanged.emit()