import type { Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'
import { useCommanders } from '../../hooks/useMeta'

interface CommanderPickerProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

export function CommanderPicker({ config, dispatch }: CommanderPickerProps) {
  const { data: commanders } = useCommanders()

  const sides = Array.isArray(config.sides)
    ? (config.sides as Record<string, unknown>[]).map((s) => (s.side as string) ?? '')
    : ['blue', 'red']

  const cc = (config.commander_config as Record<string, unknown>) ?? {}
  const sideDefaults = (cc.side_defaults as Record<string, string>) ?? {}

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Commander Profiles
      </h3>
      <div className="space-y-3">
        {sides.map((side) => {
          const selectedId = sideDefaults[side] ?? ''
          const selected = commanders?.find((c) => c.profile_id === selectedId)
          return (
            <div key={side}>
              <label
                htmlFor={`commander-${side}`}
                className="block text-xs font-medium text-gray-700 dark:text-gray-300"
              >
                {side.charAt(0).toUpperCase() + side.slice(1)} Commander
              </label>
              <select
                id={`commander-${side}`}
                className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                value={selectedId}
                onChange={(e) =>
                  dispatch({ type: 'SET_COMMANDER', side, profile_id: e.target.value })
                }
              >
                <option value="">None</option>
                {commanders?.map((c) => (
                  <option key={c.profile_id} value={c.profile_id}>
                    {c.display_name || c.profile_id}
                  </option>
                ))}
              </select>
              {selected && (
                <div className="mt-1">
                  {selected.description && (
                    <p className="mb-1 text-xs text-gray-500 dark:text-gray-400">
                      {selected.description}
                    </p>
                  )}
                  {Object.keys(selected.traits).length > 0 && (
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 rounded border border-gray-200 p-1.5 text-xs dark:border-gray-700">
                      {Object.entries(selected.traits).map(([trait, value]) => (
                        <div key={trait} className="flex justify-between">
                          <span className="text-gray-600 dark:text-gray-400">
                            {trait.replace(/_/g, ' ')}
                          </span>
                          <span className="font-mono text-gray-800 dark:text-gray-200">
                            {value.toFixed(1)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
