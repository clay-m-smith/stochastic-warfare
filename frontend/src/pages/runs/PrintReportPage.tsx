import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useRun, useRunNarrative } from '../../hooks/useRuns'
import { formatDate, formatSeconds } from '../../lib/format'
import type { RunResult } from '../../types/api'

export function PrintReportPage() {
  const { runId } = useParams<{ runId: string }>()
  const { data: run, isLoading, error } = useRun(runId ?? '')
  const { data: narrative } = useRunNarrative(runId ?? '', undefined, { enabled: !!run })

  useEffect(() => {
    if (run && narrative) {
      const timer = setTimeout(() => window.print(), 500)
      return () => clearTimeout(timer)
    }
  }, [run, narrative])

  if (!runId) return <ErrorMessage message="No run ID" />
  if (isLoading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error.message} />
  if (!run) return <ErrorMessage message="Run not found" />

  const result = run.result as unknown as RunResult | null

  return (
    <div className="mx-auto max-w-3xl p-8 print:p-0">
      <h1 className="mb-4 text-2xl font-bold text-gray-900">
        Run Report: {run.scenario_name}
      </h1>

      <table className="mb-6 w-full text-sm">
        <tbody>
          <tr className="border-b">
            <td className="py-1 font-medium text-gray-500">Run ID</td>
            <td className="py-1">{run.run_id}</td>
          </tr>
          <tr className="border-b">
            <td className="py-1 font-medium text-gray-500">Status</td>
            <td className="py-1">{run.status}</td>
          </tr>
          <tr className="border-b">
            <td className="py-1 font-medium text-gray-500">Seed</td>
            <td className="py-1">{run.seed}</td>
          </tr>
          <tr className="border-b">
            <td className="py-1 font-medium text-gray-500">Created</td>
            <td className="py-1">{formatDate(run.created_at)}</td>
          </tr>
          <tr className="border-b">
            <td className="py-1 font-medium text-gray-500">Completed</td>
            <td className="py-1">{formatDate(run.completed_at)}</td>
          </tr>
        </tbody>
      </table>

      {result && (
        <>
          <h2 className="mb-2 text-lg font-semibold">Summary</h2>
          <div className="mb-4 grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Ticks: </span>
              <span className="font-medium">{result.ticks_executed}</span>
            </div>
            <div>
              <span className="text-gray-500">Duration: </span>
              <span className="font-medium">{formatSeconds(result.duration_s)}</span>
            </div>
            <div>
              <span className="text-gray-500">Victory: </span>
              <span className="font-medium">{result.victory?.status ?? '—'}</span>
              {result.victory?.winner && (
                <span className="ml-1 text-gray-600">({result.victory.winner})</span>
              )}
            </div>
          </div>

          <h2 className="mb-2 text-lg font-semibold">Force Composition</h2>
          <table className="mb-6 w-full text-sm">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="pb-1">Side</th>
                <th className="pb-1">Total</th>
                <th className="pb-1">Active</th>
                <th className="pb-1">Destroyed</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.sides ?? {}).map(([side, data]) => (
                <tr key={side} className="border-b">
                  <td className="py-1 font-medium">{side}</td>
                  <td className="py-1">{data.total}</td>
                  <td className="py-1">{data.active}</td>
                  <td className="py-1">{data.destroyed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {narrative && narrative.narrative && (
        <>
          <h2 className="mb-2 text-lg font-semibold">Narrative</h2>
          <div className="whitespace-pre-wrap text-sm text-gray-700">
            {narrative.narrative}
          </div>
        </>
      )}
    </div>
  )
}
