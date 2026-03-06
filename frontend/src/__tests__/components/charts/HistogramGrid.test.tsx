import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../helpers'
import { HistogramGrid } from '../../../components/charts/HistogramGrid'
import type { MetricStats } from '../../../types/api'

vi.mock('../../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

const MOCK_METRICS: Record<string, MetricStats> = {
  red_destroyed: { mean: 5.2, median: 5, std: 1.1, min: 3, max: 8, p5: 3.5, p95: 7.5, n: 10 },
  blue_active: { mean: 8.1, median: 8, std: 0.9, min: 6, max: 10, p5: 6.5, p95: 9.5, n: 10 },
}

describe('HistogramGrid', () => {
  it('renders box plots for each metric', () => {
    renderWithProviders(<HistogramGrid metrics={MOCK_METRICS} />)
    expect(screen.getByText('red_destroyed')).toBeInTheDocument()
    expect(screen.getByText('blue_active')).toBeInTheDocument()
    expect(screen.getAllByTestId('plotly-chart')).toHaveLength(2)
  })

  it('shows stats summary', () => {
    renderWithProviders(<HistogramGrid metrics={MOCK_METRICS} />)
    expect(screen.getAllByText(/mean:/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/n=10/).length).toBeGreaterThan(0)
  })

  it('shows empty state with no metrics', () => {
    renderWithProviders(<HistogramGrid metrics={{}} />)
    expect(screen.getByText('No metrics available')).toBeInTheDocument()
  })
})
