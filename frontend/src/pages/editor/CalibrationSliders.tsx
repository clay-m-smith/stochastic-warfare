import { useState, type Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'

interface CalibrationSlidersProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

// ---------------------------------------------------------------------------
// Toggle definitions — 29 enable_* flags grouped by domain
// ---------------------------------------------------------------------------

interface ToggleDef {
  key: string
  label: string
}

const TOGGLE_GROUPS: Record<string, ToggleDef[]> = {
  Environment: [
    { key: 'enable_seasonal_effects', label: 'Seasonal Effects' },
    { key: 'enable_equipment_stress', label: 'Equipment Stress' },
    { key: 'enable_obstacle_effects', label: 'Obstacle Effects' },
    { key: 'enable_fire_zones', label: 'Fire Zones' },
    { key: 'enable_ice_crossing', label: 'Ice Crossing' },
    { key: 'enable_bridge_capacity', label: 'Bridge Capacity' },
    { key: 'enable_environmental_fatigue', label: 'Environmental Fatigue' },
  ],
  'Detection & Sensors': [
    { key: 'enable_fog_of_war', label: 'Fog of War' },
    { key: 'enable_obscurants', label: 'Obscurants' },
    { key: 'enable_thermal_crossover', label: 'Thermal Crossover' },
    { key: 'enable_nvg_detection', label: 'NVG Detection' },
  ],
  'Naval & Maritime': [
    { key: 'enable_sea_state_ops', label: 'Sea State Ops' },
    { key: 'enable_acoustic_layers', label: 'Acoustic Layers' },
    { key: 'enable_mine_persistence', label: 'Mine Persistence' },
    { key: 'enable_carrier_ops', label: 'Carrier Ops' },
  ],
  'Air & Space': [
    { key: 'enable_air_routing', label: 'Air Routing' },
    { key: 'enable_air_combat_environment', label: 'Air Combat Environment' },
    { key: 'enable_space_effects', label: 'Space Effects' },
    { key: 'enable_em_propagation', label: 'EM Propagation' },
  ],
  'C2 & AI': [
    { key: 'enable_c2_friction', label: 'C2 Friction' },
    { key: 'enable_command_hierarchy', label: 'Command Hierarchy' },
    { key: 'enable_event_feedback', label: 'Event Feedback' },
    { key: 'enable_missile_routing', label: 'Missile Routing' },
  ],
  'CBRN & Human Factors': [
    { key: 'enable_cbrn_environment', label: 'CBRN Environment' },
    { key: 'enable_human_factors', label: 'Human Factors' },
  ],
  'Consequence Enforcement': [
    { key: 'enable_fuel_consumption', label: 'Fuel Consumption' },
    { key: 'enable_ammo_gate', label: 'Ammo Gate' },
    { key: 'enable_unconventional_warfare', label: 'Unconventional Warfare' },
  ],
}

// 21 non-deferred flags set by enable_all_modern
const MODERN_FLAGS = [
  'enable_air_routing', 'enable_fog_of_war', 'enable_seasonal_effects',
  'enable_equipment_stress', 'enable_obstacle_effects', 'enable_obscurants',
  'enable_fire_zones', 'enable_thermal_crossover', 'enable_nvg_detection',
  'enable_sea_state_ops', 'enable_acoustic_layers', 'enable_em_propagation',
  'enable_human_factors', 'enable_cbrn_environment', 'enable_air_combat_environment',
  'enable_event_feedback', 'enable_missile_routing', 'enable_c2_friction',
  'enable_space_effects', 'enable_unconventional_warfare', 'enable_mine_persistence',
]

// ---------------------------------------------------------------------------
// Slider definitions — ~40 numeric parameters grouped by domain
// ---------------------------------------------------------------------------

interface SliderDef {
  key: string
  label: string
  min: number
  max: number
  step: number
  default: number
}

const SLIDER_GROUPS: Record<string, SliderDef[]> = {
  'Combat Modifiers': [
    { key: 'hit_probability_modifier', label: 'Hit Probability', min: 0.1, max: 3.0, step: 0.1, default: 1.0 },
    { key: 'target_size_modifier', label: 'Target Size', min: 0.1, max: 3.0, step: 0.1, default: 1.0 },
    { key: 'thermal_contrast', label: 'Thermal Contrast', min: 0.1, max: 5.0, step: 0.1, default: 1.0 },
    { key: 'destruction_threshold', label: 'Destruction Threshold', min: 0.1, max: 1.0, step: 0.05, default: 0.5 },
    { key: 'disable_threshold', label: 'Disable Threshold', min: 0.1, max: 1.0, step: 0.05, default: 0.3 },
    { key: 'dew_disable_threshold', label: 'DEW Disable Threshold', min: 0.1, max: 1.0, step: 0.05, default: 0.5 },
    { key: 'max_engagers_per_side', label: 'Max Engagers/Side (0=unlimited)', min: 0, max: 50, step: 1, default: 0 },
  ],
  Morale: [
    { key: 'morale_degrade_rate_modifier', label: 'Morale Degrade Rate', min: 0.1, max: 5.0, step: 0.1, default: 1.0 },
    { key: 'morale_base_degrade_rate', label: 'Base Degrade Rate', min: 0.001, max: 0.1, step: 0.001, default: 0.05 },
    { key: 'morale_casualty_weight', label: 'Casualty Weight', min: 0.1, max: 5.0, step: 0.1, default: 2.0 },
    { key: 'morale_force_ratio_weight', label: 'Force Ratio Weight', min: 0.0, max: 2.0, step: 0.1, default: 0.5 },
    { key: 'morale_check_interval', label: 'Check Interval', min: 1, max: 60, step: 1, default: 1 },
  ],
  'Rout Cascade': [
    { key: 'rout_cascade_radius_m', label: 'Cascade Radius (m)', min: 100, max: 5000, step: 100, default: 200 },
    { key: 'rout_cascade_base_chance', label: 'Cascade Base Chance', min: 0.01, max: 0.5, step: 0.01, default: 0.05 },
  ],
  'EW / SEAD': [
    { key: 'jammer_coverage_mult', label: 'Jammer Coverage', min: 0.0, max: 5.0, step: 0.1, default: 1.0 },
    { key: 'stealth_detection_penalty', label: 'Stealth Detection Penalty', min: 0.0, max: 1.0, step: 0.05, default: 0.0 },
    { key: 'sigint_detection_bonus', label: 'SIGINT Detection Bonus', min: 0.0, max: 1.0, step: 0.05, default: 0.0 },
    { key: 'sam_suppression_modifier', label: 'SAM Suppression', min: 0.0, max: 1.0, step: 0.05, default: 0.0 },
  ],
  'Environment': [
    { key: 'visibility_m', label: 'Visibility (m)', min: 100, max: 30000, step: 100, default: 10000 },
    { key: 'formation_spacing_m', label: 'Formation Spacing (m)', min: 5, max: 200, step: 5, default: 50 },
    { key: 'night_thermal_floor', label: 'Night Thermal Floor', min: 0.1, max: 1.0, step: 0.05, default: 0.8 },
    { key: 'wind_accuracy_penalty_scale', label: 'Wind Accuracy Penalty', min: 0.0, max: 0.2, step: 0.01, default: 0.03 },
    { key: 'rain_attenuation_factor', label: 'Rain Attenuation', min: 0.1, max: 5.0, step: 0.1, default: 1.0 },
    { key: 'fire_damage_per_tick', label: 'Fire Damage/Tick', min: 0.001, max: 0.1, step: 0.001, default: 0.01 },
  ],
  'C2 & Friction': [
    { key: 'c2_min_effectiveness', label: 'C2 Min Effectiveness', min: 0.0, max: 1.0, step: 0.05, default: 0.3 },
    { key: 'observation_decay_rate', label: 'Observation Decay Rate', min: 0.0, max: 0.5, step: 0.01, default: 0.05 },
    { key: 'engagement_concealment_threshold', label: 'Concealment Threshold', min: 0.0, max: 1.0, step: 0.05, default: 0.5 },
    { key: 'planning_available_time_s', label: 'Planning Time (s)', min: 600, max: 28800, step: 600, default: 7200 },
    { key: 'order_propagation_delay_sigma', label: 'Order Delay Sigma', min: 0.0, max: 2.0, step: 0.1, default: 0.4 },
    { key: 'order_misinterpretation_base', label: 'Misinterpretation Base', min: 0.0, max: 0.3, step: 0.01, default: 0.05 },
  ],
  Tactical: [
    { key: 'dig_in_ticks', label: 'Dig-In Ticks', min: 1, max: 120, step: 1, default: 30 },
    { key: 'wave_interval_s', label: 'Wave Interval (s)', min: 30, max: 1200, step: 30, default: 300 },
    { key: 'retreat_distance_m', label: 'Retreat Distance (m)', min: 500, max: 10000, step: 500, default: 2000 },
    { key: 'misinterpretation_radius_m', label: 'Misinterpretation Radius (m)', min: 100, max: 2000, step: 100, default: 500 },
    { key: 'stratagem_duration_ticks', label: 'Stratagem Duration (ticks)', min: 10, max: 500, step: 10, default: 100 },
  ],
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const SIDE_CALIBRATION_SLIDERS: SliderDef[] = [
  { key: 'cohesion', label: 'Cohesion', min: 0, max: 1, step: 0.05, default: 0.7 },
  { key: 'force_ratio_modifier', label: 'Force Ratio Modifier', min: 0.1, max: 5.0, step: 0.1, default: 1.0 },
  { key: 'hit_probability_modifier', label: 'Hit Probability Modifier', min: 0.1, max: 3.0, step: 0.1, default: 1.0 },
  { key: 'target_size_modifier', label: 'Target Size Modifier', min: 0.1, max: 3.0, step: 0.1, default: 1.0 },
]

export function CalibrationSliders({ config, dispatch }: CalibrationSlidersProps) {
  const cal = (config.calibration_overrides as Record<string, unknown>) ?? {}
  const [activeSide, setActiveSide] = useState('blue')

  const sides = Array.isArray(config.sides)
    ? (config.sides as Record<string, unknown>[]).map((s) => (s.side as string) ?? '')
    : ['blue', 'red']
  const sideOverrides = (cal.side_overrides as Record<string, Record<string, unknown>>) ?? {}

  const isAllModern = MODERN_FLAGS.every((k) => cal[k] === true)

  const handleEnableAllModern = (checked: boolean) => {
    MODERN_FLAGS.forEach((key) => {
      dispatch({ type: 'SET_CALIBRATION', key, value: checked })
    })
    dispatch({ type: 'SET_CALIBRATION', key: 'enable_all_modern', value: checked })
  }

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Calibration
      </h3>

      {/* Master toggle */}
      <label className="mb-4 flex items-center gap-2 rounded bg-blue-50 p-2 text-sm font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-200">
        <input
          type="checkbox"
          checked={isAllModern}
          onChange={(e) => handleEnableAllModern(e.target.checked)}
          aria-label="Enable All Modern"
        />
        Enable All Modern (21 flags)
      </label>

      {/* Toggle sections */}
      <div className="space-y-2">
        {Object.entries(TOGGLE_GROUPS).map(([group, toggles]) => (
          <details key={group}>
            <summary className="cursor-pointer text-sm font-semibold text-gray-700 dark:text-gray-300">
              {group}
            </summary>
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 pl-2">
              {toggles.map((t) => (
                <label key={t.key} className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                  <input
                    type="checkbox"
                    checked={cal[t.key] === true}
                    onChange={(e) =>
                      dispatch({ type: 'SET_CALIBRATION', key: t.key, value: e.target.checked })
                    }
                    aria-label={t.label}
                  />
                  {t.label}
                </label>
              ))}
            </div>
          </details>
        ))}
      </div>

      {/* Slider sections */}
      <div className="mt-4 space-y-2">
        {Object.entries(SLIDER_GROUPS).map(([group, sliders]) => (
          <details key={group}>
            <summary className="cursor-pointer text-sm font-semibold text-gray-700 dark:text-gray-300">
              {group}
            </summary>
            <div className="mt-2 space-y-2 pl-2">
              {sliders.map((s) => {
                const raw = cal[s.key]
                const value = typeof raw === 'number' ? raw : s.default
                return (
                  <div key={s.key}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-700 dark:text-gray-300">{s.label}</span>
                      <span className="font-mono text-gray-500 dark:text-gray-400">
                        {Number.isInteger(s.step) ? value : value.toFixed(2)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={s.min}
                      max={s.max}
                      step={s.step}
                      value={value}
                      onChange={(e) =>
                        dispatch({ type: 'SET_CALIBRATION', key: s.key, value: parseFloat(e.target.value) })
                      }
                      className="mt-0.5 w-full"
                      aria-label={s.label}
                    />
                  </div>
                )
              })}
            </div>
          </details>
        ))}
      </div>

      {/* Per-Side Overrides */}
      <div className="mt-4">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-gray-700 dark:text-gray-300">
            Per-Side Overrides
          </summary>
          <div className="mt-2 pl-2">
            <div className="mb-2 flex gap-1">
              {sides.map((side) => (
                <button
                  key={side}
                  type="button"
                  className={`rounded px-3 py-1 text-xs font-medium ${
                    activeSide === side
                      ? side === 'blue'
                        ? 'bg-blue-600 text-white'
                        : 'bg-red-600 text-white'
                      : 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                  }`}
                  onClick={() => setActiveSide(side)}
                  aria-label={`${side} side`}
                >
                  {side.charAt(0).toUpperCase() + side.slice(1)}
                </button>
              ))}
            </div>
            <div className="space-y-2">
              {SIDE_CALIBRATION_SLIDERS.map((s) => {
                const sideObj = sideOverrides[activeSide] ?? {}
                const raw = sideObj[s.key]
                const value = typeof raw === 'number' ? raw : s.default
                return (
                  <div key={s.key}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-700 dark:text-gray-300">{s.label}</span>
                      <span className="font-mono text-gray-500 dark:text-gray-400">
                        {Number.isInteger(s.step) ? value : value.toFixed(2)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={s.min}
                      max={s.max}
                      step={s.step}
                      value={value}
                      onChange={(e) =>
                        dispatch({
                          type: 'SET_SIDE_CALIBRATION',
                          side: activeSide,
                          field: s.key,
                          value: parseFloat(e.target.value),
                        })
                      }
                      className="mt-0.5 w-full"
                      aria-label={`${activeSide} ${s.label}`}
                    />
                  </div>
                )
              })}
            </div>
          </div>
        </details>
      </div>
    </section>
  )
}
