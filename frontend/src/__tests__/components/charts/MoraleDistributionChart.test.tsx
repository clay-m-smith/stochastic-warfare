import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../helpers'
import { MoraleDistributionChart } from '../../../components/charts/MoraleDistributionChart'
import type { MoraleAnalytics } from '../../../types/analytics'

vi.mock('../../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

describe('MoraleDistributionChart', () => {
  it('renders chart with morale data', () => {
    const data: MoraleAnalytics = {
      timeline: [
        { tick: 1, steady: 8, shaken: 2, broken: 0, routed: 0, surrendered: 0 },
        { tick: 5, steady: 5, shaken: 3, broken: 2, routed: 0, surrendered: 0 },
      ],
    }
    renderWithProviders(<MoraleDistributionChart data={data} dt={5} />)
    expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
  })

  it('shows empty state with no morale data', () => {
    renderWithProviders(<MoraleDistributionChart data={{ timeline: [] }} dt={5} />)
    expect(screen.getByText('No morale transitions recorded')).toBeInTheDocument()
  })
})
