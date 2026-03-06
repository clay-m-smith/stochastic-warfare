import { describe, it, expect } from 'vitest'
import { editorReducer } from '../../hooks/useScenarioEditor'
import type { EditorState } from '../../types/editor'

function makeState(config: Record<string, unknown> = {}): EditorState {
  return { config, validationErrors: [], isDirty: false }
}

const MINIMAL_CONFIG = {
  name: 'Test',
  date: '2025-01-01',
  duration_hours: 4,
  terrain: { width_m: 5000, height_m: 5000 },
  sides: [
    { side: 'blue', units: [{ unit_type: 'm1a2_abrams', count: 2 }] },
    { side: 'red', units: [{ unit_type: 't72b3', count: 3 }] },
  ],
}

describe('editorReducer', () => {
  it('INIT resets state', () => {
    const state = makeState({ name: 'old' })
    const next = editorReducer(state, { type: 'INIT', config: { name: 'new' } })
    expect(next.config.name).toBe('new')
    expect(next.isDirty).toBe(false)
    expect(next.validationErrors).toEqual([])
  })

  it('SET_FIELD sets top-level field', () => {
    const state = makeState({ name: 'old' })
    const next = editorReducer(state, { type: 'SET_FIELD', path: ['name'], value: 'new' })
    expect(next.config.name).toBe('new')
    expect(next.isDirty).toBe(true)
  })

  it('SET_FIELD sets nested field', () => {
    const state = makeState({ terrain: { width_m: 5000 } })
    const next = editorReducer(state, { type: 'SET_FIELD', path: ['terrain', 'width_m'], value: 10000 })
    expect((next.config.terrain as Record<string, unknown>).width_m).toBe(10000)
  })

  it('SET_TERRAIN_FIELD updates terrain', () => {
    const state = makeState({ terrain: { width_m: 5000 } })
    const next = editorReducer(state, { type: 'SET_TERRAIN_FIELD', field: 'height_m', value: 8000 })
    const terrain = next.config.terrain as Record<string, unknown>
    expect(terrain.height_m).toBe(8000)
    expect(terrain.width_m).toBe(5000)
  })

  it('SET_WEATHER_FIELD updates weather conditions', () => {
    const state = makeState({ weather_conditions: { visibility_m: 10000 } })
    const next = editorReducer(state, { type: 'SET_WEATHER_FIELD', field: 'wind_speed_mps', value: 15 })
    const weather = next.config.weather_conditions as Record<string, unknown>
    expect(weather.wind_speed_mps).toBe(15)
    expect(weather.visibility_m).toBe(10000)
  })

  it('ADD_UNIT appends to side units', () => {
    const state = makeState(structuredClone(MINIMAL_CONFIG))
    const next = editorReducer(state, { type: 'ADD_UNIT', sideIndex: 0, unit_type: 'm2_bradley' })
    const sides = next.config.sides as Record<string, unknown>[]
    const blueUnits = sides[0]!.units as Record<string, unknown>[]
    expect(blueUnits).toHaveLength(2)
    expect(blueUnits[1]!.unit_type).toBe('m2_bradley')
    expect(blueUnits[1]!.count).toBe(1)
  })

  it('REMOVE_UNIT removes from side units', () => {
    const state = makeState(structuredClone(MINIMAL_CONFIG))
    const next = editorReducer(state, { type: 'REMOVE_UNIT', sideIndex: 0, unitIndex: 0 })
    const sides = next.config.sides as Record<string, unknown>[]
    expect((sides[0]!.units as unknown[]).length).toBe(0)
  })

  it('SET_UNIT_COUNT changes count', () => {
    const state = makeState(structuredClone(MINIMAL_CONFIG))
    const next = editorReducer(state, { type: 'SET_UNIT_COUNT', sideIndex: 1, unitIndex: 0, count: 10 })
    const sides = next.config.sides as Record<string, unknown>[]
    const redUnits = sides[1]!.units as Record<string, unknown>[]
    expect(redUnits[0]!.count).toBe(10)
  })

  it('TOGGLE_CONFIG enables a config key', () => {
    const state = makeState({ name: 'test' })
    const next = editorReducer(state, { type: 'TOGGLE_CONFIG', key: 'ew_config', enabled: true })
    expect(next.config.ew_config).toBeDefined()
  })

  it('TOGGLE_CONFIG disables a config key', () => {
    const state = makeState({ ew_config: { enable_ew: true } })
    const next = editorReducer(state, { type: 'TOGGLE_CONFIG', key: 'ew_config', enabled: false })
    expect(next.config.ew_config).toBeUndefined()
  })

  it('SET_CALIBRATION sets calibration override', () => {
    const state = makeState({})
    const next = editorReducer(state, { type: 'SET_CALIBRATION', key: 'hit_probability_modifier', value: 1.5 })
    const cal = next.config.calibration_overrides as Record<string, number>
    expect(cal.hit_probability_modifier).toBe(1.5)
  })

  it('SET_VALIDATION stores errors', () => {
    const state = makeState({})
    const next = editorReducer(state, { type: 'SET_VALIDATION', errors: ['error 1', 'error 2'] })
    expect(next.validationErrors).toEqual(['error 1', 'error 2'])
  })
})
