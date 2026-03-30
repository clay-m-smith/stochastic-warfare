import type { Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'
import { useSchools } from '../../hooks/useMeta'

interface DoctrinePickerProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

export function DoctrinePicker({ config, dispatch }: DoctrinePickerProps) {
  const { data: schools } = useSchools()

  const sides = Array.isArray(config.sides)
    ? (config.sides as Record<string, unknown>[]).map((s) => (s.side as string) ?? '')
    : ['blue', 'red']

  const sc = (config.school_config as Record<string, unknown>) ?? {}

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Doctrinal Schools
      </h3>
      <div className="space-y-3">
        {sides.map((side) => {
          const selectedId = (sc[`${side}_school`] as string) ?? ''
          const selected = schools?.find((s) => s.school_id === selectedId)
          return (
            <div key={side}>
              <label
                htmlFor={`school-${side}`}
                className="block text-xs font-medium text-gray-700 dark:text-gray-300"
              >
                {side.charAt(0).toUpperCase() + side.slice(1)} School
              </label>
              <select
                id={`school-${side}`}
                className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                value={selectedId}
                onChange={(e) => dispatch({ type: 'SET_SCHOOL', side, school_id: e.target.value })}
              >
                <option value="">None</option>
                {schools?.map((s) => (
                  <option key={s.school_id} value={s.school_id}>
                    {s.display_name || s.school_id}
                  </option>
                ))}
              </select>
              {selected && (
                <div className="mt-1 space-y-0.5">
                  <p className="text-xs text-gray-500 dark:text-gray-400">{selected.description}</p>
                  <div className="flex gap-2">
                    <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
                      OODA {selected.ooda_multiplier.toFixed(1)}x
                    </span>
                    {selected.risk_tolerance && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                        Risk: {selected.risk_tolerance}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
