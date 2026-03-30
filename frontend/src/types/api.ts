// TypeScript interfaces mirroring api/schemas.py

// --- Scenarios ---

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
}

export interface ForceSummaryEntry {
  unit_count: number
  unit_types: string[]
}

export interface ScenarioDetail {
  name: string
  config: Record<string, unknown>
  force_summary: Record<string, ForceSummaryEntry>
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

export interface RunSubmitRequest {
  scenario: string
  seed?: number
  max_ticks?: number
  config_overrides?: Record<string, unknown>
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
  config_overrides: Record<string, unknown>
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
  completed_iterations: number
  status: RunStatus
  created_at: string
  completed_at: string | null
  metrics: Record<string, MetricStats> | null
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
  overrides_a?: Record<string, unknown>
  overrides_b?: Record<string, unknown>
  label_a?: string
  label_b?: string
  num_iterations?: number
  max_ticks?: number
}

export interface SweepRequest {
  scenario: string
  parameter_name: string
  values: number[]
  num_iterations?: number
  max_ticks?: number
}
