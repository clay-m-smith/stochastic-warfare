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
  mouseWorldX: null as number | null,
  mouseWorldY: null as number | null,
  showMorale: false,
  onToggleMorale: vi.fn(),
  showHealth: true,
  onToggleHealth: vi.fn(),
  showPosture: false,
  onTogglePosture: vi.fn(),
  showSuppression: true,
  onToggleSuppression: vi.fn(),
  showLogistics: false,
  onToggleLogistics: vi.fn(),
}

describe('MapControls overlay toggles', () => {
  it('renders all 5 overlay toggle labels', () => {
    render(<MapControls {...defaultProps} />)
    expect(screen.getByText('Morale')).toBeInTheDocument()
    expect(screen.getByText('Health')).toBeInTheDocument()
    expect(screen.getByText('Posture')).toBeInTheDocument()
    expect(screen.getByText('Suppression')).toBeInTheDocument()
    expect(screen.getByText('Logistics')).toBeInTheDocument()
  })

  it('Health toggle defaults to checked', () => {
    render(<MapControls {...defaultProps} />)
    const checkbox = screen.getByText('Health').closest('label')!.querySelector('input')!
    expect(checkbox.checked).toBe(true)
  })

  it('Posture toggle defaults to unchecked', () => {
    render(<MapControls {...defaultProps} />)
    const checkbox = screen.getByText('Posture').closest('label')!.querySelector('input')!
    expect(checkbox.checked).toBe(false)
  })

  it('calls onToggleMorale when Morale clicked', () => {
    const onToggleMorale = vi.fn()
    render(<MapControls {...defaultProps} onToggleMorale={onToggleMorale} />)
    const checkbox = screen.getByText('Morale').closest('label')!.querySelector('input')!
    fireEvent.click(checkbox)
    expect(onToggleMorale).toHaveBeenCalled()
  })

  it('calls onToggleLogistics when Logistics clicked', () => {
    const onToggleLogistics = vi.fn()
    render(<MapControls {...defaultProps} onToggleLogistics={onToggleLogistics} />)
    const checkbox = screen.getByText('Logistics').closest('label')!.querySelector('input')!
    fireEvent.click(checkbox)
    expect(onToggleLogistics).toHaveBeenCalled()
  })
})
