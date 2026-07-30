import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { ComparisonCharts } from '../../../components/charts/ComparisonCharts'
import { renderWithProviders } from '../../helpers'
import type {
  AnalysisBatchResult,
  CompareResult,
  RuntimeProvenance,
} from '../../../types/analysis'

vi.mock('../../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

const SHA = 'a'.repeat(64)
const RUNTIME_PROVENANCE: RuntimeProvenance = {
  code_revision: {
    commit: '1'.repeat(40),
    dirty: false,
    worktree_fingerprint: SHA,
  },
  data_revision: SHA,
  data_file_count: 12,
  catalog_revision: SHA,
  doctrine_catalog_fingerprint: SHA,
  doctrine_assignment_fingerprint: SHA,
  loaded_roster_loadout_fingerprint: SHA,
  final_roster_loadout_fingerprint: SHA,
  initial_unit_assignments: [],
  arriving_unit_assignments: [],
}

function batch(variantId: string): AnalysisBatchResult {
  return {
    scenario_path: '/data/scenarios/test/scenario.yaml',
    data_root: '/data',
    variant_id: variantId,
    ordered_metrics: ['red_destroyed'],
    base_seed: 42,
    seeds: [42, 43, 44, 45],
    max_ticks: 100,
    source_fingerprint: SHA,
    config_fingerprint: SHA,
    authored_roster: [['blue', 1], ['red', 1]],
    loaded_roster: [['blue', 1], ['red', 1]],
    code_revision: RUNTIME_PROVENANCE.code_revision,
    data_revision: SHA,
    data_file_count: 12,
    catalog_revision: SHA,
    doctrine_catalog_fingerprint: SHA,
    loaded_roster_loadout_fingerprint: SHA,
    initial_unit_assignments: [],
    metric_vectors: [['red_destroyed', [0, 1, 1, 2]]],
    runs: [{
      variant_id: variantId,
      seed: 42,
      ticks_executed: 10,
      duration_s: 50,
      winning_side: 'blue',
      condition_type: 'time_expired',
      game_over: true,
      source_fingerprint: SHA,
      config_fingerprint: SHA,
      authored_roster: [['blue', 1], ['red', 1]],
      loaded_roster: [['blue', 1], ['red', 1]],
      runtime_provenance: RUNTIME_PROVENANCE,
    }],
  }
}

const RESULT: CompareResult = {
  label_a: 'Control',
  label_b: 'Variant',
  num_iterations: 4,
  alpha: 0.05,
  ordered_metrics: ['red_destroyed'],
  seeds: [42, 43, 44, 45],
  metrics: [
    {
      metric: 'red_destroyed',
      mean_a: 1,
      std_a: 0.5,
      mean_b: 2,
      std_b: 0.5,
      n_total: 4,
      n_nonzero: 3,
      positive: 2,
      negative: 1,
      tied: 1,
      mean_paired_difference: 1,
      median_paired_difference: 1,
      paired_superiority: 0.625,
      raw_p_value: 0.5,
      holm_adjusted_p_value: 0.5,
      alpha: 0.05,
      family_wise_significant: false,
    },
  ],
  raw_a: { red_destroyed: [0, 1, 1, 2] },
  raw_b: { red_destroyed: [1, 0, 1, 6] },
  batch_a: batch('a'),
  batch_b: batch('b'),
}

describe('ComparisonCharts', () => {
  it('renders paired direction, counts, superiority, and adjusted evidence', () => {
    renderWithProviders(
      <ComparisonCharts
        result={RESULT}
        labelA="Control"
        labelB="Variant"
      />,
    )

    expect(
      screen.getByText('Variant higher / mean 1.000 / median 1.000'),
    ).toBeInTheDocument()
    expect(screen.getByText('2 / 1 / 1')).toBeInTheDocument()
    expect(screen.getByText('0.625')).toBeInTheDocument()
    expect(screen.getByText('0.5000 / 0.5000')).toBeInTheDocument()
    expect(screen.getByText('no')).toBeInTheDocument()
    expect(screen.queryByText(/Mann-Whitney/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Effect Size/i)).not.toBeInTheDocument()
    expect(
      screen.getByLabelText('Comparison raw vectors and provenance'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Control raw red_destroyed: [0,1,1,2]'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Variant raw red_destroyed: [1,0,1,6]'),
    ).toBeInTheDocument()
    expect(screen.getAllByText('Doctrine assignment:')).toHaveLength(2)
  })
})
