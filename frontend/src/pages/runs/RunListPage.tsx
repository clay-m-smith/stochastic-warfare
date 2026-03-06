import { useNavigate } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { EmptyState } from '../../components/EmptyState'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useRuns } from '../../hooks/useRuns'
import { formatDate } from '../../lib/format'
import type { RunStatus } from '../../types/api'

const STATUS_COLORS: Record<RunStatus, string> = {
  pending: 'bg-gray-200 text-gray-700',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  cancelled: 'bg-yellow-100 text-yellow-800',
}

export function RunListPage() {
  const navigate = useNavigate()
  const { data: runs, isLoading, error, refetch } = useRuns({ limit: 50 })

  return (
    <div>
      <PageHeader title="Runs">
        <button
          onClick={() => navigate('/runs/new')}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          New Run
        </button>
      </PageHeader>

      {isLoading && <LoadingSpinner />}
      {error && <ErrorMessage message={error.message} onRetry={() => refetch()} />}
      {!isLoading && !error && (!runs || runs.length === 0) && (
        <EmptyState message="No runs yet. Start one from the Scenarios page." />
      )}

      {runs && runs.length > 0 && (
        <div className="overflow-x-auto rounded-lg bg-white shadow">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-gray-500">
                <th className="px-4 py-3 font-medium">Scenario</th>
                <th className="px-4 py-3 font-medium">Seed</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Completed</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{run.scenario_name}</td>
                  <td className="px-4 py-3 text-gray-600">{run.seed}</td>
                  <td className="px-4 py-3">
                    <Badge className={STATUS_COLORS[run.status]}>{run.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(run.created_at)}</td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(run.completed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
