// Exercise job description behavior with controlled fixtures and explicit assertions.
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import JobDescription from '../src/components/JobDescription.vue'

it('formats posting headings, paragraphs and lists without executing source HTML', () => {
  const wrapper = mount(JobDescription, {
    props: {
      text: '# About the job\nA meaningful role.\n\n**Requirements**\n- Python\n- SQL\n\n<script>alert(1)</script>',
    },
  })
  expect(wrapper.findAll('h3').map((node) => node.text())).toEqual([
    'About the job',
    'Requirements',
  ])
  expect(wrapper.findAll('li').map((node) => node.text())).toEqual(['Python', 'SQL'])
  expect(wrapper.find('script').exists()).toBe(false)
  expect(wrapper.text()).toContain('<script>alert(1)</script>')
})

it('shows an explicit missing description message', () => {
  expect(mount(JobDescription).text()).toContain('The source did not return a job description.')
})

it('cleans scraper artifacts, preserves numbered lists and formats inline metadata and links', () => {
  const wrapper = mount(JobDescription, {
    props: {
      text: '**Salary:** $100,000\n\nA sentence wrapped\nover two lines.\n\n1. First step\n\n2. Second step\n* undefined\n\n[Company website](https://example.com)',
    },
  })
  expect(wrapper.get('strong').text()).toBe('Salary:')
  expect(wrapper.text()).toContain('A sentence wrapped over two lines.')
  expect(wrapper.get('ol').findAll('li')).toHaveLength(2)
  expect(wrapper.text()).not.toContain('undefined')
  expect(wrapper.get('a').attributes('href')).toBe('https://example.com')
})
