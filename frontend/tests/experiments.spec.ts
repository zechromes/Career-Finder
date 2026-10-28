import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import EvalView from '../src/views/EvalView.vue'
const source = 'a'.repeat(32)
const id = 'c'.repeat(32)
const fingerprint = 'b'.repeat(64)
const settings = {
  source_id: source,
  fingerprint,
  phase: 'both',
  top_k: 1,
  embedding_models: ['text-embedding-3-small'],
  providers: ['gpt'],
  labels: {},
}
const result = {
  id,
  source_id: source,
  status: 'running',
  fingerprint,
  settings,
  pool_size: 1,
  top_k: 1,
  scope: 'Synthetic',
  retrieval: [],
  generation: [],
  message: 'Working',
}
const json = (value: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(value), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
async function setup(poll: () => Promise<Response>) {
  let reads = 0
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      if (path === '/api/review-datasets') return json([])
      if (path.endsWith('/options'))
        return json({
          generation_models: [{ value: 'gpt', label: 'GPT', model_id: 'synthetic' }],
          embedding_models: ['text-embedding-3-small'],
        })
      if (path.endsWith('/sources')) return json([{ id: source, name: 'Synthetic', job_count: 1 }])
      if (path.includes('/sources/'))
        return json({
          source_id: source,
          fingerprint,
          scope: 'Synthetic',
          jobs: [{ id: 'job', title: 'Developer', company: 'Example', description: 'Python' }],
        })
      if (path.endsWith('/cancel'))
        return json({ ...result, status: 'cancelled', message: 'Cancelled' })
      if (path.endsWith(id)) return ++reads === 1 ? json(result) : poll()
      throw new Error('Unexpected request')
    }),
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/eval', component: EvalView }],
  })
  await router.push(`/eval?experiment=${id}`)
  const wrapper = mount(EvalView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}
it('does not restore a running state when an older poll completes after cancellation', async () => {
  let resolve!: (value: Response) => void
  const wrapper = await setup(
    () =>
      new Promise<Response>((done) => {
        resolve = done
      }),
  )
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Cancel experiment')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('cancelled · Cancelled')
  resolve(await json(result))
  await flushPromises()
  expect(wrapper.text()).toContain('cancelled · Cancelled')
  expect(wrapper.findAll('button').some((button) => button.text() === 'Cancel experiment')).toBe(
    false,
  )
  wrapper.unmount()
})
it('releases the form when a polled experiment expires', async () => {
  const wrapper = await setup(() =>
    json({ detail: 'Experiment expired or server restarted.' }, 404),
  )
  expect(wrapper.get('[role="alert"]').text()).toContain('Experiment expired')
  expect(
    wrapper
      .findAll('button')
      .find((button) => button.text() === 'Run experiment')!
      .attributes('disabled'),
  ).toBeUndefined()
  wrapper.unmount()
})
