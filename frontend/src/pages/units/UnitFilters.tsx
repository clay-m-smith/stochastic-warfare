import { SearchInput } from '../../components/SearchInput'
import { Select } from '../../components/Select'

const DOMAIN_OPTIONS = [
  { value: '', label: 'All Domains' },
  { value: 'land', label: 'Land' },
  { value: 'air', label: 'Air' },
  { value: 'naval', label: 'Naval' },
  { value: 'submarine', label: 'Submarine' },
  { value: 'space', label: 'Space' },
]

const ERA_OPTIONS = [
  { value: '', label: 'All Eras' },
  { value: 'modern', label: 'Modern' },
  { value: 'ww2', label: 'WW2' },
  { value: 'ww1', label: 'WW1' },
  { value: 'napoleonic', label: 'Napoleonic' },
  { value: 'ancient_medieval', label: 'Ancient & Medieval' },
]

interface UnitFiltersProps {
  domain: string
  era: string
  search: string
  onDomainChange: (d: string) => void
  onEraChange: (e: string) => void
  onSearchChange: (s: string) => void
}

export function UnitFilters({
  domain,
  era,
  search,
  onDomainChange,
  onEraChange,
  onSearchChange,
}: UnitFiltersProps) {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-3">
      <div className="w-64">
        <SearchInput value={search} onChange={onSearchChange} placeholder="Search units..." />
      </div>
      <Select value={domain} onChange={onDomainChange} options={DOMAIN_OPTIONS} />
      <Select value={era} onChange={onEraChange} options={ERA_OPTIONS} />
    </div>
  )
}
