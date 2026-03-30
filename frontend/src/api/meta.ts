import { apiGet } from './client'
import type { CommanderInfo, EraInfo, HealthResponse, SchoolInfo, WeaponDetail, WeaponSummary } from '../types/api'

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

export function fetchSchools(): Promise<SchoolInfo[]> {
  return apiGet<SchoolInfo[]>('/api/meta/schools')
}

export function fetchCommanders(): Promise<CommanderInfo[]> {
  return apiGet<CommanderInfo[]>('/api/meta/commanders')
}

export function fetchWeapons(): Promise<WeaponSummary[]> {
  return apiGet<WeaponSummary[]>('/api/meta/weapons')
}

export function fetchWeaponDetail(weaponId: string): Promise<WeaponDetail> {
  return apiGet<WeaponDetail>(`/api/meta/weapons/${encodeURIComponent(weaponId)}`)
}
