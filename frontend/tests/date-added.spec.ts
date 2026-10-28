// Exercise date added behavior with controlled fixtures and explicit assertions.
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import DateAdded from '../src/components/DateAdded.vue'

describe('Date added', () => {
  it('renders a semantic timestamp', () => {
    const value = '2026-10-09T10:30:00+00:00'
    const wrapper = mount(DateAdded, { props: { value } })
    expect(wrapper.get('time').attributes('datetime')).toBe(value)
    expect(wrapper.text()).toContain('2026')
  })
  it('does not invent dates for historical or invalid values', () => {
    for (const value of [null, '', 'invalid']) {
      const wrapper = mount(DateAdded, { props: { value } })
      expect(wrapper.text()).toBe('Not recorded')
      expect(wrapper.find('time').exists()).toBe(false)
    }
  })
})
