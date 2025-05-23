# table_controllers.py
"""
Contains controller classes for managing UI logic for data tables
(Tracks and Points tables) in the MainWindow.
"""
import logging
from typing import Optional, TYPE_CHECKING, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets

import config # For table column constants
# MODIFIED: Import ElementVisibilityMode instead of TrackVisibilityMode
from element_manager import ElementVisibilityMode, ElementType, ElementData

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
        
        if hasattr(main_window_ref, 'linesTableWidget') and isinstance(main_window_ref.linesTableWidget, QtWidgets.QTableWidget):
            self._lines_table = main_window_ref.linesTableWidget
            # Connect header click for lines table if it exists
            if hasattr(self._lines_table, 'horizontalHeader') and hasattr(self._lines_table.horizontalHeader(), 'sectionClicked'):
                 self._lines_table.horizontalHeader().sectionClicked.connect(
                     lambda logical_index: self.handle_visibility_header_clicked(logical_index, ElementType.MEASUREMENT_LINE)
                 )
        else:
            self._lines_table = None
            logger.error("TrackDataViewController: linesTableWidget not found or not a QTableWidget on MainWindow.")

        self._element_visibility_button_groups: Dict[int, QtWidgets.QButtonGroup] = {} # Key is element_id
        self._video_loaded: bool = False
        self._total_frames_for_validation: int = 0


        self._tracks_table.itemSelectionChanged.connect(self._on_track_selection_changed_in_table)
        self._tracks_table.cellClicked.connect(self._on_tracks_table_cell_clicked)
        if hasattr(self._tracks_table, 'horizontalHeader') and hasattr(self._tracks_table.horizontalHeader(), 'sectionClicked'):
            self._tracks_table.horizontalHeader().sectionClicked.connect(
                lambda logical_index: self.handle_visibility_header_clicked(logical_index, ElementType.TRACK)
            )
        
        self._points_table.cellClicked.connect(self._on_points_table_cell_clicked)

        self._element_manager.elementListChanged.connect(self.update_tracks_table_ui)
        if self._lines_table: 
            self._element_manager.elementListChanged.connect(self.update_lines_table_ui)
        self._element_manager.activeElementDataChanged.connect(self.update_points_table_ui)
        self._element_manager.activeElementDataChanged.connect(self._sync_active_element_selection_in_tables)
        
        self._scale_manager.scaleOrUnitChanged.connect(self.update_points_table_ui)
        
    def set_video_loaded_status(self, is_loaded: bool, total_frames: int = 0) -> None:
        if self._video_loaded != is_loaded:
            self._video_loaded = is_loaded
            self._total_frames_for_validation = total_frames if is_loaded else 0
            
            logger.debug(f"TrackDataViewController: video_loaded status changed to {is_loaded}. Updating tables.")
            self.update_tracks_table_ui()
            if self._lines_table:
                self.update_lines_table_ui()
            self.update_points_table_ui()
        elif is_loaded and self._total_frames_for_validation != total_frames:
            self._total_frames_for_validation = total_frames
            logger.debug(f"TrackDataViewController: video_loaded status same, but total_frames changed. Updating tables.")
            self.update_tracks_table_ui()
            if self._lines_table:
                self.update_lines_table_ui()
            self.update_points_table_ui()

    def handle_visibility_header_clicked(self, logical_index: int, element_type_to_filter: ElementType) -> None:
        if not self._element_manager.elements: return

        target_mode: Optional[ElementVisibilityMode] = None
        
        # Determine target mode based on which visibility column was clicked
        # These column indices are now generic for Tracks and Lines tables
        if element_type_to_filter == ElementType.TRACK:
            if logical_index == config.COL_VIS_HIDDEN: target_mode = ElementVisibilityMode.HIDDEN
            elif logical_index == config.COL_VIS_HOME_FRAME: target_mode = ElementVisibilityMode.HOME_FRAME
            elif logical_index == config.COL_VIS_INCREMENTAL: target_mode = ElementVisibilityMode.INCREMENTAL
            elif logical_index == config.COL_VIS_ALWAYS: target_mode = ElementVisibilityMode.ALWAYS_VISIBLE
        elif element_type_to_filter == ElementType.MEASUREMENT_LINE:
            if logical_index == config.COL_LINE_VIS_HIDDEN: target_mode = ElementVisibilityMode.HIDDEN
            elif logical_index == config.COL_LINE_VIS_HOME_FRAME: target_mode = ElementVisibilityMode.HOME_FRAME
            elif logical_index == config.COL_LINE_VIS_INCREMENTAL: target_mode = ElementVisibilityMode.INCREMENTAL
            elif logical_index == config.COL_LINE_VIS_ALWAYS: target_mode = ElementVisibilityMode.ALWAYS_VISIBLE

        if target_mode:
            logger.info(f"Controller: Setting all {element_type_to_filter.name} elements visibility to {target_mode.name} via header click.")
            self._element_manager.set_all_elements_visibility(target_mode, element_type_to_filter)

    @QtCore.Slot()
    def _on_track_selection_changed_in_table(self) -> None: # This specifically handles TRACKS table selection
        selected_items = self._tracks_table.selectedItems()
        if not selected_items:
            return

        selected_row = self._tracks_table.row(selected_items[0])
        if selected_row < 0 or selected_row >= self._tracks_table.rowCount():
            logger.debug(f"TrackDataViewController: Invalid selected_row {selected_row} in _on_track_selection_changed_in_table. Ignoring.")
            return
            
        id_item = self._tracks_table.item(selected_row, config.COL_TRACK_ID)
        if id_item:
            element_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if element_id is not None and isinstance(element_id, int):
                element_index_in_manager = -1
                for idx, el in enumerate(self._element_manager.elements):
                    # Ensure we are selecting a TRACK type element
                    if el['id'] == element_id and el['type'] == ElementType.TRACK: 
                        element_index_in_manager = idx
                        break
                
                if element_index_in_manager != -1:
                    if self._element_manager.active_element_index != element_index_in_manager:
                        logger.debug(f"Controller: Tracks table selection changed to row {selected_row}, element ID {element_id}. Setting active element.")
                        self._element_manager.set_active_element(element_index_in_manager)
                else:
                    logger.warning(f"Could not find TRACK element with ID {element_id} in ElementManager from table selection.")

    # You will need a similar `_on_line_selection_changed_in_table` if you connect itemSelectionChanged for _lines_table
    # For now, let's assume line selection might be handled by cellClicked or directly by main_window if needed.

    @QtCore.Slot(int, int)
    def _on_tracks_table_cell_clicked(self, row: int, column: int) -> None:
        if not self._video_loaded: return
        if row < 0 or row >= self._tracks_table.rowCount():
             logger.debug(f"TrackDataViewController: Cell click on invalid row {row} in tracks table. Ignoring.")
             return

        id_item = self._tracks_table.item(row, config.COL_TRACK_ID)
        if not id_item:
            logger.debug("TrackDataViewController: Cell click on non-data row or invalid ID item in tracks table.")
            return

        element_id_clicked = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(element_id_clicked, int):
            logger.warning(f"TrackDataViewController: Invalid element_id data in tracks table: {element_id_clicked}")
            return

        element_index_clicked = -1
        for idx, el in enumerate(self._element_manager.elements):
            if el['id'] == element_id_clicked and el['type'] == ElementType.TRACK: 
                element_index_clicked = idx
                break
        
        if element_index_clicked == -1:
            logger.warning(f"TrackDataViewController: Clicked TRACK element ID {element_id_clicked} not found in manager.")
            return

        current_modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_ctrl_click = (current_modifiers == QtCore.Qt.KeyboardModifier.ControlModifier)
        is_active_element_in_manager = (element_index_clicked == self._element_manager.active_element_index)

        if is_ctrl_click: # Ctrl+Click to select/deselect
            if is_active_element_in_manager and self._element_manager.get_active_element_type() == ElementType.TRACK:
                logger.info(f"TrackDataViewController: Ctrl+Clicked on active TRACK element {element_id_clicked}. Deselecting.")
                self._element_manager.set_active_element(-1)
            else: # Select if not active or active but different type
                logger.info(f"TrackDataViewController: Ctrl+Clicked on TRACK element {element_id_clicked}. Selecting.")
                if self._element_manager.active_element_index != element_index_clicked:
                    self._element_manager.set_active_element(element_index_clicked)
            return 
        
        # Normal click for seeking frame (if on Start/End Frame columns)
        if column == config.COL_TRACK_START_FRAME or column == config.COL_TRACK_END_FRAME:
            frame_item_widget = self._tracks_table.item(row, column)
            if frame_item_widget:
                frame_text = frame_item_widget.text()
                try:
                    target_frame_0based = int(frame_text) - 1
                    if 0 <= target_frame_0based < self._total_frames_for_validation:
                        logger.debug(f"TrackDataViewController: Frame link clicked for TRACK element {element_id_clicked}. Emitting seekVideoToFrame({target_frame_0based})")
                        self.seekVideoToFrame.emit(target_frame_0based)
                except (ValueError, TypeError):
                    logger.warning(f"TrackDataViewController: Could not parse frame number: '{frame_text}'")
        
        # A normal click on a track row (not Ctrl) should also select it if not already active
        if not is_active_element_in_manager and self._element_manager.get_active_element_type() != ElementType.TRACK:
            if self._element_manager.active_element_index != element_index_clicked:
                 self._element_manager.set_active_element(element_index_clicked)

        logger.debug(f"TrackDataViewController: Normal cell ({row},{column}) click on TRACK element {element_id_clicked}.")


    @QtCore.Slot()
    def _sync_active_element_selection_in_tables(self) -> None: # Renamed for clarity
        if not hasattr(self, '_element_manager'):
            logger.warning("TrackDataViewController: Cannot sync table selection, element_manager missing.")
            return

        active_id = self._element_manager.get_active_element_id()
        active_type = self._element_manager.get_active_element_type()
        
        logger.debug(f"TrackDataViewController: Syncing table selections to manager's active ID: {active_id}, Type: {active_type}")
        
        if hasattr(self, '_tracks_table') and self._tracks_table:
            if active_type == ElementType.TRACK:
                self._select_element_row_by_id_in_ui(active_id, self._tracks_table, config.COL_TRACK_ID)
            else:
                self._tracks_table.clearSelection()
                logger.debug("Active element is not a TRACK (or none active), cleared tracks table selection.")

        if hasattr(self, '_lines_table') and self._lines_table:
            if active_type == ElementType.MEASUREMENT_LINE:
                self._select_element_row_by_id_in_ui(active_id, self._lines_table, config.COL_LINE_ID)
            else:
                self._lines_table.clearSelection()
                logger.debug("Active element is not a MEASUREMENT_LINE (or none active), cleared lines table selection.")


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
                    pass # Ignore if text is not a valid frame number

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
        if checked: # Only act when a radio button is checked
            mode = button.property("visibility_mode")
            element_index = button.property("element_index") # This should be the index in ElementManager.elements
            
            if isinstance(mode, ElementVisibilityMode) and isinstance(element_index, int):
                logger.debug(f"Controller: Visibility changed for element index {element_index} to {mode.name}")
                self._element_manager.set_element_visibility_mode(element_index, mode)


    def _clear_internal_visibility_button_groups(self) -> None: # Now clears all groups
        for element_id_key in list(self._element_visibility_button_groups.keys()): # Iterate over a copy of keys
            group = self._element_visibility_button_groups.pop(element_id_key, None)
            if group:
                try:
                    # Disconnect all signals from the group to be safe, though specific disconnect is better
                    group.buttonToggled.disconnect(self._on_visibility_changed_in_table)
                except (TypeError, RuntimeError): 
                    pass # Already disconnected or error
        self._element_visibility_button_groups.clear()


    def _select_element_row_by_id_in_ui(self, element_id_to_select: int,
                                         target_table: QtWidgets.QTableWidget,
                                         id_column_index: int) -> None:
        if element_id_to_select == -1:
            target_table.clearSelection()
            return
        
        found_row = -1
        num_data_rows_in_table = 0
        if target_table is self._tracks_table:
            track_elements = [el for el in self._element_manager.elements if el['type'] == ElementType.TRACK]
            num_data_rows_in_table = len(track_elements)
        elif self._lines_table and target_table is self._lines_table:
            line_elements = [el for el in self._element_manager.elements if el['type'] == ElementType.MEASUREMENT_LINE]
            num_data_rows_in_table = len(line_elements)
        else:
            num_data_rows_in_table = target_table.rowCount()


        for row_idx in range(num_data_rows_in_table):
            item = target_table.item(row_idx, id_column_index)
            if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == element_id_to_select:
                found_row = row_idx
                break
        
        if found_row != -1:
            # Ensure this does not re-trigger selection changed signals that call set_active_element
            target_table.blockSignals(True)
            target_table.selectRow(found_row)
            target_table.blockSignals(False)
            if item: target_table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
        else:
            target_table.clearSelection() # Clear if ID not found in current table items
            logger.debug(f"Controller: Could not find row for element ID {element_id_to_select} in table {target_table.objectName()}. Cleared selection.")


    def _create_centered_cell_widget_for_table(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        cell_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(cell_widget)
        layout.addWidget(widget)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        return cell_widget

    @QtCore.Slot()
    def update_tracks_table_ui(self) -> None: # Specifically for TRACKS
        logger.debug("TrackDataViewController: Updating tracks table UI...")
        if not hasattr(self, '_tracks_table') or not self._tracks_table: return

        current_active_element_id = self._element_manager.get_active_element_id()
        current_active_type = self._element_manager.get_active_element_type()
        selected_row_to_restore = -1

        self._tracks_table.blockSignals(True)
        # No need to call _clear_internal_visibility_button_groups here,
        # as new groups are created and old ones are implicitly disconnected if rows are rebuilt.
        # However, if rows are *updated* rather than rebuilt, managing groups explicitly is safer.
        # For simplicity of this update, let's clear and rebuild groups.
        self._clear_internal_visibility_button_groups()


        track_elements_to_display = []
        for el_idx, el in enumerate(self._element_manager.elements):
            if el['type'] == ElementType.TRACK:
                track_elements_to_display.append({'element': el, 'manager_index': el_idx})
        
        num_data_rows = len(track_elements_to_display)
        self._tracks_table.setRowCount(num_data_rows)

        link_color = QtGui.QColor("blue")
        link_tooltip = "Click to jump to this frame"
        style = self._main_window_ref.style()

        for row_idx, track_info in enumerate(track_elements_to_display):
            element = track_info['element']
            element_index_in_manager = track_info['manager_index']
            element_id = element['id']
            track_data: ElementData = element['data']
            
            num_points = len(track_data)
            start_frame, end_frame = (-1, -1)
            if num_points > 0: start_frame = track_data[0][0]; end_frame = track_data[-1][0]
            
            delete_button = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon), "")
            delete_button.setToolTip(f"Delete Track {element_id}"); delete_button.setFlat(True); delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            delete_button.setProperty("element_index", element_index_in_manager) # Store manager index
            delete_button.clicked.connect(lambda checked=False, el_idx=element_index_in_manager: self._on_delete_element_button_clicked_in_table(el_idx))
            self._tracks_table.setCellWidget(row_idx, config.COL_DELETE, self._create_centered_cell_widget_for_table(delete_button))

            id_item = QtWidgets.QTableWidgetItem(str(element_id))
            id_item.setData(QtCore.Qt.ItemDataRole.UserRole, element_id) # Store ID for retrieval
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
            rb_hidden = QtWidgets.QRadioButton()
            rb_home_frame = QtWidgets.QRadioButton() # New RadioButton
            rb_incremental = QtWidgets.QRadioButton()
            rb_always = QtWidgets.QRadioButton()
            
            rb_hidden.setProperty("visibility_mode", ElementVisibilityMode.HIDDEN); rb_hidden.setProperty("element_index", element_index_in_manager)
            rb_home_frame.setProperty("visibility_mode", ElementVisibilityMode.HOME_FRAME); rb_home_frame.setProperty("element_index", element_index_in_manager) # New
            rb_incremental.setProperty("visibility_mode", ElementVisibilityMode.INCREMENTAL); rb_incremental.setProperty("element_index", element_index_in_manager)
            rb_always.setProperty("visibility_mode", ElementVisibilityMode.ALWAYS_VISIBLE); rb_always.setProperty("element_index", element_index_in_manager)
            
            button_group = QtWidgets.QButtonGroup(self) # Parent is self (TrackDataViewController)
            button_group.addButton(rb_hidden); 
            button_group.addButton(rb_home_frame) # New
            button_group.addButton(rb_incremental); 
            button_group.addButton(rb_always)
            button_group.setExclusive(True)
            self._element_visibility_button_groups[element_id] = button_group # Store by element ID
            
            button_group.blockSignals(True)
            if current_mode == ElementVisibilityMode.HIDDEN: rb_hidden.setChecked(True)
            elif current_mode == ElementVisibilityMode.HOME_FRAME: rb_home_frame.setChecked(True) # New
            elif current_mode == ElementVisibilityMode.INCREMENTAL: rb_incremental.setChecked(True)
            else: rb_always.setChecked(True) # Default to ALWAYS_VISIBLE if somehow unset
            button_group.blockSignals(False)
            
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_HIDDEN, self._create_centered_cell_widget_for_table(rb_hidden))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_HOME_FRAME, self._create_centered_cell_widget_for_table(rb_home_frame)) # New
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_INCREMENTAL, self._create_centered_cell_widget_for_table(rb_incremental))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_ALWAYS, self._create_centered_cell_widget_for_table(rb_always))
            
            button_group.buttonToggled.connect(self._on_visibility_changed_in_table)

            if element_id == current_active_element_id and current_active_type == ElementType.TRACK:
                selected_row_to_restore = row_idx

        if selected_row_to_restore != -1:
            self._tracks_table.selectRow(selected_row_to_restore)
        elif self._tracks_table.rowCount() > 0 : # If no specific row to restore but table has data
            pass # Don't clear selection if there was no specific match to restore
        else: # Table is empty
            self._tracks_table.clearSelection()


        self._tracks_table.blockSignals(False)
        self.updateMainWindowUIState.emit()


    @QtCore.Slot()
    def update_lines_table_ui(self) -> None: # Specifically for LINES
        if not self._lines_table:
            logger.debug("TrackDataViewController: Skipping update_lines_table_ui, table not initialized.")
            return
        
        logger.debug("TrackDataViewController: Updating lines table UI...")
        current_active_element_id = self._element_manager.get_active_element_id()
        current_active_type = self._element_manager.get_active_element_type()
        selected_row_to_restore = -1

        self._lines_table.blockSignals(True)
        # Assuming _clear_internal_visibility_button_groups is generic enough or a separate one for lines is needed
        # For now, let's use the same one; if IDs are unique across types, it works.
        # If IDs can clash, then separate dicts for button groups are needed.
        # self._clear_internal_visibility_button_groups() # Or a _lines_visibility_button_groups

        line_elements_to_display = []
        for el_idx, el in enumerate(self._element_manager.elements): 
            if el['type'] == ElementType.MEASUREMENT_LINE:
                line_elements_to_display.append({'element': el, 'manager_index': el_idx}) 
        
        self._lines_table.setRowCount(len(line_elements_to_display))
        style = self._main_window_ref.style() # For delete icon

        for row_idx, line_info in enumerate(line_elements_to_display):
            line_element = line_info['element']
            element_index_in_manager = line_info['manager_index']
            element_id = line_element['id']
            element_data: ElementData = line_element['data'] 

            # Delete button for Lines table
            delete_button = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon), "")
            delete_button.setToolTip(f"Delete Line {element_id}"); delete_button.setFlat(True); delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            delete_button.setProperty("element_index", element_index_in_manager)
            delete_button.clicked.connect(lambda checked=False, el_idx=element_index_in_manager: self._on_delete_element_button_clicked_in_table(el_idx))
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_DELETE, self._create_centered_cell_widget_for_table(delete_button))


            id_item = QtWidgets.QTableWidgetItem(str(element_id))
            id_item.setData(QtCore.Qt.ItemDataRole.UserRole, element_id)
            id_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._lines_table.setItem(row_idx, config.COL_LINE_ID, id_item)

            frame_str = "Defining..." 
            if len(element_data) == 2: 
                frame_index_of_line = element_data[0][0] 
                frame_str = str(frame_index_of_line + 1) 
            elif self._element_manager._is_defining_element_type == ElementType.MEASUREMENT_LINE and \
                 self._element_manager.active_element_index != -1 and \
                 self._element_manager.elements[self._element_manager.active_element_index]['id'] == element_id:
                if self._element_manager._defining_element_frame_index is not None:
                    frame_str = f"{self._element_manager._defining_element_frame_index + 1} (Pending)"
            
            frame_item = QtWidgets.QTableWidgetItem(frame_str) 
            frame_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            frame_item.setFlags(frame_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            if frame_str.isdigit():
                frame_item.setForeground(QtGui.QColor("blue"))
                frame_item.setToolTip("Click to jump to this frame")
            self._lines_table.setItem(row_idx, config.COL_LINE_FRAME, frame_item)

            # Placeholder for Length and Angle - to be implemented in Phase 5
            length_item = QtWidgets.QTableWidgetItem("N/A") # Placeholder
            length_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            self._lines_table.setItem(row_idx, config.COL_LINE_LENGTH, length_item)
            angle_item = QtWidgets.QTableWidgetItem("N/A") # Placeholder
            angle_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            self._lines_table.setItem(row_idx, config.COL_LINE_ANGLE, angle_item)


            # Visibility Radio Buttons for Lines Table
            current_mode = self._element_manager.get_element_visibility_mode(element_index_in_manager)
            rb_line_hidden = QtWidgets.QRadioButton()
            rb_line_home_frame = QtWidgets.QRadioButton() # New
            rb_line_incremental = QtWidgets.QRadioButton()
            rb_line_always = QtWidgets.QRadioButton()

            rb_line_hidden.setProperty("visibility_mode", ElementVisibilityMode.HIDDEN); rb_line_hidden.setProperty("element_index", element_index_in_manager)
            rb_line_home_frame.setProperty("visibility_mode", ElementVisibilityMode.HOME_FRAME); rb_line_home_frame.setProperty("element_index", element_index_in_manager) # New
            rb_line_incremental.setProperty("visibility_mode", ElementVisibilityMode.INCREMENTAL); rb_line_incremental.setProperty("element_index", element_index_in_manager)
            rb_line_always.setProperty("visibility_mode", ElementVisibilityMode.ALWAYS_VISIBLE); rb_line_always.setProperty("element_index", element_index_in_manager)

            line_button_group = QtWidgets.QButtonGroup(self)
            line_button_group.addButton(rb_line_hidden)
            line_button_group.addButton(rb_line_home_frame) # New
            line_button_group.addButton(rb_line_incremental)
            line_button_group.addButton(rb_line_always)
            line_button_group.setExclusive(True)
            # Use a different dict or prefix keys if IDs can clash between tracks and lines
            self._element_visibility_button_groups[element_id] = line_button_group # Assuming IDs are unique globally

            line_button_group.blockSignals(True)
            if current_mode == ElementVisibilityMode.HIDDEN: rb_line_hidden.setChecked(True)
            elif current_mode == ElementVisibilityMode.HOME_FRAME: rb_line_home_frame.setChecked(True) # New
            elif current_mode == ElementVisibilityMode.INCREMENTAL: rb_line_incremental.setChecked(True)
            else: rb_line_always.setChecked(True)
            line_button_group.blockSignals(False)

            self._lines_table.setCellWidget(row_idx, config.COL_LINE_VIS_HIDDEN, self._create_centered_cell_widget_for_table(rb_line_hidden))
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_VIS_HOME_FRAME, self._create_centered_cell_widget_for_table(rb_line_home_frame)) # New
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_VIS_INCREMENTAL, self._create_centered_cell_widget_for_table(rb_line_incremental))
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_VIS_ALWAYS, self._create_centered_cell_widget_for_table(rb_line_always))
            
            line_button_group.buttonToggled.connect(self._on_visibility_changed_in_table)

            if element_id == current_active_element_id and current_active_type == ElementType.MEASUREMENT_LINE:
                selected_row_to_restore = row_idx
        
        if selected_row_to_restore != -1:
            self._lines_table.selectRow(selected_row_to_restore)
        elif self._lines_table.rowCount() > 0:
            pass # Don't clear if no specific match to restore
        else:
            self._lines_table.clearSelection()

        self._lines_table.blockSignals(False)
        logger.debug(f"TrackDataViewController: Lines table UI updated with {len(line_elements_to_display)} lines.")
        self.updateMainWindowUIState.emit()


    @QtCore.Slot()
    def update_points_table_ui(self) -> None:
        logger.debug("TrackDataViewController: Updating points table UI (now element-aware)...")
        active_element_id = self._element_manager.get_active_element_id()
        active_element_type = self._element_manager.get_active_element_type()

        if active_element_type == ElementType.TRACK and active_element_id != -1:
            self._points_tab_label.setText(f"Points for Track: {active_element_id}")
            active_points = self._element_manager.get_active_element_points_if_track()
        elif active_element_type == ElementType.MEASUREMENT_LINE and active_element_id != -1:
            self._points_tab_label.setText(f"Endpoints for Line: {active_element_id}")
            # Ensure data exists and is a list before accessing
            if self._element_manager.active_element_index != -1 and \
               0 <= self._element_manager.active_element_index < len(self._element_manager.elements) and \
               isinstance(self._element_manager.elements[self._element_manager.active_element_index].get('data'), list):
                 active_points = self._element_manager.elements[self._element_manager.active_element_index]['data']
            else: active_points = [] # Fallback
        else:
            self._points_tab_label.setText("Points: - (No compatible element selected)")
            active_points = []

        self._points_table.setRowCount(0) # Clear table before repopulating

        if not active_points: # If no points (e.g., line not fully defined yet, or empty track)
            return

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

            for col, val_str in [(config.COL_POINT_X, f"{x_display:.1f}" if isinstance(x_display, float) else str(x_display)),  # Format float
                                 (config.COL_POINT_Y, f"{y_display:.1f}" if isinstance(y_display, float) else str(y_display))]: # Format float
                item = QtWidgets.QTableWidgetItem(val_str)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self._points_table.setItem(row_idx, col, item)