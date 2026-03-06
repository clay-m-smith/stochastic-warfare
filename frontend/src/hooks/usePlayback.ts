import { useState, useCallback, useRef, useEffect } from 'react'

const SPEED_OPTIONS = [1, 2, 5, 10] as const
export type PlaybackSpeed = (typeof SPEED_OPTIONS)[number]

export function usePlayback(totalFrames: number) {
  const [currentFrame, setCurrentFrame] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState<PlaybackSpeed>(1)
  const rafRef = useRef<number | null>(null)
  const lastTimeRef = useRef<number>(0)
  const frameIntervalMs = 1000 / 30 // base 30fps

  const play = useCallback(() => {
    if (totalFrames <= 1) return
    setIsPlaying(true)
  }, [totalFrames])

  const pause = useCallback(() => {
    setIsPlaying(false)
  }, [])

  const stepForward = useCallback(() => {
    setIsPlaying(false)
    setCurrentFrame((prev) => Math.min(prev + 1, totalFrames - 1))
  }, [totalFrames])

  const stepBackward = useCallback(() => {
    setIsPlaying(false)
    setCurrentFrame((prev) => Math.max(prev - 1, 0))
  }, [])

  const seekTo = useCallback(
    (frame: number) => {
      setCurrentFrame(Math.max(0, Math.min(frame, totalFrames - 1)))
    },
    [totalFrames],
  )

  const changeSpeed = useCallback((newSpeed: PlaybackSpeed) => {
    setSpeed(newSpeed)
  }, [])

  // Animation loop
  useEffect(() => {
    if (!isPlaying || totalFrames <= 1) return

    const tick = (time: number) => {
      const elapsed = time - lastTimeRef.current
      const interval = frameIntervalMs / speed
      if (elapsed >= interval) {
        lastTimeRef.current = time
        setCurrentFrame((prev) => {
          if (prev >= totalFrames - 1) {
            setIsPlaying(false)
            return prev
          }
          return prev + 1
        })
      }
      rafRef.current = requestAnimationFrame(tick)
    }

    lastTimeRef.current = performance.now()
    rafRef.current = requestAnimationFrame(tick)

    return () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current)
      }
    }
  }, [isPlaying, totalFrames, speed, frameIntervalMs])

  return {
    currentFrame,
    isPlaying,
    speed,
    play,
    pause,
    stepForward,
    stepBackward,
    seekTo,
    setSpeed: changeSpeed,
    speedOptions: SPEED_OPTIONS,
  }
}
