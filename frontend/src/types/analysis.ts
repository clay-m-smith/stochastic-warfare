export interface CodeRevision {
  commit: string
  dirty: boolean
  worktree_fingerprint: string
}

export interface UnitCommandAssignment {
  unit_id: string
  side: string
  commander_profile_id: string | null
  doctrine_school_id: string | null
}

export interface RuntimeProvenance {
  code_revision: CodeRevision
  data_revision: string
  data_file_count: number
  catalog_revision: string
  doctrine_catalog_fingerprint: string
  doctrine_assignment_fingerprint: string
  loaded_roster_loadout_fingerprint: string
  final_roster_loadout_fingerprint: string
  initial_unit_assignments: UnitCommandAssignment[]
  arriving_unit_assignments: UnitCommandAssignment[]
}

export interface AnalysisRunRecord {
  variant_id: string
  seed: number
  ticks_executed: number
  duration_s: number
  winning_side: string
  condition_type: string
  game_over: boolean
  source_fingerprint: string
  config_fingerprint: string
  authored_roster: Array<[string, number]>
  loaded_roster: Array<[string, number]>
  runtime_provenance: RuntimeProvenance
}

export interface AnalysisBatchProvenance {
  scenario_path: string
  data_root: string
  variant_id: string
  ordered_metrics: string[]
  base_seed: number
  seeds: number[]
  max_ticks: number
  source_fingerprint: string
  config_fingerprint: string
  authored_roster: Array<[string, number]>
  loaded_roster: Array<[string, number]>
  code_revision: CodeRevision
  data_revision: string
  data_file_count: number
  catalog_revision: string
  doctrine_catalog_fingerprint: string
  loaded_roster_loadout_fingerprint: string
  initial_unit_assignments: UnitCommandAssignment[]
  runs: AnalysisRunRecord[]
}

export interface AnalysisBatchResult extends AnalysisBatchProvenance {
  metric_vectors: Array<[string, number[]]>
}

export interface MetricComparison {
  metric: string
  mean_a: number
  std_a: number
  mean_b: number
  std_b: number
  n_total: number
  n_nonzero: number
  positive: number
  negative: number
  tied: number
  mean_paired_difference: number
  median_paired_difference: number
  paired_superiority: number
  raw_p_value: number
  holm_adjusted_p_value: number
  alpha: number
  family_wise_significant: boolean
}

export interface CompareResult {
  label_a: string
  label_b: string
  num_iterations: number
  alpha: number
  ordered_metrics: string[]
  seeds: number[]
  metrics: MetricComparison[]
  raw_a: Record<string, number[]>
  raw_b: Record<string, number[]>
  batch_a: AnalysisBatchResult
  batch_b: AnalysisBatchResult
}

export interface MetricStat {
  metric: string
  mean: number
  std: number
  min: number
  max: number
  values: number[]
}

export interface SweepPoint {
  parameter_value: number
  metric_results: MetricStat[]
  batch: AnalysisBatchResult
}

export interface SweepResult {
  parameter_name: string
  points: SweepPoint[]
  ordered_metrics: string[]
  base_seed: number
  seeds: number[]
  max_ticks: number
  source_fingerprint: string
  data_root: string
}

export type DoctrineSideAssignment =
  OpenApiSchema<'DoctrineSideAssignmentRequest'>
export type DoctrineMetricResult = OpenApiSchema<'DoctrineMetricResult'>

/** Semantic batch evidence validated beyond the OpenAPI object shape. */
export type DoctrineVariantResult = Omit<
  OpenApiSchema<'DoctrineVariantResult'>,
  'batch'
> & {
  batch: AnalysisBatchResult
}

/** Doctrine results after the handwritten evidence validator succeeds. */
export type DoctrineCompareResult = Omit<
  OpenApiSchema<'DoctrineCompareResult'>,
  'results'
> & {
  results: DoctrineVariantResult[]
}
import type { OpenApiSchema } from './openapi.generated'
