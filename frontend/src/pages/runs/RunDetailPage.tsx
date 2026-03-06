import { useParams, useSearchParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { TabBar } from '../../components/TabBar'
import { useRun } from '../../hooks/useRuns'
import { formatDate } from '../../lib/format'
import type { RunResult, RunStatus } from '../../types/api'
import { RunDeleteButton } from './RunDeleteButton'
import { RunProgressPanel } from './RunProgressPanel'
import { ChartsTab } from './tabs/ChartsTab'
import { EventsTab } from './tabs/EventsTab'
import { MapTab } from './tabs/MapTab'
import { NarrativeTab } from './tabs/NarrativeTab'
import { ResultsTab } from './tabs/ResultsTab'

const STATUS_COLORS: Record<RunStatus, string> = {
  pending: 'bg-gray-200 text-gray-700',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  cancelled: 'bg-yellow-100 text-yellow-800',
}

const TABS = [
  { id: 'results', label: 'Results' },
  { id: 'charts', label: 'Charts' },
  { id: 'map', label: 'Map' },
  { id: 'narrative', label: 'Narrative' },
  { id: 'events', label: 'Events' },
]

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') ?? 'results'
  const { data: run, isLoading, error, refetch } = useRun(runId ?? '')

  if (!runId) return <ErrorMessage message="No run ID specified" />
  if (isLoading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error.message} onRetry={() => refetch()} />
  if (!run) return <ErrorMessage message="Run not found" />

  const isActive = run.status === 'pending' || run.status === 'running'
  const isCompleted = run.status === 'completed'

  return (
    <div>
      <PageHeader title={run.scenario_name}>
        <Badge className={STATUS_COLORS[run.status]}>{run.status}</Badge>
        <RunDeleteButton runId={runId} />
      </PageHeader>

      <div className="mb-6 grid grid-cols-2 gap-4 text-sm text-gray-600 sm:grid-cols-4">
        <div>
          <span className="font-medium text-gray-500">Seed:</span> {run.seed}
        </div>
        <div>
          <span className="font-medium text-gray-500">Max Ticks:</span> {run.max_ticks}
        </div>
        <div>
          <span className="font-medium text-gray-500">Created:</span> {formatDate(run.created_at)}
        </div>
        <div>
          <span className="font-medium text-gray-500">Completed:</span>{' '}
          {formatDate(run.completed_at)}
        </div>
      </div>

      {isActive && <RunProgressPanel runId={runId} />}

      {run.status === 'failed' && run.error_message && (
        <div className="mb-6 rounded-md bg-red-50 p-4 text-sm text-red-700">
          {run.error_message}
        </div>
      )}

      {isCompleted && (
        <>
          <TabBar
            tabs={TABS}
            activeTab={activeTab}
            onTabChange={(id) => setSearchParams({ tab: id })}
          />
          <div className="mt-6">
            {activeTab === 'results' && (
              <ResultsTab run={run} result={run.result as unknown as RunResult | null} />
            )}
            {activeTab === 'charts' && <ChartsTab runId={runId} result={run.result as unknown as RunResult | null} />}
            {activeTab === 'map' && <MapTab runId={runId} />}
            {activeTab === 'narrative' && <NarrativeTab runId={runId} />}
            {activeTab === 'events' && <EventsTab runId={runId} />}
          </div>
        </>
      )}
    </div>
  )
}
