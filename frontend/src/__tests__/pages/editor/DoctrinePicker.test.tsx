import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DoctrinePicker } from '../../../pages/editor/DoctrinePicker'

describe('DoctrinePicker', () => {
  it('states the exact production boundary without exposing proxy selectors', () => {
    render(<DoctrinePicker />)

    expect(screen.getByText(/exact unit assignments/)).toBeInTheDocument()
    expect(screen.getByText(/Doctrine Compare/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})
