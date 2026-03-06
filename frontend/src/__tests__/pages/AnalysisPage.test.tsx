import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../helpers'
import { AnalysisPage } from '../../pages/analysis/AnalysisPage'

beforeEach(() => {
  vi.restoreAllMocks()
  // Mock scenario list fetch for BatchPanel/ComparePanel/SweepPanel
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify([]), { status: 200 }),
  )
})

describe('AnalysisPage', () => {
  it('renders page title', () => {
    renderWithProviders(<AnalysisPage />)
    expect(screen.getByText('Analysis')).toBeInTheDocument()
  })

  it('shows three tabs', () => {
    renderWithProviders(<AnalysisPage />)
    expect(screen.getByText('Batch MC')).toBeInTheDocument()
    expect(screen.getByText('A/B Compare')).toBeInTheDocument()
    expect(screen.getByText('Sensitivity Sweep')).toBeInTheDocument()
  })

  it('defaults to batch tab', () => {
    renderWithProviders(<AnalysisPage />)
    expect(screen.getByText('Monte Carlo Batch')).toBeInTheDocument()
  })

  it('switches to compare tab', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnalysisPage />)
    await user.click(screen.getByText('A/B Compare'))
    expect(screen.getByText('A/B Comparison')).toBeInTheDocument()
  })

  it('switches to sweep tab', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnalysisPage />)
    await user.click(screen.getByText('Sensitivity Sweep'))
    expect(screen.getByText('Sensitivity Sweep', { selector: 'h2' })).toBeInTheDocument()
  })
})
