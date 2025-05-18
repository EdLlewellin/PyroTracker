# track_manager.py
"""
Manages pyroclast track data, including points, visibility states,
and the active track selection. Calculates visual elements (markers, lines)
required for rendering based on current state and frame, but does not draw.
"""
import logging
from collections import defaultdict
from enum import Enum, auto
from typing import List, Tuple, Dict, Optional, Any

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
    HIDDEN = auto()
    INCREMENTAL = auto()
    ALWAYS_VISIBLE = auto()

# --- NEW: Enum for Undo Action Types ---
class UndoActionType(Enum):
    """Defines the types of actions that can be undone."""
    POINT_ADDED = auto()
    POINT_MODIFIED = auto()

class TrackManager(QtCore.QObject):
    """
    Manages pyroclast track data and calculates visual representation.

    Handles creating, deleting, loading, and saving tracks. Calculates *what*
    needs to be drawn based on visibility modes and emits signals to notify
    the UI of changes. Does NOT perform any drawing itself.
    """
    trackListChanged = QtCore.Signal()
    activeTrackDataChanged = QtCore.Signal()
    visualsNeedUpdate = QtCore.Signal()
    # --- NEW: Signal for undo state change ---
    undoStateChanged = QtCore.Signal(bool) # True if undo is available, False otherwise

    tracks: AllTracksData
    track_visibility_modes: List[TrackVisibilityMode]
    active_track_index: int

    # --- NEW: Variables for Undo Functionality ---
    _last_action_type: Optional[UndoActionType] = None
    _last_action_details: Dict[str, Any] = {} # Stores context for undo

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        logger.info("Initializing TrackManager...")
        self.tracks = []
        self.track_visibility_modes = []
        self.active_track_index = -1
        self._clear_last_action() # Initialize undo state
        logger.info("TrackManager initialized.")

    def _clear_last_action(self) -> None:
        """Clears the stored last action, making undo unavailable."""
        # logger.debug("Clearing last undo action.")
        self._last_action_type = None
        self._last_action_details = {}
        self.undoStateChanged.emit(False)

    def reset(self) -> None:
        logger.info("Resetting TrackManager state...")
        self.tracks = []
        self.track_visibility_modes = []
        self.active_track_index = -1
        self._clear_last_action() # Clear undo state on reset
        logger.info("TrackManager reset complete.")
        logger.debug("Emitting trackListChanged and activeTrackDataChanged after reset.")
        self.trackListChanged.emit()
        self.activeTrackDataChanged.emit()

    def create_new_track(self) -> int:
        logger.info("Creating new track...")
        new_track_list: Track = []
        self.tracks.append(new_track_list)
        self.track_visibility_modes.append(TrackVisibilityMode.INCREMENTAL)
        new_track_index: int = len(self.tracks) - 1
        self.set_active_track(new_track_index)
        new_track_id: int = new_track_index + 1
        logger.info(f"Created new track {new_track_id} (index {new_track_index}).")
        self._clear_last_action() # Creating a track clears any previous point undo action
        logger.debug("Emitting trackListChanged after creating new track.")
        self.trackListChanged.emit()
        return new_track_id

    def delete_track(self, track_index_to_delete: int) -> bool:
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
        if self.active_track_index == track_index_to_delete:
            logger.info(f"Deleted track {track_id_deleted} was active. Resetting active index to -1.")
            self.active_track_index = -1
            active_track_changed = True
        elif self.active_track_index > track_index_to_delete:
            old_active: int = self.active_track_index
            self.active_track_index -= 1
            logger.info(f"Active track index shifted down from {old_active} to {self.active_track_index} due to deletion.")
            active_track_changed = True
        
        self._clear_last_action() # Deleting a track clears any previous point undo action

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
        new_active_index: int = -1
        if 0 <= track_index < len(self.tracks):
            new_active_index = track_index
        elif track_index == -1:
            new_active_index = -1
        else:
            logger.warning(f"Invalid track index {track_index} passed to set_active_track. Total tracks: {len(self.tracks)}. Ignoring.")
            return

        if self.active_track_index != new_active_index:
            old_active_index: int = self.active_track_index
            old_mode: TrackVisibilityMode = self.get_track_visibility_mode(old_active_index)

            self.active_track_index = new_active_index
            new_mode: TrackVisibilityMode = self.get_track_visibility_mode(new_active_index)

            logger.info(f"Set active track index to {self.active_track_index} (ID: {self.get_active_track_id()})")
            self._clear_last_action() # Changing active track clears undo for previous track's points
            logger.debug("Emitting activeTrackDataChanged due to active track change.")
            self.activeTrackDataChanged.emit()

            if old_mode != TrackVisibilityMode.HIDDEN or new_mode != TrackVisibilityMode.HIDDEN:
                 logger.debug(f"Emitting visualsNeedUpdate because old ({old_mode.name}) or new ({new_mode.name}) active track might be visible.")
                 self.visualsNeedUpdate.emit()

    def set_track_visibility_mode(self, track_index: int, mode: TrackVisibilityMode) -> None:
        if not (0 <= track_index < len(self.track_visibility_modes)):
            logger.warning(f"Invalid track index {track_index} for setting visibility. Ignoring.")
            return

        if self.track_visibility_modes[track_index] != mode:
            old_mode: TrackVisibilityMode = self.track_visibility_modes[track_index]
            self.track_visibility_modes[track_index] = mode
            track_id: int = track_index + 1
            logger.info(f"Set visibility for track {track_id} (index {track_index}) to {mode.name}")
            if old_mode != TrackVisibilityMode.HIDDEN or mode != TrackVisibilityMode.HIDDEN:
                logger.debug("Emitting visualsNeedUpdate due to visibility mode change for a potentially visible track.")
                self.visualsNeedUpdate.emit()
            self.trackListChanged.emit()

    def get_track_visibility_mode(self, track_index: int) -> TrackVisibilityMode:
        if 0 <= track_index < len(self.track_visibility_modes):
            return self.track_visibility_modes[track_index]
        return TrackVisibilityMode.HIDDEN

    def set_all_tracks_visibility(self, mode: TrackVisibilityMode) -> None:
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
                if old_mode != TrackVisibilityMode.HIDDEN or mode != TrackVisibilityMode.HIDDEN:
                    needs_visual_update = True
        if changed:
            logger.debug("Visibility changed for at least one track. Emitting trackListChanged.")
            self.trackListChanged.emit()
        if needs_visual_update:
            logger.debug("Visual update needed due to visibility change. Emitting visualsNeedUpdate.")
            self.visualsNeedUpdate.emit()
        if not changed:
             logger.debug("All tracks were already in the target visibility mode. No changes made.")

    def get_active_track_id(self) -> int:
         return self.active_track_index + 1 if self.active_track_index != -1 else -1

    def get_point_for_active_track(self, frame_index: int) -> Optional[PointData]:
        """
        Retrieves a specific point for the currently active track at the given frame index.
        Returns None if no active track, or if the point doesn't exist.
        """
        if self.active_track_index < 0 or self.active_track_index >= len(self.tracks):
            return None
        active_track_list: Track = self.tracks[self.active_track_index]
        for point_data in active_track_list:
            if point_data[0] == frame_index:
                return point_data
        return None

    def add_point(self, frame_index: int, time_ms: float, x: float, y: float) -> bool:
        if self.active_track_index < 0 or self.active_track_index >= len(self.tracks):
            logger.error("Add Point Error: No active track selected.")
            self._clear_last_action()
            return False

        active_track_list: Track = self.tracks[self.active_track_index]
        active_track_id: int = self.get_active_track_id()
        x_coord: float = round(x, 3)
        y_coord: float = round(y, 3)

        existing_point_data: Optional[PointData] = None
        existing_point_index_in_list: int = -1 # Index within the active_track_list
        for i, p_data in enumerate(active_track_list):
            if p_data[0] == frame_index:
                existing_point_data = p_data
                existing_point_index_in_list = i
                break
        
        # --- Store information for UNDO ---
        self._last_action_details = {
            "track_index": self.active_track_index,
            "frame_index": frame_index,
            "time_ms": time_ms # Store time_ms in case a new point is added
        }
        if existing_point_data:
            self._last_action_type = UndoActionType.POINT_MODIFIED
            self._last_action_details["previous_point_data"] = existing_point_data # Store (frame, time, x, y)
            logger.debug(f"Preparing UNDO for POINT_MODIFIED: Previous data {existing_point_data}")
        else:
            self._last_action_type = UndoActionType.POINT_ADDED
            logger.debug(f"Preparing UNDO for POINT_ADDED at frame {frame_index}")
        # --- End UNDO storage ---

        new_point_data_tuple: PointData = (frame_index, time_ms, x_coord, y_coord)

        if existing_point_index_in_list != -1:
            active_track_list[existing_point_index_in_list] = new_point_data_tuple
            logger.info(f"Updated point for track {active_track_id} at frame {frame_index}: ({x_coord}, {y_coord})")
        else:
            active_track_list.append(new_point_data_tuple)
            active_track_list.sort(key=lambda p: p[0])
            logger.info(f"Added point for track {active_track_id} at frame {frame_index}: ({x_coord}, {y_coord})")

        self.undoStateChanged.emit(True) # Undo is now available
        self.activeTrackDataChanged.emit()
        self.trackListChanged.emit()
        if self.get_track_visibility_mode(self.active_track_index) != TrackVisibilityMode.HIDDEN:
            self.visualsNeedUpdate.emit()
        return True

    def delete_point(self, track_index: int, frame_index: int) -> bool:
        if not (0 <= track_index < len(self.tracks)):
            logger.error(f"Delete Point Error: Invalid track index {track_index}.")
            return False

        target_track_list: Track = self.tracks[track_index]
        point_to_remove_idx: int = -1
        for i, point_data in enumerate(target_track_list):
            if point_data[0] == frame_index:
                point_to_remove_idx = i
                break

        if point_to_remove_idx != -1:
            # --- MODIFICATION: Store info for potential UNDO of delete (currently out of scope) ---
            # For now, deleting a point clears the general undo stack for add/modify.
            # If undoing delete was required, this would be more complex.
            self._clear_last_action() # Deleting a point invalidates the last add/modify undo.
            # --- END MODIFICATION ---

            del target_track_list[point_to_remove_idx]
            track_id: int = track_index + 1
            logger.info(f"Deleted point from track {track_id} (index {track_index}) at frame {frame_index}")

            if track_index == self.active_track_index:
                self.activeTrackDataChanged.emit()
            self.trackListChanged.emit()
            if self.get_track_visibility_mode(track_index) != TrackVisibilityMode.HIDDEN:
                self.visualsNeedUpdate.emit()
            return True
        else:
            logger.warning(f"Attempted to delete point for track {track_index+1} at frame {frame_index}, but no point found.")
            return False

    # --- NEW: Undo Functionality ---
    def can_undo_last_point_action(self) -> bool:
        """Checks if there is a point action that can be undone."""
        return self._last_action_type is not None

    def undo_last_point_action(self) -> bool:
        """
        Reverts the last point addition or modification if possible.
        Returns True if an action was undone, False otherwise.
        """
        if not self.can_undo_last_point_action():
            logger.info("Undo requested, but no action available to undo.")
            return False

        action_type = self._last_action_type
        details = self._last_action_details
        track_idx_to_undo = details.get("track_index")
        frame_idx_to_undo = details.get("frame_index")

        if track_idx_to_undo is None or frame_idx_to_undo is None or \
           not (0 <= track_idx_to_undo < len(self.tracks)):
            logger.error(f"Undo failed: Invalid details stored. TrackIdx: {track_idx_to_undo}, FrameIdx: {frame_idx_to_undo}")
            self._clear_last_action()
            return False
        
        undone_successfully = False
        if action_type == UndoActionType.POINT_ADDED:
            logger.info(f"Undoing POINT_ADDED: Deleting point from track {track_idx_to_undo+1} at frame {frame_idx_to_undo}.")
            # This reuses the existing delete_point logic, which already handles signals.
            # We pass the specific track_index and frame_index from the stored details.
            # Temporarily clear the last action so delete_point itself doesn't clear it again
            # if it thinks it's a user action.
            current_last_action = self._last_action_type, self._last_action_details
            self._last_action_type = None # Avoid delete_point clearing its own undo state
            
            # Call delete_point directly on the specific track and frame
            undone_successfully = self.delete_point_internal(track_idx_to_undo, frame_idx_to_undo)
            
            if not undone_successfully: # Restore if delete failed internally (shouldn't happen if logic is right)
                self._last_action_type, self._last_action_details = current_last_action
            else: # Actual clear after successful undo
                self._clear_last_action()


        elif action_type == UndoActionType.POINT_MODIFIED:
            previous_data = details.get("previous_point_data")
            if previous_data:
                # Previous data is (frame, time, x, y)
                # Restore the point directly. Find it first.
                target_track_list: Track = self.tracks[track_idx_to_undo]
                point_list_idx_to_restore = -1
                for i, p_data in enumerate(target_track_list):
                    if p_data[0] == frame_idx_to_undo:
                        point_list_idx_to_restore = i
                        break
                
                if point_list_idx_to_restore != -1:
                    target_track_list[point_list_idx_to_restore] = previous_data
                    # No need to re-sort as frame index doesn't change
                    logger.info(f"Undoing POINT_MODIFIED: Restored point for track {track_idx_to_undo+1} at frame {frame_idx_to_undo} to {previous_data[2:]}.")
                    undone_successfully = True
                    self._clear_last_action() # Clear after successful undo
                    
                    # Emit signals for UI update
                    if track_idx_to_undo == self.active_track_index:
                        self.activeTrackDataChanged.emit()
                    self.trackListChanged.emit() # Point count, start/end frame might not change, but data does
                    if self.get_track_visibility_mode(track_idx_to_undo) != TrackVisibilityMode.HIDDEN:
                        self.visualsNeedUpdate.emit()
                else:
                    logger.error(f"Undo POINT_MODIFIED failed: Point not found in track {track_idx_to_undo+1} at frame {frame_idx_to_undo} to restore.")
            else:
                logger.error("Undo POINT_MODIFIED failed: No previous_point_data stored.")
        
        if not undone_successfully and self.can_undo_last_point_action(): # If failed but didn't clear
             self._clear_last_action() # Ensure it's cleared if undo process had an issue

        return undone_successfully

    def delete_point_internal(self, track_index: int, frame_index: int) -> bool:
        """
        Internal version of delete_point that doesn't clear the undo stack.
        Used by the undo_last_point_action method.
        """
        if not (0 <= track_index < len(self.tracks)):
            return False
        target_track_list: Track = self.tracks[track_index]
        point_to_remove_idx: int = -1
        for i, point_data in enumerate(target_track_list):
            if point_data[0] == frame_index:
                point_to_remove_idx = i
                break
        if point_to_remove_idx != -1:
            del target_track_list[point_to_remove_idx]
            # Emit signals as usual
            if track_index == self.active_track_index:
                self.activeTrackDataChanged.emit()
            self.trackListChanged.emit()
            if self.get_track_visibility_mode(track_index) != TrackVisibilityMode.HIDDEN:
                self.visualsNeedUpdate.emit()
            return True
        return False
    # --- End NEW Undo Functionality ---


    def find_closest_visible_track(self, click_x: float, click_y: float, current_frame_index: int) -> int:
        min_dist_sq: float = config.CLICK_TOLERANCE_SQ
        closest_track_index: int = -1
        # logger.debug(f"Finding closest visible track to ({click_x:.1f}, {click_y:.1f}) on frame {current_frame_index}, tolerance_sq={min_dist_sq}")
        for track_index, track_data in enumerate(self.tracks):
            visibility_mode: TrackVisibilityMode = self.get_track_visibility_mode(track_index)
            if visibility_mode == TrackVisibilityMode.HIDDEN: continue
            for point_data in track_data:
                frame_idx, _, x_coord, y_coord = point_data
                point_marker_is_visible_now: bool = False
                if visibility_mode == TrackVisibilityMode.INCREMENTAL:
                    if frame_idx <= current_frame_index: point_marker_is_visible_now = True
                elif visibility_mode == TrackVisibilityMode.ALWAYS_VISIBLE:
                    point_marker_is_visible_now = True
                if point_marker_is_visible_now:
                    dx: float = click_x - x_coord; dy: float = click_y - y_coord
                    dist_sq: float = dx*dx + dy*dy
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq; closest_track_index = track_index
        # if closest_track_index != -1: logger.debug(f"Closest visible track found: Index {closest_track_index} (ID: {closest_track_index+1}) with min_dist_sq={min_dist_sq:.2f}")
        # else: logger.debug("No visible track marker found within tolerance on the current frame.")
        return closest_track_index

    def get_visual_elements(self, current_frame_index: int) -> List[VisualElement]:
        visual_elements: List[VisualElement] = []
        if current_frame_index < 0: return visual_elements
        # logger.debug(f"Getting visual elements for frame {current_frame_index}")
        for track_index, track_data in enumerate(self.tracks):
            is_active: bool = (track_index == self.active_track_index)
            visibility_mode: TrackVisibilityMode = self.get_track_visibility_mode(track_index)
            track_id: int = track_index + 1
            if visibility_mode == TrackVisibilityMode.HIDDEN: continue
            line_style: str = config.STYLE_LINE_ACTIVE if is_active else config.STYLE_LINE_INACTIVE
            previous_visible_point_coords: Optional[Tuple[float, float]] = None
            for point_data in track_data:
                frame_idx, _, x_coord, y_coord = point_data
                point_is_visible_in_mode: bool = False
                if visibility_mode == TrackVisibilityMode.INCREMENTAL: point_is_visible_in_mode = (frame_idx <= current_frame_index)
                elif visibility_mode == TrackVisibilityMode.ALWAYS_VISIBLE: point_is_visible_in_mode = True
                if point_is_visible_in_mode:
                    is_current_frame_marker = (frame_idx == current_frame_index)
                    if is_active: marker_style = config.STYLE_MARKER_ACTIVE_CURRENT if is_current_frame_marker else config.STYLE_MARKER_ACTIVE_OTHER
                    else: marker_style = config.STYLE_MARKER_INACTIVE_CURRENT if is_current_frame_marker else config.STYLE_MARKER_INACTIVE_OTHER
                    visual_elements.append({'type': 'marker', 'pos': (x_coord, y_coord), 'style': marker_style, 'track_id': track_id, 'frame_idx': frame_idx})
                    if previous_visible_point_coords:
                        prev_x, prev_y = previous_visible_point_coords
                        visual_elements.append({'type': 'line', 'p1': (prev_x, prev_y), 'p2': (x_coord, y_coord), 'style': line_style, 'track_id': track_id})
                    previous_visible_point_coords = (x_coord, y_coord)
        # logger.debug(f"Generated {len(visual_elements)} visual elements.")
        return visual_elements

    def find_closest_visible_point(self, click_x: float, click_y: float, current_frame_index: int) -> Optional[Tuple[int, PointData]]:
            min_dist_sq: float = config.CLICK_TOLERANCE_SQ
            closest_track_index: int = -1
            closest_point_data: Optional[PointData] = None
            # logger.debug(f"Finding closest visible point to ({click_x:.1f}, {click_y:.1f}) on frame {current_frame_index}, tolerance_sq={min_dist_sq}")
            for track_index, track_data in enumerate(self.tracks):
                visibility_mode: TrackVisibilityMode = self.get_track_visibility_mode(track_index)
                if visibility_mode == TrackVisibilityMode.HIDDEN: continue
                for point_data_tuple in track_data:
                    frame_idx, _, x_coord, y_coord = point_data_tuple
                    point_marker_is_visible_now: bool = False
                    if visibility_mode == TrackVisibilityMode.INCREMENTAL: point_marker_is_visible_now = (frame_idx <= current_frame_index)
                    elif visibility_mode == TrackVisibilityMode.ALWAYS_VISIBLE: point_marker_is_visible_now = True
                    if point_marker_is_visible_now:
                        dx: float = click_x - x_coord; dy: float = click_y - y_coord
                        dist_sq: float = dx*dx + dy*dy
                        if dist_sq < min_dist_sq:
                            min_dist_sq = dist_sq; closest_track_index = track_index
                            closest_point_data = point_data_tuple
            # if closest_track_index != -1 and closest_point_data is not None: logger.debug(f"Closest visible point found: Track Index {closest_track_index}, Point Data: {closest_point_data}")
            # else: logger.debug("No visible track marker point found within tolerance on the current frame.")
            return (closest_track_index, closest_point_data) if closest_track_index != -1 and closest_point_data is not None else None

    def get_track_summary(self) -> List[Tuple[int, int, int, int]]:
        # logger.debug("Generating track summary...")
        summary: List[Tuple[int, int, int, int]] = []
        for i, track in enumerate(self.tracks):
            track_id: int = i + 1; num_points: int = len(track)
            start_frame: int = -1; end_frame: int = -1
            if num_points > 0: start_frame = track[0][0]; end_frame = track[-1][0]
            summary.append((track_id, num_points, start_frame, end_frame))
        # logger.debug(f"Generated summary for {len(summary)} tracks.")
        return summary

    def get_active_track_points_for_table(self) -> Track:
        if self.active_track_index < 0 or self.active_track_index >= len(self.tracks): return []
        points: Track = list(self.tracks[self.active_track_index])
        # logger.debug(f"Returning {len(points)} points (copy) for active track {self.get_active_track_id()}.")
        return points

    def get_all_track_data(self) -> AllTracksData:
        # logger.debug(f"Returning deep copy of all data for {len(self.tracks)} tracks.")
        return [list(track) for track in self.tracks]

    def load_tracks_from_data(self, parsed_data: List[Tuple[int, int, float, float, float]],
                              video_width: int, video_height: int, video_frame_count: int, video_fps: float
                             ) -> Tuple[bool, List[str]]:
        logger.info(f"Attempting to load {len(parsed_data)} parsed points into TrackManager...")
        warnings_list: List[str] = []
        loaded_tracks_dict: Dict[int, Track] = defaultdict(list)
        time_tolerance_ms: float = (0.5 * 1000 / video_fps) if video_fps > 0 else 50.0
        points_skipped_validation: int = 0; points_validated: int = 0
        try:
            logger.debug("Starting validation pass...")
            for point_tuple in parsed_data:
                track_id, frame_idx, time_ms, x, y = point_tuple
                point_desc = f"Point (Track {track_id}, Frame {frame_idx})"
                is_valid_point = True
                if not (0 <= frame_idx < video_frame_count):
                    msg = f"{point_desc}: Frame index {frame_idx} is outside video range [0, {video_frame_count - 1}]. Skipping point."
                    warnings_list.append(msg); is_valid_point = False
                if is_valid_point and not (0 <= x < video_width):
                    msg = f"{point_desc}: X-coordinate {x:.2f} is outside video range [0, {video_width}). Skipping point."
                    warnings_list.append(msg); is_valid_point = False
                if is_valid_point and not (0 <= y < video_height):
                     msg = f"{point_desc}: Y-coordinate {y:.2f} is outside video range [0, {video_height}). Skipping point."
                     warnings_list.append(msg); is_valid_point = False
                if is_valid_point and video_fps > 0:
                    expected_time_ms = (frame_idx / video_fps) * 1000
                    if abs(time_ms - expected_time_ms) > time_tolerance_ms:
                         msg = f"{point_desc}: Warning: Time {time_ms:.1f}ms seems inconsistent with frame index (expected ~{expected_time_ms:.1f}ms for {video_fps} FPS)."
                         warnings_list.append(msg)
                if is_valid_point:
                    loaded_tracks_dict[track_id].append((frame_idx, time_ms, x, y)); points_validated += 1
                else:
                    logger.warning(warnings_list[-1]); points_skipped_validation += 1
            logger.info(f"Validation complete: {points_validated} points passed, {points_skipped_validation} points skipped.")
            self.reset() # Clears existing tracks and undo state
            sorted_track_ids = sorted(loaded_tracks_dict.keys())
            tracks_skipped_empty = 0; loaded_track_count = 0
            for track_id in sorted_track_ids:
                track_points = loaded_tracks_dict[track_id]
                if not track_points:
                    msg = f"Skipping Track ID {track_id} as it contained no valid points after validation."
                    warnings_list.append(msg); tracks_skipped_empty += 1; logger.warning(msg)
                    continue
                track_points.sort(key=lambda p: p[0])
                self.tracks.append(track_points)
                self.track_visibility_modes.append(TrackVisibilityMode.INCREMENTAL)
                loaded_track_count += 1
            self.active_track_index = 0 if self.tracks else -1
            logger.info(f"Successfully loaded {points_validated} points into {loaded_track_count} tracks. Skipped {tracks_skipped_empty} empty tracks.")
            self.trackListChanged.emit(); self.activeTrackDataChanged.emit(); self.visualsNeedUpdate.emit()
            return True, warnings_list
        except Exception as e:
             error_msg = f"Critical internal error processing loaded track data: {e}"
             logger.exception(error_msg)
             self.reset()
             return False, warnings_list + [error_msg]