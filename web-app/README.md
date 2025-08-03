# Map Enhancer Wizard - Web Application

A modern React-based web application for enhancing 2D occupancy grid maps, built with Next.js and TypeScript.

## Features

- **Modern Web Interface**: Clean, responsive design built with React and Tailwind CSS
- **Real-time Processing**: Live preview of filter applications
- **Interactive Canvas**: Zoom, pan, and navigate through your map
- **Multiple Filters**: Blur, dilation, erosion, and morphological opening
- **File Support**: Upload PGM + YAML map files

## Technologies

- **Frontend**: React 18, Next.js 14, TypeScript
- **Styling**: Tailwind CSS for modern, responsive design
- **Image Processing**: Canvas API for client-side image manipulation
- **File Handling**: Native browser APIs for file upload/download

## Quick Start

1. **Install Dependencies**
   ```bash
   cd web-app
   npm install
   ```

2. **Start Development Server**
   ```bash
   npm run dev
   ```

3. **Open Browser**
   Navigate to `http://localhost:3000`

4. **Upload Maps**
   - Click "Select Map Files" or drag & drop
   - Choose both PGM and YAML files
   - Start enhancing your maps!

## Usage

1. **Load Map**: Upload your PGM (image) and YAML (metadata) files
2. **Adjust Filters**: Use the control panel to fine-tune enhancement parameters
3. **Preview**: See real-time changes in the map canvas
4. **Navigate**: Zoom and pan to inspect details
5. **Export**: Save enhanced map and updated metadata

## Filter Descriptions

- **Blur**: Smooths noise using Gaussian blur
- **Dilation**: Expands occupied areas (safer navigation)
- **Erosion**: Shrinks occupied areas (refined boundaries)
- **Opening**: Removes small noise objects

## Development

```bash
# Development server
npm run dev

# Type checking
npm run type-check

# Build for production
npm run build

# Start production server
npm start
```


