import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../api/p4Fetch';

type OverlayType = 'heatmap' | 'markers' | 'clusters' | 'polygons' | 'animated' | 'weather';

interface OverlayDef {
  id: string;
  name: string;
  type: OverlayType;
  url?: string;
  data?: GeoJSON.FeatureCollection;
  visible?: boolean;
  color?: string;
}

interface MapOverlaysProps {
  map: maplibregl.Map;
  visibleOverlays?: string[];
}

export default function MapOverlays({ map, visibleOverlays }: MapOverlaysProps) {
  const { data: overlayData } = useQuery<OverlayDef[]>({
    queryKey: ['map-overlays'],
    queryFn: () => apiFetch<OverlayDef[]>('/map/overlays').catch(() => []),
  });

  const overlays = overlayData ?? [];
  const activeOverlays = visibleOverlays
    ? overlays.filter((o) => visibleOverlays.includes(o.id))
    : overlays.filter((o) => o.visible !== false);

  const addedSourcesRef = useRef<Set<string>>(new Set());
  const animationRef = useRef<number | null>(null);

  useEffect(() => {
    if (!map.isStyleLoaded()) return;

    const activeIds = new Set(activeOverlays.map((o) => `overlay-${o.id}`));

    overlays.forEach((overlay) => {
      const srcId = `overlay-src-${overlay.id}`;
      const layerId = `overlay-${overlay.id}`;
      const isActive = activeIds.has(layerId);

      if (!isActive) {
        if (map.getLayer(layerId)) map.removeLayer(layerId);
        if (map.getLayer(`${layerId}-inner`)) map.removeLayer(`${layerId}-inner`);
        if (map.getLayer(`${layerId}-pulse`)) map.removeLayer(`${layerId}-pulse`);
        if (map.getSource(srcId)) map.removeSource(srcId);
        addedSourcesRef.current.delete(layerId);
        return;
      }

      if (addedSourcesRef.current.has(layerId)) return;

      const geojsonData = overlay.data || { type: 'FeatureCollection' as const, features: [] as GeoJSON.Feature[] };

      try {
        if (!map.getSource(srcId)) {
          map.addSource(srcId, {
            type: 'geojson',
            data: overlay.url || geojsonData,
            cluster: overlay.type === 'clusters' || overlay.type === 'animated',
            clusterMaxZoom: 14,
            clusterRadius: 50,
          });
        }

        switch (overlay.type) {
          case 'heatmap':
            map.addLayer({
              id: layerId,
              type: 'heatmap',
              source: srcId,
              paint: {
                'heatmap-weight': ['interpolate', ['linear'], ['get', 'mag'], 0, 0, 6, 1],
                'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 1, 15, 3],
                'heatmap-color': [
                  'interpolate', ['linear'], ['heatmap-density'],
                  0, 'rgba(33,102,172,0)', 0.2, 'rgb(103,169,207)', 0.4, 'rgb(209,229,240)',
                  0.6, 'rgb(253,219,199)', 0.8, 'rgb(239,138,98)', 1, 'rgb(178,24,43)',
                ],
                'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 2, 15, 20],
                'heatmap-opacity': 0.7,
              },
            });
            break;

          case 'markers':
            map.addLayer({
              id: layerId,
              type: 'circle',
              source: srcId,
              paint: {
                'circle-radius': 6,
                'circle-color': overlay.color || '#ef4444',
                'circle-stroke-width': 2,
                'circle-stroke-color': '#ffffff',
              },
            });
            break;

          case 'clusters':
            map.addLayer({
              id: layerId,
              type: 'circle',
              source: srcId,
              filter: ['has', 'point_count'],
              paint: {
                'circle-color': ['step', ['get', 'point_count'], '#51bbd6', 100, '#f1f075', 750, '#f28cb1'],
                'circle-radius': ['step', ['get', 'point_count'], 15, 100, 20, 750, 25],
              },
            });
            map.addLayer({
              id: `${layerId}-inner`,
              type: 'symbol',
              source: srcId,
              filter: ['has', 'point_count'],
              layout: {
                'text-field': '{point_count_abbreviated}',
                'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
                'text-size': 12,
              },
              paint: { 'text-color': '#ffffff' },
            });
            break;

          case 'polygons':
            map.addLayer({
              id: layerId,
              type: 'fill',
              source: srcId,
              paint: {
                'fill-color': [
                  'match', ['get', 'zone'],
                  'evacuation', '#3b82f6',
                  'danger', '#ef4444',
                  'safe', '#22c55e',
                  '#6b7280',
                ] as maplibregl.ExpressionSpecification,
                'fill-opacity': 0.3,
                'fill-outline-color': [
                  'match', ['get', 'zone'],
                  'evacuation', '#3b82f6',
                  'danger', '#ef4444',
                  'safe', '#22c55e',
                  '#6b7280',
                ] as maplibregl.ExpressionSpecification,
              },
            });
            break;

          case 'animated':
            map.addLayer({
              id: layerId,
              type: 'circle',
              source: srcId,
              paint: {
                'circle-radius': 8,
                'circle-color': overlay.color || '#22c55e',
                'circle-stroke-width': 3,
                'circle-stroke-color': '#ffffff',
              },
            });
            map.addLayer({
              id: `${layerId}-pulse`,
              type: 'circle',
              source: srcId,
              paint: {
                'circle-radius': 16,
                'circle-color': overlay.color || '#22c55e',
                'circle-opacity': 0.4,
              },
            });
            break;

          case 'weather':
            map.addLayer({
              id: layerId,
              type: 'circle',
              source: srcId,
              paint: {
                'circle-radius': ['interpolate', ['linear'], ['get', 'speed'], 0, 3, 100, 12],
                'circle-color': ['interpolate', ['linear'], ['get', 'speed'], 0, '#67e8f9', 50, '#f59e0b', 100, '#ef4444'] as maplibregl.ExpressionSpecification,
                'circle-opacity': 0.7,
                'circle-stroke-width': 1,
                'circle-stroke-color': '#ffffff',
                'circle-stroke-opacity': 0.5,
              },
            });
            break;
        }

        addedSourcesRef.current.add(layerId);
      } catch {
        // source/layer may have been added by a race condition
      }
    });
  }, [map, overlays, activeOverlays]);

  useEffect(() => {
    const hasAnimated = activeOverlays.some((o) => o.type === 'animated');
    if (!hasAnimated) {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
      return;
    }

    let pulse = 0;
    const animate = () => {
      pulse = (pulse + 0.02) % 1;
      activeOverlays
        .filter((o) => o.type === 'animated')
        .forEach((o) => {
          const layerId = `overlay-${o.id}-pulse`;
          if (map.getLayer(layerId)) {
            const radius = 8 + pulse * 12;
            const opacity = 0.6 * (1 - pulse);
            map.setPaintProperty(layerId, 'circle-radius', radius);
            map.setPaintProperty(layerId, 'circle-opacity', opacity);
          }
        });
      animationRef.current = requestAnimationFrame(animate);
    };
    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
    };
  }, [map, activeOverlays]);

  useEffect(() => {
    const onStyleData = () => { addedSourcesRef.current.clear(); };
    map.on('styledata', onStyleData);
    return () => { map.off('styledata', onStyleData); };
  }, [map]);

  return null;
}

export function OverlayLegend({ overlays }: { overlays: OverlayDef[] }) {
  if (overlays.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {overlays.map((overlay) => (
        <div key={overlay.id} className="flex items-center gap-2 text-xs">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: overlay.color || '#6b7280' }} />
          <span className="text-slate-300">{overlay.name}</span>
          <span className="text-slate-600 ml-auto">{overlay.type}</span>
        </div>
      ))}
    </div>
  );
}
