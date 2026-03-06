import { describe, it, expect } from 'vitest'
import { formatDuration, formatDate, formatNumber } from '../../lib/format'

describe('formatDuration', () => {
  it('returns dash for zero or negative', () => {
    expect(formatDuration(0)).toBe('—')
    expect(formatDuration(-1)).toBe('—')
  })

  it('formats sub-hour as minutes', () => {
    expect(formatDuration(0.5)).toBe('30m')
  })

  it('formats whole hours', () => {
    expect(formatDuration(4)).toBe('4h')
  })

  it('formats hours and minutes', () => {
    expect(formatDuration(2.5)).toBe('2h 30m')
  })
})

describe('formatDate', () => {
  it('returns dash for null', () => {
    expect(formatDate(null)).toBe('—')
  })

  it('returns dash for invalid date', () => {
    expect(formatDate('not-a-date')).toBe('—')
  })
})

describe('formatNumber', () => {
  it('formats with locale separators', () => {
    const result = formatNumber(1000)
    // Exact format depends on locale, but should contain "1" and "000"
    expect(result).toContain('1')
    expect(result).toContain('000')
  })
})
