import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigToggles } from '../../../pages/editor/ConfigToggles'

describe('ConfigToggles', () => {
  it('exposes school creation as explicitly unsupported without proxy data', () => {
    const dispatch = vi.fn()
    render(<ConfigToggles config={{}} dispatch={dispatch} />)

    expect(screen.getByLabelText('Doctrinal Schools')).toBeDisabled()
    expect(screen.getByText(/exact unit IDs/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Doctrinal Schools'))
    expect(dispatch).not.toHaveBeenCalled()
  })

  it('allows an existing exact school configuration to be removed', () => {
    const dispatch = vi.fn()
    render(
      <ConfigToggles
        config={{
          school_config: {
            unit_assignments: { blue_m1a2_0000: 'maneuverist' },
          },
        }}
        dispatch={dispatch}
      />,
    )

    const schools = screen.getByLabelText('Doctrinal Schools')
    expect(schools).toBeEnabled()
    fireEvent.click(schools)
    expect(dispatch).toHaveBeenCalledWith({
      type: 'TOGGLE_CONFIG',
      key: 'school_config',
      enabled: false,
    })
  })

  it('exposes Space creation as explicitly unsupported without proxy data', () => {
    const dispatch = vi.fn()
    render(<ConfigToggles config={{}} dispatch={dispatch} />)

    expect(screen.getByLabelText('Space')).toBeDisabled()
    expect(screen.getByText(/explicit catalog constellation IDs/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Space'))
    expect(dispatch).not.toHaveBeenCalled()
  })

  it('allows an existing explicit Space configuration to be removed', () => {
    const dispatch = vi.fn()
    render(
      <ConfigToggles
        config={{
          space_config: {
            enable_space: true,
            constellation_ids: ['worldview3_reference_optical'],
          },
        }}
        dispatch={dispatch}
      />,
    )

    const space = screen.getByLabelText('Space')
    expect(space).toBeEnabled()
    fireEvent.click(space)
    expect(dispatch).toHaveBeenCalledWith({
      type: 'TOGGLE_CONFIG',
      key: 'space_config',
      enabled: false,
    })
  })
})
