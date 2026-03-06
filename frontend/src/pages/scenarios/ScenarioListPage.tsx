import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useScenarios } from '../../hooks/useScenarios'
import { eraOrder } from '../../lib/era'
import { ScenarioCard } from './ScenarioCard'
import { ScenarioFilters } from './ScenarioFilters'

export function ScenarioListPage() {
  const { data: scenarios, isLoading, error, refetch } = useScenarios()
  const [searchParams, setSearchParams] = useSearchParams()

  const era = searchParams.get('era') ?? ''
  const sort = searchParams.get('sort') ?? 'name-asc'
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
    let result = scenarios ?? []
    if (era) result = result.filter((s) => s.era === era)
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(
        (s) =>
          s.display_name.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q) ||
          s.terrain_type.toLowerCase().includes(q),
      )
    }
    const sorted = [...result]
    switch (sort) {
      case 'name-desc':
        sorted.sort((a, b) => b.display_name.localeCompare(a.display_name))
        break
      case 'era':
        sorted.sort((a, b) => eraOrder(a.era) - eraOrder(b.era))
        break
      case 'duration':
        sorted.sort((a, b) => a.duration_hours - b.duration_hours)
        break
      default:
        sorted.sort((a, b) => a.display_name.localeCompare(b.display_name))
    }
    return sorted
  }, [scenarios, era, search, sort])

  return (
    <div>
      <PageHeader title="Scenarios" />
      <ScenarioFilters
        era={era}
        sort={sort}
        search={search}
        onEraChange={(v) => updateParam('era', v)}
        onSortChange={(v) => updateParam('sort', v)}
        onSearchChange={(v) => updateParam('q', v)}
      />
      {isLoading && <LoadingSpinner />}
      {error && <ErrorMessage message={error.message} onRetry={() => refetch()} />}
      {!isLoading && !error && filtered.length === 0 && (
        <EmptyState message="No scenarios match your filters." />
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((s) => (
          <ScenarioCard key={s.name} scenario={s} />
        ))}
      </div>
    </div>
  )
}
