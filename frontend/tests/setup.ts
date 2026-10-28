// Exercise setup behavior with controlled fixtures and explicit assertions.
import { beforeEach, vi } from 'vitest'
// Reset shared fixtures and mocks between test cases.
beforeEach(() => {
  for (const name of ['localStorage', 'sessionStorage']) {
    const values = new Map<string, string>()
    vi.stubGlobal(name, {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    })
  }
})
