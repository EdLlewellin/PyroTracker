# element_manager.py
"""
Manages element data (tracks, and eventually other types like lines),
including points, visibility states, and the active element selection.
Calculates visual elements (markers, lines) required for rendering
based on current state and frame, but does not draw.
"""
import logging
import math # Added for length and angle calculation
from collections import defaultdict
from enum import Enum, auto
from typing import List, Tuple, Dict, Optional, Any, TYPE_CHECKING # Added TYPE_CHECKING
import copy

from PySide6 import QtCore

import config
import settings_manager 

if TYPE_CHECKING:
    from scale_manager import ScaleManager # For type hinting

logger = logging.getLogger(__name__)

# --- Type Aliases ---
PointData = Tuple[int, float, float, float]
ElementData = List[PointData]
AllElementsForSaving = List[ElementData]
VisualElement = Dict[str, Any]

class ElementVisibilityMode(Enum):
    HIDDEN = auto()
    HOME_FRAME = auto()
    INCREMENTAL = auto()
    ALWAYS_VISIBLE = auto()

class UndoActionType(Enum):
    POINT_ADDED = auto()
    POINT_MODIFIED = auto()
    POINT_DELETED = auto()

class ElementType(Enum):
    TRACK = auto()
    MEASUREMENT_LINE = auto()

class ElementManager(QtCore.QObject):
    elementListChanged = QtCore.Signal()
    activeElementDataChanged = QtCore.Signal()
    visualsNeedUpdate = QtCore.Signal()
    undoStateChanged = QtCore.Signal(bool)

    elements: List[Dict[str, Any]]
    active_element_index: int
    _next_element_id: int
    _last_action_type: Optional[UndoActionType] = None
    _last_action_details: Dict[str, Any] = {}
    _is_defining_element_type: Optional[ElementType] = None
    _defining_element_first_point_data: Optional[PointData] = None
    _defining_element_frame_index: Optional[int] = None

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        logger.info("Initializing ElementManager...")
        self.elements = []
        self.active_element_index = -1
        self._next_element_id = 1
        self._clear_last_action()
        self._reset_defining_state()
        logger.info("ElementManager initialized.")

    def _reset_defining_state(self) -> None:
        self._is_defining_element_type = None
        self._defining_element_first_point_data = None
        self._defining_element_frame_index = None

    def _clear_last_action(self) -> None:
        self._last_action_type = None
        self._last_action_details = {}
        self.undoStateChanged.emit(False)

    def reset(self) -> None:
        logger.info("Resetting ElementManager state...")
        self.elements = []
        self.active_element_index = -1
        self._next_element_id = 1
        self._clear_last_action()
        self._reset_defining_state()
        logger.info("ElementManager reset complete.")
        self.elementListChanged.emit()
        self.activeElementDataChanged.emit()

    def _get_new_element_id(self) -> int:
        current_max_id = 0
        if self.elements:
            current_max_id = max(el.get('id', 0) for el in self.elements)
        self._next_element_id = current_max_id + 1
        return self._next_element_id

    def create_new_track(self) -> int:
        logger.info("Creating new track element...")
        new_id = self._get_new_element_id()
        new_element = {
            'id': new_id,
            'type': ElementType.TRACK,
            'name': f"Track {new_id}",
            'data': [],
            'visibility_mode': ElementVisibilityMode.INCREMENTAL
        }
        self.elements.append(new_element)
        new_element_index: int = len(self.elements) - 1
        self.set_active_element(new_element_index)
        logger.info(f"Created new track element ID {new_id} (index {new_element_index}).")
        self._clear_last_action()
        self.elementListChanged.emit()
        return new_id

    def create_new_line(self) -> int:
        logger.info("Creating new measurement line element...")
        new_id = self._get_new_element_id()
        new_element = {
            'id': new_id,
            'type': ElementType.MEASUREMENT_LINE,
            'name': f"Line {new_id}",
            'data': [],
            'visibility_mode': ElementVisibilityMode.INCREMENTAL
        }
        self.elements.append(new_element)
        new_element_index: int = len(self.elements) - 1
        self.set_active_element(new_element_index)
        self._is_defining_element_type = ElementType.MEASUREMENT_LINE
        self._defining_element_first_point_data = None
        self._defining_element_frame_index = None
        logger.info(f"Created new measurement line element ID {new_id} (index {new_element_index}). Awaiting first point.")
        self._clear_last_action()
        self.elementListChanged.emit()
        return new_id

    def cancel_active_line_definition(self) -> None:
        logger.debug("Attempting to cancel active line definition...")
        if self._is_defining_element_type == ElementType.MEASUREMENT_LINE and \
           self.active_element_index != -1 and \
           0 <= self.active_element_index < len(self.elements):
            current_defining_element = self.elements[self.active_element_index]
            element_id_cancelled = current_defining_element.get('id', 'N/A')
            if current_defining_element.get('type') == ElementType.MEASUREMENT_LINE and \
               not current_defining_element['data']:
                logger.info(f"Cancelling definition of Measurement Line ID {element_id_cancelled}. Removing empty element.")
                del self.elements[self.active_element_index]
                self._reset_defining_state()
                self.active_element_index = -1
                self.elementListChanged.emit()
                self.activeElementDataChanged.emit()
                self.visualsNeedUpdate.emit()
                self._clear_last_action()
                return
            logger.debug(f"Line ID {element_id_cancelled} was being defined but might have data. Resetting defining state only.")
        if self._is_defining_element_type is not None:
            self._reset_defining_state()
            self.visualsNeedUpdate.emit()
            logger.debug("Reset defining state in ElementManager due to cancellation request.")
        else:
            logger.debug("No active line definition process to cancel in ElementManager.")

    def delete_element_by_index(self, element_index_to_delete: int) -> bool:
        if not (0 <= element_index_to_delete < len(self.elements)):
            logger.error(f"Cannot delete element: Index {element_index_to_delete} out of bounds.")
            return False
        deleted_element = self.elements[element_index_to_delete]
        element_id_deleted: int = deleted_element['id']
        element_type_deleted: ElementType = deleted_element['type']
        logger.info(f"Deleting element index {element_index_to_delete} (ID: {element_id_deleted}, Type: {element_type_deleted.name})...")
        was_visible = deleted_element['visibility_mode'] != ElementVisibilityMode.HIDDEN
        if self.active_element_index == element_index_to_delete and self._is_defining_element_type is not None:
            self._reset_defining_state()
            logger.debug("Reset defining state because the element being defined was deleted.")
        del self.elements[element_index_to_delete]
        active_element_changed: bool = False
        if self.active_element_index == element_index_to_delete:
            self.active_element_index = -1
            active_element_changed = True
        elif self.active_element_index > element_index_to_delete:
            self.active_element_index -= 1
            active_element_changed = True
        self._clear_last_action()
        self.elementListChanged.emit()
        if active_element_changed: self.activeElementDataChanged.emit()
        if was_visible: self.visualsNeedUpdate.emit()
        logger.info(f"Element ID {element_id_deleted} deleted successfully.")
        return True

    def set_active_element(self, element_index: int) -> None:
        new_active_idx: int = -1
        if 0 <= element_index < len(self.elements):
            new_active_idx = element_index
        elif element_index != -1:
            logger.warning(f"set_active_element: Invalid index {element_index}. Deselecting.")

        if self.active_element_index != new_active_idx:
            old_active_element_index: int = self.active_element_index
            if new_active_idx == -1 and self._is_defining_element_type is not None and \
               old_active_element_index != -1 and \
               0 <= old_active_element_index < len(self.elements) and \
               self.elements[old_active_element_index]['type'] == self._is_defining_element_type:
                logger.info(f"Cancelling definition of element ID {self.elements[old_active_element_index]['id']} due to deselection.")
                if not self.elements[old_active_element_index]['data']: # If it was an empty line being defined
                    logger.debug(f"Removing empty element ID {self.elements[old_active_element_index]['id']} that was being defined.")
                    del self.elements[old_active_element_index]
                    self.elementListChanged.emit() # Notify list changed before resetting state
                self._reset_defining_state()
            
            self.active_element_index = new_active_idx
            self._clear_last_action() # Changed active element, clear undo for point ops
            self.activeElementDataChanged.emit() # Emit that active data (or lack thereof) changed

            # Determine if a redraw is needed based on visibility of old/new active elements
            old_element_was_visible = False
            if old_active_element_index != -1 and old_active_element_index < len(self.elements): # Check if old index is still valid (it might have been deleted if cancelling definition)
                 if self.elements[old_active_element_index]['visibility_mode'] != ElementVisibilityMode.HIDDEN:
                    old_element_was_visible = True
            
            new_element_is_visible = False
            if self.active_element_index != -1: # New active element exists
                if self.elements[self.active_element_index]['visibility_mode'] != ElementVisibilityMode.HIDDEN:
                    new_element_is_visible = True

            if old_element_was_visible or new_element_is_visible:
                 self.visualsNeedUpdate.emit()
            logger.debug(f"Active element set to index: {self.active_element_index}")

    def set_element_visibility_mode(self, element_index: int, mode: ElementVisibilityMode) -> None:
        if not (0 <= element_index < len(self.elements)): return
        element = self.elements[element_index]
        if element['visibility_mode'] != mode:
            old_mode = element['visibility_mode']
            element['visibility_mode'] = mode
            logger.debug(f"Visibility for element ID {element['id']} (index {element_index}) set to {mode.name}")
            if old_mode != ElementVisibilityMode.HIDDEN or mode != ElementVisibilityMode.HIDDEN:
                self.visualsNeedUpdate.emit()
            self.elementListChanged.emit() # To update table radio buttons

    def get_element_visibility_mode(self, element_index: int) -> ElementVisibilityMode:
        if 0 <= element_index < len(self.elements):
            return self.elements[element_index]['visibility_mode']
        return ElementVisibilityMode.HIDDEN 

    def set_all_elements_visibility(self, mode: ElementVisibilityMode, element_type_filter: Optional[ElementType] = None) -> None:
        if not self.elements: return
        changed_any = False
        needs_visual_update_overall = False
        for i, element in enumerate(self.elements):
            if element_type_filter and element['type'] != element_type_filter: continue
            if element['visibility_mode'] != mode:
                old_mode = element['visibility_mode']
                element['visibility_mode'] = mode
                changed_any = True
                if old_mode != ElementVisibilityMode.HIDDEN or mode != ElementVisibilityMode.HIDDEN:
                    needs_visual_update_overall = True
        if changed_any: self.elementListChanged.emit()
        if needs_visual_update_overall: self.visualsNeedUpdate.emit()

    def get_active_element_id(self) -> int:
        if self.active_element_index != -1 and 0 <= self.active_element_index < len(self.elements):
            return self.elements[self.active_element_index]['id']
        return -1
        
    def get_active_element_type(self) -> Optional[ElementType]:
        if self.active_element_index != -1 and 0 <= self.active_element_index < len(self.elements):
            return self.elements[self.active_element_index]['type']
        return None

    def get_point_for_active_element(self, frame_index: int) -> Optional[PointData]:
        if self.active_element_index == -1: return None
        active_element = self.elements[self.active_element_index]
        if active_element['type'] == ElementType.TRACK:
            track_data: ElementData = active_element['data']
            for point_data in track_data:
                if point_data[0] == frame_index: return point_data
        return None

    def add_point(self, frame_index: int, time_ms: float, x: float, y: float) -> bool:
        if self.active_element_index == -1:
            logger.warning("add_point: No active element selected.")
            self._clear_last_action(); return False
        active_element = self.elements[self.active_element_index]
        element_type = active_element['type']
        element_id = active_element['id']
        element_data: ElementData = active_element['data']
        x_coord, y_coord = round(x, 3), round(y, 3)
        new_point_data: PointData = (frame_index, time_ms, x_coord, y_coord)

        if element_type == ElementType.TRACK:
            # ... (existing track point addition logic) ...
            existing_point_data_tuple: Optional[PointData] = None; existing_point_idx_in_list: int = -1
            for i, p_data in enumerate(element_data):
                if p_data[0] == frame_index: existing_point_data_tuple, existing_point_idx_in_list = p_data, i; break
            self._last_action_details = {"element_index": self.active_element_index, "frame_index": frame_index, "time_ms": time_ms}
            if existing_point_data_tuple: self._last_action_type = UndoActionType.POINT_MODIFIED; self._last_action_details["previous_point_data"] = existing_point_data_tuple
            else: self._last_action_type = UndoActionType.POINT_ADDED
            if existing_point_idx_in_list != -1: element_data[existing_point_idx_in_list] = new_point_data
            else: element_data.append(new_point_data); element_data.sort(key=lambda p: p[0])
            self.undoStateChanged.emit(True); self.activeElementDataChanged.emit(); self.elementListChanged.emit()
            if active_element['visibility_mode'] != ElementVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
            return True
        elif element_type == ElementType.MEASUREMENT_LINE and self._is_defining_element_type == ElementType.MEASUREMENT_LINE and active_element['id'] == self.get_active_element_id():
            if self._defining_element_first_point_data is None: # Defining first point of the line
                self._defining_element_first_point_data = new_point_data
                self._defining_element_frame_index = frame_index # Store the frame for the line
                logger.info(f"Measurement Line (ID: {element_id}): First point set at frame {frame_index}. Awaiting second point.")
                self.visualsNeedUpdate.emit() # To show the first temporary marker if any
                return True
            else: # Defining second point of the line
                if self._defining_element_frame_index == frame_index: # Second point must be on the same frame
                    element_data.clear() # Clear any previous attempts if re-clicked
                    element_data.append(self._defining_element_first_point_data)
                    element_data.append(new_point_data)
                    logger.info(f"Measurement Line (ID: {element_id}): Second point set at frame {frame_index}. Line defined.")
                    
                    defining_element_id_before_reset = self.get_active_element_id()
                    self._reset_defining_state() # Line definition complete
                    self._clear_last_action() # Line creation is a single conceptual action, not undone point-by-point here yet

                    # Emit signals after state is fully updated
                    if self.active_element_index != -1 and \
                       0 <= self.active_element_index < len(self.elements) and \
                       self.elements[self.active_element_index]['id'] == defining_element_id_before_reset :
                        self.activeElementDataChanged.emit() # Update points table for this line

                    self.elementListChanged.emit() # Update lines table (e.g., with length/angle later)
                    if active_element['visibility_mode'] != ElementVisibilityMode.HIDDEN:
                        self.visualsNeedUpdate.emit()
                    return True
                else:
                    logger.warning(f"Measurement Line (ID: {element_id}): Second point must be on the same frame as the first (expected frame {self._defining_element_frame_index}, got {frame_index}). Action ignored.")
                    # Do not clear defining state here, user might click again on the correct frame.
                    return False
        else:
            logger.warning(f"add_point: Active element (ID: {element_id}) is type {element_type.name}, or not in defining state for it. Cannot add point in current context.")
            if self._is_defining_element_type is not None and active_element['id'] != self.get_active_element_id():
                logger.warning(f"Mismatch: Defining type {self._is_defining_element_type.name} but active element is {active_element['id']} / {element_type.name}")
            self._clear_last_action(); return False

    def delete_point(self, element_index_for_point_delete: int, frame_index: int) -> bool:
        # ... (existing track point deletion logic, no changes here for now) ...
        if not (0 <= element_index_for_point_delete < len(self.elements)): self._clear_last_action(); return False
        target_element = self.elements[element_index_for_point_delete]
        if target_element['type'] != ElementType.TRACK: self._clear_last_action(); return False
        track_data_list: ElementData = target_element['data']; point_to_remove_idx: int = -1; deleted_point_data_tuple: Optional[PointData] = None
        for i, p_data in enumerate(track_data_list):
            if p_data[0] == frame_index: point_to_remove_idx = i; deleted_point_data_tuple = p_data; break
        if point_to_remove_idx != -1 and deleted_point_data_tuple is not None:
            self._last_action_type = UndoActionType.POINT_DELETED; self._last_action_details = {"element_index": element_index_for_point_delete, "frame_index": frame_index, "deleted_point_data": deleted_point_data_tuple}
            del track_data_list[point_to_remove_idx]; logger.info(f"Deleted point from element ID {target_element['id']} at frame {frame_index}")
            self.undoStateChanged.emit(True)
            if element_index_for_point_delete == self.active_element_index: self.activeElementDataChanged.emit()
            self.elementListChanged.emit(); 
            if target_element['visibility_mode'] != ElementVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
            return True
        else: self._clear_last_action(); return False

    def can_undo_last_point_action(self) -> bool:
        # ... (existing logic, no changes here for now) ...
        if self._last_action_type in [UndoActionType.POINT_ADDED, UndoActionType.POINT_MODIFIED, UndoActionType.POINT_DELETED]:
            details = self._last_action_details; element_idx_to_undo = details.get("element_index")
            if element_idx_to_undo is not None and 0 <= element_idx_to_undo < len(self.elements):
                if self.elements[element_idx_to_undo]['type'] == ElementType.TRACK: return True
        return False

    def undo_last_point_action(self) -> bool:
        # ... (existing logic, no changes here for now) ...
        if not self.can_undo_last_point_action(): return False
        action_type = self._last_action_type; details = self._last_action_details; element_idx_to_undo = details.get("element_index")
        frame_idx_to_undo = details.get("frame_index"); undone_successfully = False
        if action_type == UndoActionType.POINT_ADDED:
            if frame_idx_to_undo is not None: undone_successfully = self._delete_point_for_undo(element_idx_to_undo, frame_idx_to_undo)
        elif action_type == UndoActionType.POINT_MODIFIED:
            previous_data = details.get("previous_point_data")
            if previous_data and frame_idx_to_undo is not None: undone_successfully = self._restore_point_for_undo(element_idx_to_undo, frame_idx_to_undo, previous_data)
        elif action_type == UndoActionType.POINT_DELETED:
            deleted_data = details.get("deleted_point_data")
            if deleted_data: undone_successfully = self._add_point_for_undo(element_idx_to_undo, deleted_data)
        if undone_successfully: self._clear_last_action()
        else: 
            if self.can_undo_last_point_action(): self._clear_last_action() 
        return undone_successfully

    def _delete_point_for_undo(self, element_index: int, frame_index: int) -> bool:
        # ... (existing logic) ...
        track_data_list: ElementData = self.elements[element_index]['data']; point_idx = -1
        for i, p_data in enumerate(track_data_list):
            if p_data[0] == frame_index: point_idx = i; break
        if point_idx != -1:
            del track_data_list[point_idx]
            if element_index == self.active_element_index: self.activeElementDataChanged.emit()
            self.elementListChanged.emit()
            if self.elements[element_index]['visibility_mode'] != ElementVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
            return True
        return False

    def _restore_point_for_undo(self, element_index: int, frame_index: int, point_to_restore: PointData) -> bool:
        # ... (existing logic) ...
        track_data_list: ElementData = self.elements[element_index]['data']; point_idx = -1
        for i, p_data in enumerate(track_data_list):
            if p_data[0] == frame_index: point_idx = i; break
        if point_idx != -1:
            track_data_list[point_idx] = point_to_restore
            if element_index == self.active_element_index: self.activeElementDataChanged.emit()
            self.elementListChanged.emit()
            if self.elements[element_index]['visibility_mode'] != ElementVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
            return True
        logger.error(f"_restore_point_for_undo: Point not found at frame {frame_index} in element ID {self.elements[element_index]['id']}")
        return False

    def _add_point_for_undo(self, element_index: int, point_data_to_add: PointData) -> bool:
        # ... (existing logic) ...
        track_data_list: ElementData = self.elements[element_index]['data']
        for i, p_data in enumerate(track_data_list):
            if p_data[0] == point_data_to_add[0]: 
                logger.warning(f"_add_point_for_undo: Point for frame {point_data_to_add[0]} already exists in element ID {self.elements[element_index]['id']}. Overwriting for undo.")
                track_data_list[i] = point_data_to_add; track_data_list.sort(key=lambda p: p[0]); break
        else: track_data_list.append(point_data_to_add); track_data_list.sort(key=lambda p: p[0])
        if element_index == self.active_element_index: self.activeElementDataChanged.emit()
        self.elementListChanged.emit()
        if self.elements[element_index]['visibility_mode'] != ElementVisibilityMode.HIDDEN: self.visualsNeedUpdate.emit()
        return True

    def find_closest_visible_track_element_index(self, click_x: float, click_y: float, current_frame_index: int) -> int:
        # ... (existing logic) ...
        min_dist_sq = config.CLICK_TOLERANCE_SQ; closest_element_index = -1
        for i, element in enumerate(self.elements):
            if element['type'] != ElementType.TRACK: continue 
            vis_mode = element['visibility_mode']; track_data: ElementData = element['data']
            if vis_mode == ElementVisibilityMode.HIDDEN: continue
            for p_data in track_data:
                f_idx, _, px, py = p_data
                is_vis = (vis_mode == ElementVisibilityMode.ALWAYS_VISIBLE) or \
                         (vis_mode == ElementVisibilityMode.INCREMENTAL and f_idx <= current_frame_index) or \
                         (vis_mode == ElementVisibilityMode.HOME_FRAME and f_idx == current_frame_index)
                if is_vis: 
                    dist_sq = (click_x - px)**2 + (click_y - py)**2
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        closest_element_index = i
        return closest_element_index

    def _format_length_for_display(self, length_meters: float) -> str:
        """Formats a length in meters for display, using unit prefixes."""
        if length_meters == 0:
            return "0 m"
        if abs(length_meters) >= config.SCIENTIFIC_NOTATION_UPPER_THRESHOLD or \
           (abs(length_meters) > 0 and abs(length_meters) <= config.SCIENTIFIC_NOTATION_LOWER_THRESHOLD):
            return f"{length_meters:.2e}" # Scientific notation for very large/small
        
        for factor, singular_abbr, plural_abbr_or_none in config.UNIT_PREFIXES:
            if abs(length_meters) >= factor * 0.99: # Check if value is generally in this unit's range
                value_in_unit = length_meters / factor
                # Determine precision (simplified from ExportHandler for now)
                if factor >= 1.0:  # m, km
                    precision = 2 if abs(value_in_unit) < 10 else 1 if abs(value_in_unit) < 100 else 0
                elif factor >= 1e-3: # mm, cm
                    precision = 1 if abs(value_in_unit) < 100 else 0
                else: # µm, nm
                    precision = 0
                
                # Avoid decimal for larger whole numbers
                if precision > 0 and value_in_unit == math.floor(value_in_unit):
                    if abs(value_in_unit) >= 10 : precision = 0
                
                formatted_value = f"{value_in_unit:.{precision}f}"
                unit_to_display = plural_abbr_or_none if plural_abbr_or_none and abs(float(formatted_value)) != 1.0 else singular_abbr
                return f"{formatted_value} {unit_to_display}"
        
        return f"{length_meters:.3f} m" # Fallback

    def get_visual_elements(self, current_frame_index: int, scale_manager: Optional['ScaleManager'] = None) -> List[VisualElement]:
        visual_elements_list: List[VisualElement] = []
        if current_frame_index < 0: return visual_elements_list

        show_line_lengths = settings_manager.get_setting(settings_manager.KEY_SHOW_MEASUREMENT_LINE_LENGTHS)
        text_font_size = settings_manager.get_setting(settings_manager.KEY_MEASUREMENT_LINE_LENGTH_TEXT_FONT_SIZE)
        text_color = settings_manager.get_setting(settings_manager.KEY_MEASUREMENT_LINE_LENGTH_TEXT_COLOR)

        for i, element in enumerate(self.elements):
            element_id = element['id']
            element_type = element['type']
            element_data: ElementData = element['data']
            visibility_mode: ElementVisibilityMode = element['visibility_mode']
            is_active_element = (i == self.active_element_index)

            if visibility_mode == ElementVisibilityMode.HIDDEN:
                continue

            if element_type == ElementType.TRACK:
                # ... (existing track visual element generation) ...
                line_style = config.STYLE_LINE_ACTIVE if is_active_element else config.STYLE_LINE_INACTIVE
                previous_visible_point_coords: Optional[Tuple[float,float]] = None
                if visibility_mode == ElementVisibilityMode.HOME_FRAME:
                    for point_data_tuple in element_data:
                        frame_idx, _, point_x, point_y = point_data_tuple
                        if frame_idx == current_frame_index:
                            marker_style = config.STYLE_MARKER_ACTIVE_CURRENT if is_active_element else config.STYLE_MARKER_INACTIVE_CURRENT
                            visual_elements_list.append({'type': 'marker', 'pos': (point_x, point_y), 'style': marker_style, 'element_id': element_id, 'frame_idx': frame_idx})
                    continue 
                for point_data_tuple in element_data:
                    frame_idx, _, point_x, point_y = point_data_tuple
                    is_point_visible_now = (visibility_mode == ElementVisibilityMode.ALWAYS_VISIBLE) or \
                                           (visibility_mode == ElementVisibilityMode.INCREMENTAL and frame_idx <= current_frame_index)
                    if is_point_visible_now:
                        is_current_frame_marker = (frame_idx == current_frame_index)
                        marker_style = ""
                        if is_active_element:
                            marker_style = config.STYLE_MARKER_ACTIVE_CURRENT if is_current_frame_marker else config.STYLE_MARKER_ACTIVE_OTHER
                        else:
                            marker_style = config.STYLE_MARKER_INACTIVE_CURRENT if is_current_frame_marker else config.STYLE_MARKER_INACTIVE_OTHER
                        visual_elements_list.append({'type': 'marker', 'pos': (point_x, point_y), 'style': marker_style, 'element_id': element_id, 'frame_idx': frame_idx})
                        if previous_visible_point_coords:
                            visual_elements_list.append({'type': 'line', 'p1': previous_visible_point_coords, 'p2': (point_x, point_y), 'style': line_style, 'element_id': element_id})
                        previous_visible_point_coords = (point_x, point_y)
            
            elif element_type == ElementType.MEASUREMENT_LINE:
                if len(element_data) == 2: 
                    p1_data, p2_data = element_data[0], element_data[1]
                    line_definition_frame = p1_data[0] 
                    is_line_visible_on_current_frame = False
                    if visibility_mode == ElementVisibilityMode.ALWAYS_VISIBLE: is_line_visible_on_current_frame = True
                    elif visibility_mode == ElementVisibilityMode.INCREMENTAL and current_frame_index >= line_definition_frame: is_line_visible_on_current_frame = True
                    elif visibility_mode == ElementVisibilityMode.HOME_FRAME and current_frame_index == line_definition_frame: is_line_visible_on_current_frame = True
                    
                    if is_line_visible_on_current_frame:
                        style_key = config.STYLE_MEASUREMENT_LINE_ACTIVE if is_active_element else config.STYLE_MEASUREMENT_LINE_NORMAL
                        _f1, _t1, x1, y1 = p1_data
                        _f2, _t2, x2, y2 = p2_data
                        visual_elements_list.append({'type': 'line', 'p1': (x1, y1), 'p2': (x2, y2), 'style': style_key, 'element_id': element_id })
                        
                        if show_line_lengths:
                            dx_px = x2 - x1
                            dy_px = y2 - y1
                            pixel_length = math.sqrt(dx_px*dx_px + dy_px*dy_px)
                            length_text_str = ""

                            if scale_manager and scale_manager.get_scale_m_per_px():
                                m_per_px = scale_manager.get_scale_m_per_px()
                                real_world_length_m = pixel_length * m_per_px
                                length_text_str = self._format_length_for_display(real_world_length_m)
                            else:
                                length_text_str = f"{pixel_length:.1f} px"
                            
                            visual_elements_list.append({
                                'type': 'text',
                                'text': length_text_str,
                                'line_p1': (x1, y1), # Pass line endpoints for positioning utility
                                'line_p2': (x2, y2),
                                'font_size': text_font_size,
                                'color': text_color, # This should be QColor from settings_manager
                                'element_id': element_id,
                                'label_type': 'measurement_line_length' 
                            })
        return visual_elements_list

    def find_closest_visible_point(self, click_x: float, click_y: float, current_frame_index: int) -> Optional[Tuple[int, PointData]]:
        # ... (existing logic, no changes needed here for this phase) ...
        min_dist_sq = config.CLICK_TOLERANCE_SQ
        closest_element_idx = -1
        closest_point_data: Optional[PointData] = None
        for i, element in enumerate(self.elements):
            if element['type'] != ElementType.TRACK: continue 
            vis_mode = element['visibility_mode']; track_data: ElementData = element['data']
            if vis_mode == ElementVisibilityMode.HIDDEN: continue
            for p_data_tuple in track_data:
                f_idx, _, px, py = p_data_tuple
                is_vis_now = False
                if vis_mode == ElementVisibilityMode.ALWAYS_VISIBLE: is_vis_now = True
                elif vis_mode == ElementVisibilityMode.INCREMENTAL and f_idx <= current_frame_index: is_vis_now = True
                elif vis_mode == ElementVisibilityMode.HOME_FRAME and f_idx == current_frame_index: is_vis_now = True
                if is_vis_now:
                    dist_sq = (click_x - px)**2 + (click_y - py)**2
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq; closest_element_idx = i; closest_point_data = p_data_tuple
        if closest_element_idx != -1 and closest_point_data is not None:
            return (closest_element_idx, closest_point_data)
        return None

    def get_track_elements_summary(self) -> List[Tuple[int, int, int, int]]:
        # ... (existing logic) ...
        summary = []
        for i, element in enumerate(self.elements):
            if element['type'] == ElementType.TRACK:
                track_data: ElementData = element['data']
                num_points = len(track_data); start_frame, end_frame = (-1, -1)
                if num_points > 0: start_frame = track_data[0][0]; end_frame = track_data[-1][0]
                summary.append((element['id'], num_points, start_frame, end_frame))
        return summary

    def get_active_element_points_if_track(self) -> ElementData:
        # ... (existing logic) ...
        if self.active_element_index != -1:
            active_element = self.elements[self.active_element_index]
            if active_element['type'] == ElementType.TRACK: return list(active_element['data']) 
        return []


    def get_elements_by_type(self, element_type_filter: ElementType) -> List[Dict[str, Any]]:
        """
        Retrieves all elements of a specific type.

        Args:
            element_type_filter: The ElementType to filter by (e.g., ElementType.TRACK).

        Returns:
            A new list containing deep copies of element dictionaries that match
            the specified type. Returns an empty list if no elements match.
        """
        # Return deep copies to prevent accidental modification of internal element data
        # if the caller modifies the list or dictionaries within it.
        import copy # Ensure copy module is imported (usually at the top of the file)
        
        matching_elements: List[Dict[str, Any]] = []
        for el in self.elements:
            if el.get('type') == element_type_filter:
                matching_elements.append(copy.deepcopy(el))
        
        logger.debug(f"Retrieved {len(matching_elements)} elements of type {element_type_filter.name}")
        return matching_elements


    def get_all_elements_for_project_save(self) -> List[Dict[str, Any]]:
        """
        Prepares all elements for saving in the JSON project file format.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, where each dictionary
                                 represents an element structured for JSON serialization.
                                 Points are saved as raw Top-Left pixel coordinates.
        """
        elements_for_save: List[Dict[str, Any]] = []
        for element in self.elements:
            element_dict_for_save = {
                'id': element['id'],
                'type': element['type'].name,  # Store enum name as string [cite: 9]
                'name': element.get('name', f"{element['type'].name.title()} {element['id']}"), # Ensure name exists [cite: 9]
                'visibility_mode': element['visibility_mode'].name, # Store enum name as string [cite: 9]
                'data': []
            }
            
            # Structure point data as a list of dictionaries [cite: 10]
            point_list_for_save = []
            for point_tuple in element['data']:
                frame_idx, time_ms, x_tl_px, y_tl_px = point_tuple
                point_dict = {
                    'frame_index': frame_idx,
                    'time_ms': time_ms,
                    'x': x_tl_px, # Raw TL pixel coordinates [cite: 10]
                    'y': y_tl_px  # Raw TL pixel coordinates [cite: 10]
                }
                point_list_for_save.append(point_dict)
            
            element_dict_for_save['data'] = point_list_for_save
            elements_for_save.append(element_dict_for_save)
            
        logger.info(f"Prepared {len(elements_for_save)} elements for project saving.")
        return elements_for_save

# MODIFIED for Phase A: Renamed and restructured for JSON project loading
    def load_elements_from_project_data(self,
                                        elements_data_from_project: List[Dict[str, Any]],
                                        video_width: int, # Still needed for point validation
                                        video_height: int, # Still needed for point validation
                                        video_frame_count: int, # Still needed for point validation
                                        video_fps: float # Still needed for time consistency checks (optional)
                                       ) -> Tuple[bool, List[str]]:
        """
        Loads elements from a list of dictionaries (typically from a JSON project file).

        Args:
            elements_data_from_project: A list of dictionaries, where each dictionary
                                        represents an element.
            video_width: Width of the current video for validating point coordinates.
            video_height: Height of the current video for validating point coordinates.
            video_frame_count: Total frames in the current video for validation.
            video_fps: FPS of the current video for optional time consistency checks.

        Returns:
            Tuple[bool, List[str]]: A tuple containing a success boolean and a list
                                    of warning messages.
        """
        warnings: List[str] = []
        self.reset() # Clear existing elements before loading new ones
        
        max_loaded_id = 0
        loaded_elements_count = 0
        total_valid_points_loaded = 0
        total_skipped_points = 0

        time_tolerance_ms = (500 / video_fps) if video_fps > 0 else 50.0

        for element_dict in elements_data_from_project:
            element_id = element_dict.get('id')
            element_type_str = element_dict.get('type')
            element_name = element_dict.get('name')
            visibility_mode_str = element_dict.get('visibility_mode')
            points_list_of_dicts = element_dict.get('data', [])

            # --- Validation of basic element structure ---
            if element_id is None or not isinstance(element_id, int) or element_id <= 0:
                warnings.append(f"Skipping element due to missing or invalid ID: {element_dict.get('name', 'Unknown')}")
                logger.warning(f"Skipping element due to missing/invalid ID: {element_id}. Element dict: {element_dict}")
                continue
            if not element_type_str or not isinstance(element_type_str, str):
                warnings.append(f"Skipping element ID {element_id} ({element_name}) due to missing or invalid type string.")
                logger.warning(f"Skipping element ID {element_id} ({element_name}) due to missing or invalid type string: {element_type_str}")
                continue

            # --- Convert type string to ElementType enum ---
            try:
                element_type_enum = ElementType[element_type_str.upper()]
            except KeyError:
                warnings.append(f"Skipping element ID {element_id} ({element_name}) due to unrecognized type: '{element_type_str}'.")
                logger.warning(f"Unrecognized element type '{element_type_str}' for element ID {element_id}.")
                continue

            # --- Convert visibility mode string to Enum ---
            visibility_mode_enum = ElementVisibilityMode.INCREMENTAL # Default
            if visibility_mode_str and isinstance(visibility_mode_str, str):
                try:
                    visibility_mode_enum = ElementVisibilityMode[visibility_mode_str.upper()]
                except KeyError:
                    warnings.append(f"Element ID {element_id} ({element_name}) has unrecognized visibility mode '{visibility_mode_str}'. Using default INCREMENTAL.")
                    logger.warning(f"Unrecognized visibility mode '{visibility_mode_str}' for element ID {element_id}. Defaulting to INCREMENTAL.")
            
            internal_points_data: ElementData = []
            current_element_skipped_points = 0
            for point_dict in points_list_of_dicts:
                frame_idx = point_dict.get('frame_index')
                time_ms = point_dict.get('time_ms')
                x_tl_px = point_dict.get('x')
                y_tl_px = point_dict.get('y')

                point_description = f"Point in Element ID {element_id} (F{frame_idx})"
                is_valid_point = True

                if not all(isinstance(val, (int, float)) for val in [frame_idx, time_ms, x_tl_px, y_tl_px]):
                    warnings.append(f"{point_description}: Contains invalid or missing coordinate/frame/time data. Skipped.")
                    is_valid_point = False
                else: # Basic types are okay, now check values
                    frame_idx = int(frame_idx) # Ensure int
                    if not (0 <= frame_idx < video_frame_count):
                        warnings.append(f"{point_description}: Frame index ({frame_idx}) out of video range [0, {video_frame_count-1}]. Skipped.")
                        is_valid_point = False
                    if is_valid_point and not (0 <= x_tl_px < video_width): # Assuming TL origin, so coords >= 0
                        warnings.append(f"{point_description}: X-coordinate ({x_tl_px:.2f}) out of video width [0, {video_width-1}]. Skipped.")
                        is_valid_point = False
                    if is_valid_point and not (0 <= y_tl_px < video_height): # Assuming TL origin
                        warnings.append(f"{point_description}: Y-coordinate ({y_tl_px:.2f}) out of video height [0, {video_height-1}]. Skipped.")
                        is_valid_point = False
                    if is_valid_point and video_fps > 0: # Optional time consistency check
                        expected_time_ms = (frame_idx / video_fps) * 1000.0
                        if abs(time_ms - expected_time_ms) > time_tolerance_ms:
                            warnings.append(f"{point_description}: Time ({time_ms:.1f}ms) seems inconsistent with frame index and FPS (expected ~{expected_time_ms:.1f}ms). Using file time.")
                
                if is_valid_point:
                    internal_points_data.append((frame_idx, time_ms, x_tl_px, y_tl_px))
                else:
                    current_element_skipped_points += 1
                    logger.warning(warnings[-1]) # Log the last warning added

            if not internal_points_data and element_type_enum == ElementType.MEASUREMENT_LINE and len(points_list_of_dicts) != 2:
                # If it was supposed to be a line but its points were invalid, or it didn't have 2 points to begin with.
                warnings.append(f"Element ID {element_id} ({element_name}) of type {element_type_enum.name} loaded with no valid points. It will be empty.")
            elif not internal_points_data and element_type_enum == ElementType.TRACK and points_list_of_dicts:
                # If it was a track with points, but all were invalid
                 warnings.append(f"Element ID {element_id} ({element_name}) of type {element_type_enum.name} had all its points skipped due to validation errors. It will be empty.")


            # Sort points by frame index for internal consistency
            internal_points_data.sort(key=lambda p: p[0])

            # Specific validation for Measurement Lines (must have exactly 2 points on the same frame)
            if element_type_enum == ElementType.MEASUREMENT_LINE:
                if len(internal_points_data) != 2:
                    warnings.append(f"Element ID {element_id} ({element_name}): Measurement Line must have exactly 2 valid points. Found {len(internal_points_data)}. Skipping element.")
                    logger.warning(f"Measurement Line ID {element_id} skipped. Expected 2 valid points, found {len(internal_points_data)}.")
                    total_skipped_points += current_element_skipped_points
                    continue # Skip this element
                elif internal_points_data[0][0] != internal_points_data[1][0]: # Check if points are on the same frame
                    warnings.append(f"Element ID {element_id} ({element_name}): Measurement Line points must be on the same frame. Found frames {internal_points_data[0][0]} and {internal_points_data[1][0]}. Skipping element.")
                    logger.warning(f"Measurement Line ID {element_id} skipped. Points on different frames.")
                    total_skipped_points += current_element_skipped_points
                    continue # Skip this element

            new_internal_element = {
                'id': element_id,
                'type': element_type_enum,
                'name': element_name if element_name else f"{element_type_enum.name.title().replace('_',' ')} {element_id}",
                'data': internal_points_data,
                'visibility_mode': visibility_mode_enum
            }
            self.elements.append(new_internal_element)
            loaded_elements_count += 1
            total_valid_points_loaded += len(internal_points_data)
            total_skipped_points += current_element_skipped_points
            if element_id > max_loaded_id:
                max_loaded_id = element_id

        self._next_element_id = max_loaded_id + 1
        self.active_element_index = -1 # Deselect any active element
        
        logger.info(f"Load from project data: {loaded_elements_count} element(s) loaded. "
                    f"Total valid points: {total_valid_points_loaded}. Total skipped points: {total_skipped_points}.")
        
        self.elementListChanged.emit()
        self.activeElementDataChanged.emit()
        self.visualsNeedUpdate.emit()
        self._clear_last_action() # Loading new data clears undo history
        
        return True, warnings
