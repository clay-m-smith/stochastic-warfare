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
}

export interface ReplayFrame {
  tick: number
  units: MapUnitFrame[]
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
