import type { Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'

interface WeatherSectionProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

export function WeatherSection({ config, dispatch }: WeatherSectionProps) {
  const weather = (config.weather_conditions as Record<string, unknown>) ?? {}

  const set = (field: string, value: unknown) =>
    dispatch({ type: 'SET_WEATHER_FIELD', field, value })

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Weather</h3>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Visibility (m)</span>
          <input
            type="number"
            min={50}
            step={100}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(weather.visibility_m as number) ?? 10000}
            onChange={(e) => set('visibility_m', parseFloat(e.target.value) || 10000)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Wind Speed (m/s)</span>
          <input
            type="number"
            min={0}
            step={1}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(weather.wind_speed_mps as number) ?? 5}
            onChange={(e) => set('wind_speed_mps', parseFloat(e.target.value) || 0)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Wind Direction (deg)</span>
          <input
            type="number"
            min={0}
            max={360}
            step={5}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(weather.wind_direction_deg as number) ?? 0}
            onChange={(e) => set('wind_direction_deg', parseFloat(e.target.value) || 0)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Temperature (C)</span>
          <input
            type="number"
            step={1}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(weather.temperature_c as number) ?? 20}
            onChange={(e) => set('temperature_c', parseFloat(e.target.value) || 20)}
          />
        </label>

        <label className="block">
          <span className="text-sm text-gray-700 dark:text-gray-300">Cloud Cover (0-1)</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.1}
            className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            value={(weather.cloud_cover as number) ?? 0.3}
            onChange={(e) => set('cloud_cover', parseFloat(e.target.value) || 0)}
          />
        </label>
      </div>
    </section>
  )
}
