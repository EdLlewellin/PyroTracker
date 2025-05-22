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
from track_manager import TrackVisibilityMode, ElementType 

if TYPE_CHECKING:
    # To avoid circular imports, only for type hinting
    from main_window import MainWindow # For QMessageBox parent and style access
    from track_manager import TrackManager
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

    def __init__(self,
                 main_window_ref: 'MainWindow', # For style, status bar, QMessageBox parent
                 track_manager: 'TrackManager',
                 video_handler: 'VideoHandler',
                 scale_manager: 'ScaleManager',
                 coord_transformer: 'CoordinateTransformer',
                 tracks_table_widget: QtWidgets.QTableWidget,
                 points_table_widget: QtWidgets.QTableWidget,
                 points_tab_label: QtWidgets.QLabel,
                 parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)

        self._main_window_ref = main_window_ref 
        self._track_manager = track_manager
        self._video_handler = video_handler
        self._scale_manager = scale_manager
        self._coord_transformer = coord_transformer
        self._tracks_table = tracks_table_widget
        self._points_table = points_table_widget
        self._points_tab_label = points_tab_label

        # MODIFIED: Key for button groups will be element ID, not track_id (index+1)
        self._element_visibility_button_groups: Dict[int, QtWidgets.QButtonGroup] = {}
        self._video_loaded: bool = False 
        self._total_frames_for_validation: int = 0


        self._tracks_table.itemSelectionChanged.connect(self._on_track_selection_changed_in_table)
        self._tracks_table.cellClicked.connect(self._on_tracks_table_cell_clicked)
        
        self._points_table.cellClicked.connect(self._on_points_table_cell_clicked)

        self._track_manager.trackListChanged.connect(self.update_tracks_table_ui)
        self._track_manager.activeTrackDataChanged.connect(self.update_points_table_ui)
        self._track_manager.activeTrackDataChanged.connect(self._sync_tracks_table_selection_with_manager) # New connection
        
        self._scale_manager.scaleOrUnitChanged.connect(self.update_points_table_ui)
        
    def set_video_loaded_status(self, is_loaded: bool, total_frames: int = 0) -> None:
        if self._video_loaded != is_loaded: 
            self._video_loaded = is_loaded
            self._total_frames_for_validation = total_frames if is_loaded else 0
            
            logger.debug(f"TrackDataViewController: video_loaded status changed to {is_loaded}. Updating tables.")
            self.update_tracks_table_ui() 
            self.update_points_table_ui()
        elif is_loaded and self._total_frames_for_validation != total_frames:
            self._total_frames_for_validation = total_frames
            logger.debug(f"TrackDataViewController: video_loaded status same, but total_frames changed. Updating tables.")
            self.update_tracks_table_ui()
            self.update_points_table_ui()

    def handle_visibility_header_clicked(self, logical_index: int) -> None:
        # MODIFIED: Check self._track_manager.elements
        if not self._track_manager.elements: return

        target_mode: Optional[TrackVisibilityMode] = None
        if logical_index == config.COL_VIS_HIDDEN: target_mode = TrackVisibilityMode.HIDDEN
        elif logical_index == config.COL_VIS_INCREMENTAL: target_mode = TrackVisibilityMode.INCREMENTAL
        elif logical_index == config.COL_VIS_ALWAYS: target_mode = TrackVisibilityMode.ALWAYS_VISIBLE

        if target_mode:
            logger.info(f"Controller: Setting all track-type elements visibility to {target_mode.name} via header click.")
            # MODIFIED: Pass element_type_filter
            self._track_manager.set_all_elements_visibility(target_mode, ElementType.TRACK)

    @QtCore.Slot()
    def _on_track_selection_changed_in_table(self) -> None:
        selected_items = self._tracks_table.selectedItems()
        if not selected_items:
            return

        selected_row = self._tracks_table.row(selected_items[0])
        id_item = self._tracks_table.item(selected_row, config.COL_TRACK_ID)
        if id_item:
            element_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole) # This is the element ID
            if element_id is not None and isinstance(element_id, int):
                # Find the element's current index in TrackManager.elements list
                element_index_in_manager = -1
                for idx, el in enumerate(self._track_manager.elements):
                    if el['id'] == element_id and el['type'] == ElementType.TRACK:
                        element_index_in_manager = idx
                        break
                
                if element_index_in_manager != -1:
                    # MODIFIED: Use active_element_index and set_active_element
                    if self._track_manager.active_element_index != element_index_in_manager:
                        logger.debug(f"Controller: Tracks table selection changed to row {selected_row}, element ID {element_id}. Setting active element.")
                        self._track_manager.set_active_element(element_index_in_manager)
                else:
                    logger.warning(f"Could not find element with ID {element_id} in TrackManager from table selection.")


    @QtCore.Slot(int, int)
    def _on_tracks_table_cell_clicked(self, row: int, column: int) -> None:
        if not self._video_loaded:
            return

        id_item = self._tracks_table.item(row, config.COL_TRACK_ID)
        if not id_item:
            logger.debug("TableController: Cell click on non-data row or invalid ID item.")
            return

        element_id_clicked = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(element_id_clicked, int):
            logger.warning(f"TableController: Invalid element_id data: {element_id_clicked}")
            return

        # Find element index in manager
        element_index_clicked = -1
        for idx, el in enumerate(self._track_manager.elements):
            if el['id'] == element_id_clicked and el['type'] == ElementType.TRACK:
                element_index_clicked = idx
                break
        
        if element_index_clicked == -1:
            logger.warning(f"TableController: Clicked element ID {element_id_clicked} not found in manager.")
            return

        current_modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_ctrl_click = (current_modifiers == QtCore.Qt.KeyboardModifier.ControlModifier)
        # MODIFIED: Use active_element_index
        is_active_element_in_manager = (element_index_clicked == self._track_manager.active_element_index)

        if is_ctrl_click:
            if is_active_element_in_manager:
                logger.info(f"TableController: Ctrl+Clicked on active element {element_id_clicked}. Deselecting.")
                # MODIFIED: Use set_active_element
                self._track_manager.set_active_element(-1)
                return 
            else:
                logger.info(f"TableController: Ctrl+Clicked on non-active element {element_id_clicked}. Selecting.")
                # MODIFIED: Use active_element_index and set_active_element
                if self._track_manager.active_element_index != element_index_clicked:
                    self._track_manager.set_active_element(element_index_clicked)
                return 
        
        if column == config.COL_TRACK_START_FRAME or column == config.COL_TRACK_END_FRAME:
            frame_item_widget = self._tracks_table.item(row, column)
            if frame_item_widget:
                frame_text = frame_item_widget.text()
                try:
                    target_frame_0based = int(frame_text) - 1
                    if 0 <= target_frame_0based < self._total_frames_for_validation:
                        logger.debug(f"TableController: Frame link clicked for element {element_id_clicked}. Emitting seekVideoToFrame({target_frame_0based})")
                        self.seekVideoToFrame.emit(target_frame_0based)
                except (ValueError, TypeError):
                    logger.warning(f"TableController: Could not parse frame number: '{frame_text}'")
        
        logger.debug(f"TableController: Normal cell ({row},{column}) click on element {element_id_clicked}.")


    @QtCore.Slot()
    def _sync_tracks_table_selection_with_manager(self) -> None:
        if not hasattr(self, '_track_manager') or not hasattr(self, '_tracks_table'):
            logger.warning("TrackDataViewController: Cannot sync selection, manager or table missing.")
            return

        # MODIFIED: Use get_active_element_id
        active_id = self._track_manager.get_active_element_id() 
        logger.debug(f"TrackDataViewController: Syncing tracks table selection to manager's active ID: {active_id}")
        self._select_element_row_by_id_in_ui(active_id)


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

    @QtCore.Slot(int) # Parameter is element_index
    def _on_delete_element_button_clicked_in_table(self, element_index: int) -> None:
        # MODIFIED: element_index is now the direct index in self.elements
        if not (0 <= element_index < len(self._track_manager.elements)):
            logger.error(f"Delete button clicked for invalid element index: {element_index}")
            return

        element_to_delete = self._track_manager.elements[element_index]
        element_id = element_to_delete['id']
        element_type_name = element_to_delete['type'].name.replace("_", " ").title() # "Track" or "Measurement Line"

        reply = QtWidgets.QMessageBox.question(self._main_window_ref, f"Confirm Delete {element_type_name}", 
                                             f"Delete {element_type_name} {element_id}?",
                                             QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
                                             QtWidgets.QMessageBox.StandardButton.Cancel)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            logger.info(f"Controller: User confirmed deletion for element index {element_index} (ID: {element_id}).")
            # MODIFIED: Call delete_element_by_index
            success = self._track_manager.delete_element_by_index(element_index)
            msg = f"Deleted {element_type_name} {element_id}" if success else f"Failed to delete {element_type_name} {element_id}"
            self.statusBarMessage.emit(msg, 3000)
            if not success:
                logger.error(f"Controller: TrackManager failed to delete element index {element_index}.")
                QtWidgets.QMessageBox.warning(self._main_window_ref, "Delete Error", f"Could not delete {element_type_name} {element_id}.")
            self.updateMainWindowUIState.emit()


    @QtCore.Slot(QtWidgets.QAbstractButton, bool)
    def _on_visibility_changed_in_table(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        if checked:
            mode = button.property("visibility_mode")
            # MODIFIED: property is now "element_index"
            element_index = button.property("element_index") 
            if isinstance(mode, TrackVisibilityMode) and isinstance(element_index, int):
                # MODIFIED: Call set_element_visibility_mode
                logger.debug(f"Controller: Visibility changed for element index {element_index} to {mode.name}")
                self._track_manager.set_element_visibility_mode(element_index, mode)


    def _clear_internal_visibility_button_groups(self) -> None:
        # MODIFIED: Use _element_visibility_button_groups
        for group in self._element_visibility_button_groups.values():
            try:
                group.buttonToggled.disconnect(self._on_visibility_changed_in_table)
            except (TypeError, RuntimeError): pass 
        self._element_visibility_button_groups.clear()

    # MODIFIED: Renamed for clarity
    def _select_element_row_by_id_in_ui(self, element_id_to_select: int) -> None:
         if element_id_to_select == -1:
              self._tracks_table.clearSelection()
              return
         found_row = -1
         # Iterate only up to num_data_rows for actual element data
         num_data_rows = self._tracks_table.rowCount() -1 # Exclude button row if present
         for row_idx in range(num_data_rows):
              item = self._tracks_table.item(row_idx, config.COL_TRACK_ID)
              if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == element_id_to_select:
                  # Also ensure it's a TRACK type element if this table is strictly for tracks
                  # For Phase 1, get_track_elements_summary will only return tracks, so this check might be redundant
                  # but good for future-proofing if the table starts showing other element types.
                  # element_in_manager = next((el for el_idx, el in enumerate(self._track_manager.elements) if el['id'] == element_id_to_select), None)
                  # if element_in_manager and element_in_manager['type'] == ElementType.TRACK:
                  found_row = row_idx
                  break
         if found_row != -1:
             self._tracks_table.blockSignals(True)
             self._tracks_table.selectRow(found_row)
             self._tracks_table.blockSignals(False)
             if item: self._tracks_table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
         else:
             # This can happen if the active element in TrackManager is not a TRACK type element,
             # or if the element list is empty/ID not found.
             self._tracks_table.clearSelection() # Ensure no invalid selection is shown
             logger.debug(f"Controller: Could not find row for element ID {element_id_to_select} (or it's not a Track) in tracks table.")


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
        # MODIFIED: Use get_active_element_id
        current_active_element_id = self._track_manager.get_active_element_id()
        selected_row_to_restore = -1

        previous_track_count = 0
        for r in range(self._tracks_table.rowCount() -1): # -1 for button row
            id_item = self._tracks_table.item(r, config.COL_TRACK_ID)
            if id_item and id_item.data(QtCore.Qt.ItemDataRole.UserRole) is not None:
                previous_track_count +=1


        self._tracks_table.blockSignals(True)
        self._clear_internal_visibility_button_groups()

        # MODIFIED: get_track_elements_summary now filters for TRACK type elements
        track_summary_list = self._track_manager.get_track_elements_summary()
        num_data_rows = len(track_summary_list)
        total_rows = num_data_rows + 1 # +1 for the "New Track" button row
        self._tracks_table.setRowCount(total_rows)

        link_color = QtGui.QColor("blue")
        link_tooltip = "Click to jump to this frame"
        style = self._main_window_ref.style() 

        for row_idx in range(num_data_rows):
            self._tracks_table.setSpan(row_idx, 0, 1, 1) # Keep span for delete button column
            
            # MODIFIED: Summary now returns (element_id, num_points, start_frame, end_frame)
            element_id, num_points, start_frame, end_frame = track_summary_list[row_idx]
            
            # Find the element's current index in the TrackManager.elements list
            element_index_in_manager = -1
            for idx, el_dict in enumerate(self._track_manager.elements):
                if el_dict['id'] == element_id and el_dict['type'] == ElementType.TRACK:
                    element_index_in_manager = idx
                    break
            
            if element_index_in_manager == -1: # Should not happen if summary is correct
                logger.error(f"Could not find element ID {element_id} in TrackManager during table update.")
                continue

            delete_button = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon), "")
            delete_button.setToolTip(f"Delete Track {element_id}"); delete_button.setFlat(True); delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            # MODIFIED: Pass element_index_in_manager to delete handler
            delete_button.setProperty("element_index", element_index_in_manager) 
            delete_button.clicked.connect(lambda checked=False, el_idx=element_index_in_manager: self._on_delete_element_button_clicked_in_table(el_idx))
            self._tracks_table.setCellWidget(row_idx, config.COL_DELETE, self._create_centered_cell_widget_for_table(delete_button))

            id_item = QtWidgets.QTableWidgetItem(str(element_id))
            # MODIFIED: Store element_id as UserRole data
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

            # MODIFIED: Use element_index_in_manager for visibility
            current_mode = self._track_manager.get_element_visibility_mode(element_index_in_manager)
            rb_hidden = QtWidgets.QRadioButton(); rb_incremental = QtWidgets.QRadioButton(); rb_always = QtWidgets.QRadioButton()
            
            rb_hidden.setProperty("visibility_mode", TrackVisibilityMode.HIDDEN); rb_hidden.setProperty("element_index", element_index_in_manager)
            rb_incremental.setProperty("visibility_mode", TrackVisibilityMode.INCREMENTAL); rb_incremental.setProperty("element_index", element_index_in_manager)
            rb_always.setProperty("visibility_mode", TrackVisibilityMode.ALWAYS_VISIBLE); rb_always.setProperty("element_index", element_index_in_manager)
            
            button_group = QtWidgets.QButtonGroup(self) # Parent 'self' should be okay
            button_group.addButton(rb_hidden); button_group.addButton(rb_incremental); button_group.addButton(rb_always)
            button_group.setExclusive(True)
            # MODIFIED: Key for button group dict by element_id
            self._element_visibility_button_groups[element_id] = button_group 
            
            button_group.blockSignals(True)
            if current_mode == TrackVisibilityMode.HIDDEN: rb_hidden.setChecked(True)
            elif current_mode == TrackVisibilityMode.INCREMENTAL: rb_incremental.setChecked(True)
            else: rb_always.setChecked(True) # default or ALWAYS_VISIBLE
            button_group.blockSignals(False)
            
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_HIDDEN, self._create_centered_cell_widget_for_table(rb_hidden))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_INCREMENTAL, self._create_centered_cell_widget_for_table(rb_incremental))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_ALWAYS, self._create_centered_cell_widget_for_table(rb_always))
            button_group.buttonToggled.connect(self._on_visibility_changed_in_table)

            if element_id == current_active_element_id:
                selected_row_to_restore = row_idx

        # "New Track" button row
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
        else: # If no active element or active element not in summary, clear selection
            self._tracks_table.clearSelection()

        self._tracks_table.blockSignals(False)

        if num_data_rows != previous_track_count:
            logger.debug("Track count changed, emitting updateMainWindowUIState.")
            self.updateMainWindowUIState.emit()


    @QtCore.Slot()
    def update_points_table_ui(self) -> None:
        logger.debug("TrackDataViewController: Updating points table UI (now element-aware)...")
        # MODIFIED: get_active_element_id and get_active_element_type
        active_element_id = self._track_manager.get_active_element_id()
        active_element_type = self._track_manager.get_active_element_type()

        # Only display points if the active element is a TRACK
        if active_element_type == ElementType.TRACK and active_element_id != -1:
            self._points_tab_label.setText(f"Points for Track: {active_element_id}")
            # MODIFIED: get_active_element_points_if_track ensures it's for a track
            active_points = self._track_manager.get_active_element_points_if_track()
        else:
            self._points_tab_label.setText("Points for Track: -")
            active_points = [] # Clear points if not a track or no active element

        self._points_table.setRowCount(0) # Clear previous points

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

            frame_item = QtWidgets.QTableWidgetItem(str(frame_idx + 1)) # 1-based for display
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