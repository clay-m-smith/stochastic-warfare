import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfigDiff } from '../../../pages/editor/ConfigDiff'
import { renderWithProviders } from '../../helpers'

describe('ConfigDiff', () => {
  it('shows no changes when configs are identical', () => {
    const config = { name: 'test', seed: 42 }
    renderWithProviders(<ConfigDiff original={config} modified={config} />)
    expect(screen.getByText('No changes from original.')).toBeInTheDocument()
  })

  it('shows changed fields', async () => {
    const original = { name: 'test', seed: 42, nested: { value: 1 } }
    const modified = { name: 'modified', seed: 42, nested: { value: 2 } }
    renderWithProviders(<ConfigDiff original={original} modified={modified} />)

    // Click to expand
    const button = screen.getByText('Changes (2)')
    await userEvent.click(button)

    expect(screen.getByText('name')).toBeInTheDocument()
    expect(screen.getByText('nested.value')).toBeInTheDocument()
  })
})
