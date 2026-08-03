import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { ScenarioDetailPage } from '../../pages/scenarios/ScenarioDetailPage'
import { Routes, Route } from 'react-router-dom'
import type { ScenarioDetail } from '../../types/api'

const MOCK_DETAIL: ScenarioDetail = {
  name: '73_easting',
  config: {
    name: '73 Easting',
    era: 'modern',
    duration_hours: 4,
    terrain: {
      terrain_type: 'desert',
      width_m: 5000,
      height_m: 5000,
      base_elevation_m: 200,
    },
    weather_conditions: { visibility_m: 800, wind_speed_mps: 4.5 },
    ew_config: {},
    cbrn_config: {},
    escalation_config: {},
    school_config: {},
    space_config: {},
    dew_config: {},
    documented_outcomes: [
      { metric: 'Blue casualties', value: '1 KIA', source: 'Bourque 2001' },
    ],
  },
  force_summary: {
    blue: { unit_count: 3, unit_types: ['m1a1_abrams', 'm3_bradley'] },
    red: { unit_count: 5, unit_types: ['t72', 'bmp2'] },
  },
  historical_validation: {
    aggregate_disposition: 'unsupported',
    current_engine_regression_evidence: true,
    accepted_claim_ids: [],
    ledger_sha256: 'a'.repeat(64),
    claims: [
      {
        claim_id: 'scenario.73_easting.documented_outcomes',
        disposition: 'unsupported',
        reason_codes: ['legacy_metadata_not_runtime_loaded'],
        limitation: 'Legacy metadata is not production historical-validation evidence.',
        intended_use: 'historical_outcome_consistency',
        metric_scope: ['exchange_ratio'],
        event_scope: 'legacy_unspecified',
        current_engine_regression_evidence: true,
        accepted_study_id: null,
        accepted_artifact_path: null,
      },
    ],
  },
}

beforeEach(() => {
  vi.restoreAllMocks()
})

function renderDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/scenarios/:name" element={<ScenarioDetailPage />} />
    </Routes>,
    { route: '/scenarios/73_easting' },
  )
}

describe('ScenarioDetailPage', () => {
  it('renders scenario name and era badge', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    expect(screen.getByText('Modern')).toBeInTheDocument()
  })

  it('displays force table', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('blue')).toBeInTheDocument()
    })
    expect(screen.getByText('red')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('shows every configured optional-subsystem badge', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => expect(screen.getByText('Electronic Warfare')).toBeInTheDocument())
    expect(screen.getByText('CBRN')).toBeInTheDocument()
    expect(screen.getByText('Escalation')).toBeInTheDocument()
    expect(screen.getByText('Doctrinal Schools')).toBeInTheDocument()
    expect(screen.getByText('Space')).toBeInTheDocument()
    expect(screen.getByText('Directed Energy Weapons')).toBeInTheDocument()
  })

  it('shows canonical terrain and weather measurements with source units', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('desert')).toBeInTheDocument()
    })
    expect(screen.getByText('200m')).toBeInTheDocument()
    expect(screen.getByText('800 m')).toBeInTheDocument()
    expect(screen.getByText('4.5 m/s')).toBeInTheDocument()
  })

  it('shows typed unsupported status and never renders raw legacy outcomes', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('Historical Validation')).toBeInTheDocument()
    })
    expect(screen.getAllByText(/Unsupported/i)).toHaveLength(2)
    expect(
      screen.getByText(
        'Current-engine regression evidence exists, but it is not historical validation or predictive calibration.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Legacy metadata is not production historical-validation evidence.'),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText(
        'Current-engine regression evidence for scenario.73_easting.documented_outcomes',
      ),
    ).toHaveTextContent('Present')
    expect(screen.queryByText('Documented Outcomes')).not.toBeInTheDocument()
    expect(screen.queryByText('Blue casualties')).not.toBeInTheDocument()
    expect(screen.queryByText('Bourque 2001')).not.toBeInTheDocument()
  })

  it('preserves accepted claim truth when a mixed scenario aggregates unsupported', async () => {
    const mixedDetail: ScenarioDetail = {
      ...MOCK_DETAIL,
      historical_validation: {
        ...MOCK_DETAIL.historical_validation,
        accepted_claim_ids: ['scenario.73_easting.accepted_scope'],
        claims: [
          {
            claim_id: 'scenario.73_easting.accepted_scope',
            disposition: 'production_validated',
            reason_codes: ['accepted_production_evidence'],
            limitation: 'Only this exact claim scope is accepted.',
            intended_use: 'historical_outcome_consistency',
            metric_scope: ['american_vehicles_destroyed'],
            event_scope: 'source_synchronous_cutoff',
            current_engine_regression_evidence: false,
            accepted_study_id: '73_easting.accepted.v1',
            accepted_artifact_path: 'docs/evidence/accepted.json',
          },
          ...MOCK_DETAIL.historical_validation.claims,
        ],
      },
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mixedDetail), { status: 200 }),
    )

    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('scenario.73_easting.accepted_scope')).toBeInTheDocument()
    })
    expect(screen.getByText('Production Validated')).toBeInTheDocument()
    expect(screen.getAllByText('Unsupported')).toHaveLength(2)
    expect(screen.getByText(/Only the accepted claim scopes listed below/)).toBeInTheDocument()
    expect(screen.queryByText(/No accepted production/)).not.toBeInTheDocument()
    expect(
      screen.getByLabelText(
        'Current-engine regression evidence for scenario.73_easting.accepted_scope',
      ),
    ).toHaveTextContent('None recorded')
    expect(
      screen.getByLabelText(
        'Current-engine regression evidence for scenario.73_easting.documented_outcomes',
      ),
    ).toHaveTextContent('Present')
  })

  it('shows Run This Scenario button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('Run This Scenario')).toBeInTheDocument()
    })
  })
})
