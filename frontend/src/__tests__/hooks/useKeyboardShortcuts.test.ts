import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('useKeyboardShortcuts', () => {
  it('calls action on matching key press', () => {
    const action = vi.fn()
    renderHook(() =>
      useKeyboardShortcuts([{ key: ' ', action, description: 'Play/Pause' }]),
    )
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: ' ' }))
    })
    expect(action).toHaveBeenCalled()
  })

  it('ignores keypresses when disabled', () => {
    const action = vi.fn()
    renderHook(() =>
      useKeyboardShortcuts([{ key: ' ', action, description: 'Test' }], false),
    )
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: ' ' }))
    })
    expect(action).not.toHaveBeenCalled()
  })

  it('skips when target is input', () => {
    const action = vi.fn()
    renderHook(() =>
      useKeyboardShortcuts([{ key: 'a', action, description: 'Test' }]),
    )
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    act(() => {
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }))
    })
    expect(action).not.toHaveBeenCalled()
    document.body.removeChild(input)
  })

  it('handles ctrl modifier', () => {
    const action = vi.fn()
    renderHook(() =>
      useKeyboardShortcuts([{ key: 's', ctrl: true, action, description: 'Save' }]),
    )
    // Without ctrl — should not trigger
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 's' }))
    })
    expect(action).not.toHaveBeenCalled()
    // With ctrl — should trigger
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true }))
    })
    expect(action).toHaveBeenCalled()
  })

  it('cleans up on unmount', () => {
    const action = vi.fn()
    const { unmount } = renderHook(() =>
      useKeyboardShortcuts([{ key: 'x', action, description: 'Test' }]),
    )
    unmount()
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'x' }))
    })
    expect(action).not.toHaveBeenCalled()
  })
})
