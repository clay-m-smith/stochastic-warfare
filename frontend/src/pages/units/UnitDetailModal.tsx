import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useUnit } from '../../hooks/useUnits'

interface UnitDetailModalProps {
  unitType: string | null
  onClose: () => void
}

function renderValue(value: unknown, depth: number = 0): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-gray-400 dark:text-gray-500">—</span>
  if (typeof value === 'boolean') return <span>{value ? 'Yes' : 'No'}</span>
  if (typeof value === 'number' || typeof value === 'string') return <span>{String(value)}</span>

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-gray-400 dark:text-gray-500">[]</span>
    return (
      <ul className="list-inside list-disc">
        {value.map((item, i) => (
          <li key={i}>{renderValue(item, depth + 1)}</li>
        ))}
      </ul>
    )
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) return <span className="text-gray-400 dark:text-gray-500">{'{}'}</span>
    return (
      <div className={depth > 0 ? 'ml-4' : ''}>
        {entries.map(([k, v]) => (
          <div key={k} className="py-1">
            <span className="font-medium text-gray-700 dark:text-gray-300">{k}: </span>
            {renderValue(v, depth + 1)}
          </div>
        ))}
      </div>
    )
  }

  return <span>{String(value)}</span>
}

export function UnitDetailModal({ unitType, onClose }: UnitDetailModalProps) {
  const { data, isLoading } = useUnit(unitType ?? '')

  return (
    <Dialog open={!!unitType} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white dark:bg-gray-800 p-6 shadow-xl">
          <DialogTitle className="mb-4 text-xl font-bold text-gray-900 dark:text-gray-100">
            {data?.definition?.name ? String(data.definition.name) : unitType}
          </DialogTitle>

          {isLoading && <LoadingSpinner />}

          {data && (
            <div className="text-sm">
              {renderValue(data.definition)}
            </div>
          )}

          <button
            onClick={onClose}
            aria-label="Close"
            className="mt-6 rounded-md bg-gray-100 dark:bg-gray-700 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            Close
          </button>
        </DialogPanel>
      </div>
    </Dialog>
  )
}
