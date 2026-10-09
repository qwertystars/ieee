export type Vec3 = {
  x: number;
  y: number;
  z?: number;
};

export type Survivor = {
  id: string;
  position: Vec3;
  urgency: "low" | "medium" | "high";
  relayNodeId?: string;
  confidence?: number;
  lat?: number;
  lng?: number;
};

export type Hazard = {
  id: string;
  position: Vec3;
  severity?: "low" | "medium" | "high";
};

export type RouteState = {
  path: Vec3[];
  survivors: Survivor[];
  hazards: Hazard[];
};
