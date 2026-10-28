import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import ApplicationStepper from '../src/components/ApplicationStepper.vue'
const run = {
  id: 'example',
  status: 'running',
  phase: 2,
  message: 'LinkedIn: loading descriptions — 5/15 checked, 5 ready (3 cached).',
} as any
it('shows activity without inventing a collection percentage and puts status below it', () => {
  const wrapper = mount(ApplicationStepper, { props: { run } })
  const bar = wrapper.get('[role="progressbar"]')
  expect(bar.attributes('aria-valuenow')).toBeUndefined()
  expect(bar.attributes('aria-valuetext')).toBe(run.message)
  expect(bar.element.nextElementSibling?.textContent).toContain(run.message)
})
it('shows measured evaluation progress and clamps stale counts', async () => {
  const wrapper = mount(ApplicationStepper, {
    props: { run: { ...run, phase: 4, evaluated_jobs: 5, evaluation_total: 20 } },
  })
  expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('25')
  await wrapper.setProps({ run: { ...run, phase: 4, evaluated_jobs: 30, evaluation_total: 20 } })
  expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('100')
})
it.each(['complete', 'cancelled', 'error', 'awaiting_search'])(
  'stops loading for %s while retaining status text',
  (status) => {
    const wrapper = mount(ApplicationStepper, { props: { run: { ...run, status } } })
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(run.message)
  },
)
