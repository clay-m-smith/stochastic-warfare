import { useState } from 'react'
import { EmptyState } from '../../../components/EmptyState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { Select } from '../../../components/Select'
import { useRunNarrative } from '../../../hooks/useRuns'

interface NarrativeTabProps {
  runId: string
}

const SIDE_OPTIONS = [
  { value: '', label: 'All Sides' },
  { value: 'blue', label: 'Blue' },
  { value: 'red', label: 'Red' },
]

const STYLE_OPTIONS = [
  { value: 'full', label: 'Full' },
  { value: 'summary', label: 'Summary' },
  { value: 'timeline', label: 'Timeline' },
]

export function NarrativeTab({ runId }: NarrativeTabProps) {
  const [side, setSide] = useState('')
  const [style, setStyle] = useState('full')
  const { data, isLoading } = useRunNarrative(
    runId,
    { side: side || undefined, style },
  )

  return (
    <div className="space-y-4">
      <div className="flex gap-4">
        <Select value={side} onChange={setSide} options={SIDE_OPTIONS} />
        <Select value={style} onChange={setStyle} options={STYLE_OPTIONS} />
      </div>

      {isLoading && <LoadingSpinner />}

      {!isLoading && !data?.narrative && (
        <EmptyState message="No narrative available for this run." />
      )}

      {data?.narrative && (
        <div className="rounded-lg bg-white p-6 shadow">
          <div className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-gray-800">
            {data.narrative}
          </div>
          {data.tick_count > 0 && (
            <div className="mt-4 text-xs text-gray-400">
              Covering {data.tick_count} ticks
            </div>
          )}
        </div>
      )}
    </div>
  )
}
