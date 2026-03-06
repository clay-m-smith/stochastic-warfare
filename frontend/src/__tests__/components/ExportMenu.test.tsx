import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ExportMenu } from '../../components/ExportMenu'

beforeEach(() => {
  vi.restoreAllMocks()
  // @headlessui/react v2 requires ResizeObserver
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
})

describe('ExportMenu', () => {
  it('renders Export button', () => {
    render(<ExportMenu items={[{ label: 'Download JSON', onClick: vi.fn() }]} />)
    expect(screen.getByText('Export')).toBeInTheDocument()
  })

  it('shows items on click', async () => {
    const onClick = vi.fn()
    render(<ExportMenu items={[{ label: 'Download JSON', onClick }]} />)
    fireEvent.click(screen.getByText('Export'))
    expect(screen.getByText('Download JSON')).toBeInTheDocument()
  })

  it('calls onClick when item selected', async () => {
    const onClick = vi.fn()
    render(<ExportMenu items={[{ label: 'Download JSON', onClick }]} />)
    fireEvent.click(screen.getByText('Export'))
    fireEvent.click(screen.getByText('Download JSON'))
    expect(onClick).toHaveBeenCalled()
  })
})
