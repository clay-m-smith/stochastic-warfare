import { useNavigate } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { eraBadgeColor, eraDisplayName } from '../../lib/era'
import { formatDuration } from '../../lib/format'
import type { ScenarioSummary } from '../../types/api'

interface ScenarioCardProps {
  scenario: ScenarioSummary
}

export function ScenarioCard({ scenario }: ScenarioCardProps) {
  const navigate = useNavigate()

  return (
    <Card onClick={() => navigate(`/scenarios/${scenario.name}`)}>
      <div className="mb-2 flex items-start justify-between">
        <h3 className="font-semibold text-gray-900">{scenario.display_name || scenario.name}</h3>
        <Badge className={eraBadgeColor(scenario.era)}>{eraDisplayName(scenario.era)}</Badge>
      </div>

      <div className="mb-3 flex flex-wrap gap-2 text-xs text-gray-500">
        {scenario.terrain_type && <span>{scenario.terrain_type}</span>}
        {scenario.duration_hours > 0 && (
          <>
            <span>&middot;</span>
            <span>{formatDuration(scenario.duration_hours)}</span>
          </>
        )}
        <span>&middot;</span>
        <span>{scenario.sides.length} sides</span>
      </div>

      <div className="flex flex-wrap gap-1">
        {scenario.sides.map((side) => (
          <Badge key={side} className="bg-gray-200 text-gray-700">
            {side}
          </Badge>
        ))}
      </div>

      {(scenario.has_ew || scenario.has_cbrn || scenario.has_escalation || scenario.has_schools) && (
        <div className="mt-2 flex flex-wrap gap-1">
          {scenario.has_ew && <Badge className="bg-yellow-100 text-yellow-800">EW</Badge>}
          {scenario.has_cbrn && <Badge className="bg-orange-100 text-orange-800">CBRN</Badge>}
          {scenario.has_escalation && <Badge className="bg-red-100 text-red-800">Escalation</Badge>}
          {scenario.has_schools && <Badge className="bg-purple-100 text-purple-800">Schools</Badge>}
        </div>
      )}
    </Card>
  )
}
