import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CalibrationSliders } from '../../pages/editor/CalibrationSliders'
import { editorReducer } from '../../hooks/useScenarioEditor'
import type { EditorState } from '../../types/editor'

// ---------------------------------------------------------------------------
// Reducer-level tests for SET_CALIBRATION with boolean values
// ---------------------------------------------------------------------------

describe('editorReducer SET_CALIBRATION', () => {
  const initial: EditorState = {
    config: { calibration_overrides: {} },
    validationErrors: [],
    isDirty: false,
  }

  it('handles boolean toggle values', () => {
    const next = editorReducer(initial, {
      type: 'SET_CALIBRATION',
      key: 'enable_fog_of_war',
      value: true,
    })
    const cal = next.config.calibration_overrides as Record<string, unknown>
    expect(cal.enable_fog_of_war).toBe(true)
    expect(next.isDirty).toBe(true)
  })

  it('handles numeric slider values', () => {
    const next = editorReducer(initial, {
      type: 'SET_CALIBRATION',
      key: 'hit_probability_modifier',
      value: 2.5,
    })
    const cal = next.config.calibration_overrides as Record<string, unknown>
    expect(cal.hit_probability_modifier).toBe(2.5)
  })
})

// ---------------------------------------------------------------------------
// Component render tests
// ---------------------------------------------------------------------------

describe('CalibrationSliders component', () => {
  const dispatch = vi.fn()
  const config = { calibration_overrides: {} }

  it('renders the master Enable All Modern toggle', () => {
    render(<CalibrationSliders config={config} dispatch={dispatch} />)
    expect(screen.getByLabelText('Enable All Modern')).toBeInTheDocument()
  })

  it('renders all 7 toggle group headers', () => {
    render(<CalibrationSliders config={config} dispatch={dispatch} />)
    const groups = [
      'Detection & Sensors', 'Naval & Maritime',
      'Air & Space', 'C2 & AI', 'CBRN & Human Factors', 'Consequence Enforcement',
    ]
    for (const g of groups) {
      expect(screen.getByText(g)).toBeInTheDocument()
    }
    // "Environment" appears in both toggle and slider sections
    expect(screen.getAllByText('Environment')).toHaveLength(2)
  })

  it('enable_all_modern toggle dispatches 22 actions (21 flags + meta)', () => {
    dispatch.mockClear()
    render(<CalibrationSliders config={config} dispatch={dispatch} />)
    const checkbox = screen.getByLabelText('Enable All Modern')
    fireEvent.click(checkbox)
    // 21 MODERN_FLAGS + 1 enable_all_modern = 22 dispatches
    expect(dispatch).toHaveBeenCalledTimes(22)
    // Last call should be enable_all_modern
    expect(dispatch).toHaveBeenLastCalledWith({
      type: 'SET_CALIBRATION',
      key: 'enable_all_modern',
      value: true,
    })
  })

  it('renders slider groups', () => {
    render(<CalibrationSliders config={config} dispatch={dispatch} />)
    const groups = ['Combat Modifiers', 'Morale', 'EW / SEAD', 'C2 & Friction', 'Tactical']
    for (const g of groups) {
      expect(screen.getByText(g)).toBeInTheDocument()
    }
  })

  it('slider dispatches numeric value on change', () => {
    dispatch.mockClear()
    render(<CalibrationSliders config={config} dispatch={dispatch} />)
    // Open Combat Modifiers details
    const combatSummary = screen.getByText('Combat Modifiers')
    fireEvent.click(combatSummary)
    const slider = screen.getByLabelText('Hit Probability')
    fireEvent.change(slider, { target: { value: '2.0' } })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'SET_CALIBRATION',
      key: 'hit_probability_modifier',
      value: 2.0,
    })
  })

  it('reflects existing calibration values in toggles', () => {
    const configWithCal = {
      calibration_overrides: { enable_fog_of_war: true },
    }
    render(<CalibrationSliders config={configWithCal} dispatch={dispatch} />)
    const checkbox = screen.getByLabelText('Fog of War')
    expect(checkbox).toBeChecked()
  })
})
