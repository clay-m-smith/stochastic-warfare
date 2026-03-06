import { apiGet } from './client'
import type { TerrainData, FramesData } from '../types/map'

export function fetchRunTerrain(runId: string): Promise<TerrainData> {
  return apiGet<TerrainData>(`/api/runs/${encodeURIComponent(runId)}/terrain`)
}

export function fetchRunFrames(
  runId: string,
  params?: { start_tick?: number; end_tick?: number },
): Promise<FramesData> {
  const sp = new URLSearchParams()
  if (params?.start_tick != null) sp.set('start_tick', String(params.start_tick))
  if (params?.end_tick != null) sp.set('end_tick', String(params.end_tick))
  const qs = sp.toString()
  return apiGet<FramesData>(
    `/api/runs/${encodeURIComponent(runId)}/frames${qs ? `?${qs}` : ''}`,
  )
}
