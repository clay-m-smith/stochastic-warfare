import { StatCard } from '../../components/StatCard'
import type { RunResult, SideForces } from '../../types/api'

const SIDE_COLORS: Record<string, string> = {
  blue: 'border-l-4 border-l-blue-500',
  red: 'border-l-4 border-l-red-500',
}

interface RunSummaryCardProps {
  result: RunResult
}

export function RunSummaryCard({ result }: RunSummaryCardProps) {
  const victoryStatus = result.victory?.status ?? 'unknown'
  const winner = result.victory?.winner ?? result.victory?.winning_side

  return (
    <div>
      <div
        className={`mb-4 rounded-lg p-4 text-center text-lg font-bold ${
          victoryStatus === 'decisive' || victoryStatus === 'victory'
            ? 'bg-green-100 text-green-800'
            : victoryStatus === 'draw' || victoryStatus === 'stalemate'
              ? 'bg-yellow-100 text-yellow-800'
              : 'bg-gray-100 text-gray-800'
        }`}
      >
        {winner ? `${winner.toUpperCase()} ${victoryStatus}` : victoryStatus.toUpperCase()}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Object.entries(result.sides).map(([side, forces]) => {
          const sf = forces as SideForces
          return (
            <div
              key={side}
              className={`rounded-lg bg-white p-4 shadow ${SIDE_COLORS[side] ?? 'border-l-4 border-l-gray-400'}`}
            >
              <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">{side}</h3>
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
