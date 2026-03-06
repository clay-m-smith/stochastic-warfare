import { SearchInput } from '../../components/SearchInput'
import { Select } from '../../components/Select'

const ERA_OPTIONS = [
  { value: '', label: 'All Eras' },
  { value: 'modern', label: 'Modern' },
  { value: 'ww2', label: 'WW2' },
  { value: 'ww1', label: 'WW1' },
  { value: 'napoleonic', label: 'Napoleonic' },
  { value: 'ancient_medieval', label: 'Ancient & Medieval' },
]

const SORT_OPTIONS = [
  { value: 'name-asc', label: 'Name A-Z' },
  { value: 'name-desc', label: 'Name Z-A' },
  { value: 'era', label: 'Era' },
  { value: 'duration', label: 'Duration' },
]

interface ScenarioFiltersProps {
  era: string
  sort: string
  search: string
  onEraChange: (era: string) => void
  onSortChange: (sort: string) => void
  onSearchChange: (search: string) => void
}

export function ScenarioFilters({
  era,
  sort,
  search,
  onEraChange,
  onSortChange,
  onSearchChange,
}: ScenarioFiltersProps) {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-3">
      <div className="w-64">
        <SearchInput value={search} onChange={onSearchChange} placeholder="Search scenarios..." />
      </div>
      <Select value={era} onChange={onEraChange} options={ERA_OPTIONS} />
      <Select value={sort} onChange={onSortChange} options={SORT_OPTIONS} />
    </div>
  )
}
