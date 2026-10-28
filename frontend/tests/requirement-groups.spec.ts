// Exercise requirement groups behavior with controlled fixtures and explicit assertions.
import { expect, it } from 'vitest'
import { groupRequirements } from '../src/utils/requirementGroups'
it('groups existing labels and removes repetitive prefixes', () => {
  expect(
    groupRequirements([
      'Required: Python',
      'Responsibility: Build APIs',
      'Preferred: AWS',
      'Must-have: Python',
    ]),
  ).toEqual([
    { title: 'Must-haves', items: ['Python'] },
    { title: 'Responsibilities', items: ['Build APIs'] },
    { title: 'Nice-to-haves', items: ['AWS'] },
  ])
})
it('keeps unclassified requirements without assuming they are mandatory', () => {
  expect(groupRequirements(['Experience with SQL'])).toEqual([
    { title: 'Other requirements', items: ['Experience with SQL'] },
  ])
  expect(groupRequirements([])).toEqual([])
})
