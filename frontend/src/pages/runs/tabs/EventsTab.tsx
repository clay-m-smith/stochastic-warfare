import { useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { EmptyState } from '../../../components/EmptyState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { useRunEvents } from '../../../hooks/useRuns'

interface EventsTabProps {
  runId: string
}

const PAGE_SIZE = 100
const ROW_HEIGHT = 40

export function EventsTab({ runId }: EventsTabProps) {
  const [offset, setOffset] = useState(0)
  const [eventType, setEventType] = useState('')
  const parentRef = useRef<HTMLDivElement>(null)
  const { data, isLoading } = useRunEvents(runId, {
    offset,
    limit: PAGE_SIZE,
    event_type: eventType || undefined,
  })

  const events = data?.events ?? []
  const total = data?.total ?? 0

  const virtualizer = useVirtualizer({
    count: events.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 5,
  })

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
          </table>
          <div
            ref={parentRef}
            className="max-h-[600px] overflow-y-auto"
          >
            <div style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
              {virtualizer.getVirtualItems().map((virtualRow) => {
                const ev = events[virtualRow.index]!
                return (
                  <div
                    key={virtualRow.index}
                    data-testid="event-row"
                    className="absolute left-0 right-0 flex border-b border-gray-100 dark:border-gray-700 text-sm"
                    style={{
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    <span className="w-20 shrink-0 px-4 py-2 text-gray-600 dark:text-gray-400">{ev.tick}</span>
                    <span className="w-48 shrink-0 px-4 py-2 font-mono text-xs text-gray-900 dark:text-gray-100 truncate">{ev.event_type}</span>
                    <span className="w-32 shrink-0 px-4 py-2 text-gray-600 dark:text-gray-400 truncate">{ev.source}</span>
                    <span className="flex-1 px-4 py-2 font-mono text-xs text-gray-500 dark:text-gray-400 truncate">
                      {JSON.stringify(ev.data)}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
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
