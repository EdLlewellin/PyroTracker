# PyroTracker

## Description

PyroTracker provides a graphical user interface (GUI) for tracking volcanic pyroclasts in eruption videos. Users can load a video, navigate through frames, manage different coordinate systems (Top-Left, Bottom-Left, Custom Origin), optionally define a pixel-to-meter scale manually or by drawing a line on a feature of known length, mark the changing position of specific pyroclasts over time to generate tracks, and save/load this track data.

The tool features interactive zoom and pan capabilities; frame-by-frame navigation; optional auto-advancing; multi-track management with visibility controls; track selection via table or image view clicks; visual feedback for marked tracks; **on-screen information overlays (filename, time, frame number)**; an optional on-screen scale bar and scale definition line; persistent visual preferences (colors, sizes); a video metadata viewer; export capabilities for both the full video with overlays and individual frames as PNG images; and **undo functionality for point marking, modification, and deletion.** Coordinate system information, custom origins, scaling factors, and defined scale line coordinates (if set) are saved and loaded with track files, allowing data to be output in either pixels or meters. A **View Menu** provides centralized control for toggling the visibility of various on-screen overlays.

Built using Python with the PySide6 (Qt6) framework for the GUI and OpenCV for video handling. Uses Python's standard `logging` module for diagnostics and Qt's `QSettings` for preference persistence.

## Download and Run (Recommended for Most Users)

Pre-built versions of PyroTracker for Windows, macOS, and Linux are available for easy installation without needing to install Python or other dependencies.

1.  **Go to the [Latest Release page](https://github.com/EdLlewellin/PyroTracker/releases).**
2.  Under the "Assets" section for the latest release, download the correct file for your operating system:
    * **Windows:** Download the `PyroTracker-windows.exe` file.
    * **macOS:** Download the `PyroTracker-macos.zip` file.
    * **Linux:** Download the `PyroTracker-linux` file.
3.  **Run the application:**
    * **Windows:** Simply double-click the downloaded `PyroTracker-windows.exe` file. You might see a security warning ("Windows protected your PC"); click "More info" and then "Run anyway".
    * **macOS:** Double-click the downloaded `PyroTracker-macos.zip` file to unzip it. This will create a `PyroTracker.app` file. Double-click `PyroTracker.app` to run it.
        * *Note:* You might see a security warning ("App can't be opened because it is from an unidentified developer"). If so, right-click (or Ctrl-click) the `PyroTracker.app` file and select "Open", then confirm in the dialog box. You should only need to do this the first time.
    * **Linux:** Open a terminal, navigate to the directory where you downloaded the file, make it executable using the command `chmod +x PyroTracker-linux`, and then run it using `./PyroTracker-linux`.

---

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
* **Interactive View & Overlays:**
    * Zoom in/out using `Ctrl + Mouse Wheel` or overlay buttons (+/-).
    * Pan the view using left-click-and-drag.
    * Zoom/pan state persists across frame changes (after the initial frame).
    * Minimum and maximum zoom levels enforced.
    * Overlay buttons for Zoom In (+), Zoom Out (-), and Fit View (⤢) in the top-right corner.
    * **Information Overlays:** Displays video filename (top-left), current/total time (bottom-left), and current/total frame number (bottom-left, below time if both visible) directly on the viewport. Appearance (color, font size) for each is customizable via `Edit -> Preferences...`.
    * **Optional Scale Bar / Line:** If a pixel-to-meter scale is set, a scale bar and/or the defined scale line are displayed on the image view (bottom-right / defined location respectively). The bar's length represents a round number in appropriate units (e.g., cm, m, km) and dynamically updates with zoom.
    * **View Menu Control:** The `View` menu allows toggling the visibility of:
        * Filename, Time, and Frame Number information overlays.
        * On-screen Scale Bar.
        * Defined Scale Line.
        * Coordinate System Origin Marker.
        These menu actions synchronize with corresponding checkboxes in the side panels where applicable.
* **Multi-Track Pyroclast Tracking:**
    * Create new tracks using the "New Track" button (or `Ctrl+N` shortcut via `Edit -> New Track`).
    * **Select Active Track:**
        * `Ctrl+Click` on a visible track marker in the image view or on a blank area to deselect.
        * Click on a track row in the "Tracks" table.
    * **Add/Update Points:** Left-click on the video frame to mark a pyroclast's position for the *active* track on the current frame. Clicking again *updates* the existing point's coordinates. Only one point per track per frame is allowed. Coordinates are stored internally in Top-Left system but displayed according to the selected coordinate system and scale unit (pixels or meters).
    * **Delete Point:** Delete the point for the *active* track on the *current* frame by pressing the `Delete` or `Backspace` key.
    * **Undo Point Operation:** Undo the last point addition, modification, or deletion using `Edit -> Undo Point Action` or `Ctrl+Z`.
    * **Visuals:** Markers (crosses) and lines are drawn based on track activity and visibility settings. Default colors (e.g., active=yellow/red, inactive=blue/cyan) can be customized via Preferences.
    * **Track Visibility Control:** Control track display mode individually (Hidden 'X', Incremental '>', Always Visible '✓') using radio buttons in the "Tracks" table. Set all tracks to a specific mode by clicking the corresponding header icon. Visuals update according to the selected mode and current frame.
    * **Delete Tracks:** Delete entire tracks using the trash can icon button (🗑️) in the first column of the "Tracks" table (confirmation required).
* **Auto-Advance:** Optionally enable automatic frame advance after adding/updating a point via the "Frame Advance" panel. Control the number of frames to advance using the spin box.
* **Scale Configuration:**
    * Set a pixel-to-meter scale using input boxes for "m/px" or "px/m" in the "Scale Configuration" panel. Entering a value in one box automatically calculates the reciprocal.
    * **Set Scale by Feature:** Define scale by clicking the 'Set' button, clicking two points on a feature of known length in the image view, and entering the real-world distance in the dialog.
    * A 'Show scale line' checkbox (and corresponding `View` menu item) toggles the visibility of this defined line on the image. The line's appearance (color, width, text, end ticks) can be customized via Preferences.
    * Reset the scale using the reset button.
    * A "Display in meters" checkbox allows toggling the units for displayed data in the "Points" table.
    * A "Show Scale Bar" checkbox (and corresponding `View` menu item) allows toggling the visibility of the on-screen scale bar. The scale bar's appearance (color, font size, bar height) can be customized via Preferences. Both checkboxes are only enabled if a valid scale is set.
* **Coordinate System Management:**
    * Select coordinate system mode (Top-Left, Bottom-Left, Custom) using radio buttons in the "Coordinate System" panel.
    * Set a custom origin by clicking "Pick Custom" and then clicking the desired origin location on the image view.
    * The effective Top-Left coordinates of the origin for each system are displayed.
    * **Live Cursor Position:** The current position of the mouse cursor over the image is displayed live, transformed into each of the three coordinate systems (Top-Left, Bottom-Left, Custom). Both pixel and metric (if scale is set) coordinates are shown simultaneously for each system.
    * Toggle the visibility of the effective origin marker on the image using the "Show Origin" checkbox (and corresponding `View` menu item). The marker color can be customized via Preferences.
    * Selected coordinate system and custom origin are saved/loaded with track files.
* **Data Display & UI:**
    * Resizable main window split between the video view/controls (left) and data/settings panels (right).
    * "Tracks" tab: Lists all tracks with controls for deletion, selection, and visibility.
    * "Points" tab: Displays points (Frame, Time (s), X, Y) for the active track. Column headers (X, Y) indicate current display units (pixels or meters).
    * "Frame Advance" panel: Controls for the auto-advance feature.
    * "Scale Configuration" panel: Controls for setting the m/px scale, setting scale from feature, toggling display units, and toggling scale bar / line visibility.
    * "Coordinate System" panel: Controls for selecting coordinate system, setting custom origin, viewing live cursor positions (in both pixels and meters), and toggling origin marker visibility.
* **Save/Load Tracks:**
    * Save all current track point data to a CSV file via `File -> Save Tracks As...`. The CSV includes a header with video metadata (filename, dimensions, frame count, FPS, duration), application version, coordinate system settings, scale factor, data units (px or m), and defined scale line coordinates (if set). Coordinates are saved in the chosen system and unit.
    * **Precision Warning:** If saving in meters, a warning is displayed about potential precision loss, offering options to save in meters, pixels, or cancel.
    * Load track point data from a previously saved CSV file via `File -> Load Tracks...`. This replaces any existing tracks (confirmation required). Coordinate system, scale settings (factor, display unit preference), and defined scale line coordinates are loaded from the file and applied. Basic validation and metadata mismatch warnings are provided.
* **Exporting:**
    * **Export Video with Overlays:** `File -> Export Video with Overlays...` allows exporting the full video sequence or a custom range with all visible overlays (tracks, origin marker, scale line, scale bar, info overlays) rendered onto each frame. Users can choose between MP4 (using 'mp4v' codec) and AVI (using 'MJPG' codec) formats, and select viewport or original video resolution.
    * **Export Current Frame to PNG:** `File -> Export Current Frame to PNG...` saves the currently displayed frame, including all visible overlays, as a PNG image file. User can select viewport or original video resolution.
* **Preferences:** Customize visual settings (track/origin colors and sizes, scale line/bar appearance, info overlay appearance) via `Edit -> Preferences...`. Settings are persisted between sessions using `QSettings`.
* **Video Information:** View technical metadata extracted from the loaded video file via `File -> Video Information...`.
* **Logging:** Diagnostic information is printed to the console using standard Python logging (configured in `main.py`). Level defaults to DEBUG.

## Developer Requirements

* Python 3.x (Developed with 3.9+)
* PySide6 (`pip install PySide6`)
* OpenCV for Python (`pip install opencv-python`)
* NumPy (usually installed as a dependency with OpenCV) (`pip install numpy`)
* Pillow (`pip install Pillow`) (Needed for icon conversion during automated builds)

*(Note: The Python standard libraries `csv`, `os`, `math`, `logging`, `enum`, `sys`, `typing`, `re` are also used but do not require separate installation).*

## Developer Installation (from Source)

1.  Ensure Python 3 and pip are installed.
2.  Clone the repository: `git clone https://github.com/EdLlewellin/PyroTracker.git`
3.  Navigate into the directory: `cd PyroTracker`
4.  (Recommended) Create and activate a virtual environment:
    ```bash
    python -m venv venv
    # On Windows:
    venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```
5.  Install the required external libraries:
    ```bash
    pip install -r requirements.txt
    ```
    *(The `requirements.txt` file includes PySide6, opencv-python, numpy, and Pillow).*
6.  The `PyroTracker.ico` file should be present in the main directory (used by PyInstaller during builds).

## Developer Usage (from Source)

1.  Ensure you have followed the Developer Installation steps, including activating the virtual environment if you created one.
2.  Run the application from your terminal in the project's root directory:
    ```bash
    python main.py
    ```
    *(Note: Debugging information will be printed to the console).*
3.  **Basic Workflow:**
    * Go to `File -> Open Video...` to load a video file.
    * Use the slider, buttons, or `Mouse Wheel` to navigate frames. Use `Spacebar` to toggle play/pause. Enter frame numbers or time directly into the navigation bar fields and press Enter to seek.
    * Use `Ctrl + Mouse Wheel` or overlay buttons (+/-) to zoom, and left-click-drag to pan. Use the overlay "Fit" button (⤢) to reset view. Enter zoom percentage in navigation bar and press Enter.
    * **(Optional) Set Scale:** In the "Scale Configuration" panel, enter a value for `m/px` (or `px/m`) and press Enter. Alternatively, click 'Set' under 'Scale from feature', click two points on the image, enter the known distance in meters, and click OK.
    * In the "Coordinate System" panel, select the desired system. Use "Pick Custom" to set a user-defined origin. Observe live cursor coordinates (shown in both pixels and meters if scale is set).
    * **Toggle Overlays:** Use the `View` menu or checkboxes in the side panels (Scale Configuration, Coordinate System) to toggle visibility of info overlays (filename, time, frame), scale bar, defined scale line, and origin marker.
    * Click "New Track" in the "Tracks" tab (or press `Ctrl+N`).
    * **Select** a track using `Ctrl+Click` on a marker or by clicking its table row.
    * **Select & Jump** to a specific point's frame using `Shift+Click` on its marker.
    * **Add/Update Point:** Navigate to the desired frame and left-click (no modifiers) on the video to mark the active pyroclast's position.
    * **(Optional) Auto-Advance:** Enable and configure in the "Frame Advance" panel.
    * **Set Visibility:** Use radio buttons or header icons in the "Tracks" table.
    * **Delete Point:** Press `Delete` or `Backspace` to remove the active track's point on the current frame.
    * **Undo Point Action:** Use `Edit -> Undo Point Action` or `Ctrl+Z` to revert the last point addition, modification, or deletion.
    * **Delete Track:** Click the trash can icon in the "Tracks" table.
    * **Save/Load:** Use `File -> Save Tracks As...` and `File -> Load Tracks...`.
    * **Export:** Use `File -> Export Video with Overlays...` or `File -> Export Current Frame to PNG...`.
    * **Customize:** Go to `Edit -> Preferences...` to change visual settings.
    * **View Info:** Go to `File -> Video Information...` to see video metadata.
    * **About:** Go to `Help -> About` for application details.

## File Structure

* `main.py`: Entry point script; initializes QApplication, logging, and MainWindow.
* `config.py`: Shared constants (CSV format, metadata keys, table indices, default styles, app info).
* `coordinates.py`: `CoordinateSystem` enum and `CoordinateTransformer` class for coordinate management.
* `scale_manager.py`: `ScaleManager` class; manages pixel-to-meter scale factor, display units, and defined scale line data.
* `scale_bar_widget.py`: `ScaleBarWidget` class; custom widget for drawing the dynamic on-screen scale bar.
* `info_overlay_widget.py`: `InfoOverlayWidget` class; custom widget for rendering fixed informational text overlays (filename, time, frame number) on the image view.
* `settings_manager.py`: Manages persistent application settings (visuals) using QSettings.
* `ui_setup.py`: Function `setup_main_window_ui` to create and arrange GUI widgets and menus for the `MainWindow`.
* `main_window.py`: `MainWindow` class; orchestrates core components (VideoHandler, TrackManager, etc.), main application signals/slots, menu actions, and drawing of scene overlays. Initializes UI controllers.
* `interactive_image_view.py`: `InteractiveImageView` class (QGraphicsView) for frame display, mouse interaction, and hosting overlay widgets.
* `video_handler.py`: `VideoHandler` class; manages video loading (OpenCV), playback (QTimer), navigation, frame extraction.
* `track_manager.py`: `TrackManager` class; stores and manages multi-track point data, visibility settings, and point operation undo logic.
* `file_io.py`: Functions for CSV track data reading/writing, including metadata and coordinate transformations.
* `export_handler.py`: `ExportHandler` class; manages logic for exporting video frames with overlays as new video files or individual images.
* `export_options_dialog.py`: `ExportOptionsDialog` class for selecting video export range and resolution.
* `panel_controllers.py`: Contains controller classes (`ScalePanelController`, `CoordinatePanelController`) that manage UI logic for specific QGroupBox panels.
* `table_controllers.py`: Contains `TrackDataViewController` class that manages UI logic for the Tracks and Points data tables.
* `view_menu_controller.py`: `ViewMenuController` class; manages the View menu and actions related to overlay visibility.
* `preferences_dialog.py`: `PreferencesDialog` class for editing visual settings.
* `metadata_dialog.py`: `MetadataDialog` class for displaying video metadata.
* `collapsible_panel.qss`: Qt Style Sheet file used for styling the collapsible QGroupBox panels. Loaded by `main.py`.
* `PyroTracker.ico`: Application icon file (used for builds).
* `icons/` (directory): Contains SVG files (e.g., `arrow_right.svg`, `arrow_down.svg`) used by `collapsible_panel.qss` for panel indicators.
* `.github/workflows/release.yml`: GitHub Actions workflow for automated building and releasing.
* `requirements.txt`: Lists Python dependencies for `pip`.
* `.gitignore`: Specifies intentionally untracked files for Git.

## Future Improvements / Todo

* Add basic data analysis capabilities (e.g., velocity calculation, track plotting).
* Enhance logging configuration (e.g., allow user to set level, log to file).
* Replace standard text/pixmap overlay buttons with custom SVG icons for a cleaner look.
* Consider adding unit tests for core logic.
* Improve error handling for invalid video files or corrupted CSVs.
* **(Done for Undo)** Add undo/redo functionality for point marking/deletion. (Current: Undo for add, modify, delete implemented; Redo is a potential future addition).
* **(Done)** Allow customization of scale bar appearance (colors, font, bar height) via Preferences.
* **(Done)** Allow customization of defined scale line appearance (color, width, text, end ticks) via Preferences.
* **(Done)** Allow customization of info overlay appearance (colors, font sizes) via Preferences.
* Add more video export format options with clear indication of codec dependencies.