interface ProgressBarProps {
  value: number
  max: number
  label?: string
}

export function ProgressBar({ value, max, label }: ProgressBarProps) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div>
      {label && <div className="mb-1 text-sm text-gray-600 dark:text-gray-400">{label}</div>}
      <div className="h-4 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={value}
          aria-valuemin={0}
          aria-valuemax={max}
        />
      </div>
      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {value} / {max} ({pct.toFixed(0)}%)
      </div>
    </div>
  )
}
