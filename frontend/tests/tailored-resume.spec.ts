// Tailored resume panel: saved preview, honesty callouts, generation and copy; no network.
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TailoredResume from '../src/components/TailoredResume.vue'

const resume = {
  name: 'Sam Example',
  headline: 'Data Engineer',
  contact: ['sam@example.test', 'linkedin.com/in/sam', 'Sydney'],
  profile_points: ['Built Python ETL pipelines at Acme', 'Led code reviews'],
  skills: ['Python', 'Airflow'],
  sections: [
    {
      title: 'Relevant Experience',
      entries: [
        { heading: 'Data Engineer, Acme', dates: '2023 - Present', bullets: ['Built ETL'] },
        { heading: 'Analyst', organization: 'Beta', location: 'Remote', dates: 'Mar 2021 - Dec 2021', bullets: ['Wrote SQL'] },
      ],
    },
    { title: 'Referees', entries: [{ heading: 'Jo Lee', organization: 'Acme', bullets: ['Contact details available upon request'] }] },
  ],
  gaps: ['Kubernetes'],
  unverified: ['Cut costs by 30%.'],
  model: 'claude-model',
  generated_at: 1_800_000_000,
}
const job = { title: 'Data Engineer', company: 'Example Co', apply_url: 'https://example.test/1' }

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

it('shows a saved resume with what to check and what is missing', () => {
  const wrapper = mount(TailoredResume, {
    props: { job: { ...job, tailored_resume: resume } as any, runId: 'run1' },
  })
  const preview = wrapper.get('#tailored-resume-print')
  expect(preview.text()).toContain('Sam Example')
  // The guide's order: Career Profile, sections, Technical Skills, then Referees last.
  expect(preview.findAll('h4').map((heading) => heading.text())).toEqual([
    'Career Profile',
    'Relevant Experience',
    'Technical Skills',
    'Referees',
  ])
  expect(preview.findAll('ul')[0].findAll('li').map((li) => li.text())).toEqual(resume.profile_points)
  expect(preview.text()).toContain('Python, Airflow')
  expect(preview.text()).toContain('sam@example.test | linkedin.com/in/sam | Sydney')
  expect(preview.findAll('a').map((link) => link.attributes('href'))).toEqual([
    'mailto:sam@example.test',
    'https://linkedin.com/in/sam',
  ])
  // ATS-friendly: no tables, images, icons or multi-column grids.
  expect(preview.findAll('table, img, svg, [class*="grid"]')).toHaveLength(0)
  // Title with dates on one line, then the organisation and location.
  const analyst = preview.findAll('.resume-entry')[1].findAll('p')
  expect(analyst[0].text()).toBe('Analyst Mar 2021 - Dec 2021')
  expect(analyst[1].text()).toBe('Beta, Remote')
  expect(preview.text()).toContain('Built ETL')
  // Gaps and unverified lines are shown to the user, never inside the printable sheet.
  expect(preview.text()).not.toContain('Kubernetes')
  expect(wrapper.text()).toContain('Check before sending')
  expect(wrapper.text()).toContain('Cut costs by 30%.')
  expect(wrapper.get('[aria-label="Requirements not shown on your resume"]').text()).toBe('Kubernetes')
  expect(wrapper.find('button').text()).toBe('Regenerate')
})

it('generates a resume for this job and copies it as text', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => resume })
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('fetch', fetch)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const wrapper = mount(TailoredResume, { props: { job: job as any, runId: 'run1' } })
  expect(wrapper.text()).toContain('No tailored resume yet')
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(fetch).toHaveBeenCalledWith(
    '/api/searches/run1/tailored-resume',
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ key: job.apply_url }) }),
  )
  expect(wrapper.get('#tailored-resume-print').text()).toContain('Sam Example')
  await wrapper.findAll('button').find((item) => item.text() === 'Copy text')!.trigger('click')
  await flushPromises()
  const text = writeText.mock.calls[0][0]
  expect(text).toContain('CAREER PROFILE\n• Built Python ETL pipelines at Acme\n• Led code reviews')
  expect(text).toContain('RELEVANT EXPERIENCE\nData Engineer, Acme | 2023 - Present\n• Built ETL')
  expect(text).toContain('Analyst | Mar 2021 - Dec 2021\nBeta, Remote\n• Wrote SQL')
  // Technical Skills comes before Referees, which closes the resume.
  expect(text.indexOf('TECHNICAL SKILLS')).toBeLessThan(text.indexOf('REFEREES'))
  expect(wrapper.text()).toContain('Copied to the clipboard.')
})

it('shows the server error when generation fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: 'Key rejected' }) }),
  )
  const wrapper = mount(TailoredResume, { props: { job: job as any, runId: 'run1' } })
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toBe('Key rejected')
})

it('prints only the resume, with no browser header room and its own title, then restores the page', async () => {
  document.title = 'Career Finder'
  const print = vi.fn(() => {
    // While the dialog is open: zero page margin (no date/title/URL headers), resume title.
    expect(document.head.textContent).toContain('@page { margin: 0; }')
    expect(document.documentElement.classList.contains('printing-resume')).toBe(true)
    expect(document.title).toBe('Sam Example Resume')
  })
  vi.stubGlobal('print', print)
  const wrapper = mount(TailoredResume, {
    props: { job: { ...job, tailored_resume: resume } as any, runId: 'run1' },
    attachTo: document.body,
  })
  // A print-only copy sits directly under <body>, outside the app.
  expect(document.querySelector('body > .resume-print-root')?.textContent).toContain('Sam Example')
  await wrapper.findAll('button').find((item) => item.text() === 'Download PDF')!.trigger('click')
  expect(print).toHaveBeenCalledOnce()
  window.dispatchEvent(new Event('afterprint'))
  expect(document.title).toBe('Career Finder')
  expect(document.head.textContent).not.toContain('@page')
  expect(document.documentElement.classList.contains('printing-resume')).toBe(false)
  wrapper.unmount()
})
