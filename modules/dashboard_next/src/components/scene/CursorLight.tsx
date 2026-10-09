"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useRef } from "react";
import { PointLight } from "three";

export function CursorLight() {
  const lightRef = useRef<PointLight>(null);
  const { viewport } = useThree();

  useFrame(({ mouse }) => {
    if (!lightRef.current) return;
    const x = mouse.x * viewport.width * 0.45;
    const z = mouse.y * viewport.height * 0.45;
    lightRef.current.position.set(x, 12, z);
  });

  return (
    <pointLight
      ref={lightRef}
      intensity={1.8}
      color="#22d3ee"
      distance={90}
      decay={2}
      position={[0, 12, 0]}
    />
  );
}
