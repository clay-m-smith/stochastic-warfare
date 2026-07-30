import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { DoctrineComparePanel } from '../../../pages/analysis/DoctrineComparePanel'
import { doctrineCompareResult } from '../../fixtures/analysis'
import type { DoctrineCompareResult } from '../../../types/analysis'

const MOCK_SCENARIOS = [
  { name: '73_easting', display_name: '73 Easting', era: 'modern', duration_hours: 4, sides: ['blue', 'red'], terrain_type: 'desert', has_ew: false, has_cbrn: false, has_escalation: false, has_schools: true, has_space: false, has_dew: false },
  { name: 'austerlitz', display_name: 'Austerlitz', era: 'napoleonic', duration_hours: 10, sides: ['french', 'coalition'], terrain_type: 'hilly_defense', has_ew: false, has_cbrn: false, has_escalation: false, has_schools: true, has_space: false, has_dew: false },
]

const MOCK_SCHOOLS = [
  { school_id: 'maneuverist', display_name: 'Maneuver Warfare', description: '', ooda_multiplier: 1.2, risk_tolerance: 'high' },
  { school_id: 'attrition', display_name: 'Attrition', description: '', ooda_multiplier: 0.9, risk_tolerance: 'low' },
  { school_id: 'clausewitzian', display_name: 'Clausewitzian', description: '', ooda_multiplier: 1.0, risk_tolerance: 'medium' },
]

function renderPanel(doctrineResult?: DoctrineCompareResult) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const urlStr = typeof url === 'string' ? url : url.toString()
    if (urlStr.includes('/meta/schools')) {
      return new Response(JSON.stringify(MOCK_SCHOOLS), { status: 200 })
    }
    if (urlStr.includes('/scenarios')) {
      return new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 })
    }
    if (urlStr.includes('/analysis/doctrine-compare') && doctrineResult) {
      return new Response(JSON.stringify(doctrineResult), { status: 200 })
    }
    return new Response(JSON.stringify([]), { status: 200 })
  })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DoctrineComparePanel />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return fetchSpy
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('DoctrineComparePanel', () => {
  it('renders scenario selector and school checkboxes', async () => {
    renderPanel()
    await waitFor(() => {
      expect(screen.getByText('Doctrine Comparison')).toBeInTheDocument()
    })
    // School checkboxes should load
    await waitFor(() => {
      expect(screen.getByText('Maneuver Warfare')).toBeInTheDocument()
    })
    expect(screen.getByText('Attrition')).toBeInTheDocument()
    expect(screen.getByText('Clausewitzian')).toBeInTheDocument()
  })

  it('shows side to vary selector', async () => {
    renderPanel()
    await waitFor(() => {
      expect(screen.getByLabelText('Side to vary')).toBeInTheDocument()
    })
  })

  it('submit button is disabled without enough schools', async () => {
    renderPanel()
    await waitFor(() => {
      expect(screen.getByText('Run Comparison')).toBeInTheDocument()
    })
    expect(screen.getByText('Run Comparison')).toBeDisabled()
  })

  it('submits typed assignments and renders raw vectors with batch provenance', async () => {
    const user = userEvent.setup()
    const response = doctrineCompareResult()
    const fetchSpy = renderPanel(response)

    await screen.findByText('Maneuver Warfare')
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[0]!, '73_easting')
    await user.click(screen.getByRole('checkbox', { name: 'Maneuver Warfare' }))
    await user.click(screen.getByRole('checkbox', { name: 'Attrition' }))
    await user.click(screen.getByRole('button', { name: 'Run Comparison' }))

    await screen.findByRole('columnheader', { name: 'win blue' })
    expect(screen.getByText('blue: maneuverist')).toBeInTheDocument()
    expect(screen.getByText('blue: attrition')).toBeInTheDocument()
    expect(screen.getByText('raw: [1,1,0,1,0,1,1,0,1,0]')).toBeInTheDocument()
    expect(screen.getByText('raw: [0,1,0,0,1,0,1,0,0,1]')).toBeInTheDocument()
    expect(
      screen.getAllByText('raw: [1,2,3,4,5,6,7,8,9,10]'),
    ).toHaveLength(2)
    expect(
      screen.getAllByText('raw: [2,3,4,5,6,7,8,9,10,11]'),
    ).toHaveLength(2)
    expect(screen.getAllByText('Provenance')).toHaveLength(2)
    expect(
      screen.getAllByText('Source: ' + 'a'.repeat(64)),
    ).toHaveLength(2)
    expect(
      screen.getByText(`Doctrine assignment: ${'7'.repeat(64)}`),
    ).toBeInTheDocument()
    expect(
      screen.getByText(`Loadout topology: ${'4'.repeat(64)}`),
    ).toBeInTheDocument()

    const renderedText = document.body.textContent ?? ''
    expect(renderedText).not.toMatch(/Mann[-\s]?Whitney/i)
    expect(renderedText).not.toMatch(/rank[-\s]?biserial/i)

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/api/analysis/doctrine-compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: '73_easting',
          variants: [
            {
              variant_id: 'maneuverist',
              assignments: [{ side: 'blue', school_id: 'maneuverist' }],
            },
            {
              variant_id: 'attrition',
              assignments: [{ side: 'blue', school_id: 'attrition' }],
            },
          ],
          metrics: [
            'win_blue',
            'blue_destroyed',
            'red_destroyed',
            'ticks_executed',
          ],
          num_iterations: 10,
          base_seed: 42,
          max_ticks: 10000,
        }),
      })
    })
  })

  it('resets to exact Austerlitz sides and submits non-blue metrics', async () => {
    const user = userEvent.setup()
    const fetchSpy = renderPanel(doctrineCompareResult({
      scenarioPath: '/data/eras/napoleonic/scenarios/austerlitz/scenario.yaml',
      sides: ['french', 'coalition'],
      sideToVary: 'french',
    }))

    await screen.findByText('Maneuver Warfare')
    const scenarioSelect = screen.getAllByRole('combobox')[0]!
    const sideSelect = screen.getByLabelText('Side to vary')
    await user.selectOptions(scenarioSelect, '73_easting')
    await user.selectOptions(sideSelect, 'red')
    expect(sideSelect).toHaveValue('red')

    await user.selectOptions(scenarioSelect, 'austerlitz')
    expect(sideSelect).toHaveValue('french')
    expect(screen.getByRole('option', { name: 'french' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'coalition' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Blue' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: 'Maneuver Warfare' }))
    await user.click(screen.getByRole('checkbox', { name: 'Attrition' }))
    await user.click(screen.getByRole('button', { name: 'Run Comparison' }))

    await screen.findByText('french: maneuverist')
    expect(screen.getByText('french: attrition')).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/api/analysis/doctrine-compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: 'austerlitz',
          variants: [
            {
              variant_id: 'maneuverist',
              assignments: [{ side: 'french', school_id: 'maneuverist' }],
            },
            {
              variant_id: 'attrition',
              assignments: [{ side: 'french', school_id: 'attrition' }],
            },
          ],
          metrics: [
            'win_french',
            'french_destroyed',
            'coalition_destroyed',
            'ticks_executed',
          ],
          num_iterations: 10,
          base_seed: 42,
          max_ticks: 10000,
        }),
      })
    })
  })

  it('visibly rejects doctrine evidence whose mapped side is absent at runtime', async () => {
    const response = doctrineCompareResult()
    for (const run of response.results[0]!.batch.runs) {
      run.runtime_provenance.initial_unit_assignments = (
        run.runtime_provenance.initial_unit_assignments.filter(
          (assignment) => assignment.side !== 'blue',
        )
      )
    }
    renderPanel(response)
    const user = userEvent.setup()

    await screen.findByText('Maneuver Warfare')
    await user.selectOptions(screen.getAllByRole('combobox')[0]!, '73_easting')
    await user.click(screen.getByRole('checkbox', { name: 'Maneuver Warfare' }))
    await user.click(screen.getByRole('checkbox', { name: 'Attrition' }))
    await user.click(screen.getByRole('button', { name: 'Run Comparison' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Doctrine result rejected:',
      )
    })
    expect(screen.queryByText('blue: maneuverist')).not.toBeInTheDocument()
  })
})
