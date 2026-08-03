import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchScenarios, fetchScenario } from '../../api/scenarios'
import type {
  HistoricalValidationSummary,
  ScenarioDetail,
  ScenarioSummary,
} from '../../types/api'

beforeEach(() => {
  vi.restoreAllMocks()
})

const HISTORICAL_VALIDATION: HistoricalValidationSummary = {
  aggregate_disposition: 'unsupported',
  current_engine_regression_evidence: true,
  accepted_claim_ids: [],
  ledger_sha256: 'a'.repeat(64),
  claims: [],
}

const MOCK_SCENARIO: ScenarioSummary = {
  name: '73_easting',
  display_name: '73 Easting',
  era: 'modern',
  duration_hours: 4,
  sides: ['blue', 'red'],
  terrain_type: 'desert',
  has_ew: false,
  has_cbrn: false,
  has_escalation: false,
  has_schools: false,
  has_space: false,
  has_dew: false,
  historical_validation: HISTORICAL_VALIDATION,
}

describe('fetchScenarios', () => {
  it('returns scenario list from /api/scenarios', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([MOCK_SCENARIO]), { status: 200 }),
    )
    const result = await fetchScenarios()
    expect(result).toEqual([MOCK_SCENARIO])
    expect(fetch).toHaveBeenCalledWith('/api/scenarios')
  })
})

describe('fetchScenario', () => {
  it('returns scenario detail from /api/scenarios/:name', async () => {
    const detail: ScenarioDetail = {
      name: '73_easting',
      config: { name: '73 Easting', era: 'modern' },
      force_summary: { blue: { unit_count: 3, unit_types: ['m1a1_abrams'] } },
      historical_validation: HISTORICAL_VALIDATION,
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )
    const result = await fetchScenario('73_easting')
    expect(result).toEqual(detail)
    expect(fetch).toHaveBeenCalledWith('/api/scenarios/73_easting')
  })

  it('encodes special characters in name', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        name: 'test name',
        config: {},
        force_summary: {},
        historical_validation: HISTORICAL_VALIDATION,
      }), { status: 200 }),
    )
    await fetchScenario('test name')
    expect(fetch).toHaveBeenCalledWith('/api/scenarios/test%20name')
  })
})
