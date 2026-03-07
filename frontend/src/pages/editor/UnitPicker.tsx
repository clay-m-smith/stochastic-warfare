import { useState } from 'react'
import { Dialog } from '@headlessui/react'
import { useUnits } from '../../hooks/useUnits'

interface UnitPickerProps {
  era: string
  onSelect: (unitType: string) => void
  onClose: () => void
}

export function UnitPicker({ era, onSelect, onClose }: UnitPickerProps) {
  const [search, setSearch] = useState('')
  const [domainFilter, setDomainFilter] = useState<string | null>(null)
  const { data: units } = useUnits()

  const filtered = (units ?? []).filter((u) => {
    if (u.era !== era && u.era !== 'modern' && era !== 'modern') return false
    if (search && !u.unit_type.toLowerCase().includes(search.toLowerCase()) &&
        !u.display_name.toLowerCase().includes(search.toLowerCase())) return false
    if (domainFilter && u.domain !== domainFilter) return false
    return true
  })

  const domains = Array.from(new Set((units ?? []).map((u) => u.domain))).filter(Boolean).sort()

  return (
    <Dialog open onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto max-h-[80vh] w-full max-w-lg overflow-hidden rounded-lg bg-white dark:bg-gray-800 shadow-xl">
          <div className="border-b border-gray-200 dark:border-gray-700 p-4">
            <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-gray-100">Add Unit</Dialog.Title>
            <input
              type="text"
              placeholder="Search units..."
              className="mt-2 block w-full rounded border-gray-300 text-sm shadow-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
            <div className="mt-2 flex flex-wrap gap-1">
              <button
                className={`rounded px-2 py-1 text-xs ${domainFilter === null ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
                onClick={() => setDomainFilter(null)}
              >
                All
              </button>
              {domains.map((d) => (
                <button
                  key={d}
                  className={`rounded px-2 py-1 text-xs ${domainFilter === d ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
                  onClick={() => setDomainFilter(d)}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          <div className="max-h-80 overflow-y-auto p-2">
            {filtered.length === 0 && (
              <p className="p-4 text-center text-sm text-gray-400 dark:text-gray-500">No units found</p>
            )}
            {filtered.map((u) => (
              <button
                key={u.unit_type}
                className="block w-full rounded px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700"
                onClick={() => onSelect(u.unit_type)}
              >
                <span className="font-medium text-gray-800 dark:text-gray-200">{u.display_name || u.unit_type}</span>
                <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">{u.domain}</span>
              </button>
            ))}
          </div>
          <div className="border-t border-gray-200 dark:border-gray-700 p-3 text-right">
            <button
              className="rounded px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
              onClick={onClose}
            >
              Cancel
            </button>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}
