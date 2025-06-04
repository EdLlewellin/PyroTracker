# kymograph_options_dialog.py
"""
Dialog for selecting the time or frame range for kymograph generation.
"""
import logging
import math
import re
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

class KymographOptionsDialog(QtWidgets.QDialog):
    def __init__(self,
                 total_frames: int,
                 fps: float,
                 current_frame_idx: int, # For defaulting start frame
                 parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Kymograph Generation Options")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._total_frames = total_frames
        self._fps = fps if fps > 0 else 30.0 # Use a sensible default if FPS is invalid
        self._total_duration_ms = (self._total_frames / self._fps) * 1000 if self._fps > 0 and self._total_frames > 0 else 0.0
        self._current_frame_idx_0_based = current_frame_idx # 0-based

        # --- Internal state for selected values ---
        self._use_full_range: bool = True
        # Default to full range (0-based internally)
        self._start_frame_0_based: int = 0
        self._end_frame_0_based: int = self._total_frames - 1 if self._total_frames > 0 else 0
        
        # Flags to prevent signal feedback loops
        self._is_updating_fields_programmatically: bool = False

        self._setup_ui()
        self._connect_signals()
        
        # Initial population and UI state update
        self._update_ui_from_internal_state()

        logger.debug(f"KymographOptionsDialog initialized. Total frames: {self._total_frames}, FPS: {self._fps:.2f}")

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # --- Range Section ---
        range_group_box = QtWidgets.QGroupBox("Kymograph Range")
        range_layout = QtWidgets.QVBoxLayout(range_group_box)

        self.fullRangeRadioButton = QtWidgets.QRadioButton("Full Video Range")
        self.fullRangeRadioButton.setChecked(self._use_full_range)
        range_layout.addWidget(self.fullRangeRadioButton)

        self.customRangeRadioButton = QtWidgets.QRadioButton("Custom Range")
        self.customRangeRadioButton.setChecked(not self._use_full_range)
        range_layout.addWidget(self.customRangeRadioButton)

        self.customRangeInputsWidget = QtWidgets.QWidget()
        custom_inputs_form_layout = QtWidgets.QFormLayout(self.customRangeInputsWidget)
        custom_inputs_form_layout.setContentsMargins(10, 5, 5, 5)
        custom_inputs_form_layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        custom_inputs_form_layout.setHorizontalSpacing(10)
        custom_inputs_form_layout.setVerticalSpacing(8)

        # Frame Inputs
        frame_input_h_layout = QtWidgets.QHBoxLayout()
        self.startFrameInput = QtWidgets.QLineEdit()
        self.startFrameInput.setValidator(QtGui.QIntValidator(1, self._total_frames if self._total_frames > 0 else 1, self))
        self.startFrameInput.setToolTip(f"Enter start frame (1 to {self._total_frames if self._total_frames > 0 else 1})")
        self.startFrameInput.setObjectName("startFrameInput")
        self.endFrameInput = QtWidgets.QLineEdit()
        self.endFrameInput.setValidator(QtGui.QIntValidator(1, self._total_frames if self._total_frames > 0 else 1, self))
        self.endFrameInput.setToolTip(f"Enter end frame (1 to {self._total_frames if self._total_frames > 0 else 1})")
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

        # Time Inputs
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
        
        # Set Start/End from Current Buttons
        set_points_button_layout = QtWidgets.QHBoxLayout()
        set_points_button_layout.setContentsMargins(0, 0, 0, 0)
        self.setStartFromCurrentButton = QtWidgets.QPushButton("Set From Current")
        self.setStartFromCurrentButton.setToolTip("Set start point to current video position")
        self.setEndFromCurrentButton = QtWidgets.QPushButton("Set From Current")
        self.setEndFromCurrentButton.setToolTip("Set end point to current video position")
        
        spacer_width_for_label = 70 # Approximate, adjust as needed
        set_points_button_layout.addSpacing(spacer_width_for_label) 
        set_points_button_layout.addWidget(self.setStartFromCurrentButton)
        set_points_button_layout.addStretch(1) 
        set_points_button_layout.addWidget(self.setEndFromCurrentButton)
        set_points_button_layout.addStretch(2) 
        custom_inputs_form_layout.addRow(set_points_button_layout)

        range_layout.addWidget(self.customRangeInputsWidget)
        main_layout.addWidget(range_group_box)

        # --- Dialog Buttons ---
        self.buttonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        generate_button = self.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        generate_button.setText("Generate")
        generate_button.setAutoDefault(True)
        main_layout.addWidget(self.buttonBox)

    def _connect_signals(self):
        self.fullRangeRadioButton.toggled.connect(self._on_range_type_changed)
        
        self.startFrameInput.editingFinished.connect(self._on_start_frame_input_changed)
        self.endFrameInput.editingFinished.connect(self._on_end_frame_input_changed)
        self.startTimeInput.editingFinished.connect(self._on_start_time_input_changed)
        self.endTimeInput.editingFinished.connect(self._on_end_time_input_changed)

        # Install event filters for Enter key press
        self.startFrameInput.installEventFilter(self)
        self.endFrameInput.installEventFilter(self)
        self.startTimeInput.installEventFilter(self)
        self.endTimeInput.installEventFilter(self)

        self.setStartFromCurrentButton.clicked.connect(self._set_start_from_current_video_pos)
        self.setEndFromCurrentButton.clicked.connect(self._set_end_from_current_video_pos)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _format_time_ms(self, ms: float) -> str:
        if ms < 0: return "--:--.---"
        try:
            s_total, mils = divmod(round(ms), 1000)
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
                ms_val = int(ms_str.ljust(3, '0'))
                if 0 <= s < 60 and 0 <= ms_val < 1000: total_ms = (m * 60 + s) * 1000 + ms_val
            except ValueError: total_ms = None
        if total_ms is None:
            match_ss_mmm = re.fullmatch(r"(\d+)\.?(\d{1,3})?", time_str)
            if match_ss_mmm:
                try:
                    s = int(match_ss_mmm.group(1))
                    ms_str = match_ss_mmm.group(2) if match_ss_mmm.group(2) else "0"
                    ms_val = int(ms_str.ljust(3, '0'))
                    if 0 <= ms_val < 1000: total_ms = s * 1000 + ms_val
                except ValueError: total_ms = None
        return total_ms
        
    def _frame_to_ms(self, frame_idx_0_based: int) -> float:
        if self._fps <= 0: return 0.0
        return (frame_idx_0_based / self._fps) * 1000.0

    def _ms_to_frame(self, ms: float) -> int:
        if self._fps <= 0: return 0
        frame_0_based = round((ms / 1000.0) * self._fps)
        return max(0, min(int(frame_0_based), self._total_frames - 1 if self._total_frames > 0 else 0))

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if isinstance(event, QtGui.QKeyEvent):
                key_event = event
                if key_event.key() == QtCore.Qt.Key.Key_Return or key_event.key() == QtCore.Qt.Key.Key_Enter:
                    if watched is self.startFrameInput: self._on_start_frame_input_changed(); self.endFrameInput.setFocus(); self.endFrameInput.selectAll(); return True
                    elif watched is self.endFrameInput: self._on_end_frame_input_changed(); self.startTimeInput.setFocus(); self.startTimeInput.selectAll(); return True
                    elif watched is self.startTimeInput: self._on_start_time_input_changed(); self.endTimeInput.setFocus(); self.endTimeInput.selectAll(); return True
                    elif watched is self.endTimeInput: self._on_end_time_input_changed(); self.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setFocus(); return True
        return super().eventFilter(watched, event)

    @QtCore.Slot(bool)
    def _on_range_type_changed(self, checked: bool):
        if self._is_updating_fields_programmatically: return
        self._use_full_range = self.fullRangeRadioButton.isChecked()
        logger.debug(f"Range type changed. Use full range: {self._use_full_range}")
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
                    self._end_frame_0_based = self._start_frame_0_based
                self._update_dependent_fields("frame")
        except ValueError: self._update_inputs_from_internal_state()

    @QtCore.Slot()
    def _on_end_frame_input_changed(self):
        if self._is_updating_fields_programmatically: return
        try:
            val_1_based = int(self.endFrameInput.text())
            new_end_frame_0_based = max(0, min(val_1_based - 1, self._total_frames - 1 if self._total_frames > 0 else 0))
            if new_end_frame_0_based != self._end_frame_0_based:
                self._end_frame_0_based = new_end_frame_0_based
                if self._end_frame_0_based < self._start_frame_0_based:
                    self._start_frame_0_based = self._end_frame_0_based
                self._update_dependent_fields("frame")
        except ValueError: self._update_inputs_from_internal_state()

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
        else: self._update_inputs_from_internal_state()

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
        else: self._update_inputs_from_internal_state()

    def _update_dependent_fields(self, source_changed: str):
        self._is_updating_fields_programmatically = True
        if source_changed == "time":
            self.startFrameInput.setText(str(self._start_frame_0_based + 1))
            self.endFrameInput.setText(str(self._end_frame_0_based + 1))
        elif source_changed == "frame":
            self.startTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._start_frame_0_based)))
            self.endTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._end_frame_0_based)))
        self._update_duration_labels()
        self._is_updating_fields_programmatically = False

    @QtCore.Slot()
    def _set_start_from_current_video_pos(self):
        self._is_updating_fields_programmatically = True
        self._start_frame_0_based = self._current_frame_idx_0_based
        if self._start_frame_0_based > self._end_frame_0_based:
            self._end_frame_0_based = self._start_frame_0_based
        self._update_inputs_from_internal_state() # Updates all relevant fields
        self._is_updating_fields_programmatically = False
        self._update_duration_labels()
        logger.debug(f"Set start from current: Start frame {self._start_frame_0_based + 1}")

    @QtCore.Slot()
    def _set_end_from_current_video_pos(self):
        self._is_updating_fields_programmatically = True
        self._end_frame_0_based = self._current_frame_idx_0_based
        if self._end_frame_0_based < self._start_frame_0_based:
            self._start_frame_0_based = self._end_frame_0_based
        self._update_inputs_from_internal_state() # Updates all relevant fields
        self._is_updating_fields_programmatically = False
        self._update_duration_labels()
        logger.debug(f"Set end from current: End frame {self._end_frame_0_based + 1}")

    def _update_ui_from_internal_state(self):
        self._is_updating_fields_programmatically = True
        self.fullRangeRadioButton.setChecked(self._use_full_range)
        self.customRangeRadioButton.setChecked(not self._use_full_range)
        self.customRangeInputsWidget.setEnabled(not self._use_full_range)

        temp_start_frame = self._start_frame_0_based
        temp_end_frame = self._end_frame_0_based
        if self._use_full_range:
            temp_start_frame = 0
            temp_end_frame = self._total_frames - 1 if self._total_frames > 0 else 0
        
        self.startFrameInput.setText(str(temp_start_frame + 1))
        self.endFrameInput.setText(str(temp_end_frame + 1))
        self.startTimeInput.setText(self._format_time_ms(self._frame_to_ms(temp_start_frame)))
        self.endTimeInput.setText(self._format_time_ms(self._frame_to_ms(temp_end_frame)))
        self._update_duration_labels(start_override=temp_start_frame, end_override=temp_end_frame)
        self._is_updating_fields_programmatically = False

    def _update_inputs_from_internal_state(self):
        """Populates QLineEdit fields from internal start/end frame state."""
        self._is_updating_fields_programmatically = True
        self.startFrameInput.setText(str(self._start_frame_0_based + 1))
        self.endFrameInput.setText(str(self._end_frame_0_based + 1))
        self.startTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._start_frame_0_based)))
        self.endTimeInput.setText(self._format_time_ms(self._frame_to_ms(self._end_frame_0_based)))
        self._is_updating_fields_programmatically = False

    def _update_duration_labels(self, start_override: Optional[int] = None, end_override: Optional[int] = None):
        start_f = start_override if start_override is not None else self._start_frame_0_based
        end_f = end_override if end_override is not None else self._end_frame_0_based

        if self._total_frames == 0:
            self.durationFrameDisplayLabel.setText("Duration: --- frames")
            self.durationTimeDisplayLabel.setText("Duration: --:--.---")
            return

        frame_duration = (end_f - start_f) + 1 if end_f >= start_f else 0
        time_duration_ms = frame_duration * (1000.0 / self._fps) if frame_duration > 0 and self._fps > 0 else 0.0

        self.durationFrameDisplayLabel.setText(f"Duration: {frame_duration} frame{'s' if frame_duration != 1 else ''}")
        self.durationTimeDisplayLabel.setText(f"Duration: {self._format_time_ms(time_duration_ms)}")

    def _validate_inputs(self) -> bool:
        if self._use_full_range:
            return True

        try:
            start_f_text = int(self.startFrameInput.text()) - 1
            end_f_text = int(self.endFrameInput.text()) - 1
            # Update internal state based on final text box values before validation
            self._start_frame_0_based = start_f_text
            self._end_frame_0_based = end_f_text
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Frame numbers must be integers.")
            return False

        if not (0 <= self._start_frame_0_based < self._total_frames):
            QtWidgets.QMessageBox.warning(self, "Invalid Range", f"Start frame ({self._start_frame_0_based + 1}) is out of video range (1 to {self._total_frames}).")
            return False
        if not (0 <= self._end_frame_0_based < self._total_frames):
            QtWidgets.QMessageBox.warning(self, "Invalid Range", f"End frame ({self._end_frame_0_based + 1}) is out of video range (1 to {self._total_frames}).")
            return False
        if self._start_frame_0_based > self._end_frame_0_based:
            QtWidgets.QMessageBox.warning(self, "Invalid Range", "Start frame cannot be after end frame.")
            return False
        return True

    @QtCore.Slot()
    def accept(self):
        if not self._use_full_range:
            self._is_updating_fields_programmatically = False # Allow final processing
            self._on_start_frame_input_changed()
            self._on_end_frame_input_changed()
            self._on_start_time_input_changed()
            self._on_end_time_input_changed()
            self._is_updating_fields_programmatically = True
        
        if self._validate_inputs():
            if self._use_full_range: # Ensure internal state reflects full range if selected
                self._start_frame_0_based = 0
                self._end_frame_0_based = self._total_frames - 1 if self._total_frames > 0 else 0
            
            logger.info(f"KymographOptionsDialog accepted. FullRange: {self._use_full_range}, "
                        f"StartFrame: {self._start_frame_0_based}, EndFrame: {self._end_frame_0_based}")
            super().accept()
        else:
            logger.info("KymographOptionsDialog validation failed.")

    # --- Public Methods to Get Results ---
    def get_selected_range_0_based(self) -> Tuple[int, int]:
        if self._use_full_range:
            return 0, (self._total_frames - 1 if self._total_frames > 0 else 0)
        return self._start_frame_0_based, self._end_frame_0_based