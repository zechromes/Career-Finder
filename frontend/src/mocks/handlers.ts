// Provide synthetic API responses and browser persistence for isolated UI tests.
import { http, HttpResponse, delay } from 'msw'
import { playgroundHandlers } from './playground'
import type { Run, Profile, Job, Preferences } from '../types/domain'
const profile: Profile = {
  name: 'Alex Example',
  headline: 'Software Developer',
  profile: 'Early-career developer with Python experience.',
  tech_skills: ['Python', 'SQL'],
  soft_skills: ['Communication'],
  years_of_experience: 2,
  preferred_domains: ['Python Developer'],
  work_history: ['Developer, Example, 2024–2026'],
  education: ['Bachelor of Computing'],
  section_headings: ['Experience', 'Education', 'Projects', 'Certifications'],
  sections: [{ heading: 'Projects', entries: ['Job tracker | Personal | 2026 | Python and SQL'] }],
  target_roles_reason: 'Two years of Python development fit junior developer roles.',
  source_text: '',
  career_level: 'junior',
}
const job: Job = {
  requirement_set_id: '',
  requirement_extraction_model: '',
  requirement_extraction_version: '',
  completed_models: 0,
  agreement_count: 0,
  assessment_summary: '',
  postedAt: '2026-09-25',
  applyUrl: 'https://example.com/jobs/1',
  verdict: 'strong_match',
  missingSkills: ['Docker'],
  mismatch_reason: '',
  evaluation_model_id: 'claude-sonnet-5-5',
  score_method: 'legacy',
  company_logo: '',
  job_description: '',
  jobId: 'demo-job',
  title: 'Python Developer',
  company: 'Example Co',
  location: 'Sydney',
  source: 'linkedin',
  posted_at: '2026-09-25',
  apply_url: 'https://example.com/jobs/1',
  score: 84,
  fit_category: 'strong_match',
  verification: 'unverified',
  work_type: 'hybrid',
  rationale: 'Python and SQL experience align with this junior role.',
  missing_skills: ['Docker'],
  about_company: 'Builds developer tools.',
  candidate_requirements: ['Python', 'SQL', '2 years of professional experience'],
  salary: 'AUD 90,000–110,000 per year',
}
const saved = JSON.parse(localStorage.getItem('career-demo-run') || 'null')
let run: Run | null = saved?.run || null
let startTime = saved?.startTime || 0
let searching = saved?.searching || false
let appending = saved?.appending || false
const scenario = () =>
  new URLSearchParams(location.search).get('scenario') || sessionStorage.getItem('mock-scenario')
// Advance synthetic pipeline progress and persist the mock run snapshot.
function snapshot() {
  if (!run) return null
  const elapsed = Date.now() - startTime
  if (run.status === 'running' && !searching && elapsed > 500)
    Object.assign(run, {
      status: 'awaiting_search',
      profile,
      phases: { '1': 'done', '2': 'pending', '3': 'pending', '4': 'pending' },
    })
  if (run.status === 'running' && searching) {
    if (elapsed > 500)
      Object.assign(run, {
        phase: 4,
        evaluation_total: 1,
        phases: { '1': 'done', '2': 'done', '3': 'done', '4': 'active' },
      })
    if (elapsed > 900)
      Object.assign(run, {
        recommendations: appending
          ? [
              ...(run.recommendations || []),
              ...(scenario() === 'no-new' ||
              run.recommendations?.some((item) => item.jobId === 'more-job')
                ? []
                : scenario() === 'append-15'
                  ? Array.from({ length: 15 }, (_, index) => ({
                      ...job,
                      jobId: `more-job-${index}`,
                      title: `New role ${index + 1}`,
                      apply_url: `https://example.com/new/${index}`,
                      applyUrl: `https://example.com/new/${index}`,
                    })).filter(
                      (item) =>
                        !run!.recommendations?.some((previous) => previous.jobId === item.jobId),
                    )
                  : [
                      {
                        ...job,
                        jobId: 'more-job',
                        title:
                          (run.preferences as Partial<Preferences> | undefined)?.queries?.[0] ||
                          'Software Engineer',
                        apply_url: 'https://example.com/jobs/2',
                        applyUrl: 'https://example.com/jobs/2',
                      },
                    ]),
            ]
          : scenario() === 'zero' || scenario() === 'scrape-failure'
            ? []
            : [job],
        evaluated_jobs: 1,
      })
    if (elapsed > 2200 && scenario() !== 'evaluating')
      Object.assign(run, {
        status: scenario() === 'scrape-failure' ? 'error' : 'complete',
        message: appending
          ? scenario() === 'no-new'
            ? 'No new jobs found. Your existing results are kept.'
            : 'More jobs added. Your existing results are kept.'
          : 'Evaluation finished',
        error: scenario() === 'scrape-failure' ? 'Scraper timed out. Retry scraping.' : null,
        scrape_errors:
          scenario() === 'scrape-failure' ? ['LinkedIn description request failed.'] : [],
        skipped_models:
          scenario() === 'model-skipped'
            ? [
                'Google Gemini · gemini-4-argon was skipped: Provider quota is exhausted. Verdicts use the remaining models; retry it once it is available.',
              ]
            : [],
        busy_boards:
          scenario() === 'board-busy'
            ? [
                'LinkedIn limited how many jobs could be loaded this time, so you may see fewer jobs from it. Nothing needs to change on your side.',
              ]
            : [],
        phases: { '1': 'done', '2': 'done', '3': 'done', '4': 'done' },
      })
  }
  if (run.status === 'complete' && run.profile && !run.saved_profile_id) {
    const savedProfile = {
      id: crypto.randomUUID(),
      name: run.profile.name || 'Saved resume',
      profile: run.profile,
      preferences: (run.preferences || null) as Preferences | null,
      resume_available: true,
      updated_at: Date.now() / 1000,
    }
    profiles.push(savedProfile)
    persistProfiles()
    run.saved_profile_id = savedProfile.id
    run.saved_profile_name = savedProfile.name
  }
  run.revision = (run.revision || 0) + 1
  localStorage.setItem('career-demo-run', JSON.stringify({ run, startTime, searching, appending }))
  return structuredClone(run)
}
type SavedProfile = {
  id: string
  name: string
  profile: Profile
  preferences: Preferences | null
  updated_at: number
  resume_available?: boolean
}
let profiles: SavedProfile[] = JSON.parse(localStorage.getItem('career-demo-profiles') || '[]')
// Keep synthetic saved profiles available across test-page reloads.
function persistProfiles() {
  localStorage.setItem('career-demo-profiles', JSON.stringify(profiles))
}
const apiKeys: { provider: string; label: string; source: string | null; hint: string }[] = [
  { provider: 'openai', label: 'OpenAI GPT', source: null, hint: '' },
  { provider: 'anthropic', label: 'Anthropic Claude', source: null, hint: '' },
  { provider: 'google', label: 'Google Gemini', source: null, hint: '' },
]
export const handlers = [
  ...playgroundHandlers,
  http.get('/api/searches/:id/actions', () => {
    const key = 'career-demo-actions:' + (run?.saved_profile_id || run?.id || '')
    return HttpResponse.json({
      actions: JSON.parse(localStorage.getItem(key) || '{}'),
      dismissal_feedback: JSON.parse(localStorage.getItem(key + ':feedback') || '{}'),
    })
  }),
  http.put('/api/searches/:id/actions', async ({ request }) => {
    const key = 'career-demo-actions:' + (run?.saved_profile_id || run?.id || '')
    const actions = JSON.parse(localStorage.getItem(key) || '{}')
    const body = (await request.json()) as {
      key: string
      action: string
      value: boolean
      dismissal?: { reason: string } | null
    }
    const feedback = JSON.parse(localStorage.getItem(key + ':feedback') || '{}')
    if (body.action === 'dismissed') {
      if (!body.value || body.dismissal === null) delete feedback[body.key]
      else if (body.dismissal) {
        const job = [
          ...(run?.recommendations || []),
          ...(run?.excluded_recommendations || []),
        ].find((job) => job.apply_url === body.key || job.jobId === body.key)
        feedback[body.key] = {
          ...body.dismissal,
          title: job?.title || '',
          location: job?.location || '',
          seniority: '',
        }
      }
    }
    localStorage.setItem(key + ':feedback', JSON.stringify(feedback))
    actions[body.key] = { ...actions[body.key], [body.action]: body.value }
    localStorage.setItem(key, JSON.stringify(actions))
    return HttpResponse.json({ actions, dismissal_feedback: feedback })
  }),

  http.get('/api/locations/suggest', () =>
    HttpResponse.json([
      { label: 'Sydney, New South Wales, Australia', value: 'Sydney, New South Wales, Australia' },
    ]),
  ),
  http.get('/api/profiles', () => HttpResponse.json(profiles)),
  http.post('/api/profiles', async ({ request }) => {
    const body = (await request.json()) as SavedProfile
    const saved = {
      ...body,
      resume_available: true,
      id: crypto.randomUUID(),
      updated_at: Date.now() / 1000,
    }
    profiles.push(saved)
    persistProfiles()
    if (run) {
      run.saved_profile_id = saved.id
      run.saved_profile_name = saved.name
      snapshot()
    }
    return HttpResponse.json(saved, { status: 201 })
  }),
  http.put('/api/profiles/:id', async ({ request, params }) => {
    const body = (await request.json()) as SavedProfile
    const saved = {
      ...profiles.find((item) => item.id === params.id),
      ...body,
      id: String(params.id),
      updated_at: Date.now() / 1000,
    }
    profiles = profiles.map((item) => (item.id === params.id ? saved : item))
    persistProfiles()
    return HttpResponse.json(saved)
  }),
  http.delete('/api/profiles/:id', ({ params }) => {
    profiles = profiles.filter((item) => item.id !== params.id)
    persistProfiles()
    return HttpResponse.json({ deleted: true })
  }),
  http.post('/api/profiles/:id/searches', ({ params, request }) => {
    const saved = profiles.find((item) => item.id === params.id)
    if (!saved || !run) return HttpResponse.json({ detail: 'Profile not found' }, { status: 404 })
    if (run.status === 'complete' && new URL(request.url).searchParams.get('fresh') !== 'true')
      return HttpResponse.json({ id: run.id, runId: run.id }, { status: 201 })
    run = {
      ...run,
      id: 'continued',
      runId: 'continued',
      saved_profile_id: saved.id,
      saved_profile_name: saved.name,
      profile: saved.profile,
      preferences: saved.preferences || {},
      status: 'awaiting_search',
      phase: 1,
      recommendations: [],
      excluded_recommendations: [],
    }
    searching = false
    snapshot()
    return HttpResponse.json({ id: 'continued', runId: 'continued' }, { status: 201 })
  }),
  http.get('/api/config', () => HttpResponse.json({ evaluation_provider: 'claude' })),
  http.get('/api/settings/keys', () => HttpResponse.json(apiKeys)),
  http.put('/api/settings/keys/:provider', ({ params }) => {
    const item = apiKeys.find((key) => key.provider === params.provider)
    if (item) Object.assign(item, { source: 'settings', hint: '…mock' })
    return HttpResponse.json(apiKeys)
  }),
  http.delete('/api/settings/keys/:provider', ({ params }) => {
    const item = apiKeys.find((key) => key.provider === params.provider)
    if (item) Object.assign(item, { source: null, hint: '' })
    return HttpResponse.json(apiKeys)
  }),
  http.get('/api/models/resume', () =>
    HttpResponse.json([
      { value: 'openai', label: 'gpt-4o-mini' },
      { value: 'anthropic', label: 'claude-sonnet-4-5-20250929' },
    ]),
  ),
  http.get('/api/models/evaluation', () =>
    HttpResponse.json([
      { value: 'claude', label: 'claude-sonnet-5-5' },
      { value: 'gpt', label: 'gpt-6.1-sol' },
      { value: 'gemini', label: 'gemini-4-argon' },
    ]),
  ),
  http.post('/api/resumes/upload', async () => {
    await delay(100)
    if (scenario() === 'not-resume') {
      return HttpResponse.json(
        {
          detail:
            'This file does not appear to be a resume/CV. Please upload your resume or CV as a PDF.',
        },
        { status: 422 },
      )
    }
    startTime = Date.now()
    searching = false
    appending = false
    run = {
      last_search_added: 0,
      saved_profile_name: '',
      message: '',
      jobs_found: 0,
      jobs_screened: 0,
      evaluation_total: 0,
      evaluated_jobs: 0,
      evaluation_failed: 0,
      retry_total: 0,
      retry_done: 0,
      displayed_jobs: 0,
      excluded_jobs: 0,
      evaluation_model: 'claude',
      evaluation_model_id: 'claude-sonnet-5-5',
      revision: 0,
      worker_active: false,
      id: 'demo',
      runId: 'demo',
      status: 'awaiting_search',
      profile,
      phase: 1,
      phases: { '1': 'done', '2': 'pending', '3': 'pending', '4': 'pending' },
      recommendations: [],
      excluded_recommendations: [],
    }
    return HttpResponse.json({ id: 'demo', runId: 'demo' }, { status: 201 })
  }),
  http.get('/api/searches/:id', () =>
    snapshot()
      ? HttpResponse.json(snapshot())
      : HttpResponse.json({ detail: 'Run not found' }, { status: 404 }),
  ),
  http.get('/api/searches/:id/progress', ({ request }) => {
    if (scenario() === 'polling') return HttpResponse.error()
    let timer: ReturnType<typeof setTimeout>
    const stream = new ReadableStream({
      start(controller) {
        const send = () => {
          if (request.signal.aborted) {
            controller.close()
            return
          }
          const data = snapshot()
          controller.enqueue(
            new TextEncoder().encode(`event: phase_update\ndata: ${JSON.stringify(data)}\n\n`),
          )
          if (!data || data.status !== 'running') {
            controller.close()
            return
          }
          timer = setTimeout(send, 250)
        }
        send()
      },
      cancel() {
        clearTimeout(timer)
      },
    })
    return new HttpResponse(stream, {
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
    })
  }),
  http.put('/api/searches/:id/confirm-profile', async ({ request }) => {
    const body = (await request.json()) as { profile: Profile; preferences: Preferences }
    appending = false
    if (run)
      Object.assign(run, {
        profile: body.profile,
        preferences: body.preferences,
        status: 'running',
        phase: 2,
        message: 'Collecting vacancies',
      })
    startTime = Date.now()
    searching = true
    return HttpResponse.json({ id: 'demo', runId: 'demo' }, { status: 202 })
  }),
  http.post('/api/searches/:id/find-more', async ({ request }) => {
    if (!run) return HttpResponse.json({ detail: 'Run not found' }, { status: 404 })
    const body = (await request.json()) as { preferences: Preferences }
    Object.assign(run, {
      preferences: body.preferences,
      status: 'running',
      phase: 2,
      message: 'Looking for more jobs; existing results are kept.',
      error: null,
    })
    startTime = Date.now()
    searching = true
    appending = true
    return HttpResponse.json({ id: run.id, runId: run.id }, { status: 202 })
  }),
  http.post('/api/searches/:id/retry-scraping', () => {
    if (!run) return HttpResponse.json({ detail: 'Run not found' }, { status: 404 })
    Object.assign(run, {
      status: 'running',
      phase: 2,
      error: null,
      scrape_errors: [],
      message: 'Retrying failed sources; keeping your previous results',
    })
    startTime = Date.now()
    searching = true
    appending = true
    return HttpResponse.json({ id: run.id, runId: run.id }, { status: 202 })
  }),
  http.post('/api/searches/:id/cancel', () => {
    if (run) run.status = 'cancelled'
    return HttpResponse.json(run)
  }),
  http.delete('/api/searches/:id', () => {
    run = null
    localStorage.removeItem('career-demo-run')
    return HttpResponse.json({ deleted: true, deletion_pending: false })
  }),
]
