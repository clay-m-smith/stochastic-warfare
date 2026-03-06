interface MapControlsProps {
  showLabels: boolean
  onToggleLabels: () => void
  showDestroyed: boolean
  onToggleDestroyed: () => void
  showEngagements: boolean
  onToggleEngagements: () => void
  showTrails: boolean
  onToggleTrails: () => void
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
  onZoomToFit,
  mouseWorldX,
  mouseWorldY,
}: MapControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded bg-white/90 px-3 py-2 text-xs shadow">
      <Toggle label="Labels" checked={showLabels} onChange={onToggleLabels} />
      <Toggle label="Destroyed" checked={showDestroyed} onChange={onToggleDestroyed} />
      <Toggle label="Engagements" checked={showEngagements} onChange={onToggleEngagements} />
      <Toggle label="Trails" checked={showTrails} onChange={onToggleTrails} />
      <button
        onClick={onZoomToFit}
        className="rounded bg-gray-200 px-2 py-1 hover:bg-gray-300"
      >
        Fit
      </button>
      {mouseWorldX != null && mouseWorldY != null && (
        <span className="ml-auto font-mono text-gray-500">
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
}: {
  label: string
  checked: boolean
  onChange: () => void
}) {
  return (
    <label className="flex cursor-pointer items-center gap-1">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="h-3 w-3"
      />
      <span>{label}</span>
    </label>
  )
}
