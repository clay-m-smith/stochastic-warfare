import { apiGet } from './client'
import type {
  FramesData,
  PrivilegedFramesData,
  PrivilegedFramesParams,
  RunFramesParams,
  SideFowFramesData,
  SideFowFramesParams,
  TerrainData,
} from '../types/map'

export function fetchRunTerrain(runId: string): Promise<TerrainData> {
  return apiGet<TerrainData>(`/api/runs/${encodeURIComponent(runId)}/terrain`)
}

export function fetchRunFrames(
  runId: string,
  params: SideFowFramesParams,
): Promise<SideFowFramesData>
export function fetchRunFrames(
  runId: string,
  params?: PrivilegedFramesParams,
): Promise<PrivilegedFramesData>
export function fetchRunFrames(
  runId: string,
  params: RunFramesParams,
): Promise<FramesData>
export function fetchRunFrames(
  runId: string,
  params?: RunFramesParams,
): Promise<FramesData> {
  const sp = new URLSearchParams()
  if (params?.start_tick != null) sp.set('start_tick', String(params.start_tick))
  if (params?.end_tick != null) sp.set('end_tick', String(params.end_tick))
  const rawScope = (params as { scope?: unknown } | undefined)?.scope
  const rawSide = (params as { side?: unknown } | undefined)?.side
  if (rawScope === 'SIDE_FOW') {
    const side = rawSide
    if (typeof side !== 'string' || !side || side.trim() !== side) {
      throw new Error('SIDE_FOW frame requests require a non-empty trimmed side')
    }
    sp.set('scope', rawScope)
    sp.set('side', side)
  } else {
    if (rawScope !== undefined && rawScope !== 'PRIVILEGED_ENGINE') {
      throw new Error('frame request has an unknown targeting exposure scope')
    }
    if (rawSide !== undefined) {
      throw new Error('side is valid only for SIDE_FOW frame requests')
    }
    if (rawScope === 'PRIVILEGED_ENGINE') sp.set('scope', rawScope)
  }
  const qs = sp.toString()
  return apiGet<FramesData>(
    `/api/runs/${encodeURIComponent(runId)}/frames${qs ? `?${qs}` : ''}`,
  )
}
