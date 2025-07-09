# Map Enhancer Wizard

**Map Enhancer Wizard** is a tool designed to enhance 2D Occupancy Grid maps, providing users with an easy way to improve the quality and usability of their maps through a user-friendly interface.

This is **version 1** of the tool. Future versions will include:

- Additional filters for more versatile map enhancements
- Automation features to streamline the enhancement process
- AI-powered enhancements for intelligent map improvements
- Support for 3D maps

## Dependencies

To use this tool, you need to have the following Python packages installed:

- opencv-python
- pillow
- pyyaml
- numpy

You can install these dependencies using pip:

```bash
pip install opencv-python pillow pyyaml numpy
```

## Usage

The main file to run is `map_enhancer_wizard.py`. To start the wizard, simply execute the following command in your terminal:

```bash
python map_enhancer_wizard.py
```

Follow the on-screen instructions to load your 2D Occupancy Grid map and apply enhancements.

The wizard will guide you through the process of enhancing your map, allowing you to choose from available options and preview changes before saving.

**Note:** Ensure your 2D Occupancy Grid map is in a compatible format. The tool expects maps to be in YAML format, typically with an associated image file (e.g., .pgm).

## Limitations and Known Issues

As this is version 1, there are some limitations:

- Limited set of enhancement filters
- Only supports 2D Occupancy Grid maps
- No automation or AI features yet
- May not handle very large maps efficiently

If you encounter any issues or have suggestions for future versions, please open an issue on the GitHub repository.

## Contributing

Contributions are welcome! If you'd like to add new features, fix bugs, or improve the documentation, please fork the repository and submit a pull request.

Please ensure your code follows the project's coding standards and includes appropriate tests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

If you need help or have questions, please open an issue on the GitHub repository.