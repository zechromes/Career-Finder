import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { api } from '../src/stores/pipeline'
import { jobActionKey, useJobsStore } from '../src/stores/jobs'
vi.mock('../src/stores/pipeline', () => ({ api: vi.fn() }))
const job = { jobId: 'old', apply_url: 'https://example.test/job?utm_source=test#detail' } as any
const run = { id: 'run', recommendations: [job], excluded_recommendations: [] } as any
beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.mocked(api).mockReset()
})
it('shares actions across tracking URLs and different run job IDs', async () => {
  vi.mocked(api).mockResolvedValue({ actions: {} })
  const store = useJobsStore()
  store.load('run')
  store.toggle(job, 'saved')
  await flushPromises()
  expect(store.flags({ ...job, jobId: 'new', apply_url: 'https://example.test/job' }).saved).toBe(
    true,
  )
  expect(JSON.parse(vi.mocked(api).mock.calls[0][1]!.body as string).key).toBe(
    'https://example.test/job',
  )
})
it('retries failed local edits after reopening, overriding stale server values', async () => {
  vi.mocked(api).mockRejectedValueOnce(new Error('offline'))
  const store = useJobsStore()
  store.load('run')
  store.toggle(job, 'saved')
  await flushPromises()
  expect(store.storageError).toContain('saved locally')
  store.load('run')
  vi.mocked(api).mockResolvedValue({ actions: { [jobActionKey(job)]: { saved: false } } })
  await store.sync(run)
  await flushPromises()
  expect(store.flags(job).saved).toBe(true)
  expect(JSON.parse(vi.mocked(api).mock.calls.at(-1)![1]!.body as string).value).toBe(true)
  expect(localStorage.getItem('career-actions-pending:run')).toBe('{}')
})
it('ignores delayed synchronization from another run', async () => {
  let finish!: (value: any) => void
  vi.mocked(api).mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve
    }),
  )
  const store = useJobsStore()
  store.load('run')
  const request = store.sync(run)
  store.load('different')
  finish({ actions: { [jobActionKey(job)]: { saved: true } } })
  await request
  expect(store.flags(job).saved).toBeUndefined()
})
it('migrates legacy job IDs and keeps the final rapid toggle', async () => {
  localStorage.setItem('career-actions:run', JSON.stringify({ old: { applied: true } }))
  vi.mocked(api).mockResolvedValue({ actions: {} })
  const store = useJobsStore()
  store.load('run')
  await store.sync(run)
  await flushPromises()
  expect(store.flags(job).applied).toBe(true)
  store.toggle(job, 'saved')
  store.toggle(job, 'saved')
  await flushPromises()
  expect(store.flags(job).saved).toBe(false)
  expect(JSON.parse(vi.mocked(api).mock.calls.at(-1)![1]!.body as string)).toMatchObject({
    action: 'saved',
    value: false,
  })
})

it.each(['saved', 'applied', 'dismissed'] as const)(
  'keeps a confirmed %s action when an older sync finishes during evaluation',
  async (action) => {
    let finishWrite!: (value: any) => void
    let finishSync!: (value: any) => void
    vi.mocked(api).mockImplementation(
      (_path, init) =>
        new Promise((resolve) => {
          if (init?.method === 'PUT') finishWrite = resolve
          else finishSync = resolve
        }),
    )
    const store = useJobsStore()
    store.load('run')
    store.toggle(job, action)
    await flushPromises()
    const syncing = store.sync({ ...run, status: 'running', phase: 4 })
    finishWrite({ actions: { [jobActionKey(job)]: { [action]: true } } })
    await flushPromises()
    expect(store.flags(job)[action]).toBe(true)
    finishSync({ actions: { [jobActionKey(job)]: { [action]: false } } })
    await syncing
    expect(store.flags(job)[action]).toBe(true)
    store.load('run')
    expect(store.flags(job)[action]).toBe(true)
  },
)

it('persists a reason with dismissal and clears feedback when restored', async () => {
  vi.mocked(api).mockResolvedValue({ actions: {} })
  const store = useJobsStore()
  store.load('run')
  store.dismiss({ ...job, title: 'Developer', location: 'Sydney' }, { reason: 'location' })
  await flushPromises()
  expect(JSON.parse(vi.mocked(api).mock.calls.at(-1)![1]!.body as string)).toMatchObject({
    action: 'dismissed',
    value: true,
    dismissal: { reason: 'location' },
  })
  store.load('run')
  expect(store.feedback[jobActionKey(job)]?.reason).toBe('location')
  store.toggle(job, 'dismissed')
  await flushPromises()
  expect(store.flags(job).dismissed).toBe(false)
  expect(store.feedback).toEqual({})
  expect(JSON.parse(vi.mocked(api).mock.calls.at(-1)![1]!.body as string).dismissal).toBeNull()
})

it('keeps a changed reason when an older dismissal write finishes', async () => {
  let finish!: (value: any) => void
  vi.mocked(api).mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve
    }),
  )
  vi.mocked(api).mockResolvedValue({ actions: {} })
  const store = useJobsStore()
  store.load('run')
  store.dismiss(job, { reason: 'role' })
  await flushPromises()
  store.dismiss(job, { reason: 'location' })
  finish({ actions: {}, dismissal_feedback: { [jobActionKey(job)]: { reason: 'role' } } })
  await flushPromises()
  expect(store.feedback[jobActionKey(job)]?.reason).toBe('location')
  expect(JSON.parse(vi.mocked(api).mock.calls.at(-1)![1]!.body as string).dismissal.reason).toBe(
    'location',
  )
})

it('retries feedback after reload without a stale sync overwriting it', async () => {
  vi.mocked(api).mockRejectedValueOnce(new Error('offline'))
  const store = useJobsStore()
  store.load('run')
  store.dismiss(job, { reason: 'role' })
  await flushPromises()
  store.load('run')
  vi.mocked(api).mockResolvedValue({ actions: {}, dismissal_feedback: {} })
  await store.sync(run)
  await flushPromises()
  expect(JSON.parse(vi.mocked(api).mock.calls.at(-1)![1]!.body as string).dismissal.reason).toBe(
    'role',
  )
  expect(store.flags(job).dismissed).toBe(true)
})

it('removes a preference without restoring the dismissed job', async () => {
  vi.mocked(api).mockResolvedValue({ actions: {} })
  const store = useJobsStore()
  store.load('run')
  store.dismiss(job, { reason: 'role' })
  await flushPromises()
  store.forgetFeedback(jobActionKey(job))
  await flushPromises()
  expect(store.feedback).toEqual({})
  expect(store.flags(job).dismissed).toBe(true)
  expect(JSON.parse(vi.mocked(api).mock.calls.at(-1)![1]!.body as string)).toMatchObject({
    value: true,
    dismissal: null,
  })
})

it('keeps the sync warning when another action succeeds but feedback is still pending', async () => {
  vi.mocked(api).mockRejectedValueOnce(new Error('offline'))
  const store = useJobsStore()
  store.load('run')
  store.dismiss(job, { reason: 'role' })
  await flushPromises()
  vi.mocked(api).mockResolvedValue({ actions: {} })
  store.toggle(job, 'saved')
  await flushPromises()
  expect(store.storageError).toContain('saved locally')
  expect(
    JSON.parse(localStorage.getItem('career-feedback-pending:run')!)[jobActionKey(job)].reason,
  ).toBe('role')
  await store.sync(run)
  await flushPromises()
  expect(store.storageError).toBe('')
})
