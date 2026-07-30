import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi, expect } from 'vitest'
import { toHaveNoViolations } from 'jest-axe'

expect.extend(toHaveNoViolations)

class TestLocalStorage implements Storage {
  private readonly entries = new Map<string, string>()

  get length(): number {
    return this.entries.size
  }

  clear(): void {
    this.entries.clear()
  }

  getItem(key: string): string | null {
    return this.entries.get(String(key)) ?? null
  }

  key(index: number): string | null {
    return [...this.entries.keys()][index] ?? null
  }

  removeItem(key: string): void {
    this.entries.delete(String(key))
  }

  setItem(key: string, value: string): void {
    this.entries.set(String(key), String(value))
  }
}

let testLocalStorage: Storage

function installLocalStorage(): void {
  testLocalStorage = new TestLocalStorage()
  const descriptor = {
    configurable: true,
    enumerable: true,
    value: testLocalStorage,
    writable: true,
  }

  Object.defineProperty(globalThis, 'localStorage', descriptor)
  Object.defineProperty(window, 'localStorage', descriptor)
}

installLocalStorage()

beforeEach(() => {
  installLocalStorage()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  testLocalStorage.clear()
})
