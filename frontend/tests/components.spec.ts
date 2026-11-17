// Exercise components behavior with controlled fixtures and explicit assertions.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import UploadZone from '../src/components/UploadZone.vue'
import ProfileReview from '../src/components/ProfileReview.vue'
import JobCard from '../src/components/JobCard.vue'
import JobDashboard from '../src/components/JobDashboard.vue'
import { useProfileStore } from '../src/stores/profile'
import { useJobsStore } from '../src/stores/jobs'
import { useSnackbarStore } from '../src/stores/snackbar'
const job = {
  jobId: 'a',
  title: 'Developer',
  company: 'Example',
  score: 85,
  fit_category: 'strong_match',
  location: 'Sydney',
  source: 'linkedin',
  apply_url: 'https://example.com',
  missing_skills: ['SQL'],
  candidate_requirements: ['Python'],
  about_company: 'Software company',
  salary: 'AUD 100,000',
}

it('shows retry loading and restores the action after retry finishes', async () => {
  const wrapper = mount(JobDashboard, {
    props: { evaluationErrors: [{ title: 'Developer', message: 'Timed out' }] },
  })
  const button = () => wrapper.findAll('button').find((item) => item.text().includes('Retry'))!
  await button().trigger('click')
  expect(wrapper.emitted('retry-evaluation')).toHaveLength(1)
  await wrapper.setProps({ retryingEvaluations: true, busy: true })
  expect(button().text()).toBe('Retrying evaluations…')
  expect(button().attributes('disabled')).toBeDefined()
  expect(button().attributes('aria-busy')).toBe('true')
  expect(wrapper.find('[role="status"]').text()).toContain('Successful assessments are kept')
  await wrapper.setProps({ busy: false, running: true })
  expect(button().attributes('disabled')).toBeDefined()
  await wrapper.setProps({ retryingEvaluations: false, running: false })
  expect(button().text()).toBe('Retry failed evaluations')
  expect(button().attributes('disabled')).toBeUndefined()
})
it('groups failed assessments by model and reason instead of listing every job', () => {
  const wrapper = mount(JobDashboard, {
    props: {
      evaluationOptions: [{ value: 'claude', label: 'Anthropic Claude' }],
      evaluationErrors: [
        { title: 'Developer', provider: 'claude', category: 'credentials', message: 'Key rejected' },
        { title: 'Analyst', provider: 'claude', category: 'credentials', message: 'Key rejected' },
        { title: 'Tester', provider: 'gpt', category: 'rate_limit', message: 'Too many requests' },
      ],
    },
  })
  const chips = wrapper.findAll('[aria-label="Failures by model"] li').map((item) => item.text())
  expect(chips).toEqual(['Anthropic Claude · Key rejected · 2 jobs', 'gpt · Rate limit · 1 job'])
  expect(wrapper.find('details').text()).toContain('Developer · Analyst')
})
it('shows the verdict as a colored chip in the results table', async () => {
  const wrapper = mount(JobDashboard, {
    props: { jobs: [job, { ...job, jobId: 'b', apply_url: 'https://example.com/b', fit_category: 'review' }] },
  })
  await wrapper.findAll('button').find((item) => item.text().includes('Table'))!.trigger('click')
  const chips = wrapper.findAll('tbody td span.rounded-full')
  expect(chips.map((chip) => chip.text())).toEqual(['Strong match', 'For review'])
  expect(chips[0].classes()).toContain('bg-emerald-50')
  expect(chips[1].classes()).toContain('bg-amber-50')
})
// Reset shared fixtures and mocks between test cases.
beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})
function drop(wrapper: ReturnType<typeof mount>, file: File) {
  return wrapper.trigger('drop', { dataTransfer: { files: [file] } })
}
describe('Upload validation and accessibility', () => {
  it.each([
    [new File(['x'], 'resume.txt', { type: 'text/plain' }), 'PDF'],
    [new File([], 'empty.pdf', { type: 'application/pdf' }), 'empty'],
    [
      new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.pdf', { type: 'application/pdf' }),
      '5 MB',
    ],
    [new File(['x'], 'spoof.pdf', { type: 'text/plain' }), 'PDF'],
  ])('rejects invalid files', async (file, message) => {
    const wrapper = mount(UploadZone)
    await drop(wrapper, file)
    expect(wrapper.get('[role="alert"]').text()).toContain(message)
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0] ?? null).toBeNull()
  })
  it('accepts a valid file and supports keyboard opening', async () => {
    const wrapper = mount(UploadZone)
    const click = vi.spyOn(wrapper.get('input').element, 'click')
    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(click).toHaveBeenCalled()
    const file = new File(['%PDF-1.4'], 'resume.pdf', { type: 'application/pdf' })
    await drop(wrapper, file)
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([file])
  })
  it('ignores drop and keyboard events when disabled', async () => {
    const wrapper = mount(UploadZone, { props: { disabled: true } })
    const click = vi.spyOn(wrapper.get('input').element, 'click')
    await wrapper.trigger('keydown', { key: 'Enter' })
    await drop(wrapper, new File(['x'], 'resume.pdf', { type: 'application/pdf' }))
    expect(click).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
it('edits profile before confirmation and uses backend model labels', async () => {
  const wrapper = mount(ProfileReview, {
    props: { models: [{ value: 'gpt', label: 'configured-model' }] },
  })
  const store = useProfileStore()
  await wrapper.findAll('input')[0].setValue('Edited name')
  expect(store.draft.name).toBe('Edited name')
  expect(wrapper.text()).toContain('configured-model')
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('confirm')).toBeUndefined()
  store.preferences.queries = ['Developer']
  store.preferences.locations = []
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('confirm')).toHaveLength(1)
})
it('shows score, sections, missing skills, safe links and browser actions', async () => {
  const store = useJobsStore()
  store.load('run')
  const wrapper = mount(JobCard, { props: { job: job as any } })
  expect(wrapper.text()).toContain('85/100')
  expect(wrapper.text()).toContain('Not verified')
  expect(wrapper.text()).toContain('Salary')
  expect(wrapper.get('a').attributes('rel')).toBe('noopener noreferrer')
  await wrapper.get('button[aria-label="Actions for Developer at Example"]').trigger('click')
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Save')!
    .trigger('click')
  expect(store.flags(job as any).saved).toBe(true)
  store.load('run')
  expect(store.flags(job as any).saved).toBe(true)
})
it('omits unknown salary, renders untrusted text plainly and blocks unsafe URLs', () => {
  const wrapper = mount(JobCard, {
    props: {
      job: {
        ...job,
        salary: null,
        about_company: '<img src=x onerror=alert(1)>',
        apply_url: 'javascript:alert(1)',
      } as any,
    },
  })
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('a').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('Salary')
})
it('filters and sorts cards and keeps dismissed jobs recoverable', async () => {
  const wrapper = mount(JobDashboard, {
    props: {
      jobs: [
        job,
        {
          ...job,
          jobId: 'b',
          apply_url: 'https://example.com/analyst',
          title: 'Analyst',
          location: 'Melbourne',
          score: 50,
        },
      ] as any,
    },
  })
  expect(wrapper.findAll('article')).toHaveLength(2)
  await wrapper.get('input[type="search"]').setValue('Analyst')
  expect(wrapper.findAll('article')).toHaveLength(1)
  await wrapper.get('input[type="search"]').setValue('')
  useJobsStore().toggle(job as any, 'dismissed')
  await wrapper.vm.$nextTick()
  expect(wrapper.findAll('article')).toHaveLength(1)
  const actions = wrapper.findAll('select').at(-1)!
  await actions.setValue('dismissed')
  expect(wrapper.find('article').text()).toContain('Developer')
})

it('shows assessment summaries without raw descriptions or requirement evidence', () => {
  const wrapper = mount(JobCard, {
    props: {
      job: {
        ...job,
        job_description: 'Raw posting text for analysis only.',
        description_available: true,
        requirement_verdicts: [
          { requirement: 'Private evidence row', verdict: 'met', job_quote: 'Quoted evidence' },
        ],
      } as any,
    },
  })
  const details = wrapper.get('details').text()
  expect(details).not.toContain('Requirement evidence')
  expect(details).not.toContain('Private evidence row')
  expect(details).not.toContain('Job description')
  expect(details).not.toContain('Raw posting text')
  for (const section of [
    'Match rationale',
    'About the company',
    'What the company needs',
    'Salary',
    'Missing skills',
  ]) {
    expect(details).toContain(section)
  }
})

it('copies the application URL and confirms success', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  const wrapper = mount(JobCard, { props: { job: job as any } })
  await wrapper.get('button[aria-label="Actions for Developer at Example"]').trigger('click')
  await wrapper.get('button[aria-label="Copy link for Developer"]').trigger('click')
  expect(writeText).toHaveBeenCalledWith('https://example.com/')
  expect(useSnackbarStore().message).toBe('Link copied to clipboard.')
})
it('offers manual copying when clipboard access fails', async () => {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockRejectedValue(new Error('Denied')) },
  })
  const wrapper = mount(JobCard, { props: { job: job as any } })
  await wrapper.get('button[aria-label="Actions for Developer at Example"]').trigger('click')
  await wrapper.get('button[aria-label="Copy link for Developer"]').trigger('click')
  expect((wrapper.get('input[readonly]').element as HTMLInputElement).value).toBe(
    'https://example.com/',
  )
})

it('switches to table view and keeps per-job actions', async () => {
  const wrapper = mount(JobDashboard, { props: { jobs: [job] as any } })
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Table')!
    .trigger('click')
  expect(wrapper.get('table').text()).toContain('Developer')
  expect(localStorage.getItem('careerResultsView')).toBe('table')
  await wrapper.get('button[aria-label="Actions for Developer at Example"]').trigger('click')
  expect(wrapper.text()).toContain('Mark as applied')
  await wrapper.get('[data-actions]').trigger('keydown', { key: 'Escape' })
  expect(wrapper.find('[data-actions]').exists()).toBe(false)
})

it('combines recommended and excluded jobs without category tabs', async () => {
  const wrapper = mount(JobDashboard, {
    props: {
      jobs: [job] as any,
      excludedJobs: [
        {
          ...job,
          jobId: 'excluded',
          title: 'Senior Architect',
          fit_category: 'not_suitable',
          mismatch_reason: 'Requires ten years of leadership',
        },
      ] as any,
    },
  })
  expect(wrapper.findAll('article')).toHaveLength(2)
  expect(wrapper.find('[aria-label="Result categories"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('Not recommended')
  await wrapper.get('input[type="search"]').setValue('leadership')
  expect(wrapper.findAll('article')).toHaveLength(1)
  expect(wrapper.get('article').text()).toContain('Senior Architect')
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Table')!
    .trigger('click')
  expect(wrapper.get('table').text()).toContain('Not recommended')
})

it('sorts best matches by verdict then score with jobs still being assessed last', async () => {
  const wrapper = mount(JobDashboard, {
    props: {
      jobs: [
        { ...job, jobId: 'review', title: 'Review role', fit_category: 'review', score: 95 },
        { ...job, jobId: 'pending', title: 'Pending role', fit_category: 'review', score: null },
        { ...job, jobId: 'strong-low', title: 'Strong lower', score: 80 },
        { ...job, jobId: 'strong-high', title: 'Strong higher', score: 90 },
      ] as any,
      excludedJobs: [
        {
          ...job,
          jobId: 'excluded',
          title: 'Excluded role',
          fit_category: 'not_suitable',
          score: 30,
        },
      ] as any,
    },
  })
  const titles = () => wrapper.findAll('article h3').map((item) => item.text())
  const expected = ['Strong higher', 'Strong lower', 'Review role', 'Excluded role', 'Pending role']
  expect(titles()).toEqual(expected)
  const sort = wrapper
    .findAll('select')
    .find((select) => select.find('option[value="match"]').exists())!
  expect((sort.element as HTMLSelectElement).value).toBe('match')
  expect(sort.find('option[value="score"]').exists()).toBe(false)
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Table')!
    .trigger('click')
  expect(
    wrapper.findAll('tbody th[scope="row"] > div > div > span').map((item) => item.text()),
  ).toEqual(expected)
})

it('orders model verdicts without scores by shortlist position', async () => {
  const done = { claude: { status: 'complete' } }
  const wrapper = mount(JobDashboard, {
    props: {
      jobs: [
        {
          ...job,
          jobId: 'b',
          title: 'Second',
          score: null,
          shortlist_rank: 1,
          model_evaluations: done,
        },
        {
          ...job,
          jobId: 'w',
          title: 'Waiting',
          score: null,
          shortlist_rank: 0,
          model_evaluations: { claude: { status: 'pending' } },
        },
        {
          ...job,
          jobId: 'r',
          title: 'Review',
          fit_category: 'review',
          score: null,
          shortlist_rank: 0,
          model_evaluations: done,
        },
        {
          ...job,
          jobId: 'a',
          title: 'First',
          score: null,
          shortlist_rank: 0,
          model_evaluations: done,
        },
      ] as any,
    },
  })
  expect(wrapper.findAll('article h3').map((item) => item.text())).toEqual([
    'First',
    'Second',
    'Review',
    'Waiting',
  ])
  expect(wrapper.text()).not.toContain('Score unavailable')
})

it('toggles match ordering from the table header and keeps unscored jobs last', async () => {
  const wrapper = mount(JobDashboard, {
    props: {
      jobs: [
        { ...job, jobId: 'high', title: 'High match', score: 90 },
        { ...job, jobId: 'low', title: 'Low match', score: 30, fit_category: 'not_suitable' },
        { ...job, jobId: 'unknown', title: 'Unscored role', score: null, fit_category: 'review' },
      ] as any,
    },
  })
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Table')!
    .trigger('click')
  const header = () => wrapper.get('th[aria-sort]')
  const titles = () =>
    wrapper.findAll('tbody th[scope="row"] > div > div > span').map((item) => item.text())
  expect(header().attributes('aria-sort')).toBe('descending')
  await header().get('button').trigger('click')
  expect(header().attributes('aria-sort')).toBe('ascending')
  expect(titles()).toEqual(['Low match', 'High match', 'Unscored role'])
  const sort = wrapper
    .findAll('select')
    .find((select) => select.find('option[value="match"]').exists())!
  expect((sort.element as HTMLSelectElement).value).toBe('match_asc')
  await header().get('button').trigger('click')
  expect(titles()).toEqual(['High match', 'Low match', 'Unscored role'])
  await sort.setValue('company')
  expect(header().attributes('aria-sort')).toBe('none')
  await header().get('button').trigger('click')
  expect(header().attributes('aria-sort')).toBe('descending')
})

it('orders pagination controls and supports direct, first and last page navigation', async () => {
  const wrapper = mount(JobDashboard, {
    props: {
      jobs: Array.from({ length: 120 }, (_, index) => ({ ...job, jobId: String(index) })) as any,
    },
  })
  const nav = () => wrapper.get('nav[aria-label="Results pagination"]')
  const button = (label: string) =>
    nav()
      .findAll('button')
      .find((item) => (item.attributes('aria-label') || item.text()) === label)!
  expect(
    nav()
      .findAll('button')
      .map((item) => item.attributes('aria-label') || item.text()),
  ).toEqual([
    'First page',
    'Previous page',
    'Page 1',
    'Page 2',
    'Page 10',
    'Next page',
    'Last page',
  ])
  expect(nav().text()).toContain('…')
  expect(button('First page').attributes('disabled')).toBeDefined()
  expect(button('Previous page').attributes('disabled')).toBeDefined()
  await button('Last page').trigger('click')
  expect(button('Page 10').attributes('aria-current')).toBe('page')
  expect(button('Next page').attributes('disabled')).toBeDefined()
  expect(button('Last page').attributes('disabled')).toBeDefined()
  await button('Previous page').trigger('click')
  expect(button('Page 9').attributes('aria-current')).toBe('page')
  await button('Page 8').trigger('click')
  expect(button('Page 8').attributes('aria-current')).toBe('page')
  await button('First page').trigger('click')
  expect(button('Page 1').attributes('aria-current')).toBe('page')
  await wrapper.get('input[type="search"]').setValue('no-matching-postings')
  expect(wrapper.find('nav[aria-label="Results pagination"]').exists()).toBe(false)
})

it('restores workspace pagination and filters after the results component remounts', async () => {
  const jobs = Array.from({ length: 36 }, (_, index) => ({
    ...job,
    jobId: String(index),
    title: `Developer ${index}`,
  })) as any
  let wrapper = mount(JobDashboard, {
    props: { runId: 'first', jobs },
    global: { stubs: { RouterLink: true } },
  })
  await wrapper.get('input[type="search"]').setValue('Developer')
  await wrapper.get('button[aria-label="Page 3"]').trigger('click')
  wrapper.unmount()
  wrapper = mount(JobDashboard, {
    props: { runId: 'first', jobs: [] },
    global: { stubs: { RouterLink: true } },
  })
  await wrapper.setProps({ jobs })
  expect(wrapper.get('button[aria-label="Page 3"]').attributes('aria-current')).toBe('page')
  expect((wrapper.get('input[type="search"]').element as HTMLInputElement).value).toBe('Developer')
  await wrapper.setProps({ runId: 'second' })
  expect(wrapper.get('button[aria-label="Page 1"]').attributes('aria-current')).toBe('page')
  expect((wrapper.get('input[type="search"]').element as HTMLInputElement).value).toBe('')
  await wrapper.setProps({ runId: 'first' })
  expect(wrapper.get('button[aria-label="Page 3"]').attributes('aria-current')).toBe('page')
  await wrapper.setProps({ jobs: jobs.slice(0, 15) })
  expect(wrapper.get('button[aria-label="Page 2"]').attributes('aria-current')).toBe('page')
  await wrapper.get('input[type="search"]').setValue('Developer 1')
  expect(wrapper.get('button[aria-label="Page 1"]').attributes('aria-current')).toBe('page')
  wrapper.unmount()
})

it('shows all active table statuses and updates them when actions change', async () => {
  localStorage.setItem('careerResultsView', 'table')
  const store = useJobsStore()
  const wrapper = mount(JobDashboard, { props: { jobs: [job] as any } })
  const status = () => wrapper.get('tbody tr').findAll('td')[4]!
  expect(status().text()).toBe('No status')
  store.toggle(job as any, 'saved')
  store.toggle(job as any, 'applied')
  await wrapper.vm.$nextTick()
  expect(status().text()).toContain('Saved')
  expect(status().text()).toContain('Applied')
  expect(status().text()).not.toContain('No status')
  store.dismiss(job as any, null)
  await wrapper.vm.$nextTick()
  expect(wrapper.find('tbody tr').exists()).toBe(false)
  await wrapper
    .findAll('select')
    .find((select) => select.find('option[value="dismissed"]').exists())!
    .setValue('dismissed')
  expect(status().text()).toContain('Dismissed')
  expect(status().text()).toContain('Saved')
  expect(status().text()).toContain('Applied')
  store.toggle(job as any, 'saved')
  store.toggle(job as any, 'applied')
  await wrapper.vm.$nextTick()
  expect(status().text()).toBe('Dismissed')
})
