# table_controllers.py
"""
Contains controller classes for managing UI logic for data tables
(Tracks and Points tables) in the MainWindow.
"""
import logging
from typing import Optional, TYPE_CHECKING, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets

import config # For table column constants
# MODIFIED: Import ElementType as well
from element_manager import TrackVisibilityMode, ElementType, ElementData

if TYPE_CHECKING:
    # To avoid circular imports, only for type hinting
    from main_window import MainWindow # For QMessageBox parent and style access
    from element_manager import ElementManager
    from video_handler import VideoHandler
    from scale_manager import ScaleManager
    from coordinates import CoordinateTransformer


logger = logging.getLogger(__name__)

class TrackDataViewController(QtCore.QObject):
    """
    Manages UI logic for the Tracks table and Points table.
    """
    # Signals to MainWindow or other components
    seekVideoToFrame = QtCore.Signal(int)
    updateMainWindowUIState = QtCore.Signal() # To trigger MainWindow._update_ui_state
    statusBarMessage = QtCore.Signal(str, int) # message, timeout

    _lines_table: Optional[QtWidgets.QTableWidget] # Added for the new lines table

    def __init__(self,
                 main_window_ref: 'MainWindow', 
                 element_manager: 'ElementManager',
                 video_handler: 'VideoHandler',
                 scale_manager: 'ScaleManager',
                 coord_transformer: 'CoordinateTransformer',
                 tracks_table_widget: QtWidgets.QTableWidget,
                 points_table_widget: QtWidgets.QTableWidget,
                 points_tab_label: QtWidgets.QLabel,
                 parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)

        self._main_window_ref = main_window_ref 
        self._element_manager = element_manager
        self._video_handler = video_handler
        self._scale_manager = scale_manager
        self._coord_transformer = coord_transformer
        self._tracks_table = tracks_table_widget
        self._points_table = points_table_widget
        self._points_tab_label = points_tab_label
        
        # --- NEW: Initialize linesTableWidget ---
        # It's expected that main_window_ref will have this attribute set up by ui_setup.py
        if hasattr(main_window_ref, 'linesTableWidget') and isinstance(main_window_ref.linesTableWidget, QtWidgets.QTableWidget):
            self._lines_table = main_window_ref.linesTableWidget
        else:
            self._lines_table = None
            logger.error("TrackDataViewController: linesTableWidget not found or not a QTableWidget on MainWindow.")
        # --- END NEW ---

        self._element_visibility_button_groups: Dict[int, QtWidgets.QButtonGroup] = {}
        self._video_loaded: bool = False 
        self._total_frames_for_validation: int = 0


        self._tracks_table.itemSelectionChanged.connect(self._on_track_selection_changed_in_table)
        self._tracks_table.cellClicked.connect(self._on_tracks_table_cell_clicked)
        
        self._points_table.cellClicked.connect(self._on_points_table_cell_clicked)

        self._element_manager.elementListChanged.connect(self.update_tracks_table_ui)
        # --- NEW: Connect elementListChanged to update_lines_table_ui ---
        if self._lines_table: # Only connect if the table exists
            self._element_manager.elementListChanged.connect(self.update_lines_table_ui)
        # --- END NEW ---
        self._element_manager.activeElementDataChanged.connect(self.update_points_table_ui)
        self._element_manager.activeElementDataChanged.connect(self._sync_tracks_table_selection_with_manager) 
        
        self._scale_manager.scaleOrUnitChanged.connect(self.update_points_table_ui)
        
    def set_video_loaded_status(self, is_loaded: bool, total_frames: int = 0) -> None:
        if self._video_loaded != is_loaded: 
            self._video_loaded = is_loaded
            self._total_frames_for_validation = total_frames if is_loaded else 0
            
            logger.debug(f"TrackDataViewController: video_loaded status changed to {is_loaded}. Updating tables.")
            self.update_tracks_table_ui()
            # --- NEW: Update lines table on video load status change ---
            if self._lines_table:
                self.update_lines_table_ui()
            # --- END NEW ---
            self.update_points_table_ui()
        elif is_loaded and self._total_frames_for_validation != total_frames:
            self._total_frames_for_validation = total_frames
            logger.debug(f"TrackDataViewController: video_loaded status same, but total_frames changed. Updating tables.")
            self.update_tracks_table_ui()
            # --- NEW: Update lines table on total_frames change (if video loaded) ---
            if self._lines_table:
                self.update_lines_table_ui()
            # --- END NEW ---
            self.update_points_table_ui()

    def handle_visibility_header_clicked(self, logical_index: int) -> None:
        if not self._element_manager.elements: return

        target_mode: Optional[TrackVisibilityMode] = None
        if logical_index == config.COL_VIS_HIDDEN: target_mode = TrackVisibilityMode.HIDDEN
        elif logical_index == config.COL_VIS_INCREMENTAL: target_mode = TrackVisibilityMode.INCREMENTAL
        elif logical_index == config.COL_VIS_ALWAYS: target_mode = TrackVisibilityMode.ALWAYS_VISIBLE

        if target_mode:
            # Determine which table's header was clicked based on the column index range
            # This is a bit heuristic; ideally, we'd get the sender table directly.
            # For now, assume tracks table if within its column range.
            # Line table specific header clicks will need separate handling or more specific signals.
            if config.COL_VIS_HIDDEN <= logical_index <= config.COL_VIS_ALWAYS : # Tracks table specific columns
                 logger.info(f"Controller: Setting all track-type elements visibility to {target_mode.name} via header click.")
                 self._element_manager.set_all_elements_visibility(target_mode, ElementType.TRACK)
            # Add similar logic for Lines table header clicks in the future if visibility applies similarly

    @QtCore.Slot()
    def _on_track_selection_changed_in_table(self) -> None:
        selected_items = self._tracks_table.selectedItems()
        if not selected_items:
            return

        selected_row = self._tracks_table.row(selected_items[0])
        id_item = self._tracks_table.item(selected_row, config.COL_TRACK_ID)
        if id_item:
            element_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole) 
            if element_id is not None and isinstance(element_id, int):
                element_index_in_manager = -1
                for idx, el in enumerate(self._element_manager.elements):
                    if el['id'] == element_id and el['type'] == ElementType.TRACK: # Ensure it's a track
                        element_index_in_manager = idx
                        break
                
                if element_index_in_manager != -1:
                    if self._element_manager.active_element_index != element_index_in_manager:
                        logger.debug(f"Controller: Tracks table selection changed to row {selected_row}, element ID {element_id}. Setting active element.")
                        self._element_manager.set_active_element(element_index_in_manager)
                else:
                    logger.warning(f"Could not find TRACK element with ID {element_id} in ElementManager from table selection.")


    @QtCore.Slot(int, int)
    def _on_tracks_table_cell_clicked(self, row: int, column: int) -> None:
        if not self._video_loaded:
            return

        id_item = self._tracks_table.item(row, config.COL_TRACK_ID)
        if not id_item:
            logger.debug("TableController: Cell click on non-data row or invalid ID item in tracks table.")
            return

        element_id_clicked = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(element_id_clicked, int):
            logger.warning(f"TableController: Invalid element_id data in tracks table: {element_id_clicked}")
            return

        element_index_clicked = -1
        for idx, el in enumerate(self._element_manager.elements):
            if el['id'] == element_id_clicked and el['type'] == ElementType.TRACK: # Ensure it's a track
                element_index_clicked = idx
                break
        
        if element_index_clicked == -1:
            logger.warning(f"TableController: Clicked TRACK element ID {element_id_clicked} not found in manager.")
            return

        current_modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_ctrl_click = (current_modifiers == QtCore.Qt.KeyboardModifier.ControlModifier)
        is_active_element_in_manager = (element_index_clicked == self._element_manager.active_element_index)

        if is_ctrl_click:
            if is_active_element_in_manager:
                logger.info(f"TableController: Ctrl+Clicked on active TRACK element {element_id_clicked}. Deselecting.")
                self._element_manager.set_active_element(-1)
                return 
            else:
                logger.info(f"TableController: Ctrl+Clicked on non-active TRACK element {element_id_clicked}. Selecting.")
                if self._element_manager.active_element_index != element_index_clicked:
                    self._element_manager.set_active_element(element_index_clicked)
                return 
        
        if column == config.COL_TRACK_START_FRAME or column == config.COL_TRACK_END_FRAME:
            frame_item_widget = self._tracks_table.item(row, column)
            if frame_item_widget:
                frame_text = frame_item_widget.text()
                try:
                    target_frame_0based = int(frame_text) - 1
                    if 0 <= target_frame_0based < self._total_frames_for_validation:
                        logger.debug(f"TableController: Frame link clicked for TRACK element {element_id_clicked}. Emitting seekVideoToFrame({target_frame_0based})")
                        self.seekVideoToFrame.emit(target_frame_0based)
                except (ValueError, TypeError):
                    logger.warning(f"TableController: Could not parse frame number: '{frame_text}'")
        
        logger.debug(f"TableController: Normal cell ({row},{column}) click on TRACK element {element_id_clicked}.")


    @QtCore.Slot()
    def _sync_tracks_table_selection_with_manager(self) -> None:
        if not hasattr(self, '_element_manager') or not hasattr(self, '_tracks_table'):
            logger.warning("TrackDataViewController: Cannot sync tracks table selection, manager or table missing.")
            return

        active_id = self._element_manager.get_active_element_id() 
        active_type = self._element_manager.get_active_element_type()
        
        logger.debug(f"TrackDataViewController: Syncing tracks table selection to manager's active ID: {active_id}, Type: {active_type}")
        # Only select in tracks table if the active element is a TRACK
        if active_type == ElementType.TRACK:
            self._select_element_row_by_id_in_ui(active_id)
        else: # If active element is not a track (e.g., a line or none), clear tracks table selection
            self._tracks_table.clearSelection()
            logger.debug(f"Active element is not a TRACK (or none active), cleared tracks table selection.")


    @QtCore.Slot(int, int)
    def _on_points_table_cell_clicked(self, row: int, column: int) -> None:
        if not self._video_loaded: return

        if column == config.COL_POINT_FRAME:
            item = self._points_table.item(row, column)
            if item:
                try:
                    target_frame_0based = int(item.text()) - 1
                    if 0 <= target_frame_0based < self._total_frames_for_validation:
                        logger.debug(f"Controller: Points table frame link clicked. Emitting seekVideoToFrame({target_frame_0based})")
                        self.seekVideoToFrame.emit(target_frame_0based)
                        self._points_table.selectRow(row)
                except ValueError:
                    pass

    @QtCore.Slot(int) 
    def _on_delete_element_button_clicked_in_table(self, element_index: int) -> None:
        if not (0 <= element_index < len(self._element_manager.elements)):
            logger.error(f"Delete button clicked for invalid element index: {element_index}")
            return

        element_to_delete = self._element_manager.elements[element_index]
        element_id = element_to_delete['id']
        element_type_name = element_to_delete['type'].name.replace("_", " ").title() 

        reply = QtWidgets.QMessageBox.question(self._main_window_ref, f"Confirm Delete {element_type_name}", 
                                             f"Delete {element_type_name} {element_id}?",
                                             QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
                                             QtWidgets.QMessageBox.StandardButton.Cancel)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            logger.info(f"Controller: User confirmed deletion for element index {element_index} (ID: {element_id}).")
            success = self._element_manager.delete_element_by_index(element_index)
            msg = f"Deleted {element_type_name} {element_id}" if success else f"Failed to delete {element_type_name} {element_id}"
            self.statusBarMessage.emit(msg, 3000)
            if not success:
                logger.error(f"Controller: ElementManager failed to delete element index {element_index}.")
                QtWidgets.QMessageBox.warning(self._main_window_ref, "Delete Error", f"Could not delete {element_type_name} {element_id}.")
            self.updateMainWindowUIState.emit()


    @QtCore.Slot(QtWidgets.QAbstractButton, bool)
    def _on_visibility_changed_in_table(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        if checked:
            mode = button.property("visibility_mode")
            element_index = button.property("element_index") 
            if isinstance(mode, TrackVisibilityMode) and isinstance(element_index, int):
                logger.debug(f"Controller: Visibility changed for element index {element_index} to {mode.name}")
                self._element_manager.set_element_visibility_mode(element_index, mode)


    def _clear_internal_visibility_button_groups(self) -> None:
        for group in self._element_visibility_button_groups.values():
            try:
                group.buttonToggled.disconnect(self._on_visibility_changed_in_table)
            except (TypeError, RuntimeError): pass 
        self._element_visibility_button_groups.clear()

    def _select_element_row_by_id_in_ui(self, element_id_to_select: int) -> None:
         # This method is currently tailored for the _tracks_table.
         # If lines table selection needs similar sync, a more generic approach or separate method might be needed.
         target_table = self._tracks_table # Assume tracks table for now
         id_column_index = config.COL_TRACK_ID # Assume ID column for tracks

         if element_id_to_select == -1:
              target_table.clearSelection()
              return
         found_row = -1
         num_data_rows = target_table.rowCount()
         # Adjust for button row if it's the tracks table
         if target_table is self._tracks_table:
             num_data_rows -=1 

         for row_idx in range(num_data_rows):
              item = target_table.item(row_idx, id_column_index)
              if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == element_id_to_select:
                  found_row = row_idx
                  break
         if found_row != -1:
             target_table.blockSignals(True)
             target_table.selectRow(found_row)
             target_table.blockSignals(False)
             if item: target_table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
         else:
             target_table.clearSelection() 
             logger.debug(f"Controller: Could not find row for element ID {element_id_to_select} in the current table context.")


    def _create_centered_cell_widget_for_table(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        cell_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(cell_widget)
        layout.addWidget(widget)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        return cell_widget

    @QtCore.Slot()
    def update_tracks_table_ui(self) -> None:
        logger.debug("TrackDataViewController: Updating tracks table UI (now element-aware)...")
        current_active_element_id = self._element_manager.get_active_element_id()
        current_active_type = self._element_manager.get_active_element_type()
        selected_row_to_restore = -1

        previous_track_count = 0
        for r in range(self._tracks_table.rowCount() -1): 
            id_item = self._tracks_table.item(r, config.COL_TRACK_ID)
            if id_item and id_item.data(QtCore.Qt.ItemDataRole.UserRole) is not None:
                previous_track_count +=1


        self._tracks_table.blockSignals(True)
        # Clear only track-related button groups. If lines have separate groups, they'd be managed separately.
        # For now, this clears all, which is fine as lines table doesn't use this dict yet.
        self._clear_internal_visibility_button_groups() 

        track_summary_list = self._element_manager.get_track_elements_summary()
        num_data_rows = len(track_summary_list)
        total_rows = num_data_rows + 1 
        self._tracks_table.setRowCount(total_rows)

        link_color = QtGui.QColor("blue")
        link_tooltip = "Click to jump to this frame"
        style = self._main_window_ref.style() 

        for row_idx in range(num_data_rows):
            self._tracks_table.setSpan(row_idx, 0, 1, 1) 
            
            element_id, num_points, start_frame, end_frame = track_summary_list[row_idx]
            
            element_index_in_manager = -1
            for idx, el_dict in enumerate(self._element_manager.elements):
                if el_dict['id'] == element_id and el_dict['type'] == ElementType.TRACK:
                    element_index_in_manager = idx
                    break
            
            if element_index_in_manager == -1: 
                logger.error(f"Could not find element ID {element_id} in ElementManager during table update.")
                continue

            delete_button = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon), "")
            delete_button.setToolTip(f"Delete Track {element_id}"); delete_button.setFlat(True); delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            delete_button.setProperty("element_index", element_index_in_manager) 
            delete_button.clicked.connect(lambda checked=False, el_idx=element_index_in_manager: self._on_delete_element_button_clicked_in_table(el_idx))
            self._tracks_table.setCellWidget(row_idx, config.COL_DELETE, self._create_centered_cell_widget_for_table(delete_button))

            id_item = QtWidgets.QTableWidgetItem(str(element_id))
            id_item.setData(QtCore.Qt.ItemDataRole.UserRole, element_id) 
            id_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._tracks_table.setItem(row_idx, config.COL_TRACK_ID, id_item)

            for col, val, is_link in [
                (config.COL_TRACK_POINTS, str(num_points), False),
                (config.COL_TRACK_START_FRAME, str(start_frame + 1) if start_frame != -1 else "N/A", start_frame != -1),
                (config.COL_TRACK_END_FRAME, str(end_frame + 1) if end_frame != -1 else "N/A", end_frame != -1)
            ]:
                item = QtWidgets.QTableWidgetItem(val)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if is_link: item.setForeground(link_color); item.setToolTip(link_tooltip)
                self._tracks_table.setItem(row_idx, col, item)

            current_mode = self._element_manager.get_element_visibility_mode(element_index_in_manager)
            rb_hidden = QtWidgets.QRadioButton(); rb_incremental = QtWidgets.QRadioButton(); rb_always = QtWidgets.QRadioButton()
            
            rb_hidden.setProperty("visibility_mode", TrackVisibilityMode.HIDDEN); rb_hidden.setProperty("element_index", element_index_in_manager)
            rb_incremental.setProperty("visibility_mode", TrackVisibilityMode.INCREMENTAL); rb_incremental.setProperty("element_index", element_index_in_manager)
            rb_always.setProperty("visibility_mode", TrackVisibilityMode.ALWAYS_VISIBLE); rb_always.setProperty("element_index", element_index_in_manager)
            
            button_group = QtWidgets.QButtonGroup(self) 
            button_group.addButton(rb_hidden); button_group.addButton(rb_incremental); button_group.addButton(rb_always)
            button_group.setExclusive(True)
            self._element_visibility_button_groups[element_id] = button_group 
            
            button_group.blockSignals(True)
            if current_mode == TrackVisibilityMode.HIDDEN: rb_hidden.setChecked(True)
            elif current_mode == TrackVisibilityMode.INCREMENTAL: rb_incremental.setChecked(True)
            else: rb_always.setChecked(True) 
            button_group.blockSignals(False)
            
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_HIDDEN, self._create_centered_cell_widget_for_table(rb_hidden))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_INCREMENTAL, self._create_centered_cell_widget_for_table(rb_incremental))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_ALWAYS, self._create_centered_cell_widget_for_table(rb_always))
            button_group.buttonToggled.connect(self._on_visibility_changed_in_table)

            if element_id == current_active_element_id and current_active_type == ElementType.TRACK:
                selected_row_to_restore = row_idx

        button_row_index = num_data_rows 
        new_track_button_in_table = QtWidgets.QPushButton("New Track")
        new_track_button_in_table.setToolTip("Start a new track for marking points (Ctrl+N)")
        new_track_button_in_table.clicked.connect(self._main_window_ref._create_new_track) 
        new_track_button_in_table.setEnabled(self._video_loaded)
        self._tracks_table.setCellWidget(button_row_index, 0, new_track_button_in_table)
        self._tracks_table.setSpan(button_row_index, 0, 1, config.TOTAL_TRACK_COLUMNS)
        self._tracks_table.setRowHeight(button_row_index, new_track_button_in_table.sizeHint().height() + 4)


        if selected_row_to_restore != -1:
            self._tracks_table.selectRow(selected_row_to_restore)
        else: 
            self._tracks_table.clearSelection()

        self._tracks_table.blockSignals(False)

        if num_data_rows != previous_track_count:
            logger.debug("Track count changed, emitting updateMainWindowUIState.")
            self.updateMainWindowUIState.emit()

    @QtCore.Slot()
    def update_lines_table_ui(self) -> None:
        if not self._lines_table:
            logger.debug("TrackDataViewController: Skipping update_lines_table_ui, table not initialized.")
            return
        
        logger.debug("TrackDataViewController: Updating lines table UI...")
        self._lines_table.setRowCount(0) # Clear existing rows

        if not self._video_loaded: # If no video, ensure table is empty
            logger.debug("TrackDataViewController: No video loaded, lines table remains empty.")
            return
        
        line_elements_to_display = []
        for el_idx, el in enumerate(self._element_manager.elements): # Iterate with index
            if el['type'] == ElementType.MEASUREMENT_LINE:
                line_elements_to_display.append({'element': el, 'manager_index': el_idx}) # Store element and its index
        
        self._lines_table.setRowCount(len(line_elements_to_display))
        
        # Placeholder column indices (should ideally come from config.py later)
        # These are conceptual for now, matching ui_setup.py's initial setup.
        # COL_LINE_DELETE = 0 (Conceptual)
        COL_LINE_ID = 1       # As per ui_setup.py for linesTableWidget
        COL_LINE_FRAME = 2    # As per ui_setup.py for linesTableWidget
        # COL_LINE_LENGTH = 3 (Future)
        # COL_LINE_ANGLE = 4  (Future)
        # COL_LINE_VIS_HIDDEN = 5 (Future)
        # ... and so on for other visibility controls

        for row_idx, line_info in enumerate(line_elements_to_display):
            line_element = line_info['element']
            # manager_idx = line_info['manager_index'] # Available if needed for delete/visibility later

            element_id = line_element['id']
            element_data: ElementData = line_element['data'] # Type hint for clarity

            # ID item
            id_item = QtWidgets.QTableWidgetItem(str(element_id))
            id_item.setData(QtCore.Qt.ItemDataRole.UserRole, element_id)
            id_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._lines_table.setItem(row_idx, COL_LINE_ID, id_item)

            # Frame item - Populated if the line is defined (has 2 points)
            frame_str = "Defining..." # Default if still being defined
            if len(element_data) == 2: # Line is fully defined with two points
                # Both points of a line are on the same frame.
                frame_index_of_line = element_data[0][0] # Get frame from first point
                frame_str = str(frame_index_of_line + 1) # Display 1-based
            elif self._element_manager._is_defining_element_type == ElementType.MEASUREMENT_LINE and \
                 self._element_manager.active_element_index != -1 and \
                 self._element_manager.elements[self._element_manager.active_element_index]['id'] == element_id:
                # If this line is currently active and being defined
                if self._element_manager._defining_element_frame_index is not None:
                    frame_str = f"{self._element_manager._defining_element_frame_index + 1} (Pending)"
            
            frame_item = QtWidgets.QTableWidgetItem(frame_str) 
            frame_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            frame_item.setFlags(frame_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            # If frame_str is a number (line defined), make it a link
            if frame_str.isdigit():
                frame_item.setForeground(QtGui.QColor("blue"))
                frame_item.setToolTip("Click to jump to this frame")
            self._lines_table.setItem(row_idx, COL_LINE_FRAME, frame_item)
            
            # Future: Populate Length, Angle, Delete Button, Visibility Radios
            # For Length/Angle:
            # if len(element_data) == 2:
            #    p1_x, p1_y = element_data[0][2], element_data[0][3]
            #    p2_x, p2_y = element_data[1][2], element_data[1][3]
            #    # Calculate length (using scale_manager) and angle
            #    # Format and set table items
            # else:
            #    # Set N/A or empty for length/angle

        # Configure column resize modes (can be done once in __init__ or here if columns might change)
        if self._lines_table.columnCount() > 0:
            header = self._lines_table.horizontalHeader()
            # Example: if col 0 is delete, 1 is ID, 2 is Frame
            # if self._lines_table.columnCount() > 0: header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # Delete
            if self._lines_table.columnCount() > COL_LINE_ID: header.setSectionResizeMode(COL_LINE_ID, QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # ID
            if self._lines_table.columnCount() > COL_LINE_FRAME: header.setSectionResizeMode(COL_LINE_FRAME, QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # Frame
            # for other columns (Length, Angle, Visibility), set as Stretch or ResizeToContents as needed
            # e.g., header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch) # Length

        logger.debug(f"TrackDataViewController: Lines table UI updated with {len(line_elements_to_display)} lines.")

    @QtCore.Slot()
    def update_points_table_ui(self) -> None:
        logger.debug("TrackDataViewController: Updating points table UI (now element-aware)...")
        active_element_id = self._element_manager.get_active_element_id()
        active_element_type = self._element_manager.get_active_element_type()

        # Display points only if the active element is a TRACK
        if active_element_type == ElementType.TRACK and active_element_id != -1:
            self._points_tab_label.setText(f"Points for Track: {active_element_id}")
            active_points = self._element_manager.get_active_element_points_if_track()
        # --- NEW: Display points if active element is a MEASUREMENT_LINE ---
        elif active_element_type == ElementType.MEASUREMENT_LINE and active_element_id != -1:
            self._points_tab_label.setText(f"Endpoints for Line: {active_element_id}")
            # In Phase 2, line data will be empty. Phase 3 will populate this.
            active_points = self._element_manager.elements[self._element_manager.active_element_index]['data'] 
        # --- END NEW ---
        else:
            self._points_tab_label.setText("Points: - (No compatible element selected)")
            active_points = [] 

        self._points_table.setRowCount(0) 

        link_color = QtGui.QColor("blue")
        link_tooltip = "Click to jump to this frame"
        display_unit_short = self._scale_manager.get_display_unit_short()
        x_header_text = f"X [{display_unit_short}]"
        y_header_text = f"Y [{display_unit_short}]"

        pointsHeader = self._points_table.horizontalHeader()
        pointsHeader.model().setHeaderData(config.COL_POINT_X, QtCore.Qt.Orientation.Horizontal, x_header_text)
        pointsHeader.model().setHeaderData(config.COL_POINT_Y, QtCore.Qt.Orientation.Horizontal, y_header_text)

        self._points_table.setRowCount(len(active_points))
        for row_idx, point_data in enumerate(active_points):
            frame_idx, time_ms, x_internal_px, y_internal_px = point_data

            frame_item = QtWidgets.QTableWidgetItem(str(frame_idx + 1)) 
            frame_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            frame_item.setForeground(link_color); frame_item.setToolTip(link_tooltip)
            frame_item.setFlags(frame_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._points_table.setItem(row_idx, config.COL_POINT_FRAME, frame_item)

            time_sec_str = f"{(time_ms / 1000.0):.3f}" if time_ms >= 0 else "--.---"
            time_item = QtWidgets.QTableWidgetItem(time_sec_str)
            time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            time_item.setFlags(time_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._points_table.setItem(row_idx, config.COL_POINT_TIME, time_item)

            x_coord_sys_px, y_coord_sys_px = self._coord_transformer.transform_point_for_display(x_internal_px, y_internal_px)
            x_display, y_display, _ = self._scale_manager.get_transformed_coordinates_for_display(x_coord_sys_px, y_coord_sys_px)

            for col, val_str in [(config.COL_POINT_X, f"{x_display}"), (config.COL_POINT_Y, f"{y_display}")]:
                item = QtWidgets.QTableWidgetItem(val_str)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self._points_table.setItem(row_idx, col, item)