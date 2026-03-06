import { useQuery } from '@tanstack/react-query'
import { fetchRunTerrain, fetchRunFrames } from '../api/map'
import type { TerrainData, FramesData } from '../types/map'

export function useRunTerrain(runId: string) {
  return useQuery<TerrainData>({
    queryKey: ['runs', runId, 'terrain'],
    queryFn: () => fetchRunTerrain(runId),
    enabled: !!runId,
    staleTime: Infinity,
  })
}

export function useRunFrames(runId: string) {
  return useQuery<FramesData>({
    queryKey: ['runs', runId, 'frames'],
    queryFn: () => fetchRunFrames(runId),
    enabled: !!runId,
    staleTime: Infinity,
  })
}
