import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MapControls } from '../../../components/map/MapControls'

const defaultProps = {
  showLabels: false,
  onToggleLabels: vi.fn(),
  showDestroyed: true,
  onToggleDestroyed: vi.fn(),
  showEngagements: true,
  onToggleEngagements: vi.fn(),
  showTrails: false,
  onToggleTrails: vi.fn(),
  showSensors: false,
  onToggleSensors: vi.fn(),
  showFow: false,
  onToggleFow: vi.fn(),
  fowSide: 'blue',
  onChangeFowSide: vi.fn(),
  availableSides: ['blue', 'red'],
  fowAvailable: true,
  onZoomToFit: vi.fn(),
  mouseWorldX: 1234.5,
  mouseWorldY: 5678.9,
}

describe('MapControls', () => {
  it('renders toggle checkboxes', () => {
    render(<MapControls {...defaultProps} />)
    expect(screen.getByText('Labels')).toBeInTheDocument()
    expect(screen.getByText('Destroyed')).toBeInTheDocument()
    expect(screen.getByText('Engagements')).toBeInTheDocument()
    expect(screen.getByText('Trails')).toBeInTheDocument()
    expect(screen.getByText('Sensors')).toBeInTheDocument()
    expect(screen.getByText('FOW')).toBeInTheDocument()
  })

  it('renders Fit button', () => {
    render(<MapControls {...defaultProps} />)
    expect(screen.getByText('Fit')).toBeInTheDocument()
  })

  it('calls onZoomToFit when Fit clicked', () => {
    const onZoomToFit = vi.fn()
    render(<MapControls {...defaultProps} onZoomToFit={onZoomToFit} />)
    fireEvent.click(screen.getByText('Fit'))
    expect(onZoomToFit).toHaveBeenCalled()
  })

  it('displays mouse world coordinates', () => {
    render(<MapControls {...defaultProps} />)
    expect(screen.getByText(/E 1235/)).toBeInTheDocument()
    expect(screen.getByText(/N 5679/)).toBeInTheDocument()
  })

  it('hides coordinates when null', () => {
    render(<MapControls {...defaultProps} mouseWorldX={null} mouseWorldY={null} />)
    expect(screen.queryByText(/^E /)).not.toBeInTheDocument()
  })

  it('calls toggle callbacks', () => {
    const onToggleLabels = vi.fn()
    render(<MapControls {...defaultProps} onToggleLabels={onToggleLabels} />)
    const checkbox = screen.getByText('Labels').closest('label')!.querySelector('input')!
    fireEvent.click(checkbox)
    expect(onToggleLabels).toHaveBeenCalled()
  })
})
