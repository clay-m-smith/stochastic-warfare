import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MapLegend } from '../../../components/map/MapLegend'
import type { OverlayOptions } from '../../../lib/unitRendering'

function makeOverlays(overrides: Partial<OverlayOptions> = {}): OverlayOptions {
  return {
    showMorale: false,
    showHealth: false,
    showPosture: false,
    showSuppression: false,
    showLogistics: false,
    ...overrides,
  }
}

describe('MapLegend overlay sections', () => {
  it('shows morale legend section when showMorale is true', () => {
    render(<MapLegend overlays={makeOverlays({ showMorale: true })} />)
    expect(screen.getByText('Morale')).toBeInTheDocument()
    expect(screen.getByText('Shaken')).toBeInTheDocument()
    expect(screen.getByText('Broken')).toBeInTheDocument()
    expect(screen.getByText('Routed')).toBeInTheDocument()
  })

  it('hides morale legend section when showMorale is false', () => {
    render(<MapLegend overlays={makeOverlays({ showMorale: false })} />)
    expect(screen.queryByText('Shaken')).not.toBeInTheDocument()
  })

  it('shows posture abbreviation legend when enabled', () => {
    render(<MapLegend overlays={makeOverlays({ showPosture: true })} />)
    expect(screen.getByText('Posture')).toBeInTheDocument()
    expect(screen.getByText('Defensive')).toBeInTheDocument()
    expect(screen.getByText('Fortified')).toBeInTheDocument()
    expect(screen.getByText('Battle Stations')).toBeInTheDocument()
  })

  it('shows suppression legend when enabled', () => {
    render(<MapLegend overlays={makeOverlays({ showSuppression: true })} />)
    // 'Suppression' heading
    const headings = screen.getAllByText('Suppression')
    expect(headings.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Pinned')).toBeInTheDocument()
  })

  it('shows logistics legend when enabled', () => {
    render(<MapLegend overlays={makeOverlays({ showLogistics: true })} />)
    expect(screen.getByText('Fuel')).toBeInTheDocument()
    expect(screen.getByText('Ammo')).toBeInTheDocument()
  })

  it('hides logistics legend when disabled', () => {
    render(<MapLegend overlays={makeOverlays({ showLogistics: false })} />)
    expect(screen.queryByText('Fuel')).not.toBeInTheDocument()
    expect(screen.queryByText('Ammo')).not.toBeInTheDocument()
  })

  it('shows health legend when enabled', () => {
    render(<MapLegend overlays={makeOverlays({ showHealth: true })} />)
    expect(screen.getByText('Health')).toBeInTheDocument()
  })
})
