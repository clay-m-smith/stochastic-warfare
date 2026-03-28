import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../helpers'
import { EngagementSummaryChart } from '../../../components/charts/EngagementSummaryChart'
import type { EngagementAnalytics } from '../../../types/analytics'

vi.mock('../../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

describe('EngagementSummaryChart', () => {
  it('renders chart with engagement data', () => {
    const data: EngagementAnalytics = {
      by_type: [
        { type: 'DIRECT_FIRE', count: 100, hit_rate: 0.25 },
        { type: 'INDIRECT_FIRE', count: 30, hit_rate: 0.1 },
      ],
      total: 130,
    }
    renderWithProviders(<EngagementSummaryChart data={data} />)
    expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
  })

  it('shows empty state with no engagements', () => {
    renderWithProviders(<EngagementSummaryChart data={{ by_type: [], total: 0 }} />)
    expect(screen.getByText('No engagements recorded')).toBeInTheDocument()
  })
})
