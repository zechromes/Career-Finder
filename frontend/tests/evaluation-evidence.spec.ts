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

it('navigates requirement comparisons with buttons and arrow keys, and resets for another model', async () => {
  const requirements = ['Python', 'SQL'].map((requirement) => ({
    requirement,
    verdict: 'met',
    importance: 'must_have',
    job_quote: `${requirement} required`,
    resume_quote: `Used ${requirement}`,
  }))
  const wrapper = mount(EvaluationEvidence, {
    props: {
      job: {
        model_evaluations: {
          claude: { status: 'complete', requirement_verdicts: requirements },
          gpt: { status: 'complete', requirement_verdicts: requirements.slice(0, 1) },
        },
      } as any,
    },
  })
  const next = wrapper.get('[aria-label="Next requirement"]')
  const previous = wrapper.get('[aria-label="Previous requirement"]')
  expect(previous.attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('Requirement 1 of 2')
  expect(wrapper.text()).not.toContain('SQL required')
  await next.trigger('click')
  expect(wrapper.text()).toContain('SQL required')
  expect(wrapper.text()).toContain('Used SQL')
  expect(wrapper.text()).not.toContain('Python required')
  expect(next.attributes('disabled')).toBeDefined()
  await previous.trigger('keydown', { key: 'ArrowLeft' })
  expect(wrapper.text()).toContain('Requirement 1 of 2')
  await next.trigger('click')
  await wrapper.get('[aria-label="Evaluation models"]').findAll('button')[1].trigger('click')
  expect(wrapper.text()).toContain('Requirement 1 of 1')
  expect(wrapper.text()).toContain('Python required')
  expect(next.attributes('disabled')).toBeDefined()
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
