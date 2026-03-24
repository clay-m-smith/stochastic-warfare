import type { Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'
import { useEras } from '../../hooks/useMeta'

interface GeneralSectionProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

export function GeneralSection({ config, dispatch }: GeneralSectionProps) {
  const { data: eras } = useEras()

  const set = (path: string[], value: unknown) =>
    dispatch({ type: 'SET_FIELD', path, value })

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">General</h3>
      <div className="grid grid-cols-2 gap-4">
        <div className="block">
          <label htmlFor="general-name" className="text-sm text-gray-700 dark:text-gray-300">Name</label>
          <input
            id="general-name"
            type="text"
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(config.name as string) ?? ''}
            onChange={(e) => set(['name'], e.target.value)}
          />
        </div>

        <div className="block">
          <label htmlFor="general-duration" className="text-sm text-gray-700 dark:text-gray-300">Duration (hours)</label>
          <input
            id="general-duration"
            type="number"
            min={0.1}
            step={0.5}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(config.duration_hours as number) ?? 4}
            onChange={(e) => set(['duration_hours'], parseFloat(e.target.value) || 1)}
          />
        </div>

        <div className="block">
          <label htmlFor="general-era" className="text-sm text-gray-700 dark:text-gray-300">Era</label>
          <select
            id="general-era"
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(config.era as string) ?? 'modern'}
            onChange={(e) => set(['era'], e.target.value)}
          >
            {eras
              ? eras.map((era) => (
                  <option key={era.value} value={era.value}>
                    {era.name}
                  </option>
                ))
              : <option value="modern">Modern</option>}
          </select>
        </div>

        <div className="block">
          <label htmlFor="general-date" className="text-sm text-gray-700 dark:text-gray-300">Date</label>
          <input
            id="general-date"
            type="text"
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(config.date as string) ?? ''}
            onChange={(e) => set(['date'], e.target.value)}
          />
        </div>
      </div>
    </section>
  )
}
