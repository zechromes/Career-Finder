import { expect, it } from 'vitest'
import { requirementSection } from '../src/utils/requirementSections'
it('uses source section headings and keeps ambiguous or absent quotes unclassified', () => {
  const posting =
    '# Qualifications\nPython required\n**Nice to have**\nSQL experience\nWhat you’ll do:\nBuild APIs\n# Benefits\nTraining budget'
  expect(requirementSection(posting, 'Python required')).toBe('Qualifications')
  expect(requirementSection(posting, 'SQL experience')).toBe('Nice to have')
  expect(requirementSection(posting, 'Build APIs')).toBe('Responsibilities')
  expect(requirementSection(posting, 'Training budget')).toBe('Other requirements')
  expect(requirementSection(posting, 'Missing quote')).toBe('Other requirements')
  expect(requirementSection('Python required', 'Python required')).toBe('Other requirements')
  expect(requirementSection('# Qualifications\nPython\n# Nice to have\nPython', 'Python')).toBe(
    'Other requirements',
  )
})
