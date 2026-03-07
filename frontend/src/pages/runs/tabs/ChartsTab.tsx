import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EventActivityChart } from '../../../components/charts/EventActivityChart'
import { EngagementTimeline } from '../../../components/charts/EngagementTimeline'
import { ForceStrengthChart } from '../../../components/charts/ForceStrengthChart'
import { MoraleChart } from '../../../components/charts/MoraleChart'
import { EmptyState } from '../../../components/EmptyState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { useRunEvents } from '../../../hooks/useRuns'
import {
  buildEngagementData,
  buildEventCounts,
  buildForceTimeSeries,
  buildMoraleTimeSeries,
} from '../../../lib/eventProcessing'
import type { RunResult } from '../../../types/api'

interface ChartsTabProps {
  runId: string
  result: RunResult | null
}

export function ChartsTab({ runId, result }: ChartsTabProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const currentTick = searchParams.get('tick') ? Number(searchParams.get('tick')) : null
  const { data: eventsData, isLoading } = useRunEvents(runId, { limit: 10000 })

  const handleChartClick = useCallback(
    (event: Plotly.PlotMouseEvent) => {
      const point = event.points?.[0]
      if (point && typeof point.x === 'number') {
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          next.set('tick', String(Math.round(point.x as number)))
          return next
        })
      }
    },
    [setSearchParams],
  )

  if (isLoading) return <LoadingSpinner />

  const events = eventsData?.events ?? []
  if (events.length === 0) {
    return <EmptyState message="No events recorded for this run." />
  }

  const forceData = buildForceTimeSeries(events, result)
  const engagementData = buildEngagementData(events)
  const moraleData = buildMoraleTimeSeries(events)
  const activityData = buildEventCounts(events)

  // Build vertical reference line shape for chart sync
  const tickMarkerShapes = currentTick != null
    ? [
        {
          type: 'line' as const,
          x0: currentTick,
          x1: currentTick,
          y0: 0,
          y1: 1,
          yref: 'paper' as const,
          line: { color: '#FF6600', width: 1, dash: 'dot' as const },
        },
      ]
    : []

  const tickOverrides = { shapes: tickMarkerShapes }

  return (
    <div className="space-y-6">
      <ForceStrengthChart data={forceData} layoutOverrides={tickOverrides} onClick={handleChartClick} />
      <EngagementTimeline data={engagementData} layoutOverrides={tickOverrides} onClick={handleChartClick} />
      <EventActivityChart data={activityData} layoutOverrides={tickOverrides} onClick={handleChartClick} />
      <MoraleChart data={moraleData} layoutOverrides={tickOverrides} onClick={handleChartClick} />
    </div>
  )
}
