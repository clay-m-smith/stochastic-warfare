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
  const { data: eventsData, isLoading } = useRunEvents(runId, { limit: 10000 })

  if (isLoading) return <LoadingSpinner />

  const events = eventsData?.events ?? []
  if (events.length === 0) {
    return <EmptyState message="No events recorded for this run." />
  }

  const forceData = buildForceTimeSeries(events, result)
  const engagementData = buildEngagementData(events)
  const moraleData = buildMoraleTimeSeries(events)
  const activityData = buildEventCounts(events)

  return (
    <div className="space-y-6">
      <ForceStrengthChart data={forceData} />
      <EngagementTimeline data={engagementData} />
      <EventActivityChart data={activityData} />
      <MoraleChart data={moraleData} />
    </div>
  )
}
