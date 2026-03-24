import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MapLegend } from '../../components/map/MapLegend'
import * as fs from 'fs'
import * as path from 'path'

describe('MapLegend accessibility', () => {
  it('SVG icons are aria-hidden', () => {
    const { container } = render(<MapLegend sides={['blue', 'red']} />)
    const svgs = container.querySelectorAll('svg')
    expect(svgs.length).toBeGreaterThan(0)
    svgs.forEach((svg) => {
      expect(svg).toHaveAttribute('aria-hidden', 'true')
    })
  })
})

describe('prefers-reduced-motion', () => {
  it('index.css contains prefers-reduced-motion query', () => {
    const cssPath = path.resolve(__dirname, '../../index.css')
    const cssContent = fs.readFileSync(cssPath, 'utf-8')
    expect(cssContent).toContain('prefers-reduced-motion')
    expect(cssContent).toContain('animation-duration: 0.01ms')
  })
})
