import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { KeyboardShortcutHelp } from '../../components/KeyboardShortcutHelp'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('KeyboardShortcutHelp', () => {
  const shortcuts = [
    { key: ' ', action: vi.fn(), description: 'Play / Pause' },
    { key: 'ArrowRight', action: vi.fn(), description: 'Step Forward' },
  ]

  it('renders shortcuts list when open', () => {
    render(<KeyboardShortcutHelp open shortcuts={shortcuts} onClose={vi.fn()} />)
    expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument()
    expect(screen.getByText('Play / Pause')).toBeInTheDocument()
    expect(screen.getByText('Step Forward')).toBeInTheDocument()
  })

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn()
    render(<KeyboardShortcutHelp open shortcuts={shortcuts} onClose={onClose} />)
    fireEvent.click(screen.getByText('Close'))
    expect(onClose).toHaveBeenCalled()
  })
})
