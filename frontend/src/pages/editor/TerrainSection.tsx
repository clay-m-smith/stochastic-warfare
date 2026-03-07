import type { Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'

const TERRAIN_TYPES = [
  'flat_desert', 'desert', 'grassland', 'forest', 'mixed',
  'urban', 'coastal', 'mountain', 'arctic', 'jungle',
]

interface TerrainSectionProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

export function TerrainSection({ config, dispatch }: TerrainSectionProps) {
  const terrain = (config.terrain as Record<string, unknown>) ?? {}

  const set = (field: string, value: unknown) =>
    dispatch({ type: 'SET_TERRAIN_FIELD', field, value })

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Terrain</h3>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Width (m)</span>
          <input
            type="number"
            min={100}
            step={100}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(terrain.width_m as number) ?? 5000}
            onChange={(e) => set('width_m', parseInt(e.target.value) || 5000)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Height (m)</span>
          <input
            type="number"
            min={100}
            step={100}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(terrain.height_m as number) ?? 5000}
            onChange={(e) => set('height_m', parseInt(e.target.value) || 5000)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Cell Size (m)</span>
          <input
            type="number"
            min={10}
            step={10}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(terrain.cell_size_m as number) ?? 100}
            onChange={(e) => set('cell_size_m', parseInt(e.target.value) || 100)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Base Elevation (m)</span>
          <input
            type="number"
            step={10}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(terrain.base_elevation as number) ?? 0}
            onChange={(e) => set('base_elevation', parseFloat(e.target.value) || 0)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Terrain Type</span>
          <select
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(terrain.terrain_type as string) ?? 'mixed'}
            onChange={(e) => set('terrain_type', e.target.value)}
          >
            {TERRAIN_TYPES.map((t) => (
              <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </label>
      </div>
    </section>
  )
}
