import type {
  AnalysisBatchProvenance,
  AnalysisBatchResult,
  CodeRevision,
  CompareResult,
  DoctrineCompareResult,
  SweepResult,
} from '../types/analysis'
import type { BatchDetail, MetricStats } from '../types/api'

const SHA256_PATTERN = /^[0-9a-f]{64}$/
const GIT_COMMIT_PATTERN = /^[0-9a-f]{40}$/
const TERMINAL_CONDITION_TYPES = new Set([
  'attrition_ratio',
  'force_destroyed',
  'max_ticks',
  'morale_collapsed',
  'supply_exhausted',
  'territory_control',
  'time_expired',
])

interface SweepExpectation {
  scenario: string
  parameterName: string
  values: number[]
  orderedMetrics: string[]
  numIterations: number
  baseSeed: number
  maxTicks: number
}

export interface BatchExpectation {
  batchId?: string
  scenario: string
  orderedMetrics: string[]
  numIterations: number
  baseSeed: number
  maxTicks: number
}

export interface CompareExpectation {
  scenario: string
  labelA: string
  labelB: string
  orderedMetrics: string[]
  numIterations: number
  baseSeed: number
  maxTicks: number
  alpha: number
}

export interface DoctrineExpectation {
  scenario: string
  variants: Array<{
    variant_id: string
    assignments: Array<{
      side: string
      school_id: string
    }>
  }>
  orderedMetrics: string[]
  numIterations: number
  baseSeed: number
  maxTicks: number
}

interface ProvenanceExpectation {
  orderedMetrics: string[]
  seeds: number[]
  baseSeed: number
  maxTicks: number
  sourceFingerprint?: string
  dataRoot?: string
}

function sameOrderedValues<T>(actual: T[], expected: T[]): boolean {
  return (
    actual.length === expected.length
    && actual.every((value, index) => value === expected[index])
  )
}

function isNonEmptyTrimmed(value: unknown): value is string {
  return (
    typeof value === 'string'
    && value.length > 0
    && value === value.trim()
  )
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isStrictInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isSafeInteger(value)
}

function codeRevisionError(revision: CodeRevision | undefined): string | null {
  if (!revision) return 'missing code revision'
  if (!GIT_COMMIT_PATTERN.test(revision.commit)) {
    return 'invalid code revision commit'
  }
  if (typeof revision.dirty !== 'boolean') {
    return 'invalid code revision dirty state'
  }
  if (!SHA256_PATTERN.test(revision.worktree_fingerprint)) {
    return 'invalid worktree fingerprint'
  }
  return null
}

function sampleMean(values: number[]): number {
  return values.reduce((total, value) => total + value, 0) / values.length
}

function sampleStd(values: number[], mean: number): number {
  if (values.length === 1) return 0
  const squaredError = values.reduce(
    (total, value) => total + (value - mean) ** 2,
    0,
  )
  return Math.sqrt(squaredError / (values.length - 1))
}

function median(values: number[]): number {
  return percentile(values, 0.5)
}

function percentile(values: number[], percentage: number): number {
  const ordered = [...values].sort((left, right) => left - right)
  const position = (ordered.length - 1) * percentage
  const lowerIndex = Math.floor(position)
  const upperIndex = Math.ceil(position)
  const lower = ordered[lowerIndex]!
  const upper = ordered[upperIndex]!
  return lower + (upper - lower) * (position - lowerIndex)
}

function numericallyEqual(actual: number, expected: number): boolean {
  const scale = Math.max(1, Math.abs(actual), Math.abs(expected))
  return Math.abs(actual - expected) <= Number.EPSILON * 32 * scale
}

function metricVectorError(
  values: number[] | undefined,
  expectedCount: number,
  path: string,
): string | null {
  if (!Array.isArray(values) || values.length !== expectedCount) {
    return `${path} must contain exactly ${expectedCount} values`
  }
  if (!values.every(isFiniteNumber)) {
    return `${path} contains a non-finite value`
  }
  return null
}

function fingerprintError(
  provenance: AnalysisBatchProvenance,
): string | null {
  const digests: Array<[string, unknown]> = [
    ['source fingerprint', provenance.source_fingerprint],
    ['config fingerprint', provenance.config_fingerprint],
    ['data revision', provenance.data_revision],
    ['catalog revision', provenance.catalog_revision],
    ['doctrine catalog fingerprint', provenance.doctrine_catalog_fingerprint],
    ['loadout fingerprint', provenance.loaded_roster_loadout_fingerprint],
  ]
  const invalid = digests.find(([, value]) => (
    typeof value !== 'string' || !SHA256_PATTERN.test(value)
  ))
  if (invalid) return `invalid ${invalid[0]}`
  return codeRevisionError(provenance.code_revision)
}

function rosterError(
  roster: Array<[string, number]> | undefined,
  path: string,
): string | null {
  if (!Array.isArray(roster) || roster.length === 0) {
    return `${path} is missing`
  }
  const sides: string[] = []
  for (const entry of roster) {
    if (
      !Array.isArray(entry)
      || entry.length !== 2
      || !isNonEmptyTrimmed(entry[0])
      || !isStrictInteger(entry[1])
      || entry[1] < 1
    ) {
      return `${path} contains an invalid entry`
    }
    sides.push(entry[0])
  }
  if (new Set(sides).size !== sides.length) {
    return `${path} contains duplicate sides`
  }
  return null
}

function assignmentError(
  assignments: AnalysisBatchProvenance['initial_unit_assignments'] | undefined,
  path: string,
  requireNonEmpty: boolean,
): string | null {
  if (!Array.isArray(assignments) || (requireNonEmpty && assignments.length === 0)) {
    return `${path} is missing`
  }
  const unitIds: string[] = []
  for (const assignment of assignments) {
    if (
      !assignment
      || !isNonEmptyTrimmed(assignment.unit_id)
      || !isNonEmptyTrimmed(assignment.side)
      || (
        assignment.commander_profile_id !== null
        && !isNonEmptyTrimmed(assignment.commander_profile_id)
      )
      || (
        assignment.doctrine_school_id !== null
        && !isNonEmptyTrimmed(assignment.doctrine_school_id)
      )
    ) {
      return `${path} contains an invalid assignment`
    }
    unitIds.push(assignment.unit_id)
  }
  if (new Set(unitIds).size !== unitIds.length) {
    return `${path} contains duplicate unit IDs`
  }
  return null
}

function assignmentCoverageError(
  initial: AnalysisBatchProvenance['initial_unit_assignments'],
  arriving: AnalysisBatchProvenance['initial_unit_assignments'],
  roster: Array<[string, number]>,
  path: string,
): string | null {
  const expectedBySide = new Map(roster)
  const initialBySide = new Map<string, number>()
  const initialIds = new Set(initial.map((assignment) => assignment.unit_id))
  for (const assignment of initial) {
    if (!expectedBySide.has(assignment.side)) {
      return `${path} contains an unknown side`
    }
    initialBySide.set(
      assignment.side,
      (initialBySide.get(assignment.side) ?? 0) + 1,
    )
  }
  for (const [side, count] of expectedBySide) {
    if (initialBySide.get(side) !== count) {
      return `${path} initial assignments do not cover the loaded roster`
    }
  }
  if (arriving.some((assignment) => !expectedBySide.has(assignment.side))) {
    return `${path} arriving assignments contain an unknown side`
  }
  if (arriving.some((assignment) => initialIds.has(assignment.unit_id))) {
    return `${path} initial and arriving unit IDs overlap`
  }
  return null
}

function semanticMetricError(
  provenance: AnalysisBatchProvenance,
  rawMetrics: Record<string, number[]>,
  orderedMetrics: string[],
): string | null {
  const initialCounts = new Map(provenance.loaded_roster)
  const sides = [...initialCounts.keys()]
  const supportedMetrics = new Set(['ticks_executed'])
  for (const side of sides) {
    supportedMetrics.add(`${side}_active`)
    supportedMetrics.add(`${side}_destroyed`)
    supportedMetrics.add(`win_${side}`)
  }
  if (new Set(sides).size === 2 && sides.includes('blue') && sides.includes('red')) {
    supportedMetrics.add('exchange_ratio')
  }
  const unsupported = orderedMetrics.find((metric) => !supportedMetrics.has(metric))
  if (unsupported) return `metric ${unsupported} is unsupported by the batch roster`

  for (const [runIndex, run] of provenance.runs.entries()) {
    const arrivingCounts = new Map<string, number>()
    for (const assignment of run.runtime_provenance.arriving_unit_assignments) {
      arrivingCounts.set(
        assignment.side,
        (arrivingCounts.get(assignment.side) ?? 0) + 1,
      )
    }
    const finalCounts = new Map(
      sides.map((side) => [
        side,
        initialCounts.get(side)! + (arrivingCounts.get(side) ?? 0),
      ]),
    )
    for (const metric of orderedMetrics) {
      const observed = rawMetrics[metric]![runIndex]!
      if (metric === 'ticks_executed' && observed !== run.ticks_executed) {
        return `metric ${metric} differs from run ${runIndex}`
      }
      if (metric.startsWith('win_')) {
        const expectedWin = Number(run.winning_side === metric.slice(4))
        if (observed !== expectedWin) {
          return `metric ${metric} differs from run ${runIndex}`
        }
      }
      for (const [side, finalCount] of finalCounts) {
        if (
          metric === `${side}_active`
          || metric === `${side}_destroyed`
        ) {
          if (!Number.isSafeInteger(observed) || observed < 0 || observed > finalCount) {
            return `metric ${metric} is outside run ${runIndex} roster bounds`
          }
        }
        const active = rawMetrics[`${side}_active`]?.[runIndex]
        const destroyed = rawMetrics[`${side}_destroyed`]?.[runIndex]
        if (
          active !== undefined
          && destroyed !== undefined
          && active + destroyed > finalCount
        ) {
          return `metrics for ${side} exceed run ${runIndex} roster bounds`
        }
      }
      if (metric === 'exchange_ratio') {
        if (observed < 0 || observed > finalCounts.get('red')!) {
          return `metric ${metric} is outside run ${runIndex} roster bounds`
        }
        const blueDestroyed = rawMetrics.blue_destroyed?.[runIndex]
        const redDestroyed = rawMetrics.red_destroyed?.[runIndex]
        if (
          blueDestroyed !== undefined
          && redDestroyed !== undefined
          && observed !== redDestroyed / Math.max(1, blueDestroyed)
        ) {
          return `metric ${metric} differs from run ${runIndex} destroyed counts`
        }
      }
    }
  }
  return null
}

function provenanceError(
  provenance: AnalysisBatchProvenance | null | undefined,
  expected: ProvenanceExpectation,
): string | null {
  if (!provenance) return 'missing batch provenance'
  if (
    !isNonEmptyTrimmed(provenance.scenario_path)
    || !isNonEmptyTrimmed(provenance.data_root)
    || !isNonEmptyTrimmed(provenance.variant_id)
  ) {
    return 'batch provenance identifiers are missing'
  }
  if (!Array.isArray(provenance.ordered_metrics)
    || !sameOrderedValues(provenance.ordered_metrics, expected.orderedMetrics)) {
    return 'batch provenance metric order is inconsistent'
  }
  if (!Array.isArray(provenance.seeds)
    || !sameOrderedValues(provenance.seeds, expected.seeds)) {
    return 'batch provenance seeds are inconsistent'
  }
  if (
    provenance.base_seed !== expected.baseSeed
    || provenance.max_ticks !== expected.maxTicks
  ) {
    return 'batch provenance run bounds are inconsistent'
  }
  if (
    expected.sourceFingerprint !== undefined
    && provenance.source_fingerprint !== expected.sourceFingerprint
  ) {
    return 'batch provenance source fingerprint is inconsistent'
  }
  if (
    expected.dataRoot !== undefined
    && provenance.data_root !== expected.dataRoot
  ) {
    return 'batch provenance data root is inconsistent'
  }

  const fingerprintFailure = fingerprintError(provenance)
  if (fingerprintFailure) return fingerprintFailure
  if (!isStrictInteger(provenance.data_file_count) || provenance.data_file_count < 1) {
    return 'batch provenance data file count is invalid'
  }
  const authoredRosterFailure = rosterError(
    provenance.authored_roster,
    'batch authored roster',
  )
  if (authoredRosterFailure) return authoredRosterFailure
  const loadedRosterFailure = rosterError(
    provenance.loaded_roster,
    'batch loaded roster',
  )
  if (loadedRosterFailure) return loadedRosterFailure
  if (
    JSON.stringify(provenance.loaded_roster)
    !== JSON.stringify(provenance.authored_roster)
  ) {
    return 'batch loaded roster differs from authored roster'
  }
  const initialAssignmentFailure = assignmentError(
    provenance.initial_unit_assignments,
    'batch initial assignments',
    true,
  )
  if (initialAssignmentFailure) return initialAssignmentFailure
  const knownSides = new Set(
    provenance.loaded_roster.map(([side]) => side),
  )
  if (
    provenance.initial_unit_assignments.some(
      (assignment) => !knownSides.has(assignment.side),
    )
  ) {
    return 'batch initial assignments contain an unknown side'
  }
  const initialCoverageFailure = assignmentCoverageError(
    provenance.initial_unit_assignments,
    [],
    provenance.loaded_roster,
    'batch initial assignments',
  )
  if (initialCoverageFailure) return initialCoverageFailure
  if (!Array.isArray(provenance.runs)
    || provenance.runs.length !== expected.seeds.length) {
    return 'batch provenance run evidence is incomplete'
  }

  for (const [index, run] of provenance.runs.entries()) {
    const runtime = run?.runtime_provenance
    if (
      !run
      || run.variant_id !== provenance.variant_id
      || run.seed !== expected.seeds[index]
      || !isStrictInteger(run.ticks_executed)
      || run.ticks_executed < 1
      || run.ticks_executed > expected.maxTicks
      || !isFiniteNumber(run.duration_s)
      || run.duration_s < 0
      || !isNonEmptyTrimmed(run.winning_side)
      || (
        run.winning_side !== 'draw'
        && !knownSides.has(run.winning_side)
      )
      || !isNonEmptyTrimmed(run.condition_type)
      || !TERMINAL_CONDITION_TYPES.has(run.condition_type)
      || run.game_over !== true
    ) {
      return `batch run ${index} is incomplete`
    }
    if (
      run.source_fingerprint !== provenance.source_fingerprint
      || run.config_fingerprint !== provenance.config_fingerprint
    ) {
      return `batch run ${index} fingerprint is inconsistent`
    }
    if (
      JSON.stringify(run.authored_roster)
        !== JSON.stringify(provenance.authored_roster)
      || JSON.stringify(run.loaded_roster)
        !== JSON.stringify(provenance.loaded_roster)
    ) {
      return `batch run ${index} roster is inconsistent`
    }
    if (!runtime) return `batch run ${index} runtime provenance is missing`
    const runtimeCodeError = codeRevisionError(runtime.code_revision)
    if (runtimeCodeError) return `batch run ${index} ${runtimeCodeError}`
    if (
      runtime.code_revision.commit !== provenance.code_revision.commit
      || runtime.code_revision.dirty !== provenance.code_revision.dirty
      || runtime.code_revision.worktree_fingerprint
        !== provenance.code_revision.worktree_fingerprint
      || runtime.data_revision !== provenance.data_revision
      || runtime.data_file_count !== provenance.data_file_count
      || runtime.catalog_revision !== provenance.catalog_revision
      || runtime.doctrine_catalog_fingerprint
        !== provenance.doctrine_catalog_fingerprint
      || runtime.loaded_roster_loadout_fingerprint
        !== provenance.loaded_roster_loadout_fingerprint
    ) {
      return `batch run ${index} runtime identity is inconsistent`
    }
    if (
      JSON.stringify(runtime.initial_unit_assignments)
      !== JSON.stringify(provenance.initial_unit_assignments)
    ) {
      return `batch run ${index} initial assignments are inconsistent`
    }
    const arrivingAssignmentFailure = assignmentError(
      runtime.arriving_unit_assignments,
      `batch run ${index} arriving assignments`,
      false,
    )
    if (arrivingAssignmentFailure) return arrivingAssignmentFailure
    const assignmentCoverageFailure = assignmentCoverageError(
      runtime.initial_unit_assignments,
      runtime.arriving_unit_assignments,
      provenance.loaded_roster,
      `batch run ${index} assignments`,
    )
    if (assignmentCoverageFailure) return assignmentCoverageFailure
    if (
      !SHA256_PATTERN.test(runtime.doctrine_assignment_fingerprint)
      || !SHA256_PATTERN.test(runtime.final_roster_loadout_fingerprint)
    ) {
      return `batch run ${index} runtime fingerprint is invalid`
    }
  }
  return null
}

function batchResultError(
  batch: AnalysisBatchResult | null | undefined,
  expected: ProvenanceExpectation,
): string | null {
  const provenanceFailure = provenanceError(batch, expected)
  if (provenanceFailure) return provenanceFailure
  if (!batch || !Array.isArray(batch.metric_vectors)) {
    return 'batch metric vectors are missing'
  }
  if (batch.metric_vectors.length !== expected.orderedMetrics.length) {
    return 'batch metric vector count is inconsistent'
  }
  for (const [index, metric] of expected.orderedMetrics.entries()) {
    const vector = batch.metric_vectors[index]
    if (!Array.isArray(vector) || vector.length !== 2 || vector[0] !== metric) {
      return `batch metric vector ${index} is out of order`
    }
    const vectorFailure = metricVectorError(
      vector[1],
      expected.seeds.length,
      `batch metric ${metric}`,
    )
    if (vectorFailure) return vectorFailure
  }
  return semanticMetricError(
    batch,
    Object.fromEntries(batch.metric_vectors),
    expected.orderedMetrics,
  )
}

function scenarioMatches(scenarioPath: string, scenario: string): boolean {
  if (!isNonEmptyTrimmed(scenarioPath) || !isNonEmptyTrimmed(scenario)) {
    return false
  }
  const pathParts = scenarioPath.split('/').filter(Boolean)
  const scenarioParts = scenario.split('/').filter(Boolean)
  const scenarioId = scenarioParts.at(-1)
  const pathFile = pathParts.at(-1)
  const pathParent = pathParts.at(-2)
  return (
    scenarioId !== undefined
    && pathParent === scenarioId
    && pathFile === 'scenario.yaml'
  )
}

function rawMetricMapError(
  raw: Record<string, number[]> | null | undefined,
  orderedMetrics: string[],
  expectedCount: number,
  path: string,
): string | null {
  if (
    !raw
    || !sameOrderedValues(Object.keys(raw), orderedMetrics)
  ) {
    return `${path} keys/order are inconsistent`
  }
  for (const metric of orderedMetrics) {
    const vectorFailure = metricVectorError(
      raw[metric],
      expectedCount,
      `${path}.${metric}`,
    )
    if (vectorFailure) return vectorFailure
  }
  return null
}

function twoSidedSignPValue(positive: number, negative: number): number {
  const nonzero = positive + negative
  if (nonzero === 0) return 1
  const tailLimit = Math.min(positive, negative)
  let combination = 1
  let tail = 1
  for (let count = 1; count <= tailLimit; count += 1) {
    combination *= (nonzero - count + 1) / count
    tail += combination
  }
  return Math.min(1, (2 * tail) / (2 ** nonzero))
}

function compareStatisticError(
  result: CompareResult,
  expected: CompareExpectation,
): string | null {
  if (
    !Array.isArray(result.metrics)
    || result.metrics.length !== expected.orderedMetrics.length
    || !sameOrderedValues(
      result.metrics.map((metric) => metric.metric),
      expected.orderedMetrics,
    )
  ) {
    return 'comparison statistic order is inconsistent'
  }

  const rawPValues: number[] = []
  for (const [index, metric] of result.metrics.entries()) {
    const name = expected.orderedMetrics[index]!
    const valuesA = result.raw_a[name]!
    const valuesB = result.raw_b[name]!
    const differences = valuesA.map((value, valueIndex) => (
      valuesB[valueIndex]! - value
    ))
    const positive = differences.filter((value) => value > 0).length
    const negative = differences.filter((value) => value < 0).length
    const tied = differences.length - positive - negative
    const meanA = sampleMean(valuesA)
    const meanB = sampleMean(valuesB)
    const rawPValue = twoSidedSignPValue(positive, negative)
    const numericExpectations: Array<[string, number, unknown]> = [
      ['mean_a', meanA, metric.mean_a],
      ['std_a', sampleStd(valuesA, meanA), metric.std_a],
      ['mean_b', meanB, metric.mean_b],
      ['std_b', sampleStd(valuesB, meanB), metric.std_b],
      ['mean_paired_difference', sampleMean(differences), metric.mean_paired_difference],
      ['median_paired_difference', median(differences), metric.median_paired_difference],
      ['paired_superiority', (positive + 0.5 * tied) / differences.length, metric.paired_superiority],
      ['raw_p_value', rawPValue, metric.raw_p_value],
      ['alpha', expected.alpha, metric.alpha],
    ]
    const invalidNumeric = numericExpectations.find(([, value, actual]) => (
      !isFiniteNumber(actual) || !numericallyEqual(actual, value)
    ))
    if (invalidNumeric) {
      return `comparison metric ${name} ${invalidNumeric[0]} is inconsistent`
    }
    if (
      metric.n_total !== differences.length
      || metric.n_nonzero !== positive + negative
      || metric.positive !== positive
      || metric.negative !== negative
      || metric.tied !== tied
    ) {
      return `comparison metric ${name} paired counts are inconsistent`
    }
    rawPValues.push(rawPValue)
  }

  const order = rawPValues
    .map((value, index) => ({ value, index }))
    .sort((left, right) => left.value - right.value || left.index - right.index)
  const adjusted = Array(rawPValues.length).fill(0) as number[]
  let previous = 0
  for (const [rank, item] of order.entries()) {
    previous = Math.max(
      previous,
      Math.min(1, item.value * (rawPValues.length - rank)),
    )
    adjusted[item.index] = previous
  }
  for (const [index, metric] of result.metrics.entries()) {
    if (
      !isFiniteNumber(metric.holm_adjusted_p_value)
      || !numericallyEqual(metric.holm_adjusted_p_value, adjusted[index]!)
      || metric.family_wise_significant
        !== (adjusted[index]! <= expected.alpha)
    ) {
      return `comparison metric ${metric.metric} Holm evidence is inconsistent`
    }
  }
  return null
}

function batchVectorValues(
  batch: AnalysisBatchResult,
  metric: string,
): number[] | undefined {
  return batch.metric_vectors.find(([name]) => name === metric)?.[1]
}

function sharedBatchIdentityError(
  left: AnalysisBatchResult,
  right: AnalysisBatchResult,
): string | null {
  const fields: Array<keyof AnalysisBatchProvenance> = [
    'scenario_path',
    'data_root',
    'source_fingerprint',
    'data_revision',
    'data_file_count',
    'catalog_revision',
    'doctrine_catalog_fingerprint',
    'loaded_roster_loadout_fingerprint',
  ]
  if (fields.some((field) => (
    JSON.stringify(left[field]) !== JSON.stringify(right[field])
  ))) {
    return 'analysis batches do not share one source identity'
  }
  if (
    JSON.stringify(left.code_revision) !== JSON.stringify(right.code_revision)
    || JSON.stringify(left.authored_roster)
      !== JSON.stringify(right.authored_roster)
    || JSON.stringify(left.loaded_roster)
      !== JSON.stringify(right.loaded_roster)
  ) {
    return 'analysis batches do not share one runtime identity'
  }
  return null
}

export function validateCompareResult(
  result: CompareResult,
  expected: CompareExpectation,
): string | null {
  if (
    result.label_a !== expected.labelA
    || result.label_b !== expected.labelB
    || result.num_iterations !== expected.numIterations
    || !isFiniteNumber(result.alpha)
    || !numericallyEqual(result.alpha, expected.alpha)
  ) {
    return 'comparison response does not match the submitted request'
  }
  if (
    !Array.isArray(result.ordered_metrics)
    || !sameOrderedValues(result.ordered_metrics, expected.orderedMetrics)
  ) {
    return 'comparison metric order does not match the submitted request'
  }
  const expectedSeeds = Array.from(
    { length: expected.numIterations },
    (_, index) => expected.baseSeed + index,
  )
  if (
    !Array.isArray(result.seeds)
    || !sameOrderedValues(result.seeds, expectedSeeds)
  ) {
    return 'comparison seed evidence does not match the submitted request'
  }
  const rawAFailure = rawMetricMapError(
    result.raw_a,
    expected.orderedMetrics,
    expected.numIterations,
    'comparison A raw metrics',
  )
  if (rawAFailure) return rawAFailure
  const rawBFailure = rawMetricMapError(
    result.raw_b,
    expected.orderedMetrics,
    expected.numIterations,
    'comparison B raw metrics',
  )
  if (rawBFailure) return rawBFailure

  const batchAError = batchResultError(result.batch_a, {
    orderedMetrics: expected.orderedMetrics,
    seeds: expectedSeeds,
    baseSeed: expected.baseSeed,
    maxTicks: expected.maxTicks,
  })
  if (batchAError) return `comparison A: ${batchAError}`
  const batchBError = batchResultError(result.batch_b, {
    orderedMetrics: expected.orderedMetrics,
    seeds: expectedSeeds,
    baseSeed: expected.baseSeed,
    maxTicks: expected.maxTicks,
  })
  if (batchBError) return `comparison B: ${batchBError}`
  if (
    result.batch_a.variant_id !== 'a'
    || result.batch_b.variant_id !== 'b'
    || !scenarioMatches(result.batch_a.scenario_path, expected.scenario)
    || !scenarioMatches(result.batch_b.scenario_path, expected.scenario)
  ) {
    return 'comparison batch identity does not match the submitted request'
  }
  const sharedIdentityFailure = sharedBatchIdentityError(
    result.batch_a,
    result.batch_b,
  )
  if (sharedIdentityFailure) return sharedIdentityFailure
  for (const metric of expected.orderedMetrics) {
    if (
      !sameOrderedValues(
        result.raw_a[metric]!,
        batchVectorValues(result.batch_a, metric) ?? [],
      )
      || !sameOrderedValues(
        result.raw_b[metric]!,
        batchVectorValues(result.batch_b, metric) ?? [],
      )
    ) {
      return `comparison raw metric ${metric} differs from batch evidence`
    }
  }
  return compareStatisticError(result, expected)
}

export function validateDoctrineResult(
  result: DoctrineCompareResult,
  expected: DoctrineExpectation,
): string | null {
  if (
    result.num_iterations !== expected.numIterations
    || result.base_seed !== expected.baseSeed
    || result.max_ticks !== expected.maxTicks
    || !Array.isArray(result.ordered_metrics)
    || !sameOrderedValues(result.ordered_metrics, expected.orderedMetrics)
  ) {
    return 'doctrine response does not match the submitted request'
  }
  const expectedSeeds = Array.from(
    { length: expected.numIterations },
    (_, index) => expected.baseSeed + index,
  )
  if (
    !Array.isArray(result.seeds)
    || !sameOrderedValues(result.seeds, expectedSeeds)
    || !Array.isArray(result.results)
    || result.results.length !== expected.variants.length
  ) {
    return 'doctrine seed or variant evidence is incomplete'
  }
  if (!scenarioMatches(result.scenario, expected.scenario)) {
    return 'doctrine scenario does not match the submitted request'
  }

  const batches: AnalysisBatchResult[] = []
  const assignmentFingerprints: string[] = []
  for (const [variantIndex, variantResult] of result.results.entries()) {
    const expectedVariant = expected.variants[variantIndex]!
    if (
      variantResult.variant_id !== expectedVariant.variant_id
      || JSON.stringify(variantResult.assignments)
        !== JSON.stringify(expectedVariant.assignments)
    ) {
      return `doctrine variant ${variantIndex} policy does not match the submitted request`
    }
    if (
      !Array.isArray(variantResult.metrics)
      || variantResult.metrics.length !== expected.orderedMetrics.length
      || !sameOrderedValues(
        variantResult.metrics.map((metric) => metric.metric),
        expected.orderedMetrics,
      )
    ) {
      return `doctrine variant ${variantResult.variant_id} metric order is inconsistent`
    }
    const batchFailure = batchResultError(variantResult.batch, {
      orderedMetrics: expected.orderedMetrics,
      seeds: expectedSeeds,
      baseSeed: expected.baseSeed,
      maxTicks: expected.maxTicks,
    })
    if (batchFailure) {
      return `doctrine variant ${variantResult.variant_id}: ${batchFailure}`
    }
    if (
      variantResult.batch.variant_id !== expectedVariant.variant_id
      || variantResult.batch.scenario_path !== result.scenario
    ) {
      return `doctrine variant ${variantResult.variant_id} batch identity is inconsistent`
    }

    for (const [metricIndex, metric] of variantResult.metrics.entries()) {
      const vectorFailure = metricVectorError(
        metric.values,
        expected.numIterations,
        `doctrine variant ${variantResult.variant_id} metric ${metric.metric}`,
      )
      if (vectorFailure) return vectorFailure
      const batchValues = variantResult.batch.metric_vectors[metricIndex]![1]
      if (!sameOrderedValues(metric.values, batchValues)) {
        return `doctrine variant ${variantResult.variant_id} metric ${metric.metric} differs from batch evidence`
      }
      const mean = sampleMean(metric.values)
      if (
        !isFiniteNumber(metric.mean)
        || !numericallyEqual(metric.mean, mean)
        || !isFiniteNumber(metric.std)
        || !numericallyEqual(metric.std, sampleStd(metric.values, mean))
      ) {
        return `doctrine variant ${variantResult.variant_id} metric ${metric.metric} statistics are inconsistent`
      }
    }

    const policyBySide = new Map(
      expectedVariant.assignments.map((assignment) => [
        assignment.side,
        assignment.school_id,
      ]),
    )
    for (const run of variantResult.batch.runs) {
      const runtimeAssignments = [
        ...run.runtime_provenance.initial_unit_assignments,
        ...run.runtime_provenance.arriving_unit_assignments,
      ]
      if ([...policyBySide.keys()].some((side) => (
        !runtimeAssignments.some((assignment) => assignment.side === side)
      ))) {
        return `doctrine variant ${variantResult.variant_id} policy side is absent from runtime assignments`
      }
      if (runtimeAssignments.some((assignment) => (
        policyBySide.has(assignment.side)
        && assignment.doctrine_school_id !== policyBySide.get(assignment.side)
      ))) {
        return `doctrine variant ${variantResult.variant_id} policy is absent from runtime assignments`
      }
    }
    assignmentFingerprints.push(
      variantResult.batch.runs[0]!.runtime_provenance
        .doctrine_assignment_fingerprint,
    )
    batches.push(variantResult.batch)
  }

  for (const batch of batches.slice(1)) {
    const sharedIdentityFailure = sharedBatchIdentityError(batches[0]!, batch)
    if (sharedIdentityFailure) return sharedIdentityFailure
  }
  if (new Set(assignmentFingerprints).size !== assignmentFingerprints.length) {
    return 'doctrine variants do not have distinct assignment fingerprints'
  }
  return null
}

function statisticError(
  stats: MetricStats | undefined,
  values: number[],
  path: string,
): string | null {
  if (!stats) return `${path} statistics are missing`
  const mean = sampleMean(values)
  const expected: Record<keyof Omit<MetricStats, 'n'>, number> = {
    mean,
    median: percentile(values, 0.5),
    std: sampleStd(values, mean),
    min: Math.min(...values),
    max: Math.max(...values),
    p5: percentile(values, 0.05),
    p95: percentile(values, 0.95),
  }
  if (stats.n !== values.length) return `${path}.n is inconsistent`
  for (const [name, value] of Object.entries(expected)) {
    const actual = stats[name as keyof typeof expected]
    if (!isFiniteNumber(actual) || !numericallyEqual(actual, value)) {
      return `${path}.${name} is inconsistent`
    }
  }
  return null
}

export function validateBatchDetail(
  detail: BatchDetail,
  expected?: BatchExpectation,
): string | null {
  if (detail.status !== 'completed') return null
  if (
    expected
    && (
      (expected.batchId !== undefined && detail.batch_id !== expected.batchId)
      ||
      detail.scenario_name !== expected.scenario
      || detail.num_iterations !== expected.numIterations
      || detail.base_seed !== expected.baseSeed
      || detail.max_ticks !== expected.maxTicks
      || !sameOrderedValues(detail.ordered_metrics, expected.orderedMetrics)
    )
  ) {
    return 'completed batch does not match the submitted request'
  }
  if (
    !isStrictInteger(detail.num_iterations)
    || detail.num_iterations < 1
    || detail.completed_iterations !== detail.num_iterations
    || !isStrictInteger(detail.base_seed)
    || detail.base_seed < 0
    || !isStrictInteger(detail.max_ticks)
    || detail.max_ticks < 1
  ) {
    return 'completed batch run bounds are inconsistent'
  }
  if (
    !Array.isArray(detail.ordered_metrics)
    || detail.ordered_metrics.length === 0
    || new Set(detail.ordered_metrics).size !== detail.ordered_metrics.length
    || !detail.ordered_metrics.every(isNonEmptyTrimmed)
  ) {
    return 'completed batch metric order is invalid'
  }
  if (!detail.metrics || !detail.raw_metrics || !detail.provenance) {
    return 'completed batch is missing raw-vector or provenance evidence'
  }
  if (
    !sameOrderedValues(Object.keys(detail.metrics), detail.ordered_metrics)
    || !sameOrderedValues(Object.keys(detail.raw_metrics), detail.ordered_metrics)
  ) {
    return 'completed batch metric keys/order are inconsistent'
  }

  for (const metric of detail.ordered_metrics) {
    const values = detail.raw_metrics[metric]
    const vectorFailure = metricVectorError(
      values,
      detail.num_iterations,
      `raw metric ${metric}`,
    )
    if (vectorFailure) return vectorFailure
    const statsFailure = statisticError(detail.metrics[metric], values!, `metric ${metric}`)
    if (statsFailure) return statsFailure
  }

  const seeds = Array.from(
    { length: detail.num_iterations },
    (_, index) => detail.base_seed + index,
  )
  const provenanceFailure = provenanceError(detail.provenance, {
    orderedMetrics: detail.ordered_metrics,
    seeds,
    baseSeed: detail.base_seed,
    maxTicks: detail.max_ticks,
  })
  if (provenanceFailure) return provenanceFailure
  if (
    detail.provenance.variant_id !== 'batch'
    || (
      expected !== undefined
      && !scenarioMatches(detail.provenance.scenario_path, expected.scenario)
    )
  ) {
    return 'completed batch provenance identity is inconsistent'
  }
  return semanticMetricError(
    detail.provenance,
    detail.raw_metrics,
    detail.ordered_metrics,
  )
}

export function validateSweepResult(
  result: SweepResult,
  expected: SweepExpectation,
): string | null {
  if (result.parameter_name !== expected.parameterName) {
    return 'sweep parameter name is inconsistent'
  }
  if (
    !Array.isArray(result.ordered_metrics)
    || result.ordered_metrics.length === 0
    || !sameOrderedValues(result.ordered_metrics, expected.orderedMetrics)
    || new Set(result.ordered_metrics).size !== result.ordered_metrics.length
    || !result.ordered_metrics.every(isNonEmptyTrimmed)
  ) {
    return 'sweep metric order is invalid'
  }
  if (
    !Array.isArray(result.seeds)
    || result.seeds.length !== expected.numIterations
    || !result.seeds.every((seed, index) => (
      seed === result.base_seed + index && isStrictInteger(seed)
    ))
    || result.base_seed !== expected.baseSeed
  ) {
    return 'sweep seed evidence is incomplete'
  }
  if (
    result.max_ticks !== expected.maxTicks
    || !SHA256_PATTERN.test(result.source_fingerprint)
    || !isNonEmptyTrimmed(result.data_root)
  ) {
    return 'sweep source or run-bound evidence is invalid'
  }
  if (
    !Array.isArray(result.points)
    || result.points.length !== expected.values.length
  ) {
    return 'sweep point evidence is incomplete'
  }

  const configFingerprints: string[] = []
  for (const [pointIndex, point] of result.points.entries()) {
    if (
      !isFiniteNumber(point.parameter_value)
      || point.parameter_value !== expected.values[pointIndex]
    ) {
      return `sweep point ${pointIndex} parameter value is inconsistent`
    }
    if (
      !Array.isArray(point.metric_results)
      || point.metric_results.length !== result.ordered_metrics.length
      || !sameOrderedValues(
        point.metric_results.map((metric) => metric.metric),
        result.ordered_metrics,
      )
    ) {
      return `sweep point ${pointIndex} metric order is inconsistent`
    }

    const batchFailure = batchResultError(point.batch, {
      orderedMetrics: result.ordered_metrics,
      seeds: result.seeds,
      baseSeed: result.base_seed,
      maxTicks: result.max_ticks,
      sourceFingerprint: result.source_fingerprint,
      dataRoot: result.data_root,
    })
    if (batchFailure) return `sweep point ${pointIndex}: ${batchFailure}`
    if (!scenarioMatches(point.batch.scenario_path, expected.scenario)) {
      return `sweep point ${pointIndex} scenario does not match the submitted request`
    }
    configFingerprints.push(point.batch.config_fingerprint)

    for (const [metricIndex, metric] of point.metric_results.entries()) {
      const values = metric.values
      const vectorFailure = metricVectorError(
        values,
        expected.numIterations,
        `sweep point ${pointIndex} metric ${metric.metric}`,
      )
      if (vectorFailure) return vectorFailure
      const batchValues = point.batch.metric_vectors[metricIndex]![1]
      if (!sameOrderedValues(values, batchValues)) {
        return `sweep point ${pointIndex} metric ${metric.metric} raw vector is inconsistent`
      }
      const mean = sampleMean(values)
      const expectedStats = {
        mean,
        std: sampleStd(values, mean),
        min: Math.min(...values),
        max: Math.max(...values),
      }
      for (const [name, value] of Object.entries(expectedStats)) {
        const actual = metric[name as keyof typeof expectedStats]
        if (!isFiniteNumber(actual) || !numericallyEqual(actual, value)) {
          return `sweep point ${pointIndex} metric ${metric.metric} ${name} is inconsistent`
        }
      }
    }
  }
  if (new Set(configFingerprints).size !== configFingerprints.length) {
    return 'sweep point config fingerprints are not distinct'
  }
  return null
}
