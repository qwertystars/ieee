"use client";

import type { Hazard } from "@/types/route";

type HazardMarkerProps = {
  hazard: Hazard;
};

export function HazardMarker({ hazard }: HazardMarkerProps) {
  const { x, y, z } = hazard.position;
  const baseY = (z ?? 0.2) + 0.4;

  return (
    <group position={[x, baseY, y]}>
      <mesh>
        <cylinderGeometry args={[1.1, 1.1, 2, 10, 1, true]} />
        <meshBasicMaterial color="#ef4444" wireframe />
      </mesh>
      <mesh rotation={[0, 0, Math.PI / 4]}>
        <boxGeometry args={[2.2, 0.2, 0.2]} />
        <meshStandardMaterial color="#f87171" emissive="#ef4444" />
      </mesh>
      <mesh rotation={[0, 0, -Math.PI / 4]}>
        <boxGeometry args={[2.2, 0.2, 0.2]} />
        <meshStandardMaterial color="#f87171" emissive="#ef4444" />
      </mesh>
    </group>
  );
}
