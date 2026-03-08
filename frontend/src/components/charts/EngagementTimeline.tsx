import type { EngagementPoint } from '../../lib/eventProcessing'
import { PlotlyChart } from './PlotlyChart'

interface EngagementTimelineProps {
  data: EngagementPoint[]
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
  onClick?: (event: Plotly.PlotMouseEvent) => void
}

export function EngagementTimeline({ data, className, layoutOverrides, onClick }: EngagementTimelineProps) {
  if (data.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No engagement data available</div>
  }

  const hits = data.filter((d) => d.hit)
  const misses = data.filter((d) => !d.hit)
  const hasRange = data.some((d) => d.range != null)

  const makeTrace = (points: EngagementPoint[], name: string, color: string): Plotly.Data => ({
    x: points.map((p) => p.time_s),
    y: hasRange ? points.map((p) => p.range ?? 0) : points.map(() => 1),
    name,
    type: 'scatter' as const,
    mode: 'markers' as const,
    marker: { color, size: 6, opacity: 0.7 },
    text: points.map(
      (p) => `${p.attacker} → ${p.target}${p.weapon ? ` (${p.weapon})` : ''}`,
    ),
    hoverinfo: 'text+x+y' as Plotly.PlotData['hoverinfo'],
  })

  return (
    <PlotlyChart
      data={[
        makeTrace(hits, 'Hit', '#22c55e'),
        makeTrace(misses, 'Miss', '#ef4444'),
      ]}
      layout={{
        title: { text: 'Engagement Timeline' },
        xaxis: { title: { text: 'Elapsed Time (s)' } },
        yaxis: { title: { text: hasRange ? 'Range (m)' : 'Engagement' } },
        height: 350,
        ...layoutOverrides,
      }}
      className={className}
      onClick={onClick}
    />
  )
}
