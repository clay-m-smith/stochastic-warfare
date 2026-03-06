import { apiGet } from './client'
import type { EraInfo, HealthResponse } from '../types/api'

export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/api/health')
}

export function fetchEras(): Promise<EraInfo[]> {
  return apiGet<EraInfo[]>('/api/meta/eras')
}

export function fetchDoctrines(): Promise<{ name: string; category: string; display_name?: string }[]> {
  return apiGet('/api/meta/doctrines')
}

export function fetchTerrainTypes(): Promise<string[]> {
  return apiGet<string[]>('/api/meta/terrain-types')
}
