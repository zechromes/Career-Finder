// Exercise save profile behavior with controlled fixtures and explicit assertions.
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SaveProfile from '../src/components/SaveProfile.vue'
import { useProfileStore } from '../src/stores/profile'
// Reset shared fixtures and mocks between test cases.
beforeEach(() => setActivePinia(createPinia()))
// Release test state and restore patched dependencies.
afterEach(() => vi.unstubAllGlobals())
it('updates a loaded profile-only workspace without requiring its original PDF', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ id: 'saved', resume_available: false }) })
  vi.stubGlobal('fetch', fetch)
  const wrapper = mount(SaveProfile, {
    props: {
      runId: 'run',
      profile: { name: 'Candidate' } as any,
      savedProfileId: 'saved',
      savedProfileName: 'Engineering',
    },
    global: { stubs: { RouterLink: true } },
  })
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(fetch.mock.calls[0][0]).toBe('/api/profiles/saved')
  expect(fetch.mock.calls[0][1].method).toBe('PUT')
  expect(JSON.parse(fetch.mock.calls[0][1].body).source_run_id).toBeUndefined()
  expect(wrapper.text()).toContain('Profile and preferences saved')
})
it('repeated manual saves update the created workspace instead of making duplicates', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ id: 'created', resume_available: true }) })
  vi.stubGlobal('fetch', fetch)
  const wrapper = mount(SaveProfile, {
    props: { runId: 'run', profile: { name: 'Candidate' } as any },
    global: { stubs: { RouterLink: true } },
  })
  await wrapper.get('input').setValue('Engineering')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(fetch.mock.calls.map((call) => call[1].method)).toEqual(['POST', 'PUT'])
})
it('defaults to automatic level priority while preserving explicitly saved all-level searches', () => {
  const store = useProfileStore()
  expect(store.preferences.seniority).toBe('auto')
  store.load({ profile: { name: 'Candidate' } as any, preferences: { seniority: 'any' } })
  expect(store.preferences.seniority).toBe('any')
})
