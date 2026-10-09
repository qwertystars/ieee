"use client";

import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Group } from "three";
import type { Survivor } from "@/types/route";

const urgencyColor: Record<Survivor["urgency"], string> = {
  low: "#60a5fa",
  medium: "#22d3ee",
  high: "#f97316",
};

type SurvivorSignalProps = {
  survivor: Survivor;
};

export function SurvivorSignal({ survivor }: SurvivorSignalProps) {
  const { x, y, z } = survivor.position;
  const baseY = (z ?? 0.8) + 0.8;
  const auraRef = useRef<Group>(null);

  useFrame(({ clock }) => {
    if (!auraRef.current) return;
    const pulse = 1 + Math.sin(clock.elapsedTime * 2.2) * 0.18;
    auraRef.current.scale.setScalar(pulse);
  });

  return (
    <group position={[x, baseY, y]}>
      <mesh>
        <sphereGeometry args={[0.55, 18, 18]} />
        <meshStandardMaterial
          color="#ef4444"
          emissive="#ef4444"
          emissiveIntensity={1.6}
          roughness={0.3}
        />
      </mesh>
      <group ref={auraRef} scale={[1.1, 1.1, 1.1]}>
        <mesh>
          <sphereGeometry args={[1.2, 28, 28]} />
          <meshStandardMaterial
            color={urgencyColor[survivor.urgency]}
            emissive={urgencyColor[survivor.urgency]}
            emissiveIntensity={2}
            transparent
            opacity={0.25}
          />
        </mesh>
      </group>
    </group>
  );
}
