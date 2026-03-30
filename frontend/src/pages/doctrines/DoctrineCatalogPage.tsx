import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { EmptyState } from '../../components/EmptyState'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { SearchInput } from '../../components/SearchInput'
import { useDoctrines } from '../../hooks/useMeta'

export function DoctrineCatalogPage() {
  const { data: doctrines, isLoading, error, refetch } = useDoctrines()
  const [searchParams, setSearchParams] = useSearchParams()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const search = searchParams.get('q') ?? ''

  function updateSearch(value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set('q', value)
      } else {
        next.delete('q')
      }
      return next
    })
  }

  const filtered = useMemo(() => {
    let result = doctrines ?? []
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(
        (d) =>
          d.name.toLowerCase().includes(q) ||
          (d.display_name ?? '').toLowerCase().includes(q) ||
          (d.category ?? '').toLowerCase().includes(q),
      )
    }
    return [...result].sort((a, b) => a.name.localeCompare(b.name))
  }, [doctrines, search])

  return (
    <div>
      <PageHeader title="Doctrine Catalog" />
      <div className="mb-4">
        <SearchInput
          value={search}
          onChange={updateSearch}
          placeholder="Search doctrines..."
        />
      </div>
      {isLoading && <LoadingSpinner />}
      {error && <ErrorMessage message={error.message} onRetry={() => refetch()} />}
      {!isLoading && !error && filtered.length === 0 && (
        <EmptyState message="No doctrines match your search." />
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((d) => (
          <Card key={d.name} onClick={() => setExpandedId(expandedId === d.name ? null : d.name)}>
            <h3 className="mb-1 font-semibold text-gray-900 dark:text-gray-100">
              {d.display_name || d.name}
            </h3>
            <div className="mb-2 flex flex-wrap gap-1">
              {d.category && (
                <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                  {d.category}
                </Badge>
              )}
            </div>
            {expandedId === d.name && (
              <div className="mt-2 border-t border-gray-200 pt-2 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
                <div>ID: <span className="font-mono">{d.name}</span></div>
                {d.category && <div>Category: {d.category}</div>}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  )
}
