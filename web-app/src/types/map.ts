export interface MapMetadata {
  image: string;
  resolution: number;
  origin: [number, number, number];
  negate: number;
  occupied_thresh: number;
  free_thresh: number;
}

export interface FilterSettings {
  blur: number;
  dilation: number;
  erosion: number;
  opening: number;
}

export interface MapData {
  originalImage: ImageData | null;
  processedImage: ImageData | null;
  metadata: MapMetadata | null;
  fileName: string;
}

export interface ProcessingState {
  isLoading: boolean;
  error: string | null;
  progress: number;
}
