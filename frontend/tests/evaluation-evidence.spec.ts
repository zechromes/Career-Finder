// Exercise evaluation evidence behavior with controlled fixtures and explicit assertions.
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import EvaluationEvidence from '../src/components/EvaluationEvidence.vue'

it('switches between independent model assessments and distinguishes failure from missing evidence', async () => {
  const wrapper = mount(EvaluationEvidence, {
    props: {
      job: {
        model_evaluations: {
          claude: {
            provider: 'claude',
            evaluation_model_id: 'claude-model',
            status: 'complete',
            score: 80,
            fit_category: 'strong_match',
            rationale: 'Claude rationale',
            requirement_verdicts: [
              {
                requirement: 'Python',
                importance: 'must_have',
                verdict: 'met',
                job_quote: 'Python required',
                resume_quote: 'Built Python APIs',
                job_evidence_verified: true,
                resume_evidence_verified: true,
              },
            ],
          },
          gpt: {
            provider: 'gpt',
            evaluation_model_id: 'gpt-model',
            status: 'failed',
            error: 'Quota unavailable',
          },
          gemini: {
            provider: 'gemini',
            evaluation_model_id: 'gemini-model',
            status: 'complete',
            score: 40,
            fit_category: 'review',
            rationale: 'Gemini rationale',
            requirement_verdicts: [],
          },
        },
      } as any,
    },
  })
  expect(wrapper.text()).toContain('Claude rationale')
  expect(wrapper.text()).toContain('Built Python APIs')
  await wrapper.findAll('button')[1].trigger('click')
  expect(wrapper.text()).toContain('Quota unavailable')
  expect(wrapper.text()).not.toContain('Claude rationale')
  await wrapper.findAll('button')[2].trigger('click')
  expect(wrapper.text()).toContain('Gemini rationale')
  expect(wrapper.text()).toContain('Requirement-level evidence is unavailable')
})

it('lists requirements gaps first, filters by verdict and resets the filter for another model', async () => {
  const row = (requirement: string, verdict: string, importance = 'must_have') => ({
    requirement,
    verdict,
    importance,
    job_quote: `${requirement} required`,
    resume_quote: `Used ${requirement}`,
    explanation: `${requirement} explained`,
  })
  const wrapper = mount(EvaluationEvidence, {
    props: {
      job: {
        model_evaluations: {
          claude: {
            status: 'complete',
            requirement_verdicts: [
              row('Python', 'met'),
              row('Kubernetes', 'not_met'),
              row('Docker', 'partial', 'nice_to_have'),
              row('SQL', 'partial'),
            ],
          },
          gpt: { status: 'complete', requirement_verdicts: [row('Python', 'met')] },
        },
      } as any,
    },
  })
  const requirements = () =>
    wrapper.findAll('summary').map((item) => item.find('.font-medium').text())
  // Not met, then partial (required before preferred), then met.
  expect(requirements()).toEqual(['Kubernetes', 'SQL', 'Docker', 'Python'])
  // Explanations show without opening a row; quotes are inside it.
  expect(wrapper.find('summary').text()).toContain('Kubernetes explained')
  expect(wrapper.find('details').find('blockquote').text()).toBe('Kubernetes required')
  const filters = wrapper.get('[aria-label="Show requirements by verdict"]')
  const partial = filters.findAll('button').find((item) => item.text().includes('Partially met'))!
  await partial.trigger('click')
  expect(partial.attributes('aria-pressed')).toBe('true')
  expect(requirements()).toEqual(['SQL', 'Docker'])
  await partial.trigger('click')
  expect(requirements()).toHaveLength(4)
  await partial.trigger('click')
  await wrapper.get('[aria-label="Evaluation models"]').findAll('button')[1].trigger('click')
  expect(requirements()).toEqual(['Python'])
})

it('clamps a long summary until it is expanded', async () => {
  const wrapper = mount(EvaluationEvidence, {
    props: {
      job: {
        model_evaluations: {
          claude: { status: 'complete', rationale: 'Long reasoning. '.repeat(40), requirement_verdicts: [] },
        },
      } as any,
    },
  })
  const summary = () => wrapper.find('p.max-w-prose')
  const toggle = wrapper.findAll('button').find((item) => item.text() === 'Show full summary')!
  expect(summary().classes()).toContain('line-clamp-4')
  await toggle.trigger('click')
  expect(summary().classes()).not.toContain('line-clamp-4')
  expect(toggle.attributes('aria-expanded')).toBe('true')
})

it('uses shared source sections and labels unclear importance without making it required', () => {
  const wrapper = mount(EvaluationEvidence, {
    props: {
      job: {
        model_evaluations: {
          gpt: {
            status: 'complete',
            requirement_verdicts: [
              {
                requirement_id: 'req_001',
                requirement: 'Build APIs',
                importance: 'unclear',
                type: 'responsibility',
                section: 'What you will do',
                verdict: 'unknown',
                job_quote: 'Build APIs',
                resume_quote: '',
                explanation: 'Evidence is missing.',
              },
            ],
          },
        },
      } as any,
    },
  })
  expect(wrapper.text()).toContain('What you will do')
  expect(wrapper.text()).toContain('Importance unclear')
  expect(wrapper.text()).toContain('Evidence is missing.')
})

it('lists every resume quote for a requirement with its own verification', () => {
  const wrapper = mount(EvaluationEvidence, {
    props: {
      job: {
        model_evaluations: {
          claude: {
            provider: 'claude',
            status: 'complete',
            fit_category: 'strong_match',
            rationale: 'Claude rationale',
            requirement_verdicts: [
              {
                requirement: 'Python',
                importance: 'must_have',
                verdict: 'met',
                job_quote: 'Python required',
                resume_quotes: ['Built Python APIs', 'Python job tracker', 'Invented award'],
                resume_quotes_verified: [true, true, false],
                job_evidence_verified: true,
                resume_evidence_verified: true,
              },
            ],
          },
        },
      } as any,
    },
  })
  const quotes = wrapper.findAll('blockquote').map((item) => item.text())
  expect(quotes).toEqual(
    expect.arrayContaining(['Built Python APIs', 'Python job tracker', 'Invented award']),
  )
  expect(wrapper.text().match(/Verified against resume/g)).toHaveLength(2)
  expect(wrapper.text()).toContain('Quote not verified')
})
