# Map Enhancer Wizard (V2)

<img width="1847" height="1051" alt="Map Enhancer Wizard Banner" src="https://github.com/user-attachments/assets/c11b2135-a6a7-41ce-82ab-2d8217158592" />

**Map Enhancer Wizard** is a *Tkinter*-based graphical user interface (*GUI*) application designed to enhance 2D Occupancy Grid maps for robotics and navigation applications. It provides an intuitive interface to load, filter, and optimize maps, with features like kernel-based optimization, corner anchor detection, and interactive control point manipulation. The tool is ideal for refining maps used in *SLAM* (Simultaneous Localization and Mapping) or robotic path planning, offering real-time previews and customizable enhancement parameters.

The wizard guides users through a step-by-step process, supporting map loading, filtering (erosion, dilation, Gaussian blur), kernel optimization, and saving enhanced maps in *YAML* and image formats (e.g., *.pgm*).

## Key Features

* **Map Loading**: Load 2D Occupancy Grid maps from *.yaml* files with associated *.pgm* images.
* **Filtering**: Apply morphological operations (erosion, dilation) and Gaussian blur with adjustable parameters.
* **Kernel Optimization**: Optimize map features using control points with user-defined constraints and corner anchoring.
* **Interactive Canvas**: Add/remove constraint pairs, pan/zoom, and preview changes in real-time.
* **Corner Anchor Detection**: Automatically detect and fix corner points to preserve map structure.
* **History and Undo**: Save snapshots and revert changes.
* **Export Options**: Save enhanced maps as *.yaml* and *.pgm* files.
* **Coming Soon**: Automation features, AI-powered enhancements, and 3D map support.

## Code Structure

The codebase is organized in a modular structure for maintainability, with classes and utilities separated by functionality. Here's the directory layout:

```
Map_Enhancer_Wizard/
├── classes/
│   ├── map_enhancer_wizard.py  # Main wizard class handling UI and map processing
│   ├── optimizer.py  # Kernel optimization and corner anchor detection logic
│   ├── tooltip.py  # Tooltip functionality for UI elements
├── util/
│   ├── clamp.py  # Utility to clamp values within a range
│   ├── cv_to_photo.py  # Converts OpenCV images to Tkinter PhotoImage
│   ├── linux_mousewheel_bind.py  # Cross-platform mouse wheel event binding
│   ├── morphological_kernel.py  # Generates morphological kernels for OpenCV
│   ├── safe_float.py  # Safely converts values to float
│   ├── safe_int.py  # Safely converts values to integer
├── main.py  # Entry point to run the application
└── README.md
```

* **`classes/`**: Core application logic, including the main wizard, optimization, and tooltip classes.
* **`util/`**: Shared utility functions for image conversion, value clamping, and platform-specific bindings.
* **`main.py`**: The main script to launch the wizard.

## Installation and Usage

### Prerequisites

* **Python**: *3.8+* (tested on *3.8* and *3.10*).
* **Dependencies**: Install required libraries:
  ```bash
  pip install opencv-python pillow pyyaml numpy
  ```
* **Map Files**: Ensure 2D Occupancy Grid maps include a *.yaml* file and a corresponding *.pgm* image in the same directory.

### Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/ali-pahlevani/Map_Enhancer_Wizard.git
   cd Map_Enhancer_Wizard/code
   ```

2. **Run the Application**:
   Run the main file:
   ```bash
   python3 main.py
   ```

### Troubleshooting Installation

* **Tkinter Errors**: Ensure Tkinter is installed (usually included with Python; on Linux, install `python3-tk`).
* **OpenCV Errors**: Verify `opencv-python` is installed correctly (`pip install opencv-python`).
* **Map Loading Issues**: Ensure the *.yaml* file specifies the correct image file path and that both files are in the same directory.
* **Display Issues**: On *WSL* or Linux, ensure a display server is running (e.g., `export DISPLAY=:0` or use an *X server* like *Xming*).

## Tutorial: Enhancing a 2D Occupancy Grid Map

The wizard provides a tabbed interface for map enhancement. Below is a step-by-step guide to using the tool.

### Step 1: Load Map

* **Open Map**: Click *File* > *Open Map* and select a *.yaml* file containing map metadata and a *.pgm* image.
* The map appears in the *Original* tab of the canvas.
* **Note**: The *.yaml* file must reference a valid *.pgm* image in the same directory.

<img width="1847" height="1051" alt="Load Map" src="https://github.com/user-attachments/assets/5cb10ae2-ac0a-4671-b6e7-299dff8e3c10" />

### Step 2: Apply Filters

* Switch to the *Filtering* tab.
* **Adjust Parameters**:
  * **Erosion/Dilation Size**: Set kernel size for morphological operations (odd numbers, e.g., *3*, *5*).
  * **Gaussian Blur Size**: Set blur kernel size (odd numbers, e.g., *3*, *5*).
  * **Gaussian Sigma**: Adjust blur strength (e.g., *0.0* for no blur).
* **Apply Filters**: Click *Apply* to process the map and view results in the *Filtered* tab.
* **Canvas Controls**: Zoom with the mouse wheel, pan with the middle mouse button, press *F* to fit the window.

<img width="1847" height="1051" alt="Filtering" src="https://github.com/user-attachments/assets/d97f9c77-0c0f-45eb-854c-3e5e0f451715" />

### Step 3: Optimize Map

* Switch to the *Optimization* tab.
* **Generate Control Points**:
  * Set *N points* (e.g., *2000*) and click *Generate (occupied only)* to create control points on occupied (black) pixels.
* **Add Constraints**:
  * Click two red control points on the canvas to toggle a green constraint line.
  * Double-click a point to remove its connections.
* **Adjust Parameters**:
  * **Kernel Size**: Size of kernels carried by control points (odd, e.g., *5*).
  * **Step α**: Gradient step size (e.g., *0.05*).
  * **Line Weight λc**: Constraint strength (e.g., *2.0*).
  * **Elastic Weight λs**: Neighbor smoothing (e.g., *0.08*).
  * **Neighbor Radius**: Influence radius (e.g., *8* pixels).
  * **Max Iters/Tol**: Optimization limits (e.g., *100*, *1e-3*).
* **Corner Anchor Settings**:
  * **Angle Band**: Range for corner detection (e.g., *85°–95°*).
  * **Quality Level**: Corner strictness (0–1, e.g., *0.05*).
  * **2nd Peak**: Minimum count or ratio for secondary angle peak (e.g., *5*, *0.20*).
* **Run Optimization**:
  * Click *Start* for continuous optimization, *Step Once* for single iteration, or *Stop* to halt.
  * View progress in *Status* (iteration count, score).
* **Apply/Revert**: Click *Apply to Enhanced* to save changes or *Revert Working* to undo.
* **Canvas Controls**: Same as filtering (zoom, pan, fit).

<img width="1847" height="1051" alt="Optimization_1" src="https://github.com/user-attachments/assets/a9a5923d-2d0c-4c0b-b284-cce048d44967" />

<img width="1847" height="1051" alt="Optimization_2" src="https://github.com/user-attachments/assets/eb0c1546-5c92-44d1-a870-a6c9646cad1f" />

### Step 4: Save Enhanced Map

* Click *File* > *Save Enhanced Map* to export the optimized map as *.yaml* and *.pgm* files.
* Choose a directory to save the files.

<img width="1847" height="1051" alt="SaveMap_1" src="https://github.com/user-attachments/assets/9195f472-8be8-4756-886e-fb8f798fe510" />

<img width="1847" height="1051" alt="SaveMap_2" src="https://github.com/user-attachments/assets/31bcbce2-b683-442b-8119-a8e5918332ef" />

## Future Visions

**Map Enhancer Wizard** is a foundation for an open-source 2D map enhancement tool. Planned enhancements include:

* **Additional Filters**: Advanced morphological and AI-based processing.
* **Automation**: One-click map enhancement workflows.
* **3D Map Support**: Extend to 3D occupancy grids and point clouds.
* **Performance Optimizations**: Faster processing for large maps.
* **UI Enhancements**: Improved canvas controls and undo/redo functionality.
* **And definitely a lot more!!!**

I’d **love collaborations**! Contribute via pull requests on *GitHub* for bug fixes, new features, or documentation improvements. Reach out via *GitHub Issues* for questions, suggestions, or partnership ideas.

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository.
2. Create a branch (`git checkout -b feature/your-feature`).
3. Commit changes (`git commit -m "Add your feature"`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a pull request.

Please include tests and documentation updates. For major changes, discuss in a *GitHub Issue* first.

## Limitations and Known Issues

* Limited to 2D Occupancy Grid maps (*.yaml* + *.pgm*).
* No AI or automation features in this version.
* Large maps (>50000 pixels) may require downsampling for control point generation.
* Corner anchor detection may miss subtle corners (adjust *qualityLevel* or angle band).

Report issues or suggestions on the *GitHub* repository.

---

+ If you have any questions, please let me know: **a.pahlevani1998@gmail.com**

+ Also, don't forget to check out our **website** at: **https://www.SLAMbotics.org**
