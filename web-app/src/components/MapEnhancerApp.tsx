import React, { useState, useCallback } from 'react';
import { MapData, FilterSettings, ProcessingState, MapMetadata } from '@/types/map';
import { MapCanvas } from '@/components/MapCanvas';
import { ControlPanel } from '@/components/ControlPanel';

export default function MapEnhancerApp() {
  const [mapData, setMapData] = useState<MapData>({
    originalImage: null,
    processedImage: null,
    metadata: null,
    fileName: ''
  });

  const [filters, setFilters] = useState<FilterSettings>({
    blur: 0,
    dilation: 0,
    erosion: 0,
    opening: 0
  });

  const [processingState, setProcessingState] = useState<ProcessingState>({
    isLoading: false,
    error: null,
    progress: 0
  });

  const [processedImage, setProcessedImage] = useState<ImageData | null>(null);

  const handleFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;

    setProcessingState({ isLoading: true, error: null, progress: 0 });

    try {
      let pgmFile: File | null = null;
      let yamlFile: File | null = null;

      // Find PGM and YAML files
      for (const file of Array.from(files)) {
        if (file.name.endsWith('.pgm')) {
          pgmFile = file;
        } else if (file.name.endsWith('.yaml') || file.name.endsWith('.yml')) {
          yamlFile = file;
        }
      }

      if (!pgmFile || !yamlFile) {
        throw new Error('Please select both PGM and YAML files');
      }

      // Parse YAML metadata
      const yamlText = await yamlFile.text();
      const metadata: MapMetadata = parseYaml(yamlText);

      // Load PGM image
      const imageData = await loadPGMImage(pgmFile);

      setMapData({
        originalImage: imageData,
        processedImage: null,
        metadata,
        fileName: pgmFile.name.replace('.pgm', '')
      });

      setProcessingState({ isLoading: false, error: null, progress: 100 });
    } catch (error) {
      setProcessingState({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to load map',
        progress: 0
      });
    }
  }, []);

  const loadPGMImage = async (file: File): Promise<ImageData> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const arrayBuffer = e.target?.result as ArrayBuffer;
          const uint8Array = new Uint8Array(arrayBuffer);
          
          // Parse PGM header
          let offset = 0;
          const decoder = new TextDecoder();
          
          // Read header line by line
          let headerComplete = false;
          let width = 0;
          let height = 0;
          let maxVal = 255;
          let headerLines = 0;
          
          while (!headerComplete && offset < uint8Array.length) {
            let lineEnd = offset;
            while (lineEnd < uint8Array.length && uint8Array[lineEnd] !== 10) { // \n
              lineEnd++;
            }
            
            const line = decoder.decode(uint8Array.slice(offset, lineEnd)).trim();
            
            if (line.startsWith('#')) {
              // Comment line, skip
            } else if (headerLines === 0 && line === 'P5') {
              // Magic number
              headerLines++;
            } else if (headerLines === 1) {
              // Width and height
              const [w, h] = line.split(' ').map(Number);
              width = w;
              height = h;
              headerLines++;
            } else if (headerLines === 2) {
              // Max value
              maxVal = Number(line);
              headerComplete = true;
            }
            
            offset = lineEnd + 1;
          }
          
          // Create ImageData from pixel data
          const pixelData = uint8Array.slice(offset);
          const imageData = new ImageData(width, height);
          
          for (let i = 0; i < pixelData.length; i++) {
            const value = pixelData[i];
            const idx = i * 4;
            imageData.data[idx] = value;     // R
            imageData.data[idx + 1] = value; // G
            imageData.data[idx + 2] = value; // B
            imageData.data[idx + 3] = 255;   // A
          }
          
          resolve(imageData);
        } catch (error) {
          reject(new Error('Failed to parse PGM file'));
        }
      };
      reader.onerror = () => reject(new Error('Failed to read file'));
      reader.readAsArrayBuffer(file);
    });
  };

  const parseYaml = (yamlText: string): MapMetadata => {
    // Simple YAML parser for map metadata
    const lines = yamlText.split('\n');
    const metadata: any = {};
    
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('#')) {
        const [key, ...valueParts] = trimmed.split(':');
        if (key && valueParts.length > 0) {
          const value = valueParts.join(':').trim();
          
          // Parse different value types
          if (value.startsWith('[') && value.endsWith(']')) {
            // Array
            metadata[key.trim()] = value.slice(1, -1).split(',').map(v => Number(v.trim()));
          } else if (!isNaN(Number(value))) {
            // Number
            metadata[key.trim()] = Number(value);
          } else {
            // String
            metadata[key.trim()] = value;
          }
        }
      }
    }
    
    return metadata as MapMetadata;
  };

  const handleReset = () => {
    setFilters({
      blur: 0,
      dilation: 0,
      erosion: 0,
      opening: 0
    });
  };

  const handleSave = async () => {
    if (!processedImage || !mapData.metadata) {
      alert('No processed image to save');
      return;
    }

    try {
      // Create canvas and draw processed image
      const canvas = document.createElement('canvas');
      canvas.width = processedImage.width;
      canvas.height = processedImage.height;
      const ctx = canvas.getContext('2d')!;
      ctx.putImageData(processedImage, 0, 0);

      // Convert to blob and download
      canvas.toBlob((blob) => {
        if (blob) {
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `${mapData.fileName}_enhanced.png`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
        }
      }, 'image/png');

      // Also download updated YAML
      const updatedMetadata = {
        ...mapData.metadata,
        image: `${mapData.fileName}_enhanced.png`
      };

      const yamlContent = Object.entries(updatedMetadata)
        .map(([key, value]) => {
          if (Array.isArray(value)) {
            return `${key}: [${value.join(', ')}]`;
          }
          return `${key}: ${value}`;
        })
        .join('\n');

      const yamlBlob = new Blob([yamlContent], { type: 'text/yaml' });
      const yamlUrl = URL.createObjectURL(yamlBlob);
      const yamlLink = document.createElement('a');
      yamlLink.href = yamlUrl;
      yamlLink.download = `${mapData.fileName}_enhanced.yaml`;
      document.body.appendChild(yamlLink);
      yamlLink.click();
      document.body.removeChild(yamlLink);
      URL.revokeObjectURL(yamlUrl);

    } catch (error) {
      alert('Failed to save files');
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = '.pgm,.yaml,.yml';
    
    // Create a new FileList-like object
    Object.defineProperty(input, 'files', {
      value: files,
      writable: false
    });
    
    handleFileUpload({ target: input } as any);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Map Enhancer Wizard
            </h1>
            <p className="text-sm text-gray-600">
              Modern web-based 2D occupancy grid map enhancement tool
            </p>
          </div>
          
          <div className="flex items-center space-x-4">
            <input
              type="file"
              multiple
              accept=".pgm,.yaml,.yml"
              onChange={handleFileUpload}
              className="hidden"
              id="file-upload"
            />
            <label
              htmlFor="file-upload"
              className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 cursor-pointer font-medium"
            >
              Select Map Files
            </label>
            
            {processingState.isLoading && (
              <div className="flex items-center space-x-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                <span className="text-sm text-gray-600">Loading...</span>
              </div>
            )}
          </div>
        </div>
        
        {processingState.error && (
          <div className="mt-2 text-sm text-red-600 bg-red-50 p-2 rounded">
            {processingState.error}
          </div>
        )}
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        <ControlPanel
          filters={filters}
          onFiltersChange={setFilters}
          onReset={handleReset}
          onSave={handleSave}
          isProcessing={processingState.isLoading}
        />
        
        <div
          className="flex-1 p-6"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <MapCanvas
            mapData={mapData}
            filters={filters}
            onProcessedImageChange={setProcessedImage}
          />
        </div>
      </div>

      {/* Status Bar */}
      <footer className="bg-white border-t border-gray-200 px-6 py-2">
        <div className="flex items-center justify-between text-sm text-gray-600">
          <div>
            {mapData.originalImage ? (
              <span>Map loaded: {mapData.fileName} ({mapData.originalImage.width}×{mapData.originalImage.height})</span>
            ) : (
              <span>Select a map folder to begin</span>
            )}
          </div>
          <div className="text-xs">
            Version 2.0 | Built with React & Next.js
          </div>
        </div>
      </footer>
    </div>
  );
}
