// Exercise location input behavior with controlled fixtures and explicit assertions.
import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import LocationInput from '../src/components/LocationInput.vue'

// Release test state and restore patched dependencies.
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

it('debounces suggestions and selects a full location with the keyboard', async () => {
  vi.useFakeTimers()
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => [
      {
        label: 'Sydney, New South Wales, Australia',
        value: 'Sydney, New South Wales, Australia',
      },
    ],
  })
  vi.stubGlobal('fetch', fetch)
  const wrapper = mount(LocationInput)
  const input = wrapper.get('input')
  await input.setValue('Sy')
  await input.setValue('Sydney')
  await vi.advanceTimersByTimeAsync(499)
  expect(fetch).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  await flushPromises()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(wrapper.get('[role="option"]').text()).toContain('Australia')
  await input.trigger('keydown', { key: 'ArrowDown' })
  await input.trigger('keydown', { key: 'Enter' })
  expect(wrapper.get('[aria-label="Remove Sydney, New South Wales, Australia"]').exists()).toBe(
    true,
  )
  expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
  wrapper.unmount()
})

it('accepts custom locations including commas when suggestions fail', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Offline')))
  const wrapper = mount(LocationInput)
  const input = wrapper.get('input')
  await input.setValue('Custom city, Country')
  await vi.advanceTimersByTimeAsync(500)
  await flushPromises()
  expect(wrapper.text()).toContain('Suggestions unavailable')
  await input.trigger('keydown', { key: ',' })
  expect(wrapper.find('[aria-label="Remove Custom city, Country"]').exists()).toBe(false)
  await input.trigger('keydown', { key: 'Enter' })
  expect(wrapper.get('[aria-label="Remove Custom city, Country"]').exists()).toBe(true)
  wrapper.unmount()
})
