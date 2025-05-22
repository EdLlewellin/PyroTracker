# track_manager.py
"""
Manages element data (tracks, and eventually other types like lines),
including points, visibility states, and the active element selection.
Calculates visual elements (markers, lines) required for rendering
based on current state and frame, but does not draw.
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

ElementData = List[PointData] # For tracks, this is a list of points. For lines, it will be two points.
"""Type alias for the data associated with an element (e.g., a list of points for a track)."""

AllElementsForSaving = List[ElementData] # For saving, might need to distinguish by type if format changes
"""Type alias for all track data, a list of individual Tracks, used for saving for now."""


VisualElement = Dict[str, Any]
"""Type alias for the visual element structure passed for drawing.
   e.g., {'type': 'marker', 'pos': (x,y), 'style': STYLE_*, 'element_id': int}"""

class TrackVisibilityMode(Enum): # Renaming this can be a future step if it applies to more than tracks
    """Enum defining the visibility modes for elements like tracks."""
    HIDDEN = auto()
    INCREMENTAL = auto()
    ALWAYS_VISIBLE = auto()

class UndoActionType(Enum):
    """Defines the types of actions that can be undone."""
    POINT_ADDED = auto()
    POINT_MODIFIED = auto()
    POINT_DELETED = auto()
    # Future: LINE_ADDED, ELEMENT_DELETED etc.

class ElementType(Enum):
    """Defines the types of elements the manager can handle."""
    TRACK = auto()
    MEASUREMENT_LINE = auto() # For future use

class TrackManager(QtCore.QObject):
    """
    Manages data for different types of elements (tracks, lines) and calculates visual representation.
    """
    # Signals (consider renaming for generality in a later phase if needed)
    trackListChanged = QtCore.Signal() # Emitted when the list of elements changes (add/delete)
    activeTrackDataChanged = QtCore.Signal() # Emitted when active element's data or selection changes
    visualsNeedUpdate = QtCore.Signal()
    undoStateChanged = QtCore.Signal(bool)

    elements: List[Dict[str, Any]]
    active_element_index: int
    _next_element_id: int

    _last_action_type: Optional[UndoActionType] = None
    _last_action_details: Dict[str, Any] = {}

    # --- NEW: Internal state for line definition ---
    _is_defining_element_type: Optional[ElementType] = None
    _defining_element_first_point_data: Optional[PointData] = None
    _defining_element_frame_index: Optional[int] = None


    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        logger.info("Initializing TrackManager...")
        self.elements = []
        self.active_element_index = -1
        self._next_element_id = 1
        self._clear_last_action()
        self._reset_defining_state() # Initialize defining state
        logger.info("TrackManager initialized.")

    def _reset_defining_state(self) -> None:
        """Resets the internal state variables for defining a new element."""
        self._is_defining_element_type = None
        self._defining_element_first_point_data = None
        self._defining_element_frame_index = None

    def _clear_last_action(self) -> None:
        """Clears the stored last action, making undo unavailable."""
        self._last_action_type = None
        self._last_action_details = {}
        self.undoStateChanged.emit(False)

    def reset(self) -> None:
        logger.info("Resetting TrackManager state...")
        self.elements = []
        self.active_element_index = -1
        self._next_element_id = 1
        self._clear_last_action()
        self._reset_defining_state() # Also reset defining state on full reset
        logger.info("TrackManager reset complete.")
        self.trackListChanged.emit()
        self.activeTrackDataChanged.emit() # Ensure points table clears

    def _get_new_element_id(self) -> int:
        """Generates a new unique ID for an element."""
        current_max_id = 0
        if self.elements:
            current_max_id = max(el.get('id', 0) for el in self.elements)
        self._next_element_id = current_max_id + 1
        return self._next_element_id

    def create_new_track(self) -> int:
        """Creates a new element of type TRACK."""
        logger.info("Creating new track element...")
        new_id = self._get_new_element_id()
        new_element = {
            'id': new_id,
            'type': ElementType.TRACK,
            'name': f"Track {new_id}", # Default name
            'data': [], # Track data is a list of PointData
            'visibility_mode': TrackVisibilityMode.INCREMENTAL
        }
        self.elements.append(new_element)
        new_element_index: int = len(self.elements) - 1
        self.set_active_element(new_element_index) # Automatically select the new track

        logger.info(f"Created new track element ID {new_id} (index {new_element_index}).")
        self._clear_last_action() # Creating a new track clears any previous point undo
        self.trackListChanged.emit()
        return new_id

    # --- NEW METHOD for Phase 2 ---
    def create_new_line(self) -> int:
        """Creates a new element of type MEASUREMENT_LINE and prepares for definition."""
        logger.info("Creating new measurement line element...")
        new_id = self._get_new_element_id() # [cite: 103]
        new_element = {
            'id': new_id,
            'type': ElementType.MEASUREMENT_LINE, # [cite: 101]
            'name': f"Line {new_id}", # Default name
            'data': [], # Line data will be two PointData tuples [cite: 102]
            'visibility_mode': TrackVisibilityMode.INCREMENTAL # [cite: 103]
        }
        self.elements.append(new_element) # [cite: 104]
        new_element_index: int = len(self.elements) - 1
        self.set_active_element(new_element_index) # [cite: 104]

        # Enter defining state
        self._is_defining_element_type = ElementType.MEASUREMENT_LINE # [cite: 104]
        self._defining_element_first_point_data = None
        self._defining_element_frame_index = None # Will be set when first point is clicked

        logger.info(f"Created new measurement line element ID {new_id} (index {new_element_index}). Awaiting first point.")
        self._clear_last_action()
        self.trackListChanged.emit() # [cite: 105]
        return new_id
    # --- END NEW METHOD ---

    def delete_element_by_index(self, element_index_to_delete: int) -> bool:
        """Deletes an element by its current list index."""
        if not (0 <= element_index_to_delete < len(self.elements)):
            logger.error(f"Cannot delete element: Index {element_index_to_delete} is out of bounds (0-{len(self.elements)-1}).")
            return False

        deleted_element = self.elements[element_index_to_delete]
        element_id_deleted: int = deleted_element['id']
        element_type_deleted: ElementType = deleted_element['type']

        logger.info(f"Deleting element index {element_index_to_delete} (ID: {element_id_deleted}, Type: {element_type_deleted.name})...")
        was_visible = deleted_element['visibility_mode'] != TrackVisibilityMode.HIDDEN

        # If the element being deleted was in the process of being defined, reset defining state
        if self.active_element_index == element_index_to_delete and \
           self._is_defining_element_type is not None:
            self._reset_defining_state()
            logger.debug("Reset defining state because the element being defined was deleted.")


        del self.elements[element_index_to_delete]
        logger.debug(f"Removed element data for index {element_index_to_delete}.")

        active_element_changed: bool = False
        if self.active_element_index == element_index_to_delete:
            self.active_element_index = -1 # Deselect
            active_element_changed = True
        elif self.active_element_index > element_index_to_delete:
            self.active_element_index -= 1 # Adjust index
            active_element_changed = True
        
        self._clear_last_action()

        self.trackListChanged.emit() 
        if active_element_changed:
            self.activeTrackDataChanged.emit() 
        if was_visible:
            self.visualsNeedUpdate.emit()

        logger.info(f"Element ID {element_id_deleted} deleted successfully.")
        return True

    def set_active_element(self, element_index: int) -> None:
        """Sets the active element by its list index."""
        new_active_idx: int = -1
        if 0 <= element_index < len(self.elements):
            new_active_idx = element_index
        elif element_index != -1: 
            logger.warning(f"set_active_element: Invalid index {element_index}. Deselecting.")

        if self.active_element_index != new_active_idx:
            old_active_element_index: int = self.active_element_index
            
            # If we are deselecting an element that was being defined, cancel the definition process
            if new_active_idx == -1 and self._is_defining_element_type is not None and \
               old_active_element_index != -1 and self.elements[old_active_element_index]['type'] == self._is_defining_element_type:
                logger.info(f"Cancelling definition of element ID {self.elements[old_active_element_index]['id']} due to deselection.")
                # Remove the partially defined element if it has no points (typical for lines before 1st point)
                if not self.elements[old_active_element_index]['data']:
                    logger.debug(f"Removing empty element ID {self.elements[old_active_element_index]['id']} that was being defined.")
                    del self.elements[old_active_element_index]
                    # No need to adjust new_active_idx as it's -1.
                    # The active_element_index will be set to -1 below.
                    # Note: This means old_active_element_index is now invalid if it was the last element.
                    # The list of elements has changed, so re-emit trackListChanged.
                    self.trackListChanged.emit()
                self._reset_defining_state()

            self.active_element_index = new_active_idx
            old_vis_mode = self.get_element_visibility_mode(old_active_element_index) # Use old index before it's changed
            new_vis_mode = self.get_element_visibility_mode(self.active_element_index) # Use new index

            self._clear_last_action()
            self.activeTrackDataChanged.emit() 

            if (old_active_element_index != -1 and old_active_element_index < len(self.elements) and \
                self.elements[old_active_element_index]['visibility_mode'] != TrackVisibilityMode.HIDDEN) or \
               (self.active_element_index != -1 and new_vis_mode != TrackVisibilityMode.HIDDEN):
                 self.visualsNeedUpdate.emit()
            logger.debug(f"Active element set to index: {self.active_element_index}")
        else: # No change in active_element_index
             # If trying to set to the same element that is currently being defined, do nothing extra.
             # If trying to set to -1 when already -1, also do nothing.
            pass


    def set_element_visibility_mode(self, element_index: int, mode: TrackVisibilityMode) -> None:
        if not (0 <= element_index < len(self.elements)):
            return
        
        element = self.elements[element_index]
        if element['visibility_mode'] != mode:
            old_mode = element['visibility_mode']
            element['visibility_mode'] = mode
            logger.debug(f"Visibility for element ID {element['id']} (index {element_index}) set to {mode.name}")
            if old_mode != TrackVisibilityMode.HIDDEN or mode != TrackVisibilityMode.HIDDEN:
                self.visualsNeedUpdate.emit()
            self.trackListChanged.emit() 

    def get_element_visibility_mode(self, element_index: int) -> TrackVisibilityMode:
        if 0 <= element_index < len(self.elements):
            return self.elements[element_index]['visibility_mode']
        return TrackVisibilityMode.HIDDEN 

    def set_all_elements_visibility(self, mode: TrackVisibilityMode, element_type_filter: Optional[ElementType] = None) -> None:
        """Sets visibility for all elements, optionally filtered by type."""
        if not self.elements: return
        changed_any = False
        needs_visual_update_overall = False

        for i, element in enumerate(self.elements):
            if element_type_filter and element['type'] != element_type_filter:
                continue

            if element['visibility_mode'] != mode:
                old_mode = element['visibility_mode']
                element['visibility_mode'] = mode
                changed_any = True
                if old_mode != TrackVisibilityMode.HIDDEN or mode != TrackVisibilityMode.HIDDEN:
                    needs_visual_update_overall = True
        
        if changed_any:
            self.trackListChanged.emit()
        if needs_visual_update_overall:
            self.visualsNeedUpdate.emit()

    def get_active_element_id(self) -> int:
        """Returns the ID of the currently active element, or -1 if none."""
        if self.active_element_index != -1 and 0 <= self.active_element_index < len(self.elements):
            return self.elements[self.active_element_index]['id']
        return -1
        
    def get_active_element_type(self) -> Optional[ElementType]:
        """Returns the type of the currently active element, or None."""
        if self.active_element_index != -1 and 0 <= self.active_element_index < len(self.elements):
            return self.elements[self.active_element_index]['type']
        return None

    def get_point_for_active_element(self, frame_index: int) -> Optional[PointData]:
        """Gets a specific point for the active element if it's a TRACK and contains the point."""
        if self.active_element_index == -1: return None
        
        active_element = self.elements[self.active_element_index]
        if active_element['type'] == ElementType.TRACK:
            track_data: ElementData = active_element['data']
            for point_data in track_data:
                if point_data[0] == frame_index:
                    return point_data
        # Future: Could add logic for MEASUREMENT_LINE if we allow selecting its points
        return None

    def add_point(self, frame_index: int, time_ms: float, x: float, y: float) -> bool:
        """
        Adds or updates a point for the active element.
        For TRACK: Adds/updates a point in its list.
        For MEASUREMENT_LINE (during definition): Stores the first or second point.
        """
        if self.active_element_index == -1:
            logger.warning("add_point: No active element selected.")
            self._clear_last_action()
            return False

        active_element = self.elements[self.active_element_index]
        element_type = active_element['type']
        element_id = active_element['id']
        element_data: ElementData = active_element['data']
        x_coord, y_coord = round(x, 3), round(y, 3)
        new_point_data: PointData = (frame_index, time_ms, x_coord, y_coord)

        if element_type == ElementType.TRACK:
            existing_point_data_tuple: Optional[PointData] = None
            existing_point_idx_in_list: int = -1
            for i, p_data in enumerate(element_data):
                if p_data[0] == frame_index:
                    existing_point_data_tuple, existing_point_idx_in_list = p_data, i
                    break
            
            self._last_action_details = {
                "element_index": self.active_element_index,
                "frame_index": frame_index,
                "time_ms": time_ms
            }
            if existing_point_data_tuple:
                self._last_action_type = UndoActionType.POINT_MODIFIED
                self._last_action_details["previous_point_data"] = existing_point_data_tuple
            else:
                self._last_action_type = UndoActionType.POINT_ADDED
            
            if existing_point_idx_in_list != -1:
                element_data[existing_point_idx_in_list] = new_point_data
            else:
                element_data.append(new_point_data)
                element_data.sort(key=lambda p: p[0])
            
            self.undoStateChanged.emit(True)
            self.activeTrackDataChanged.emit()
            self.trackListChanged.emit()
            if active_element['visibility_mode'] != TrackVisibilityMode.HIDDEN:
                self.visualsNeedUpdate.emit()
            return True

        elif element_type == ElementType.MEASUREMENT_LINE and self._is_defining_element_type == ElementType.MEASUREMENT_LINE:
            # Logic for defining a line (Phase 3)
            # For Phase 2, this part isn't fully fleshed out but we acknowledge the type.
            logger.info(f"Point click received for defining MEASUREMENT_LINE (ID: {element_id}). Phase 3 will handle this.")
            # In Phase 3:
            # if self._defining_element_first_point_data is None:
            #     self._defining_element_first_point_data = new_point_data
            #     self._defining_element_frame_index = frame_index
            #     #MainWindow should then transition to "click second point" mode
            # elif self._defining_element_frame_index == frame_index: # Second point on same frame
            #     element_data.append(self._defining_element_first_point_data)
            #     element_data.append(new_point_data)
            #     self._reset_defining_state()
            #     # MainWindow should return to normal mode
            #     self.activeTrackDataChanged.emit() # To update points table for the line
            #     self.trackListChanged.emit() # To update lines table (length, angle)
            #     if active_element['visibility_mode'] != TrackVisibilityMode.HIDDEN:
            #         self.visualsNeedUpdate.emit()
            #     # Record UndoActionType.LINE_ADDED
            # else:
            #     logger.warning("Second point for line not on the same frame as the first. Action ignored.")
            #     return False
            return False # For Phase 2, don't fully process yet

        else:
            logger.warning(f"add_point: Active element (ID: {element_id}) is type {element_type.name}, "
                           f"or not in defining state for it. Cannot add point in current context.")
            self._clear_last_action()
            return False


    def delete_point(self, element_index_for_point_delete: int, frame_index: int) -> bool:
        """Deletes a point from the specified element (if it's a TRACK) at the given frame_index."""
        if not (0 <= element_index_for_point_delete < len(self.elements)):
            logger.error(f"Delete Point Error: Invalid element index {element_index_for_point_delete}.")
            self._clear_last_action()
            return False

        target_element = self.elements[element_index_for_point_delete]
        if target_element['type'] != ElementType.TRACK:
            logger.warning(f"Delete Point Error: Element ID {target_element['id']} is not a TRACK.")
            self._clear_last_action()
            return False

        track_data_list: ElementData = target_element['data']
        point_to_remove_idx: int = -1
        deleted_point_data_tuple: Optional[PointData] = None

        for i, p_data in enumerate(track_data_list):
            if p_data[0] == frame_index:
                point_to_remove_idx = i
                deleted_point_data_tuple = p_data 
                break

        if point_to_remove_idx != -1 and deleted_point_data_tuple is not None:
            self._last_action_type = UndoActionType.POINT_DELETED
            self._last_action_details = {
                "element_index": element_index_for_point_delete,
                "frame_index": frame_index, 
                "deleted_point_data": deleted_point_data_tuple 
            }
            del track_data_list[point_to_remove_idx]
            logger.info(f"Deleted point from element ID {target_element['id']} at frame {frame_index}")

            self.undoStateChanged.emit(True)
            if element_index_for_point_delete == self.active_element_index:
                self.activeTrackDataChanged.emit()
            self.trackListChanged.emit() 
            if target_element['visibility_mode'] != TrackVisibilityMode.HIDDEN:
                self.visualsNeedUpdate.emit()
            return True
        else:
            logger.warning(f"Attempted to delete point for element ID {target_element['id']} at frame {frame_index}, but no point found.")
            self._clear_last_action()
            return False

    def can_undo_last_point_action(self) -> bool:
        """Checks if the last action was a point operation that can be undone."""
        # For now, only point operations on TRACKS are undoable
        if self._last_action_type in [UndoActionType.POINT_ADDED, UndoActionType.POINT_MODIFIED, UndoActionType.POINT_DELETED]:
            details = self._last_action_details
            element_idx_to_undo = details.get("element_index")
            if element_idx_to_undo is not None and 0 <= element_idx_to_undo < len(self.elements):
                if self.elements[element_idx_to_undo]['type'] == ElementType.TRACK:
                    return True
        return False

    def undo_last_point_action(self) -> bool:
        if not self.can_undo_last_point_action(): # This now also checks if it's a TRACK
            logger.info("Undo requested, but no TRACK point action available to undo.")
            return False

        action_type = self._last_action_type
        details = self._last_action_details
        element_idx_to_undo = details.get("element_index") # Already validated by can_undo
        
        target_element = self.elements[element_idx_to_undo] # Known to be a TRACK
        frame_idx_to_undo = details.get("frame_index") 
        undone_successfully = False

        if action_type == UndoActionType.POINT_ADDED:
            if frame_idx_to_undo is not None:
                logger.info(f"Undoing POINT_ADDED: Deleting point from element ID {target_element['id']} at frame {frame_idx_to_undo}.")
                undone_successfully = self._delete_point_for_undo(element_idx_to_undo, frame_idx_to_undo)
            else: logger.error("Undo POINT_ADDED failed: Missing frame_index in details.")
        
        elif action_type == UndoActionType.POINT_MODIFIED:
            previous_data = details.get("previous_point_data")
            if previous_data and frame_idx_to_undo is not None:
                logger.info(f"Undoing POINT_MODIFIED: Restoring point for element ID {target_element['id']} at frame {frame_idx_to_undo}.")
                undone_successfully = self._restore_point_for_undo(element_idx_to_undo, frame_idx_to_undo, previous_data)
            else: logger.error("Undo POINT_MODIFIED failed: Missing previous_point_data or frame_idx_to_undo.")

        elif action_type == UndoActionType.POINT_DELETED:
            deleted_data = details.get("deleted_point_data")
            if deleted_data:
                logger.info(f"Undoing POINT_DELETED: Restoring point {deleted_data} to element ID {target_element['id']}.")
                undone_successfully = self._add_point_for_undo(element_idx_to_undo, deleted_data)
            else: logger.error("Undo POINT_DELETED failed: No deleted_point_data stored.")
        
        if undone_successfully:
            self._clear_last_action()
        else: # If undo failed for some reason, still clear the action to prevent repeated failed attempts
            if self.can_undo_last_point_action(): # Check again before clearing
                 self._clear_last_action() 
        return undone_successfully

    def _delete_point_for_undo(self, element_index: int, frame_index: int) -> bool:
        """Internal: Deletes a point from a TRACK element, used by undo logic."""
        track_data_list: ElementData = self.elements[element_index]['data']
        point_idx = -1
        for i, p_data in enumerate(track_data_list):
            if p_data[0] == frame_index: point_idx = i; break
        if point_idx != -1:
            del track_data_list[point_idx]
            if element_index == self.active_element_index: self.activeTrackDataChanged.emit()
            self.trackListChanged.emit()
            if self.elements[element_index]['visibility_mode'] != TrackVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
            return True
        return False

    def _restore_point_for_undo(self, element_index: int, frame_index: int, point_to_restore: PointData) -> bool:
        """Internal: Restores a modified point in a TRACK element, used by undo logic."""
        track_data_list: ElementData = self.elements[element_index]['data']
        point_idx = -1
        for i, p_data in enumerate(track_data_list):
            if p_data[0] == frame_index: point_idx = i; break
        if point_idx != -1:
            track_data_list[point_idx] = point_to_restore
            if element_index == self.active_element_index: self.activeTrackDataChanged.emit()
            self.trackListChanged.emit()
            if self.elements[element_index]['visibility_mode'] != TrackVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
            return True
        logger.error(f"_restore_point_for_undo: Point not found at frame {frame_index} in element ID {self.elements[element_index]['id']}")
        return False

    def _add_point_for_undo(self, element_index: int, point_data_to_add: PointData) -> bool:
        """Internal helper to add a point back to a TRACK element, used by undo for POINT_DELETED."""
        track_data_list: ElementData = self.elements[element_index]['data']
        for i, p_data in enumerate(track_data_list):
            if p_data[0] == point_data_to_add[0]: 
                logger.warning(f"_add_point_for_undo: Point for frame {point_data_to_add[0]} already exists in element ID {self.elements[element_index]['id']}. Overwriting for undo.")
                track_data_list[i] = point_data_to_add
                track_data_list.sort(key=lambda p: p[0]) 
                break
        else: 
            track_data_list.append(point_data_to_add)
            track_data_list.sort(key=lambda p: p[0])

        logger.info(f"Re-added point {point_data_to_add} to element ID {self.elements[element_index]['id']} via undo.")
        if element_index == self.active_element_index: self.activeTrackDataChanged.emit()
        self.trackListChanged.emit()
        if self.elements[element_index]['visibility_mode'] != TrackVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
        return True

    def find_closest_visible_track_element_index(self, click_x: float, click_y: float, current_frame_index: int) -> int:
        """Finds the index of the closest visible TRACK element to a click."""
        min_dist_sq = config.CLICK_TOLERANCE_SQ
        closest_element_index = -1
        for i, element in enumerate(self.elements):
            if element['type'] != ElementType.TRACK: continue 

            vis_mode = element['visibility_mode']
            if vis_mode == TrackVisibilityMode.HIDDEN: continue

            track_data: ElementData = element['data']
            for p_data in track_data:
                f_idx, _, px, py = p_data
                is_vis = (vis_mode == TrackVisibilityMode.ALWAYS_VISIBLE) or \
                         (vis_mode == TrackVisibilityMode.INCREMENTAL and f_idx <= current_frame_index)
                if is_vis: 
                    dist_sq = (click_x - px)**2 + (click_y - py)**2
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        closest_element_index = i
        return closest_element_index

    def get_visual_elements(self, current_frame_index: int) -> List[VisualElement]:
        """Generates visual elements for all managed items (currently only tracks)."""
        visual_elements_list: List[VisualElement] = []
        if current_frame_index < 0: return visual_elements_list

        for i, element in enumerate(self.elements):
            element_id = element['id']
            element_type = element['type']
            element_data: ElementData = element['data']
            visibility_mode = element['visibility_mode']
            is_active_element = (i == self.active_element_index)

            if visibility_mode == TrackVisibilityMode.HIDDEN:
                continue

            if element_type == ElementType.TRACK:
                line_style = config.STYLE_LINE_ACTIVE if is_active_element else config.STYLE_LINE_INACTIVE
                previous_visible_point_coords: Optional[Tuple[float,float]] = None

                for point_data_tuple in element_data:
                    frame_idx, _, point_x, point_y = point_data_tuple
                    
                    is_point_visible_now = False
                    if visibility_mode == TrackVisibilityMode.ALWAYS_VISIBLE:
                        is_point_visible_now = True
                    elif visibility_mode == TrackVisibilityMode.INCREMENTAL and frame_idx <= current_frame_index:
                        is_point_visible_now = True

                    if is_point_visible_now:
                        is_current_frame_marker = (frame_idx == current_frame_index)
                        
                        marker_style = ""
                        if is_active_element:
                            marker_style = config.STYLE_MARKER_ACTIVE_CURRENT if is_current_frame_marker else config.STYLE_MARKER_ACTIVE_OTHER
                        else: 
                            marker_style = config.STYLE_MARKER_INACTIVE_CURRENT if is_current_frame_marker else config.STYLE_MARKER_INACTIVE_OTHER
                        
                        visual_elements_list.append({
                            'type': 'marker', 
                            'pos': (point_x, point_y), 
                            'style': marker_style, 
                            'element_id': element_id, 
                            'frame_idx': frame_idx
                        })

                        if previous_visible_point_coords:
                            visual_elements_list.append({
                                'type': 'line', 
                                'p1': previous_visible_point_coords, 
                                'p2': (point_x, point_y), 
                                'style': line_style, 
                                'element_id': element_id
                            })
                        previous_visible_point_coords = (point_x, point_y)
            
            # Future: Add logic for ElementType.MEASUREMENT_LINE here in Phase 4+

        return visual_elements_list

    def find_closest_visible_point(self, click_x: float, click_y: float, current_frame_index: int) -> Optional[Tuple[int, PointData]]:
        """Finds the closest visible point of a TRACK element to a click."""
        min_dist_sq = config.CLICK_TOLERANCE_SQ
        closest_element_idx = -1
        closest_point_data: Optional[PointData] = None

        for i, element in enumerate(self.elements):
            if element['type'] != ElementType.TRACK: continue

            vis_mode = element['visibility_mode']
            if vis_mode == TrackVisibilityMode.HIDDEN: continue
            
            track_data: ElementData = element['data']
            for p_data_tuple in track_data:
                f_idx, _, px, py = p_data_tuple
                is_vis_now = (vis_mode == TrackVisibilityMode.ALWAYS_VISIBLE) or \
                             (vis_mode == TrackVisibilityMode.INCREMENTAL and f_idx <= current_frame_index)
                if is_vis_now:
                    dist_sq = (click_x - px)**2 + (click_y - py)**2
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        closest_element_idx = i
                        closest_point_data = p_data_tuple
                        
        if closest_element_idx != -1 and closest_point_data is not None:
            return (closest_element_idx, closest_point_data)
        return None

    def get_track_elements_summary(self) -> List[Tuple[int, int, int, int]]:
        """Provides a summary for TRACK type elements (for the tracks table)."""
        summary = []
        for i, element in enumerate(self.elements):
            if element['type'] == ElementType.TRACK:
                track_data: ElementData = element['data']
                num_points = len(track_data)
                start_frame, end_frame = (-1, -1)
                if num_points > 0:
                    start_frame = track_data[0][0]
                    end_frame = track_data[-1][0]
                summary.append((element['id'], num_points, start_frame, end_frame))
        return summary

    def get_active_element_points_if_track(self) -> ElementData:
        """Returns point data for the active element if it's a TRACK (for points table)."""
        if self.active_element_index != -1:
            active_element = self.elements[self.active_element_index]
            if active_element['type'] == ElementType.TRACK:
                return list(active_element['data']) 
        return []

    def get_all_track_type_data_for_saving(self) -> AllElementsForSaving:
        """Returns data for all TRACK type elements, in the old AllTracksData format for saving."""
        tracks_data_to_save: AllElementsForSaving = []
        for element in self.elements:
            if element['type'] == ElementType.TRACK:
                tracks_data_to_save.append(list(element['data'])) 
        return tracks_data_to_save

    def load_tracks_from_data(self, parsed_data: List[Tuple[int, int, float, float, float]],
                              video_width: int, video_height: int, video_frame_count: int, video_fps: float
                             ) -> Tuple[bool, List[str]]:
        """Loads data from CSV, creating TRACK elements."""
        warnings: List[str] = []
        loaded_elements_by_id: Dict[int, List[PointData]] = defaultdict(list)
        
        time_tolerance_ms = (500 / video_fps) if video_fps > 0 else 50.0 
        valid_points_count = 0
        skipped_points_count = 0

        for track_id_from_file, frame_idx, time_ms, x, y in parsed_data:
            point_description = f"Point (ID {track_id_from_file}, F{frame_idx})"
            is_valid_point = True
            if not (0 <= frame_idx < video_frame_count):
                warnings.append(f"{point_description}: Frame index out of video range. Skipped.")
                is_valid_point = False
            if is_valid_point and not (0 <= x < video_width): 
                warnings.append(f"{point_description}: X-coordinate out of video width. Skipped.")
                is_valid_point = False
            if is_valid_point and not (0 <= y < video_height):
                warnings.append(f"{point_description}: Y-coordinate out of video height. Skipped.")
                is_valid_point = False
            
            if is_valid_point and video_fps > 0:
                expected_time_ms = (frame_idx / video_fps) * 1000.0
                if abs(time_ms - expected_time_ms) > time_tolerance_ms:
                    warnings.append(f"{point_description}: Time ({time_ms:.1f}ms) seems inconsistent with frame index and FPS (expected ~{expected_time_ms:.1f}ms). Using file time.")
            
            if is_valid_point:
                loaded_elements_by_id[track_id_from_file].append((frame_idx, time_ms, x, y))
                valid_points_count +=1
            else:
                logger.warning(warnings[-1]) 
                skipped_points_count +=1
        
        self.reset() 
        
        skipped_empty_tracks_count = 0
        loaded_elements_count = 0
        
        sorted_track_ids_from_file = sorted(loaded_elements_by_id.keys())

        for element_id_from_file in sorted_track_ids_from_file:
            points_for_this_element = loaded_elements_by_id[element_id_from_file]
            if not points_for_this_element:
                warnings.append(f"Track ID {element_id_from_file} from file is empty after validation. Skipped.")
                skipped_empty_tracks_count += 1
                continue

            points_for_this_element.sort(key=lambda p: p[0]) 

            # For now, assuming loaded CSVs only contain TRACK type data.
            # Phase 3 load logic will need to infer type based on point count per frame. [cite: 80, 81]
            new_element = {
                'id': element_id_from_file, 
                'type': ElementType.TRACK, # All loaded elements are initially tracks [cite: 91]
                'name': f"Track {element_id_from_file}",
                'data': points_for_this_element,
                'visibility_mode': TrackVisibilityMode.INCREMENTAL 
            }
            self.elements.append(new_element)
            loaded_elements_count += 1
            if element_id_from_file >= self._next_element_id:
                self._next_element_id = element_id_from_file + 1
                
        self.active_element_index = -1 
        
        logger.info(f"Load from data: {loaded_elements_count} element(s) (assumed TRACK type) loaded with {valid_points_count} points. "
                    f"{skipped_points_count} points skipped. {skipped_empty_tracks_count} empty elements skipped.")

        self.trackListChanged.emit()
        self.activeTrackDataChanged.emit() 
        self.visualsNeedUpdate.emit() 
        
        return True, warnings