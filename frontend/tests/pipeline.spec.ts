// Exercise pipeline behavior with controlled fixtures and explicit assertions.
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePipelineStore } from '../src/stores/pipeline'
let store: ReturnType<typeof usePipelineStore>
const response = (data: object, ok = true) => ({
  ok,
  status: ok ? 200 : 422,
  json: async () => data,
})

it('marks evaluation retry submission busy, prevents duplicates and clears loading on failure', async () => {
  let finish!: (value: ReturnType<typeof response>) => void
  const fetch = vi.fn(
    () =>
      new Promise<ReturnType<typeof response>>((resolve) => {
        finish = resolve
      }),
  )
  vi.stubGlobal('fetch', fetch)
  store.runId = 'r'
  const retry = store.action('retry-evaluation')
  expect(store.activeAction).toBe('retry-evaluation')
  expect(store.busy).toBe(true)
  await store.action('retry-evaluation')
  expect(fetch).toHaveBeenCalledOnce()
  finish(response({ detail: 'A worker is still active.' }, false))
  await retry
  expect(store.activeAction).toBe('')
  expect(store.busy).toBe(false)
  expect(store.error).toBe('A worker is still active.')
})
// Reset shared fixtures and mocks between test cases.
beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
  store = usePipelineStore()
})
// Release test state and restore patched dependencies.
afterEach(() => {
  store.$dispose()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
it('attaches to URL run, ignores stale snapshots and does not start new jobs', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(response({ id: 'shared', status: 'complete', revision: 4 }))
  vi.stubGlobal('fetch', fetch)
  await store.attach('shared')
  expect(store.run?.id).toBe('shared')
  expect(fetch).toHaveBeenCalledOnce()
  expect(fetch.mock.calls[0][0]).toBe('/api/searches/shared')
})
it('falls back to polling and recovers after network loss', async () => {
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new Error('Offline'))
    .mockResolvedValue(response({ id: 'r', status: 'complete' }))
  vi.stubGlobal('fetch', fetch)
  await store.attach('r')
  expect(store.reconnecting).toBe(true)
  await vi.advanceTimersByTimeAsync(3000)
  expect(store.run?.status).toBe('complete')
  expect(store.reconnecting).toBe(false)
})
it('keeps data when deletion fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(response({ id: 'r', status: 'complete' }))
      .mockResolvedValueOnce(response({ detail: 'Deletion failed' }, false)),
  )
  await store.attach('r')
  expect(await store.deleteData()).toBeNull()
  expect(store.runId).toBe('r')
  expect(store.error).toContain('Deletion failed')
})
it('submits edited profile with preferences to the confirmation endpoint', async () => {
  const fetch = vi.fn().mockResolvedValue(response({ id: 'r', status: 'complete' }))
  vi.stubGlobal('fetch', fetch)
  await store.attach('r')
  await store.confirm({ name: 'Updated' } as any, { queries: ['Engineer'] } as any)
  const call = fetch.mock.calls.find(([, options]) => options?.method === 'PUT')!
  expect(call[0]).toBe('/api/searches/r/confirm-profile')
  expect(JSON.parse(call[1].body).profile.name).toBe('Updated')
})

it.each([[[]], [['  ']], [['Sydney']]])(
  'normalizes empty locations before sending a search: %j',
  async (...args) => {
    const locations = args[0] as string[]
    const fetch = vi.fn().mockResolvedValue(response({ id: 'r', status: 'complete' }))
    vi.stubGlobal('fetch', fetch)
    await store.attach('r')
    const preferences = { queries: ['Engineer'], locations } as any
    await store.confirm({ name: 'Updated' } as any, preferences)
    const call = fetch.mock.calls.find(([, options]) => options?.method === 'PUT')!
    expect(JSON.parse(call[1].body).preferences.locations).toEqual(
      locations?.[0]?.trim() ? locations : ['Worldwide'],
    )
    expect(preferences.locations).toBe(locations)
  },
)

it('finds more jobs in the same run without changing its profile or clearing results on request failure', async () => {
  const original = {
    id: 'r',
    status: 'complete',
    profile: { name: 'Existing' },
    recommendations: [{ jobId: 'kept' }],
  }
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(response(original))
    .mockResolvedValueOnce(response({ detail: 'Search unavailable' }, false))
  vi.stubGlobal('fetch', fetch)
  await store.attach('r')
  expect(
    await store.findMore({ queries: ['Analyst'], locations: [], evaluation_model: 'gpt' } as any),
  ).toBe(false)
  const [url, request] = fetch.mock.calls[1]
  expect(url).toBe('/api/searches/r/find-more')
  expect(request.method).toBe('POST')
  expect(JSON.parse(request.body)).toEqual({
    preferences: { queries: ['Analyst'], locations: ['Worldwide'] },
  })
  expect(store.run).toEqual(original)
  expect(store.error).toBe('Search unavailable')
})
