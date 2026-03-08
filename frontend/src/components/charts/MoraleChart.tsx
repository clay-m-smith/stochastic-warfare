import { useState } from 'react'
import type { MoraleChange } from '../../lib/eventProcessing'
import { PlotlyChart } from './PlotlyChart'

const MORALE_VALUES: Record<string, number> = {
  steady: 4,
  shaken: 3,
  wavering: 2,
  broken: 1,
  routed: 0,
}

interface MoraleChartProps {
  data: MoraleChange[]
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
  onClick?: (event: Plotly.PlotMouseEvent) => void
}

export function MoraleChart({ data, className, layoutOverrides, onClick }: MoraleChartProps) {
  const unitIds = [...new Set(data.map((d) => d.unit_id))]
  const [selectedUnits, setSelectedUnits] = useState<string[]>(() => unitIds.slice(0, 5))

  if (data.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No morale data available</div>
  }

  const traces: Plotly.Data[] = selectedUnits.map((uid) => {
    const points = data.filter((d) => d.unit_id === uid)
    return {
      x: points.map((p) => p.time_s),
      y: points.map((p) => MORALE_VALUES[p.new_state] ?? 2),
      name: uid,
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      line: { shape: 'hv' as const },
    }
  })

  return (
    <div className={className}>
      {unitIds.length > 5 && (
        <div className="mb-2">
          <label className="text-xs text-gray-500">
            Showing {selectedUnits.length} of {unitIds.length} units.{' '}
            <button
              onClick={() => setSelectedUnits(unitIds)}
              className="text-blue-500 hover:underline"
            >
              Show all
            </button>
          </label>
        </div>
      )}
      <PlotlyChart
        data={traces}
        layout={{
          title: { text: 'Morale State Over Time' },
          xaxis: { title: { text: 'Elapsed Time (s)' } },
          yaxis: {
            title: { text: 'Morale' },
            tickvals: [0, 1, 2, 3, 4],
            ticktext: ['Routed', 'Broken', 'Wavering', 'Shaken', 'Steady'],
            range: [-0.5, 4.5],
          },
          height: 350,
          ...layoutOverrides,
        }}
        onClick={onClick}
      />
    </div>
  )
}
