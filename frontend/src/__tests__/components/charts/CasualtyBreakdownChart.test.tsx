import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../helpers'
import { CasualtyBreakdownChart } from '../../../components/charts/CasualtyBreakdownChart'
import type { CasualtyAnalytics } from '../../../types/analytics'

vi.mock('../../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

describe('CasualtyBreakdownChart', () => {
  it('renders chart with data', () => {
    const data: CasualtyAnalytics = {
      groups: [
        { label: 'm256', count: 5, side: 'red' },
        { label: 'rpg7', count: 2, side: 'blue' },
      ],
      total: 7,
    }
    renderWithProviders(<CasualtyBreakdownChart data={data} />)
    expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
  })

  it('shows empty state with no casualties', () => {
    renderWithProviders(<CasualtyBreakdownChart data={{ groups: [], total: 0 }} />)
    expect(screen.getByText('No casualties recorded')).toBeInTheDocument()
  })
})
