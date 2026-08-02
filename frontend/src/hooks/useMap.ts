import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { fetchRunTerrain, fetchRunFrames } from '../api/map'
import type {
  FramesData,
  PrivilegedFramesData,
  PrivilegedFramesParams,
  RunFramesParams,
  SideFowFramesData,
  SideFowFramesParams,
  TerrainData,
} from '../types/map'

export function useRunTerrain(runId: string) {
  return useQuery<TerrainData>({
    queryKey: ['runs', runId, 'terrain'],
    queryFn: () => fetchRunTerrain(runId),
    enabled: !!runId,
    staleTime: Infinity,
  })
}

export function useRunFrames(
  runId: string,
  params: SideFowFramesParams,
): UseQueryResult<SideFowFramesData>
export function useRunFrames(
  runId: string,
  params?: PrivilegedFramesParams,
): UseQueryResult<PrivilegedFramesData>
export function useRunFrames(
  runId: string,
  params: RunFramesParams,
): UseQueryResult<FramesData>
export function useRunFrames(runId: string, params?: RunFramesParams) {
  const scope = params?.scope ?? 'PRIVILEGED_ENGINE'
  const side = params?.scope === 'SIDE_FOW' ? params.side : null
  return useQuery<FramesData>({
    queryKey: [
      'runs',
      runId,
      'frames',
      scope,
      side,
      params?.start_tick ?? null,
      params?.end_tick ?? null,
    ],
    queryFn: () => params
      ? fetchRunFrames(runId, params)
      : fetchRunFrames(runId),
    enabled: !!runId,
    staleTime: Infinity,
  })
}
