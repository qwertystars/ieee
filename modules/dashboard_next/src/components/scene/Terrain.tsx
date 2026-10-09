"use client";

import { Grid } from "@react-three/drei";
import { useMemo } from "react";
import { PlaneGeometry } from "three";

export function Terrain() {
  const geometry = useMemo(() => {
    const geo = new PlaneGeometry(180, 180, 70, 70);
    const position = geo.attributes.position;

    for (let i = 0; i < position.count; i += 1) {
      const x = position.getX(i);
      const y = position.getY(i);
      const elevation =
        Math.sin(x * 0.08) * 1.5 + Math.cos(y * 0.1) * 1.2 + Math.sin((x + y) * 0.04) * 2.2;
      position.setZ(i, elevation);
    }

    geo.computeVertexNormals();
    return geo;
  }, []);

  return (
    <group>
      <mesh geometry={geometry} rotation-x={-Math.PI / 2} position={[0, -2, 0]}>
        <meshStandardMaterial
          color="#0b1220"
          emissive="#0b1220"
          metalness={0.4}
          roughness={0.7}
        />
      </mesh>
      <Grid
        args={[180, 180]}
        cellSize={4}
        cellThickness={0.6}
        cellColor="#1e293b"
        sectionSize={20}
        sectionThickness={1.2}
        sectionColor="#60a5fa"
        fadeDistance={70}
        fadeStrength={2}
        position={[0, -1.8, 0]}
      />
    </group>
  );
}
