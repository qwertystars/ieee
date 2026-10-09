"use client";

import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import type { Hazard, Survivor, Vec3 } from "@/types/route";

// Fix for default marker icons in Leaflet + Next.js
const DefaultIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

L.Marker.prototype.options.icon = DefaultIcon;

const survivorIcon = L.divIcon({
  className: "custom-survivor-icon",
  html: `
    <div class="relative flex items-center justify-center">
      <div class="absolute w-8 h-8 bg-cyan-400 rounded-full animate-ping opacity-25"></div>
      <div class="relative w-4 h-4 bg-cyan-400 rounded-full shadow-[0_0_15px_#22d3ee] border-2 border-white"></div>
    </div>
  `,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

const hazardIcon = L.divIcon({
  className: "custom-hazard-icon",
  html: `<div class="w-4 h-4 bg-red-500 rotate-45 border-2 border-white shadow-[0_0_10px_#ef4444]"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

type MapCanvasProps = {
  path: Vec3[];
  survivors: Survivor[];
  hazards: Hazard[];
};

function AutoCenter({ survivors }: { survivors: Survivor[] }) {
  const map = useMap();
  useEffect(() => {
    if (survivors.length > 0) {
      const validCoords = survivors
        .filter(s => s.lat !== undefined && s.lng !== undefined)
        .map(s => [s.lat!, s.lng!] as [number, number]);
      
      if (validCoords.length > 0) {
        map.fitBounds(validCoords, { padding: [50, 50], maxZoom: 16 });
      }
    }
  }, [survivors, map]);
  return null;
}

export default function MapCanvas({ path, survivors, hazards }: MapCanvasProps) {
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  if (!isMounted) return <div className="h-full w-full bg-slate-950" />;

  const defaultCenter: [number, number] = [12.8406, 80.1534]; // Default to some fallback or center of detected items

  return (
    <div className="h-full w-full">
      <MapContainer
        center={defaultCenter}
        zoom={13}
        className="h-full w-full"
        zoomControl={false}
      >
        <TileLayer
          attribution='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        />
        <TileLayer
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png"
          pane="shadowPane"
        />
        
        {survivors.map((survivor) => (
          survivor.lat !== undefined && survivor.lng !== undefined && (
            <Marker 
              key={survivor.id} 
              position={[survivor.lat, survivor.lng]} 
              icon={survivorIcon}
            >
              <Popup className="custom-popup">
                <div className="text-slate-900 font-sans">
                  <p className="font-bold">Survivor {survivor.id}</p>
                  <p className="text-xs">Urgency: {survivor.urgency}</p>
                </div>
              </Popup>
            </Marker>
          )
        ))}

        {hazards.map((hazard) => (
           // Note: Hazards in this project currently only have local X,Y in the mock data.
           // If they have lat/lng, we'd show them here.
           null
        ))}

        <AutoCenter survivors={survivors} />
      </MapContainer>
    </div>
  );
}
