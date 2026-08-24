// Public transport aliases come from FastAPI's generated OpenAPI contract.
// Handwritten types below this section are semantic UI/runtime views that the
// OpenAPI document cannot express (for example websocket messages and the
// independently validated result/provenance envelopes).
import type { AnalysisBatchProvenance } from './analysis'
import type {
  OpenApiMaterializedSchema,
  OpenApiSchema,
} from './openapi.generated'

// --- Scenarios ---

export type HistoricalClaimDisposition =
  OpenApiSchema<'HistoricalClaimDisposition'>
export type HistoricalValidationClaim =
  OpenApiSchema<'HistoricalValidationClaim'>
export type HistoricalValidationSummary =
  OpenApiSchema<'HistoricalValidationSummary'>
export type ScenarioSummary = OpenApiMaterializedSchema<'ScenarioSummary'>

export interface ForceSummaryEntry {
  unit_count: number
  unit_types: string[]
}

/** Semantic UI projection for the scenario force-summary payload. */
export type ScenarioDetail = Omit<
  OpenApiMaterializedSchema<'ScenarioDetail'>,
  'force_summary'
> & {
  force_summary: Record<string, ForceSummaryEntry>
}

// --- Units ---

export type UnitSummary = OpenApiMaterializedSchema<'UnitSummary'>
export type UnitDetail = OpenApiMaterializedSchema<'UnitDetail'>

// --- Runs ---

export type RunStatus = OpenApiSchema<'RunStatus'>
export type MoraleCalibration = OpenApiSchema<'MoraleCalibration'>
export type SideCalibration = OpenApiSchema<'SideCalibration'>
export type CalibrationOverrides = OpenApiSchema<'CalibrationSchema'>
export type RunSubmitRequest = OpenApiSchema<'RunSubmitRequest'>
export type RunSubmitResponse = OpenApiMaterializedSchema<'RunSubmitResponse'>
export type RunSummary = OpenApiMaterializedSchema<'RunSummary'>
export type RunDetail = OpenApiMaterializedSchema<'RunDetail'>

// --- Meta ---

export type HealthResponse = OpenApiMaterializedSchema<'HealthResponse'>
export type EraInfo = OpenApiMaterializedSchema<'EraInfo'>
export type SchoolInfo = OpenApiMaterializedSchema<'SchoolInfo'>
export type CommanderInfo = OpenApiMaterializedSchema<'CommanderInfo'>
export type WeaponSummary = OpenApiMaterializedSchema<'WeaponSummary'>
export type WeaponDetail = OpenApiMaterializedSchema<'WeaponDetail'>

// --- Events ---

export type EventItem = OpenApiMaterializedSchema<'EventItem'>
export type EventsResponse = Omit<
  OpenApiMaterializedSchema<'EventsResponse'>,
  'events'
> & {
  events: EventItem[]
}

// --- Narrative ---

export type NarrativeResponse = OpenApiMaterializedSchema<'NarrativeResponse'>

// --- Forces ---

export interface SideForces {
  total: number
  active: number
  disabled: number
  destroyed: number
}

type ForcesResponseTransport = OpenApiMaterializedSchema<'ForcesResponse'>

/** Semantic run-result projection layered over the transport object. */
export type ForcesResponse = Omit<ForcesResponseTransport, 'sides'> & {
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

export type BatchSubmitRequest = OpenApiSchema<'BatchSubmitRequest'>
export type BatchSubmitResponse =
  OpenApiMaterializedSchema<'BatchSubmitResponse'>

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

/** Semantic evidence fields validated by analysisEvidence.ts after transport. */
export type BatchDetail = Omit<
  OpenApiMaterializedSchema<'BatchDetail'>,
  'metrics' | 'provenance'
> & {
  metrics: Record<string, MetricStats> | null
  provenance: AnalysisBatchProvenance | null
}

export interface BatchProgressMessage {
  type: 'iteration' | 'complete' | 'error'
  iteration?: number
  total?: number
  seed?: number
  message?: string
}

// --- Analysis ---

export type CompareRequest = OpenApiSchema<'CompareRequest'>
export type SweepRequest = OpenApiSchema<'SweepRequest'>
export type DoctrineCompareRequest = OpenApiSchema<'DoctrineCompareRequest'>
