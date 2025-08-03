import React from 'react';
import { FilterSettings } from '@/types/map';
import { Slider } from '@/components/ui/slider';

interface ControlPanelProps {
  filters: FilterSettings;
  onFiltersChange: (filters: FilterSettings) => void;
  onReset: () => void;
  onSave: () => void;
  isProcessing: boolean;
}

export function ControlPanel({
  filters,
  onFiltersChange,
  onReset,
  onSave,
  isProcessing
}: ControlPanelProps) {
  const updateFilter = (key: keyof FilterSettings, value: number) => {
    onFiltersChange({
      ...filters,
      [key]: value
    });
  };

  return (
    <div className="w-80 bg-white border-r border-gray-200 p-6 overflow-y-auto">
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            Map Enhancement Controls
          </h2>
        </div>

        <div className="border-t pt-6">
          <div className="space-y-6">
            {/* Blur */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700">
                  Blur Kernel Size
                </label>
                <span className="text-xs text-gray-500">
                  {filters.blur}
                </span>
              </div>
              <Slider
                value={filters.blur}
                onValueChange={(value) => updateFilter('blur', value)}
                min={0}
                max={5}
                step={1}
                disabled={isProcessing}
              />
              <p className="text-xs text-gray-500">
                Smooth noise with Gaussian blur
              </p>
            </div>

            {/* Dilation */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700">
                  Dilation Kernel Size
                </label>
                <span className="text-xs text-gray-500">
                  {filters.dilation}
                </span>
              </div>
              <Slider
                value={filters.dilation}
                onValueChange={(value) => updateFilter('dilation', value)}
                min={0}
                max={10}
                step={1}
                disabled={isProcessing}
              />
              <p className="text-xs text-gray-500">
                Expand obstacles (make them thicker)
              </p>
            </div>

            {/* Erosion */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700">
                  Erosion Kernel Size
                </label>
                <span className="text-xs text-gray-500">
                  {filters.erosion}
                </span>
              </div>
              <Slider
                value={filters.erosion}
                onValueChange={(value) => updateFilter('erosion', value)}
                min={0}
                max={10}
                step={1}
                disabled={isProcessing}
              />
              <p className="text-xs text-gray-500">
                Shrink obstacles (make them thinner)
              </p>
            </div>

            {/* Opening */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700">
                  Opening Kernel Size
                </label>
                <span className="text-xs text-gray-500">
                  {filters.opening}
                </span>
              </div>
              <Slider
                value={filters.opening}
                onValueChange={(value) => updateFilter('opening', value)}
                min={0}
                max={5}
                step={1}
                disabled={isProcessing}
              />
              <p className="text-xs text-gray-500">
                Remove small objects/noise
              </p>
            </div>
          </div>
        </div>

        <div className="border-t pt-6 space-y-3">
          <button
            onClick={onSave}
            disabled={isProcessing}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {isProcessing ? 'Processing...' : 'Save Enhanced Map'}
          </button>
          
          <button
            onClick={onReset}
            disabled={isProcessing}
            className="w-full bg-gray-600 text-white py-2 px-4 rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            Reset All Filters
          </button>
        </div>
      </div>
    </div>
  );
}
