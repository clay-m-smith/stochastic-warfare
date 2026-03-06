import type { Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'

interface ConfigTogglesProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

const TOGGLES = [
  { key: 'ew_config', label: 'Electronic Warfare', color: 'bg-purple-100 text-purple-700' },
  { key: 'cbrn_config', label: 'CBRN', color: 'bg-yellow-100 text-yellow-700' },
  { key: 'escalation_config', label: 'Escalation', color: 'bg-red-100 text-red-700' },
  { key: 'school_config', label: 'Doctrinal Schools', color: 'bg-blue-100 text-blue-700' },
  { key: 'space_config', label: 'Space', color: 'bg-indigo-100 text-indigo-700' },
  { key: 'dew_config', label: 'Directed Energy', color: 'bg-orange-100 text-orange-700' },
]

export function ConfigToggles({ config, dispatch }: ConfigTogglesProps) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Optional Systems
      </h3>
      <div className="flex flex-wrap gap-3">
        {TOGGLES.map((t) => {
          const enabled = config[t.key] != null
          return (
            <label key={t.key} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) =>
                  dispatch({ type: 'TOGGLE_CONFIG', key: t.key, enabled: e.target.checked })
                }
                className="rounded border-gray-300"
              />
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${enabled ? t.color : 'bg-gray-100 text-gray-400'}`}>
                {t.label}
              </span>
            </label>
          )
        })}
      </div>
    </section>
  )
}
