# Map Enhancer Wizard (V1)

**Map Enhancer Wizard** is a tool designed to enhance 2D Occupancy Grid maps and experimental 3D maps, providing users with an easy way to improve map quality through a user-friendly interface.

Current features include thresholding, blurring, and morphological operations such as opening, closing, dilation, and erosion to correct common mapping artifacts in 2D maps. A basic 3D viewer is also included that can load `.db` files containing point data.

This is **version 1** of the tool. Future versions will include:

- **Additional filters** for more versatile map enhancements
- **Automation features** to streamline the enhancement process
- **AI-powered enhancements** for intelligent map improvements
- More advanced **3D map** processing
 
## Preview

![Map Enhancer Wizard Preview](https://github.com/user-attachments/assets/4dbd4538-ddf7-4dc9-af1a-184c2ab03395)

## Dependencies

To use this tool, you need to have the following Python packages installed:

- opencv-python
- pillow
- pyyaml
- numpy
- matplotlib *(for the 3D viewer)*

You can install these dependencies using **pip**:

```bash
pip install opencv-python pillow pyyaml numpy matplotlib
```

## Usage

The main file to run is `map_enhancer_wizard.py`. To start the wizard, simply execute the following command in your **terminal**:

```bash
python3 code/map_enhancer_wizard.py
```

After launching you can choose between the 2D and 3D modules.

* For **2D maps**, ensure the selected folder contains a **.yaml** file along with its corresponding image file (e.g., **.pgm**).
* For **3D maps**, simply provide a SQLite **.db** file. The viewer scans the
  database for tables containing 3D coordinates (`x`, `y`, `z`,
  `pose_x`, `pose_y`, `pose_z`), or even a binary `pose` blob as used by
  **RTAB‑Map**'s `Node` table. Any detected data are converted into a point
  cloud for basic visualisation.

## Examples

Below are example collages demonstrating the enhancement results. Each collage includes **four images**: **two** showing the **occupancy map** before and after enhancement, and **two** showing the corresponding **cost maps** before and after enhancement.

### Example 1
![Example 1: Occupancy and Cost Map Enhancement](https://github.com/user-attachments/assets/4149fe0b-3bf4-4f04-b520-a2f0fa883235)

### Example 2
![Example 2: Occupancy and Cost Map Enhancement](https://github.com/user-attachments/assets/0fe744f3-6ae5-4f06-a868-0dde060fb924)

### Example 3
![Example 3: Occupancy and Cost Map Enhancement](https://github.com/user-attachments/assets/608c0558-aa63-478e-a97b-4ef6fc729e13)

## Limitations and Known Issues

As this is version 1, there are some **limitations**:

- Limited set of enhancement filters
- 3D support is minimal: it looks for raw coordinate columns or the
  translation part of a `pose` blob. Complex RTAB‑Map features such as
  compressed scans are not yet handled
- No automation or AI features yet
- May not handle very large maps efficiently

If you encounter any issues or have suggestions for future versions, please **open an issue** on the GitHub repository.

## Contributing

Contributions are welcome! If you'd like to add new features, fix bugs, or improve the documentation, please **fork the repository** and submit a **pull request**.

Please ensure your code follows the project's coding standards and includes appropriate tests.

## Support

If you have any questions, please let me know: **a.pahlevani1998@gmail.com**

+ Also, please don't forget to check out our **website** at: **https://www.SLAMbotics.org**

## Please stay tuned for the next versions of the app.
