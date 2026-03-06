import { useReducer } from 'react'
import type { EditorAction, EditorState } from '../types/editor'

function setNested(obj: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> {
  if (path.length === 0) return obj
  const key = path[0]!
  if (path.length === 1) {
    return { ...obj, [key]: value }
  }
  const rest = path.slice(1)
  const child = (obj[key] as Record<string, unknown>) ?? {}
  return { ...obj, [key]: setNested({ ...child }, rest, value) }
}

function getSides(config: Record<string, unknown>): Record<string, unknown>[] {
  const sides = config.sides
  if (Array.isArray(sides)) return sides as Record<string, unknown>[]
  return []
}

function setSides(config: Record<string, unknown>, sides: Record<string, unknown>[]): Record<string, unknown> {
  return { ...config, sides }
}

const CONFIG_DEFAULTS: Record<string, Record<string, unknown>> = {
  ew_config: { enable_ew: true },
  cbrn_config: { enable_cbrn: true },
  escalation_config: { enable_escalation: true },
  school_config: { enable_schools: true },
  space_config: { enable_space: true },
  dew_config: { enable_dew: true },
}

function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case 'INIT':
      return { config: structuredClone(action.config), validationErrors: [], isDirty: false }

    case 'SET_FIELD':
      return { ...state, config: setNested(state.config, action.path, action.value), isDirty: true }

    case 'SET_TERRAIN_FIELD': {
      const terrain = (state.config.terrain as Record<string, unknown>) ?? {}
      return {
        ...state,
        config: { ...state.config, terrain: { ...terrain, [action.field]: action.value } },
        isDirty: true,
      }
    }

    case 'SET_WEATHER_FIELD': {
      const weather = (state.config.weather_conditions as Record<string, unknown>) ?? {}
      return {
        ...state,
        config: { ...state.config, weather_conditions: { ...weather, [action.field]: action.value } },
        isDirty: true,
      }
    }

    case 'UPDATE_SIDE': {
      const sides = [...getSides(state.config)]
      sides[action.sideIndex] = action.side as unknown as Record<string, unknown>
      return { ...state, config: setSides(state.config, sides), isDirty: true }
    }

    case 'ADD_UNIT': {
      const sides = getSides(state.config).map((s) => ({ ...s }))
      const side = sides[action.sideIndex]
      if (side) {
        const units = [...((side.units as Record<string, unknown>[]) ?? [])]
        units.push({ unit_type: action.unit_type, count: 1 })
        sides[action.sideIndex] = { ...side, units }
      }
      return { ...state, config: setSides(state.config, sides), isDirty: true }
    }

    case 'REMOVE_UNIT': {
      const sides = getSides(state.config).map((s) => ({ ...s }))
      const side = sides[action.sideIndex]
      if (side) {
        const units = [...((side.units as Record<string, unknown>[]) ?? [])]
        units.splice(action.unitIndex, 1)
        sides[action.sideIndex] = { ...side, units }
      }
      return { ...state, config: setSides(state.config, sides), isDirty: true }
    }

    case 'SET_UNIT_COUNT': {
      const sides = getSides(state.config).map((s) => ({ ...s }))
      const side = sides[action.sideIndex]
      if (side) {
        const units = ((side.units as Record<string, unknown>[]) ?? []).map((u) => ({ ...u }))
        if (units[action.unitIndex]) {
          units[action.unitIndex] = { ...units[action.unitIndex], count: action.count }
        }
        sides[action.sideIndex] = { ...side, units }
      }
      return { ...state, config: setSides(state.config, sides), isDirty: true }
    }

    case 'TOGGLE_CONFIG': {
      const next = { ...state.config }
      if (action.enabled) {
        next[action.key] = CONFIG_DEFAULTS[action.key] ?? {}
      } else {
        delete next[action.key]
      }
      return { ...state, config: next, isDirty: true }
    }

    case 'SET_CALIBRATION': {
      const cal = (state.config.calibration_overrides as Record<string, unknown>) ?? {}
      return {
        ...state,
        config: { ...state.config, calibration_overrides: { ...cal, [action.key]: action.value } },
        isDirty: true,
      }
    }

    case 'SET_VALIDATION':
      return { ...state, validationErrors: action.errors }

    default:
      return state
  }
}

export function useScenarioEditor(initialConfig: Record<string, unknown>) {
  const [state, dispatch] = useReducer(editorReducer, {
    config: structuredClone(initialConfig),
    validationErrors: [],
    isDirty: false,
  })

  return { state, dispatch, config: state.config }
}

// Export for testing
export { editorReducer }
