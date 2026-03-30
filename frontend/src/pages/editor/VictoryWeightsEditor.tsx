import type { Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'

interface VictoryWeightsEditorProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

interface WeightDef {
  key: string
  label: string
  default: number
}

const WEIGHT_DEFS: WeightDef[] = [
  { key: 'force_ratio', label: 'Force Ratio', default: 1.0 },
  { key: 'morale_ratio', label: 'Morale Ratio', default: 0.0 },
  { key: 'casualty_exchange', label: 'Casualty Exchange', default: 0.0 },
]

export function VictoryWeightsEditor({ config, dispatch }: VictoryWeightsEditorProps) {
  const cal = (config.calibration_overrides as Record<string, unknown>) ?? {}
  const vw = (cal.victory_weights as Record<string, number>) ?? {}

  const values = WEIGHT_DEFS.map((w) => {
    const raw = vw[w.key]
    return { ...w, value: typeof raw === 'number' ? raw : w.default }
  })

  const total = values.reduce((sum, v) => sum + v.value, 0)

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Victory Weights
      </h3>
      <div className="space-y-2">
        {values.map((w) => {
          const pct = total > 0 ? Math.round((w.value / total) * 100) : 0
          return (
            <div key={w.key}>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-700 dark:text-gray-300">{w.label}</span>
                <span className="font-mono text-gray-500 dark:text-gray-400">
                  {w.value.toFixed(2)}{' '}
                  <span className="text-gray-400 dark:text-gray-500">({pct}%)</span>
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={w.value}
                onChange={(e) =>
                  dispatch({ type: 'SET_VICTORY_WEIGHT', key: w.key, value: parseFloat(e.target.value) })
                }
                className="mt-0.5 w-full"
                aria-label={w.label}
              />
            </div>
          )
        })}
      </div>
      {total === 0 && (
        <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
          All weights are zero — victory evaluation will use defaults.
        </p>
      )}
    </section>
  )
}
