# PyroTracker

## Description

PyroTracker provides a graphical user interface (GUI) for tracking volcanic pyroclasts in eruption videos. Users can load a video, navigate through frames, manage different coordinate systems (Top-Left, Bottom-Left, Custom Origin), mark the changing position of specific pyroclasts over time to generate tracks, and save/load this track data.

The tool features interactive zoom and pan capabilities, frame-by-frame navigation, optional auto-advancing, multi-track management with visibility controls, track selection via table or image view clicks, visual feedback for marked tracks, persistent visual preferences (colors, sizes), and a video metadata viewer. Coordinate system information (including custom origins) is saved and loaded with track files.

Built using Python with the PySide6 (Qt6) framework for the GUI and OpenCV for video handling. Uses Python's standard `logging` module for diagnostics and Qt's `QSettings` for preference persistence.

## Features

* **Load Video:** Open common video file formats (.mp4, .avi, .mov, .mkv) via `File -> Open Video...`.
* **Frame Navigation:**
    * Seek through frames using a slider.
    * Step frame-by-frame using "Next >>" and "<< Prev" buttons.
    * Step frame-by-frame using `Mouse Wheel Scroll` (Scroll Up: Previous, Scroll Down: Next).
    * Play/Pause video playback at its native frame rate (toggle button or `Spacebar`).
    * Display current frame number and total frames.
    * Display current time and total video duration (MM:SS.mmm).
    * Display the video FPS and filename (tooltip shows the full path).
    * Click on frame numbers in the "Tracks" table (Start/End Frame columns) or "Points" table (Frame column) to jump directly to that frame.
    * `Shift+Click` on a visible track marker in the image view to select that track *and* jump directly to the frame containing that specific marker.
* **Interactive View:**
    * Zoom in/out using `Ctrl + Mouse Wheel` or overlay buttons (+/-).
    * Pan the view using left-click-and-drag.
    * Zoom/pan state persists across frame changes (after the initial frame).
    * Minimum and maximum zoom levels enforced.
    * Overlay buttons for Zoom In (+), Zoom Out (-), and Fit View (⤢) in the top-right corner.
* **Multi-Track Pyroclast Tracking:**
    * Create new tracks using the "New Track" button (or `Ctrl+N` shortcut via `Edit -> New Track`).
    * **Select Active Track:**
        * `Ctrl+Click` on a visible track marker in the image view.
        * Click on a track row in the "Tracks" table.
    * **Add/Update Points:** Left-click on the video frame to mark a pyroclast's position for the *active* track on the current frame. Clicking again *updates* the existing point's coordinates. Only one point per track per frame is allowed. Coordinates are stored internally in Top-Left system but displayed according to the selected coordinate system.
    * **Delete Point:** Delete the point for the *active* track on the *current* frame by pressing the `Delete` or `Backspace` key.
    * **Visuals:** Markers (crosses) and lines are drawn based on track activity and visibility settings. Default colors (e.g., active=yellow/red, inactive=blue/cyan) can be customized via Preferences.
    * **Track Visibility Control:** Control track display mode individually (Hidden 'X', Incremental '>', Always Visible '✓') using radio buttons in the "Tracks" table. Set all tracks to a specific mode by clicking the corresponding header icon. Visuals update according to the selected mode and current frame.
    * **Delete Tracks:** Delete entire tracks using the trash can icon button (🗑️) in the first column of the "Tracks" table (confirmation required).
* **Auto-Advance:** Optionally enable automatic frame advance after adding/updating a point via the "Frame Advance" panel. Control the number of frames to advance using the spin box.
* **Coordinate System Management:**
    * Select coordinate system mode (Top-Left, Bottom-Left, Custom) using radio buttons in the "Coordinate System" panel.
    * Set a custom origin by clicking "Pick Custom" and then clicking the desired origin location on the image view.
    * The effective Top-Left coordinates of the origin for each system are displayed.
    * **Live Cursor Position:** The current position of the mouse cursor over the image is displayed live, transformed into each of the three coordinate systems (Top-Left, Bottom-Left, Custom).
    * Toggle the visibility of the effective origin marker on the image using the "Show Origin" checkbox. The marker color can be customized via Preferences.
    * Selected coordinate system and custom origin are saved/loaded with track files.
* **Data Display & UI:**
    * Resizable main window split between the video view/controls (left) and data/settings panels (right).
    * "Tracks" tab: Lists all tracks with controls for deletion, selection, and visibility.
    * "Points" tab: Displays points (Frame, Time (s), X, Y) for the active track, with coordinates shown in the current display system.
    * "Frame Advance" panel: Controls for the auto-advance feature.
    * "Coordinate System" panel: Controls for selecting coordinate system, setting custom origin, viewing live cursor positions, and toggling origin marker visibility.
* **Save/Load Tracks:**
    * Save all current track point data to a CSV file via `File -> Save Tracks As...`. The CSV includes a header with video metadata (filename, dimensions, frame count, FPS, duration), application version, coordinate system settings, and columns for `track_id`, `frame_index`, `time_ms`, `x`, `y` (coordinates saved in the currently selected system's format).
    * Load track point data from a previously saved CSV file via `File -> Load Tracks...`. This replaces any existing tracks (confirmation required). Coordinate system settings are loaded from the file and applied. Basic validation and metadata mismatch warnings are provided.
* **Preferences:** Customize visual settings (track/origin colors, marker size, line width) via `Edit -> Preferences...`. Settings are persisted between sessions using `QSettings`.
* **Video Information:** View technical metadata extracted from the loaded video file via `File -> Video Information...`.
* **Logging:** Diagnostic information is printed to the console using standard Python logging (configured in `main.py`). Level defaults to DEBUG.

## Requirements

* Python 3.x (Developed with 3.9+)
* PySide6 (`pip install PySide6`)
* OpenCV for Python (`pip install opencv-python`)
* NumPy (usually installed as a dependency with OpenCV) (`pip install numpy`)

*(Note: The Python standard libraries `csv`, `os`, `math`, `logging`, `enum`, `sys`, `typing` are also used but do not require separate installation).*

## Installation

1.  Ensure Python 3 is installed.
2.  Install the required external libraries:
    ```bash
    pip install PySide6 opencv-python numpy
    ```
3.  Place the `PyroTracker.ico` file in the same directory as the Python scripts (optional, for the application icon).

## Usage

1.  Save all Python files (`main.py`, `main_window.py`, `interactive_image_view.py`, `track_manager.py`, `video_handler.py`, `file_io.py`, `ui_setup.py`, `config.py`, `coordinates.py`, `settings_manager.py`, `preferences_dialog.py`, `metadata_dialog.py`) and optionally `PyroTracker.ico` in the same directory.
2.  Run the application from your terminal:
    ```bash
    python main.py
    ```
    *(Note: Debugging information will be printed to the console).*
3.  Go to `File -> Open Video...` to load a video file.
4.  Use the slider, buttons, or `Mouse Wheel` to navigate frames. Use `Spacebar` to toggle play/pause.
5.  Use `Ctrl + Mouse Wheel` or overlay buttons (+/-) to zoom, and left-click-drag to pan. Use the overlay "Fit" button (⤢) to reset view.
6.  In the "Coordinate System" panel, select the desired system. Use "Pick Custom" to set a user-defined origin. Toggle the origin marker with "Show Origin". Observe live cursor coordinates.
7.  Click "New Track" in the "Tracks" tab (or press `Ctrl+N`).
8.  **Select** a track using `Ctrl+Click` on a marker or by clicking its table row.
9.  **Select & Jump** to a specific point's frame using `Shift+Click` on its marker.
10. **Add/Update Point:** Navigate to the desired frame and left-click (no modifiers) on the video to mark the active pyroclast's position.
11. **(Optional) Auto-Advance:** Enable and configure in the "Frame Advance" panel.
12. **Set Visibility:** Use radio buttons or header icons in the "Tracks" table.
13. **Delete Point:** Press `Delete` or `Backspace` to remove the active track's point on the current frame.
14. **Delete Track:** Click the trash can icon in the "Tracks" table.
15. **Save/Load:** Use `File -> Save Tracks As...` and `File -> Load Tracks...`.
16. **Customize:** Go to `Edit -> Preferences...` to change visual settings.
17. **View Info:** Go to `File -> Video Information...` to see video metadata.
18. **About:** Go to `Help -> About` for application details.

## File Structure

* `main.py`: Entry point script; initializes QApplication, logging, and MainWindow.
* `config.py`: Shared constants (CSV format, metadata keys, table indices, default styles, app info).
* `coordinates.py`: `CoordinateSystem` enum and `CoordinateTransformer` class for coordinate management.
* `settings_manager.py`: Manages persistent application settings (visuals) using QSettings.
* `ui_setup.py`: Function `setup_main_window_ui` to create and arrange GUI widgets and menus.
* `main_window.py`: `MainWindow` class; orchestrates UI, components, signals/slots, drawing.
* `interactive_image_view.py`: `InteractiveImageView` class (QGraphicsView) for frame display and mouse interaction (zoom, pan, clicks).
* `video_handler.py`: `VideoHandler` class; manages video loading (OpenCV), playback (QTimer), navigation, frame extraction.
* `track_manager.py`: `TrackManager` class; stores and manages multi-track point data and visibility settings.
* `file_io.py`: Functions for CSV track data reading/writing, including metadata and coordinate transformations.
* `preferences_dialog.py`: `PreferencesDialog` class for editing visual settings stored by `settings_manager`.
* `metadata_dialog.py`: `MetadataDialog` class for displaying video metadata retrieved by `video_handler`.
* `PyroTracker.ico`: (Optional) Application icon file.

## Future Improvements / Todo

* Add basic data analysis capabilities (e.g., velocity calculation, track plotting).
* Enhance logging configuration (e.g., allow user to set level, log to file).
* Replace standard text/pixmap overlay buttons with custom SVG icons for a cleaner look.
* Consider adding unit tests for core logic (e.g., `TrackManager`, `VideoHandler`, `CoordinateTransformer`).
* Improve error handling for invalid video files or corrupted CSVs.
* Add undo/redo functionality for point marking/deletion.