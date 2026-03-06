import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { YamlPreview } from '../../../pages/editor/YamlPreview'

beforeEach(() => {
  vi.restoreAllMocks()
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
})

describe('YamlPreview', () => {
  it('renders YAML content', () => {
    render(<YamlPreview config={{ name: 'test', duration_hours: 4 }} />)
    expect(screen.getByText(/duration_hours: 4/)).toBeInTheDocument()
    expect(screen.getByText(/name: test/)).toBeInTheDocument()
  })

  it('has copy button', () => {
    render(<YamlPreview config={{ name: 'test' }} />)
    const copyBtn = screen.getByText('Copy')
    expect(copyBtn).toBeInTheDocument()
    fireEvent.click(copyBtn)
    expect(navigator.clipboard.writeText).toHaveBeenCalled()
  })
})
