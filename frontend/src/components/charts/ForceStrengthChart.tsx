import type { ForceTimePoint } from '../../lib/eventProcessing'
import { PlotlyChart } from './PlotlyChart'

const SIDE_COLORS: Record<string, string> = {
  blue: '#3b82f6',
  red: '#ef4444',
  green: '#22c55e',
  neutral: '#6b7280',
}

interface ForceStrengthChartProps {
  data: ForceTimePoint[]
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
}

export function ForceStrengthChart({ data, className, layoutOverrides }: ForceStrengthChartProps) {
  if (data.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No force data available</div>
  }

  const sides = Object.keys(data[0]!).filter((k) => k !== 'tick')
  const traces: Plotly.Data[] = sides.map((side) => ({
    x: data.map((p) => p.tick),
    y: data.map((p) => (p[side] as number | undefined) ?? 0),
    name: side,
    type: 'scatter' as const,
    mode: 'lines' as const,
    fill: 'tozeroy' as const,
    line: { color: SIDE_COLORS[side] ?? '#6b7280' },
  }))

  return (
    <PlotlyChart
      data={traces}
      layout={{
        title: { text: 'Force Strength Over Time' },
        xaxis: { title: { text: 'Tick' } },
        yaxis: { title: { text: 'Active Units' }, rangemode: 'tozero' },
        height: 350,
        ...layoutOverrides,
      }}
      className={className}
    />
  )
}
