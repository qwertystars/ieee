"use client";

import { Canvas } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { Suspense } from "react";
import type { Hazard, Survivor, Vec3 } from "@/types/route";
import { CursorLight } from "./CursorLight";
import { HazardMarker } from "./HazardMarker";
import { RoutePath } from "./RoutePath";
import { SurvivorSignal } from "./SurvivorSignal";
import { Terrain } from "./Terrain";

type SceneCanvasProps = {
  path: Vec3[];
  survivors: Survivor[];
  hazards: Hazard[];
};

export function SceneCanvas({ path, survivors, hazards }: SceneCanvasProps) {
  return (
    <Canvas
      className="h-full w-full"
      camera={{ position: [0, 16, 26], fov: 80, near: 0.1, far: 200 }}
      onCreated={({ camera }) => {
        camera.lookAt(0, 0, 0);
      }}
      dpr={[1, 2]}
      gl={{ antialias: true, powerPreference: "high-performance" }}
    >
      <color attach="background" args={["#05070f"]} />
      <fog attach="fog" args={["#05070f", 35, 120]} />
      <ambientLight intensity={0.25} color="#60a5fa" />
      <directionalLight
        position={[18, 32, 8]}
        intensity={1.2}
        color="#93c5fd"
      />
      <directionalLight position={[-18, 18, -14]} intensity={0.6} color="#22d3ee" />
      <CursorLight />

      <Suspense fallback={null}>
        <Terrain />
        {path.length > 1 ? <RoutePath path={path} /> : null}
        {survivors.map((survivor) => (
          <SurvivorSignal key={survivor.id} survivor={survivor} />
        ))}
        {hazards.map((hazard) => (
          <HazardMarker key={hazard.id} hazard={hazard} />
        ))}
      </Suspense>

      <EffectComposer>
        <Bloom
          intensity={1.35}
          luminanceThreshold={0.2}
          luminanceSmoothing={0.15}
        />
      </EffectComposer>
    </Canvas>
  );
}
