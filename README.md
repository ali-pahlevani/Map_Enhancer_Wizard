# Map Enhancer Wizard (V1)

**Map Enhancer Wizard** is a tool designed to enhance 2D Occupancy Grid maps, providing users with an easy way to improve the quality and usability of their maps through a user-friendly interface.

This is **version 1** of the tool. Future versions will include:

- **Additional filters** for more versatile map enhancements
- **Automation features** to streamline the enhancement process
- **AI-powered enhancements** for intelligent map improvements
- Support for **3D maps**

## Preview

![Map Enhancer Wizard Preview](https://github.com/user-attachments/assets/4dbd4538-ddf7-4dc9-af1a-184c2ab03395)

## Dependencies

To use this tool, you need to have the following Python packages installed:

- opencv-python
- pillow
- pyyaml
- numpy

You can install these dependencies using **pip**:

```bash
pip install opencv-python pillow pyyaml numpy
```

## Usage

The main file to run is `map_enhancer_wizard.py`. To start the wizard, simply execute the following command in your **terminal**:

```bash
python3 map_enhancer_wizard.py
```

Follow the on-screen **instructions** to load your 2D Occupancy Grid map and apply enhancements.

The wizard will guide you through the process of enhancing your map, allowing you to choose from available options and preview changes before saving.

+ **Note:** Ensure your 2D Occupancy Grid map is in a compatible format. The tool expects a **.yaml** file along with its corresponding image file (e.g., **.pgm**). Basically, you’ll need to **double-click** and select the folder that **contains both** the .yaml and image file of your map.

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
- Only supports 2D Occupancy Grid maps
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
