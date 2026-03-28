import { LAND_COVER_COLORS, LAND_COVER_NAMES } from '../../lib/terrain'
import { getSideColor, formatSideName } from '../../lib/sideColors'
import type { OverlayOptions } from '../../lib/unitRendering'

const TERRAIN_ENTRIES = [0, 1, 3, 6, 9, 11, 14] // Representative subset

const DOMAIN_SHAPES = [
  { domain: 'Ground', shape: 'rectangle' },
  { domain: 'Air', shape: 'triangle' },
  { domain: 'Naval', shape: 'diamond' },
]

interface MapLegendProps {
  sides?: string[]
  overlays?: OverlayOptions
}

export function MapLegend({ sides, overlays }: MapLegendProps) {
  const displaySides = sides && sides.length > 0 ? sides : ['blue', 'red']
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
          {displaySides.map((side) => (
            <div key={side} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm border border-gray-300 dark:border-gray-600"
                style={{ backgroundColor: getSideColor(side) }}
              />
              <span className="capitalize">{formatSideName(side)}</span>
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

      <div>
        <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Status</div>
        <div className="flex gap-3">
          <div className="flex items-center gap-1">
            <StatusIcon type="active" />
            <span>Active</span>
          </div>
          <div className="flex items-center gap-1">
            <StatusIcon type="disabled" />
            <span>Disabled</span>
          </div>
          <div className="flex items-center gap-1">
            <StatusIcon type="destroyed" />
            <span>Destroyed</span>
          </div>
        </div>
      </div>

      {overlays?.showMorale && (
        <div>
          <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Morale</div>
          <div className="flex flex-wrap gap-2">
            {[
              { label: 'Steady', color: '#666666' },
              { label: 'Shaken', color: '#DDDD00' },
              { label: 'Broken', color: '#FF8800' },
              { label: 'Routed', color: '#FF2222' },
              { label: 'Surrendered', color: '#999999' },
            ].map(({ label, color }) => (
              <div key={label} className="flex items-center gap-1">
                <span
                  className="inline-block h-3 w-3 rounded-sm border border-gray-300 dark:border-gray-600"
                  style={{ backgroundColor: color }}
                />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {overlays?.showHealth && (
        <div>
          <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Health</div>
          <div className="flex items-center gap-2">
            <svg width="60" height="8" aria-hidden="true">
              <rect x="0" y="0" width="60" height="6" fill="#333" rx="1" />
              <rect x="0" y="0" width="20" height="6" fill="#FF2222" rx="1" />
              <rect x="20" y="0" width="20" height="6" fill="#DDDD00" />
              <rect x="40" y="0" width="20" height="6" fill="#22CC22" rx="1" />
            </svg>
            <span>Low...Full</span>
          </div>
        </div>
      )}

      {overlays?.showPosture && (
        <div>
          <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Posture</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
            {[
              { abbrev: 'D', label: 'Defensive' },
              { abbrev: 'F', label: 'Fortified' },
              { abbrev: 'A', label: 'Assault' },
              { abbrev: 'S', label: 'On Station' },
              { abbrev: 'B', label: 'Battle Stations' },
              { abbrev: 'H', label: 'Halted' },
            ].map(({ abbrev, label }) => (
              <div key={label} className="flex items-center gap-1">
                <span className="inline-block w-3 text-center font-mono font-bold">{abbrev}</span>
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {overlays?.showSuppression && (
        <div>
          <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Suppression</div>
          <div className="flex items-center gap-1">
            {[
              { label: 'None', opacity: 1.0 },
              { label: 'Light', opacity: 0.85 },
              { label: 'Mod', opacity: 0.65 },
              { label: 'Heavy', opacity: 0.45 },
              { label: 'Pinned', opacity: 0.30 },
            ].map(({ label, opacity }) => (
              <div key={label} className="flex flex-col items-center">
                <span
                  className="inline-block h-3 w-3 rounded-sm border border-gray-300 dark:border-gray-600"
                  style={{ backgroundColor: '#666', opacity }}
                />
                <span className="text-[8px]">{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {overlays?.showLogistics && (
        <div>
          <div className="mb-1 font-semibold text-gray-700 dark:text-gray-300">Logistics</div>
          <div className="flex gap-3">
            <div className="flex items-center gap-1">
              <span className="inline-block h-3 w-2 rounded-sm" style={{ backgroundColor: '#4488FF' }} />
              <span>Fuel</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="inline-block h-3 w-2 rounded-sm" style={{ backgroundColor: '#FF8800' }} />
              <span>Ammo</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="inline-block h-3 w-2 rounded-sm" style={{ backgroundColor: '#FF2222' }} />
              <span>Low (&lt;20%)</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatusIcon({ type }: { type: 'active' | 'disabled' | 'destroyed' }) {
  const size = 12
  const opacity = type === 'destroyed' ? 0.35 : type === 'disabled' ? 0.55 : 1.0
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden="true">
      <rect x="1" y="1" width="10" height="10" fill="#666" stroke="#000" strokeWidth="0.5" opacity={opacity} />
      {type === 'disabled' && (
        <line x1="10" y1="2" x2="2" y2="10" stroke="#FF8800" strokeWidth="2" />
      )}
      {type === 'destroyed' && (
        <>
          <line x1="2" y1="2" x2="10" y2="10" stroke="#FF0000" strokeWidth="2" />
          <line x1="10" y1="2" x2="2" y2="10" stroke="#FF0000" strokeWidth="2" />
        </>
      )}
    </svg>
  )
}

function DomainIcon({ shape }: { shape: string }) {
  const size = 12
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden="true">
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
