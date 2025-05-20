# export_options_dialog.py
import logging
import math
import re
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

# Assuming ExportResolutionMode will be (or is) defined in export_handler.py
# If it's not yet, we can define it here temporarily or wait until export_handler.py is modified.
# For now, let's assume it will be available from where it's currently defined (export_handler.py)
from export_handler import ExportResolutionMode

logger = logging.getLogger(__name__)

class ExportOptionsDialog(QtWidgets.QDialog):
    def __init__(self,
                 total_frames: int,
                 fps: float,
                 current_frame_idx: int, # For defaulting start frame
                 video_frame_width: int, # For displaying original resolution
                 video_frame_height: int, # For displaying original resolution
                 parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Export Options")
        self.setModal(True)
        self.setMinimumWidth(500) # Adjusted minimum width

        self._total_frames = total_frames
        self._fps = fps if fps > 0 else 30.0 # Use a sensible default if FPS is invalid
        self._total_duration_ms = (self._total_frames / self._fps) * 1000 if self._fps > 0 and self._total_frames > 0 else 0.0
        self._current_frame_idx_0_based = current_frame_idx # 0-based

        self._video_frame_width = video_frame_width
        self._video_frame_height = video_frame_height

        # --- Internal state for selected values ---
        self._export_full_video: bool = True
        # Default to full range (0-based internally)
        self._start_frame_0_based: int = 0
        self._end_frame_0_based: int = self._total_frames - 1 if self._total_frames > 0 else 0
        self._resolution_mode: ExportResolutionMode = ExportResolutionMode.VIEWPORT

        # Flags to prevent signal feedback loops
        self._is_updating_fields_programmatically: bool = False

        self._setup_ui()
        self._connect_signals()
        
        # Initial population and UI state update
        self._update_ui_from_internal_state()

        logger.debug(f"ExportOptionsDialog initialized. Total frames: {self._total_frames}, FPS: {self._fps:.2f}")


    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # --- Export Range Section ---
        range_group_box = QtWidgets.QGroupBox("Export Range")
        range_layout = QtWidgets.QVBoxLayout(range_group_box)

        self.fullVideoRadioButton = QtWidgets.QRadioButton("Full Video")
        self.fullVideoRadioButton.setChecked(self._export_full_video)
        range_layout.addWidget(self.fullVideoRadioButton)

        self.customRangeRadioButton = QtWidgets.QRadioButton("Custom Range")
        self.customRangeRadioButton.setChecked(not self._export_full_video)
        range_layout.addWidget(self.customRangeRadioButton)

        self.customRangeInputsWidget = QtWidgets.QWidget()
        custom_inputs_form_layout = QtWidgets.QFormLayout(self.customRangeInputsWidget)
        custom_inputs_form_layout.setContentsMargins(10, 5, 5, 5)
        custom_inputs_form_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        custom_inputs_form_layout.setHorizontalSpacing(10)
        custom_inputs_form_layout.setVerticalSpacing(8)

        # --- Frame Inputs ---
        frame_input_h_layout = QtWidgets.QHBoxLayout()
        self.startFrameInput = QtWidgets.QLineEdit()
        self.startFrameInput.setValidator(QtGui.QIntValidator(1, self._total_frames if self._total_frames > 0 else 1, self))
        self.startFrameInput.setToolTip(f"Enter start frame (1 to {self._total_frames})")
        self.startFrameInput.setObjectName("startFrameInput")
        self.endFrameInput = QtWidgets.QLineEdit()
        self.endFrameInput.setValidator(QtGui.QIntValidator(1, self._total_frames if self._total_frames > 0 else 1, self))
        self.endFrameInput.setToolTip(f"Enter end frame (1 to {self._total_frames})")
        self.endFrameInput.setObjectName("endFrameInput")
        self.durationFrameDisplayLabel = QtWidgets.QLabel("Duration: --- frames")
        
        frame_input_h_layout.addWidget(QtWidgets.QLabel("Start:"))
        frame_input_h_layout.addWidget(self.startFrameInput)
        frame_input_h_layout.addSpacing(10)
        frame_input_h_layout.addWidget(QtWidgets.QLabel("End:"))
        frame_input_h_layout.addWidget(self.endFrameInput)
        frame_input_h_layout.addSpacing(10)
        frame_input_h_layout.addWidget(self.durationFrameDisplayLabel)
        frame_input_h_layout.addStretch()
        custom_inputs_form_layout.addRow("Frames:", frame_input_h_layout)

        # --- Time Inputs ---
        time_input_h_layout = QtWidgets.QHBoxLayout()
        self.startTimeInput = QtWidgets.QLineEdit()
        self.startTimeInput.setToolTip("Enter start time (MM:SS.mmm or SSS.mmm)")
        self.startTimeInput.setObjectName("startTimeInput")
        self.endTimeInput = QtWidgets.QLineEdit()
        self.endTimeInput.setToolTip("Enter end time (MM:SS.mmm or SSS.mmm)")
        self.endTimeInput.setObjectName("endTimeInput")
        self.durationTimeDisplayLabel = QtWidgets.QLabel("Duration: --:--.---")

        time_input_h_layout.addWidget(QtWidgets.QLabel("Start:"))
        time_input_h_layout.addWidget(self.startTimeInput)
        time_input_h_layout.addSpacing(10)
        time_input_h_layout.addWidget(QtWidgets.QLabel("End:"))
        time_input_h_layout.addWidget(self.endTimeInput)
        time_input_h_layout.addSpacing(10)
        time_input_h_layout.addWidget(self.durationTimeDisplayLabel)
        time_input_h_layout.addStretch()
        custom_inputs_form_layout.addRow("Time:", time_input_h_layout)
        
        # --- Buttons to set Start/End from Current Video Position ---
        # This QHBoxLayout will contain two buttons, intended to align under Start and End columns
        set_points_button_layout = QtWidgets.QHBoxLayout()
        set_points_button_layout.setContentsMargins(0, 0, 0, 0) # No extra margins for this layout

        self.setStartFromCurrentButton = QtWidgets.QPushButton("Set From Current") # Shortened Text
        self.setStartFromCurrentButton.setToolTip("Set start point (frame and time) to current video position")
        
        self.setEndFromCurrentButton = QtWidgets.QPushButton("Set From Current") # Shortened Text
        self.setEndFromCurrentButton.setToolTip("Set end point (frame and time) to current video position")
        
        # Attempt to align: Add a spacer that roughly matches the width of "Frames:"/"Time:" label + "Start:" label
        # This is an approximation and might need tweaking or a more complex layout for perfection.
        # The QFormLayout's label column width can vary.
        # We'll use a stretch factor for the space before the first button,
        # then space between buttons, then stretch factor for space after the last button.
        
        # To better control alignment, we can fix the width of the QLineEdit fields if they don't already have one
        # For example:
        # self.startFrameInput.setFixedWidth(80)
        # self.endFrameInput.setFixedWidth(80)
        # self.startTimeInput.setFixedWidth(100)
        # self.endTimeInput.setFixedWidth(100)
        # Then adjust spacers accordingly. Let's try without fixed widths first.

        spacer_width_for_label_plus_start_label = 70 # Approximate, adjust as needed
        set_points_button_layout.addSpacing(spacer_width_for_label_plus_start_label) 
        set_points_button_layout.addWidget(self.setStartFromCurrentButton)
        set_points_button_layout.addStretch(1) # Stretch between buttons
        set_points_button_layout.addWidget(self.setEndFromCurrentButton)
        set_points_button_layout.addStretch(2) # More stretch to push to the right of duration
        
        # Add this layout as a new row in the form layout, spanning the field column
        custom_inputs_form_layout.addRow(set_points_button_layout)

        range_layout.addWidget(self.customRangeInputsWidget)
        main_layout.addWidget(range_group_box)

        # --- Resolution Section ---
        resolution_group_box = QtWidgets.QGroupBox("Export Resolution")
        resolution_layout = QtWidgets.QVBoxLayout(resolution_group_box)
        self.viewportResRadioButton = QtWidgets.QRadioButton("Current Viewport Resolution")
        self.viewportResRadioButton.setToolTip("Export at the resolution of the current view in the application.")
        self.originalResRadioButton = QtWidgets.QRadioButton(f"Original Video Resolution ({self._video_frame_width}x{self._video_frame_height})")
        self.originalResRadioButton.setToolTip(f"Export at the video's original {self._video_frame_width}x{self._video_frame_height} resolution.")

        if not (self._video_frame_width > 0 and self._video_frame_height > 0):
            self.originalResRadioButton.setEnabled(False)
            self.originalResRadioButton.setText("Original Video Resolution (N/A)")
            self.originalResRadioButton.setToolTip("Original video resolution is not available.")
            self.viewportResRadioButton.setChecked(True)
            self._resolution_mode = ExportResolutionMode.VIEWPORT
        else:
             if self._resolution_mode == ExportResolutionMode.VIEWPORT:
                self.viewportResRadioButton.setChecked(True)
             else:
                self.originalResRadioButton.setChecked(True)

        resolution_layout.addWidget(self.viewportResRadioButton)
        resolution_layout.addWidget(self.originalResRadioButton)
        main_layout.addWidget(resolution_group_box)

        # --- Dialog Buttons ---
        self.buttonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        export_button = self.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        export_button.setText("Export")
        export_button.setAutoDefault(True)
        main_layout.addWidget(self.buttonBox)
    def _connect_signals(self):
        self.fullVideoRadioButton.toggled.connect(self._on_range_type_changed)
        
        self.startFrameInput.editingFinished.connect(self._on_start_frame_input_changed)
        self.endFrameInput.editingFinished.connect(self._on_end_frame_input_changed)
        self.startTimeInput.editingFinished.connect(self._on_start_time_input_changed)
        self.endTimeInput.editingFinished.connect(self._on_end_time_input_changed)

        self.startFrameInput.installEventFilter(self)
        self.endFrameInput.installEventFilter(self)
        self.startTimeInput.installEventFilter(self)
        self.endTimeInput.installEventFilter(self)

        # Connect the new "Set Current" buttons
        self.setStartFromCurrentButton.clicked.connect(self._set_start_from_current_video_pos)
        self.setEndFromCurrentButton.clicked.connect(self._set_end_from_current_video_pos)

        self.viewportResRadioButton.toggled.connect(self._on_resolution_changed)
        self.originalResRadioButton.toggled.connect(self._on_resolution_changed) 

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _format_time_ms(self, ms: float) -> str:
        if ms < 0: return "--:--.---"
        try:
            s_total, mils = divmod(round(ms), 1000) # Use round on ms for more accurate display of .999 etc.
            m, s = divmod(int(s_total), 60)
            return f"{m:02d}:{s:02d}.{int(mils):03d}"
        except Exception:
            return "--:--.---"

    def _parse_time_str_to_ms(self, time_str: str) -> Optional[float]:
        time_str = time_str.strip()
        total_ms: Optional[float] = None
        match_mm_ss_mmm = re.fullmatch(r"(\d+):([0-5]?\d)\.?(\d{1,3})?", time_str)
        if match_mm_ss_mmm:
            try:
                m = int(match_mm_ss_mmm.group(1))
                s = int(match_mm_ss_mmm.group(2))
                ms_str = match_mm_ss_mmm.group(3) if match_mm_ss_mmm.group(3) else "0"
                ms = int(ms_str.ljust(3, '0')) # Pad to 3 digits
                if 0 <= s < 60 and 0 <= ms < 1000: total_ms = (m * 60 + s) * 1000 + ms
            except ValueError: total_ms = None
        if total_ms is None:
            match_ss_mmm = re.fullmatch(r"(\d+)\.?(\d{1,3})?", time_str)
            if match_ss_mmm:
                try:
                    s = int(match_ss_mmm.group(1))
                    ms_str = match_ss_mmm.group(2) if match_ss_mmm.group(2) else "0"
                    ms = int(ms_str.ljust(3, '0'))
                    if 0 <= ms < 1000: total_ms = s * 1000 + ms
                except ValueError: total_ms = None
        return total_ms
        
    def _frame_to_ms(self, frame_idx_0_based: int) -> float:
        if self._fps <= 0: return 0.0
        return (frame_idx_0_based / self._fps) * 1000.0

    def _ms_to_frame(self, ms: float) -> int: # Returns 0-based frame
        if self._fps <= 0: return 0
        frame_0_based = round((ms / 1000.0) * self._fps)
        return max(0, min(int(frame_0_based), self._total_frames - 1 if self._total_frames > 0 else 0))


    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.KeyPress:
            # Ensure event is a QKeyEvent
            if isinstance(event, QtGui.QKeyEvent):
                key_event = event
                if key_event.key() == QtCore.Qt.Key.Key_Return or key_event.key() == QtCore.Qt.Key.Key_Enter:
                    if watched is self.startFrameInput:
                        logger.debug("Enter pressed in startFrameInput")
                        self._on_start_frame_input_changed()
                        # Try to move focus to next logical widget to prevent re-triggering
                        self.endFrameInput.setFocus() 
                        self.endFrameInput.selectAll()
                        return True # Event handled
                    elif watched is self.endFrameInput:
                        logger.debug("Enter pressed in endFrameInput")
                        self._on_end_frame_input_changed()
                        self.startTimeInput.setFocus()
                        self.startTimeInput.selectAll()
                        return True # Event handled
                    elif watched is self.startTimeInput:
                        logger.debug("Enter pressed in startTimeInput")
                        self._on_start_time_input_changed()
                        self.endTimeInput.setFocus()
                        self.endTimeInput.selectAll()
                        return True # Event handled
                    elif watched is self.endTimeInput:
                        logger.debug("Enter pressed in endTimeInput")
                        self._on_end_time_input_changed()
                        # Optionally move focus to the Export button or another non-input widget
                        self.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setFocus()
                        return True # Event handled
        return super().eventFilter(watched, event)


    @QtCore.Slot(bool)
    def _on_range_type_changed(self, checked: bool):
        if self._is_updating_fields_programmatically: return
        # This slot is connected to fullVideoRadioButton.
        # 'checked' is True if fullVideoRadioButton is selected.
        self._export_full_video = checked
        logger.debug(f"Range type changed. Export full video: {self._export_full_video}")
        self._update_ui_from_internal_state()


    @QtCore.Slot()
    def _on_start_frame_input_changed(self):
        if self._is_updating_fields_programmatically: return
        try:
            val_1_based = int(self.startFrameInput.text())
            new_start_frame_0_based = max(0, min(val_1_based - 1, self._total_frames - 1 if self._total_frames > 0 else 0))
            
            if new_start_frame_0_based != self._start_frame_0_based:
                self._start_frame_0_based = new_start_frame_0_based
                if self._start_frame_0_based > self._end_frame_0_based:
                    self._end_frame_0_based = self._start_frame_0_based # End follows start
                self._update_dependent_fields("frame")
        except ValueError:
            # Revert to current internal state if input is invalid
            self._update_inputs_from_internal_state() # Reverts startFrameInput to valid state

    @QtCore.Slot()
    def _on_end_frame_input_changed(self):
        if self._is_updating_fields_programmatically: return
        try:
            val_1_based = int(self.endFrameInput.text())
            new_end_frame_0_based = max(0, min(val_1_based - 1, self._total_frames - 1 if self._total_frames > 0 else 0))

            if new_end_frame_0_based != self._end_frame_0_based:
                self._end_frame_0_based = new_end_frame_0_based
                if self._end_frame_0_based < self._start_frame_0_based:
                    self._start_frame_0_based = self._end_frame_0_based # Start follows end
                self._update_dependent_fields("frame")
        except ValueError:
            self._update_inputs_from_internal_state()

    @QtCore.Slot()
    def _on_start_time_input_changed(self):
        if self._is_updating_fields_programmatically: return
        ms = self._parse_time_str_to_ms(self.startTimeInput.text())
        if ms is not None:
            new_start_frame_0_based = self._ms_to_frame(ms)
            if new_start_frame_0_based != self._start_frame_0_based:
                self._start_frame_0_based = new_start_frame_0_based
                if self._start_frame_0_based > self._end_frame_0_based:
                    self._end_frame_0_based = self._start_frame_0_based
                self._update_dependent_fields("time")
        else: # Invalid time input
            self._update_inputs_from_internal_state()


    @QtCore.Slot()
    def _on_end_time_input_changed(self):
        if self._is_updating_fields_programmatically: return
        ms = self._parse_time_str_to_ms(self.endTimeInput.text())
        if ms is not None:
            new_end_frame_0_based = self._ms_to_frame(ms)
            if new_end_frame_0_based != self._end_frame_0_based:
                self._end_frame_0_based = new_end_frame_0_based
                if self._end_frame_0_based < self._start_frame_0_based:
                    self._start_frame_0_based = self._end_frame_0_based
                self._update_dependent_fields("time")
        else: # Invalid time input
             self._update_inputs_from_internal_state()

    def _update_dependent_fields(self, source_changed: str):
        """
        source_changed: "frame" or "time" indicating which input type triggered the update.
        This method ensures all fields (frame, time, duration) are consistent.
        """
        self._is_updating_fields_programmatically = True
        
        # Update frame inputs if time was the source, or if ensuring consistency
        if source_changed == "time" or source_changed == "init":
            self.startFrameInput.setText(str(self._start_frame_0_based + 1))
            self.endFrameInput.setText(str(self._end_frame_0_based + 1))

        # Update time inputs if frame was the source, or if ensuring consistency
        if source_changed == "frame" or source_changed == "init":
            self.startTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._start_frame_0_based)))
            self.endTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._end_frame_0_based)))
        
        self._update_duration_labels()
        self._is_updating_fields_programmatically = False

    @QtCore.Slot(bool)
    def _on_resolution_changed(self, checked: bool):
        if checked: # Only act if a radio button is being checked
            if self.viewportResRadioButton.isChecked():
                self._resolution_mode = ExportResolutionMode.VIEWPORT
            elif self.originalResRadioButton.isChecked():
                self._resolution_mode = ExportResolutionMode.ORIGINAL_VIDEO
            logger.debug(f"Resolution mode changed to: {self._resolution_mode.name}")


    @QtCore.Slot()
    def _set_start_from_current_video_pos(self):
        self._is_updating_fields_programmatically = True # Prevent feedback loops
        self._start_frame_0_based = self._current_frame_idx_0_based
        # If new start is after current end, pull end to new start
        if self._start_frame_0_based > self._end_frame_0_based:
            self._end_frame_0_based = self._start_frame_0_based
        
        self.startFrameInput.setText(str(self._start_frame_0_based + 1))
        self.startTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._start_frame_0_based)))
        # Also update end fields if they were changed by the above logic
        self.endFrameInput.setText(str(self._end_frame_0_based + 1))
        self.endTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._end_frame_0_based)))
        
        self._is_updating_fields_programmatically = False
        self._update_duration_labels() # Explicitly update duration after programmatic changes
        logger.debug(f"Set start from current: Start frame {self._start_frame_0_based + 1}, Start time {self.startTimeInput.text()}")


    @QtCore.Slot()
    def _set_end_from_current_video_pos(self):
        self._is_updating_fields_programmatically = True # Prevent feedback loops
        self._end_frame_0_based = self._current_frame_idx_0_based
        # If new end is before current start, pull start to new end
        if self._end_frame_0_based < self._start_frame_0_based:
            self._start_frame_0_based = self._end_frame_0_based

        self.endFrameInput.setText(str(self._end_frame_0_based + 1))
        self.endTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._end_frame_0_based)))
        # Also update start fields if they were changed
        self.startFrameInput.setText(str(self._start_frame_0_based + 1))
        self.startTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._start_frame_0_based)))

        self._is_updating_fields_programmatically = False
        self._update_duration_labels() # Explicitly update duration
        logger.debug(f"Set end from current: End frame {self._end_frame_0_based + 1}, End time {self.endTimeInput.text()}")


    def _update_ui_from_internal_state(self):
        """Populates all UI fields from the internal state variables."""
        self._is_updating_fields_programmatically = True

        self.fullVideoRadioButton.setChecked(self._export_full_video)
        self.customRangeRadioButton.setChecked(not self._export_full_video)
        self.customRangeInputsWidget.setEnabled(not self._export_full_video)

        # If full video, reset internal start/end to full range for display consistency
        temp_start_frame = self._start_frame_0_based
        temp_end_frame = self._end_frame_0_based
        if self._export_full_video:
            temp_start_frame = 0
            temp_end_frame = self._total_frames - 1 if self._total_frames > 0 else 0
        
        self.startFrameInput.setText(str(temp_start_frame + 1))
        self.endFrameInput.setText(str(temp_end_frame + 1))
        self.startTimeInput.setText(self._format_time_ms(self._frame_to_ms(temp_start_frame)))
        self.endTimeInput.setText(self._format_time_ms(self._frame_to_ms(temp_end_frame)))

        self._update_duration_labels(start_override=temp_start_frame, end_override=temp_end_frame)
        
        if self.originalResRadioButton.isEnabled(): # Only set if option is valid
            self.viewportResRadioButton.setChecked(self._resolution_mode == ExportResolutionMode.VIEWPORT)
            self.originalResRadioButton.setChecked(self._resolution_mode == ExportResolutionMode.ORIGINAL_VIDEO)
        else: # Original not available, force viewport
            self.viewportResRadioButton.setChecked(True)
            self._resolution_mode = ExportResolutionMode.VIEWPORT


        self._is_updating_fields_programmatically = False


    def _update_duration_labels(self, start_override: Optional[int] = None, end_override: Optional[int] = None):
        start_f = start_override if start_override is not None else self._start_frame_0_based
        end_f = end_override if end_override is not None else self._end_frame_0_based

        if self._total_frames == 0:
            self.durationFrameDisplayLabel.setText("Duration: --- frames")
            self.durationTimeDisplayLabel.setText("Duration: --:--.---")
            return

        if end_f < start_f: # Should not happen with validation, but defensive
            frame_duration = 0
        else:
            frame_duration = (end_f - start_f) + 1
        
        time_duration_ms = self._frame_to_ms(end_f) - self._frame_to_ms(start_f)
        # Duration in time should also be inclusive of start and end "moments"
        # If fps is, e.g., 10, frame 0 is 0-100ms, frame 1 is 100-200ms.
        # Clip from frame 0 to frame 0 is 1 frame long, duration 100ms.
        if frame_duration > 0 and self._fps > 0:
             time_duration_ms = frame_duration * (1000.0 / self._fps)
        else:
             time_duration_ms = 0


        self.durationFrameDisplayLabel.setText(f"Duration: {frame_duration} frame{'s' if frame_duration != 1 else ''}")
        self.durationTimeDisplayLabel.setText(f"Duration: {self._format_time_ms(time_duration_ms)}")

    def _validate_inputs(self) -> bool:
        if self._export_full_video:
            return True # No validation needed for full export

        # Ensure final values from LineEdits are parsed into internal state before validation
        # This handles the case where user types and clicks "Export" without Tab/Enter
        try:
            start_f_text = int(self.startFrameInput.text()) -1
            end_f_text = int(self.endFrameInput.text()) - 1
            self._start_frame_0_based = start_f_text
            self._end_frame_0_based = end_f_text
        except ValueError: # If text is not int, it's invalid.
             QtWidgets.QMessageBox.warning(self, "Invalid Input", "Frame numbers must be integers.")
             return False


        if not (0 <= self._start_frame_0_based < self._total_frames):
            QtWidgets.QMessageBox.warning(self, "Invalid Range",
                                          f"Start frame ({self._start_frame_0_based + 1}) is out of video range (1 to {self._total_frames}).")
            return False
        if not (0 <= self._end_frame_0_based < self._total_frames):
            QtWidgets.QMessageBox.warning(self, "Invalid Range",
                                          f"End frame ({self._end_frame_0_based + 1}) is out of video range (1 to {self._total_frames}).")
            return False
        if self._start_frame_0_based > self._end_frame_0_based:
            QtWidgets.QMessageBox.warning(self, "Invalid Range",
                                          "Start frame cannot be after end frame.")
            return False
        return True

    @QtCore.Slot()
    def accept(self):
        if not self._export_full_video:
            # Ensure current values in text boxes are processed into internal state
            # before validation, in case editingFinished didn't fire for the last active field.
            # Temporarily unblock signals to allow handlers to run if text changed.
            self._is_updating_fields_programmatically = False
            self._on_start_frame_input_changed() # Process start frame if it has focus
            self._on_end_frame_input_changed()   # Process end frame
            self._on_start_time_input_changed()  # Process start time
            self._on_end_time_input_changed()    # Process end time
            self._is_updating_fields_programmatically = True # Re-block for safety
        
        if self._validate_inputs():
            if self._export_full_video: # Ensure internal state reflects full range if selected
                self._start_frame_0_based = 0
                self._end_frame_0_based = self._total_frames - 1 if self._total_frames > 0 else 0
            
            # Update resolution mode from radio buttons one last time
            if self.viewportResRadioButton.isChecked():
                self._resolution_mode = ExportResolutionMode.VIEWPORT
            elif self.originalResRadioButton.isChecked() and self.originalResRadioButton.isEnabled():
                self._resolution_mode = ExportResolutionMode.ORIGINAL_VIDEO
            
            logger.info(f"ExportOptionsDialog accepted. FullExport: {self._export_full_video}, "
                        f"StartFrame: {self._start_frame_0_based}, EndFrame: {self._end_frame_0_based}, "
                        f"Resolution: {self._resolution_mode.name}")
            super().accept()
        else:
            logger.info("ExportOptionsDialog validation failed.")
            # Keep dialog open

    # --- Public Methods to Get Results ---
    def get_selected_range_0_based(self) -> Tuple[int, int]:
        # If "Full Video" was selected, ensure it returns the full range
        if self._export_full_video:
            return 0, (self._total_frames - 1 if self._total_frames > 0 else 0)
        return self._start_frame_0_based, self._end_frame_0_based

    def get_resolution_mode(self) -> ExportResolutionMode:
        return self._resolution_mode