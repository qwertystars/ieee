"use client";

import { useMemo } from "react";
import { CatmullRomCurve3, TubeGeometry, Vector3 } from "three";
import type { Vec3 } from "@/types/route";

type RoutePathProps = {
  path: Vec3[];
};

export function RoutePath({ path }: RoutePathProps) {
  const geometry = useMemo(() => {
    if (path.length < 2) return null;
    const points = path.map((point) => new Vector3(point.x, point.z ?? 0.4, point.y));
    const curve = new CatmullRomCurve3(points);
    return new TubeGeometry(curve, 120, 0.35, 12, false);
  }, [path]);

  if (!geometry) return null;

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color="#60a5fa"
        emissive="#60a5fa"
        emissiveIntensity={2}
        roughness={0.2}
        metalness={0.6}
      />
    </mesh>
  );
}
