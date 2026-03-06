import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PlaybackControls } from '../../../components/map/PlaybackControls'

const defaultProps = {
  currentFrame: 5,
  totalFrames: 100,
  isPlaying: false,
  speed: 1 as const,
  currentTick: 50,
  onPlay: vi.fn(),
  onPause: vi.fn(),
  onStepForward: vi.fn(),
  onStepBackward: vi.fn(),
  onSeek: vi.fn(),
  onSetSpeed: vi.fn(),
  speedOptions: [1, 2, 5, 10] as const,
}

describe('PlaybackControls', () => {
  it('shows frame info', () => {
    render(<PlaybackControls {...defaultProps} />)
    expect(screen.getByText(/Frame 6\/100/)).toBeInTheDocument()
    expect(screen.getByText(/Tick 50/)).toBeInTheDocument()
  })

  it('shows Play button when not playing', () => {
    render(<PlaybackControls {...defaultProps} />)
    expect(screen.getByLabelText('Play')).toBeInTheDocument()
  })

  it('shows Pause button when playing', () => {
    render(<PlaybackControls {...defaultProps} isPlaying={true} />)
    expect(screen.getByLabelText('Pause')).toBeInTheDocument()
  })

  it('calls onPlay when play clicked', () => {
    const onPlay = vi.fn()
    render(<PlaybackControls {...defaultProps} onPlay={onPlay} />)
    fireEvent.click(screen.getByLabelText('Play'))
    expect(onPlay).toHaveBeenCalled()
  })

  it('calls onStepForward when >> clicked', () => {
    const onStepForward = vi.fn()
    render(<PlaybackControls {...defaultProps} onStepForward={onStepForward} />)
    fireEvent.click(screen.getByLabelText('Step forward'))
    expect(onStepForward).toHaveBeenCalled()
  })

  it('calls onStepBackward when << clicked', () => {
    const onStepBackward = vi.fn()
    render(<PlaybackControls {...defaultProps} onStepBackward={onStepBackward} />)
    fireEvent.click(screen.getByLabelText('Step backward'))
    expect(onStepBackward).toHaveBeenCalled()
  })

  it('has speed selector with options', () => {
    render(<PlaybackControls {...defaultProps} />)
    const select = screen.getByLabelText('Playback speed')
    expect(select).toBeInTheDocument()
    expect(select.querySelectorAll('option')).toHaveLength(4)
  })

  it('has timeline scrubber', () => {
    render(<PlaybackControls {...defaultProps} />)
    const scrubber = screen.getByLabelText('Timeline scrubber') as HTMLInputElement
    expect(scrubber.value).toBe('5')
    expect(scrubber.max).toBe('99') // totalFrames - 1
  })
})
