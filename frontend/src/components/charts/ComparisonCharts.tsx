import type { CompareResult } from '../../types/analysis'
import { PlotlyChart } from './PlotlyChart'

interface ComparisonChartsProps {
  result: CompareResult
  labelA: string
  labelB: string
  className?: string
}

function ProvenanceCard({
  label,
  batch,
}: {
  label: string
  batch: CompareResult['batch_a']
}) {
  const runtime = batch.runs[0]?.runtime_provenance
  if (!runtime) {
    return <div className="text-red-600">Missing runtime provenance for {label}</div>
  }
  const revision = runtime.code_revision
  const revisionLabel = `${revision.commit}${revision.dirty ? ' (dirty)' : ' (clean)'}`
  return (
    <div className="rounded border border-gray-200 p-3 dark:border-gray-700">
      <div className="font-medium text-gray-900 dark:text-gray-100">{label} provenance</div>
      <dl className="mt-2 grid gap-1 break-all text-xs text-gray-600 dark:text-gray-400">
        <div><dt className="inline font-medium">Code revision: </dt><dd className="inline">{revisionLabel}</dd></div>
        <div><dt className="inline font-medium">Source SHA-256: </dt><dd className="inline">{batch.source_fingerprint}</dd></div>
        <div><dt className="inline font-medium">Config SHA-256: </dt><dd className="inline">{batch.config_fingerprint}</dd></div>
        <div><dt className="inline font-medium">Data revision: </dt><dd className="inline">{runtime.data_revision}</dd></div>
        <div><dt className="inline font-medium">Catalog revision: </dt><dd className="inline">{runtime.catalog_revision}</dd></div>
        <div><dt className="inline font-medium">Doctrine assignment: </dt><dd className="inline">{runtime.doctrine_assignment_fingerprint}</dd></div>
        <div><dt className="inline font-medium">Initial loadout topology: </dt><dd className="inline">{runtime.loaded_roster_loadout_fingerprint}</dd></div>
        <div><dt className="inline font-medium">Final loadout topology: </dt><dd className="inline">{runtime.final_roster_loadout_fingerprint}</dd></div>
      </dl>
    </div>
  )
}

export function ComparisonCharts({ result, labelA, labelB, className }: ComparisonChartsProps) {
  const metrics = result.metrics ?? []

  if (metrics.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400 dark:text-gray-500">No comparison data available</div>
  }

  const metricNames = metrics.map((m) => m.metric)
  const meansA = metrics.map((m) => m.mean_a)
  const meansB = metrics.map((m) => m.mean_b)

  return (
    <div className={className}>
      <PlotlyChart
        data={[
          {
            x: metricNames,
            y: meansA,
            name: labelA,
            type: 'bar' as const,
            marker: { color: '#3b82f6' },
            error_y: { type: 'data' as const, array: metrics.map((m) => m.std_a), visible: true },
          },
          {
            x: metricNames,
            y: meansB,
            name: labelB,
            type: 'bar' as const,
            marker: { color: '#ef4444' },
            error_y: { type: 'data' as const, array: metrics.map((m) => m.std_b), visible: true },
          },
        ]}
        layout={{
          title: { text: `Paired comparison: ${labelA} vs ${labelB}` },
          barmode: 'group',
          height: 400,
        }}
      />

      <div className="mt-4 overflow-x-auto rounded-lg bg-white dark:bg-gray-800 shadow">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-gray-500 dark:text-gray-400">
              <th className="px-4 py-3 font-medium">Metric</th>
              <th className="px-4 py-3 font-medium">{labelA} (mean +/- std)</th>
              <th className="px-4 py-3 font-medium">{labelB} (mean +/- std)</th>
              <th className="px-4 py-3 font-medium">Direction / paired mean / median difference</th>
              <th className="px-4 py-3 font-medium">Positive / negative / tied</th>
              <th className="px-4 py-3 font-medium">Paired superiority</th>
              <th className="px-4 py-3 font-medium">Raw p / Holm-adjusted p</th>
              <th className="px-4 py-3 font-medium">Family-wise significant</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.metric} className="border-b border-gray-100 dark:border-gray-700">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{m.metric}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{m.mean_a.toFixed(2)} +/- {m.std_a.toFixed(2)}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{m.mean_b.toFixed(2)} +/- {m.std_b.toFixed(2)}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                  {m.mean_paired_difference > 0
                    ? `${labelB} higher`
                    : m.mean_paired_difference < 0
                      ? `${labelA} higher`
                      : 'no mean difference'}
                  {' / '}
                  mean {m.mean_paired_difference.toFixed(3)}
                  {' / '}
                  median {m.median_paired_difference.toFixed(3)}
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                  {m.positive} / {m.negative} / {m.tied}
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                  {m.paired_superiority.toFixed(3)}
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                  {m.raw_p_value.toFixed(4)} / {m.holm_adjusted_p_value.toFixed(4)}
                </td>
                <td className={`px-4 py-3 ${m.family_wise_significant ? 'font-semibold text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'}`}>
                  {m.family_wise_significant ? 'yes' : 'no'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div
        aria-label="Comparison raw vectors and provenance"
        className="mt-4 rounded-lg bg-white p-4 shadow dark:bg-gray-800"
      >
        <div className="text-sm text-gray-700 dark:text-gray-300">
          Common seeds: {result.seeds.join(', ')}
        </div>
        <div className="mt-3 grid gap-2 text-xs text-gray-600 dark:text-gray-400">
          {result.ordered_metrics.map((metric) => {
            const valuesA = result.raw_a[metric]
            const valuesB = result.raw_b[metric]
            return (
              <div key={metric}>
                <div>{labelA} raw {metric}: {valuesA ? JSON.stringify(valuesA) : 'Missing raw vector'}</div>
                <div>{labelB} raw {metric}: {valuesB ? JSON.stringify(valuesB) : 'Missing raw vector'}</div>
              </div>
            )
          })}
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <ProvenanceCard label={labelA} batch={result.batch_a} />
          <ProvenanceCard label={labelB} batch={result.batch_b} />
        </div>
      </div>
    </div>
  )
}
