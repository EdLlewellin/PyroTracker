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

# --- MODIFIED: Enum for Undo Action Types ---
class UndoActionType(Enum):
    """Defines the types of actions that can be undone."""
    POINT_ADDED = auto()
    POINT_MODIFIED = auto()
    POINT_DELETED = auto() # New action type

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
    undoStateChanged = QtCore.Signal(bool)

    tracks: AllTracksData
    track_visibility_modes: List[TrackVisibilityMode]
    active_track_index: int

    _last_action_type: Optional[UndoActionType] = None
    _last_action_details: Dict[str, Any] = {}

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        logger.info("Initializing TrackManager...")
        self.tracks = []
        self.track_visibility_modes = []
        self.active_track_index = -1
        self._clear_last_action()
        logger.info("TrackManager initialized.")

    def _clear_last_action(self) -> None:
        """Clears the stored last action, making undo unavailable."""
        self._last_action_type = None
        self._last_action_details = {}
        self.undoStateChanged.emit(False)

    def reset(self) -> None:
        logger.info("Resetting TrackManager state...")
        self.tracks = []
        self.track_visibility_modes = []
        self.active_track_index = -1
        self._clear_last_action()
        logger.info("TrackManager reset complete.")
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
        self._clear_last_action()
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
            self.active_track_index = -1
            active_track_changed = True
        elif self.active_track_index > track_index_to_delete:
            self.active_track_index -= 1
            active_track_changed = True
        
        self._clear_last_action()

        self.trackListChanged.emit()
        if active_track_changed:
            self.activeTrackDataChanged.emit()
        if was_visible:
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
            return

        if self.active_track_index != new_active_index:
            old_active_index: int = self.active_track_index
            old_mode: TrackVisibilityMode = self.get_track_visibility_mode(old_active_index)
            self.active_track_index = new_active_index
            new_mode: TrackVisibilityMode = self.get_track_visibility_mode(new_active_index)
            self._clear_last_action()
            self.activeTrackDataChanged.emit()
            if old_mode != TrackVisibilityMode.HIDDEN or new_mode != TrackVisibilityMode.HIDDEN:
                 self.visualsNeedUpdate.emit()

    def set_track_visibility_mode(self, track_index: int, mode: TrackVisibilityMode) -> None:
        if not (0 <= track_index < len(self.track_visibility_modes)):
            return
        if self.track_visibility_modes[track_index] != mode:
            old_mode = self.track_visibility_modes[track_index]
            self.track_visibility_modes[track_index] = mode
            if old_mode != TrackVisibilityMode.HIDDEN or mode != TrackVisibilityMode.HIDDEN:
                self.visualsNeedUpdate.emit()
            self.trackListChanged.emit()

    def get_track_visibility_mode(self, track_index: int) -> TrackVisibilityMode:
        if 0 <= track_index < len(self.track_visibility_modes):
            return self.track_visibility_modes[track_index]
        return TrackVisibilityMode.HIDDEN

    def set_all_tracks_visibility(self, mode: TrackVisibilityMode) -> None:
        if not self.tracks: return
        changed, needs_visual_update = False, False
        for i in range(len(self.track_visibility_modes)):
            if self.track_visibility_modes[i] != mode:
                if self.track_visibility_modes[i] != TrackVisibilityMode.HIDDEN or mode != TrackVisibilityMode.HIDDEN:
                    needs_visual_update = True
                self.track_visibility_modes[i] = mode
                changed = True
        if changed: self.trackListChanged.emit()
        if needs_visual_update: self.visualsNeedUpdate.emit()

    def get_active_track_id(self) -> int:
         return self.active_track_index + 1 if self.active_track_index != -1 else -1

    def get_point_for_active_track(self, frame_index: int) -> Optional[PointData]:
        if self.active_track_index < 0 or self.active_track_index >= len(self.tracks):
            return None
        for point_data in self.tracks[self.active_track_index]:
            if point_data[0] == frame_index:
                return point_data
        return None

    def add_point(self, frame_index: int, time_ms: float, x: float, y: float) -> bool:
        if self.active_track_index < 0 or self.active_track_index >= len(self.tracks):
            self._clear_last_action()
            return False

        active_track_list = self.tracks[self.active_track_index]
        x_coord, y_coord = round(x, 3), round(y, 3)
        existing_point_data, existing_point_index_in_list = None, -1
        for i, p_data in enumerate(active_track_list):
            if p_data[0] == frame_index:
                existing_point_data, existing_point_index_in_list = p_data, i
                break
        
        self._last_action_details = {
            "track_index": self.active_track_index, "frame_index": frame_index, "time_ms": time_ms
        }
        if existing_point_data:
            self._last_action_type = UndoActionType.POINT_MODIFIED
            self._last_action_details["previous_point_data"] = existing_point_data
        else:
            self._last_action_type = UndoActionType.POINT_ADDED
        
        new_point_data_tuple = (frame_index, time_ms, x_coord, y_coord)
        if existing_point_index_in_list != -1:
            active_track_list[existing_point_index_in_list] = new_point_data_tuple
        else:
            active_track_list.append(new_point_data_tuple)
            active_track_list.sort(key=lambda p: p[0])

        self.undoStateChanged.emit(True)
        self.activeTrackDataChanged.emit()
        self.trackListChanged.emit()
        if self.get_track_visibility_mode(self.active_track_index) != TrackVisibilityMode.HIDDEN:
            self.visualsNeedUpdate.emit()
        return True

    # --- MODIFIED: delete_point to store undo information ---
    def delete_point(self, track_index: int, frame_index: int) -> bool:
        if not (0 <= track_index < len(self.tracks)):
            logger.error(f"Delete Point Error: Invalid track index {track_index}.")
            self._clear_last_action() # Clear undo if attempted on invalid track
            return False

        target_track_list: Track = self.tracks[track_index]
        point_to_remove_idx: int = -1
        deleted_point_data: Optional[PointData] = None

        for i, point_data in enumerate(target_track_list):
            if point_data[0] == frame_index:
                point_to_remove_idx = i
                deleted_point_data = point_data # Store the data of the point being deleted
                break

        if point_to_remove_idx != -1 and deleted_point_data is not None:
            # --- Store information for UNDO ---
            self._last_action_type = UndoActionType.POINT_DELETED
            self._last_action_details = {
                "track_index": track_index,
                "frame_index": frame_index, # Though also in deleted_point_data, store for consistency
                "deleted_point_data": deleted_point_data # Store (frame, time, x, y)
            }
            logger.debug(f"Preparing UNDO for POINT_DELETED: Deleted data {deleted_point_data}")
            # --- End UNDO storage ---

            del target_track_list[point_to_remove_idx]
            track_id: int = track_index + 1
            logger.info(f"Deleted point from track {track_id} (index {track_index}) at frame {frame_index}")

            self.undoStateChanged.emit(True) # Undo is now available
            if track_index == self.active_track_index:
                self.activeTrackDataChanged.emit()
            self.trackListChanged.emit()
            if self.get_track_visibility_mode(track_index) != TrackVisibilityMode.HIDDEN:
                self.visualsNeedUpdate.emit()
            return True
        else:
            logger.warning(f"Attempted to delete point for track {track_index+1} at frame {frame_index}, but no point found.")
            self._clear_last_action() # No action was performed, clear any previous undo state
            return False

    def can_undo_last_point_action(self) -> bool:
        return self._last_action_type is not None

    # --- MODIFIED: undo_last_point_action to handle POINT_DELETED ---
    def undo_last_point_action(self) -> bool:
        if not self.can_undo_last_point_action():
            logger.info("Undo requested, but no action available to undo.")
            return False

        action_type = self._last_action_type
        details = self._last_action_details
        track_idx_to_undo = details.get("track_index")
        frame_idx_to_undo = details.get("frame_index") # Used for POINT_ADDED and POINT_MODIFIED

        if track_idx_to_undo is None or not (0 <= track_idx_to_undo < len(self.tracks)):
            # For POINT_DELETED, frame_idx_to_undo might not be directly used if deleted_point_data has it
            if action_type != UndoActionType.POINT_DELETED and frame_idx_to_undo is None:
                logger.error(f"Undo failed: Invalid details (track/frame index missing). Action: {action_type}")
                self._clear_last_action()
                return False
            elif action_type == UndoActionType.POINT_DELETED and details.get("deleted_point_data") is None:
                logger.error(f"Undo POINT_DELETED failed: Missing deleted_point_data.")
                self._clear_last_action()
                return False


        undone_successfully = False
        if action_type == UndoActionType.POINT_ADDED:
            logger.info(f"Undoing POINT_ADDED: Deleting point from track {track_idx_to_undo+1} at frame {frame_idx_to_undo}.")
            undone_successfully = self._delete_point_for_undo(track_idx_to_undo, frame_idx_to_undo)
        
        elif action_type == UndoActionType.POINT_MODIFIED:
            previous_data = details.get("previous_point_data")
            if previous_data and frame_idx_to_undo is not None:
                undone_successfully = self._restore_point_for_undo(track_idx_to_undo, frame_idx_to_undo, previous_data)
            else:
                logger.error("Undo POINT_MODIFIED failed: Missing previous_point_data or frame_idx_to_undo.")

        elif action_type == UndoActionType.POINT_DELETED:
            deleted_data = details.get("deleted_point_data")
            if deleted_data:
                # deleted_data is (frame, time, x, y)
                # We need to re-add this point to the track
                logger.info(f"Undoing POINT_DELETED: Restoring point {deleted_data} to track {track_idx_to_undo+1}.")
                undone_successfully = self._add_point_for_undo(track_idx_to_undo, deleted_data)
            else:
                logger.error("Undo POINT_DELETED failed: No deleted_point_data stored.")
        
        if undone_successfully:
            self._clear_last_action() # Clear after successful undo
            # Signals are emitted by the helper methods (_delete_point_for_undo, _restore_point_for_undo, _add_point_for_undo)
        else: # If failed but didn't clear (e.g., error in details before calling helper)
            if self.can_undo_last_point_action(): # Check if it wasn't already cleared by a failing helper
                 self._clear_last_action()
        
        return undone_successfully

    def _delete_point_for_undo(self, track_index: int, frame_index: int) -> bool:
        """Internal: Deletes a point, used by undo logic for POINT_ADDED."""
        if not (0 <= track_index < len(self.tracks)): return False
        target_track_list = self.tracks[track_index]
        point_idx = -1
        for i, p_data in enumerate(target_track_list):
            if p_data[0] == frame_index: point_idx = i; break
        if point_idx != -1:
            del target_track_list[point_idx]
            if track_index == self.active_track_index: self.activeTrackDataChanged.emit()
            self.trackListChanged.emit()
            if self.get_track_visibility_mode(track_index) != TrackVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
            return True
        return False

    def _restore_point_for_undo(self, track_index: int, frame_index: int, point_to_restore: PointData) -> bool:
        """Internal: Restores a modified point, used by undo for POINT_MODIFIED."""
        if not (0 <= track_index < len(self.tracks)): return False
        target_track_list = self.tracks[track_index]
        point_idx = -1
        for i, p_data in enumerate(target_track_list):
            if p_data[0] == frame_index: point_idx = i; break
        if point_idx != -1:
            target_track_list[point_idx] = point_to_restore
            if track_index == self.active_track_index: self.activeTrackDataChanged.emit()
            self.trackListChanged.emit()
            if self.get_track_visibility_mode(track_index) != TrackVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
            return True
        logger.error(f"_restore_point_for_undo: Point not found at frame {frame_index} in track {track_index+1}")
        return False

    # --- NEW: Internal helper to re-add a point for undoing a delete ---
    def _add_point_for_undo(self, track_index: int, point_data_to_add: PointData) -> bool:
        """
        Internal helper to add a point back to a track, used by undo logic for POINT_DELETED.
        Ensures the track remains sorted.
        """
        if not (0 <= track_index < len(self.tracks)):
            logger.error(f"_add_point_for_undo: Invalid track_index {track_index}")
            return False
        
        target_track_list: Track = self.tracks[track_index]
        
        # Check if point already exists (should not happen if logic is correct)
        for p_data in target_track_list:
            if p_data[0] == point_data_to_add[0]: # Compare frame index
                logger.warning(f"_add_point_for_undo: Point for frame {point_data_to_add[0]} already exists in track {track_index+1}. Overwriting for undo.")
                target_track_list[target_track_list.index(p_data)] = point_data_to_add
                target_track_list.sort(key=lambda p: p[0]) # Re-sort just in case
                break
        else: # Point does not exist, append and sort
            target_track_list.append(point_data_to_add)
            target_track_list.sort(key=lambda p: p[0]) # Keep track sorted by frame

        logger.info(f"Re-added point {point_data_to_add} to track {track_index+1} via undo.")

        # Emit signals for UI update
        if track_index == self.active_track_index:
            self.activeTrackDataChanged.emit()
        self.trackListChanged.emit()
        if self.get_track_visibility_mode(track_index) != TrackVisibilityMode.HIDDEN:
            self.visualsNeedUpdate.emit()
        return True

    def find_closest_visible_track(self, click_x: float, click_y: float, current_frame_index: int) -> int:
        min_dist_sq, closest_track_index = config.CLICK_TOLERANCE_SQ, -1
        for i, track_data in enumerate(self.tracks):
            vis_mode = self.get_track_visibility_mode(i)
            if vis_mode == TrackVisibilityMode.HIDDEN: continue
            for p_data in track_data:
                f_idx, _, px, py = p_data
                is_vis = (vis_mode == TrackVisibilityMode.ALWAYS_VISIBLE) or \
                         (vis_mode == TrackVisibilityMode.INCREMENTAL and f_idx <= current_frame_index)
                if is_vis:
                    dist_sq = (click_x - px)**2 + (click_y - py)**2
                    if dist_sq < min_dist_sq: min_dist_sq, closest_track_index = dist_sq, i
        return closest_track_index

    def get_visual_elements(self, current_frame_index: int) -> List[VisualElement]:
        visual_elements: List[VisualElement] = []
        if current_frame_index < 0: return visual_elements
        for i, track_data in enumerate(self.tracks):
            is_act = (i == self.active_track_index)
            vis_mode = self.get_track_visibility_mode(i)
            if vis_mode == TrackVisibilityMode.HIDDEN: continue
            line_stl = config.STYLE_LINE_ACTIVE if is_act else config.STYLE_LINE_INACTIVE
            prev_vis_pt = None
            for p_data in track_data:
                f_idx, _, px, py = p_data
                is_vis_now = (vis_mode == TrackVisibilityMode.ALWAYS_VISIBLE) or \
                             (vis_mode == TrackVisibilityMode.INCREMENTAL and f_idx <= current_frame_index)
                if is_vis_now:
                    is_curr_f = (f_idx == current_frame_index)
                    mark_stl = (config.STYLE_MARKER_ACTIVE_CURRENT if is_curr_f else config.STYLE_MARKER_ACTIVE_OTHER) if is_act \
                               else (config.STYLE_MARKER_INACTIVE_CURRENT if is_curr_f else config.STYLE_MARKER_INACTIVE_OTHER)
                    visual_elements.append({'type': 'marker', 'pos': (px, py), 'style': mark_stl, 'track_id': i + 1, 'frame_idx': f_idx})
                    if prev_vis_pt:
                        visual_elements.append({'type': 'line', 'p1': prev_vis_pt, 'p2': (px, py), 'style': line_stl, 'track_id': i + 1})
                    prev_vis_pt = (px, py)
        return visual_elements

    def find_closest_visible_point(self, click_x: float, click_y: float, current_frame_index: int) -> Optional[Tuple[int, PointData]]:
        min_dist_sq, cl_track_idx, cl_point_data = config.CLICK_TOLERANCE_SQ, -1, None
        for i, track_data in enumerate(self.tracks):
            vis_mode = self.get_track_visibility_mode(i)
            if vis_mode == TrackVisibilityMode.HIDDEN: continue
            for p_data_tuple in track_data:
                f_idx, _, px, py = p_data_tuple
                is_vis_now = (vis_mode == TrackVisibilityMode.ALWAYS_VISIBLE) or \
                             (vis_mode == TrackVisibilityMode.INCREMENTAL and f_idx <= current_frame_index)
                if is_vis_now:
                    dist_sq = (click_x - px)**2 + (click_y - py)**2
                    if dist_sq < min_dist_sq: min_dist_sq, cl_track_idx, cl_point_data = dist_sq, i, p_data_tuple
        return (cl_track_idx, cl_point_data) if cl_track_idx != -1 and cl_point_data is not None else None

    def get_track_summary(self) -> List[Tuple[int, int, int, int]]:
        summary = []
        for i, track in enumerate(self.tracks):
            n_pts = len(track)
            s_f, e_f = (-1, -1) if not n_pts else (track[0][0], track[-1][0])
            summary.append((i + 1, n_pts, s_f, e_f))
        return summary

    def get_active_track_points_for_table(self) -> Track:
        if self.active_track_index < 0 or self.active_track_index >= len(self.tracks): return []
        return list(self.tracks[self.active_track_index])

    def get_all_track_data(self) -> AllTracksData:
        return [list(track) for track in self.tracks]

    def load_tracks_from_data(self, parsed_data: List[Tuple[int, int, float, float, float]],
                              video_width: int, video_height: int, video_frame_count: int, video_fps: float
                             ) -> Tuple[bool, List[str]]:
        warnings, loaded_tracks_dict = [], defaultdict(list)
        time_tol_ms = (500 / video_fps) if video_fps > 0 else 50.0
        valid_pts, skip_pts = 0, 0
        for tid, fid, tms, x, y in parsed_data:
            p_desc = f"Point (T{tid},F{fid})"
            valid = True
            if not (0 <= fid < video_frame_count): warnings.append(f"{p_desc}: Frame out of range. Skip."); valid=False
            if valid and not (0 <= x < video_width): warnings.append(f"{p_desc}: X-coord out of range. Skip."); valid=False
            if valid and not (0 <= y < video_height): warnings.append(f"{p_desc}: Y-coord out of range. Skip."); valid=False
            if valid and video_fps > 0 and abs(tms-(fid/video_fps)*1000) > time_tol_ms: warnings.append(f"{p_desc}: Time inconsistent.")
            if valid: loaded_tracks_dict[tid].append((fid, tms, x, y)); valid_pts+=1
            else: logger.warning(warnings[-1]); skip_pts+=1
        
        self.reset()
        skip_empty_tracks = 0; loaded_count = 0
        for tid in sorted(loaded_tracks_dict.keys()):
            pts = loaded_tracks_dict[tid]
            if not pts: warnings.append(f"Track ID {tid} empty after validation. Skip."); skip_empty_tracks+=1; continue
            pts.sort(key=lambda p:p[0])
            self.tracks.append(pts)
            self.track_visibility_modes.append(TrackVisibilityMode.INCREMENTAL)
            loaded_count+=1
        self.active_track_index = -1
        self.trackListChanged.emit(); self.activeTrackDataChanged.emit(); self.visualsNeedUpdate.emit()
        return True, warnings