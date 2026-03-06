import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { UnitDetailSidebar } from '../../../components/map/UnitDetailSidebar'
import type { MapUnitFrame } from '../../../types/map'

const UNIT: MapUnitFrame = {
  id: 'u-123',
  side: 'blue',
  x: 1234.5,
  y: 5678.9,
  domain: 0,
  status: 0,
  heading: 90,
  type: 'm1_abrams',
}

describe('UnitDetailSidebar', () => {
  it('displays unit info', () => {
    render(<UnitDetailSidebar unit={UNIT} onClose={vi.fn()} />)
    // m1_abrams appears in both header and Type row
    expect(screen.getAllByText('m1_abrams').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('u-123')).toBeInTheDocument()
    expect(screen.getByText('blue')).toBeInTheDocument()
    expect(screen.getByText('Ground')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText(/E 1235/)).toBeInTheDocument()
  })

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn()
    render(<UnitDetailSidebar unit={UNIT} onClose={onClose} />)
    fireEvent.click(screen.getByLabelText('Close unit detail'))
    expect(onClose).toHaveBeenCalled()
  })

  it('shows destroyed status', () => {
    const destroyed = { ...UNIT, status: 3 }
    render(<UnitDetailSidebar unit={destroyed} onClose={vi.fn()} />)
    expect(screen.getByText('Destroyed')).toBeInTheDocument()
  })

  it('shows heading with degree symbol', () => {
    render(<UnitDetailSidebar unit={UNIT} onClose={vi.fn()} />)
    expect(screen.getByText('90\u00B0')).toBeInTheDocument()
  })
})
