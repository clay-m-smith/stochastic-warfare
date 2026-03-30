import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import type { WeaponSummary } from '../../types/api'

interface WeaponCardProps {
  weapon: WeaponSummary
  onClick: () => void
}

export function WeaponCard({ weapon, onClick }: WeaponCardProps) {
  return (
    <Card onClick={onClick}>
      <h3 className="mb-2 font-semibold text-gray-900 dark:text-gray-100">
        {weapon.display_name || weapon.weapon_id}
      </h3>
      <div className="mb-2 flex flex-wrap gap-1">
        {weapon.category && (
          <Badge className="bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
            {weapon.category}
          </Badge>
        )}
      </div>
      <div className="flex gap-4 text-xs text-gray-500 dark:text-gray-400">
        {weapon.max_range_m > 0 && <span>Range: {weapon.max_range_m.toLocaleString()} m</span>}
        {weapon.caliber_mm > 0 && <span>Caliber: {weapon.caliber_mm} mm</span>}
      </div>
    </Card>
  )
}
