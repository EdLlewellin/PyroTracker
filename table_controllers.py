# table_controllers.py
"""
Contains controller classes for managing UI logic for data tables
(Tracks and Points tables) in the MainWindow.
"""
import logging
from typing import Optional, TYPE_CHECKING, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets

import config # For table column constants
from track_manager import TrackVisibilityMode # For setting visibility

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

        self._main_window_ref = main_window_ref # Keep a reference for specific needs
        self._track_manager = track_manager
        self._video_handler = video_handler
        self._scale_manager = scale_manager
        self._coord_transformer = coord_transformer
        self._tracks_table = tracks_table_widget
        self._points_table = points_table_widget
        self._points_tab_label = points_tab_label

        self._track_visibility_button_groups: Dict[int, QtWidgets.QButtonGroup] = {}
        self._video_loaded: bool = False # Internal state

        # Connect signals from UI elements to controller slots
        self._tracks_table.itemSelectionChanged.connect(self._on_track_selection_changed_in_table)
        self._tracks_table.cellClicked.connect(self._on_tracks_table_cell_clicked)
        # Note: Visibility header click is connected from ui_setup to MainWindow,
        # which will then call a method on this controller.
        # Delete buttons are connected dynamically in _update_tracks_table.

        self._points_table.cellClicked.connect(self._on_points_table_cell_clicked)

        # Connect signals from managers to controller slots for UI updates
        self._track_manager.trackListChanged.connect(self.update_tracks_table_ui)
        self._track_manager.activeTrackDataChanged.connect(self.update_points_table_ui)
        
        # Points table also needs to update if coordinate system or scale/units change
        self._scale_manager.scaleOrUnitChanged.connect(self.update_points_table_ui)
        # If CoordinatePanelController emits a signal for coord system changes, connect it here too
        # (Alternative: MainWindow can directly call update_points_table_ui on this controller)

    def set_video_loaded_status(self, is_loaded: bool, total_frames: int = 0) -> None:
        """Updates the controller's knowledge of video load status and updates tables
           ONLY if the loaded status actually changes, or if tables need explicit update."""
        if self._video_loaded != is_loaded: # Only update if status changes
            self._video_loaded = is_loaded
            self._total_frames_for_validation = total_frames if is_loaded else 0
            
            logger.debug(f"TrackDataViewController: video_loaded status changed to {is_loaded}. Updating tables.")
            # Update tables to reflect new video state (e.g., clear or enable 'New Track')
            self.update_tracks_table_ui() 
            self.update_points_table_ui()
        # If is_loaded state hasn't changed, but we still might need to update (e.g. total_frames change)
        elif is_loaded and self._total_frames_for_validation != total_frames:
            self._total_frames_for_validation = total_frames
            # Tables might not need full rebuild, but underlying data for validation changed.
            # For now, let's assume a full rebuild on video load is acceptable.
            logger.debug(f"TrackDataViewController: video_loaded status same, but total_frames changed. Updating tables.")
            self.update_tracks_table_ui()
            self.update_points_table_ui()

    def handle_visibility_header_clicked(self, logical_index: int) -> None:
        """Handles clicks on the visibility column headers to set mode for all tracks."""
        if not self._track_manager.tracks: return

        target_mode: Optional[TrackVisibilityMode] = None
        if logical_index == config.COL_VIS_HIDDEN: target_mode = TrackVisibilityMode.HIDDEN
        elif logical_index == config.COL_VIS_INCREMENTAL: target_mode = TrackVisibilityMode.INCREMENTAL
        elif logical_index == config.COL_VIS_ALWAYS: target_mode = TrackVisibilityMode.ALWAYS_VISIBLE

        if target_mode:
            logger.info(f"Controller: Setting all tracks visibility to {target_mode.name} via header click.")
            self._track_manager.set_all_tracks_visibility(target_mode)
            # TrackManager signals will trigger table/visual updates via connected slots.

    @QtCore.Slot()
    def _on_track_selection_changed_in_table(self) -> None:
        """Handles selection changes initiated *by the user* in the tracks table."""
        selected_items = self._tracks_table.selectedItems()
        if not selected_items:
            return

        selected_row = self._tracks_table.row(selected_items[0])
        id_item = self._tracks_table.item(selected_row, config.COL_TRACK_ID)
        if id_item:
            track_id = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if track_id is not None and isinstance(track_id, int):
                track_index = track_id - 1
                if self._track_manager.active_track_index != track_index:
                    logger.debug(f"Controller: Tracks table selection changed by user to row {selected_row}, track ID {track_id}.")
                    self._track_manager.set_active_track(track_index)
                    # TrackManager signals activeTrackDataChanged, which updates points table.


    @QtCore.Slot(int, int)
    def _on_tracks_table_cell_clicked(self, row: int, column: int) -> None:
        if not self._video_loaded:
            return

        id_item = self._tracks_table.item(row, config.COL_TRACK_ID)
        if not id_item:
            logger.debug("TableController: Cell click on non-data row or invalid ID item.")
            return

        track_id_clicked = id_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(track_id_clicked, int):
            logger.warning(f"TableController: Invalid track_id data: {track_id_clicked}")
            return

        track_index_clicked = track_id_clicked - 1
        current_modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_ctrl_click = (current_modifiers == QtCore.Qt.KeyboardModifier.ControlModifier)
        is_active_row_in_manager = (track_index_clicked == self._track_manager.active_track_index)

        if is_ctrl_click:
            if is_active_row_in_manager:
                # Ctrl+Click on an active row: DESELECT
                logger.info(f"TableController: Ctrl+Clicked on active track {track_id_clicked}. Deselecting.")
                self._track_manager.set_active_track(-1)
                # UI sync (via activeTrackDataChanged signal) will clear table selection.
                return # Action handled
            else:
                # Ctrl+Click on a NON-ACTIVE row: We want to SELECT it.
                # Directly set the TrackManager state and let UI sync.
                # This prevents the table's default Ctrl+click processing which might be causing the select/deselect.
                logger.info(f"TableController: Ctrl+Clicked on non-active track {track_id_clicked}. Selecting.")
                if self._track_manager.active_track_index != track_index_clicked:
                    self._track_manager.set_active_track(track_index_clicked)
                # If it was already selected but not active in manager (should not happen with sync),
                # this also makes it active.
                # The activeTrackDataChanged signal will trigger UI sync.
                return # Action handled
        
        # If we reach here, it's a NORMAL click (no Ctrl modifier).
        # Also handle frame link clicks here. The table's default selection will still occur for the row.
        if column == config.COL_TRACK_START_FRAME or column == config.COL_TRACK_END_FRAME:
            frame_item_widget = self._tracks_table.item(row, column)
            if frame_item_widget:
                frame_text = frame_item_widget.text()
                try:
                    target_frame_0based = int(frame_text) - 1
                    if 0 <= target_frame_0based < self._total_frames_for_validation:
                        logger.debug(f"TableController: Frame link clicked for track {track_id_clicked}. "
                                     f"Emitting seekVideoToFrame({target_frame_0based})")
                        self.seekVideoToFrame.emit(target_frame_0based)
                        # Selection change will be handled by itemSelectionChanged if row changes
                except (ValueError, TypeError):
                    logger.warning(f"TableController: Could not parse frame number: '{frame_text}'")
            # Allow fall-through for itemSelectionChanged to handle the row selection itself

        # For normal clicks, rely on QTableWidget's default selection behavior,
        # which emits itemSelectionChanged, then _on_track_selection_changed_in_table updates TrackManager.
        logger.debug(f"TableController: Normal cell ({row},{column}) click on track {track_id_clicked}. "
                     "Default selection processing (via itemSelectionChanged) will follow if not a frame link.")


    @QtCore.Slot()
    def _sync_tracks_table_selection_with_manager(self) -> None:
        """
        Ensures the tracks table's visual selection matches the TrackManager's active track.
        This is typically called when TrackManager.activeTrackDataChanged is emitted.
        """
        if not hasattr(self, '_track_manager') or not hasattr(self, '_tracks_table'): # Ensure components exist
            logger.warning("TrackDataViewController: Cannot sync selection, manager or table missing.")
            return

        active_id = self._track_manager.get_active_track_id()
        logger.debug(f"TrackDataViewController: Syncing tracks table selection to manager's active ID: {active_id}")
        self._select_track_row_by_id_in_ui(active_id)


    @QtCore.Slot(int, int)
    def _on_points_table_cell_clicked(self, row: int, column: int) -> None:
        """Handles clicks on specific cells in the points table (e.g., frame links)."""
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

    @QtCore.Slot()
    def _on_delete_track_button_clicked_in_table(self, track_index: int) -> None:
        """Handles the click signal from a track's delete button within the tracks table."""
        track_id = track_index + 1
        reply = QtWidgets.QMessageBox.question(self._main_window_ref, "Confirm Delete", f"Delete Track {track_id}?",
                                             QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
                                             QtWidgets.QMessageBox.StandardButton.Cancel)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            logger.info(f"Controller: User confirmed deletion for track index {track_index} (ID: {track_id}).")
            success = self._track_manager.delete_track(track_index)
            msg = f"Deleted Track {track_id}" if success else f"Failed to delete Track {track_id}"
            self.statusBarMessage.emit(msg, 3000)
            if not success:
                logger.error(f"Controller: TrackManager failed to delete track index {track_index}.")
                QtWidgets.QMessageBox.warning(self._main_window_ref, "Delete Error", f"Could not delete track {track_id}.")
            # TrackManager signals will trigger table updates and potentially UI state update.
            self.updateMainWindowUIState.emit()


    @QtCore.Slot(QtWidgets.QAbstractButton, bool)
    def _on_visibility_changed_in_table(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        """Handles the buttonToggled signal from visibility radio button groups in the tracks table."""
        if checked:
            mode = button.property("visibility_mode")
            track_index = button.property("track_index")
            if isinstance(mode, TrackVisibilityMode) and isinstance(track_index, int):
                logger.debug(f"Controller: Visibility changed for track index {track_index} to {mode.name}")
                self._track_manager.set_track_visibility_mode(track_index, mode)
                # TrackManager signals visualsNeedUpdate, which MainWindow is connected to.

    def _clear_internal_visibility_button_groups(self) -> None:
        """Disconnects signals and clears the stored visibility button groups."""
        for group in self._track_visibility_button_groups.values():
            try:
                group.buttonToggled.disconnect(self._on_visibility_changed_in_table)
            except (TypeError, RuntimeError): pass # Safely ignore if already disconnected
        self._track_visibility_button_groups.clear()

    def _select_track_row_by_id_in_ui(self, track_id_to_select: int) -> None:
         """Selects the row in the tracks table corresponding to the given track ID."""
         if track_id_to_select == -1:
              self._tracks_table.clearSelection()
              return
         found_row = -1
         for row_idx in range(self._tracks_table.rowCount() -1 ): # Exclude button row
              item = self._tracks_table.item(row_idx, config.COL_TRACK_ID)
              if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == track_id_to_select:
                  found_row = row_idx
                  break
         if found_row != -1:
             self._tracks_table.blockSignals(True)
             self._tracks_table.selectRow(found_row)
             self._tracks_table.blockSignals(False)
             if item: self._tracks_table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
         else:
             logger.warning(f"Controller: Could not find row for track ID {track_id_to_select} in tracks table.")

    def _create_centered_cell_widget_for_table(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Helper to create a container widget to center another widget within a table cell."""
        cell_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(cell_widget)
        layout.addWidget(widget)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        return cell_widget

    @QtCore.Slot()
    def update_tracks_table_ui(self) -> None:
        """Updates the tracks table UI based on data from TrackManager."""
        logger.debug("TrackDataViewController: Updating tracks table UI...")
        current_active_id = self._track_manager.get_active_track_id()
        selected_row_to_restore = -1

        # Store previous track count to see if we need to signal MainWindow for UI state update
        previous_track_count = self._tracks_table.rowCount() -1 # Exclude button row

        self._tracks_table.blockSignals(True)
        self._clear_internal_visibility_button_groups()

        track_summary = self._track_manager.get_track_summary()
        num_data_rows = len(track_summary)
        total_rows = num_data_rows + 1
        self._tracks_table.setRowCount(total_rows)

        link_color = QtGui.QColor("blue")
        link_tooltip = "Click to jump to this frame"
        style = self._main_window_ref.style() # Use the main_window_ref for style

        for row_idx in range(num_data_rows):
            self._tracks_table.setSpan(row_idx, 0, 1, 1)
            track_id, num_points, start_frame, end_frame = track_summary[row_idx]
            track_index = track_id - 1

            delete_button = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon), "")
            delete_button.setToolTip(f"Delete Track {track_id}"); delete_button.setFlat(True); delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            delete_button.setProperty("track_index", track_index)
            delete_button.clicked.connect(lambda checked=False, t_idx=track_index: self._on_delete_track_button_clicked_in_table(t_idx))
            self._tracks_table.setCellWidget(row_idx, config.COL_DELETE, self._create_centered_cell_widget_for_table(delete_button))

            id_item = QtWidgets.QTableWidgetItem(str(track_id))
            id_item.setData(QtCore.Qt.ItemDataRole.UserRole, track_id)
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

            current_mode = self._track_manager.get_track_visibility_mode(track_index)
            rb_hidden = QtWidgets.QRadioButton(); rb_incremental = QtWidgets.QRadioButton(); rb_always = QtWidgets.QRadioButton()
            rb_hidden.setProperty("visibility_mode", TrackVisibilityMode.HIDDEN); rb_hidden.setProperty("track_index", track_index)
            rb_incremental.setProperty("visibility_mode", TrackVisibilityMode.INCREMENTAL); rb_incremental.setProperty("track_index", track_index)
            rb_always.setProperty("visibility_mode", TrackVisibilityMode.ALWAYS_VISIBLE); rb_always.setProperty("track_index", track_index)
            
            button_group = QtWidgets.QButtonGroup(self)
            button_group.addButton(rb_hidden); button_group.addButton(rb_incremental); button_group.addButton(rb_always)
            button_group.setExclusive(True)
            self._track_visibility_button_groups[track_id] = button_group
            
            button_group.blockSignals(True)
            if current_mode == TrackVisibilityMode.HIDDEN: rb_hidden.setChecked(True)
            elif current_mode == TrackVisibilityMode.INCREMENTAL: rb_incremental.setChecked(True)
            else: rb_always.setChecked(True)
            button_group.blockSignals(False)
            
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_HIDDEN, self._create_centered_cell_widget_for_table(rb_hidden))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_INCREMENTAL, self._create_centered_cell_widget_for_table(rb_incremental))
            self._tracks_table.setCellWidget(row_idx, config.COL_VIS_ALWAYS, self._create_centered_cell_widget_for_table(rb_always))
            button_group.buttonToggled.connect(self._on_visibility_changed_in_table)

            if track_id == current_active_id:
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
        self._tracks_table.blockSignals(False)

        # Only emit updateMainWindowUIState if the number of actual data tracks changed,
        # as this primarily affects the 'Save' button state.
        if num_data_rows != previous_track_count:
            logger.debug("Track count changed, emitting updateMainWindowUIState.")
            self.updateMainWindowUIState.emit()
        else:
            # If only selection or visibility changed, main window UI state (like save button)
            # probably doesn't need a full re-evaluation from this specific table update.
            # Other actions (delete, new track) will emit this signal themselves.
            pass

    @QtCore.Slot()
    def update_points_table_ui(self) -> None:
        """Updates the points table UI based on the currently active track and display settings."""
        logger.debug("TrackDataViewController: Updating points table UI...")
        active_track_id = self._track_manager.get_active_track_id()
        self._points_tab_label.setText(f"Points for Track: {active_track_id}" if active_track_id != -1 else "Points for Track: -")
        self._points_table.setRowCount(0)
        active_points = self._track_manager.get_active_track_points_for_table()

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