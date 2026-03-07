import type { EventCountBin } from '../../lib/eventProcessing'
import { PlotlyChart } from './PlotlyChart'

interface EventActivityChartProps {
  data: EventCountBin[]
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
  onClick?: (event: Plotly.PlotMouseEvent) => void
}

export function EventActivityChart({ data, className, layoutOverrides, onClick }: EventActivityChartProps) {
  if (data.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No event data available</div>
  }

  return (
    <PlotlyChart
      data={[
        {
          x: data.map((b) => b.tick),
          y: data.map((b) => b.count),
          type: 'bar' as const,
          marker: { color: '#6366f1' },
          name: 'Events',
        },
      ]}
      layout={{
        title: { text: 'Battle Tempo (Events per Tick Range)' },
        xaxis: { title: { text: 'Tick' } },
        yaxis: { title: { text: 'Event Count' }, rangemode: 'tozero' },
        height: 300,
        ...layoutOverrides,
      }}
      className={className}
      onClick={onClick}
    />
  )
}
