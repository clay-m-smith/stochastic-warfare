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
