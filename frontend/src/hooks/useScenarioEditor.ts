import { useReducer } from 'react'
import {
  CONFIG_DEFAULTS,
  configCreationLimitation,
} from '../lib/editorConfigCapabilities'
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
        const defaultConfig = CONFIG_DEFAULTS[action.key]
        if (!defaultConfig) {
          const limitation =
            configCreationLimitation(action.key) ??
            `Adding ${action.key} is unsupported because no production default is declared.`
          return { ...state, validationErrors: [limitation] }
        }
        next[action.key] = { ...defaultConfig }
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

    case 'SET_SIDE_CALIBRATION': {
      const cal = (state.config.calibration_overrides as Record<string, unknown>) ?? {}
      const so = (cal.side_overrides as Record<string, Record<string, unknown>>) ?? {}
      const sideObj = so[action.side] ?? {}
      return {
        ...state,
        config: {
          ...state.config,
          calibration_overrides: {
            ...cal,
            side_overrides: { ...so, [action.side]: { ...sideObj, [action.field]: action.value } },
          },
        },
        isDirty: true,
      }
    }

    case 'SET_VICTORY_WEIGHT': {
      const cal = (state.config.calibration_overrides as Record<string, unknown>) ?? {}
      const vw = (cal.victory_weights as Record<string, number>) ?? {}
      return {
        ...state,
        config: {
          ...state.config,
          calibration_overrides: {
            ...cal,
            victory_weights: { ...vw, [action.key]: action.value },
          },
        },
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
