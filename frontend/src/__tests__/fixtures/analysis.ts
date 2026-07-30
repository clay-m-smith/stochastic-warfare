import type {
  AnalysisBatchResult,
  CodeRevision,
  CompareResult,
  DoctrineCompareResult,
  RuntimeProvenance,
} from '../../types/analysis'
import type { BatchDetail, MetricStats } from '../../types/api'

const SOURCE_FINGERPRINT = 'a'.repeat(64)
const DATA_REVISION = 'b'.repeat(64)
const CATALOG_REVISION = 'c'.repeat(64)
const DOCTRINE_CATALOG_FINGERPRINT = 'd'.repeat(64)
const LOADOUT_FINGERPRINT = 'e'.repeat(64)

const CODE_REVISION: CodeRevision = {
  commit: '1'.repeat(40),
  dirty: false,
  worktree_fingerprint: 'f'.repeat(64),
}

function runtimeProvenance(
  variantId: string,
  doctrineSchoolId: string,
  sides: string[],
  unitsPerSide: number,
): RuntimeProvenance {
  const assignments = sides.flatMap((side) => (
    Array.from({ length: unitsPerSide }, (_, index) => ({
      unit_id: `${side}-${variantId}-${String(index + 1).padStart(4, '0')}`,
      side,
      commander_profile_id: 'joint_campaign',
      doctrine_school_id: doctrineSchoolId,
    }))
  ))
  return {
    code_revision: CODE_REVISION,
    data_revision: DATA_REVISION,
    data_file_count: 184,
    catalog_revision: CATALOG_REVISION,
    doctrine_catalog_fingerprint: DOCTRINE_CATALOG_FINGERPRINT,
    doctrine_assignment_fingerprint: `${variantId}-assignment-digest`,
    loaded_roster_loadout_fingerprint: LOADOUT_FINGERPRINT,
    final_roster_loadout_fingerprint: `${variantId}-final-loadout-digest`,
    initial_unit_assignments: assignments,
    arriving_unit_assignments: [],
  }
}

export function analysisBatch(
  variantId: string,
  doctrineSchoolId: string,
  metricVectors: Array<[string, number[]]>,
  seeds: number[],
  sides = ['blue', 'red'],
  unitsPerSide = 1,
): AnalysisBatchResult {
  const runtime = runtimeProvenance(
    variantId,
    doctrineSchoolId,
    sides,
    unitsPerSide,
  )
  const orderedMetrics = metricVectors.map(([metric]) => metric)
  const roster = sides.map((side): [string, number] => [side, unitsPerSide])
  return {
    scenario_path: '/data/scenarios/73_easting/scenario.yaml',
    data_root: '/data',
    variant_id: variantId,
    ordered_metrics: orderedMetrics,
    base_seed: seeds[0]!,
    seeds,
    max_ticks: 500,
    source_fingerprint: SOURCE_FINGERPRINT,
    config_fingerprint: `${variantId}-config-digest`,
    authored_roster: roster,
    loaded_roster: roster,
    code_revision: CODE_REVISION,
    data_revision: DATA_REVISION,
    data_file_count: 184,
    catalog_revision: CATALOG_REVISION,
    doctrine_catalog_fingerprint: DOCTRINE_CATALOG_FINGERPRINT,
    loaded_roster_loadout_fingerprint: LOADOUT_FINGERPRINT,
    initial_unit_assignments: runtime.initial_unit_assignments,
    metric_vectors: metricVectors,
    runs: seeds.map((seed) => ({
      variant_id: variantId,
      seed,
      ticks_executed: 100,
      duration_s: 500,
      winning_side: sides[0]!,
      condition_type: 'time_expired',
      game_over: true,
      source_fingerprint: SOURCE_FINGERPRINT,
      config_fingerprint: `${variantId}-config-digest`,
      authored_roster: roster,
      loaded_roster: roster,
      runtime_provenance: runtime,
    })),
  }
}

export function evidenceBatch(
  variantId: string,
  metricVectors: Array<[string, number[]]>,
  seeds: number[],
  maxTicks = 10000,
  options: {
    doctrineSchoolId?: string
    assignmentFingerprint?: string
    configFingerprint?: string
    finalLoadoutFingerprint?: string
    scenarioPath?: string
    sides?: string[]
    unitsPerSide?: number
    winningSides?: string[]
  } = {},
): AnalysisBatchResult {
  const batch = analysisBatch(
    variantId,
    options.doctrineSchoolId ?? 'maneuverist',
    metricVectors,
    seeds,
    options.sides,
    options.unitsPerSide,
  )
  batch.max_ticks = maxTicks
  batch.scenario_path = options.scenarioPath ?? batch.scenario_path
  batch.config_fingerprint = options.configFingerprint ?? '6'.repeat(64)
  for (const [index, run] of batch.runs.entries()) {
    run.config_fingerprint = batch.config_fingerprint
    run.winning_side = options.winningSides?.[index] ?? run.winning_side
    run.runtime_provenance.doctrine_assignment_fingerprint = (
      options.assignmentFingerprint ?? '7'.repeat(64)
    )
    run.runtime_provenance.final_roster_loadout_fingerprint = (
      options.finalLoadoutFingerprint ?? '8'.repeat(64)
    )
  }
  return batch
}

export function completedBatchDetail(): BatchDetail {
  const seeds = [42, 43, 44]
  const rawMetrics = {
    blue_active: [3, 2, 2],
    blue_destroyed: [0, 1, 1],
    red_active: [2, 1, 0],
    red_destroyed: [1, 2, 3],
  }
  const orderedMetrics = Object.keys(rawMetrics)
  const metrics = Object.fromEntries(
    Object.entries(rawMetrics).map(([metric, values]) => {
      const sorted = [...values].sort((left, right) => left - right)
      const mean = values.reduce((total, value) => total + value, 0) / values.length
      return [metric, {
        mean,
        median: sorted[1]!,
        std: Math.sqrt(
          values.reduce((total, value) => total + (value - mean) ** 2, 0)
            / (values.length - 1),
        ),
        min: sorted[0]!,
        max: sorted[2]!,
        p5: sorted[0]! + 0.1 * (sorted[1]! - sorted[0]!),
        p95: sorted[1]! + 0.9 * (sorted[2]! - sorted[1]!),
        n: values.length,
      }]
    }),
  ) as Record<string, MetricStats>
  return {
    batch_id: 'batch-1',
    scenario_name: '73_easting',
    num_iterations: seeds.length,
    base_seed: seeds[0]!,
    max_ticks: 10000,
    completed_iterations: seeds.length,
    status: 'completed',
    created_at: '2026-07-29T12:00:00Z',
    completed_at: '2026-07-29T12:01:00Z',
    metrics,
    ordered_metrics: orderedMetrics,
    raw_metrics: rawMetrics,
    provenance: evidenceBatch(
      'batch',
      orderedMetrics.map((metric) => [metric, rawMetrics[metric as keyof typeof rawMetrics]]),
      seeds,
      10000,
      { unitsPerSide: 3 },
    ),
    error_message: null,
  }
}

export function compareResult(): CompareResult {
  const seeds = Array.from({ length: 10 }, (_, index) => 42 + index)
  const zeroes = Array(10).fill(0) as number[]
  const redA = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  const redB = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
  const metricVectorsA: Array<[string, number[]]> = [
    ['blue_destroyed', zeroes],
    ['red_destroyed', redA],
  ]
  const metricVectorsB: Array<[string, number[]]> = [
    ['blue_destroyed', zeroes],
    ['red_destroyed', redB],
  ]
  return {
    label_a: 'Config A',
    label_b: 'Config B',
    num_iterations: 10,
    alpha: 0.05,
    ordered_metrics: ['blue_destroyed', 'red_destroyed'],
    seeds,
    metrics: [
      {
        metric: 'blue_destroyed',
        mean_a: 0,
        std_a: 0,
        mean_b: 0,
        std_b: 0,
        n_total: 10,
        n_nonzero: 0,
        positive: 0,
        negative: 0,
        tied: 10,
        mean_paired_difference: 0,
        median_paired_difference: 0,
        paired_superiority: 0.5,
        raw_p_value: 1,
        holm_adjusted_p_value: 1,
        alpha: 0.05,
        family_wise_significant: false,
      },
      {
        metric: 'red_destroyed',
        mean_a: 5.5,
        std_a: 3.0276503540974917,
        mean_b: 6.5,
        std_b: 3.0276503540974917,
        n_total: 10,
        n_nonzero: 10,
        positive: 10,
        negative: 0,
        tied: 0,
        mean_paired_difference: 1,
        median_paired_difference: 1,
        paired_superiority: 1,
        raw_p_value: 0.001953125,
        holm_adjusted_p_value: 0.00390625,
        alpha: 0.05,
        family_wise_significant: true,
      },
    ],
    raw_a: {
      blue_destroyed: zeroes,
      red_destroyed: redA,
    },
    raw_b: {
      blue_destroyed: zeroes,
      red_destroyed: redB,
    },
    batch_a: evidenceBatch(
      'a',
      metricVectorsA,
      seeds,
      10000,
      { unitsPerSide: 11 },
    ),
    batch_b: evidenceBatch(
      'b',
      metricVectorsB,
      seeds,
      10000,
      { unitsPerSide: 11 },
    ),
  }
}

export function doctrineCompareResult({
  scenarioPath = '/data/scenarios/73_easting/scenario.yaml',
  sides = ['blue', 'red'],
  sideToVary = 'blue',
}: {
  scenarioPath?: string
  sides?: string[]
  sideToVary?: string
} = {}): DoctrineCompareResult {
  const seeds = Array.from({ length: 10 }, (_, index) => 42 + index)
  const maneuverWins = [1, 1, 0, 1, 0, 1, 1, 0, 1, 0]
  const attritionWins = [0, 1, 0, 0, 1, 0, 1, 0, 0, 1]
  const maneuverDestroyed = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  const attritionDestroyed = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
  const orderedMetrics = [
    `win_${sideToVary}`,
    ...sides.map((side) => `${side}_destroyed`),
    'ticks_executed',
  ]
  const vectors = (
    wins: number[],
    destroyed: number[],
    ticks: number,
  ): Array<[string, number[]]> => orderedMetrics.map((metric) => {
    if (metric === `win_${sideToVary}`) return [metric, wins]
    if (metric === 'ticks_executed') return [metric, Array(10).fill(ticks)]
    return [metric, destroyed]
  })
  const metricResults = (
    metricVectors: Array<[string, number[]]>,
  ) => metricVectors.map(([metric, values]) => {
    const mean = values.reduce((total, value) => total + value, 0) / values.length
    const squaredError = values.reduce(
      (total, value) => total + (value - mean) ** 2,
      0,
    )
    return {
      metric,
      mean,
      std: Math.sqrt(squaredError / (values.length - 1)),
      values,
    }
  })
  const maneuverVectors = vectors(maneuverWins, maneuverDestroyed, 100)
  const attritionVectors = vectors(attritionWins, attritionDestroyed, 100)
  return {
    scenario: scenarioPath,
    num_iterations: 10,
    base_seed: 42,
    max_ticks: 10000,
    ordered_metrics: orderedMetrics,
    seeds,
    results: [
      {
        variant_id: 'maneuverist',
        assignments: [{ side: sideToVary, school_id: 'maneuverist' }],
        metrics: metricResults(maneuverVectors),
        batch: evidenceBatch(
          'maneuverist',
          maneuverVectors,
          seeds,
          10000,
          {
            doctrineSchoolId: 'maneuverist',
            assignmentFingerprint: '7'.repeat(64),
            configFingerprint: '6'.repeat(64),
            finalLoadoutFingerprint: '8'.repeat(64),
            scenarioPath,
            sides,
            unitsPerSide: 11,
            winningSides: maneuverWins.map((won) => (
              won ? sideToVary : 'draw'
            )),
          },
        ),
      },
      {
        variant_id: 'attrition',
        assignments: [{ side: sideToVary, school_id: 'attrition' }],
        metrics: metricResults(attritionVectors),
        batch: evidenceBatch(
          'attrition',
          attritionVectors,
          seeds,
          10000,
          {
            doctrineSchoolId: 'attrition',
            assignmentFingerprint: '9'.repeat(64),
            configFingerprint: '5'.repeat(64),
            finalLoadoutFingerprint: '4'.repeat(64),
            scenarioPath,
            sides,
            unitsPerSide: 11,
            winningSides: attritionWins.map((won) => (
              won ? sideToVary : 'draw'
            )),
          },
        ),
      },
    ],
  }
}
