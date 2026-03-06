import { apiGet } from './client'
import type { ScenarioDetail, ScenarioSummary } from '../types/api'

export function fetchScenarios(): Promise<ScenarioSummary[]> {
  return apiGet<ScenarioSummary[]>('/api/scenarios')
}

export function fetchScenario(name: string): Promise<ScenarioDetail> {
  return apiGet<ScenarioDetail>(`/api/scenarios/${encodeURIComponent(name)}`)
}
