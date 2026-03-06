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
