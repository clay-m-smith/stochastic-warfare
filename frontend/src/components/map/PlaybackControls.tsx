import type { PlaybackSpeed } from '../../hooks/usePlayback'

interface PlaybackControlsProps {
  currentFrame: number
  totalFrames: number
  isPlaying: boolean
  speed: PlaybackSpeed
  currentTick: number | null
  elapsedTime?: string | null
  totalTime?: string | null
  onPlay: () => void
  onPause: () => void
  onStepForward: () => void
  onStepBackward: () => void
  onSeek: (frame: number) => void
  onSetSpeed: (speed: PlaybackSpeed) => void
  speedOptions: readonly PlaybackSpeed[]
}

export function PlaybackControls({
  currentFrame,
  totalFrames,
  isPlaying,
  speed,
  currentTick,
  elapsedTime,
  totalTime,
  onPlay,
  onPause,
  onStepForward,
  onStepBackward,
  onSeek,
  onSetSpeed,
  speedOptions,
}: PlaybackControlsProps) {
  return (
    <div className="flex items-center gap-2 rounded bg-white/90 px-3 py-2 text-xs shadow dark:bg-gray-800/90 dark:text-gray-200">
      <button
        onClick={onStepBackward}
        disabled={currentFrame <= 0}
        className="rounded px-1.5 py-0.5 hover:bg-gray-200 disabled:opacity-30 dark:hover:bg-gray-700"
        aria-label="Step backward"
      >
        {'<<'}
      </button>

      <button
        onClick={isPlaying ? onPause : onPlay}
        disabled={totalFrames <= 1}
        className="rounded bg-gray-200 px-2 py-0.5 font-bold hover:bg-gray-300 disabled:opacity-30 dark:bg-gray-700 dark:hover:bg-gray-600"
        aria-label={isPlaying ? 'Pause' : 'Play'}
      >
        {isPlaying ? '||' : '\u25B6'}
      </button>

      <button
        onClick={onStepForward}
        disabled={currentFrame >= totalFrames - 1}
        className="rounded px-1.5 py-0.5 hover:bg-gray-200 disabled:opacity-30 dark:hover:bg-gray-700"
        aria-label="Step forward"
      >
        {'>>'}
      </button>

      <input
        type="range"
        min={0}
        max={Math.max(0, totalFrames - 1)}
        value={currentFrame}
        onChange={(e) => onSeek(Number(e.target.value))}
        className="mx-2 flex-1"
        aria-label="Timeline scrubber"
      />

      <select
        value={speed}
        onChange={(e) => onSetSpeed(Number(e.target.value) as PlaybackSpeed)}
        className="rounded border px-1 py-0.5 text-xs dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
        aria-label="Playback speed"
      >
        {speedOptions.map((s) => (
          <option key={s} value={s}>
            {s}x
          </option>
        ))}
      </select>

      <span className="ml-1 font-mono text-gray-500 dark:text-gray-400">
        {elapsedTime && totalTime
          ? `${elapsedTime} / ${totalTime}`
          : currentTick != null
            ? `Tick ${currentTick}`
            : ''}{' '}
        — Frame {currentFrame + 1}/{totalFrames}
      </span>
    </div>
  )
}
