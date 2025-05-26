# PyroTracker

## Description

PyroTracker provides a graphical user interface (GUI) for tracking volcanic pyroclasts in eruption videos. Users can load a video, navigate through frames, manage different coordinate systems (Top-Left, Bottom-Left, Custom Origin), optionally define a pixel-to-meter scale manually or by drawing a line on a feature of known length, mark the changing position of specific pyroclasts over time to generate tracks, and create measurement lines. **Project data, including element coordinates (always stored as raw Top-Left pixels), video metadata, coordinate system settings, and scale information, is saved to and loaded from JSON-based project files.**

The tool features interactive zoom and pan capabilities; frame-by-frame navigation; optional auto-advancing; multi-element management (tracks and measurement lines) with visibility controls; element selection via table or image view clicks; visual feedback for marked elements; on-screen information overlays (filename, time, frame number); an optional on-screen scale bar and scale definition line; persistent visual preferences (colors, sizes); a video metadata viewer; export capabilities for both the full video with overlays and individual frames as PNG images; and undo functionality for point marking operations. A **View Menu** provides centralized control for toggling the visibility of various on-screen overlays, including measurement line lengths.

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
    * Input current frame or time directly to seek.
    * Display the video FPS and filename (tooltip shows the full path).
    * Click on frame numbers in the "Tracks" or "Measurement Lines" table (Start/End Frame or Frame columns respectively) or "Points" table (Frame column) to jump directly to that frame.
    * `Shift+Click` on a visible track marker in the image view to select that track *and* jump directly to the frame containing that specific marker.
* **Interactive View & Overlays:**
    * Zoom in/out using `Ctrl + Mouse Wheel` or overlay buttons (+/-). Zoom level displayed and editable.
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
        * **Measurement Line Lengths.**
        These menu actions synchronize with corresponding checkboxes in the side panels where applicable.
* **Multi-Element Data Collection:**
    * **Tracks:**
        * Create new tracks using the "New" button in the "Tracks" tab or `Edit -> New Track` (`Ctrl+N`).
        * **Select Active Track:** `Ctrl+Click` on a visible track marker in the image view or on a blank area to deselect. Click on a track row in the "Tracks" table.
        * **Add/Update Points:** Left-click on the video frame to mark a pyroclast's position for the *active* track on the current frame. Clicking again *updates* the existing point's coordinates. Only one point per track per frame is allowed.
        * **Delete Point:** Delete the point for the *active* track on the *current* frame by pressing the `Delete` or `Backspace` key.
        * **Undo Point Operation:** Undo the last point addition, modification, or deletion for tracks using `Edit -> Undo Point Action` or `Ctrl+Z`.
        * **Visuals:** Markers (crosses) and lines are drawn based on track activity and visibility settings.
        * **Track Visibility Control:** Control track display mode individually (Hidden, Home Frame, Incremental, Always Visible) using radio buttons in the "Tracks" table. Set all tracks to a specific mode by clicking the corresponding header icon.
        * **Delete Tracks:** Delete entire tracks using the trash can icon button (🗑️) in the "Tracks" table (confirmation required).
    * **Measurement Lines:**
        * Create new measurement lines using the "New" button in the "Measurement Lines" tab.
        * Define a line by clicking two points on the *same* video frame. Line definition can be snapped to angles (e.g., 0°, 45°, 90°) by holding `Shift` while defining the second point.
        * Lines are displayed with their length (in current display units if scale is set, otherwise pixels) and angle (0-360°, 0° to the right).
        * Length label visibility can be toggled via the `View` menu and preferences.
        * Visuals (color, width for normal and active states) are customizable via `Edit -> Preferences...`.
        * Visibility control (Hidden, Home Frame, Incremental, Always Visible) similar to tracks.
        * Delete lines using the trash can icon.
* **Auto-Advance:** Optionally enable automatic frame advance after adding/updating a track point via the "Tracks" tab controls.
* **Scale Configuration:**
    * Set a pixel-to-meter scale using input boxes for "m/px" or "px/m" in the "Scale Configuration" panel.
    * **Set Scale by Feature:** Define scale by clicking the 'Set' button, clicking two points on a feature of known length in the image view, and entering the real-world distance in meters. Line definition can be snapped to angles by holding `Shift`.
    * A 'Show scale line' checkbox toggles the visibility of this defined line. Appearance customizable via Preferences.
    * Reset the scale using the reset button.
    * A "Display in meters" checkbox toggles the units for displayed data (Points table, Measurement Line lengths, cursor coordinates).
    * A "Show Scale Bar" checkbox toggles the visibility of the on-screen scale bar. Appearance customizable via Preferences.
* **Coordinate System Management:**
    * Select coordinate system mode (Top-Left, Bottom-Left, Custom) using radio buttons.
    * Set a custom origin by clicking "Pick Custom" and then clicking the desired origin location on the image view.
    * The effective Top-Left coordinates of the origin for each system are displayed.
    * **Live Cursor Position:** Cursor position over the image is displayed live, transformed into each coordinate system, in both pixels and meters (if scale is set).
    * Toggle the visibility of the effective origin marker using the "Show Origin" checkbox. Marker appearance customizable via Preferences.
* **Data Display & UI:**
    * Resizable main window split between the video view/controls (left) and data/settings panels (right).
    * "Tracks" tab: Lists tracks with controls for quick save/copy, creation, deletion, and visibility.
    * "Measurement Lines" tab: Lists lines with controls for quick save/copy, creation, deletion, and visibility. Displays line length and angle.
    * "Points" tab: Displays points (Frame, Time (s), X, Y) for the active track or the two endpoints of an active measurement line. Column headers (X, Y) indicate current display units.
    * Collapsible side panels for "Scale Configuration" and "Coordinate System".
* **Project Save/Load (JSON Format):**
    * **Save Project:** `File -> Save Project` (`Ctrl+S`) saves the current project to its existing file path. If the project is new, it behaves like "Save Project As...".
    * **Save Project As...:** `File -> Save Project As...` saves the entire project state (all element data, video path, scale settings, coordinate system settings, relevant UI toggle states) to a new or chosen `.json` file. Element coordinates are always saved as raw Top-Left pixel values.
    * **Load Project:** `File -> Open Project...` loads a project from a `.json` file, restoring elements, settings, and attempting to reload the associated video. Issues warnings if saved video metadata mismatches the currently loaded video.
    * **Close Project:** `File -> Close Project` closes the current video and project, prompting to save unsaved changes.
* **Data Export (Simplified CSV):**
    * `File -> Export Data -> Export Tracks (as CSV)...`: Exports all track data to a simple CSV file.
    * `File -> Export Data -> Export Lines (as CSV)...`: Exports all measurement line data (endpoints, length, angle) to a simple CSV.
    * **Unit Choice:** For both export types, a dialog prompts the user to choose between "Pixel Coordinates (current display system)" or "Real-World Units (meters, if scale is set)".
    * **Quick Save/Copy Buttons:** Save (💾) and Copy (📋) icon buttons are available above the Tracks and Lines tables for quick CSV export/copy using the *current display units* without an explicit prompt.
* **Visual Exporting:**
    * **Export Video with Overlays:** `File -> Export Video with Overlays...` allows exporting a video sequence (full or custom range) with all visible overlays rendered. Options for format (MP4/AVI) and resolution (viewport/original).
    * **Export Current Frame to PNG:** `File -> Export Current Frame to PNG...` saves the current frame with overlays as a PNG. Option for viewport or original resolution.
* **Preferences:** Customize visual settings (track/origin colors and sizes, scale line/bar appearance, info overlay appearance, measurement line appearance) via `Edit -> Preferences...`. Settings are persisted.
* **Video Information:** View technical metadata from the loaded video via `File -> Video Information...`.
* **Logging:** Diagnostic information printed to console.

## Developer Requirements

* Python 3.x (Developed with 3.9+)
* PySide6 (`pip install PySide6`)
* OpenCV for Python (`pip install opencv-python`)
* NumPy (usually installed as a dependency with OpenCV) (`pip install numpy`)
* Pillow (`pip install Pillow`) (Needed for icon conversion during automated builds)

*(Note: The Python standard libraries `csv`, `os`, `math`, `logging`, `enum`, `sys`, `typing`, `re`, `json`, `io` are also used but do not require separate installation).*

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
    * Go to `File -> Open Video...`.
    * Navigate frames (slider, buttons, mouse wheel, time/frame input). Play/pause with `Spacebar`.
    * Zoom/Pan (`Ctrl+Scroll`, Left-Click-Drag). Reset view with overlay button.
    * **(Optional) Set Scale:** Use "Scale Configuration" panel (manual input or "Set" from feature).
    * Select "Coordinate System" and optionally "Pick Custom" origin. Observe live cursor coordinates.
    * **Toggle Overlays:** Use `View` menu or panel checkboxes.
    * Create elements: "New" button in "Tracks" tab (or `Ctrl+N`) for tracks; "New" button in "Measurement Lines" tab for lines.
    * **Select Active Element:** Click its row in the respective table, or `Ctrl+Click` a track marker.
    * **Add/Update Track Points:** For an active track, left-click on the video.
    * **Define Line Endpoints:** For an active (new) line, click two points on the same frame. Hold `Shift` for angle snapping.
    * **Delete Point (Tracks):** `Delete`/`Backspace` for active track's point on current frame.
    * **Undo Point Operation (Tracks):** `Edit -> Undo Point Action` or `Ctrl+Z`.
    * **Delete Element:** Click trash icon (🗑️) in "Tracks" or "Measurement Lines" table.
    * **Save/Load Project:** Use `File -> Save Project` (`Ctrl+S`), `File -> Save Project As...`, and `File -> Open Project...` for JSON project files. Use `File -> Close Project` to close the current work.
    * **Export Data:** Use `File -> Export Data` submenu for CSVs, or quick Save/Copy icons on element tabs.
    * **Export Visuals:** Use `File -> Export Video with Overlays...` or `File -> Export Current Frame to PNG...`.
    * **Customize:** `Edit -> Preferences...`.
    * **View Info:** `File -> Video Information...`.
    * **About:** `Help -> About`.

## File Structure

* `main.py`: Entry point script; initializes QApplication, logging, and MainWindow.
* `config.py`: Shared constants (metadata keys, table indices, default styles, app info).
* `coordinates.py`: `CoordinateSystem` enum and `CoordinateTransformer` class for coordinate management.
* `scale_manager.py`: `ScaleManager` class; manages pixel-to-meter scale factor, display units, and defined scale line data.
* `scale_bar_widget.py`: `ScaleBarWidget` class; custom widget for drawing the dynamic on-screen scale bar.
* `info_overlay_widget.py`: `InfoOverlayWidget` class; custom widget for rendering fixed informational text overlays (filename, time, frame number) on the image view.
* `settings_manager.py`: Manages persistent application settings (visuals) using QSettings.
* `ui_setup.py`: Function `setup_main_window_ui` to create and arrange GUI widgets and menus for the `MainWindow`.
* `main_window.py`: `MainWindow` class; orchestrates core components, main application signals/slots, menu actions, and drawing of scene overlays.
* `interactive_image_view.py`: `InteractiveImageView` class (QGraphicsView) for frame display, mouse interaction (including angle snapping for scale/measurement lines), and hosting overlay widgets.
* `video_handler.py`: `VideoHandler` class; manages video loading (OpenCV), playback (QTimer), navigation, frame extraction.
* `element_manager.py`: `ElementManager` class; stores and manages multi-element (tracks, lines) point data, visibility settings, and point operation undo logic.
* `project_manager.py`: `ProjectManager` class; orchestrates saving/loading of JSON project files, and tracks unsaved changes.
* `file_io.py`: Functions for JSON project file reading/writing and data-only CSV export. Includes `UnitSelectionDialog`.
* `export_handler.py`: `ExportHandler` class; manages logic for exporting video frames with overlays as new video files or individual images.
* `export_options_dialog.py`: `ExportOptionsDialog` class for selecting video export range and resolution.
* `panel_controllers.py`: Contains controller classes (`ScalePanelController`, `CoordinatePanelController`, `GetDistanceDialog`) that manage UI logic for specific QGroupBox panels.
* `table_controllers.py`: Contains `TrackDataViewController` class that manages UI logic for the Tracks, Lines, and Points data tables.
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

* **Adjusting Line Endpoints:** Allow users to graphically select and modify the endpoints of existing measurement lines. (Phase D)
* **Undo/Redo for Line Operations:** Integrate line creation, deletion, and endpoint modification into the undo system. (Phase E)
* Add basic data analysis capabilities (e.g., velocity calculation, track plotting).
* Enhance logging configuration (e.g., allow user to set level, log to file).
* Replace standard text/pixmap overlay buttons with custom SVG icons for a cleaner look.
* Consider adding unit tests for core logic.
* Improve error handling for invalid video files or corrupted project files.
* Add more video export format options with clear indication of codec dependencies.
* Consider Redo functionality for point/element operations.