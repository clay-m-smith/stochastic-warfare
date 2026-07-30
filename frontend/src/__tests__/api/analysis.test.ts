import { describe, it, expect, vi, beforeEach } from 'vitest'
import { runCompare, runSweep } from '../../api/analysis'
import { analysisBatch, evidenceBatch } from '../fixtures/analysis'
import type { CompareResult, SweepResult } from '../../types/analysis'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('runCompare', () => {
  it('preserves paired vectors, exact test counts, p-values, and provenance', async () => {
    const seeds = [101, 102, 103, 104, 105, 106]
    const response: CompareResult = {
      label_a: 'Control',
      label_b: 'High lethality',
      num_iterations: 6,
      alpha: 0.05,
      ordered_metrics: ['red_destroyed', 'ticks_executed'],
      seeds,
      metrics: [
        {
          metric: 'red_destroyed',
          mean_a: 0,
          std_a: 0,
          mean_b: 5 / 6,
          std_b: 0.408248290463863,
          n_total: 6,
          n_nonzero: 5,
          positive: 5,
          negative: 0,
          tied: 1,
          mean_paired_difference: 5 / 6,
          median_paired_difference: 1,
          paired_superiority: 11 / 12,
          raw_p_value: 0.0625,
          holm_adjusted_p_value: 0.125,
          alpha: 0.05,
          family_wise_significant: false,
        },
        {
          metric: 'ticks_executed',
          mean_a: 100,
          std_a: 0,
          mean_b: 100,
          std_b: 0,
          n_total: 6,
          n_nonzero: 0,
          positive: 0,
          negative: 0,
          tied: 6,
          mean_paired_difference: 0,
          median_paired_difference: 0,
          paired_superiority: 0.5,
          raw_p_value: 1,
          holm_adjusted_p_value: 1,
          alpha: 0.05,
          family_wise_significant: false,
        },
      ],
      raw_a: {
        red_destroyed: [0, 0, 0, 0, 0, 0],
        ticks_executed: [100, 100, 100, 100, 100, 100],
      },
      raw_b: {
        red_destroyed: [1, 1, 1, 1, 1, 0],
        ticks_executed: [100, 100, 100, 100, 100, 100],
      },
      batch_a: analysisBatch(
        'control',
        'maneuverist',
        [
          ['red_destroyed', [0, 0, 0, 0, 0, 0]],
          ['ticks_executed', [100, 100, 100, 100, 100, 100]],
        ],
        seeds,
      ),
      batch_b: analysisBatch(
        'high-lethality',
        'attrition',
        [
          ['red_destroyed', [1, 1, 1, 1, 1, 0]],
          ['ticks_executed', [100, 100, 100, 100, 100, 100]],
        ],
        seeds,
      ),
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(response), { status: 200 }),
    )
    const request = {
      scenario: 'test',
      label_a: 'Control',
      label_b: 'High lethality',
      metrics: ['red_destroyed', 'ticks_executed'],
      num_iterations: 6,
      base_seed: 101,
      max_ticks: 500,
      alpha: 0.05,
    }

    const result = await runCompare(request)

    expect(result).toStrictEqual(response)
    expect(result.raw_a.red_destroyed).toStrictEqual([0, 0, 0, 0, 0, 0])
    expect(result.raw_b.red_destroyed).toStrictEqual([1, 1, 1, 1, 1, 0])
    expect(result.metrics[0]).toMatchObject({
      n_total: 6,
      n_nonzero: 5,
      positive: 5,
      negative: 0,
      tied: 1,
      raw_p_value: 0.0625,
      holm_adjusted_p_value: 0.125,
    })
    expect(result.batch_a.metric_vectors).toStrictEqual([
      ['red_destroyed', [0, 0, 0, 0, 0, 0]],
      ['ticks_executed', [100, 100, 100, 100, 100, 100]],
    ])
    expect(result.batch_b.runs[0]?.runtime_provenance).toMatchObject({
      data_file_count: 184,
      doctrine_assignment_fingerprint: 'high-lethality-assignment-digest',
      final_roster_loadout_fingerprint: 'high-lethality-final-loadout-digest',
    })
    expect(fetch).toHaveBeenCalledWith('/api/analysis/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  })
})

describe('runSweep', () => {
  it('preserves ordered raw vectors and production provenance', async () => {
    const seeds = [42, 43, 44]
    const values = [3, 5, 7]
    const response: SweepResult = {
      parameter_name: 'hit_probability_modifier',
      ordered_metrics: ['red_destroyed'],
      base_seed: 42,
      seeds,
      max_ticks: 100,
      source_fingerprint: 'a'.repeat(64),
      data_root: '/data',
      points: [{
        parameter_value: 1,
        metric_results: [{
          metric: 'red_destroyed',
          mean: 5,
          std: 2,
          min: 3,
          max: 7,
          values,
        }],
        batch: evidenceBatch(
          'point-0',
          [['red_destroyed', values]],
          seeds,
          100,
          { unitsPerSide: 10 },
        ),
      }],
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(response), { status: 200 }),
    )
    const request = {
      scenario: 'test',
      parameter_name: 'hit_probability_modifier',
      values: [1],
      num_iterations: 3,
      base_seed: 42,
      max_ticks: 100,
    }

    const result = await runSweep(request)

    expect(result).toStrictEqual(response)
    expect(result.points[0]?.metric_results[0]?.values).toStrictEqual(values)
    expect(result.points[0]?.batch.metric_vectors).toStrictEqual([
      ['red_destroyed', values],
    ])
    expect(result.points[0]?.batch.runs[0]?.runtime_provenance).toMatchObject({
      doctrine_assignment_fingerprint: '7'.repeat(64),
      final_roster_loadout_fingerprint: '8'.repeat(64),
    })
    expect(fetch).toHaveBeenCalledWith('/api/analysis/sweep', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  })
})
