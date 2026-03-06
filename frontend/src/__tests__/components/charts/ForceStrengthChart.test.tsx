import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../helpers'
import { ForceStrengthChart } from '../../../components/charts/ForceStrengthChart'
import type { ForceTimePoint } from '../../../lib/eventProcessing'

vi.mock('../../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

describe('ForceStrengthChart', () => {
  it('renders chart with data', () => {
    const data: ForceTimePoint[] = [
      { tick: 0, blue: 10, red: 8 },
      { tick: 5, blue: 10, red: 7 },
    ]
    renderWithProviders(<ForceStrengthChart data={data} />)
    expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
  })

  it('shows empty state with no data', () => {
    renderWithProviders(<ForceStrengthChart data={[]} />)
    expect(screen.getByText('No force data available')).toBeInTheDocument()
  })
})
