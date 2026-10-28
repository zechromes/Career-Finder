// Synthetic human-review fixtures. No private workspace data or provider requests.
import { http, HttpResponse } from 'msw'
const id = 'd'.repeat(32)
const dataset = {
  id,
  created_at: 1793100000,
  source_id: 'a'.repeat(32),
  fingerprint: 'b'.repeat(64),
  scope: 'Synthetic full pool',
  split: 'pilot',
  profile: { headline: 'Developer', tech_skills: ['Python'] },
  profile_text: 'Technical skills: Python',
  target_roles: ['Developer'],
  jobs: [
    {
      id: 'job1',
      title: 'Python Developer',
      company: 'Example',
      url: 'https://example.test/1',
      description: 'Python required. SQL preferred.',
      previously_shortlisted: true,
      tags: ['previously_shortlisted'],
      extraction_available: true,
      model_verdicts: {
        gpt: { model: 'synthetic', status: 'complete', fit_category: 'strong_match', score: 85 },
        claude: { model: 'synthetic', status: 'complete', fit_category: 'not_suitable', score: 30 },
      },
      app_verdict: 'review',
      criteria: [
        {
          id: 'criterion1',
          requirement: 'Python',
          importance: 'must_have',
          job_quote: 'Python required.',
          section: '',
          origin: 'shared_extractor',
          extraction_model: 'synthetic',
          extraction_version: 'test',
          set_id: 'set1',
        },
      ],
      evidence: [
        {
          id: 'gpt-0',
          provider: 'gpt',
          model: 'synthetic',
          requirement: 'Python',
          verdict: 'met',
          job_quote: 'Python required.',
          resume_quote: 'Technical skills: Python',
          explanation: 'Python skills align.',
          job_quote_found: true,
          profile_quote_found: true,
        },
      ],
    },
  ],
}
const read = () =>
  JSON.parse(
    sessionStorage.getItem('career-demo-human-reviews') ||
      '{"revision":0,"jobs":{},"reviewers":{},"updated_at":null}',
  )
const deleted = () => sessionStorage.getItem('career-demo-review-deleted') === 'true'
const missing = () => HttpResponse.json({ detail: 'Review dataset not found.' }, { status: 404 })
// Mirror the server's stage report for the single synthetic, shortlisted job.
const generation = (model: string, verdict: string, fit?: string) => {
  const good = fit === 'strong_match'
  const bucket = { strong_match: 0, review: 0, not_suitable: 0, [verdict]: 1 }
  const empty = { strong_match: 0, review: 0, not_suitable: 0 }
  const binary = good || fit === 'not_suitable'
  return {
    model,
    assessed: binary ? 1 : 0,
    failed: 0,
    human_good: good ? bucket : empty,
    human_not_fit: fit === 'not_suitable' ? bucket : empty,
    strong_match_precision: binary && verdict === 'strong_match' ? Number(good) : null,
    good_fit_recall: good ? Number(verdict === 'strong_match') : null,
    good_fits_rejected: good && verdict === 'not_suitable' ? ['job1'] : [],
  }
}
const stages = (fit?: string) => {
  const good = fit === 'strong_match' ? 1 : 0
  return {
    verdicts_available: true,
    funnel: {
      good_fits: good,
      lost_at_retrieval: 0,
      not_assessed: 0,
      rejected_at_generation: 0,
      needs_review: good,
      recommended: 0,
    },
    retrieval_missed: [],
    generation: {
      claude: generation('synthetic', 'not_suitable', fit),
      gpt: generation('synthetic', 'strong_match', fit),
    },
    app: generation('Combined app verdict', 'review', fit),
  }
}
export const reviewDatasetHandlers = [
  http.get('/api/review-datasets', () =>
    HttpResponse.json(
      deleted()
        ? []
        : [
            {
              id,
              created_at: dataset.created_at,
              job_count: 1,
              outside_shortlist: 0,
              reviewed_jobs: read().jobs.job1?.fit ? 1 : 0,
            },
          ],
    ),
  ),
  http.post('/api/review-datasets', () =>
    HttpResponse.json({ dataset, labels: read() }, { status: 201 }),
  ),
  http.get('/api/review-datasets/:id', () =>
    deleted() ? missing() : HttpResponse.json({ dataset, labels: read() }),
  ),
  http.delete('/api/review-datasets/:id', () => {
    if (deleted()) return missing()
    sessionStorage.setItem('career-demo-review-deleted', 'true')
    sessionStorage.removeItem('career-demo-human-reviews')
    return HttpResponse.json({ deleted: true })
  }),
  http.put('/api/review-datasets/:id/jobs/:job', async ({ request }) => {
    const body = (await request.json()) as { revision: number; reviewer: string; review: unknown }
    const labels = read()
    if (labels.revision !== body.revision)
      return HttpResponse.json(
        { detail: 'Reviews changed in another tab. Reload before saving.' },
        { status: 409 },
      )
    labels.jobs.job1 = body.review
    labels.reviewers.job1 = body.reviewer
    labels.revision++
    labels.updated_at = Date.now() / 1000
    sessionStorage.setItem('career-demo-human-reviews', JSON.stringify(labels))
    return HttpResponse.json(labels)
  }),
  http.get('/api/review-datasets/:id/metrics', () => {
    const labels = read()
    const assisted = labels.jobs.job1?.ai_assisted === true
    // AI-assisted reviews are excluded from every metric, as on the server.
    const review = assisted ? undefined : labels.jobs.job1
    const criterion = review?.criteria?.criterion1
    const evidence = review?.evidence?.['gpt-0']
    return HttpResponse.json({
      dataset_id: id,
      revision: labels.revision,
      split: 'pilot',
      pool_size: 1,
      fit_reviewed: review?.fit ? 1 : 0,
      ai_assisted_reviews: assisted ? 1 : 0,
      retrieval: {
        label_coverage: review?.fit ? 1 : 0,
        observed_recall_at_k: review?.fit === 'strong_match' ? 1 : null,
      },
      extraction: {
        total: 1,
        reviewed: criterion?.correct != null ? 1 : 0,
        precision: criterion?.correct == null ? null : Number(criterion.correct),
        importance_accuracy: criterion?.importance
          ? Number(criterion.importance === 'must_have')
          : null,
        completeness_reviewed_jobs: review?.extraction_complete ? 1 : 0,
        missed_requirements: 0,
        recall_on_complete_reviews: review?.extraction_complete ? 1 : null,
      },
      evidence: {
        'gpt:synthetic': {
          total: 1,
          reviewed: evidence?.support ? 1 : 0,
          supported: evidence?.support === 'supported' ? 1 : 0,
          unsupported: evidence?.support === 'unsupported' ? 1 : 0,
          uncertain: evidence?.support === 'uncertain' ? 1 : 0,
          support_rate: ['supported', 'unsupported'].includes(evidence?.support)
            ? Number(evidence.support === 'supported')
            : null,
          verdict_accuracy: evidence?.verdict ? Number(evidence.verdict === 'met') : null,
        },
      },
      stages: stages(review?.fit),
      limitations: ['Synthetic pilot'],
    })
  }),
]
