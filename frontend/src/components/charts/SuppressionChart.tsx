import type { SuppressionAnalytics } from '../../types/analytics'
import { PlotlyChart } from './PlotlyChart'

interface SuppressionChartProps {
  data: SuppressionAnalytics
  dt: number
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
  onClick?: (event: Plotly.PlotMouseEvent) => void
}

export function SuppressionChart({ data, dt, className, layoutOverrides, onClick }: SuppressionChartProps) {
  if (data.timeline.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No suppression events recorded</div>
  }

  const xs = data.timeline.map((p) => p.tick * dt)
  const ys = data.timeline.map((p) => p.count)

  const annotations: Partial<Plotly.Annotations>[] = data.peak_suppressed > 0
    ? [
        {
          x: data.peak_tick * dt,
          y: data.peak_suppressed,
          text: `Peak: ${data.peak_suppressed}`,
          showarrow: true,
          arrowhead: 2,
          ax: 30,
          ay: -30,
          font: { size: 11 },
        },
      ]
    : []

  return (
    <div>
      <PlotlyChart
        data={[
          {
            x: xs,
            y: ys,
            type: 'scatter' as const,
            mode: 'lines' as const,
            fill: 'tozeroy' as const,
            line: { color: '#f59e0b' },
            name: 'Suppressed',
            hovertemplate: 'Time: %{x:.0f}s<br>%{y} units suppressed<extra></extra>',
          },
        ]}
        layout={{
          title: { text: 'Suppression Over Time' },
          xaxis: { title: { text: 'Elapsed Time (s)' } },
          yaxis: { title: { text: 'Units Suppressed' }, rangemode: 'tozero' },
          annotations,
          height: 300,
          ...layoutOverrides,
        }}
        className={className}
        onClick={onClick}
      />
      {data.rout_cascades > 0 && (
        <p className="mt-1 text-center text-xs text-gray-500 dark:text-gray-400">
          {data.rout_cascades} rout cascade{data.rout_cascades > 1 ? 's' : ''} recorded
        </p>
      )}
    </div>
  )
}
