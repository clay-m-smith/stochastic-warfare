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
// Reducer-level tests for SET_SIDE_CALIBRATION
// ---------------------------------------------------------------------------

describe('editorReducer SET_SIDE_CALIBRATION', () => {
  const initial: EditorState = {
    config: { calibration_overrides: {} },
    validationErrors: [],
    isDirty: false,
  }

  it('creates nested side_overrides structure', () => {
    const next = editorReducer(initial, {
      type: 'SET_SIDE_CALIBRATION',
      side: 'blue',
      field: 'cohesion',
      value: 0.85,
    })
    const cal = next.config.calibration_overrides as Record<string, unknown>
    const so = cal.side_overrides as Record<string, Record<string, unknown>>
    expect(so.blue!.cohesion).toBe(0.85)
    expect(next.isDirty).toBe(true)
  })

  it('preserves existing side data when setting another side', () => {
    const withBlue = editorReducer(initial, {
      type: 'SET_SIDE_CALIBRATION',
      side: 'blue',
      field: 'cohesion',
      value: 0.9,
    })
    const withRed = editorReducer(withBlue, {
      type: 'SET_SIDE_CALIBRATION',
      side: 'red',
      field: 'force_ratio_modifier',
      value: 2.0,
    })
    const cal = withRed.config.calibration_overrides as Record<string, unknown>
    const so = cal.side_overrides as Record<string, Record<string, unknown>>
    expect(so.blue!.cohesion).toBe(0.9)
    expect(so.red!.force_ratio_modifier).toBe(2.0)
  })

  it('overwrites existing field value immutably', () => {
    const first = editorReducer(initial, {
      type: 'SET_SIDE_CALIBRATION',
      side: 'blue',
      field: 'cohesion',
      value: 0.5,
    })
    const second = editorReducer(first, {
      type: 'SET_SIDE_CALIBRATION',
      side: 'blue',
      field: 'cohesion',
      value: 0.9,
    })
    const cal = second.config.calibration_overrides as Record<string, unknown>
    const so = cal.side_overrides as Record<string, Record<string, unknown>>
    expect(so.blue!.cohesion).toBe(0.9)
    // Immutability: first state should be unchanged
    const firstCal = first.config.calibration_overrides as Record<string, unknown>
    const firstSo = firstCal.side_overrides as Record<string, Record<string, unknown>>
    expect(firstSo.blue!.cohesion).toBe(0.5)
  })
})

// ---------------------------------------------------------------------------
// Reducer-level tests for SET_VICTORY_WEIGHT
// ---------------------------------------------------------------------------

describe('editorReducer SET_VICTORY_WEIGHT', () => {
  const initial: EditorState = {
    config: { calibration_overrides: {} },
    validationErrors: [],
    isDirty: false,
  }

  it('creates nested victory_weights structure', () => {
    const next = editorReducer(initial, {
      type: 'SET_VICTORY_WEIGHT',
      key: 'force_ratio',
      value: 0.6,
    })
    const cal = next.config.calibration_overrides as Record<string, unknown>
    const vw = cal.victory_weights as Record<string, number>
    expect(vw.force_ratio).toBe(0.6)
    expect(next.isDirty).toBe(true)
  })

  it('preserves other victory weight keys', () => {
    const first = editorReducer(initial, {
      type: 'SET_VICTORY_WEIGHT',
      key: 'force_ratio',
      value: 0.5,
    })
    const second = editorReducer(first, {
      type: 'SET_VICTORY_WEIGHT',
      key: 'morale_ratio',
      value: 0.3,
    })
    const cal = second.config.calibration_overrides as Record<string, unknown>
    const vw = cal.victory_weights as Record<string, number>
    expect(vw.force_ratio).toBe(0.5)
    expect(vw.morale_ratio).toBe(0.3)
  })
})

// ---------------------------------------------------------------------------
// Reducer-level tests for SET_SCHOOL
// ---------------------------------------------------------------------------

describe('editorReducer SET_SCHOOL', () => {
  it('sets school and auto-enables school_config', () => {
    const initial: EditorState = {
      config: {},
      validationErrors: [],
      isDirty: false,
    }
    const next = editorReducer(initial, {
      type: 'SET_SCHOOL',
      side: 'blue',
      school_id: 'maneuverist',
    })
    const sc = next.config.school_config as Record<string, unknown>
    expect(sc.blue_school).toBe('maneuverist')
    expect(next.isDirty).toBe(true)
  })

  it('clears school_id when empty string', () => {
    const withSchool: EditorState = {
      config: { school_config: { enable_schools: true, blue_school: 'maneuverist' } },
      validationErrors: [],
      isDirty: false,
    }
    const next = editorReducer(withSchool, {
      type: 'SET_SCHOOL',
      side: 'blue',
      school_id: '',
    })
    const sc = next.config.school_config as Record<string, unknown>
    expect(sc.blue_school).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Reducer-level tests for SET_COMMANDER
// ---------------------------------------------------------------------------

describe('editorReducer SET_COMMANDER', () => {
  it('sets commander and auto-enables commander_config', () => {
    const initial: EditorState = {
      config: {},
      validationErrors: [],
      isDirty: false,
    }
    const next = editorReducer(initial, {
      type: 'SET_COMMANDER',
      side: 'red',
      profile_id: 'conventional_commander',
    })
    const cc = next.config.commander_config as Record<string, unknown>
    const sd = cc.side_defaults as Record<string, unknown>
    expect(sd.red).toBe('conventional_commander')
    expect(next.isDirty).toBe(true)
  })

  it('clears profile_id when empty string', () => {
    const withCmd: EditorState = {
      config: { commander_config: { side_defaults: { blue: 'joint_commander' } } },
      validationErrors: [],
      isDirty: false,
    }
    const next = editorReducer(withCmd, {
      type: 'SET_COMMANDER',
      side: 'blue',
      profile_id: '',
    })
    const cc = next.config.commander_config as Record<string, unknown>
    const sd = cc.side_defaults as Record<string, unknown>
    expect(sd.blue).toBeUndefined()
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

  it('renders slider groups including new sections', () => {
    render(<CalibrationSliders config={config} dispatch={dispatch} />)
    const groups = ['Combat Modifiers', 'Morale', 'EW / SEAD', 'C2 & Friction', 'Tactical', 'Rout Cascade', 'Per-Side Overrides']
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

  it('per-side section shows Blue tab active by default', () => {
    render(<CalibrationSliders config={{ sides: [{ side: 'blue' }, { side: 'red' }], calibration_overrides: {} }} dispatch={dispatch} />)
    const blueBtn = screen.getByLabelText('blue side')
    expect(blueBtn).toHaveClass('bg-blue-600')
  })

  it('per-side slider dispatches SET_SIDE_CALIBRATION', () => {
    dispatch.mockClear()
    render(<CalibrationSliders config={{ sides: [{ side: 'blue' }, { side: 'red' }], calibration_overrides: {} }} dispatch={dispatch} />)
    const perSideSummary = screen.getByText('Per-Side Overrides')
    fireEvent.click(perSideSummary)
    const slider = screen.getByLabelText('blue Cohesion')
    fireEvent.change(slider, { target: { value: '0.85' } })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'SET_SIDE_CALIBRATION',
      side: 'blue',
      field: 'cohesion',
      value: 0.85,
    })
  })

  it('switching to red tab changes side label on sliders', () => {
    render(<CalibrationSliders config={{ sides: [{ side: 'blue' }, { side: 'red' }], calibration_overrides: {} }} dispatch={dispatch} />)
    const perSideSummary = screen.getByText('Per-Side Overrides')
    fireEvent.click(perSideSummary)
    const redBtn = screen.getByLabelText('red side')
    fireEvent.click(redBtn)
    expect(screen.getByLabelText('red Cohesion')).toBeInTheDocument()
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
