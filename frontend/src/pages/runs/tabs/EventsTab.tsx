import { useEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { EmptyState } from '../../../components/EmptyState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { useRunEvents } from '../../../hooks/useRuns'
import { ENGAGEMENT_EVENTS } from '../../../lib/eventProcessing'
import type { EventItem } from '../../../types/api'
import { EngagementDetailModal } from './EngagementDetailModal'

interface EventsTabProps {
  runId: string
}

const PAGE_SIZE = 100
const ROW_HEIGHT = 40

export function EventsTab({ runId }: EventsTabProps) {
  const [offset, setOffset] = useState(0)
  const [eventType, setEventType] = useState('')
  const [side, setSide] = useState('')
  const [tickMin, setTickMin] = useState('')
  const [tickMax, setTickMax] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [selectedEvent, setSelectedEvent] = useState<EventItem | null>(null)
  const parentRef = useRef<HTMLDivElement>(null)

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput)
      setOffset(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  const { data, isLoading } = useRunEvents(runId, {
    offset,
    limit: PAGE_SIZE,
    event_type: eventType || undefined,
    side: side || undefined,
    tick_min: tickMin ? parseInt(tickMin, 10) : undefined,
    tick_max: tickMax ? parseInt(tickMax, 10) : undefined,
    search: debouncedSearch || undefined,
  })

  const events = data?.events ?? []
  const total = data?.total ?? 0

  const virtualizer = useVirtualizer({
    count: events.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 5,
  })

  const hasFilters = !!(eventType || side || tickMin || tickMax || searchInput)

  const clearFilters = () => {
    setEventType('')
    setSide('')
    setTickMin('')
    setTickMax('')
    setSearchInput('')
    setDebouncedSearch('')
    setOffset(0)
  }

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Filter by event type..."
          value={eventType}
          onChange={(e) => {
            setEventType(e.target.value)
            setOffset(0)
          }}
          aria-label="Event type filter"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        />
        <select
          value={side}
          onChange={(e) => {
            setSide(e.target.value)
            setOffset(0)
          }}
          aria-label="Side filter"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        >
          <option value="">All Sides</option>
          <option value="blue">Blue</option>
          <option value="red">Red</option>
        </select>
        <input
          type="number"
          placeholder="Tick min"
          value={tickMin}
          onChange={(e) => {
            setTickMin(e.target.value)
            setOffset(0)
          }}
          aria-label="Tick minimum"
          className="w-24 rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        />
        <input
          type="number"
          placeholder="Tick max"
          value={tickMax}
          onChange={(e) => {
            setTickMax(e.target.value)
            setOffset(0)
          }}
          aria-label="Tick maximum"
          className="w-24 rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        />
        <input
          type="text"
          placeholder="Search events..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          aria-label="Event search"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        />
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-700"
          >
            Clear Filters
          </button>
        )}
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {hasFilters ? `Showing ${total} filtered events` : `${total} total events`}
        </span>
      </div>

      {isLoading && <LoadingSpinner />}

      {!isLoading && events.length === 0 && (
        <EmptyState message="No events found." />
      )}

      {events.length > 0 && (
        <div className="overflow-x-auto rounded-lg bg-white shadow dark:bg-gray-800">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-gray-500 dark:border-gray-700 dark:text-gray-400">
                <th className="px-4 py-3 font-medium" scope="col">Tick</th>
                <th className="px-4 py-3 font-medium" scope="col">Type</th>
                <th className="px-4 py-3 font-medium" scope="col">Source</th>
                <th className="px-4 py-3 font-medium" scope="col">Data</th>
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
                const isEngagement = ENGAGEMENT_EVENTS.has(ev.event_type)
                return (
                  <div
                    key={virtualRow.index}
                    data-testid="event-row"
                    className={`absolute left-0 right-0 flex border-b border-gray-100 text-sm dark:border-gray-700${
                      isEngagement ? ' cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20' : ''
                    }`}
                    style={{
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                    onClick={isEngagement ? () => setSelectedEvent(ev) : undefined}
                  >
                    <span className="w-20 shrink-0 px-4 py-2 text-gray-600 dark:text-gray-400">{ev.tick}</span>
                    <span className="w-48 shrink-0 truncate px-4 py-2 font-mono text-xs text-gray-900 dark:text-gray-100">{ev.event_type}</span>
                    <span className="w-32 shrink-0 truncate px-4 py-2 text-gray-600 dark:text-gray-400">{ev.source}</span>
                    <span className="flex-1 truncate px-4 py-2 font-mono text-xs text-gray-500 dark:text-gray-400">
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
            className="rounded-md border border-gray-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-gray-600 dark:text-gray-200"
          >
            Previous
          </button>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <button
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-gray-600 dark:text-gray-200"
          >
            Next
          </button>
        </div>
      )}

      <EngagementDetailModal event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </div>
  )
}
