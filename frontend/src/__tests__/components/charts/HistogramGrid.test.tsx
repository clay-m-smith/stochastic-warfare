import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../helpers'
import { HistogramGrid } from '../../../components/charts/HistogramGrid'
import type { MetricStats } from '../../../types/api'

vi.mock('../../../components/charts/PlotlyChart', () => ({
  PlotlyChart: ({ data }: { data: Array<{ x?: unknown[] }> }) => (
    <div data-testid="plotly-chart" data-values={JSON.stringify(data[0]?.x)} />
  ),
}))

const MOCK_METRICS: Record<string, MetricStats> = {
  red_destroyed: { mean: 5.2, median: 5, std: 1.1, min: 3, max: 8, p5: 3.5, p95: 7.5, n: 10 },
  blue_active: { mean: 8.1, median: 8, std: 0.9, min: 6, max: 10, p5: 6.5, p95: 9.5, n: 10 },
}
const ORDERED_METRICS = ['red_destroyed', 'blue_active']
const RAW_METRICS = {
  red_destroyed: [3, 4, 5, 5, 5, 5, 5, 6, 6, 8],
  blue_active: [6, 7, 8, 8, 8, 8, 8, 9, 9, 10],
}

describe('HistogramGrid', () => {
  it('plots every actual raw value in declared metric order', () => {
    renderWithProviders(
      <HistogramGrid
        metrics={MOCK_METRICS}
        orderedMetrics={ORDERED_METRICS}
        rawMetrics={RAW_METRICS}
      />,
    )
    expect(screen.getByText('red_destroyed')).toBeInTheDocument()
    expect(screen.getByText('blue_active')).toBeInTheDocument()
    const charts = screen.getAllByTestId('plotly-chart')
    expect(charts).toHaveLength(2)
    expect(charts[0]).toHaveAttribute(
      'data-values',
      JSON.stringify(RAW_METRICS.red_destroyed),
    )
    expect(charts[1]).toHaveAttribute(
      'data-values',
      JSON.stringify(RAW_METRICS.blue_active),
    )
  })

  it('shows stats summary', () => {
    renderWithProviders(
      <HistogramGrid
        metrics={MOCK_METRICS}
        orderedMetrics={ORDERED_METRICS}
        rawMetrics={RAW_METRICS}
      />,
    )
    expect(screen.getAllByText(/mean:/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/n=10/).length).toBeGreaterThan(0)
    expect(
      screen.getByText(`raw: ${JSON.stringify(RAW_METRICS.red_destroyed)}`),
    ).toBeInTheDocument()
  })

  it('shows empty state with no metrics', () => {
    renderWithProviders(
      <HistogramGrid metrics={{}} orderedMetrics={[]} rawMetrics={{}} />,
    )
    expect(screen.getByText('No metrics available')).toBeInTheDocument()
  })
})
