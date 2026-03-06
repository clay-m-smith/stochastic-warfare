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
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">General</h3>
      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span className="text-sm text-gray-700">Name</span>
          <input
            type="text"
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm"
            value={(config.name as string) ?? ''}
            onChange={(e) => set(['name'], e.target.value)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700">Duration (hours)</span>
          <input
            type="number"
            min={0.1}
            step={0.5}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm"
            value={(config.duration_hours as number) ?? 4}
            onChange={(e) => set(['duration_hours'], parseFloat(e.target.value) || 1)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700">Era</span>
          <select
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm"
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
        </label>

        <label className="block">
          <span className="text-sm text-gray-700">Date</span>
          <input
            type="text"
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm"
            value={(config.date as string) ?? ''}
            onChange={(e) => set(['date'], e.target.value)}
          />
        </label>
      </div>
    </section>
  )
}
