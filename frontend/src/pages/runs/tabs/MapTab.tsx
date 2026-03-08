import { useSearchParams } from 'react-router-dom'
import { useCallback, useMemo } from 'react'
import { EmptyState } from '../../../components/EmptyState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { TacticalMap } from '../../../components/map/TacticalMap'
import { useRunTerrain, useRunFrames } from '../../../hooks/useMap'
import { useRunEvents } from '../../../hooks/useRuns'
import { buildEngagementArcs } from '../../../lib/engagementProcessing'
import { interpolateFrames } from '../../../lib/frameInterpolation'
import type { RunResult } from '../../../types/api'

interface MapTabProps {
  runId: string
  result?: RunResult | null
}

export function MapTab({ runId, result }: MapTabProps) {
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

  const rawFrames = framesData?.frames ?? []
  // Interpolate for smooth playback when few frames (strategic campaigns)
  const frames = useMemo(() => interpolateFrames(rawFrames), [rawFrames])

  if (terrainLoading || framesLoading) return <LoadingSpinner />

  if (rawFrames.length === 0) {
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
        durationS={result?.duration_s}
        ticksExecuted={result?.ticks_executed}
      />
    </div>
  )
}
