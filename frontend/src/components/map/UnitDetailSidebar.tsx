import type { MapUnitFrame } from '../../types/map'

const DOMAIN_NAMES: Record<number, string> = {
  0: 'Ground',
  1: 'Air',
  2: 'Naval (Surface)',
  3: 'Naval (Sub)',
  4: 'Space',
}

const STATUS_NAMES: Record<number, string> = {
  0: 'Active',
  1: 'Damaged',
  2: 'Suppressed',
  3: 'Destroyed',
  4: 'Routed',
  5: 'Surrendered',
}

const MORALE_NAMES: Record<number, string> = {
  0: 'Steady',
  1: 'Shaken',
  2: 'Broken',
  3: 'Routed',
  4: 'Surrendered',
}

const MORALE_TEXT_COLORS: Record<number, string> = {
  0: 'text-green-600 dark:text-green-400',
  1: 'text-yellow-600 dark:text-yellow-400',
  2: 'text-orange-500 dark:text-orange-400',
  3: 'text-red-600 dark:text-red-400',
  4: 'text-gray-500 dark:text-gray-400',
}

const SUPPRESSION_NAMES: Record<number, string> = {
  0: 'None',
  1: 'Light',
  2: 'Moderate',
  3: 'Heavy',
  4: 'Pinned',
}

interface UnitDetailSidebarProps {
  unit: MapUnitFrame
  onClose: () => void
}

export function UnitDetailSidebar({ unit, onClose }: UnitDetailSidebarProps) {
  return (
    <div className="w-56 rounded bg-white p-3 text-sm shadow-lg dark:bg-gray-800 dark:text-gray-200" data-testid="unit-sidebar">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold">{unit.type || unit.id}</span>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
          aria-label="Close unit detail"
        >
          x
        </button>
      </div>
      <dl className="space-y-1 text-xs">
        <Row label="ID" value={unit.id} />
        <Row label="Side" value={unit.side} />
        <Row label="Type" value={unit.type} />
        <Row label="Domain" value={DOMAIN_NAMES[unit.domain] ?? String(unit.domain)} />
        <Row label="Status" value={STATUS_NAMES[unit.status] ?? String(unit.status)} />
        <Row label="Position" value={`E ${unit.x.toFixed(0)}, N ${unit.y.toFixed(0)}`} />
        <Row label="Heading" value={`${unit.heading.toFixed(0)}\u00B0`} />
        {unit.morale != null && (
          <ColorRow
            label="Morale"
            value={MORALE_NAMES[unit.morale] ?? String(unit.morale)}
            colorClass={MORALE_TEXT_COLORS[unit.morale] ?? ''}
          />
        )}
        {unit.posture ? <Row label="Posture" value={unit.posture} /> : null}
        {unit.health != null && (
          <Row label="Health" value={`${Math.round(unit.health * 100)}%`} />
        )}
        {unit.fuel_pct != null && (
          <Row label="Fuel" value={`${Math.round(unit.fuel_pct * 100)}%`} />
        )}
        {unit.ammo_pct != null && (
          <Row label="Ammo" value={`${Math.round(unit.ammo_pct * 100)}%`} />
        )}
        {unit.suppression != null && (
          <Row label="Suppression" value={SUPPRESSION_NAMES[unit.suppression] ?? String(unit.suppression)} />
        )}
        {unit.engaged != null && (
          <Row label="Engaged" value={unit.engaged ? 'Yes' : 'No'} />
        )}
      </dl>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  )
}

function ColorRow({ label, value, colorClass }: { label: string; value: string; colorClass: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className={`font-mono ${colorClass}`}>{value}</dd>
    </div>
  )
}
