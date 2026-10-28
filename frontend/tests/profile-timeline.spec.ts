// Exercise profile timeline behavior with controlled fixtures and explicit assertions.
import { expect, it } from 'vitest'
import { displayTimelineEntry, updateTimelineField } from '../src/utils/profileTimeline'
it('formats month ranges and separates the role, company and details', () => {
  expect(displayTimelineEntry('Engineer | Acme, Inc. | Jan 2022 - Sep 2024 | Built APIs')).toEqual({
    date: 'January 2022 – September 2024',
    title: 'Engineer',
    company: 'Acme, Inc.',
    detail: 'Built APIs',
  })
})
it('supports numeric dates and ongoing employment', () => {
  expect(displayTimelineEntry('Developer at Example, 03/2023 – Present')).toMatchObject({
    date: 'March 2023 – Present',
    title: 'Developer',
    company: 'Example',
  })
  expect(displayTimelineEntry('Degree | University | 2020-02 to 2023-11').date).toBe(
    'February 2020 – November 2023',
  )
})
it('does not invent missing months or dates', () => {
  expect(displayTimelineEntry('Developer, Example, 2024–2026').date).toBe('2024 – 2026')
  expect(displayTimelineEntry('Bachelor of Computing').date).toBe('')
})

it('keeps multiline descriptions and does not shift missing company or dates', () => {
  const updated = updateTimelineField(
    'Engineer | | |',
    'detail',
    'Built APIs.\nReduced latency by 20%.',
  )
  expect(displayTimelineEntry(updated)).toEqual({
    title: 'Engineer',
    company: '',
    date: '',
    detail: 'Built APIs.\nReduced latency by 20%.',
  })
  expect(displayTimelineEntry(updateTimelineField(updated, 'company', 'Example')).detail).toBe(
    'Built APIs.\nReduced latency by 20%.',
  )
})
