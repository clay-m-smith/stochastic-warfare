import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { afterEach, vi, expect } from 'vitest'
import { toHaveNoViolations } from 'jest-axe'

expect.extend(toHaveNoViolations)

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
