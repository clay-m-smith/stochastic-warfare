import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../helpers'
import { SuppressionChart } from '../../../components/charts/SuppressionChart'
import type { SuppressionAnalytics } from '../../../types/analytics'

vi.mock('../../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

describe('SuppressionChart', () => {
  it('renders chart with suppression data', () => {
    const data: SuppressionAnalytics = {
      peak_suppressed: 5,
      peak_tick: 10,
      rout_cascades: 2,
      timeline: [
        { tick: 5, count: 2 },
        { tick: 10, count: 5 },
        { tick: 15, count: 3 },
      ],
    }
    renderWithProviders(<SuppressionChart data={data} dt={5} />)
    expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
    expect(screen.getByText(/2 rout cascades/)).toBeInTheDocument()
  })

  it('shows empty state with no timeline', () => {
    const data: SuppressionAnalytics = {
      peak_suppressed: 0, peak_tick: 0, rout_cascades: 0, timeline: [],
    }
    renderWithProviders(<SuppressionChart data={data} dt={5} />)
    expect(screen.getByText('No suppression events recorded')).toBeInTheDocument()
  })
})
