import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { EmptyState } from '../../components/EmptyState'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useRuns, useDeleteRun } from '../../hooks/useRuns'
import { formatDate } from '../../lib/format'
import type { RunStatus } from '../../types/api'

const STATUS_COLORS: Record<RunStatus, string> = {
  pending: 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  cancelled: 'bg-yellow-100 text-yellow-800',
}

export function RunListPage() {
  const navigate = useNavigate()
  const { data: runs, isLoading, error, refetch } = useRuns({ limit: 50 })
  const deleteMutation = useDeleteRun()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)

  const toggleSelect = useCallback((runId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(runId)) next.delete(runId)
      else next.add(runId)
      return next
    })
  }, [])

  const toggleSelectAll = useCallback(() => {
    if (!runs) return
    setSelected((prev) => {
      if (prev.size === runs.length) return new Set()
      return new Set(runs.map((r) => r.run_id))
    })
  }, [runs])

  const handleDeleteSelected = useCallback(async () => {
    if (selected.size === 0) return
    const confirmed = window.confirm(
      `Delete ${selected.size} run${selected.size > 1 ? 's' : ''}? This cannot be undone.`,
    )
    if (!confirmed) return

    setDeleting(true)
    try {
      for (const runId of selected) {
        await deleteMutation.mutateAsync(runId)
      }
      setSelected(new Set())
    } finally {
      setDeleting(false)
    }
  }, [selected, deleteMutation])

  const allSelected = runs != null && runs.length > 0 && selected.size === runs.length

  return (
    <div>
      <PageHeader title="Runs">
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <button
              onClick={handleDeleteSelected}
              disabled={deleting}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {deleting ? 'Deleting...' : `Delete (${selected.size})`}
            </button>
          )}
          <button
            onClick={() => navigate('/runs/new')}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            New Run
          </button>
        </div>
      </PageHeader>

      {isLoading && <LoadingSpinner />}
      {error && <ErrorMessage message={error.message} onRetry={() => refetch()} />}
      {!isLoading && !error && (!runs || runs.length === 0) && (
        <EmptyState message="No runs yet. Start one from the Scenarios page." />
      )}

      {runs && runs.length > 0 && (
        <div className="overflow-x-auto rounded-lg bg-white dark:bg-gray-800 shadow">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-gray-500 dark:text-gray-400">
                <th className="px-4 py-3 font-medium">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleSelectAll}
                    className="rounded border-gray-300 dark:border-gray-600"
                    aria-label="Select all runs"
                  />
                </th>
                <th className="px-4 py-3 font-medium">Scenario</th>
                <th className="px-4 py-3 font-medium">Seed</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Completed</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.run_id}
                  className={`cursor-pointer border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 ${
                    selected.has(run.run_id) ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                  }`}
                  onClick={() => navigate(`/runs/${run.run_id}`)}
                >
                  <td className="px-4 py-3" onClick={(e) => toggleSelect(run.run_id, e)}>
                    <input
                      type="checkbox"
                      checked={selected.has(run.run_id)}
                      readOnly
                      className="rounded border-gray-300 dark:border-gray-600"
                      aria-label={`Select run ${run.run_id}`}
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{run.scenario_name}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{run.seed}</td>
                  <td className="px-4 py-3">
                    <Badge className={STATUS_COLORS[run.status]}>{run.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{formatDate(run.created_at)}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{formatDate(run.completed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
