import { FilterSettings } from '@/types/map';

// Image processing utilities for client-side canvas operations
export class ImageProcessor {
  
  static applyGaussianBlur(imageData: ImageData, kernelSize: number): ImageData {
    if (kernelSize === 0) return imageData;
    
    const { width, height, data } = imageData;
    const output = new Uint8ClampedArray(data);
    const radius = kernelSize;
    const sigma = radius / 3;
    
    // Create Gaussian kernel
    const kernel: number[] = [];
    const kernelSum = [];
    let sum = 0;
    
    for (let x = -radius; x <= radius; x++) {
      const value = Math.exp(-(x * x) / (2 * sigma * sigma));
      kernel.push(value);
      sum += value;
    }
    
    // Normalize kernel
    for (let i = 0; i < kernel.length; i++) {
      kernel[i] /= sum;
    }
    
    // Apply horizontal blur
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        let r = 0, g = 0, b = 0;
        
        for (let kx = -radius; kx <= radius; kx++) {
          const px = Math.max(0, Math.min(width - 1, x + kx));
          const idx = (y * width + px) * 4;
          const weight = kernel[kx + radius];
          
          r += data[idx] * weight;
          g += data[idx + 1] * weight;
          b += data[idx + 2] * weight;
        }
        
        const idx = (y * width + x) * 4;
        output[idx] = r;
        output[idx + 1] = g;
        output[idx + 2] = b;
      }
    }
    
    // Apply vertical blur
    const temp = new Uint8ClampedArray(output);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        let r = 0, g = 0, b = 0;
        
        for (let ky = -radius; ky <= radius; ky++) {
          const py = Math.max(0, Math.min(height - 1, y + ky));
          const idx = (py * width + x) * 4;
          const weight = kernel[ky + radius];
          
          r += temp[idx] * weight;
          g += temp[idx + 1] * weight;
          b += temp[idx + 2] * weight;
        }
        
        const idx = (y * width + x) * 4;
        output[idx] = r;
        output[idx + 1] = g;
        output[idx + 2] = b;
      }
    }
    
    return new ImageData(output, width, height);
  }

  static applyThreshold(imageData: ImageData, threshold: number): ImageData {
    const data = new Uint8ClampedArray(imageData.data);
    const thresholdValue = threshold * 255;
    
    for (let i = 0; i < data.length; i += 4) {
      // Convert to grayscale first
      const gray = (data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114);
      const binary = gray <= thresholdValue ? 0 : 255;
      data[i] = binary;     // R
      data[i + 1] = binary; // G
      data[i + 2] = binary; // B
      // Alpha stays the same
    }
    
    return new ImageData(data, imageData.width, imageData.height);
  }

  static applyMorphology(imageData: ImageData, operation: 'dilation' | 'erosion' | 'opening' | 'closing', kernelSize: number): ImageData {
    if (kernelSize === 0) return imageData;
    
    const { width, height } = imageData;
    const data = new Uint8ClampedArray(imageData.data);
    const output = new Uint8ClampedArray(data);
    
    const radius = Math.floor(kernelSize / 2);
    
    for (let y = radius; y < height - radius; y++) {
      for (let x = radius; x < width - radius; x++) {
        const idx = (y * width + x) * 4;
        
        let value: number;
        
        if (operation === 'dilation') {
          // Dilation: take minimum value in kernel (expands black areas/obstacles)
          value = 255;
          for (let ky = -radius; ky <= radius; ky++) {
            for (let kx = -radius; kx <= radius; kx++) {
              const kidx = ((y + ky) * width + (x + kx)) * 4;
              value = Math.min(value, data[kidx]);
            }
          }
        } else { // erosion
          // Erosion: take maximum value in kernel (shrinks black areas/obstacles)
          value = 0;
          for (let ky = -radius; ky <= radius; ky++) {
            for (let kx = -radius; kx <= radius; kx++) {
              const kidx = ((y + ky) * width + (x + kx)) * 4;
              value = Math.max(value, data[kidx]);
            }
          }
        }
        
        output[idx] = value;
        output[idx + 1] = value;
        output[idx + 2] = value;
      }
    }
    
    return new ImageData(output, width, height);
  }

  static processImage(originalImageData: ImageData, filters: FilterSettings): ImageData {
    let processed = new ImageData(
      new Uint8ClampedArray(originalImageData.data),
      originalImageData.width,
      originalImageData.height
    );
    
    // Apply filters in the correct sequence
    
    // 1. Apply blur first (for noise reduction)
    if (filters.blur > 0) {
      processed = this.applyGaussianBlur(processed, filters.blur);
    }
    
    // 2. Apply morphological opening (erosion followed by dilation) - removes noise
    if (filters.opening > 0) {
      processed = this.applyMorphology(processed, 'erosion', filters.opening);
      processed = this.applyMorphology(processed, 'dilation', filters.opening);
    }
    
    // 3. Apply dilation (expand white areas - make obstacles thicker)
    if (filters.dilation > 0) {
      processed = this.applyMorphology(processed, 'dilation', filters.dilation);
    }
    
    // 4. Apply erosion (shrink white areas - make obstacles thinner)
    if (filters.erosion > 0) {
      processed = this.applyMorphology(processed, 'erosion', filters.erosion);
    }
    
    return processed;
  }

  // Helper method to draw obstacles
  static drawLine(imageData: ImageData, x1: number, y1: number, x2: number, y2: number, color: [number, number, number] = [0, 0, 0]): ImageData {
    const data = new Uint8ClampedArray(imageData.data);
    const { width, height } = imageData;
    
    const dx = Math.abs(x2 - x1);
    const dy = Math.abs(y2 - y1);
    const sx = x1 < x2 ? 1 : -1;
    const sy = y1 < y2 ? 1 : -1;
    let err = dx - dy;
    
    let x = x1;
    let y = y1;
    
    while (true) {
      if (x >= 0 && x < width && y >= 0 && y < height) {
        const idx = (y * width + x) * 4;
        data[idx] = color[0];
        data[idx + 1] = color[1];
        data[idx + 2] = color[2];
      }
      
      if (x === x2 && y === y2) break;
      
      const e2 = 2 * err;
      if (e2 > -dy) {
        err -= dy;
        x += sx;
      }
      if (e2 < dx) {
        err += dx;
        y += sy;
      }
    }
    
    return new ImageData(data, width, height);
  }

  static drawRectangle(imageData: ImageData, x: number, y: number, width: number, height: number, color: [number, number, number] = [0, 0, 0]): ImageData {
    const data = new Uint8ClampedArray(imageData.data);
    const imgWidth = imageData.width;
    const imgHeight = imageData.height;
    
    for (let dy = 0; dy < height; dy++) {
      for (let dx = 0; dx < width; dx++) {
        const px = x + dx;
        const py = y + dy;
        
        if (px >= 0 && px < imgWidth && py >= 0 && py < imgHeight) {
          const idx = (py * imgWidth + px) * 4;
          data[idx] = color[0];
          data[idx + 1] = color[1];
          data[idx + 2] = color[2];
        }
      }
    }
    
    return new ImageData(data, imgWidth, imgHeight);
  }
}
