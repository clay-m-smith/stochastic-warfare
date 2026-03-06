import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TerrainPreview } from '../../../pages/editor/TerrainPreview'

beforeEach(() => {
  vi.restoreAllMocks()
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
    fillRect: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    rotate: vi.fn(),
    translate: vi.fn(),
    fillText: vi.fn(),
    set fillStyle(_v: string) {},
    set strokeStyle(_v: string) {},
    set lineWidth(_v: number) {},
    set font(_v: string) {},
    set textAlign(_v: string) {},
  })
})

describe('TerrainPreview', () => {
  it('renders canvas and label', () => {
    render(<TerrainPreview config={{ terrain: { width_m: 5000, height_m: 5000, terrain_type: 'desert' } }} />)
    expect(screen.getByText('Terrain Preview')).toBeInTheDocument()
    expect(document.querySelector('canvas')).toBeInTheDocument()
  })

  it('handles missing terrain config', () => {
    render(<TerrainPreview config={{}} />)
    expect(screen.getByText('Terrain Preview')).toBeInTheDocument()
  })

  it('renders with objectives', () => {
    render(
      <TerrainPreview
        config={{
          terrain: { width_m: 5000, height_m: 5000 },
          objectives: [{ objective_id: 'obj1', position: [2500, 2500], radius_m: 500 }],
        }}
      />,
    )
    expect(screen.getByText('Terrain Preview')).toBeInTheDocument()
  })
})
