// TypeScript interfaces for map/spatial data (Phase 35)

export interface MapUnitFrame {
  id: string
  side: string
  x: number
  y: number
  domain: number
  status: number
  heading: number
  type: string
  sensor_range?: number
  // Phase 92 enriched fields (Phase 94 visualization)
  morale?: number      // 0=STEADY, 1=SHAKEN, 2=BROKEN, 3=ROUTED, 4=SURRENDERED
  posture?: string     // MOVING, DEFENSIVE, DUG_IN, etc.
  health?: number      // 0.0–1.0
  fuel_pct?: number    // 0.0–1.0
  ammo_pct?: number    // 0.0–1.0
  suppression?: number // 0–4
  engaged?: boolean
}

export interface ReplayFrame {
  tick: number
  units: MapUnitFrame[]
  detected?: Record<string, string[]>
}

export interface FramesData {
  frames: ReplayFrame[]
  total_frames: number
}

export interface ObjectiveInfo {
  id: string
  x: number
  y: number
  radius: number
}

export interface TerrainData {
  width_cells: number
  height_cells: number
  cell_size: number
  origin_easting: number
  origin_northing: number
  land_cover: number[][]
  elevation?: number[][]
  objectives: ObjectiveInfo[]
  extent: number[]
}

export interface ViewportTransform {
  offsetX: number
  offsetY: number
  scale: number
}

export interface EngagementArc {
  attackerX: number
  attackerY: number
  targetX: number
  targetY: number
  hit: boolean
  tick: number
}
