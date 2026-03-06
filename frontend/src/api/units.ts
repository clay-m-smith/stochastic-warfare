import { apiGet } from './client'
import type { UnitDetail, UnitSummary } from '../types/api'

export function fetchUnits(params?: {
  domain?: string
  era?: string
  category?: string
}): Promise<UnitSummary[]> {
  const sp = new URLSearchParams()
  if (params?.domain) sp.set('domain', params.domain)
  if (params?.era) sp.set('era', params.era)
  if (params?.category) sp.set('category', params.category)
  const qs = sp.toString()
  return apiGet<UnitSummary[]>(`/api/units${qs ? `?${qs}` : ''}`)
}

export function fetchUnit(unitType: string): Promise<UnitDetail> {
  return apiGet<UnitDetail>(`/api/units/${encodeURIComponent(unitType)}`)
}
