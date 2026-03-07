import { Disclosure } from '@headlessui/react'

interface ConfigDiffProps {
  original: Record<string, unknown>
  modified: Record<string, unknown>
}

interface DiffEntry {
  path: string
  oldValue: unknown
  newValue: unknown
}

function collectDiffs(
  original: Record<string, unknown>,
  modified: Record<string, unknown>,
  prefix = '',
): DiffEntry[] {
  const diffs: DiffEntry[] = []
  const allKeys = new Set([...Object.keys(original), ...Object.keys(modified)])

  for (const key of allKeys) {
    const path = prefix ? `${prefix}.${key}` : key
    const oldVal = original[key]
    const newVal = modified[key]

    if (
      oldVal != null &&
      newVal != null &&
      typeof oldVal === 'object' &&
      typeof newVal === 'object' &&
      !Array.isArray(oldVal) &&
      !Array.isArray(newVal)
    ) {
      diffs.push(
        ...collectDiffs(
          oldVal as Record<string, unknown>,
          newVal as Record<string, unknown>,
          path,
        ),
      )
    } else if (JSON.stringify(oldVal) !== JSON.stringify(newVal)) {
      diffs.push({ path, oldValue: oldVal, newValue: newVal })
    }
  }

  return diffs
}

function formatValue(v: unknown): string {
  if (v === undefined) return '(none)'
  if (v === null) return 'null'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export function ConfigDiff({ original, modified }: ConfigDiffProps) {
  const diffs = collectDiffs(original, modified)

  if (diffs.length === 0) {
    return (
      <div className="rounded-lg bg-white dark:bg-gray-800 p-4 shadow text-sm text-gray-500 dark:text-gray-400">
        No changes from original.
      </div>
    )
  }

  return (
    <Disclosure>
      {({ open }) => (
        <div className="rounded-lg bg-white dark:bg-gray-800 shadow">
          <Disclosure.Button className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
            <span>Changes ({diffs.length})</span>
            <span className="text-xs">{open ? '▲' : '▼'}</span>
          </Disclosure.Button>
          <Disclosure.Panel className="px-4 pb-3">
            <ul className="space-y-1 text-xs font-mono">
              {diffs.map((d) => (
                <li key={d.path} className="text-gray-600 dark:text-gray-400">
                  <span className="font-semibold text-gray-800 dark:text-gray-200">{d.path}</span>
                  {': '}
                  <span className="text-red-500 line-through">{formatValue(d.oldValue)}</span>
                  {' → '}
                  <span className="text-green-600 dark:text-green-400">{formatValue(d.newValue)}</span>
                </li>
              ))}
            </ul>
          </Disclosure.Panel>
        </div>
      )}
    </Disclosure>
  )
}
