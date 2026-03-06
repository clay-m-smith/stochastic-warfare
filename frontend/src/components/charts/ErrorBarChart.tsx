import { PlotlyChart } from './PlotlyChart'

interface ErrorBarPoint {
  x: number | string
  mean: number
  std: number
}

interface ErrorBarChartProps {
  data: ErrorBarPoint[]
  title?: string
  xLabel?: string
  yLabel?: string
  className?: string
}

export function ErrorBarChart({ data, title, xLabel, yLabel, className }: ErrorBarChartProps) {
  if (data.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No sweep data available</div>
  }

  return (
    <PlotlyChart
      data={[
        {
          x: data.map((d) => d.x),
          y: data.map((d) => d.mean),
          error_y: {
            type: 'data' as const,
            array: data.map((d) => d.std),
            visible: true,
          },
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          marker: { color: '#6366f1', size: 8 },
          name: 'Mean',
        },
      ]}
      layout={{
        title: { text: title ?? 'Parameter Sweep' },
        xaxis: { title: { text: xLabel ?? 'Parameter Value' } },
        yaxis: { title: { text: yLabel ?? 'Metric' } },
        height: 400,
      }}
      className={className}
    />
  )
}
