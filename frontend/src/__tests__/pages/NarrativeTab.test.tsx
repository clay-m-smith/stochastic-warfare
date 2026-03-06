import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { NarrativeTab } from '../../pages/runs/tabs/NarrativeTab'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('NarrativeTab', () => {
  it('renders narrative text', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ narrative: 'The battle of 73 Easting began at dawn.', tick_count: 50 }), { status: 200 }),
    )
    renderWithProviders(<NarrativeTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText(/The battle of 73 Easting/)).toBeInTheDocument()
    })
  })

  it('shows tick count', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ narrative: 'Some text', tick_count: 100 }), { status: 200 }),
    )
    renderWithProviders(<NarrativeTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText(/100 ticks/)).toBeInTheDocument()
    })
  })

  it('shows empty state when no narrative', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ narrative: '', tick_count: 0 }), { status: 200 }),
    )
    renderWithProviders(<NarrativeTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText('No narrative available for this run.')).toBeInTheDocument()
    })
  })

  it('has side filter', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ narrative: 'text', tick_count: 10 }), { status: 200 }),
    )
    renderWithProviders(<NarrativeTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText('All Sides')).toBeInTheDocument()
    })
  })

  it('has style toggle', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ narrative: 'text', tick_count: 10 }), { status: 200 }),
    )
    renderWithProviders(<NarrativeTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText('Full')).toBeInTheDocument()
    })
    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('Timeline')).toBeInTheDocument()
  })
})
