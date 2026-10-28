import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import AppSnackbar from '../src/components/AppSnackbar.vue'
import JobActions from '../src/components/JobActions.vue'
import { useSnackbarStore } from '../src/stores/snackbar'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
})
afterEach(() => vi.useRealTimers())

it('announces, replaces, dismisses and automatically clears notifications', async () => {
  const wrapper = mount(AppSnackbar)
  const store = useSnackbarStore()
  store.show('Saved.')
  await wrapper.vm.$nextTick()
  expect(wrapper.get('[role="status"]').text()).toBe('Saved.')
  vi.advanceTimersByTime(4000)
  store.show('Job marked as applied.')
  vi.advanceTimersByTime(1000)
  expect(store.message).toBe('Job marked as applied.')
  vi.advanceTimersByTime(4000)
  expect(store.message).toBe('')
  store.show('Saved.')
  await wrapper.vm.$nextTick()
  await wrapper.get('button').trigger('click')
  expect(store.message).toBe('')
  wrapper.unmount()
  store.$dispose()
})

it('confirms save and applied toggles and their reversals', async () => {
  const wrapper = mount(JobActions, {
    props: {
      inline: true,
      job: { title: 'Engineer', company: 'Example', apply_url: 'https://example.test/job' } as any,
    },
  })
  const store = useSnackbarStore()
  await wrapper.get('button[title="Save"]').trigger('click')
  expect(store.message).toBe('Saved.')
  await wrapper.get('button[title="Saved"]').trigger('click')
  expect(store.message).toBe('Removed from saved jobs.')
  await wrapper.get('button[title="Mark as applied"]').trigger('click')
  expect(store.message).toBe('Job marked as applied.')
  await wrapper.get('button[title="Applied"]').trigger('click')
  expect(store.message).toBe('Applied status removed.')
  wrapper.unmount()
  store.$dispose()
})

it.each([null, document.body])(
  'keeps the menu available during pointer focus loss to %s',
  async (target) => {
    const wrapper = mount(JobActions, {
      attachTo: document.body,
      props: {
        job: {
          title: 'Engineer',
          company: 'Example',
          apply_url: 'https://example.test/job',
        } as any,
      },
    })
    try {
      await wrapper.get('button[aria-expanded]').trigger('click')
      const applied = wrapper.get('button[aria-label="Mark as applied: Engineer at Example"]')
      await applied.trigger('pointerdown')
      // Some browsers move focus to the page body rather than the clicked button.
      await wrapper.get('button[aria-label="Save: Engineer at Example"]').trigger('focusout', {
        relatedTarget: target,
      })
      expect(wrapper.find('[data-actions]').exists()).toBe(true)
      await applied.trigger('pointerup')
      await applied.trigger('click')
      expect(
        wrapper.get('button[aria-label="Applied: Engineer at Example"]').attributes('aria-pressed'),
      ).toBe('true')
      expect(useSnackbarStore().message).toBe('Job marked as applied.')
      await wrapper.get('button[aria-label="Applied: Engineer at Example"]').trigger('focusout', {
        relatedTarget: document.body,
      })
      expect(wrapper.find('[data-actions]').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  },
)
