/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_MESH_API_BASE?: string
  readonly VITE_THERMAL_API_BASE?: string
  readonly VITE_DRONE_URL?: string
  readonly VITE_LOCAL_DEMO_LOGIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
