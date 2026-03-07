import type { Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'

interface CalibrationSlidersProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

const SLIDERS = [
  { key: 'hit_probability_modifier', label: 'Hit Probability', min: 0.1, max: 3.0, step: 0.1, default: 1.0 },
  { key: 'target_size_modifier', label: 'Target Size', min: 0.1, max: 3.0, step: 0.1, default: 1.0 },
  { key: 'morale_degrade_rate_modifier', label: 'Morale Degrade Rate', min: 0.1, max: 5.0, step: 0.1, default: 1.0 },
  { key: 'thermal_contrast', label: 'Thermal Contrast', min: 0.1, max: 5.0, step: 0.1, default: 1.0 },
]

export function CalibrationSliders({ config, dispatch }: CalibrationSlidersProps) {
  const cal = (config.calibration_overrides as Record<string, number>) ?? {}

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Calibration
      </h3>
      <div className="space-y-3">
        {SLIDERS.map((s) => {
          const value = cal[s.key] ?? s.default
          return (
            <div key={s.key}>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-700 dark:text-gray-300">{s.label}</span>
                <span className="font-mono text-gray-500 dark:text-gray-400">{value.toFixed(1)}</span>
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
                className="mt-1 w-full"
              />
            </div>
          )
        })}
      </div>
    </section>
  )
}
