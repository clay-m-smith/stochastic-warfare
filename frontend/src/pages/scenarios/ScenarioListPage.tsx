import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useScenarios } from '../../hooks/useScenarios'
import { eraDisplayName, eraOrder } from '../../lib/era'
import type { ScenarioSummary } from '../../types/api'
import { ScenarioCard } from './ScenarioCard'
import { ScenarioFilters } from './ScenarioFilters'

const ERA_SECTION_ORDER = ['modern', 'ww2', 'ww1', 'napoleonic', 'ancient_medieval']

interface ScenarioSection {
  key: string
  title: string
  subtitle?: string
  scenarios: ScenarioSummary[]
}

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

  // Partition filtered scenarios into sections: regression references first,
  // then by era.
  // Respects existing sort within each section.
  const sections = useMemo<ScenarioSection[]>(() => {
    const regressionReferences: ScenarioSummary[] = []
    const byEra: Record<string, ScenarioSummary[]> = {}
    for (const s of filtered) {
      if (s.historical_validation.current_engine_regression_evidence) {
        regressionReferences.push(s)
      } else {
        const key = s.era || 'other'
        if (!byEra[key]) byEra[key] = []
        byEra[key].push(s)
      }
    }
    const result: ScenarioSection[] = []
    if (regressionReferences.length > 0) {
      result.push({
        key: 'regression-references',
        title: 'Current-Engine Regression References',
        subtitle:
          'Scenarios with typed current-engine regression evidence — not historical validation or predictive calibration',
        scenarios: regressionReferences,
      })
    }
    for (const eraKey of ERA_SECTION_ORDER) {
      if (byEra[eraKey]?.length) {
        result.push({
          key: `era-${eraKey}`,
          title: eraDisplayName(eraKey),
          scenarios: byEra[eraKey],
        })
      }
    }
    // Any eras not in ERA_SECTION_ORDER (defensive)
    for (const [eraKey, items] of Object.entries(byEra)) {
      if (!ERA_SECTION_ORDER.includes(eraKey) && items.length > 0) {
        result.push({
          key: `era-${eraKey}`,
          title: eraDisplayName(eraKey),
          scenarios: items,
        })
      }
    }
    return result
  }, [filtered])

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
      {sections.map((section, idx) => (
        <section key={section.key} className={idx > 0 ? 'mt-8' : ''}>
          <div className="mb-3 border-b border-gray-200 pb-2 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {section.title}
              <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
                ({section.scenarios.length})
              </span>
            </h2>
            {section.subtitle && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{section.subtitle}</p>
            )}
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {section.scenarios.map((s) => (
              <ScenarioCard key={s.name} scenario={s} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
