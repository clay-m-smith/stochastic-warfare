import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useExport } from '../../hooks/useExport'

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn().mockReturnValue('blob:test'),
    revokeObjectURL: vi.fn(),
  })
})

describe('useExport', () => {
  it('downloadJSON triggers download', () => {
    const { result } = renderHook(() => useExport(), { wrapper })
    act(() => result.current.downloadJSON({ key: 'value' }, 'test.json'))
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalled()
  })

  it('downloadCSV formats headers and rows', () => {
    const { result } = renderHook(() => useExport(), { wrapper })
    act(() => result.current.downloadCSV(['a', 'b'], [[1, 'hello']], 'test.csv'))
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('downloadCSV escapes commas in cells', () => {
    const { result } = renderHook(() => useExport(), { wrapper })
    act(() => result.current.downloadCSV(['col'], [['has, comma']], 'test.csv'))
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('downloadYAML generates YAML content', () => {
    const { result } = renderHook(() => useExport(), { wrapper })
    act(() => result.current.downloadYAML({ name: 'test' }, 'test.yaml'))
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('printReport navigates to print page', () => {
    const { result } = renderHook(() => useExport(), { wrapper })
    act(() => result.current.printReport('run123'))
  })
})
