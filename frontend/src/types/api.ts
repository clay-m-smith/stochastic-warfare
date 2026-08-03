// TypeScript interfaces mirroring api/schemas.py
import type { AnalysisBatchProvenance } from './analysis'

// --- Scenarios ---

export type HistoricalClaimDisposition =
  | 'production_validated'
  | 'current_engine_regression_only'
  | 'unsupported'

export interface HistoricalValidationClaim {
  claim_id: string
  disposition: HistoricalClaimDisposition
  reason_codes: string[]
  limitation: string
  intended_use: string
  metric_scope: string[]
  event_scope: string
  current_engine_regression_evidence: boolean
  accepted_study_id: string | null
  accepted_artifact_path: string | null
}

export interface HistoricalValidationSummary {
  aggregate_disposition: HistoricalClaimDisposition
  claims: HistoricalValidationClaim[]
  accepted_claim_ids: string[]
  current_engine_regression_evidence: boolean
  ledger_sha256: string
}

export interface ScenarioSummary {
  name: string
  display_name: string
  era: string
  duration_hours: number
  sides: string[]
  terrain_type: string
  has_ew: boolean
  has_cbrn: boolean
  has_escalation: boolean
  has_schools: boolean
  has_space: boolean
  has_dew: boolean
  historical_validation: HistoricalValidationSummary
}

export interface ForceSummaryEntry {
  unit_count: number
  unit_types: string[]
}

export interface ScenarioDetail {
  name: string
  config: Record<string, unknown>
  force_summary: Record<string, ForceSummaryEntry>
  historical_validation: HistoricalValidationSummary
}

// --- Units ---

export interface UnitSummary {
  unit_type: string
  display_name: string
  domain: string
  category: string
  era: string
  max_speed: number
  crew_size: number
}

export interface UnitDetail {
  unit_type: string
  definition: Record<string, unknown>
}

// --- Runs ---

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface MoraleCalibration {
  base_degrade_rate?: number
  base_recover_rate?: number
  casualty_weight?: number
  suppression_weight?: number
  leadership_weight?: number
  cohesion_weight?: number
  force_ratio_weight?: number
  transition_cooldown_s?: number
  degrade_rate_modifier?: number
  check_interval?: number
}

export interface SideCalibration {
  cohesion?: number | null
  force_ratio_modifier?: number | null
  start_x?: number | null
  start_y?: number | null
  formation_spacing_m?: number | null
  hit_probability_modifier?: number | null
  target_size_modifier?: number | null
}

/** Canonical sparse request shape for the backend CalibrationSchema. */
export interface CalibrationOverrides {
  hit_probability_modifier?: number
  target_size_modifier?: number
  visibility_m?: number | null
  thermal_contrast?: number
  morale_degrade_rate_modifier?: number
  max_engagers_per_side?: number
  formation_spacing_m?: number
  destruction_threshold?: number
  disable_threshold?: number
  dew_disable_threshold?: number
  defensive_sides?: string[]
  dig_in_ticks?: number
  wave_interval_s?: number
  target_selection_mode?: 'closest' | 'nearest' | 'threat_scored'
  roe_level?: 'WEAPONS_HOLD' | 'WEAPONS_TIGHT' | 'WEAPONS_FREE' | null
  enable_air_routing?: boolean
  jammer_coverage_mult?: number
  stealth_detection_penalty?: number
  sigint_detection_bonus?: number
  sam_suppression_modifier?: number
  sead_effectiveness?: number | null
  sead_arm_effectiveness?: number | null
  iads_degradation_rate?: number | null
  drone_provocation_prob?: number | null
  morale?: MoraleCalibration
  night_thermal_floor?: number
  wind_accuracy_penalty_scale?: number
  rain_attenuation_factor?: number
  c2_min_effectiveness?: number
  enable_fog_of_war?: boolean
  observation_decay_rate?: number
  engagement_concealment_threshold?: number
  target_value_weights?: Record<string, number> | null
  rout_cascade_radius_m?: number | null
  rout_cascade_base_chance?: number | null
  rout_cascade_shaken_susceptibility?: number | null
  gas_casualty_floor?: number
  gas_protection_scaling?: number
  subsystem_weibull_shapes?: Record<string, number>
  posture_blast_protection?: Record<string, number> | null
  posture_frag_protection?: Record<string, number> | null
  enable_seasonal_effects?: boolean
  enable_equipment_stress?: boolean
  enable_obstacle_effects?: boolean
  enable_obscurants?: boolean
  enable_fire_zones?: boolean
  enable_thermal_crossover?: boolean
  enable_nvg_detection?: boolean
  enable_sea_state_ops?: boolean
  enable_acoustic_layers?: boolean
  enable_em_propagation?: boolean
  enable_human_factors?: boolean
  heat_casualty_base_rate?: number
  cold_casualty_base_rate?: number
  mopp_fov_reduction_4?: number
  mopp_reload_factor_4?: number
  mopp_comms_factor_4?: number
  altitude_sickness_threshold_m?: number
  altitude_sickness_rate?: number
  enable_cbrn_environment?: boolean
  cbrn_washout_coefficient?: number
  cbrn_arrhenius_ea?: number
  cbrn_inversion_multiplier?: number
  cbrn_uv_degradation_rate?: number
  enable_air_combat_environment?: boolean
  cloud_ceiling_min_attack_m?: number
  icing_maneuver_penalty?: number
  icing_power_penalty?: number
  icing_radar_penalty_db?: number
  wind_bvr_missile_speed_mps?: number
  enable_event_feedback?: boolean
  enable_missile_routing?: boolean
  enable_c2_friction?: boolean
  degraded_equipment_threshold?: number
  planning_available_time_s?: number
  stratagem_concentration_bonus?: number
  stratagem_deception_bonus?: number
  order_propagation_delay_sigma?: number
  order_misinterpretation_base?: number
  enable_space_effects?: boolean
  enable_fuel_consumption?: boolean
  enable_ammo_gate?: boolean
  fire_damage_per_tick?: number
  stratagem_duration_ticks?: number
  retreat_distance_m?: number
  misinterpretation_radius_m?: number
  enable_carrier_ops?: boolean
  enable_ice_crossing?: boolean
  enable_bridge_capacity?: boolean
  enable_environmental_fatigue?: boolean
  enable_command_hierarchy?: boolean
  deception_phantom_count?: number
  enable_unconventional_warfare?: boolean
  enable_mine_persistence?: boolean
  guerrilla_disengage_threshold?: number
  human_shield_pk_reduction?: number
  enable_detection_culling?: boolean
  enable_scan_scheduling?: boolean
  enable_lod?: boolean
  enable_soa?: boolean
  enable_parallel_detection?: boolean
  lod_nearby_interval?: number
  lod_distant_interval?: number
  lod_hysteresis_ticks?: number
  enable_all_modern?: boolean
  weapon_assignments?: Record<string, string>
  victory_weights?: Record<string, number> | null
  side_overrides?: Record<string, SideCalibration>
}

export interface RunSubmitRequest {
  scenario: string
  seed?: number
  max_ticks?: number
  config_overrides?: CalibrationOverrides
  frame_interval?: number | null
}

export interface RunSubmitResponse {
  run_id: string
  status: RunStatus
}

export interface RunSummary {
  run_id: string
  scenario_name: string
  seed: number
  status: RunStatus
  created_at: string
  completed_at: string | null
  error_message: string | null
}

export interface RunDetail {
  run_id: string
  scenario_name: string
  scenario_path: string
  seed: number
  max_ticks: number
  config_overrides: CalibrationOverrides
  status: RunStatus
  created_at: string
  started_at: string | null
  completed_at: string | null
  result: Record<string, unknown> | null
  error_message: string | null
}

// --- Meta ---

export interface HealthResponse {
  status: string
  version: string
  scenario_count: number
  unit_count: number
}

export interface EraInfo {
  name: string
  value: string
  disabled_modules: string[]
}

export interface SchoolInfo {
  school_id: string
  display_name: string
  description: string
  ooda_multiplier: number
  risk_tolerance: string
}

export interface CommanderInfo {
  profile_id: string
  display_name: string
  description: string
  traits: Record<string, number>
}

export interface WeaponSummary {
  weapon_id: string
  display_name: string
  category: string
  max_range_m: number
  caliber_mm: number
}

export interface WeaponDetail {
  weapon_id: string
  definition: Record<string, unknown>
}

// --- Events ---

export interface EventItem {
  tick: number
  event_type: string
  source: string
  data: Record<string, unknown>
}

export interface EventsResponse {
  events: EventItem[]
  total: number
  offset: number
  limit: number
}

// --- Narrative ---

export interface NarrativeResponse {
  narrative: string
  tick_count: number
}

// --- Forces ---

export interface SideForces {
  total: number
  active: number
  disabled: number
  destroyed: number
}

export interface ForcesResponse {
  sides: Record<string, SideForces>
}

// --- Typed Run Result ---

export interface VictoryResult {
  status: string
  winner?: string | null
  winning_side?: string
  condition_type?: string
  message?: string
}

export interface RunResult {
  scenario: string
  seed: number
  ticks_executed: number
  duration_s: number
  victory: VictoryResult
  sides: Record<string, SideForces>
}

// --- WebSocket ---

export interface RunProgressMessage {
  type: 'tick' | 'complete' | 'error'
  tick?: number
  max_ticks?: number
  elapsed_s?: number
  active_units?: Record<string, number>
  game_over?: boolean
  message?: string
}

// --- Batch ---

export interface BatchSubmitRequest {
  scenario: string
  num_iterations?: number
  base_seed?: number
  max_ticks?: number
  config_overrides?: CalibrationOverrides
  metrics?: string[]
}

export interface BatchSubmitResponse {
  batch_id: string
  status: RunStatus
}

export interface MetricStats {
  mean: number
  median: number
  std: number
  min: number
  max: number
  p5: number
  p95: number
  n: number
}

export interface BatchDetail {
  batch_id: string
  scenario_name: string
  num_iterations: number
  base_seed: number
  max_ticks: number
  completed_iterations: number
  status: RunStatus
  created_at: string
  completed_at: string | null
  metrics: Record<string, MetricStats> | null
  ordered_metrics: string[]
  raw_metrics: Record<string, number[]> | null
  provenance: AnalysisBatchProvenance | null
  error_message: string | null
}

export interface BatchProgressMessage {
  type: 'iteration' | 'complete' | 'error'
  iteration?: number
  total?: number
  seed?: number
  message?: string
}

// --- Analysis ---

export interface CompareRequest {
  scenario: string
  overrides_a?: CalibrationOverrides
  overrides_b?: CalibrationOverrides
  label_a?: string
  label_b?: string
  metrics?: string[]
  num_iterations?: number
  base_seed?: number
  max_ticks?: number
  alpha?: number
}

export interface SweepRequest {
  scenario: string
  parameter_name: string
  values: number[]
  metrics?: string[]
  num_iterations?: number
  base_seed?: number
  max_ticks?: number
}
