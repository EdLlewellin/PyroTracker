# table_controllers.py
"""
Contains controller classes for managing UI logic for data tables
(Tracks and Points tables) in the MainWindow.
"""
import logging
import math # Added for length and angle calculation
from typing import Optional, TYPE_CHECKING, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets

import config # For table column constants
from element_manager import ElementVisibilityMode, ElementType, ElementData

if TYPE_CHECKING:
    from main_window import MainWindow
    from element_manager import ElementManager
    from video_handler import VideoHandler
    from scale_manager import ScaleManager
    from coordinates import CoordinateTransformer

logger = logging.getLogger(__name__)

class TrackDataViewController(QtCore.QObject):
    seekVideoToFrame = QtCore.Signal(int)
    updateMainWindowUIState = QtCore.Signal()
    statusBarMessage = QtCore.Signal(str, int)

    _lines_table: Optional[QtWidgets.QTableWidget]

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
            if hasattr(self._lines_table, 'horizontalHeader') and hasattr(self._lines_table.horizontalHeader(), 'sectionClicked'):
                 self._lines_table.horizontalHeader().sectionClicked.connect(
                     lambda logical_index: self.handle_visibility_header_clicked(logical_index, ElementType.MEASUREMENT_LINE)
                 )
            # Connect selection change for lines table for future use (e.g., updating points table)
            self._lines_table.itemSelectionChanged.connect(self._on_line_selection_changed_in_table)
            self._lines_table.cellClicked.connect(self._on_lines_table_cell_clicked)


        else:
            self._lines_table = None
            logger.error("TrackDataViewController: linesTableWidget not found or not a QTableWidget on MainWindow.")

        self._element_visibility_button_groups: Dict[int, QtWidgets.QButtonGroup] = {}
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
        # Also update lines table if scale changes, as length display depends on it
        if self._lines_table:
            self._scale_manager.scaleOrUnitChanged.connect(self.update_lines_table_ui)


    def set_video_loaded_status(self, is_loaded: bool, total_frames: int = 0) -> None:
        # ... (existing method, no changes needed here for this phase) ...
        if self._video_loaded != is_loaded:
            self._video_loaded = is_loaded
            self._total_frames_for_validation = total_frames if is_loaded else 0
            logger.debug(f"TrackDataViewController: video_loaded status changed to {is_loaded}. Updating tables.")
            self.update_tracks_table_ui()
            if self._lines_table: self.update_lines_table_ui()
            self.update_points_table_ui()
        elif is_loaded and self._total_frames_for_validation != total_frames:
            self._total_frames_for_validation = total_frames
            logger.debug(f"TrackDataViewController: video_loaded status same, but total_frames changed. Updating tables.")
            self.update_tracks_table_ui()
            if self._lines_table: self.update_lines_table_ui()
            self.update_points_table_ui()

    def handle_visibility_header_clicked(self, logical_index: int, element_type_to_filter: ElementType) -> None:
        # ... (existing method, no changes needed here for this phase) ...
        if not self._element_manager.elements: return
        target_mode: Optional[ElementVisibilityMode] = None
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
    def _on_track_selection_changed_in_table(self) -> None:
        # ... (existing method, no changes needed here for this phase) ...
        selected_items = self._tracks_table.selectedItems()
        if not selected_items: return
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
                    if el['id'] == element_id and el['type'] == ElementType.TRACK: 
                        element_index_in_manager = idx; break
                if element_index_in_manager != -1:
                    if self._element_manager.active_element_index != element_index_in_manager:
                        logger.debug(f"Controller: Tracks table selection changed to row {selected_row}, element ID {element_id}. Setting active element.")
                        self._element_manager.set_active_element(element_index_in_manager)
                else: logger.warning(f"Could not find TRACK element with ID {element_id} in ElementManager from table selection.")

    @QtCore.Slot()
    def _on_line_selection_changed_in_table(self) -> None:
        if not self._lines_table: return
        selected_items = self._lines_table.selectedItems()
        if not selected_items: return

        selected_row = self._lines_table.row(selected_items[0])
        if selected_row < 0 or selected_row >= self._lines_table.rowCount():
            logger.debug(f"TrackDataViewController: Invalid selected_row {selected_row} in _on_line_selection_changed_in_table. Ignoring.")
            return
            
        id_item = self._lines_table.item(selected_row, config.COL_LINE_ID)
        if id_item:
            element_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if element_id is not None and isinstance(element_id, int):
                element_index_in_manager = -1
                for idx, el in enumerate(self._element_manager.elements):
                    if el['id'] == element_id and el['type'] == ElementType.MEASUREMENT_LINE: 
                        element_index_in_manager = idx
                        break
                
                if element_index_in_manager != -1:
                    if self._element_manager.active_element_index != element_index_in_manager:
                        logger.debug(f"Controller: Lines table selection changed to row {selected_row}, element ID {element_id}. Setting active element.")
                        self._element_manager.set_active_element(element_index_in_manager)
                else:
                    logger.warning(f"Could not find MEASUREMENT_LINE element with ID {element_id} in ElementManager from table selection.")


    @QtCore.Slot(int, int)
    def _on_tracks_table_cell_clicked(self, row: int, column: int) -> None:
        # ... (existing method, ensure it doesn't conflict if line selection also uses this) ...
        # For Phase 5, this can remain as is. If line selection via cell click needs different behavior,
        # we'll address it in Phase 6.
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
                element_index_clicked = idx; break
        if element_index_clicked == -1:
            logger.warning(f"TrackDataViewController: Clicked TRACK element ID {element_id_clicked} not found in manager.")
            return
        current_modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_ctrl_click = (current_modifiers == QtCore.Qt.KeyboardModifier.ControlModifier)
        is_active_element_in_manager = (element_index_clicked == self._element_manager.active_element_index)

        if is_ctrl_click:
            if is_active_element_in_manager and self._element_manager.get_active_element_type() == ElementType.TRACK:
                logger.info(f"TrackDataViewController: Ctrl+Clicked on active TRACK element {element_id_clicked}. Deselecting.")
                self._element_manager.set_active_element(-1)
            else: 
                logger.info(f"TrackDataViewController: Ctrl+Clicked on TRACK element {element_id_clicked}. Selecting.")
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
                        logger.debug(f"TrackDataViewController: Frame link clicked for TRACK element {element_id_clicked}. Emitting seekVideoToFrame({target_frame_0based})")
                        self.seekVideoToFrame.emit(target_frame_0based)
                except (ValueError, TypeError): logger.warning(f"TrackDataViewController: Could not parse frame number: '{frame_text}'")
        
        # A normal click on a track row should select it if it's not already the active element OR if the active element is not a track
        if self._element_manager.active_element_index != element_index_clicked or self._element_manager.get_active_element_type() != ElementType.TRACK:
            self._element_manager.set_active_element(element_index_clicked)
        logger.debug(f"TrackDataViewController: Normal cell ({row},{column}) click on TRACK element {element_id_clicked}.")


    @QtCore.Slot(int, int)
    def _on_lines_table_cell_clicked(self, row: int, column: int) -> None:
        if not self._video_loaded or not self._lines_table: return
        if row < 0 or row >= self._lines_table.rowCount():
            logger.debug(f"TrackDataViewController: Cell click on invalid row {row} in lines table. Ignoring.")
            return

        id_item = self._lines_table.item(row, config.COL_LINE_ID)
        if not id_item:
            logger.debug("TrackDataViewController: Cell click on non-data row or invalid ID item in lines table.")
            return
        
        element_id_clicked = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(element_id_clicked, int):
            logger.warning(f"TrackDataViewController: Invalid element_id data in lines table: {element_id_clicked}")
            return

        element_index_clicked = -1
        for idx, el in enumerate(self._element_manager.elements):
            if el['id'] == element_id_clicked and el['type'] == ElementType.MEASUREMENT_LINE:
                element_index_clicked = idx
                break
        
        if element_index_clicked == -1:
            logger.warning(f"TrackDataViewController: Clicked MEASUREMENT_LINE element ID {element_id_clicked} not found in manager.")
            return

        current_modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_ctrl_click = (current_modifiers == QtCore.Qt.KeyboardModifier.ControlModifier)
        is_active_element_in_manager = (element_index_clicked == self._element_manager.active_element_index)

        if is_ctrl_click:
            if is_active_element_in_manager and self._element_manager.get_active_element_type() == ElementType.MEASUREMENT_LINE:
                logger.info(f"TrackDataViewController: Ctrl+Clicked on active MEASUREMENT_LINE {element_id_clicked}. Deselecting.")
                self._element_manager.set_active_element(-1)
            else:
                logger.info(f"TrackDataViewController: Ctrl+Clicked on MEASUREMENT_LINE {element_id_clicked}. Selecting.")
                if self._element_manager.active_element_index != element_index_clicked:
                    self._element_manager.set_active_element(element_index_clicked)
            return

        if column == config.COL_LINE_FRAME:
            frame_item_widget = self._lines_table.item(row, column)
            if frame_item_widget:
                frame_text = frame_item_widget.text().split(" ")[0] # Get only number part if "(Pending)"
                try:
                    target_frame_0based = int(frame_text) - 1
                    if 0 <= target_frame_0based < self._total_frames_for_validation:
                        logger.debug(f"TrackDataViewController: Frame link clicked for LINE element {element_id_clicked}. Emitting seekVideoToFrame({target_frame_0based})")
                        self.seekVideoToFrame.emit(target_frame_0based)
                except (ValueError, TypeError):
                    logger.warning(f"TrackDataViewController: Could not parse frame number from lines table: '{frame_text}'")

        # A normal click on a line row should select it if it's not already the active element OR if the active element is not a line
        if self._element_manager.active_element_index != element_index_clicked or self._element_manager.get_active_element_type() != ElementType.MEASUREMENT_LINE:
             self._element_manager.set_active_element(element_index_clicked)
        logger.debug(f"TrackDataViewController: Normal cell ({row},{column}) click on MEASUREMENT_LINE {element_id_clicked}.")


    @QtCore.Slot()
    def _sync_active_element_selection_in_tables(self) -> None:
        # ... (existing method, no changes needed here for this phase) ...
        if not hasattr(self, '_element_manager'):
            logger.warning("TrackDataViewController: Cannot sync table selection, element_manager missing.")
            return
        active_id = self._element_manager.get_active_element_id()
        active_type = self._element_manager.get_active_element_type()
        logger.debug(f"TrackDataViewController: Syncing table selections to manager's active ID: {active_id}, Type: {active_type.name if active_type else 'None'}")
        if hasattr(self, '_tracks_table') and self._tracks_table:
            if active_type == ElementType.TRACK: self._select_element_row_by_id_in_ui(active_id, self._tracks_table, config.COL_TRACK_ID)
            else: self._tracks_table.clearSelection(); logger.debug("Active element is not a TRACK, cleared tracks table selection.")
        if hasattr(self, '_lines_table') and self._lines_table:
            if active_type == ElementType.MEASUREMENT_LINE: self._select_element_row_by_id_in_ui(active_id, self._lines_table, config.COL_LINE_ID)
            else: self._lines_table.clearSelection(); logger.debug("Active element is not a LINE, cleared lines table selection.")

    @QtCore.Slot(int, int)
    def _on_points_table_cell_clicked(self, row: int, column: int) -> None:
        # ... (existing method, no changes needed here for this phase) ...
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
                except ValueError: pass

    @QtCore.Slot(int)
    def _on_delete_element_button_clicked_in_table(self, element_index: int) -> None:
        # ... (existing method, should work for lines too) ...
        if not (0 <= element_index < len(self._element_manager.elements)):
            logger.error(f"Delete button clicked for invalid element index: {element_index}")
            return
        element_to_delete = self._element_manager.elements[element_index]
        element_id = element_to_delete['id']; element_type_name = element_to_delete['type'].name.replace("_", " ").title()
        reply = QtWidgets.QMessageBox.question(self._main_window_ref, f"Confirm Delete {element_type_name}", f"Delete {element_type_name} {element_id}?", QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel, QtWidgets.QMessageBox.StandardButton.Cancel)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            logger.info(f"Controller: User confirmed deletion for element index {element_index} (ID: {element_id}).")
            success = self._element_manager.delete_element_by_index(element_index)
            msg = f"Deleted {element_type_name} {element_id}" if success else f"Failed to delete {element_type_name} {element_id}"
            self.statusBarMessage.emit(msg, 3000)
            if not success: logger.error(f"Controller: ElementManager failed to delete element index {element_index}."); QtWidgets.QMessageBox.warning(self._main_window_ref, "Delete Error", f"Could not delete {element_type_name} {element_id}.")
            self.updateMainWindowUIState.emit()

    @QtCore.Slot(QtWidgets.QAbstractButton, bool)
    def _on_visibility_changed_in_table(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        # ... (existing method, should work for lines too if properties are set correctly) ...
        if checked:
            mode = button.property("visibility_mode"); element_index = button.property("element_index")
            if isinstance(mode, ElementVisibilityMode) and isinstance(element_index, int):
                logger.debug(f"Controller: Visibility changed for element index {element_index} to {mode.name}")
                self._element_manager.set_element_visibility_mode(element_index, mode)

    def _clear_internal_visibility_button_groups(self) -> None:
        # ... (existing method) ...
        for element_id_key in list(self._element_visibility_button_groups.keys()):
            group = self._element_visibility_button_groups.pop(element_id_key, None)
            if group:
                try: group.buttonToggled.disconnect(self._on_visibility_changed_in_table)
                except (TypeError, RuntimeError): pass 
        self._element_visibility_button_groups.clear()

    def _select_element_row_by_id_in_ui(self, element_id_to_select: int, target_table: QtWidgets.QTableWidget, id_column_index: int) -> None:
        # ... (existing method) ...
        if element_id_to_select == -1: target_table.clearSelection(); return
        found_row = -1; num_data_rows_in_table = 0
        if target_table is self._tracks_table: num_data_rows_in_table = len([el for el in self._element_manager.elements if el['type'] == ElementType.TRACK])
        elif self._lines_table and target_table is self._lines_table: num_data_rows_in_table = len([el for el in self._element_manager.elements if el['type'] == ElementType.MEASUREMENT_LINE])
        else: num_data_rows_in_table = target_table.rowCount()
        for row_idx in range(num_data_rows_in_table):
            item = target_table.item(row_idx, id_column_index)
            if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == element_id_to_select: found_row = row_idx; break
        if found_row != -1:
            target_table.blockSignals(True); target_table.selectRow(found_row); target_table.blockSignals(False)
            if item: target_table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
        else: target_table.clearSelection(); logger.debug(f"Controller: Could not find row for element ID {element_id_to_select} in table {target_table.objectName()}. Cleared selection.")

    def _create_centered_cell_widget_for_table(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        # ... (existing method) ...
        cell_widget = QtWidgets.QWidget(); layout = QtWidgets.QHBoxLayout(cell_widget)
        layout.addWidget(widget); layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0); return cell_widget

    @QtCore.Slot()
    def update_tracks_table_ui(self) -> None:
        # ... (existing method, no changes needed here for this phase) ...
        logger.debug("TrackDataViewController: Updating tracks table UI...")
        if not hasattr(self, '_tracks_table') or not self._tracks_table: return
        current_active_element_id = self._element_manager.get_active_element_id()
        current_active_type = self._element_manager.get_active_element_type()
        selected_row_to_restore = -1
        self._tracks_table.blockSignals(True)
        self._clear_internal_visibility_button_groups() # Clears all groups, fine for now if IDs are unique
        track_elements_to_display = []
        for el_idx, el in enumerate(self._element_manager.elements):
            if el['type'] == ElementType.TRACK: track_elements_to_display.append({'element': el, 'manager_index': el_idx})
        num_data_rows = len(track_elements_to_display); self._tracks_table.setRowCount(num_data_rows)
        link_color = QtGui.QColor("blue"); link_tooltip = "Click to jump to this frame"; style = self._main_window_ref.style()
        for row_idx, track_info in enumerate(track_elements_to_display):
            element = track_info['element']; element_index_in_manager = track_info['manager_index']
            element_id = element['id']; track_data: ElementData = element['data']
            num_points = len(track_data); start_frame, end_frame = (-1, -1)
            if num_points > 0: start_frame = track_data[0][0]; end_frame = track_data[-1][0]
            delete_button = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon), "")
            delete_button.setToolTip(f"Delete Track {element_id}"); delete_button.setFlat(True); delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            delete_button.setProperty("element_index", element_index_in_manager)
            delete_button.clicked.connect(lambda checked=False, el_idx=element_index_in_manager: self._on_delete_element_button_clicked_in_table(el_idx))
            self._tracks_table.setCellWidget(row_idx, config.COL_DELETE, self._create_centered_cell_widget_for_table(delete_button))
            id_item = QtWidgets.QTableWidgetItem(str(element_id)); id_item.setData(QtCore.Qt.ItemDataRole.UserRole, element_id)
            id_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._tracks_table.setItem(row_idx, config.COL_TRACK_ID, id_item)
            for col, val, is_link in [(config.COL_TRACK_POINTS, str(num_points), False), (config.COL_TRACK_START_FRAME, str(start_frame + 1) if start_frame != -1 else "N/A", start_frame != -1), (config.COL_TRACK_END_FRAME, str(end_frame + 1) if end_frame != -1 else "N/A", end_frame != -1)]:
                item = QtWidgets.QTableWidgetItem(val); item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if is_link: item.setForeground(link_color); item.setToolTip(link_tooltip)
                self._tracks_table.setItem(row_idx, col, item)
            current_mode = self._element_manager.get_element_visibility_mode(element_index_in_manager)
            rb_hidden = QtWidgets.QRadioButton(); rb_home_frame = QtWidgets.QRadioButton(); rb_incremental = QtWidgets.QRadioButton(); rb_always = QtWidgets.QRadioButton()
            rb_hidden.setProperty("visibility_mode", ElementVisibilityMode.HIDDEN); rb_hidden.setProperty("element_index", element_index_in_manager)
            rb_home_frame.setProperty("visibility_mode", ElementVisibilityMode.HOME_FRAME); rb_home_frame.setProperty("element_index", element_index_in_manager)
            rb_incremental.setProperty("visibility_mode", ElementVisibilityMode.INCREMENTAL); rb_incremental.setProperty("element_index", element_index_in_manager)
            rb_always.setProperty("visibility_mode", ElementVisibilityMode.ALWAYS_VISIBLE); rb_always.setProperty("element_index", element_index_in_manager)
            button_group = QtWidgets.QButtonGroup(self); button_group.addButton(rb_hidden); button_group.addButton(rb_home_frame); button_group.addButton(rb_incremental); button_group.addButton(rb_always); button_group.setExclusive(True)
            self._element_visibility_button_groups[element_id] = button_group
            button_group.blockSignals(True)
            if current_mode == ElementVisibilityMode.HIDDEN: rb_hidden.setChecked(True)
            elif current_mode == ElementVisibilityMode.HOME_FRAME: rb_home_frame.setChecked(True)
            elif current_mode == ElementVisibilityMode.INCREMENTAL: rb_incremental.setChecked(True)
            else: rb_always.setChecked(True)
            button_group.blockSignals(False)
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_HIDDEN, self._create_centered_cell_widget_for_table(rb_hidden))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_HOME_FRAME, self._create_centered_cell_widget_for_table(rb_home_frame))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_INCREMENTAL, self._create_centered_cell_widget_for_table(rb_incremental))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_ALWAYS, self._create_centered_cell_widget_for_table(rb_always))
            button_group.buttonToggled.connect(self._on_visibility_changed_in_table)
            if element_id == current_active_element_id and current_active_type == ElementType.TRACK: selected_row_to_restore = row_idx
        if selected_row_to_restore != -1: self._tracks_table.selectRow(selected_row_to_restore)
        elif self._tracks_table.rowCount() > 0 : pass 
        else: self._tracks_table.clearSelection()
        self._tracks_table.blockSignals(False); self.updateMainWindowUIState.emit()

    @QtCore.Slot()
    def update_lines_table_ui(self) -> None:
        if not self._lines_table:
            logger.debug("TrackDataViewController: Skipping update_lines_table_ui, table not initialized.")
            return
        
        logger.debug("TrackDataViewController: Updating lines table UI...")
        current_active_element_id = self._element_manager.get_active_element_id()
        current_active_type = self._element_manager.get_active_element_type()
        selected_row_to_restore = -1

        self._lines_table.blockSignals(True)
        # Clearing and rebuilding groups for lines too. Ensure _element_visibility_button_groups handles IDs correctly.
        # If track IDs and line IDs can overlap, this might need refinement (e.g., separate dicts or prefixed keys).
        # Assuming unique IDs across all element types for now.
        # _clear_internal_visibility_button_groups() # Already called by update_tracks_table_ui if it runs first

        line_elements_to_display = []
        for el_idx, el in enumerate(self._element_manager.elements): 
            if el['type'] == ElementType.MEASUREMENT_LINE:
                line_elements_to_display.append({'element': el, 'manager_index': el_idx}) 
        
        self._lines_table.setRowCount(len(line_elements_to_display))
        style = self._main_window_ref.style() 
        link_color = QtGui.QColor("blue")
        link_tooltip = "Click to jump to this frame"

        for row_idx, line_info in enumerate(line_elements_to_display):
            line_element = line_info['element']
            element_index_in_manager = line_info['manager_index']
            element_id = line_element['id']
            element_data: ElementData = line_element['data'] 

            # Delete button
            delete_button = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon), "")
            delete_button.setToolTip(f"Delete Line {element_id}"); delete_button.setFlat(True); delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            delete_button.setProperty("element_index", element_index_in_manager)
            delete_button.clicked.connect(lambda checked=False, el_idx=element_index_in_manager: self._on_delete_element_button_clicked_in_table(el_idx))
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_DELETE, self._create_centered_cell_widget_for_table(delete_button))

            # ID
            id_item = QtWidgets.QTableWidgetItem(str(element_id))
            id_item.setData(QtCore.Qt.ItemDataRole.UserRole, element_id)
            id_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._lines_table.setItem(row_idx, config.COL_LINE_ID, id_item)

            # Frame
            frame_str = "Defining..." 
            line_definition_frame = -1
            if len(element_data) == 2: 
                line_definition_frame = element_data[0][0] 
                frame_str = str(line_definition_frame + 1) 
            elif self._element_manager._is_defining_element_type == ElementType.MEASUREMENT_LINE and \
                 self._element_manager.active_element_index != -1 and \
                 self._element_manager.elements[self._element_manager.active_element_index]['id'] == element_id:
                if self._element_manager._defining_element_frame_index is not None:
                    line_definition_frame = self._element_manager._defining_element_frame_index
                    frame_str = f"{line_definition_frame + 1} (Pending)"
            
            frame_item = QtWidgets.QTableWidgetItem(frame_str) 
            frame_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            item_flags_frame = frame_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable
            if frame_str.isdigit(): # Only make it a link if it's a valid frame number
                frame_item.setForeground(link_color); frame_item.setToolTip(link_tooltip)
            else: # Not a link, ensure it's not selectable if "Defining..."
                item_flags_frame &= ~QtCore.Qt.ItemFlag.ItemIsSelectable
            frame_item.setFlags(item_flags_frame)
            self._lines_table.setItem(row_idx, config.COL_LINE_FRAME, frame_item)

            # Length and Angle
            length_str = "N/A"
            angle_str = "N/A"
            if len(element_data) == 2: # Line is fully defined
                p1_data, p2_data = element_data[0], element_data[1]
                _, _, x1_px_internal, y1_px_internal = p1_data
                _, _, x2_px_internal, y2_px_internal = p2_data

                # Transform points to the current display coordinate system (without scaling yet)
                x1_cs, y1_cs = self._coord_transformer.transform_point_for_display(x1_px_internal, y1_px_internal)
                x2_cs, y2_cs = self._coord_transformer.transform_point_for_display(x2_px_internal, y2_px_internal)
                
                # Calculate pixel length in the current coordinate system
                dx_cs_px = x2_cs - x1_cs
                dy_cs_px = y2_cs - y1_cs
                pixel_length_cs = math.sqrt(dx_cs_px**2 + dy_cs_px**2)

                # Get display unit and scaled length
                scaled_length, unit = self._scale_manager.transform_value_for_display(pixel_length_cs)
                
                # Use ElementManager's formatter for consistency if desired, or a local one
                # For now, using ScaleManager's direct output which includes unit.
                if self._scale_manager.get_scale_m_per_px() is not None and unit == "m":
                     # If we have ElementManager's _format_length_for_display, use it:
                    if hasattr(self._element_manager, '_format_length_for_display'):
                        length_str = self._element_manager._format_length_for_display(scaled_length) # scaled_length is already in meters
                    else: # Fallback
                        length_str = f"{scaled_length:.3f} {unit}"
                else: # Pixels
                    length_str = f"{scaled_length:.1f} {unit}"

                # Angle: 0-360 degrees, 0 to the right. Y increases downwards in scene, but display transform handles it.
                # Use dx_cs_px, dy_cs_px as they are in the current display coordinate system
                angle_rad = math.atan2(-dy_cs_px, dx_cs_px) # Negative dy because y typically increases upwards in math angles
                angle_deg = math.degrees(angle_rad)
                if angle_deg < 0:
                    angle_deg += 360
                angle_str = f"{angle_deg:.1f}°"

            length_item = QtWidgets.QTableWidgetItem(length_str)
            length_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            length_item.setFlags(length_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._lines_table.setItem(row_idx, config.COL_LINE_LENGTH, length_item)
            
            angle_item = QtWidgets.QTableWidgetItem(angle_str)
            angle_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            angle_item.setFlags(angle_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._lines_table.setItem(row_idx, config.COL_LINE_ANGLE, angle_item)

            # Visibility Radio Buttons
            current_mode = self._element_manager.get_element_visibility_mode(element_index_in_manager)
            rb_line_hidden = QtWidgets.QRadioButton(); rb_line_home_frame = QtWidgets.QRadioButton(); rb_line_incremental = QtWidgets.QRadioButton(); rb_line_always = QtWidgets.QRadioButton()
            rb_line_hidden.setProperty("visibility_mode", ElementVisibilityMode.HIDDEN); rb_line_hidden.setProperty("element_index", element_index_in_manager)
            rb_line_home_frame.setProperty("visibility_mode", ElementVisibilityMode.HOME_FRAME); rb_line_home_frame.setProperty("element_index", element_index_in_manager)
            rb_line_incremental.setProperty("visibility_mode", ElementVisibilityMode.INCREMENTAL); rb_line_incremental.setProperty("element_index", element_index_in_manager)
            rb_line_always.setProperty("visibility_mode", ElementVisibilityMode.ALWAYS_VISIBLE); rb_line_always.setProperty("element_index", element_index_in_manager)
            line_button_group = QtWidgets.QButtonGroup(self); line_button_group.addButton(rb_line_hidden); line_button_group.addButton(rb_line_home_frame); line_button_group.addButton(rb_line_incremental); line_button_group.addButton(rb_line_always); line_button_group.setExclusive(True)
            self._element_visibility_button_groups[element_id] = line_button_group # Store by element_id
            line_button_group.blockSignals(True)
            if current_mode == ElementVisibilityMode.HIDDEN: rb_line_hidden.setChecked(True)
            elif current_mode == ElementVisibilityMode.HOME_FRAME: rb_line_home_frame.setChecked(True)
            elif current_mode == ElementVisibilityMode.INCREMENTAL: rb_line_incremental.setChecked(True)
            else: rb_line_always.setChecked(True)
            line_button_group.blockSignals(False)
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_VIS_HIDDEN, self._create_centered_cell_widget_for_table(rb_line_hidden))
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_VIS_HOME_FRAME, self._create_centered_cell_widget_for_table(rb_line_home_frame))
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_VIS_INCREMENTAL, self._create_centered_cell_widget_for_table(rb_line_incremental))
            self._lines_table.setCellWidget(row_idx, config.COL_LINE_VIS_ALWAYS, self._create_centered_cell_widget_for_table(rb_line_always))
            line_button_group.buttonToggled.connect(self._on_visibility_changed_in_table)

            if element_id == current_active_element_id and current_active_type == ElementType.MEASUREMENT_LINE:
                selected_row_to_restore = row_idx
        
        if selected_row_to_restore != -1:
            self._lines_table.selectRow(selected_row_to_restore)
        elif self._lines_table.rowCount() > 0: pass
        else: self._lines_table.clearSelection()

        self._lines_table.blockSignals(False)
        logger.debug(f"TrackDataViewController: Lines table UI updated with {len(line_elements_to_display)} lines.")
        self.updateMainWindowUIState.emit()


    @QtCore.Slot()
    def update_points_table_ui(self) -> None:
        # ... (existing method, no changes needed here for this phase) ...
        logger.debug("TrackDataViewController: Updating points table UI (now element-aware)...")
        active_element_id = self._element_manager.get_active_element_id()
        active_element_type = self._element_manager.get_active_element_type()
        if active_element_type == ElementType.TRACK and active_element_id != -1:
            self._points_tab_label.setText(f"Points for Track: {active_element_id}")
            active_points = self._element_manager.get_active_element_points_if_track()
        elif active_element_type == ElementType.MEASUREMENT_LINE and active_element_id != -1:
            self._points_tab_label.setText(f"Endpoints for Line: {active_element_id}")
            if self._element_manager.active_element_index != -1 and \
               0 <= self._element_manager.active_element_index < len(self._element_manager.elements) and \
               isinstance(self._element_manager.elements[self._element_manager.active_element_index].get('data'), list):
                 active_points = self._element_manager.elements[self._element_manager.active_element_index]['data']
            else: active_points = []
        else: self._points_tab_label.setText("Points: - (No compatible element selected)"); active_points = []
        self._points_table.setRowCount(0) 
        if not active_points: return
        link_color = QtGui.QColor("blue"); link_tooltip = "Click to jump to this frame"
        display_unit_short = self._scale_manager.get_display_unit_short()
        x_header_text = f"X [{display_unit_short}]"; y_header_text = f"Y [{display_unit_short}]"
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
            for col, val_str in [(config.COL_POINT_X, f"{x_display:.1f}" if isinstance(x_display, float) else str(x_display)), (config.COL_POINT_Y, f"{y_display:.1f}" if isinstance(y_display, float) else str(y_display))]:
                item = QtWidgets.QTableWidgetItem(val_str)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self._points_table.setItem(row_idx, col, item)