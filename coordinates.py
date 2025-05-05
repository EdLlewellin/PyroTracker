# coordinates.py
"""
Handles coordinate system definitions and transformations for PyroTracker.

Defines the available coordinate systems and provides a class to manage
the current system state and perform transformations between the internal
Top-Left (TL) system and the user-selected display/storage system.
"""

import logging
from enum import Enum, auto
from typing import Tuple, Dict, Any, Optional

# Get a logger for this module
logger = logging.getLogger(__name__)

# --- Coordinate System Definition ---

class CoordinateSystem(Enum):
    """Defines the available coordinate system modes."""
    TOP_LEFT = auto()      # Origin at (0,0), Y increases downwards (Internal standard)
    BOTTOM_LEFT = auto()   # Origin at (0, video_height), Y increases upwards
    CUSTOM = auto()        # Origin at user-defined (x,y) TL point, Y increases upwards

    def __str__(self) -> str:
        """Return the string representation used for saving/loading (e.g., "TOP_LEFT")."""
        return self.name

    @classmethod
    def from_string(cls, mode_str: str) -> Optional['CoordinateSystem']:
        """Convert a string (e.g., from metadata) back to an enum member."""
        try:
            return cls[mode_str.upper()]
        except KeyError:
            logger.warning(f"Could not convert string '{mode_str}' to CoordinateSystem enum.")
            return None


# --- Coordinate Transformer Class ---

class CoordinateTransformer:
    """
    Manages the current coordinate system and performs transformations.

    Stores the selected mode, custom origin (always in internal TL coordinates),
    and video height. Provides methods to transform points between the internal
    Top-Left system and the current display/storage system, and also
    to transform points from a specified source system back to internal TL.
    """
    _mode: CoordinateSystem
    _origin_x_tl: float  # X coordinate of the custom origin (Top-Left system)
    _origin_y_tl: float  # Y coordinate of the custom origin (Top-Left system)
    _video_height: int   # Height of the video in pixels (required for Y inversion)

    def __init__(self) -> None:
        """Initializes the transformer to the default state (Top-Left)."""
        self._mode = CoordinateSystem.TOP_LEFT
        self._origin_x_tl = 0.0
        self._origin_y_tl = 0.0
        self._video_height = 0 # Must be set via set_video_height() after loading video
        logger.info(f"CoordinateTransformer initialized (Mode: {self._mode}, Origin TL: ({self._origin_x_tl}, {self._origin_y_tl}), Height: {self._video_height})")

    def set_video_height(self, height: int) -> None:
        """Sets the video height, required for Y-axis inversion in BL/Custom modes."""
        if height > 0:
            self._video_height = height
            logger.debug(f"CoordinateTransformer video height set to: {height}")
        else:
            logger.warning(f"Attempted to set invalid video height: {height}. Transformations requiring height may be inaccurate.")

    def set_mode(self, mode: CoordinateSystem) -> None:
        """Sets the current coordinate system mode."""
        if self._mode != mode:
            logger.info(f"Changing coordinate system mode from {self._mode} to {mode}")
            self._mode = mode
        else:
            logger.debug(f"Coordinate system mode already set to {mode}")

    def set_custom_origin(self, x_tl: float, y_tl: float) -> None:
        """
        Sets the custom origin using coordinates from the Top-Left system.
        Implicitly sets the mode to CUSTOM.
        """
        logger.info(f"Setting custom origin (TL coords) to ({x_tl:.3f}, {y_tl:.3f})")
        self._origin_x_tl = round(x_tl, 3) # Store rounded coordinates
        self._origin_y_tl = round(y_tl, 3)
        self.set_mode(CoordinateSystem.CUSTOM) # Setting a custom origin implies CUSTOM mode

    def get_current_origin_tl(self) -> Tuple[float, float]:
        """
        Calculates and returns the effective origin coordinates in the Top-Left
        system based on the current mode and stored custom origin.
        """
        if self._mode == CoordinateSystem.TOP_LEFT:
            return (0.0, 0.0)
        elif self._mode == CoordinateSystem.BOTTOM_LEFT:
            # Ensure video height is valid
            if self._video_height <= 0:
                 logger.warning("Cannot calculate Bottom-Left origin: Video height not set or invalid.")
                 return (0.0, 0.0) # Fallback to Top-Left origin
            return (0.0, float(self._video_height))
        elif self._mode == CoordinateSystem.CUSTOM:
            return (self._origin_x_tl, self._origin_y_tl)
        else:
             # Should not happen with Enum
             logger.error(f"Invalid coordinate system mode encountered: {self._mode}")
             return (0.0, 0.0) # Fallback

    def transform_point_for_display(self, x_tl: float, y_tl: float) -> Tuple[float, float]:
        """
        Converts internal Top-Left coordinates (x_tl, y_tl) to the display/storage
        coordinates based on the *current* transformer state (mode, origin, height).
        """
        ox_tl, oy_tl = self.get_current_origin_tl()

        # Calculate coordinates relative to the effective origin
        rel_x = x_tl - ox_tl
        rel_y = y_tl - oy_tl

        # Apply Y-axis inversion if the display/storage system is not Top-Left
        if self._mode != CoordinateSystem.TOP_LEFT:
            display_y = -rel_y
        else:
            display_y = rel_y

        # Display X is the same as relative X in all cases
        display_x = rel_x

        return (round(display_x, 3), round(display_y, 3))

    def transform_point_to_internal(self, x_display: float, y_display: float,
                                    source_mode: CoordinateSystem,
                                    source_origin_tl: Tuple[float, float],
                                    source_video_height: int) -> Tuple[float, float]:
        """
        Converts display coordinates (x_display, y_display) from a specified
        source system back to internal Top-Left coordinates. Used when loading data.

        Args:
            x_display: X coordinate in the source display system.
            y_display: Y coordinate in the source display system.
            source_mode: The CoordinateSystem mode of the source data.
            source_origin_tl: The (x, y) origin of the source system, given in TL coordinates.
            source_video_height: The video height associated with the source system.

        Returns:
            A tuple (x_tl, y_tl) representing the coordinates in the internal Top-Left system.
        """
        ox_tl, oy_tl = source_origin_tl

        # Invert the Y coordinate transformation based on the source mode
        if source_mode != CoordinateSystem.TOP_LEFT:
            # If source is Bottom-Left but height is invalid, the source origin y (oy_tl)
            # might be incorrect. Log a warning and proceed, but result may be inaccurate.
            if source_video_height <= 0 and source_mode == CoordinateSystem.BOTTOM_LEFT:
                 logger.warning("Cannot reliably transform Y from Bottom-Left: "
                                "Source video height missing/invalid in CSV. Using potentially incorrect origin.")
                 # The original oy_tl from source_origin_tl will be used, but it might be wrong if height was needed.

            rel_y = -y_display # Invert back from display Y to relative Y (TL direction)
        else:
            rel_y = y_display # No inversion needed for Top-Left source

        # Calculate absolute Top-Left coordinates by adding the source origin
        x_tl = x_display + ox_tl
        y_tl = rel_y + oy_tl

        return (round(x_tl, 3), round(y_tl, 3))

    def get_metadata(self) -> Dict[str, Any]:
        """
        Returns a dictionary containing the current coordinate system settings
        suitable for saving to metadata. Includes mode, TL origin, and height.
        """
        # Always save the stored custom origin (in TL) and video height,
        # regardless of current mode, for potential restoration on load.
        return {
            "mode": str(self._mode),
            "origin_x_tl": self._origin_x_tl,
            "origin_y_tl": self._origin_y_tl,
            "video_height": self._video_height # Preserves context for Y-inversion
        }

    # --- Properties for easier access to state ---
    @property
    def mode(self) -> CoordinateSystem:
        """Returns the currently active coordinate system mode."""
        return self._mode

    @property
    def video_height(self) -> int:
        """Returns the currently set video height."""
        return self._video_height