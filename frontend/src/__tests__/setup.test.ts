import { describe, expect, it } from 'vitest'

describe('frontend test browser environment', () => {
  it('provides the localStorage contract at a non-opaque origin', () => {
    expect(window.localStorage).toBe(localStorage)
    expect(localStorage.length).toBe(0)
    expect(localStorage.getItem('missing')).toBeNull()

    localStorage.setItem('answer', 42 as unknown as string)
    localStorage.setItem('next', 'value')

    expect(localStorage.length).toBe(2)
    expect(localStorage.getItem('answer')).toBe('42')
    expect(localStorage.key(0)).toBe('answer')

    localStorage.removeItem('answer')
    expect(localStorage.length).toBe(1)
  })

  it('starts each test with isolated localStorage', () => {
    expect(localStorage.length).toBe(0)
  })
})
