import { describe, it, expect } from 'vitest'
import { domainDisplayName, domainBadgeColor } from '../../lib/domain'

describe('domainDisplayName', () => {
  it('returns display name for known domains', () => {
    expect(domainDisplayName('land')).toBe('Land')
    expect(domainDisplayName('air')).toBe('Air')
    expect(domainDisplayName('naval')).toBe('Naval')
    expect(domainDisplayName('submarine')).toBe('Submarine')
    expect(domainDisplayName('space')).toBe('Space')
  })

  it('returns raw value for unknown domains', () => {
    expect(domainDisplayName('cyber')).toBe('cyber')
  })
})

describe('domainBadgeColor', () => {
  it('returns badge color for known domains', () => {
    expect(domainBadgeColor('land')).toContain('green')
    expect(domainBadgeColor('air')).toContain('sky')
    expect(domainBadgeColor('naval')).toContain('blue')
    expect(domainBadgeColor('submarine')).toContain('indigo')
    expect(domainBadgeColor('space')).toContain('gray')
  })

  it('returns gray fallback for unknown domains', () => {
    expect(domainBadgeColor('unknown')).toBe('bg-gray-500 text-white')
  })
})
