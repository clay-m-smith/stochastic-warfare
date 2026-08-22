// TypeScript interfaces for map/spatial data (Phase 35)

/** Exact integer values serialized by entities.base.UnitStatus. */
export const MAP_UNIT_STATUS = {
  ACTIVE: 0,
  DISABLED: 1,
  DESTROYED: 2,
  SURRENDERED: 3,
  ROUTING: 4,
} as const

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

/** Position/state fields consumed by the map renderer, including interpolation. */
export interface MapReplayFrame {
  tick: number
  units: MapUnitFrame[]
  detected?: Record<string, string[]>
}

export type TargetingExposureScope = 'PRIVILEGED_ENGINE' | 'SIDE_FOW'

export type ContactSource =
  | 'NONE'
  | 'NON_FOW_LOCAL_OBSERVATION'
  | 'FOW_OBSERVER_WITNESS'
  | 'FOW_OBSERVER_TRACK_SUPPORT'

export type EffectiveRangeBasis =
  | 'AUTHORED'
  | 'LEGACY_DERIVED_80_PERCENT_OF_MAX'

export type FireControlSource =
  | 'NONE'
  | 'DIRECT_VISUAL'
  | 'SENSOR_ATTACHMENT'

export type TargetingDisposition =
  | 'VALID_STANDOFF_HOLD'
  | 'VALID_ENGAGEMENT_SOLUTION'
  | 'EFFECTIVE_RANGE_UNKNOWN'
  | 'STANDOFF_DISABLED'
  | 'STANDOFF_NOT_SUPPORTED_FOR_ROLE'
  | 'SHOOTER_INACTIVE'
  | 'NO_TARGET'
  | 'TARGET_INACTIVE'
  | 'TARGET_NOT_HOSTILE'
  | 'TARGET_NOT_IN_BATTLE'
  | 'NO_CONTACT'
  | 'STALE_CONTACT'
  | 'CONTACT_OBSERVER_MISMATCH'
  | 'CONTACT_SENSOR_UNAVAILABLE'
  | 'CONTACT_SENSOR_OFFLINE'
  | 'CONTACT_SENSOR_WRONG_DOMAIN'
  | 'CONTACT_RANGE_EXCEEDED'
  | 'LINE_OF_SIGHT_BLOCKED'
  | 'OUTSIDE_SENSOR_FIELD_OF_VIEW'
  | 'VISIBILITY_LIMITED'
  | 'SENSING_RANGE_EXCEEDED'
  | 'NO_USABLE_WEAPON'
  | 'WEAPON_INOPERABLE'
  | 'NO_FIREABLE_AMMUNITION'
  | 'WEAPON_RESERVED'
  | 'TARGET_DOMAIN_UNSUPPORTED'
  | 'UNSUPPORTED_WEAPON_ROLE'
  | 'ROUTED_WEAPON_ROLE'
  | 'NO_COMPATIBLE_FIRE_CONTROL'
  | 'FIRE_CONTROL_SENSOR_OFFLINE'
  | 'FIRE_CONTROL_SHOOTER_DOMAIN_UNSUPPORTED'
  | 'FIRE_CONTROL_TARGET_DOMAIN_UNSUPPORTED'
  | 'FIRE_CONTROL_RANGE_EXCEEDED'
  | 'OUTSIDE_PHYSICAL_RANGE'
  | 'OUTSIDE_EFFECTIVE_RANGE'

export type WeaponModeledRole =
  | 'ground_direct_fire'
  | 'air_defense_gun'
  | 'naval_gunfire'
  | 'naval_air_defense_gun'
  | 'field_artillery'
  | 'mortar_fire'
  | 'rocket_artillery'
  | 'assault_rifle'
  | 'muzzle_loading_musket'
  | 'bolt_action_rifle'
  | 'semi_automatic_rifle'
  | 'sniper_rifle'
  | 'anti_materiel_rifle'
  | 'submachine_gun'
  | 'light_machine_gun'
  | 'general_purpose_machine_gun'
  | 'heavy_machine_gun'
  | 'individual_grenade_launcher'
  | 'automatic_grenade_launcher'
  | 'hand_grenade'
  | 'melee'
  | 'ancient_projectile'
  | 'anti_armor'
  | 'air_defense_missile'
  | 'air_to_air_missile'
  | 'air_to_ground_missile'
  | 'anti_ship_missile'
  | 'multi_role_vls'
  | 'bomb_delivery'
  | 'aircraft_gun'
  | 'torpedo'
  | 'anti_submarine'
  | 'close_in_defense'
  | 'directed_energy'
  | 'incendiary_projector'

export type SensorModeledRole =
  | 'visual_observation'
  | 'night_vision'
  | 'thermal_targeting'
  | 'airborne_fire_control_radar'
  | 'airborne_ground_fire_control_radar'
  | 'airborne_multi_domain_fire_control_radar'
  | 'airborne_maritime_search_radar'
  | 'air_search_radar'
  | 'ship_air_surface_search_radar'
  | 'surface_search_radar'
  | 'ship_surface_search_radar'
  | 'submarine_surface_search_radar'
  | 'ground_surveillance_radar'
  | 'coastal_surveillance_radar'
  | 'fire_control_radar'
  | 'ground_air_defense_fire_control_radar'
  | 'naval_fire_control_radar'
  | 'naval_air_defense_fire_control_radar'
  | 'ground_visual_sight'
  | 'ground_air_defense_optical_sight'
  | 'airborne_visual_sight'
  | 'airborne_ground_visual_targeting'
  | 'airborne_ground_bombsight'
  | 'naval_visual_director'
  | 'naval_air_defense_optical_director'
  | 'naval_lookout'
  | 'ground_night_sight'
  | 'ground_active_ir_sight'
  | 'airborne_low_light_observation'
  | 'individual_night_vision'
  | 'ground_thermal_targeting'
  | 'airborne_ground_thermal_targeting'
  | 'airborne_air_thermal_search'
  | 'airborne_surface_thermal_search'
  | 'radar_warning_esm'
  | 'electronic_support'
  | 'active_sonar'
  | 'passive_sonar'

export type ObserverTrackSupportRadarRole =
  | 'airborne_fire_control_radar'
  | 'airborne_ground_fire_control_radar'
  | 'airborne_multi_domain_fire_control_radar'
  | 'fire_control_radar'
  | 'ground_air_defense_fire_control_radar'
  | 'naval_fire_control_radar'
  | 'naval_air_defense_fire_control_radar'

export interface PrivilegedObserverTrackSupportIdentity {
  reporting_side: string
  observer_unit_id: string
  source_equipment_index: number
  sensor_id: string
  modeled_role: ObserverTrackSupportRadarRole
  target_id: string
}

export interface PrivilegedObserverTrackSupportEvidence {
  identity: PrivilegedObserverTrackSupportIdentity
  fusion_track_id: string
  sensor_type: 'RADAR'
  observation_ordinal: number
  observation_time_s: number
  native_period: number
  native_phase_residue: number
  native_due_ordinal: number
  position_m: [number, number]
  velocity_mps: [number, number]
  covariance: [
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
  ]
  projection_ordinal: number
  projection_time_s: number
}

export interface PrivilegedTargetingDecision {
  engine_tick: number
  logical_time_s: number
  battle_id: string
  ordinal: number
  shooter_id: string
  shooter_side: string
  shooter_domain: string
  target_id: string | null
  target_side: string | null
  target_domain: string | null
  distance_m: number
  weapon_id: string | null
  weapon_source_equipment_index: number | null
  weapon_modeled_role: WeaponModeledRole | null
  ammunition_id: string | null
  physical_max_range_m: number
  predictive_effective_range_m: number
  effective_range_basis: EffectiveRangeBasis | null
  legacy_derived_reference_range_m: number
  contact_source: ContactSource
  observing_unit_id: string | null
  contact_sensor_source_equipment_index: number | null
  contact_sensor_id: string | null
  contact_sensor_modeled_role: SensorModeledRole | null
  contact_time_s: number | null
  contact_range_m: number
  visibility_bound_m: number
  sensing_sensor_source_equipment_index: number | null
  sensing_sensor_id: string | null
  sensing_sensor_modeled_role: SensorModeledRole | null
  sensing_range_m: number
  fire_control_source: FireControlSource
  fire_control_sensor_source_equipment_index: number | null
  fire_control_sensor_id: string | null
  fire_control_sensor_modeled_role: SensorModeledRole | null
  fire_control_range_m: number
  disposition: TargetingDisposition
  authorized_standoff_m: number
  hold_authorized: boolean
  engagement_solution_valid: boolean
  sensing_aware_standoff_enabled: boolean
  fog_of_war_enabled: boolean
  consumable: boolean
  observer_track_support: PrivilegedObserverTrackSupportEvidence | null
}

export interface PrivilegedEngagementRevalidationOutcome {
  engine_tick: number
  logical_time_s: number
  battle_id: string
  shooter_id: string
  target_id: string
  weapon_id: string
  weapon_source_equipment_index: number
  weapon_modeled_role: WeaponModeledRole
  ammunition_id: string
  disposition: TargetingDisposition
  revalidation_passed: boolean
  fog_of_war_enabled: boolean
  consumable: boolean
}

export type PublicTrackStatus =
  | 'TENTATIVE'
  | 'CONFIRMED'
  | 'COASTING'
  | 'STALE'
  | 'LOST'

export type PublicIdentificationLevel =
  | 'UNKNOWN'
  | 'DETECTED'
  | 'CLASSIFIED'
  | 'IDENTIFIED'

export interface SideFowPublicTrack {
  track_id: string
  reporting_side: string
  easting_m: number
  northing_m: number
  velocity_east_mps: number
  velocity_north_mps: number
  position_uncertainty_m: number
  status: PublicTrackStatus
  identification_level: PublicIdentificationLevel
  domain_estimate: string | null
  type_estimate: string | null
  specific_estimate: string | null
  confidence: number
  first_detected_time_s: number
  last_sensor_contact_time_s: number
}

export interface SideFowTargetingDecision {
  engine_tick: number
  logical_time_s: number
  battle_id: string
  ordinal: number
  shooter_id: string
  viewer_side: string
  target_track_id: string | null
  disposition: TargetingDisposition
  contact_source: ContactSource
  contact_time_s: number | null
  authorized_standoff_m: number
  hold_authorized: boolean
  engagement_solution_valid: boolean
  sensing_aware_standoff_enabled: boolean
  fog_of_war_enabled: boolean
  consumable: boolean
}

export interface SideFowEngagementRevalidationOutcome {
  engine_tick: number
  logical_time_s: number
  battle_id: string
  shooter_id: string
  viewer_side: string
  target_track_id: string
  disposition: TargetingDisposition
  revalidation_passed: boolean
  fog_of_war_enabled: boolean
  consumable: boolean
}

interface ScopedReplayFrameBase extends MapReplayFrame {
  detected: Record<string, string[]>
}

export interface PrivilegedReplayFrame extends ScopedReplayFrameBase {
  scope: 'PRIVILEGED_ENGINE'
  viewer_side: null
  targeting: PrivilegedTargetingDecision[]
  targeting_outcomes: PrivilegedEngagementRevalidationOutcome[]
  tracks: never[]
  side_targeting: never[]
  side_targeting_outcomes: never[]
}

export interface SideFowReplayFrame extends ScopedReplayFrameBase {
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

export interface PrivilegedFramesData {
  scope: 'PRIVILEGED_ENGINE'
  viewer_side: null
  frames: PrivilegedReplayFrame[]
  total_frames: number
}

export interface SideFowFramesData {
  scope: 'SIDE_FOW'
  viewer_side: string
  frames: SideFowReplayFrame[]
  total_frames: number
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
