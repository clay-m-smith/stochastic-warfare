interface MapControlsProps {
  showLabels: boolean
  onToggleLabels: () => void
  showDestroyed: boolean
  onToggleDestroyed: () => void
  showEngagements: boolean
  onToggleEngagements: () => void
  showTrails: boolean
  onToggleTrails: () => void
  showSensors: boolean
  onToggleSensors: () => void
  showFow: boolean
  onToggleFow: () => void
  fowSide: string
  onChangeFowSide: (side: string) => void
  availableSides: string[]
  fowAvailable: boolean
  onZoomToFit: () => void
  mouseWorldX: number | null
  mouseWorldY: number | null
}

export function MapControls({
  showLabels,
  onToggleLabels,
  showDestroyed,
  onToggleDestroyed,
  showEngagements,
  onToggleEngagements,
  showTrails,
  onToggleTrails,
  showSensors,
  onToggleSensors,
  showFow,
  onToggleFow,
  fowSide,
  onChangeFowSide,
  availableSides,
  fowAvailable,
  onZoomToFit,
  mouseWorldX,
  mouseWorldY,
}: MapControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded bg-white/90 px-3 py-2 text-xs shadow dark:bg-gray-800/90 dark:text-gray-200">
      <Toggle label="Labels" checked={showLabels} onChange={onToggleLabels} />
      <Toggle label="Destroyed" checked={showDestroyed} onChange={onToggleDestroyed} />
      <Toggle label="Engagements" checked={showEngagements} onChange={onToggleEngagements} />
      <Toggle label="Trails" checked={showTrails} onChange={onToggleTrails} />
      <Toggle label="Sensors" checked={showSensors} onChange={onToggleSensors} />
      <Toggle
        label="FOW"
        checked={showFow}
        onChange={onToggleFow}
        disabled={!fowAvailable}
        title={fowAvailable ? 'Fog of War filter' : 'No detection data available'}
      />
      {showFow && fowAvailable && availableSides.length > 0 && (
        <select
          value={fowSide}
          onChange={(e) => onChangeFowSide(e.target.value)}
          className="rounded border border-gray-300 px-1 py-0.5 text-xs dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
          aria-label="FOW side"
        >
          {availableSides.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      )}
      <button
        onClick={onZoomToFit}
        className="rounded bg-gray-200 px-2 py-1 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600"
      >
        Fit
      </button>
      {mouseWorldX != null && mouseWorldY != null && (
        <span className="ml-auto font-mono text-gray-500 dark:text-gray-400">
          E {mouseWorldX.toFixed(0)} N {mouseWorldY.toFixed(0)}
        </span>
      )}
    </div>
  )
}

function Toggle({
  label,
  checked,
  onChange,
  disabled,
  title,
}: {
  label: string
  checked: boolean
  onChange: () => void
  disabled?: boolean
  title?: string
}) {
  return (
    <label
      className={`flex cursor-pointer items-center gap-1 ${disabled ? 'opacity-50' : ''}`}
      title={title}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        className="h-3 w-3"
      />
      <span>{label}</span>
    </label>
  )
}
