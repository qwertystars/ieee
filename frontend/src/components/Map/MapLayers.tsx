import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../api/p4Fetch';

interface LayerDef {
  id: string;
  name: string;
  group?: string;
  type: 'geojson' | 'raster' | 'point' | 'line' | 'polygon' | 'heatmap';
  url?: string;
  data?: GeoJSON.FeatureCollection;
  visible?: boolean;
  opacity?: number;
  color?: string;
}

interface MapLayersProps {
  map: maplibregl.Map;
}

const LAYER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4'];

export default function MapLayers({ map }: MapLayersProps) {
  const { data: layersData } = useQuery<LayerDef[]>({
    queryKey: ['map-layers'],
    queryFn: () => apiFetch<LayerDef[]>('/map/layers').catch(() => []),
  });

  const addedLayersRef = useRef<Set<string>>(new Set());
  const layerStatesRef = useRef<Record<string, { visible: boolean; opacity: number }>>({});

  const layers = layersData ?? [];

  useEffect(() => {
    layers.forEach((l) => {
      if (!layerStatesRef.current[l.id]) {
        layerStatesRef.current[l.id] = { visible: l.visible ?? true, opacity: l.opacity ?? 0.8 };
      }
    });
  }, [layers]);

  useEffect(() => {
    if (!map.isStyleLoaded()) return;

    layers.forEach((layer, i) => {
      const state = layerStatesRef.current[layer.id] || { visible: true, opacity: 0.8 };
      const sourceId = `layer-src-${layer.id}`;
      const layerId = `layer-${layer.id}`;
      const color = layer.color || LAYER_COLORS[i % LAYER_COLORS.length];

      if (!map.getSource(sourceId)) {
        if (layer.data) {
          map.addSource(sourceId, { type: 'geojson', data: layer.data });
        } else if (layer.url) {
          map.addSource(sourceId, { type: 'geojson', data: layer.url });
        } else {
          return;
        }

        const layerType = layer.type || 'geojson';

        if (layerType === 'heatmap') {
          map.addLayer({
            id: layerId,
            type: 'heatmap',
            source: sourceId,
            paint: {
              'heatmap-weight': ['interpolate', ['linear'], ['get', 'density'], 0, 0, 100, 1],
              'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 1, 15, 3],
              'heatmap-color': [
                'interpolate', ['linear'], ['heatmap-density'],
                0, 'rgba(33,102,172,0)', 0.2, 'rgb(103,169,207)', 0.4, 'rgb(209,229,240)',
                0.6, 'rgb(253,219,199)', 0.8, 'rgb(239,138,98)', 1, 'rgb(178,24,43)',
              ],
              'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 2, 15, 20],
              'heatmap-opacity': state.opacity,
            },
          });
        } else if (layerType === 'point') {
          map.addLayer({
            id: layerId,
            type: 'circle',
            source: sourceId,
            paint: {
              'circle-color': color,
              'circle-radius': 6,
              'circle-opacity': state.opacity,
              'circle-stroke-width': 2,
              'circle-stroke-color': '#ffffff',
              'circle-stroke-opacity': state.opacity,
            },
          });
          map.addLayer({
            id: `${layerId}-clusters`,
            type: 'circle',
            source: sourceId,
            filter: ['has', 'point_count'],
            paint: {
              'circle-color': ['step', ['get', 'point_count'], color, 10, color, 50, '#f59e0b'],
              'circle-radius': ['step', ['get', 'point_count'], 15, 10, 20, 50, 25],
              'circle-opacity': state.opacity,
            },
          });
          map.addLayer({
            id: `${layerId}-cluster-count`,
            type: 'symbol',
            source: sourceId,
            filter: ['has', 'point_count'],
            layout: {
              'text-field': '{point_count_abbreviated}',
              'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
              'text-size': 12,
            },
            paint: { 'text-color': '#ffffff' },
          });
        } else if (layerType === 'line') {
          map.addLayer({
            id: layerId,
            type: 'line',
            source: sourceId,
            paint: { 'line-color': color, 'line-width': 3, 'line-opacity': state.opacity },
          });
        } else if (layerType === 'polygon') {
          map.addLayer({
            id: layerId,
            type: 'fill',
            source: sourceId,
            paint: { 'fill-color': color, 'fill-opacity': state.opacity * 0.4, 'fill-outline-color': color },
          });
          map.addLayer({
            id: `${layerId}-outline`,
            type: 'line',
            source: sourceId,
            paint: { 'line-color': color, 'line-width': 2, 'line-opacity': state.opacity },
          });
        } else {
          map.addLayer({
            id: layerId,
            type: 'fill',
            source: sourceId,
            paint: { 'fill-color': color, 'fill-opacity': state.opacity, 'fill-outline-color': color },
          });
        }

        addedLayersRef.current.add(layerId);
      }

      const visibility = state.visible ? 'visible' : 'none';
      [layerId, `${layerId}-clusters`, `${layerId}-cluster-count`, `${layerId}-outline`].forEach((id) => {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, 'visibility', visibility);
        }
      });

      if (map.getLayer(layerId)) {
        if (layer.type === 'heatmap') {
          map.setPaintProperty(layerId, 'heatmap-opacity', state.opacity);
        } else if (layer.type === 'line') {
          map.setPaintProperty(layerId, 'line-opacity', state.opacity);
        } else if (layer.type === 'polygon') {
          map.setPaintProperty(layerId, 'fill-opacity', state.opacity * 0.4);
        } else {
          map.setPaintProperty(layerId, 'circle-opacity', state.opacity);
        }
      }

      if (!addedLayersRef.current.has(`${layerId}-click`)) {
        map.on('click', layerId, (e) => {
          if (!e.features || e.features.length === 0) return;
          const props = e.features[0].properties;
          if (!props) return;
          const rows = Object.entries(props)
            .map(([k, v]) => `<div class="flex justify-between gap-2"><span class="text-slate-500">${k}:</span><span class="text-slate-200">${v}</span></div>`)
            .join('');
          new maplibregl.Popup()
            .setLngLat(e.lngLat)
            .setHTML(`<div class="bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-xl max-w-xs text-sm font-sans">${rows}</div>`)
            .addTo(map);
        });
        map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = ''; });
        addedLayersRef.current.add(`${layerId}-click`);
      }
    });
  }, [map, layers]);

  useEffect(() => {
    const onStyleData = () => { addedLayersRef.current.clear(); };
    map.on('styledata', onStyleData);
    return () => { map.off('styledata', onStyleData); };
  }, [map]);

  return null;
}
