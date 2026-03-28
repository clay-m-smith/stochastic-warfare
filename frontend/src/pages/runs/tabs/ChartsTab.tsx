import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CasualtyBreakdownChart } from '../../../components/charts/CasualtyBreakdownChart'
import { EngagementSummaryChart } from '../../../components/charts/EngagementSummaryChart'
import { EventActivityChart } from '../../../components/charts/EventActivityChart'
import { EngagementTimeline } from '../../../components/charts/EngagementTimeline'
import { ForceStrengthChart } from '../../../components/charts/ForceStrengthChart'
import { MoraleChart } from '../../../components/charts/MoraleChart'
import { MoraleDistributionChart } from '../../../components/charts/MoraleDistributionChart'
import { SuppressionChart } from '../../../components/charts/SuppressionChart'
import { EmptyState } from '../../../components/EmptyState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { useAnalyticsSummary } from '../../../hooks/useAnalytics'
import { useRunEvents } from '../../../hooks/useRuns'
import {
  buildEngagementData,
  buildEventCounts,
  buildForceTimeSeries,
  buildMoraleTimeSeries,
  tickToSeconds,
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
  const { data: analytics } = useAnalyticsSummary(runId)
  const dt = tickToSeconds(result)

  const handleChartClick = useCallback(
    (event: Plotly.PlotMouseEvent) => {
      const point = event.points?.[0]
      if (point && typeof point.x === 'number') {
        // x is time_s, convert back to tick
        const tick = Math.round((point.x as number) / dt)
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          next.set('tick', String(tick))
          return next
        })
      }
    },
    [setSearchParams, dt],
  )

  if (isLoading) return <LoadingSpinner />

  const events = eventsData?.events ?? []
  if (events.length === 0) {
    return <EmptyState message="No events recorded for this run." />
  }

  const forceData = buildForceTimeSeries(events, result)
  const engagementData = buildEngagementData(events, result)
  const moraleData = buildMoraleTimeSeries(events, result)
  const activityData = buildEventCounts(events, result)

  // Build vertical reference line shape for chart sync (in time_s units)
  const currentTime = currentTick != null ? currentTick * dt : null
  const tickMarkerShapes = currentTime != null
    ? [
        {
          type: 'line' as const,
          x0: currentTime,
          x1: currentTime,
          y0: 0,
          y1: 1,
          yref: 'paper' as const,
          line: { color: '#FF6600', width: 1, dash: 'dot' as const },
        },
      ]
    : []

  // Set x-axis range to full scenario duration
  const totalTime = result?.duration_s ?? 0
  const tickOverrides = {
    shapes: tickMarkerShapes,
    xaxis: { range: [0, totalTime], title: { text: 'Elapsed Time (s)' } },
  }

  return (
    <div className="space-y-6">
      <ForceStrengthChart data={forceData} layoutOverrides={tickOverrides} onClick={handleChartClick} />
      <EngagementTimeline data={engagementData} layoutOverrides={tickOverrides} onClick={handleChartClick} />
      <EventActivityChart data={activityData} layoutOverrides={tickOverrides} onClick={handleChartClick} />
      <MoraleChart data={moraleData} layoutOverrides={tickOverrides} onClick={handleChartClick} />

      {/* Phase 93: Server-side analytics charts */}
      {analytics && (
        <>
          <CasualtyBreakdownChart data={analytics.casualties} layoutOverrides={tickOverrides} onClick={handleChartClick} />
          <EngagementSummaryChart data={analytics.engagements} />
          <SuppressionChart data={analytics.suppression} dt={dt} layoutOverrides={tickOverrides} onClick={handleChartClick} />
          <MoraleDistributionChart data={analytics.morale} dt={dt} layoutOverrides={tickOverrides} onClick={handleChartClick} />
        </>
      )}
    </div>
  )
}
