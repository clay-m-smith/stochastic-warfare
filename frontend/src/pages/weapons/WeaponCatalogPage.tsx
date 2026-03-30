import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { SearchInput } from '../../components/SearchInput'
import { Select } from '../../components/Select'
import { useWeapons } from '../../hooks/useMeta'
import { WeaponCard } from './WeaponCard'
import { WeaponDetailModal } from './WeaponDetailModal'

const CATEGORY_OPTIONS = [
  { value: '', label: 'All Categories' },
  { value: 'gun', label: 'Gun' },
  { value: 'autocannon', label: 'Autocannon' },
  { value: 'artillery', label: 'Artillery' },
  { value: 'missile', label: 'Missile' },
  { value: 'torpedo', label: 'Torpedo' },
  { value: 'bomb', label: 'Bomb' },
  { value: 'rocket', label: 'Rocket' },
  { value: 'directed_energy', label: 'Directed Energy' },
  { value: 'melee', label: 'Melee' },
]

export function WeaponCatalogPage() {
  const { data: weapons, isLoading, error, refetch } = useWeapons()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedWeapon, setSelectedWeapon] = useState<string | null>(null)

  const category = searchParams.get('category') ?? ''
  const search = searchParams.get('q') ?? ''

  function updateParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set(key, value)
      } else {
        next.delete(key)
      }
      return next
    })
  }

  const filtered = useMemo(() => {
    let result = weapons ?? []
    if (category) result = result.filter((w) => w.category === category)
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(
        (w) =>
          w.display_name.toLowerCase().includes(q) ||
          w.weapon_id.toLowerCase().includes(q) ||
          w.category.toLowerCase().includes(q),
      )
    }
    return [...result].sort((a, b) => (a.display_name || a.weapon_id).localeCompare(b.display_name || b.weapon_id))
  }, [weapons, category, search])

  return (
    <div>
      <PageHeader title="Weapon Catalog" />
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <SearchInput
          value={search}
          onChange={(v) => updateParam('q', v)}
          placeholder="Search weapons..."
        />
        <Select
          value={category}
          onChange={(v) => updateParam('category', v)}
          options={CATEGORY_OPTIONS}
        />
      </div>
      {isLoading && <LoadingSpinner />}
      {error && <ErrorMessage message={error.message} onRetry={() => refetch()} />}
      {!isLoading && !error && filtered.length === 0 && (
        <EmptyState message="No weapons match your filters." />
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((w) => (
          <WeaponCard key={w.weapon_id} weapon={w} onClick={() => setSelectedWeapon(w.weapon_id)} />
        ))}
      </div>
      <WeaponDetailModal weaponId={selectedWeapon} onClose={() => setSelectedWeapon(null)} />
    </div>
  )
}
