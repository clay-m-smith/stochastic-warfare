import { useState, type Dispatch } from 'react'
import type { EditorAction } from '../../types/editor'
import { UnitPicker } from './UnitPicker'

interface ForceEditorProps {
  config: Record<string, unknown>
  dispatch: Dispatch<EditorAction>
}

export function ForceEditor({ config, dispatch }: ForceEditorProps) {
  const sides = (config.sides as Record<string, unknown>[]) ?? []
  const [pickerSide, setPickerSide] = useState<number | null>(null)
  const era = (config.era as string) ?? 'modern'

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Forces</h3>
      <div className="space-y-4">
        {sides.map((side, sideIndex) => {
          const sideName = (side.side as string) ?? `Side ${sideIndex + 1}`
          const units = (side.units as Record<string, unknown>[]) ?? []

          return (
            <div key={sideIndex} className="rounded-lg border border-gray-200 p-4">
              <h4 className="mb-2 font-medium text-gray-800">{sideName}</h4>

              {units.length === 0 && (
                <p className="text-sm text-gray-400">No units</p>
              )}

              <div className="space-y-2">
                {units.map((unit, unitIndex) => (
                  <div key={unitIndex} className="flex items-center gap-3">
                    <span className="min-w-0 flex-1 truncate text-sm text-gray-700">
                      {String(unit.unit_type ?? '?')}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        className="rounded bg-gray-100 px-2 py-0.5 text-xs hover:bg-gray-200"
                        onClick={() =>
                          dispatch({
                            type: 'SET_UNIT_COUNT',
                            sideIndex,
                            unitIndex,
                            count: Math.max(1, ((unit.count as number) ?? 1) - 1),
                          })
                        }
                      >
                        -
                      </button>
                      <input
                        type="number"
                        min={1}
                        className="w-14 rounded border-gray-300 text-center text-sm"
                        value={(unit.count as number) ?? 1}
                        onChange={(e) =>
                          dispatch({
                            type: 'SET_UNIT_COUNT',
                            sideIndex,
                            unitIndex,
                            count: Math.max(1, parseInt(e.target.value) || 1),
                          })
                        }
                      />
                      <button
                        className="rounded bg-gray-100 px-2 py-0.5 text-xs hover:bg-gray-200"
                        onClick={() =>
                          dispatch({
                            type: 'SET_UNIT_COUNT',
                            sideIndex,
                            unitIndex,
                            count: ((unit.count as number) ?? 1) + 1,
                          })
                        }
                      >
                        +
                      </button>
                    </div>
                    <button
                      className="text-sm text-red-500 hover:text-red-700"
                      onClick={() => dispatch({ type: 'REMOVE_UNIT', sideIndex, unitIndex })}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>

              <button
                className="mt-3 text-sm font-medium text-blue-600 hover:text-blue-800"
                onClick={() => setPickerSide(sideIndex)}
              >
                + Add Unit
              </button>
            </div>
          )
        })}
      </div>

      {pickerSide !== null && (
        <UnitPicker
          era={era}
          onSelect={(unitType) => {
            dispatch({ type: 'ADD_UNIT', sideIndex: pickerSide, unit_type: unitType })
            setPickerSide(null)
          }}
          onClose={() => setPickerSide(null)}
        />
      )}
    </section>
  )
}
