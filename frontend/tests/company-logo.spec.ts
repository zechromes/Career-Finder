// Exercise company logo behavior with controlled fixtures and explicit assertions.
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CompanyLogo from '../src/components/CompanyLogo.vue'
it('falls back to initials if a logo fails and retries a changed URL', async () => {
  const wrapper = mount(CompanyLogo, {
    props: { company: 'Example Company', src: 'https://example.test/logo.png' },
  })
  expect(wrapper.get('img').attributes('referrerpolicy')).toBe('no-referrer')
  await wrapper.get('img').trigger('error')
  expect(wrapper.text()).toBe('EC')
  await wrapper.setProps({ src: 'https://example.test/new.png' })
  expect(wrapper.find('img').exists()).toBe(true)
})
it('rejects unsafe URLs and handles missing company data', () => {
  const wrapper = mount(CompanyLogo, { props: { src: 'javascript:alert(1)' } })
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toBe('?')
})
