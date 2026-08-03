import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { TerrainSection } from '../../../pages/editor/TerrainSection'

describe('TerrainSection', () => {
  it('reads and writes the canonical base-elevation field', () => {
    const dispatch = vi.fn()
    render(
      <TerrainSection
        config={{
          terrain: {
            width_m: 5000,
            height_m: 4000,
            cell_size_m: 100,
            base_elevation_m: 275,
            terrain_type: 'flat_desert',
          },
        }}
        dispatch={dispatch}
      />,
    )

    const input = screen.getByLabelText('Base Elevation (m)')
    expect(input).toHaveValue(275)

    fireEvent.change(input, { target: { value: '325' } })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'SET_TERRAIN_FIELD',
      field: 'base_elevation_m',
      value: 325,
    })
  })

  it('offers exactly the production TerrainConfig enum', () => {
    render(<TerrainSection config={{ terrain: {} }} dispatch={vi.fn()} />)

    const select = screen.getByLabelText('Terrain Type') as HTMLSelectElement
    expect(Array.from(select.options, (option) => option.value)).toEqual([
      'flat_desert',
      'open_ocean',
      'hilly_defense',
      'trench_warfare',
      'open_field',
    ])
  })
})
