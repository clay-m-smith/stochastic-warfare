import { Suspense, lazy } from 'react'
import { LoadingSpinner } from '../LoadingSpinner'

const Plot = lazy(() => import('react-plotly.js'))

interface PlotlyChartProps {
  data: Plotly.Data[]
  layout?: Partial<Plotly.Layout>
  className?: string
}

export function PlotlyChart({ data, layout, className = '' }: PlotlyChartProps) {
  const defaultLayout: Partial<Plotly.Layout> = {
    autosize: true,
    margin: { l: 50, r: 20, t: 30, b: 40 },
    font: { family: 'system-ui, sans-serif', size: 12 },
    legend: { orientation: 'h', y: -0.2 },
    ...layout,
  }

  return (
    <div className={className}>
      <Suspense fallback={<LoadingSpinner />}>
        <Plot
          data={data}
          layout={defaultLayout}
          config={{ responsive: true, displayModeBar: false }}
          useResizeHandler
          style={{ width: '100%', height: '100%' }}
        />
      </Suspense>
    </div>
  )
}
