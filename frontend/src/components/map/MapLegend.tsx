import { LAND_COVER_COLORS, LAND_COVER_NAMES } from '../../lib/terrain'
import { SIDE_COLORS } from '../../lib/unitRendering'

const TERRAIN_ENTRIES = [0, 1, 3, 6, 9, 11, 14] // Representative subset

const DOMAIN_SHAPES = [
  { domain: 'Ground', shape: 'rectangle' },
  { domain: 'Air', shape: 'triangle' },
  { domain: 'Naval', shape: 'diamond' },
]

export function MapLegend() {
  return (
    <div className="space-y-3 rounded bg-white/90 p-3 text-xs shadow dark:bg-gray-800/90 dark:text-gray-200">
      <div>
        <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Terrain</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
          {TERRAIN_ENTRIES.map((code) => (
            <div key={code} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 border border-gray-300 dark:border-gray-600"
                style={{ backgroundColor: LAND_COVER_COLORS[code] }}
              />
              <span>{LAND_COVER_NAMES[code]}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Sides</div>
        <div className="flex gap-3">
          {Object.entries(SIDE_COLORS).map(([side, color]) => (
            <div key={side} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm border border-gray-300 dark:border-gray-600"
                style={{ backgroundColor: color }}
              />
              <span className="capitalize">{side}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Unit Shapes</div>
        <div className="flex gap-3">
          {DOMAIN_SHAPES.map(({ domain, shape }) => (
            <div key={domain} className="flex items-center gap-1">
              <DomainIcon shape={shape} />
              <span>{domain}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function DomainIcon({ shape }: { shape: string }) {
  const size = 12
  return (
    <svg width={size} height={size} viewBox="0 0 12 12">
      {shape === 'rectangle' && (
        <rect x="1" y="1" width="10" height="10" fill="#666" stroke="#000" strokeWidth="0.5" />
      )}
      {shape === 'triangle' && (
        <polygon points="6,1 1,11 11,11" fill="#666" stroke="#000" strokeWidth="0.5" />
      )}
      {shape === 'diamond' && (
        <polygon points="6,1 11,6 6,11 1,6" fill="#666" stroke="#000" strokeWidth="0.5" />
      )}
    </svg>
  )
}
