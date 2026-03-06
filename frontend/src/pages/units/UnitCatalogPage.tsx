import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useUnits } from '../../hooks/useUnits'
import { UnitCard } from './UnitCard'
import { UnitDetailModal } from './UnitDetailModal'
import { UnitFilters } from './UnitFilters'

export function UnitCatalogPage() {
  const { data: units, isLoading, error, refetch } = useUnits()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedUnit, setSelectedUnit] = useState<string | null>(null)

  const domain = searchParams.get('domain') ?? ''
  const era = searchParams.get('era') ?? ''
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
    let result = units ?? []
    if (domain) result = result.filter((u) => u.domain === domain)
    if (era) result = result.filter((u) => u.era === era)
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(
        (u) =>
          u.display_name.toLowerCase().includes(q) ||
          u.unit_type.toLowerCase().includes(q) ||
          u.category.toLowerCase().includes(q),
      )
    }
    return [...result].sort((a, b) => a.display_name.localeCompare(b.display_name))
  }, [units, domain, era, search])

  return (
    <div>
      <PageHeader title="Unit Catalog" />
      <UnitFilters
        domain={domain}
        era={era}
        search={search}
        onDomainChange={(v) => updateParam('domain', v)}
        onEraChange={(v) => updateParam('era', v)}
        onSearchChange={(v) => updateParam('q', v)}
      />
      {isLoading && <LoadingSpinner />}
      {error && <ErrorMessage message={error.message} onRetry={() => refetch()} />}
      {!isLoading && !error && filtered.length === 0 && (
        <EmptyState message="No units match your filters." />
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((u) => (
          <UnitCard key={u.unit_type} unit={u} onClick={() => setSelectedUnit(u.unit_type)} />
        ))}
      </div>
      <UnitDetailModal unitType={selectedUnit} onClose={() => setSelectedUnit(null)} />
    </div>
  )
}
