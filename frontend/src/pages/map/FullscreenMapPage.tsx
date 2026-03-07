import { Link, useParams } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TacticalMap } from '../../components/map/TacticalMap'
import { useRunTerrain, useRunFrames } from '../../hooks/useMap'
import { useRunEvents } from '../../hooks/useRuns'
import { buildEngagementArcs } from '../../lib/engagementProcessing'

export function FullscreenMapPage() {
  const { runId } = useParams<{ runId: string }>()
  const { data: terrain, isLoading: terrainLoading } = useRunTerrain(runId ?? '')
  const { data: framesData, isLoading: framesLoading } = useRunFrames(runId ?? '')
  const { data: eventsData } = useRunEvents(runId ?? '', { limit: 10000 })

  if (!runId) return <EmptyState message="No run ID specified" />
  if (terrainLoading || framesLoading) return <LoadingSpinner />

  const frames = framesData?.frames ?? []
  if (frames.length === 0) {
    return <EmptyState message="Map data not available for this run." />
  }

  const engagementArcs = eventsData
    ? buildEngagementArcs(eventsData.events, frames)
    : []

  return (
    <div className="flex h-screen flex-col">
      <div className="flex items-center gap-4 bg-gray-800 px-4 py-2 text-sm text-white">
        <Link to={`/runs/${runId}?tab=map`} className="hover:underline">
          &larr; Back to run
        </Link>
        <span className="text-gray-400 dark:text-gray-500">Fullscreen Map — Run {runId}</span>
      </div>
      <div className="flex-1">
        <TacticalMap
          terrain={terrain!}
          frames={frames}
          engagementArcs={engagementArcs}
        />
      </div>
    </div>
  )
}
