// Exercise theme behavior with controlled fixtures and explicit assertions.
import { afterEach, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ThemeToggle from '../src/components/ThemeToggle.vue'

// Release test state and restore patched dependencies.
afterEach(() => {
  document.documentElement.classList.remove('dark')
  document.documentElement.style.colorScheme = ''
})

it('switches the document theme and saves the choice across remounts', async () => {
  const wrapper = mount(ThemeToggle)
  await wrapper.get('button').trigger('click')
  expect(document.documentElement.classList.contains('dark')).toBe(true)
  expect(document.documentElement.style.colorScheme).toBe('dark')
  expect(localStorage.getItem('careerTheme')).toBe('dark')
  wrapper.unmount()
  const restored = mount(ThemeToggle)
  expect(restored.get('button').attributes('aria-pressed')).toBe('true')
  await restored.get('button').trigger('click')
  expect(document.documentElement.classList.contains('dark')).toBe(false)
  expect(localStorage.getItem('careerTheme')).toBe('light')
  restored.unmount()
})
