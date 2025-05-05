# track_manager.py
"""
Manages pyroclast track data, including points, visibility states,
and the active track selection. Calculates visual elements (markers, lines)
required for rendering based on current state and frame, but does not draw.
"""
import logging
from collections import defaultdict
from enum import Enum, auto
from typing import List, Tuple, Dict, Optional, Any # Removed TYPE_CHECKING

from PySide6 import QtCore

import config

logger = logging.getLogger(__name__)

# --- Type Aliases ---
PointData = Tuple[int, float, float, float]
"""Type alias for a single point's data: (frame_index, time_ms, x, y)"""
Track = List[PointData]
"""Type alias for a single track, represented as a list of PointData tuples."""
AllTracksData = List[Track]
"""Type alias for all track data, a list of individual Tracks."""
VisualElement = Dict[str, Any]
"""Type alias for the visual element structure passed for drawing.
   e.g., {'type': 'marker', 'pos': (x,y), 'style': STYLE_*, 'track_id': int}"""

class TrackVisibilityMode(Enum):
    """Enum defining the visibility modes for tracks."""
    HIDDEN = auto()         # Track is completely hidden
    INCREMENTAL = auto()    # Points/lines visible up to the current frame
    ALWAYS_VISIBLE = auto() # Entire track is always visible

class TrackManager(QtCore.QObject):
    """
    Manages pyroclast track data and calculates visual representation.

    Handles creating, deleting, loading, and saving tracks. Calculates *what*
    needs to be drawn based on visibility modes and emits signals to notify
    the UI of changes. Does NOT perform any drawing itself.
    """
    # --- Signals ---
    trackListChanged = QtCore.Signal()
    """Emitted when the list of tracks changes (add, delete, load, visibility change)."""
    activeTrackDataChanged = QtCore.Signal()
    """Emitted when the data (points) of the currently active track changes, or the active track itself changes."""
    visualsNeedUpdate = QtCore.Signal()
    """Emitted when the visual representation of tracks might need updating (e.g., point added/deleted to visible track, visibility change, active track change)."""

    # --- Instance Variables ---
    # Store track points: List[List[Tuple[frame_idx, time_ms, x, y]]]
    tracks: AllTracksData
    # Store visibility mode for each track, parallel to self.tracks
    track_visibility_modes: List[TrackVisibilityMode]
    # 0-based index of the currently active track, -1 if none
    active_track_index: int
    # -------------------------

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        """Initializes the TrackManager with empty track lists."""
        super().__init__(parent)
        logger.info("Initializing TrackManager...")
        self.tracks = []
        self.track_visibility_modes = []
        self.active_track_index = -1
        logger.info("TrackManager initialized.")

    def reset(self) -> None:
        """Clears all track data, visibility modes, and resets active track."""
        logger.info("Resetting TrackManager state...")
        self.tracks = []
        self.track_visibility_modes = []
        self.active_track_index = -1
        logger.info("TrackManager reset complete.")
        logger.debug("Emitting trackListChanged and activeTrackDataChanged after reset.")
        self.trackListChanged.emit()
        self.activeTrackDataChanged.emit()
        # No need to emit visualsNeedUpdate on reset, as there's nothing to draw.

    def create_new_track(self) -> int:
        """
        Adds a new, empty track with default visibility (INCREMENTAL).
        Makes the new track active.

        Returns:
            The 1-based ID of the newly created track.
        """
        logger.info("Creating new track...")
        new_track_list: Track = []
        self.tracks.append(new_track_list)
        self.track_visibility_modes.append(TrackVisibilityMode.INCREMENTAL) # Default visibility
        new_track_index: int = len(self.tracks) - 1
        self.set_active_track(new_track_index) # Will set index and emit signals
        new_track_id: int = new_track_index + 1
        logger.info(f"Created new track {new_track_id} (index {new_track_index}).")
        logger.debug("Emitting trackListChanged after creating new track.")
        self.trackListChanged.emit() # Notify table of tracks
        return new_track_id

    def delete_track(self, track_index_to_delete: int) -> bool:
        """
        Deletes the track at the specified 0-based index.
        Adjusts the active track index if necessary. Emits appropriate signals.

        Args:
            track_index_to_delete: The 0-based index of the track to delete.

        Returns:
            True if deletion was successful, False otherwise (e.g., invalid index).
        """
        if not (0 <= track_index_to_delete < len(self.tracks)):
            logger.error(f"Cannot delete track: Index {track_index_to_delete} is out of bounds (0-{len(self.tracks)-1}).")
            return False

        track_id_deleted: int = track_index_to_delete + 1
        logger.info(f"Deleting track index {track_index_to_delete} (ID: {track_id_deleted})...")
        was_visible = self.get_track_visibility_mode(track_index_to_delete) != TrackVisibilityMode.HIDDEN

        del self.tracks[track_index_to_delete]
        del self.track_visibility_modes[track_index_to_delete]
        logger.debug(f"Removed track data and visibility mode for index {track_index_to_delete}.")

        active_track_changed: bool = False
        # Adjust active index if the deleted track was active or before the active one
        if self.active_track_index == track_index_to_delete:
            logger.info(f"Deleted track {track_id_deleted} was active. Resetting active index to -1.")
            self.active_track_index = -1
            active_track_changed = True
        elif self.active_track_index > track_index_to_delete:
            old_active: int = self.active_track_index
            self.active_track_index -= 1
            logger.info(f"Active track index shifted down from {old_active} to {self.active_track_index} due to deletion.")
            active_track_changed = True

        logger.debug("Emitting trackListChanged after deletion.")
        self.trackListChanged.emit()
        if active_track_changed:
            logger.debug("Emitting activeTrackDataChanged after deletion due to active index change.")
            self.activeTrackDataChanged.emit()
        if was_visible:
            logger.debug("Emitting visualsNeedUpdate after deleting a potentially visible track.")
            self.visualsNeedUpdate.emit()

        logger.info(f"Track {track_id_deleted} deleted successfully.")
        return True

    def set_active_track(self, track_index: int) -> None:
        """
        Sets the active track by its 0-based index (-1 for none).
        Emits signals only if the active track actually changes.
        """
        new_active_index: int = -1
        if 0 <= track_index < len(self.tracks):
            new_active_index = track_index
        elif track_index == -1:
            new_active_index = -1 # Explicitly allow setting to none
        else:
            logger.warning(f"Invalid track index {track_index} passed to set_active_track. Total tracks: {len(self.tracks)}. Ignoring.")
            return

        if self.active_track_index != new_active_index:
            old_active_index: int = self.active_track_index
            old_mode: TrackVisibilityMode = self.get_track_visibility_mode(old_active_index)

            self.active_track_index = new_active_index
            new_mode: TrackVisibilityMode = self.get_track_visibility_mode(new_active_index)

            logger.info(f"Set active track index to {self.active_track_index} (ID: {self.get_active_track_id()})")
            logger.debug("Emitting activeTrackDataChanged due to active track change.")
            self.activeTrackDataChanged.emit() # Update points table etc.

            # Update visuals if the old or new active track could be visible
            if old_mode != TrackVisibilityMode.HIDDEN or new_mode != TrackVisibilityMode.HIDDEN:
                 logger.debug(f"Emitting visualsNeedUpdate because old ({old_mode.name}) or new ({new_mode.name}) active track might be visible.")
                 self.visualsNeedUpdate.emit()

    def set_track_visibility_mode(self, track_index: int, mode: TrackVisibilityMode) -> None:
        """Sets the visibility mode for a specific track by 0-based index."""
        if not (0 <= track_index < len(self.track_visibility_modes)):
            logger.warning(f"Invalid track index {track_index} for setting visibility. Ignoring.")
            return

        if self.track_visibility_modes[track_index] != mode:
            old_mode: TrackVisibilityMode = self.track_visibility_modes[track_index]
            self.track_visibility_modes[track_index] = mode
            track_id: int = track_index + 1
            logger.info(f"Set visibility for track {track_id} (index {track_index}) to {mode.name}")
            # Need visual update if either old or new mode wasn't hidden
            if old_mode != TrackVisibilityMode.HIDDEN or mode != TrackVisibilityMode.HIDDEN:
                logger.debug("Emitting visualsNeedUpdate due to visibility mode change for a potentially visible track.")
                self.visualsNeedUpdate.emit()
            # Also emit trackListChanged as the track's status in the list might change (e.g., icon)
            self.trackListChanged.emit()


    def get_track_visibility_mode(self, track_index: int) -> TrackVisibilityMode:
        """Gets the visibility mode for a specific track. Returns HIDDEN for invalid indices."""
        if 0 <= track_index < len(self.track_visibility_modes):
            return self.track_visibility_modes[track_index]
        # logger.debug(f"get_track_visibility_mode called for invalid index {track_index}, returning HIDDEN as fallback.")
        return TrackVisibilityMode.HIDDEN # Safe fallback

    def set_all_tracks_visibility(self, mode: TrackVisibilityMode) -> None:
        """Sets the visibility mode for ALL existing tracks."""
        if not self.tracks:
             logger.debug("set_all_tracks_visibility called, but no tracks exist.")
             return

        logger.info(f"Setting visibility for ALL {len(self.tracks)} tracks to {mode.name}...")
        changed: bool = False
        needs_visual_update: bool = False
        for i in range(len(self.track_visibility_modes)):
            old_mode: TrackVisibilityMode = self.track_visibility_modes[i]
            if old_mode != mode:
                self.track_visibility_modes[i] = mode
                changed = True
                # Check if this specific change requires a visual update
                if old_mode != TrackVisibilityMode.HIDDEN or mode != TrackVisibilityMode.HIDDEN:
                    needs_visual_update = True

        if changed:
            logger.debug("Visibility changed for at least one track. Emitting trackListChanged.")
            self.trackListChanged.emit() # Update track table icons/state
        if needs_visual_update:
            logger.debug("Visual update needed due to visibility change. Emitting visualsNeedUpdate.")
            self.visualsNeedUpdate.emit() # Update graphics view
        if not changed:
             logger.debug("All tracks were already in the target visibility mode. No changes made.")

    def get_active_track_id(self) -> int:
         """Returns the 1-based ID of the active track, or -1 if no track is active."""
         return self.active_track_index + 1 if self.active_track_index != -1 else -1

    def add_point(self, frame_index: int, time_ms: float, x: float, y: float) -> bool:
        """
        Adds or updates a point for the currently active track at the given frame index.
        Rounds coordinates to 3 decimal places. Maintains sorted order of points
        within the track by frame index using list.sort().

        Args:
            frame_index: 0-based index of the frame for this point.
            time_ms: Timestamp of the frame in milliseconds.
            x: X-coordinate (scene coordinates).
            y: Y-coordinate (scene coordinates).

        Returns:
            True if the point was added/updated successfully, False otherwise (e.g., no active track).
        """
        if self.active_track_index < 0 or self.active_track_index >= len(self.tracks):
            logger.error("Add Point Error: No active track selected.")
            return False

        active_track_list: Track = self.tracks[self.active_track_index]
        active_track_id: int = self.get_active_track_id()
        # Round coordinates for consistent storage
        x_coord: float = round(x, 3)
        y_coord: float = round(y, 3)

        existing_point_index: int = -1
        # Find if a point already exists for this frame in the active track
        # Simple linear scan, ok for typical track lengths
        for i, point_data in enumerate(active_track_list):
            if point_data[0] == frame_index:
                existing_point_index = i
                break

        new_point_data: PointData = (frame_index, time_ms, x_coord, y_coord)

        if existing_point_index != -1:
            # Update existing point in-place
            active_track_list[existing_point_index] = new_point_data
            logger.info(f"Updated point for track {active_track_id} at frame {frame_index}: ({x_coord}, {y_coord})")
        else:
            # Add new point.
            active_track_list.append(new_point_data)
            # Re-sort the track by frame index after adding.
            # For mostly sequential additions, this is acceptable.
            # If performance becomes an issue with huge tracks added out-of-order,
            # consider bisect.insort or sorting only when necessary.
            active_track_list.sort(key=lambda p: p[0])
            logger.info(f"Added point for track {active_track_id} at frame {frame_index}: ({x_coord}, {y_coord})")

        # Notify UI about changes
        logger.debug("Emitting activeTrackDataChanged and trackListChanged after adding/updating point.")
        self.activeTrackDataChanged.emit() # Update points table
        self.trackListChanged.emit() # Update tracks table (point count, start/end frame)

        # If the active track is visible, its appearance might change
        if self.get_track_visibility_mode(self.active_track_index) != TrackVisibilityMode.HIDDEN:
            logger.debug("Emitting visualsNeedUpdate after adding/updating point (track is visible).")
            self.visualsNeedUpdate.emit()

        return True

    def delete_point(self, track_index: int, frame_index: int) -> bool:
        """
        Deletes a point from the specified track (by 0-based index) at the
        given frame index.

        Args:
            track_index: 0-based index of the track containing the point.
            frame_index: 0-based index of the frame corresponding to the point to delete.

        Returns:
            True if a point was found and deleted, False otherwise.
        """
        if not (0 <= track_index < len(self.tracks)):
            logger.error(f"Delete Point Error: Invalid track index {track_index}.")
            return False

        target_track_list: Track = self.tracks[track_index]
        point_to_remove_idx: int = -1
        # Find the point to remove by frame index
        for i, point_data in enumerate(target_track_list):
            if point_data[0] == frame_index:
                point_to_remove_idx = i
                break

        if point_to_remove_idx != -1:
            # Delete the point using the found list index
            del target_track_list[point_to_remove_idx]
            track_id: int = track_index + 1
            logger.info(f"Deleted point from track {track_id} (index {track_index}) at frame {frame_index}")

            # Notify UI about changes
            # If the modified track is the active one, update the points table
            if track_index == self.active_track_index:
                logger.debug("Emitting activeTrackDataChanged after point deletion (active track affected).")
                self.activeTrackDataChanged.emit()
            # Always update the tracks summary table (point count, start/end frame)
            logger.debug("Emitting trackListChanged after point deletion.")
            self.trackListChanged.emit()

            # If the track is visible, its appearance might change
            if self.get_track_visibility_mode(track_index) != TrackVisibilityMode.HIDDEN:
                logger.debug("Emitting visualsNeedUpdate after point deletion (track is visible).")
                self.visualsNeedUpdate.emit()
            return True
        else:
            # Point not found for the given frame index in this track
            logger.warning(f"Attempted to delete point for track {track_index+1} at frame {frame_index}, but no point found.")
            return False

    def find_closest_visible_track(self, click_x: float, click_y: float, current_frame_index: int) -> int:
        """
        Finds the index of the track whose *visible* marker (based on visibility
        mode and current frame) is closest to the click coordinates, within a
        defined tolerance.

        Args:
            click_x: The x-coordinate of the click (in scene coordinates).
            click_y: The y-coordinate of the click (in scene coordinates).
            current_frame_index: The 0-based index of the currently displayed frame.

        Returns:
            The 0-based index of the closest visible track, or -1 if none found
            within the squared tolerance (config.CLICK_TOLERANCE_SQ).
        """
        min_dist_sq: float = config.CLICK_TOLERANCE_SQ # Use squared distance for efficiency
        closest_track_index: int = -1
        logger.debug(f"Finding closest visible track to ({click_x:.1f}, {click_y:.1f}) on frame {current_frame_index}, tolerance_sq={min_dist_sq}")

        for track_index, track_data in enumerate(self.tracks):
            visibility_mode: TrackVisibilityMode = self.get_track_visibility_mode(track_index)

            if visibility_mode == TrackVisibilityMode.HIDDEN:
                continue # Skip hidden tracks

            # Iterate through points in the current track to check visible markers
            for point_data in track_data:
                frame_idx: int
                x_coord: float
                y_coord: float
                frame_idx, _, x_coord, y_coord = point_data # Unpack point data
                point_marker_is_visible_now: bool = False

                # Determine if this specific point's marker should be visible NOW
                if visibility_mode == TrackVisibilityMode.INCREMENTAL:
                    if frame_idx <= current_frame_index:
                        point_marker_is_visible_now = True
                elif visibility_mode == TrackVisibilityMode.ALWAYS_VISIBLE:
                    point_marker_is_visible_now = True

                # If the point's marker is visible, check distance to click
                if point_marker_is_visible_now:
                    dx: float = click_x - x_coord
                    dy: float = click_y - y_coord
                    dist_sq: float = dx*dx + dy*dy

                    # If closer than previous candidates and within tolerance
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        closest_track_index = track_index
                        # Don't break inner loop, another point in the *same* track might be closer
                        logger.debug(f"Found new candidate: Track {track_index+1} (marker frame: {frame_idx}) at dist_sq={dist_sq:.2f}")

            # After checking all points in a track, if we found the closest one so far,
            # we don't need to check other tracks if the distance is 0 (exact match).
            # However, usually we want the closest overall, so continue checking other tracks.

        if closest_track_index != -1:
             logger.debug(f"Closest visible track found: Index {closest_track_index} (ID: {closest_track_index+1}) with min_dist_sq={min_dist_sq:.2f}")
        else:
             logger.debug("No visible track marker found within tolerance on the current frame.")
        return closest_track_index

    def get_visual_elements(self, current_frame_index: int) -> List[VisualElement]:
        """
        Calculates the list of visual elements (markers, lines) needed to draw
        all managed tracks for the specified frame index. Considers track visibility,
        active state, and current frame to determine styles and visibility.

        Args:
            current_frame_index: The 0-based index of the currently displayed frame.

        Returns:
            A list of dictionaries, each describing a 'marker' or 'line'
            visual element with its properties (pos, p1, p2, style, track_id).
        """
        visual_elements: List[VisualElement] = []
        if current_frame_index < 0:
            logger.warning("get_visual_elements called with negative frame index, returning empty list.")
            return visual_elements # No frame index, nothing to draw

        logger.debug(f"Getting visual elements for frame {current_frame_index}")

        for track_index, track_data in enumerate(self.tracks):
            is_active: bool = (track_index == self.active_track_index)
            visibility_mode: TrackVisibilityMode = self.get_track_visibility_mode(track_index)
            track_id: int = track_index + 1 # 1-based ID for visual element info

            if visibility_mode == TrackVisibilityMode.HIDDEN:
                continue # Skip hidden tracks entirely

            # Determine base styles for this track based on active state
            line_style: str = config.STYLE_LINE_ACTIVE if is_active else config.STYLE_LINE_INACTIVE
            # Track the previous *visible* point in this track to draw connecting lines
            previous_visible_point_coords: Optional[Tuple[float, float]] = None

            # Iterate through points (sorted by frame index, ensured by add_point)
            for point_data in track_data:
                frame_idx: int
                x_coord: float
                y_coord: float
                frame_idx, _, x_coord, y_coord = point_data
                point_is_visible_in_mode: bool = False # Is this point generally visible based on mode/frame?

                # Determine if this point is visible based on the track's mode
                if visibility_mode == TrackVisibilityMode.INCREMENTAL:
                    point_is_visible_in_mode = (frame_idx <= current_frame_index)
                elif visibility_mode == TrackVisibilityMode.ALWAYS_VISIBLE:
                    point_is_visible_in_mode = True

                # If the point is considered visible according to the mode:
                if point_is_visible_in_mode:
                    # Determine the specific marker style
                    is_current_frame_marker = (frame_idx == current_frame_index)
                    if is_active:
                        marker_style = config.STYLE_MARKER_ACTIVE_CURRENT if is_current_frame_marker else config.STYLE_MARKER_ACTIVE_OTHER
                    else: # Inactive track
                        marker_style = config.STYLE_MARKER_INACTIVE_CURRENT if is_current_frame_marker else config.STYLE_MARKER_INACTIVE_OTHER

                    # Add the marker visual element
                    visual_elements.append({
                        'type': 'marker',
                        'pos': (x_coord, y_coord),
                        'style': marker_style,
                        'track_id': track_id,
                        'frame_idx': frame_idx # Add frame index for potential tooltips/info
                    })

                    # If there was a *previously visible* point in this track, draw a line segment
                    if previous_visible_point_coords:
                        prev_x, prev_y = previous_visible_point_coords
                        visual_elements.append({
                            'type': 'line',
                            'p1': (prev_x, prev_y),
                            'p2': (x_coord, y_coord),
                            'style': line_style,
                            'track_id': track_id
                        })

                    # Update the last visible point for the *next* iteration within this track
                    previous_visible_point_coords = (x_coord, y_coord)

        logger.debug(f"Generated {len(visual_elements)} visual elements.")
        return visual_elements

    def find_closest_visible_point(self, click_x: float, click_y: float, current_frame_index: int) -> Optional[Tuple[int, PointData]]:
            """
            Finds the specific track index and PointData tuple whose visible
            marker is closest to the click coordinates, within tolerance.

            Args:
                click_x: The x-coordinate of the click (in scene coordinates).
                click_y: The y-coordinate of the click (in scene coordinates).
                current_frame_index: The 0-based index of the currently displayed frame.

            Returns:
                A tuple containing (track_index, point_data) for the closest point,
                or None if no visible marker point is found within tolerance.
            """
            min_dist_sq: float = config.CLICK_TOLERANCE_SQ
            closest_track_index: int = -1
            closest_point_data: Optional[PointData] = None
            logger.debug(f"Finding closest visible point to ({click_x:.1f}, {click_y:.1f}) on frame {current_frame_index}, tolerance_sq={min_dist_sq}")

            for track_index, track_data in enumerate(self.tracks):
                visibility_mode: TrackVisibilityMode = self.get_track_visibility_mode(track_index)
                if visibility_mode == TrackVisibilityMode.HIDDEN:
                    continue # Skip hidden tracks

                # Iterate through points in the current track to find visible markers
                for point_data in track_data:
                    frame_idx: int
                    x_coord: float
                    y_coord: float
                    frame_idx, _, x_coord, y_coord = point_data # Unpack point data
                    point_marker_is_visible_now: bool = False

                    # Determine if this specific point's marker should be visible NOW
                    if visibility_mode == TrackVisibilityMode.INCREMENTAL:
                        point_marker_is_visible_now = (frame_idx <= current_frame_index)
                    elif visibility_mode == TrackVisibilityMode.ALWAYS_VISIBLE:
                        point_marker_is_visible_now = True

                    # If the point's marker is visible now, check distance to click
                    if point_marker_is_visible_now:
                        dx: float = click_x - x_coord
                        dy: float = click_y - y_coord
                        dist_sq: float = dx*dx + dy*dy

                        # If closer than previous candidates and within tolerance
                        if dist_sq < min_dist_sq:
                            min_dist_sq = dist_sq
                            closest_track_index = track_index
                            closest_point_data = point_data # Store the actual point data tuple
                            logger.debug(f"Found new closest point candidate: Track {track_index+1}, Frame {frame_idx} at dist_sq={dist_sq:.2f}")

            if closest_track_index != -1 and closest_point_data is not None:
                 logger.debug(f"Closest visible point found: Track Index {closest_track_index}, Point Data: {closest_point_data}")
                 return (closest_track_index, closest_point_data)
            else:
                 logger.debug("No visible track marker point found within tolerance on the current frame.")
                 return None

    # --- Data Access Methods ---

    def get_track_summary(self) -> List[Tuple[int, int, int, int]]:
        """
        Computes summary information for each track (ID, point count, start/end frame).
        Suitable for populating the main window's tracks table view.

        Returns:
            A list of tuples, where each tuple contains:
            (1-based track_id, num_points, 0-based start_frame_index, 0-based end_frame_index).
            Start/end frame index is -1 if the track has no points.
        """
        logger.debug("Generating track summary...")
        summary: List[Tuple[int, int, int, int]] = []
        for i, track in enumerate(self.tracks):
            track_id: int = i + 1 # 1-based ID for display
            num_points: int = len(track)
            start_frame: int = -1
            end_frame: int = -1
            if num_points > 0:
                # Tracks are kept sorted by frame index (point[0])
                start_frame = track[0][0]
                end_frame = track[-1][0]
            summary.append((track_id, num_points, start_frame, end_frame))
        logger.debug(f"Generated summary for {len(summary)} tracks.")
        return summary

    def get_active_track_points_for_table(self) -> Track:
        """
        Retrieves a *copy* of the point data (list of PointData tuples) for the
        currently active track. Suitable for display in the points table.

        Returns:
            A list of PointData tuples for the active track, or an empty list
            if no track is active or the active track index is invalid.
        """
        if self.active_track_index < 0 or self.active_track_index >= len(self.tracks):
            logger.debug("get_active_track_points_for_table: No active track, returning empty list.")
            return [] # Return empty list if no valid active track

        # Return a copy to prevent external modification of internal data via the table model
        points: Track = list(self.tracks[self.active_track_index])
        logger.debug(f"Returning {len(points)} points (copy) for active track {self.get_active_track_id()}.")
        return points

    def get_all_track_data(self) -> AllTracksData:
        """
        Returns a deep copy of all track data managed by this instance.
        Suitable for saving track data, ensuring internal data is not modified.

        Returns:
            A list where each element is a new list containing the point data tuples for a track.
            Example: [[(f0,t0,x0,y0), (f1,t1,x1,y1)], [(f2,t2,x2,y2)]]
        """
        logger.debug(f"Returning deep copy of all data for {len(self.tracks)} tracks.")
        # Create copies of the inner lists (Tracks) as well to ensure deep copy
        return [list(track) for track in self.tracks]

    def load_tracks_from_data(self, parsed_data: List[Tuple[int, int, float, float, float]],
                              video_width: int, video_height: int, video_frame_count: int, video_fps: float
                             ) -> Tuple[bool, List[str]]:
        """
        Loads and validates track data from a list of raw point tuples (e.g., from CSV).
        Resets existing tracks before loading. Validates points against video
        dimensions and frame count. Checks time consistency if FPS is available.

        Args:
            parsed_data: List of raw point tuples: (1-based track_id, 0-based frame_idx, time_ms, x, y).
            video_width: Width of the associated video (for coordinate validation).
            video_height: Height of the associated video (for coordinate validation).
            video_frame_count: Total number of frames in the video (for index validation).
            video_fps: Frames per second of the video (for time consistency check).

        Returns:
            A tuple containing:
            - success (bool): True if loading completed without critical errors (warnings may still exist).
                              False if a critical internal error occurred.
            - warnings_list (List[str]): A list of warnings/info messages generated during validation/loading.
        """
        logger.info(f"Attempting to load {len(parsed_data)} parsed points into TrackManager...")
        warnings_list: List[str] = []
        # Use defaultdict to group validated points by track_id easily
        loaded_tracks_dict: Dict[int, Track] = defaultdict(list)
        # Tolerance for time check (e.g., half a frame duration, fallback 50ms)
        time_tolerance_ms: float = (0.5 * 1000 / video_fps) if video_fps > 0 else 50.0
        points_skipped_validation: int = 0
        points_validated: int = 0

        try:
            # --- Validation Pass ---
            logger.debug("Starting validation pass...")
            for point_tuple in parsed_data:
                # Expecting (1-based track_id, 0-based frame_idx, time_ms, x, y)
                track_id, frame_idx, time_ms, x, y = point_tuple
                point_desc = f"Point (Track {track_id}, Frame {frame_idx})" # Log with 0-based frame index
                is_valid_point = True

                # Validate frame index (must be within [0, frame_count-1])
                if not (0 <= frame_idx < video_frame_count):
                    msg = f"{point_desc}: Frame index {frame_idx} is outside video range [0, {video_frame_count - 1}]. Skipping point."
                    warnings_list.append(msg); is_valid_point = False

                # Validate coordinates (must be within [0, width/height)) - only if frame was valid
                if is_valid_point and not (0 <= x < video_width):
                    msg = f"{point_desc}: X-coordinate {x:.2f} is outside video range [0, {video_width}). Skipping point."
                    warnings_list.append(msg); is_valid_point = False
                if is_valid_point and not (0 <= y < video_height):
                     msg = f"{point_desc}: Y-coordinate {y:.2f} is outside video range [0, {video_height}). Skipping point."
                     warnings_list.append(msg); is_valid_point = False

                # Time consistency check (only if point is otherwise valid and FPS available)
                if is_valid_point and video_fps > 0:
                    expected_time_ms = (frame_idx / video_fps) * 1000
                    if abs(time_ms - expected_time_ms) > time_tolerance_ms:
                         # Only issue a warning, don't invalidate the point based on time alone
                         msg = f"{point_desc}: Warning: Time {time_ms:.1f}ms seems inconsistent with frame index (expected ~{expected_time_ms:.1f}ms for {video_fps} FPS)."
                         warnings_list.append(msg)
                         # Do not set is_valid_point = False here

                # --- Store if Valid ---
                if is_valid_point:
                    # Store the validated point data, grouped by track_id
                    # Note: Data stored is (frame_idx, time_ms, x, y) - track_id is the dict key
                    loaded_tracks_dict[track_id].append((frame_idx, time_ms, x, y))
                    points_validated += 1
                else:
                    # Log the reason for skipping (last warning added)
                    logger.warning(warnings_list[-1])
                    points_skipped_validation += 1

            logger.info(f"Validation complete: {points_validated} points passed, {points_skipped_validation} points skipped due to validation errors.")

            # --- Load Validated Data into TrackManager ---
            self.reset() # Clear existing tracks before loading new ones

            # Process tracks sorted by their original ID for consistent order
            sorted_track_ids = sorted(loaded_tracks_dict.keys())
            tracks_skipped_empty = 0
            loaded_track_count = 0
            for track_id in sorted_track_ids:
                track_points = loaded_tracks_dict[track_id]
                # Should not happen if validation logic is correct, but double-check
                if not track_points:
                    msg = f"Skipping Track ID {track_id} as it contained no valid points after validation."
                    warnings_list.append(msg); tracks_skipped_empty += 1; logger.warning(msg)
                    continue

                # Sort points within the track by frame index (essential for operation)
                track_points.sort(key=lambda p: p[0])
                # Add the validated and sorted track points
                self.tracks.append(track_points)
                # Set default visibility for loaded tracks
                self.track_visibility_modes.append(TrackVisibilityMode.INCREMENTAL)
                loaded_track_count += 1

            # Set active track to the first loaded track, if any loaded
            self.active_track_index = 0 if self.tracks else -1
            logger.info(f"Successfully loaded {points_validated} points into {loaded_track_count} tracks. Skipped {tracks_skipped_empty} tracks that became empty after validation.")

            # --- Emit Signals ---
            logger.debug("Emitting trackListChanged and activeTrackDataChanged after loading data.")
            self.trackListChanged.emit()
            self.activeTrackDataChanged.emit()
            # Emit visuals update signal as loaded tracks might be visible on the current frame
            logger.debug("Emitting visualsNeedUpdate after loading data.")
            self.visualsNeedUpdate.emit()

            return True, warnings_list # Success (potentially with warnings)

        except Exception as e:
             # Catch unexpected errors during the processing/loading phase
             error_msg = f"Critical internal error processing loaded track data: {e}"
             logger.exception(error_msg) # Log full traceback
             self.reset() # Ensure manager is in a clean state after a critical error
             # Return failure and include the error message in the warnings list
             return False, warnings_list + [error_msg]