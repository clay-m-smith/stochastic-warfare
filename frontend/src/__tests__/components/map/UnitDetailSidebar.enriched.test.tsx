import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { UnitDetailSidebar } from '../../../components/map/UnitDetailSidebar'
import type { MapUnitFrame } from '../../../types/map'

function makeUnit(overrides: Partial<MapUnitFrame> = {}): MapUnitFrame {
  return {
    id: 'u-123',
    side: 'blue',
    x: 1234.5,
    y: 5678.9,
    domain: 0,
    status: 0,
    heading: 90,
    type: 'm1_abrams',
    ...overrides,
  }
}

describe('UnitDetailSidebar enriched fields', () => {
  it('displays morale state name', () => {
    const unit = makeUnit({ morale: 2 })
    render(<UnitDetailSidebar unit={unit} onClose={vi.fn()} />)
    expect(screen.getByText('Broken')).toBeInTheDocument()
  })

  it('displays posture string', () => {
    const unit = makeUnit({ posture: 'DEFENSIVE' })
    render(<UnitDetailSidebar unit={unit} onClose={vi.fn()} />)
    expect(screen.getByText('DEFENSIVE')).toBeInTheDocument()
  })

  it('displays health as percentage', () => {
    const unit = makeUnit({ health: 0.75 })
    render(<UnitDetailSidebar unit={unit} onClose={vi.fn()} />)
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('displays fuel and ammo percentages', () => {
    const unit = makeUnit({ fuel_pct: 0.5, ammo_pct: 0.3 })
    render(<UnitDetailSidebar unit={unit} onClose={vi.fn()} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('30%')).toBeInTheDocument()
  })

  it('displays suppression level name', () => {
    const unit = makeUnit({ suppression: 3 })
    render(<UnitDetailSidebar unit={unit} onClose={vi.fn()} />)
    expect(screen.getByText('Heavy')).toBeInTheDocument()
  })

  it('displays engaged status', () => {
    const unit = makeUnit({ engaged: true })
    render(<UnitDetailSidebar unit={unit} onClose={vi.fn()} />)
    expect(screen.getByText('Yes')).toBeInTheDocument()
  })

  it('handles missing enriched fields gracefully', () => {
    const unit = makeUnit() // no enriched fields
    render(<UnitDetailSidebar unit={unit} onClose={vi.fn()} />)
    // Should render without crashing, and not show enriched rows
    expect(screen.getAllByText('m1_abrams').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('Morale')).not.toBeInTheDocument()
    expect(screen.queryByText('Suppression')).not.toBeInTheDocument()
  })
})
