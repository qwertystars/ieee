import { create } from 'zustand';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
interface MapState {
  center: [number, number];
  zoom: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedFeature: any | null;
  setCenter: (center: [number, number]) => void;
  setZoom: (zoom: number) => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setSelectedFeature: (feature: any | null) => void;
}

export const useMapStore = create<MapState>((set) => ({
  center: [77.59, 12.97],
  zoom: 10,
  selectedFeature: null,
  setCenter: (center) => set({ center }),
  setZoom: (zoom) => set({ zoom }),
  setSelectedFeature: (feature) => set({ selectedFeature: feature }),
}));
