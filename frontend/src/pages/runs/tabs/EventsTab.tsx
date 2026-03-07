import { useState } from 'react'
import { EmptyState } from '../../../components/EmptyState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { useRunEvents } from '../../../hooks/useRuns'

interface EventsTabProps {
  runId: string
}

const PAGE_SIZE = 100

export function EventsTab({ runId }: EventsTabProps) {
  const [offset, setOffset] = useState(0)
  const [eventType, setEventType] = useState('')
  const { data, isLoading } = useRunEvents(runId, {
    offset,
    limit: PAGE_SIZE,
    event_type: eventType || undefined,
  })

  const events = data?.events ?? []
  const total = data?.total ?? 0

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <input
          type="text"
          placeholder="Filter by event type..."
          value={eventType}
          onChange={(e) => {
            setEventType(e.target.value)
            setOffset(0)
          }}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
        />
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {total} total events
        </span>
      </div>

      {isLoading && <LoadingSpinner />}

      {!isLoading && events.length === 0 && (
        <EmptyState message="No events found." />
      )}

      {events.length > 0 && (
        <div className="overflow-x-auto rounded-lg bg-white dark:bg-gray-800 shadow">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-gray-500 dark:text-gray-400">
                <th className="px-4 py-3 font-medium">Tick</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Data</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => (
                <tr key={`${ev.tick}-${i}`} className="border-b border-gray-100 dark:border-gray-700">
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{ev.tick}</td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-900 dark:text-gray-100">{ev.event_type}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{ev.source}</td>
                  <td className="max-w-md truncate px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">
                    {JSON.stringify(ev.data)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:text-gray-200 disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <button
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:text-gray-200 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
