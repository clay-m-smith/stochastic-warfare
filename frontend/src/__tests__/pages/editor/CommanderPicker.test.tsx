import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CommanderPicker } from '../../../pages/editor/CommanderPicker'

describe('CommanderPicker', () => {
  it('states the complete-catalog boundary without exposing a selector', () => {
    render(<CommanderPicker />)

    expect(screen.getByText(/complete era-specific catalog/)).toBeInTheDocument()
    expect(screen.getByText(/canonical commander_profile on every side/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})
