// Synthetic experiment endpoints; browser tests never call real model providers.
import { http, HttpResponse } from 'msw'
import type { components } from '../types/api'
const sourceId = 'a'.repeat(32)
const fingerprint = 'b'.repeat(64)
const jobs = [
  {
    id: 'python',
    title: 'Python Developer',
    company: 'Example',
    description: 'Build Python services.',
  },
  { id: 'design', title: 'Designer', company: 'Example', description: 'Design illustrations.' },
]
const models = [
  { value: 'gpt', model_id: 'gpt-demo', label: 'OpenAI GPT · gpt-demo' },
  { value: 'claude', model_id: 'claude-demo', label: 'Anthropic Claude · claude-demo' },
  { value: 'gemini', model_id: 'gemini-demo', label: 'Google Gemini · gemini-demo' },
]
const read = () => JSON.parse(sessionStorage.getItem('career-demo-experiment') || 'null')
function snapshot(record: ReturnType<typeof read>) {
  if (!record)
    return HttpResponse.json({ detail: 'Experiment expired or server restarted.' }, { status: 404 })
  const done =
    record.status === 'cancelled' ||
    Date.now() - record.started >
      (sessionStorage.getItem('mock-scenario') === 'eval-slow' ? 60000 : 800)
  return HttpResponse.json({
    ...record,
    status: record.status === 'cancelled' ? 'cancelled' : done ? 'complete' : 'running',
    retrieval: done ? record.retrieval : [],
    generation: done ? record.generation : [],
    message: done ? 'Experiment finished.' : 'Running synthetic experiment.',
  })
}
export const experimentHandlers = [
  http.get('/api/experiments/options', () =>
    HttpResponse.json({
      generation_models: models,
      embedding_models: ['text-embedding-3-small', 'text-embedding-3-large'],
    }),
  ),
  http.get('/api/experiments/sources', () =>
    HttpResponse.json([{ id: sourceId, name: 'Synthetic workspace', job_count: 2 }]),
  ),
  http.get('/api/experiments/sources/:id', () =>
    HttpResponse.json({
      source_id: sourceId,
      fingerprint,
      scope: 'Synthetic collected pool',
      jobs,
    }),
  ),
  http.post('/api/experiments', async ({ request }) => {
    const body = (await request.json()) as components['schemas']['ExperimentRequest']
    if (sessionStorage.getItem('mock-scenario') === 'eval-failure')
      return HttpResponse.json(
        { detail: 'Another experiment is still running. Wait for it to finish.' },
        { status: 409 },
      )
    const labels = body.labels || {}
    const metrics = {
      label_coverage: Object.keys(labels).length / 2,
      observed_recall_at_k: Object.values(labels).some(Boolean) ? 1 : null,
      precision_on_labeled: labels.python === undefined ? null : Number(labels.python),
      missed_labeled_positives: [],
      unlabeled_selected: labels.python === undefined ? 1 : 0,
    }
    const record = {
      id: 'c'.repeat(32),
      source_id: sourceId,
      created_at: Date.now() / 1000,
      started: Date.now(),
      fingerprint,
      scope: 'Synthetic collected pool',
      phase: body.phase,
      top_k: body.top_k,
      pool_size: 2,
      settings: body,
      status: 'running',
      retrieval:
        body.phase === 'generation'
          ? []
          : (body.embedding_models || []).map((model) => ({
              model,
              seconds: 0.12,
              ranked_ids: ['python'],
              metrics,
              error: null,
            })),
      generation:
        body.phase === 'retrieval'
          ? []
          : (body.providers || []).map((provider) => ({
              provider,
              model: models.find((model) => model.value === provider)!.model_id,
              seconds: 0.25,
              input_ids: ['python'],
              errors: [],
              metrics,
              results: [
                {
                  jobId: 'python',
                  title: 'Python Developer',
                  company: 'Example',
                  score: 85,
                  fit_category: 'strong_match',
                  rationale: 'Synthetic assessment.',
                  requirement_verdicts: [],
                },
              ],
            })),
    }
    sessionStorage.setItem('career-demo-experiment', JSON.stringify(record))
    return snapshot(record)
  }),
  http.get('/api/experiments/:id', () => snapshot(read())),
  http.post('/api/experiments/:id/cancel', () => {
    const record = read()
    if (record) {
      record.status = 'cancelled'
      record.retrieval = []
      record.generation = []
      sessionStorage.setItem('career-demo-experiment', JSON.stringify(record))
    }
    return snapshot(record)
  }),
]
