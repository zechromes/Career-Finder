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
  ingestion: {
    searches: 1,
    complete: true,
    collected: { linkedin: 6 },
    kept: 1,
    omitted: 0,
    counts: [
      { stage: 'filter', reason: 'location does not match', board: 'linkedin', count: 3 },
      { stage: 'deduplicate', reason: 'duplicate posting', board: 'linkedin', count: 1 },
      { stage: 'deduplicate', reason: 'already in this workspace', board: 'linkedin', count: 1 },
    ],
  },
  dropped_jobs: [
    {
      id: 'dropped1',
      title: 'Data Analyst',
      company: 'Example',
      location: 'Melbourne',
      url: 'https://example.test/dropped/1',
      board: 'linkedin',
      stage: 'filter',
      reason: 'location does not match',
      description: 'SQL and Python analysis.',
    },
    {
      id: 'dropped2',
      title: 'Python Developer',
      company: 'Example',
      location: 'Sydney',
      url: 'https://example.test/dropped/2',
      board: 'linkedin',
      stage: 'deduplicate',
      reason: 'duplicate posting',
      description: 'Python required. SQL preferred.',
      duplicate_of: {
        title: 'Python Developer',
        company: 'Example',
        url: 'https://example.test/1',
        board: 'indeed',
        description: 'Python required. SQL preferred.',
        method: 'same title, company and location; near-identical description',
      },
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
// Mirror the server's ingestion report for the synthetic dropped postings.
const ingestion = (labels: {
  jobs: Record<string, { fit?: string; duplicate_correct?: boolean }>
}) => {
  const dropped = labels.jobs.dropped1?.fit
  const binary = dropped === 'strong_match' || dropped === 'not_suitable'
  const good = dropped === 'strong_match' ? 1 : 0
  const same = labels.jobs.dropped2?.duplicate_correct
  return {
    available: true,
    complete: true,
    searches: 1,
    collected: 6,
    kept: 1,
    omitted: 0,
    by_reason: [
      {
        stage: 'filter',
        reason: 'location does not match',
        count: 3,
        labeled: binary ? 1 : 0,
        good_fits: good,
      },
      { stage: 'deduplicate', reason: 'duplicate posting', count: 1, labeled: 0, good_fits: 0 },
    ],
    by_board: [{ board: 'linkedin', collected: 6, dropped: 4 }],
    dropped_recorded: 1,
    labeled: binary ? 1 : 0,
    good_fits: good,
    duplicates: {
      recorded: 1,
      judged: same == null ? 0 : 1,
      same: same ? 1 : 0,
      precision: same == null ? null : Number(same),
    },
    search_text: { jobs_checked: 1, quotes: 1, kept: 1, rate: 1, lowest: [] },
  }
}
const stages = (fit: string | undefined, labels: Parameters<typeof ingestion>[0]) => {
  const good = fit === 'strong_match' ? 1 : 0
  const report = ingestion(labels)
  return {
    verdicts_available: true,
    ingestion: report,
    funnel: {
      good_fits: good + report.good_fits,
      lost_at_ingestion: report.good_fits,
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
  http.put('/api/review-datasets/:id/jobs/:job', async ({ request, params }) => {
    const body = (await request.json()) as { revision: number; reviewer: string; review: unknown }
    const labels = read()
    if (labels.revision !== body.revision)
      return HttpResponse.json(
        { detail: 'Reviews changed in another tab. Reload before saving.' },
        { status: 409 },
      )
    labels.jobs[params.job as string] = body.review
    labels.reviewers[params.job as string] = body.reviewer
    labels.revision++
    labels.updated_at = Date.now() / 1000
    sessionStorage.setItem('career-demo-human-reviews', JSON.stringify(labels))
    return HttpResponse.json(labels)
  }),
  http.post('/api/review-datasets/:id/replay', () => {
    const rule = (key: string, name: string, recall: number, added: string[]) => ({
      rule: key,
      name,
      shortlist_size: 1,
      matches_original: key === 'title_only' ? 1 : 0.5,
      metrics: { label_coverage: 1, observed_recall_at_k: recall, precision_on_labeled: 1 },
      good_fits_added: added,
      not_fits_added: [],
      unassessed_added: added.length,
    })
    return HttpResponse.json({
      dataset_id: id,
      embedding_model: 'synthetic',
      ranked_at: 1793100000,
      searches: 1,
      top_k: 1,
      unranked: 0,
      rules: [
        rule('title_only', 'Title only (until 28 Oct 2026)', 0.5, []),
        rule('stated_years', 'Stated years (current)', 1, ['job1']),
      ],
      limitations: ['Synthetic replay'],
    })
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
      stages: stages(review?.fit, labels),
      limitations: ['Synthetic pilot'],
    })
  }),
]
