import { describe, it, expect } from 'vitest'
import { eraDisplayName, eraBadgeColor, eraOrder } from '../../lib/era'

describe('eraDisplayName', () => {
  it('maps known eras', () => {
    expect(eraDisplayName('modern')).toBe('Modern')
    expect(eraDisplayName('ww2')).toBe('WW2')
    expect(eraDisplayName('ww1')).toBe('WW1')
    expect(eraDisplayName('napoleonic')).toBe('Napoleonic')
    expect(eraDisplayName('ancient_medieval')).toBe('Ancient & Medieval')
  })

  it('returns raw value for unknown era', () => {
    expect(eraDisplayName('future')).toBe('future')
  })
})

describe('eraBadgeColor', () => {
  it('returns color class for known eras', () => {
    expect(eraBadgeColor('modern')).toContain('bg-era-modern')
    expect(eraBadgeColor('ww2')).toContain('bg-era-ww2')
  })

  it('returns fallback for unknown era', () => {
    expect(eraBadgeColor('future')).toContain('bg-gray-500')
  })
})

describe('eraOrder', () => {
  it('orders modern before historical', () => {
    expect(eraOrder('modern')).toBeLessThan(eraOrder('ww2'))
    expect(eraOrder('ww2')).toBeLessThan(eraOrder('ww1'))
    expect(eraOrder('ww1')).toBeLessThan(eraOrder('napoleonic'))
    expect(eraOrder('napoleonic')).toBeLessThan(eraOrder('ancient_medieval'))
  })

  it('returns 99 for unknown era', () => {
    expect(eraOrder('future')).toBe(99)
  })
})
