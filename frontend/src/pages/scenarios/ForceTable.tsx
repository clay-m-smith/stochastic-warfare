import type { ForceSummaryEntry } from '../../types/api'

interface ForceTableProps {
  forceSummary: Record<string, ForceSummaryEntry>
}

export function ForceTable({ forceSummary }: ForceTableProps) {
  const sides = Object.entries(forceSummary)
  if (sides.length === 0) return <p className="text-sm text-gray-500">No force data available.</p>

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500">
            <th className="pb-2 pr-4 font-medium">Side</th>
            <th className="pb-2 pr-4 font-medium">Units</th>
            <th className="pb-2 font-medium">Unit Types</th>
          </tr>
        </thead>
        <tbody>
          {sides.map(([side, data]) => (
            <tr key={side} className="border-b border-gray-100">
              <td className="py-2 pr-4 font-medium text-gray-900">{side}</td>
              <td className="py-2 pr-4 text-gray-700">{data.unit_count}</td>
              <td className="py-2 text-gray-600">{data.unit_types.join(', ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
