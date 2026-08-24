// Semantic map projections refine the mechanically generated transport DTOs.
import type {
  OpenApiMaterializedSchema,
  OpenApiSchema,
} from './openapi.generated'

/** Exact integer values serialized by entities.base.UnitStatus. */
export const MAP_UNIT_STATUS = {
  ACTIVE: 0,
  DISABLED: 1,
  DESTROYED: 2,
  SURRENDERED: 3,
  ROUTING: 4,
} as const

/** Core renderer fields are required; enriched OpenAPI fields remain optional. */
export type MapUnitFrame = OpenApiSchema<'MapUnitFrame'> & Required<
  Pick<
    OpenApiSchema<'MapUnitFrame'>,
    'domain' | 'status' | 'heading' | 'type'
  >
>

/** Position/state fields consumed by the map renderer, including interpolation. */
export type MapReplayFrame = Omit<
  Pick<OpenApiSchema<'ReplayFrame'>, 'tick' | 'units' | 'detected'>,
  'units'
> & {
  units: MapUnitFrame[]
}

export type TargetingExposureScope = OpenApiSchema<'TargetingExposureScope'>
export type ContactSource = OpenApiSchema<'ContactSource'>
export type EffectiveRangeBasis = OpenApiSchema<'EffectiveRangeBasis'>
export type FireControlSource = OpenApiSchema<'FireControlSource'>
export type TargetingDisposition = OpenApiSchema<'TargetingDisposition'>
export type WeaponModeledRole = OpenApiSchema<'WeaponModeledRole'>
export type SensorModeledRole = OpenApiSchema<'SensorModeledRole'>

export type ObserverTrackSupportRadarRole =
  | 'airborne_fire_control_radar'
  | 'airborne_ground_fire_control_radar'
  | 'airborne_multi_domain_fire_control_radar'
  | 'fire_control_radar'
  | 'ground_air_defense_fire_control_radar'
  | 'naval_fire_control_radar'
  | 'naval_air_defense_fire_control_radar'

export type PrivilegedObserverTrackSupportIdentity =
  OpenApiSchema<'PrivilegedObserverTrackSupportIdentity'>
export type PrivilegedObserverTrackSupportEvidence =
  OpenApiSchema<'PrivilegedObserverTrackSupportEvidence'>
export type PrivilegedTargetingDecision =
  OpenApiSchema<'PrivilegedTargetingDecision'>
export type PrivilegedEngagementRevalidationOutcome =
  OpenApiSchema<'PrivilegedEngagementRevalidationOutcome'>

export type PublicTrackStatus = OpenApiSchema<'PublicTrackStatus'>
export type PublicIdentificationLevel =
  OpenApiSchema<'PublicIdentificationLevel'>

export type SideFowPublicTrack = OpenApiSchema<'SideFowPublicTrack'>
export type SideFowTargetingDecision =
  OpenApiSchema<'SideFowTargetingDecision'>
export type SideFowEngagementRevalidationOutcome =
  OpenApiSchema<'SideFowEngagementRevalidationOutcome'>

type ScopedReplayFrameBase = Omit<
  OpenApiSchema<'ReplayFrame'>,
  | 'scope'
  | 'viewer_side'
  | 'units'
  | 'detected'
  | 'targeting'
  | 'targeting_outcomes'
  | 'tracks'
  | 'side_targeting'
  | 'side_targeting_outcomes'
> & {
  units: MapUnitFrame[]
  detected: Record<string, string[]>
}

export type PrivilegedReplayFrame = ScopedReplayFrameBase & {
  scope: 'PRIVILEGED_ENGINE'
  viewer_side: null
  targeting: PrivilegedTargetingDecision[]
  targeting_outcomes: PrivilegedEngagementRevalidationOutcome[]
  tracks: never[]
  side_targeting: never[]
  side_targeting_outcomes: never[]
}

export type SideFowReplayFrame = ScopedReplayFrameBase & {
  scope: 'SIDE_FOW'
  viewer_side: string
  targeting: never[]
  targeting_outcomes: never[]
  tracks: SideFowPublicTrack[]
  side_targeting: SideFowTargetingDecision[]
  side_targeting_outcomes: SideFowEngagementRevalidationOutcome[]
}

/** Exact discriminated wire shape returned by the frames API. */
export type ReplayFrame = PrivilegedReplayFrame | SideFowReplayFrame

type FramesResponseTransport =
  OpenApiMaterializedSchema<'FramesResponse'>

export type PrivilegedFramesData = Omit<
  FramesResponseTransport,
  'scope' | 'viewer_side' | 'frames'
> & {
  scope: 'PRIVILEGED_ENGINE'
  viewer_side: null
  frames: PrivilegedReplayFrame[]
}

export type SideFowFramesData = Omit<
  FramesResponseTransport,
  'scope' | 'viewer_side' | 'frames'
> & {
  scope: 'SIDE_FOW'
  viewer_side: string
  frames: SideFowReplayFrame[]
}

export type FramesData = PrivilegedFramesData | SideFowFramesData

export interface FrameRangeParams {
  start_tick?: number
  end_tick?: number
}

export interface PrivilegedFramesParams extends FrameRangeParams {
  scope?: 'PRIVILEGED_ENGINE'
  side?: never
}

export interface SideFowFramesParams extends FrameRangeParams {
  scope: 'SIDE_FOW'
  side: string
}

export type RunFramesParams = PrivilegedFramesParams | SideFowFramesParams

export type ObjectiveInfo = OpenApiMaterializedSchema<'ObjectiveInfo'>

/** Renderer-required terrain fields; elevation remains an optional layer. */
export type TerrainData = Omit<
  OpenApiSchema<'TerrainResponse'>,
  'objectives'
> & Required<
  Pick<
    OpenApiSchema<'TerrainResponse'>,
    | 'width_cells'
    | 'height_cells'
    | 'cell_size'
    | 'origin_easting'
    | 'origin_northing'
    | 'land_cover'
    | 'extent'
  >
> & {
  objectives: ObjectiveInfo[]
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
