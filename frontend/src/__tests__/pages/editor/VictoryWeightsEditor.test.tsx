import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { VictoryWeightsEditor } from '../../../pages/editor/VictoryWeightsEditor'

describe('VictoryWeightsEditor', () => {
  const dispatch = vi.fn()
  const config = { calibration_overrides: {} }

  it('renders 3 sliders with correct labels', () => {
    render(<VictoryWeightsEditor config={config} dispatch={dispatch} />)
    expect(screen.getByLabelText('Force Ratio')).toBeInTheDocument()
    expect(screen.getByLabelText('Morale Ratio')).toBeInTheDocument()
    expect(screen.getByLabelText('Casualty Exchange')).toBeInTheDocument()
  })

  it('dispatches SET_VICTORY_WEIGHT on slider change', () => {
    dispatch.mockClear()
    render(<VictoryWeightsEditor config={config} dispatch={dispatch} />)
    const slider = screen.getByLabelText('Force Ratio')
    fireEvent.change(slider, { target: { value: '0.6' } })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'SET_VICTORY_WEIGHT',
      key: 'force_ratio',
      value: 0.6,
    })
  })

  it('shows normalized percentage display', () => {
    const configWithWeights = {
      calibration_overrides: {
        victory_weights: { force_ratio: 0.6, morale_ratio: 0.3, casualty_exchange: 0.1 },
      },
    }
    render(<VictoryWeightsEditor config={configWithWeights} dispatch={dispatch} />)
    expect(screen.getByText('(60%)')).toBeInTheDocument()
    expect(screen.getByText('(30%)')).toBeInTheDocument()
    expect(screen.getByText('(10%)')).toBeInTheDocument()
  })

  it('shows warning when all weights are zero', () => {
    const configZero = {
      calibration_overrides: {
        victory_weights: { force_ratio: 0, morale_ratio: 0, casualty_exchange: 0 },
      },
    }
    render(<VictoryWeightsEditor config={configZero} dispatch={dispatch} />)
    expect(screen.getByText(/All weights are zero/)).toBeInTheDocument()
  })
})
