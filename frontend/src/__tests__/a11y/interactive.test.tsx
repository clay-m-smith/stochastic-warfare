import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PlaybackControls } from '../../components/map/PlaybackControls'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { Card } from '../../components/Card'
import { StatisticsTable } from '../../components/charts/StatisticsTable'
import { TabBar } from '../../components/TabBar'
import { renderWithProviders } from '../helpers'
import { AnalysisPage } from '../../pages/analysis/AnalysisPage'
import type { MetricStats } from '../../types/api'

const defaultPlaybackProps = {
  currentFrame: 0,
  totalFrames: 10,
  isPlaying: false,
  speed: 1 as const,
  currentTick: 0,
  elapsedTime: '00:00:00',
  totalTime: '01:00:00',
  onPlay: vi.fn(),
  onPause: vi.fn(),
  onStepForward: vi.fn(),
  onStepBackward: vi.fn(),
  onSeek: vi.fn(),
  onSetSpeed: vi.fn(),
  speedOptions: [1, 2, 5, 10] as const,
}

describe('PlaybackControls accessibility', () => {
  it('slider has aria-describedby', () => {
    render(<PlaybackControls {...defaultPlaybackProps} />)
    const slider = screen.getByLabelText('Timeline scrubber')
    expect(slider).toHaveAttribute('aria-describedby', 'playback-time-display')
  })

  it('time display has id for aria-describedby reference', () => {
    const { container } = render(<PlaybackControls {...defaultPlaybackProps} />)
    const display = container.querySelector('#playback-time-display')
    expect(display).toBeInTheDocument()
  })
})

describe('LoadingSpinner accessibility', () => {
  it('has role=status', () => {
    render(<LoadingSpinner />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('has aria-label=Loading', () => {
    render(<LoadingSpinner />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Loading')
  })

  it('SVG is aria-hidden', () => {
    const { container } = render(<LoadingSpinner />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('Card accessibility', () => {
  it('clickable card has role=button', () => {
    render(<Card onClick={vi.fn()}>Click me</Card>)
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('Enter key activates clickable card', () => {
    const onClick = vi.fn()
    render(<Card onClick={onClick}>Click me</Card>)
    fireEvent.keyDown(screen.getByRole('button'), { key: 'Enter' })
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('Space key activates clickable card', () => {
    const onClick = vi.fn()
    render(<Card onClick={onClick}>Click me</Card>)
    fireEvent.keyDown(screen.getByRole('button'), { key: ' ' })
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('non-clickable card has no button role', () => {
    render(<Card>Static content</Card>)
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('StatisticsTable accessibility', () => {
  it('all th elements have scope=col', () => {
    const metrics: Record<string, MetricStats> = {
      casualties: { mean: 5, median: 4, std: 1.2, min: 2, max: 8, p5: 2.5, p95: 7.5, n: 10 },
    }
    const { container } = render(<StatisticsTable metrics={metrics} />)
    const thElements = container.querySelectorAll('th')
    expect(thElements.length).toBe(8)
    thElements.forEach((th) => {
      expect(th).toHaveAttribute('scope', 'col')
    })
  })
})

describe('TabBar accessibility', () => {
  const tabs = [
    { id: 'batch', label: 'Batch MC' },
    { id: 'compare', label: 'A/B Compare' },
  ]

  it('has role=tablist on container', () => {
    render(<TabBar tabs={tabs} activeTab="batch" onTabChange={vi.fn()} />)
    expect(screen.getByRole('tablist')).toBeInTheDocument()
  })

  it('tab buttons have role=tab', () => {
    render(<TabBar tabs={tabs} activeTab="batch" onTabChange={vi.fn()} />)
    const tabElements = screen.getAllByRole('tab')
    expect(tabElements).toHaveLength(2)
  })

  it('active tab has aria-selected=true', () => {
    render(<TabBar tabs={tabs} activeTab="batch" onTabChange={vi.fn()} />)
    const activeTab = screen.getByRole('tab', { name: 'Batch MC' })
    expect(activeTab).toHaveAttribute('aria-selected', 'true')
    const inactiveTab = screen.getByRole('tab', { name: 'A/B Compare' })
    expect(inactiveTab).toHaveAttribute('aria-selected', 'false')
  })
})

describe('AnalysisPage accessibility', () => {
  it('has tabpanel with correct aria-labelledby', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )
    const { container } = renderWithProviders(<AnalysisPage />)
    const panel = container.querySelector('[role="tabpanel"]')
    expect(panel).toBeInTheDocument()
    expect(panel).toHaveAttribute('id', 'tabpanel-batch')
    expect(panel).toHaveAttribute('aria-labelledby', 'tab-batch')
  })
})
