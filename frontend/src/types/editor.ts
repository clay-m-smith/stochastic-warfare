// Types for the scenario editor (Phase 36)

export interface RunFromConfigRequest {
  config: Record<string, unknown>
  seed?: number
  max_ticks?: number
}

export interface ValidateConfigResponse {
  valid: boolean
  errors: string[]
}

export interface EditorUnitEntry {
  unit_type: string
  count: number
}

export interface EditorSideConfig {
  side: string
  units: EditorUnitEntry[]
  experience_level?: number
  morale_initial?: string
}

export interface EditorState {
  config: Record<string, unknown>
  validationErrors: string[]
  isDirty: boolean
}

export type EditorAction =
  | { type: 'INIT'; config: Record<string, unknown> }
  | { type: 'SET_FIELD'; path: string[]; value: unknown }
  | { type: 'SET_TERRAIN_FIELD'; field: string; value: unknown }
  | { type: 'SET_WEATHER_FIELD'; field: string; value: unknown }
  | { type: 'UPDATE_SIDE'; sideIndex: number; side: EditorSideConfig }
  | { type: 'ADD_UNIT'; sideIndex: number; unit_type: string }
  | { type: 'REMOVE_UNIT'; sideIndex: number; unitIndex: number }
  | { type: 'SET_UNIT_COUNT'; sideIndex: number; unitIndex: number; count: number }
  | { type: 'TOGGLE_CONFIG'; key: string; enabled: boolean }
  | { type: 'SET_CALIBRATION'; key: string; value: number | boolean }
  | { type: 'SET_VALIDATION'; errors: string[] }
