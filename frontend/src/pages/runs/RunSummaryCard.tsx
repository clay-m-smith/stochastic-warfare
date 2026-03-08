import { StatCard } from '../../components/StatCard'
import { getSideBorderClass, formatSideName } from '../../lib/sideColors'
import type { RunResult, SideForces } from '../../types/api'

interface RunSummaryCardProps {
  result: RunResult
}

export function RunSummaryCard({ result }: RunSummaryCardProps) {
  const victoryStatus = result.victory?.status ?? 'unknown'
  const winner = result.victory?.winner

  return (
    <div>
      <div
        className={`mb-4 rounded-lg p-4 text-center ${
          victoryStatus === 'decisive' || victoryStatus === 'victory'
            ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-400'
            : victoryStatus === 'draw' || victoryStatus === 'stalemate'
              ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-400'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
        }`}
      >
        <div className="text-lg font-bold">
          {winner ? `${winner.toUpperCase()} — ${victoryStatus.charAt(0).toUpperCase() + victoryStatus.slice(1)} Victory` : victoryStatus.toUpperCase()}
        </div>
        {result.victory?.message && (
          <div className="mt-1 text-sm opacity-80">{result.victory.message}</div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Object.entries(result.sides).map(([side, forces]) => {
          const sf = forces as SideForces
          return (
            <div
              key={side}
              className={`rounded-lg bg-white dark:bg-gray-800 p-4 shadow ${getSideBorderClass(side)}`}
            >
              <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500 dark:text-gray-400">{formatSideName(side)}</h3>
              <div className="grid grid-cols-3 gap-2">
                <StatCard label="Total" value={sf.total} />
                <StatCard label="Active" value={sf.active} />
                <StatCard label="Destroyed" value={sf.destroyed} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
