import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { domainBadgeColor, domainDisplayName } from '../../lib/domain'
import { eraBadgeColor, eraDisplayName } from '../../lib/era'
import type { UnitSummary } from '../../types/api'

interface UnitCardProps {
  unit: UnitSummary
  onClick: () => void
}

export function UnitCard({ unit, onClick }: UnitCardProps) {
  return (
    <Card onClick={onClick}>
      <div className="mb-2 flex items-start justify-between">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100">{unit.display_name || unit.unit_type}</h3>
        <Badge className={eraBadgeColor(unit.era)}>{eraDisplayName(unit.era)}</Badge>
      </div>
      <div className="mb-2 flex flex-wrap gap-1">
        <Badge className={domainBadgeColor(unit.domain)}>{domainDisplayName(unit.domain)}</Badge>
        {unit.category && <Badge className="bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300">{unit.category}</Badge>}
      </div>
      <div className="flex gap-4 text-xs text-gray-500 dark:text-gray-400">
        {unit.max_speed > 0 && <span>Speed: {unit.max_speed} m/s</span>}
        {unit.crew_size > 0 && <span>Crew: {unit.crew_size}</span>}
      </div>
    </Card>
  )
}
