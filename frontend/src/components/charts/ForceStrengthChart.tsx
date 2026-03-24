import type { ForceTimePoint } from '../../lib/eventProcessing'
import { formatElapsed } from '../../lib/eventProcessing'
import { getSideColor } from '../../lib/sideColors'
import { PlotlyChart } from './PlotlyChart'

interface ForceStrengthChartProps {
  data: ForceTimePoint[]
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
  onClick?: (event: Plotly.PlotMouseEvent) => void
}

export function ForceStrengthChart({ data, className, layoutOverrides, onClick }: ForceStrengthChartProps) {
  if (data.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No force data available</div>
  }

  const sides = Object.keys(data[0]!).filter((k) => k !== 'tick' && k !== 'time_s')
  const traces: Plotly.Data[] = sides.map((side) => ({
    x: data.map((p) => p.time_s),
    y: data.map((p) => (p[side] as number | undefined) ?? 0),
    name: side,
    type: 'scatter' as const,
    mode: 'lines' as const,
    fill: 'tozeroy' as const,
    line: { color: getSideColor(side) },
    text: data.map((p) => formatElapsed(p.time_s)),
    hovertemplate: '%{text}<br>%{y} units<extra>%{fullData.name}</extra>',
  }))

  const sampleStep = Math.max(1, Math.floor(data.length / 10))
  const sampledData = data.filter((_, i) => i % sampleStep === 0 || i === data.length - 1)

  const dataSummary = (
    <table className="min-w-full text-xs">
      <thead>
        <tr>
          <th scope="col" className="px-2 py-1 text-left">Time (s)</th>
          {sides.map(s => <th key={s} scope="col" className="px-2 py-1 text-right">{s}</th>)}
        </tr>
      </thead>
      <tbody>
        {sampledData.map((p, i) => (
          <tr key={i}>
            <td className="px-2 py-1">{p.time_s.toFixed(0)}</td>
            {sides.map(s => <td key={s} className="px-2 py-1 text-right">{((p[s] as number) ?? 0)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )

  return (
    <PlotlyChart
      data={traces}
      layout={{
        title: { text: 'Force Strength Over Time' },
        xaxis: { title: { text: 'Elapsed Time (s)' } },
        yaxis: { title: { text: 'Active Units' }, rangemode: 'tozero' },
        height: 350,
        ...layoutOverrides,
      }}
      className={className}
      onClick={onClick}
      dataSummary={dataSummary}
    />
  )
}
