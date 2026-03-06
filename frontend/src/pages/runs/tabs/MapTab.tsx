import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { TacticalMap } from '../../../components/map/TacticalMap'
import { useRunTerrain, useRunFrames } from '../../../hooks/useMap'
import { useRunEvents } from '../../../hooks/useRuns'
import { buildEngagementArcs } from '../../../lib/engagementProcessing'
import { useCallback } from 'react'

interface MapTabProps {
  runId: string
}

export function MapTab({ runId }: MapTabProps) {
  const [, setSearchParams] = useSearchParams()
  const { data: terrain, isLoading: terrainLoading } = useRunTerrain(runId)
  const { data: framesData, isLoading: framesLoading } = useRunFrames(runId)
  const { data: eventsData } = useRunEvents(runId, { limit: 10000 })

  const handleTickChange = useCallback(
    (tick: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('tick', String(tick))
        next.set('tab', 'map')
        return next
      })
    },
    [setSearchParams],
  )

  if (terrainLoading || framesLoading) return <LoadingSpinner />

  const frames = framesData?.frames ?? []
  if (frames.length === 0) {
    return <EmptyState message="Map data not available for this run." />
  }

  const engagementArcs = eventsData
    ? buildEngagementArcs(eventsData.events, frames)
    : []

  return (
    <div className="h-[600px]">
      <TacticalMap
        terrain={terrain!}
        frames={frames}
        engagementArcs={engagementArcs}
        onTickChange={handleTickChange}
      />
    </div>
  )
}
