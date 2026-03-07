import { useParams, useSearchParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { ErrorMessage } from '../../components/ErrorMessage'
import { ExportMenu } from '../../components/ExportMenu'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { TabBar } from '../../components/TabBar'
import { useRun, useRunEvents, useRunNarrative } from '../../hooks/useRuns'
import { useExport } from '../../hooks/useExport'
import { formatDate, eventsToCsvRows } from '../../lib/format'
import type { RunResult, RunStatus } from '../../types/api'
import { RunDeleteButton } from './RunDeleteButton'
import { RunProgressPanel } from './RunProgressPanel'
import { ChartsTab } from './tabs/ChartsTab'
import { EventsTab } from './tabs/EventsTab'
import { MapTab } from './tabs/MapTab'
import { NarrativeTab } from './tabs/NarrativeTab'
import { ResultsTab } from './tabs/ResultsTab'

const STATUS_COLORS: Record<RunStatus, string> = {
  pending: 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300',
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
  const { data: allEvents } = useRunEvents(runId ?? '', { limit: 10000 })
  const { data: narrativeData } = useRunNarrative(runId ?? '')
  const { downloadJSON, downloadCSV, printReport } = useExport()

  if (!runId) return <ErrorMessage message="No run ID specified" />
  if (isLoading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error.message} onRetry={() => refetch()} />
  if (!run) return <ErrorMessage message="Run not found" />

  const isActive = run.status === 'pending' || run.status === 'running'
  const isCompleted = run.status === 'completed'

  const exportItems = [
    {
      label: 'Export JSON',
      onClick: () => run.result && downloadJSON(run.result, `${run.scenario_name}_result.json`),
    },
    {
      label: 'Export Events CSV',
      onClick: () => {
        if (allEvents?.events) {
          const { headers, rows } = eventsToCsvRows(allEvents.events)
          downloadCSV(headers, rows, `${run.scenario_name}_events.csv`)
        }
      },
    },
    {
      label: 'Download Narrative',
      onClick: () => {
        if (narrativeData?.narrative) {
          const blob = new Blob([narrativeData.narrative], { type: 'text/plain' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `${run.scenario_name}_narrative.txt`
          a.click()
          URL.revokeObjectURL(url)
        }
      },
    },
    { label: 'Print Report', onClick: () => printReport(runId) },
  ]

  return (
    <div>
      <PageHeader title={run.scenario_name}>
        <Badge className={STATUS_COLORS[run.status]}>{run.status}</Badge>
        {isCompleted && <ExportMenu items={exportItems} />}
        <RunDeleteButton runId={runId} />
      </PageHeader>

      <div className="mb-6 grid grid-cols-2 gap-4 text-sm text-gray-600 dark:text-gray-400 sm:grid-cols-4">
        <div>
          <span className="font-medium text-gray-500 dark:text-gray-400">Seed:</span> {run.seed}
        </div>
        <div>
          <span className="font-medium text-gray-500 dark:text-gray-400">Max Ticks:</span> {run.max_ticks}
        </div>
        <div>
          <span className="font-medium text-gray-500 dark:text-gray-400">Created:</span> {formatDate(run.created_at)}
        </div>
        <div>
          <span className="font-medium text-gray-500 dark:text-gray-400">Completed:</span>{' '}
          {formatDate(run.completed_at)}
        </div>
      </div>

      {isActive && <RunProgressPanel runId={runId} />}

      {run.status === 'failed' && run.error_message && (
        <div className="mb-6 rounded-md bg-red-50 dark:bg-red-900/30 p-4 text-sm text-red-700 dark:text-red-400">
          <pre className="whitespace-pre-wrap font-mono text-xs">{run.error_message}</pre>
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
