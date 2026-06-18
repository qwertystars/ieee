import { useState, useCallback, useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { apiFetch } from '../../api/p4Fetch';

type DrawMode = 'polygon' | 'point' | 'line' | 'circle' | null;

interface MapDrawProps {
  map: maplibregl.Map;
  mode?: DrawMode;
  onModeChange?: (mode: DrawMode) => void;
  onFeaturesChange?: (features: GeoJSON.Feature[]) => void;
}

const DRAW_SOURCE = 'draw-source';
const DRAW_FILL_LAYER = 'draw-fill-layer';
const DRAW_LINE_LAYER = 'draw-line-layer';
const DRAW_POINTS_LAYER = 'draw-points-layer';
const DRAW_TEMP_SOURCE = 'draw-temp-source';
const DRAW_TEMP_FILL = 'draw-temp-fill';
const DRAW_TEMP_LINE = 'draw-temp-line';
const DRAW_CIRCLE_SOURCE = 'draw-circle-source';
const DRAW_CIRCLE_FILL = 'draw-circle-fill';
const DRAW_CIRCLE_LINE = 'draw-circle-line';

export default function MapDraw({ map, mode, onModeChange, onFeaturesChange }: MapDrawProps) {
  const [points, setPoints] = useState<[number, number][]>([]);
  const [features, setFeatures] = useState<GeoJSON.Feature[]>([]);
  const [circleCenter, setCircleCenter] = useState<[number, number] | null>(null);
  const [circleRadius, setCircleRadius] = useState(0);
  const sourceAddedRef = useRef(false);
  const clickHandlerRef = useRef<((e: maplibregl.MapMouseEvent) => void) | null>(null);
  const dblClickHandlerRef = useRef<((e: maplibregl.MapMouseEvent) => void) | null>(null);
  const mouseMoveHandlerRef = useRef<((e: maplibregl.MapMouseEvent) => void) | null>(null);
  const mouseUpHandlerRef = useRef<(() => void) | null>(null);

  const ensureSources = useCallback(() => {
    if (!map.isStyleLoaded() || sourceAddedRef.current) return;

    const sourceEntries: [string, GeoJSON.FeatureCollection][] = [
      [DRAW_SOURCE, { type: 'FeatureCollection', features: [] }],
      [DRAW_TEMP_SOURCE, { type: 'FeatureCollection', features: [] }],
      [DRAW_CIRCLE_SOURCE, { type: 'FeatureCollection', features: [] }],
    ];
    for (const [id, data] of sourceEntries) {
      if (!map.getSource(id)) {
        map.addSource(id, { type: 'geojson', data });
      }
    }

    if (!map.getLayer(DRAW_FILL_LAYER)) {
      map.addLayer({ id: DRAW_FILL_LAYER, type: 'fill', source: DRAW_SOURCE, paint: { 'fill-color': '#ef4444', 'fill-opacity': 0.25 } });
    }
    if (!map.getLayer(DRAW_LINE_LAYER)) {
      map.addLayer({ id: DRAW_LINE_LAYER, type: 'line', source: DRAW_SOURCE, paint: { 'line-color': '#ef4444', 'line-width': 2 } });
    }
    if (!map.getLayer(DRAW_POINTS_LAYER)) {
      map.addLayer({ id: DRAW_POINTS_LAYER, type: 'circle', source: DRAW_SOURCE, paint: { 'circle-color': '#ef4444', 'circle-radius': 5, 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' } });
    }
    if (!map.getLayer(DRAW_TEMP_FILL)) {
      map.addLayer({ id: DRAW_TEMP_FILL, type: 'fill', source: DRAW_TEMP_SOURCE, paint: { 'fill-color': '#f59e0b', 'fill-opacity': 0.15 } });
    }
    if (!map.getLayer(DRAW_TEMP_LINE)) {
      map.addLayer({ id: DRAW_TEMP_LINE, type: 'line', source: DRAW_TEMP_SOURCE, paint: { 'line-color': '#f59e0b', 'line-width': 2, 'line-dasharray': [3, 3] } });
    }
    if (!map.getLayer(DRAW_CIRCLE_FILL)) {
      map.addLayer({ id: DRAW_CIRCLE_FILL, type: 'fill', source: DRAW_CIRCLE_SOURCE, paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.2 } });
    }
    if (!map.getLayer(DRAW_CIRCLE_LINE)) {
      map.addLayer({ id: DRAW_CIRCLE_LINE, type: 'line', source: DRAW_CIRCLE_SOURCE, paint: { 'line-color': '#3b82f6', 'line-width': 2 } });
    }

    sourceAddedRef.current = true;
  }, [map]);

  const updateDrawnFeatures = useCallback(
    (feats: GeoJSON.Feature[]) => {
      const src = map.getSource(DRAW_SOURCE) as maplibregl.GeoJSONSource;
      if (src) src.setData({ type: 'FeatureCollection', features: feats });
    },
    [map],
  );

  const updateTemp = useCallback(
    (pts: [number, number][]) => {
      const src = map.getSource(DRAW_TEMP_SOURCE) as maplibregl.GeoJSONSource;
      if (!src) return;
      if (pts.length < 3) {
        src.setData({ type: 'FeatureCollection', features: [] });
        return;
      }
      src.setData({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...pts, pts[0]]] } }],
      });
    },
    [map],
  );

  const updateCircle = useCallback(
    (center: [number, number], radius: number) => {
      const src = map.getSource(DRAW_CIRCLE_SOURCE) as maplibregl.GeoJSONSource;
      if (!src) return;
      if (radius <= 0) {
        src.setData({ type: 'FeatureCollection', features: [] });
        return;
      }
      const pts: [number, number][] = [];
      const steps = 64;
      for (let i = 0; i <= steps; i++) {
        const angle = (i * 2 * Math.PI) / steps;
        const lat = center[1] + (radius / 111320) * Math.cos(angle);
        const lng = center[0] + (radius / (111320 * Math.cos((center[1] * Math.PI) / 180))) * Math.sin(angle);
        pts.push([lng, lat]);
      }
      src.setData({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', properties: { radius, center }, geometry: { type: 'Polygon', coordinates: [pts] } }],
      });
    },
    [map],
  );

  useEffect(() => {
    ensureSources();
    const onStyleData = () => { sourceAddedRef.current = false; ensureSources(); };
    map.on('styledata', onStyleData);
    return () => { map.off('styledata', onStyleData); };
  }, [map, ensureSources]);

  useEffect(() => {
    if (clickHandlerRef.current) map.off('click', clickHandlerRef.current);
    if (dblClickHandlerRef.current) map.off('dblclick', dblClickHandlerRef.current);
    if (mouseMoveHandlerRef.current) map.off('mousemove', mouseMoveHandlerRef.current);
    if (mouseUpHandlerRef.current) map.off('mouseup', mouseUpHandlerRef.current);
    clickHandlerRef.current = null;
    dblClickHandlerRef.current = null;
    mouseMoveHandlerRef.current = null;
    mouseUpHandlerRef.current = null;

    map.getCanvas().style.cursor = mode ? 'crosshair' : '';

    if (!mode) {
      setPoints([]);
      setCircleCenter(null);
      setCircleRadius(0);
      const tempSrc = map.getSource(DRAW_TEMP_SOURCE) as maplibregl.GeoJSONSource;
      if (tempSrc) tempSrc.setData({ type: 'FeatureCollection', features: [] });
      const circleSrc = map.getSource(DRAW_CIRCLE_SOURCE) as maplibregl.GeoJSONSource;
      if (circleSrc) circleSrc.setData({ type: 'FeatureCollection', features: [] });
      return;
    }

    if (mode === 'point') {
      const handler = (e: maplibregl.MapMouseEvent) => {
        const feature: GeoJSON.Feature = {
          type: 'Feature',
          properties: { type: 'point', timestamp: Date.now() },
          geometry: { type: 'Point', coordinates: [e.lngLat.lng, e.lngLat.lat] },
        };
        const next = [...features, feature];
        setFeatures(next);
        updateDrawnFeatures(next);
        onFeaturesChange?.(next);
      };
      clickHandlerRef.current = handler;
      map.on('click', handler);
    }

    if (mode === 'line') {
      const clickHandler = (e: maplibregl.MapMouseEvent) => {
        setPoints((prev) => [...prev, [e.lngLat.lng, e.lngLat.lat]]);
      };
      const dblHandler = (e: maplibregl.MapMouseEvent) => {
        e.preventDefault();
        setPoints((current) => {
          if (current.length < 2) return [];
          const feature: GeoJSON.Feature = {
            type: 'Feature',
            properties: { type: 'line', timestamp: Date.now() },
            geometry: { type: 'LineString', coordinates: current },
          };
          const next = [...features, feature];
          setFeatures(next);
          updateDrawnFeatures(next);
          onFeaturesChange?.(next);
          return [];
        });
      };
      clickHandlerRef.current = clickHandler;
      dblClickHandlerRef.current = dblHandler;
      map.on('click', clickHandler);
      map.on('dblclick', dblHandler);
    }

    if (mode === 'polygon') {
      const clickHandler = (e: maplibregl.MapMouseEvent) => {
        setPoints((prev) => {
          const next: [number, number][] = [...prev, [e.lngLat.lng, e.lngLat.lat]];
          updateTemp(next);
          return next;
        });
      };
      const dblHandler = (e: maplibregl.MapMouseEvent) => {
        e.preventDefault();
        setPoints((current) => {
          if (current.length < 3) return [];
          const feature: GeoJSON.Feature = {
            type: 'Feature',
            properties: { type: 'polygon', timestamp: Date.now() },
            geometry: { type: 'Polygon', coordinates: [[...current, current[0]]] },
          };
          const next = [...features, feature];
          setFeatures(next);
          updateDrawnFeatures(next);
          onFeaturesChange?.(next);
          const tempSrc = map.getSource(DRAW_TEMP_SOURCE) as maplibregl.GeoJSONSource;
          if (tempSrc) tempSrc.setData({ type: 'FeatureCollection', features: [] });
          return [];
        });
      };
      clickHandlerRef.current = clickHandler;
      dblClickHandlerRef.current = dblHandler;
      map.on('click', clickHandler);
      map.on('dblclick', dblHandler);
    }

    if (mode === 'circle') {
      const clickHandler = (e: maplibregl.MapMouseEvent) => {
        setCircleCenter([e.lngLat.lng, e.lngLat.lat]);
        setCircleRadius(0);
      };
      const moveHandler = (e: maplibregl.MapMouseEvent) => {
        setCircleCenter((prev) => {
          if (!prev) return prev;
          const dx = e.lngLat.lng - prev[0];
          const dy = e.lngLat.lat - prev[1];
          const r = Math.sqrt(dx * dx + dy * dy) * 111320;
          setCircleRadius(r);
          updateCircle(prev, r);
          return prev;
        });
      };
      const upHandler = () => {
        setCircleCenter((center) => {
          setCircleRadius((radius) => {
            if (center && radius > 0) {
              const feature: GeoJSON.Feature = {
                type: 'Feature',
                properties: { type: 'circle', radius, center, timestamp: Date.now() },
                geometry: { type: 'Point', coordinates: center },
              };
              const next = [...features, feature];
              setFeatures(next);
              updateDrawnFeatures(next);
              onFeaturesChange?.(next);
            }
            return 0;
          });
          return null;
        });
        const circleSrc = map.getSource(DRAW_CIRCLE_SOURCE) as maplibregl.GeoJSONSource;
        if (circleSrc) circleSrc.setData({ type: 'FeatureCollection', features: [] });
      };

      clickHandlerRef.current = clickHandler;
      mouseMoveHandlerRef.current = moveHandler;
      mouseUpHandlerRef.current = upHandler;
      map.on('click', clickHandler);
      map.on('mousemove', moveHandler);
      map.on('mouseup', upHandler);
    }
  }, [mode, features]);

  const deleteSelected = () => {
    if (features.length === 0) return;
    const next = features.slice(0, -1);
    setFeatures(next);
    updateDrawnFeatures(next);
    onFeaturesChange?.(next);
  };

  const clearDrawing = () => {
    setFeatures([]);
    setPoints([]);
    setCircleCenter(null);
    setCircleRadius(0);
    onModeChange?.(null);
    updateDrawnFeatures([]);
    const tempSrc = map.getSource(DRAW_TEMP_SOURCE) as maplibregl.GeoJSONSource;
    if (tempSrc) tempSrc.setData({ type: 'FeatureCollection', features: [] });
    const circleSrc = map.getSource(DRAW_CIRCLE_SOURCE) as maplibregl.GeoJSONSource;
    if (circleSrc) circleSrc.setData({ type: 'FeatureCollection', features: [] });
    onFeaturesChange?.([]);
  };

  const saveFeatures = async () => {
    const fc: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features };
    try {
      await apiFetch('/map/drawings', {
        method: 'POST',
        body: JSON.stringify(fc),
      });
    } catch {
      const blob = new Blob([JSON.stringify(fc, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'drawn-features.geojson';
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  return null;
}
