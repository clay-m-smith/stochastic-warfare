import { useQuery } from '@tanstack/react-query'
import { fetchCommanders, fetchDoctrines, fetchEras, fetchHealth, fetchSchools, fetchWeaponDetail, fetchWeapons } from '../api/meta'
import type { CommanderInfo, EraInfo, HealthResponse, SchoolInfo, WeaponDetail, WeaponSummary } from '../types/api'

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: fetchHealth,
    staleTime: 30 * 1000,
    retry: 1,
  })
}

export function useEras() {
  return useQuery<EraInfo[]>({
    queryKey: ['eras'],
    queryFn: fetchEras,
    staleTime: 10 * 60 * 1000,
  })
}

export function useSchools() {
  return useQuery<SchoolInfo[]>({
    queryKey: ['schools'],
    queryFn: fetchSchools,
    staleTime: 10 * 60 * 1000,
  })
}

export function useCommanders() {
  return useQuery<CommanderInfo[]>({
    queryKey: ['commanders'],
    queryFn: fetchCommanders,
    staleTime: 10 * 60 * 1000,
  })
}

export function useDoctrines() {
  return useQuery<{ name: string; category: string; display_name?: string }[]>({
    queryKey: ['doctrines'],
    queryFn: fetchDoctrines,
    staleTime: 10 * 60 * 1000,
  })
}

export function useWeapons() {
  return useQuery<WeaponSummary[]>({
    queryKey: ['weapons'],
    queryFn: fetchWeapons,
    staleTime: 5 * 60 * 1000,
  })
}

export function useWeaponDetail(weaponId: string) {
  return useQuery<WeaponDetail>({
    queryKey: ['weapons', weaponId],
    queryFn: () => fetchWeaponDetail(weaponId),
    staleTime: 5 * 60 * 1000,
    enabled: !!weaponId,
  })
}
