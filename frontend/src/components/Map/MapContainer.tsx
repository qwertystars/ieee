import React, { useEffect, useRef, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useMapStore } from '../../lib/stores/mapStore';

const BASE_STYLES: Record<string, { label: string; url: string }> = {
  street: { label: 'Street', url: 'https://demotiles.maplibre.org/style.json' },
  satellite: { label: 'Satellite', url: 'https://api.maptiler.com/tiles/satellite/style.json?key=get_your_own' },
  terrain: { label: 'Terrain', url: 'https://api.maptiler.com/tiles/terrain-rgb-v2/style.json?key=get_your_own' },
  dark: { label: 'Dark', url: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json' },
};

interface MapContainerProps {
  onMapLoad?: (map: maplibregl.Map) => void;
  children?: (map: maplibregl.Map) => React.ReactNode;
}

export default function MapContainer({ onMapLoad, children }: MapContainerProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const setCenter = useMapStore((s) => s.setCenter);
  const setZoom = useMapStore((s) => s.setZoom);

  const initMap = useCallback(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: BASE_STYLES.street.url,
      center: [77.59, 12.97],
      zoom: 10,
      maxPitch: 60,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: true, showZoom: true }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 200, unit: 'metric' }), 'bottom-left');
    map.addControl(
      new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: true }),
      'top-right',
    );
    map.addControl(new maplibregl.FullscreenControl(), 'top-right');

    map.on('moveend', () => {
      const c = map.getCenter();
      setCenter([c.lng, c.lat]);
      setZoom(map.getZoom());
    });

    map.on('load', () => {
      mapRef.current = map;
      setMapLoaded(true);
      onMapLoad?.(map);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [onMapLoad, setCenter, setZoom]);

  useEffect(() => {
    const cleanup = initMap();
    return () => cleanup?.();
  }, [initMap]);

  return (
    <div className="relative w-full h-full">
      <div ref={mapContainer} className="w-full h-full" />
      {mapLoaded && mapRef.current && children?.(mapRef.current)}
    </div>
  );
}
