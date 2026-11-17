// Exercise workflow behavior with controlled fixtures and explicit assertions.
import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
async function upload(page: Page, scenario = '') {
  await page.goto('/' + scenario)
  await expect(page.getByText('Profile extraction · Powered by OpenAI')).toBeVisible()
  await page.locator('input[type=file]').setInputFiles({
    name: 'resume.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 mock fixture'),
  })
  await page.getByRole('button', { name: 'Upload and extract profile' }).click()
  await expect(page.getByRole('heading', { name: 'Review your profile', level: 2 })).toBeVisible()
}
async function confirm(page: Page) {
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Edited Candidate')
  const locations = page.getByRole('combobox', { name: 'Locations', exact: true })
  await locations.fill('Sydney')
  await locations.press('Enter')
  await page.getByRole('button', { name: 'Confirm and find jobs' }).click()
}
test('the profile shows every resume section, flags empty ones and explains target roles', async ({
  page,
}) => {
  await upload(page)
  await expect(page.getByRole('textbox', { name: 'Section heading' })).toHaveValue('Projects')
  await expect(page.getByText('came back empty: Certifications')).toBeVisible()
  await expect(page.getByText(/Suggested from your resume: Two years of Python/)).toBeVisible()
  await page.getByRole('button', { name: 'Add section' }).click()
  await page.getByRole('textbox', { name: 'Section heading' }).last().fill('Certifications')
  await expect(page.getByRole('textbox', { name: 'Section heading' })).toHaveCount(2)
  await page.getByRole('button', { name: 'Remove section Certifications' }).click()
  await expect(page.getByRole('textbox', { name: 'Section heading' })).toHaveCount(1)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('upload, edit, evaluate, filter, actions, route and accessibility', async ({ page }) => {
  await upload(page)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await confirm(page)
  await expect(
    page.getByRole('progressbar', { name: /Job (search|evaluation) progress/ }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Python Developer', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Results as they arrive' })).toBeVisible()
  await expect(page).toHaveURL(/\/run\/demo\/results/)
  await page.getByText('Assessment details', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'About the company' })).toBeVisible()
  await page
    .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
    .click()
  await page
    .getByRole('button', { name: 'Save: Python Developer at Example Co', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Saved: Python Developer at Example Co', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('status').filter({ hasText: /^Saved\.$/ })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.screenshot({ path: 'test-results/dashboard.png', fullPage: true })
  await expect
    .poll(() =>
      page.evaluate(() =>
        Object.keys(localStorage).some(
          (key) =>
            key.startsWith('career-demo-actions:') &&
            localStorage.getItem(key)?.includes('"saved":true'),
        ),
      ),
    )
    .toBe(true)
  // Remove only client flags; the mocked server copy must restore the saved action.
  await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith('career-actions:') || key.startsWith('career-actions-pending:'))
        localStorage.removeItem(key)
    }
  })
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Python Developer', exact: true })).toBeVisible()
  await page
    .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Saved: Python Developer at Example Co', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
})
test('job sources only offer supported general boards', async ({ page }) => {
  await upload(page)
  await expect(page.getByRole('checkbox', { name: 'greenhouse', exact: true })).toHaveCount(0)
  await expect(page.getByRole('checkbox', { name: 'lever', exact: true })).toHaveCount(0)
  await expect(page.getByRole('checkbox', { name: 'linkedin', exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: 'seek', exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: 'google', exact: true })).not.toBeChecked()
  await expect(page.getByRole('checkbox', { name: 'adzuna', exact: true })).not.toBeChecked()
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Python Developer', exact: true })).toBeVisible()
})

test('profile extraction is powered by OpenAI without a model selector', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Profile extraction · Powered by OpenAI')).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Profile model' })).toHaveCount(0)
})

test('non-resume rejection stays on upload and displays the server message', async ({ page }) => {
  await page.goto('/?scenario=not-resume')
  await page.locator('input[type=file]').setInputFiles({
    name: 'invoice.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 synthetic invoice'),
  })
  await page.getByRole('button', { name: 'Upload and extract profile' }).click()
  await expect(page.getByRole('alert')).toContainText(
    'This file does not appear to be a resume/CV.',
  )
  await expect(page.getByRole('heading', { name: 'Start with your resume' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Upload and extract profile' })).toBeEnabled()
})

test('invalid upload is rejected and drop zone is keyboard operable', async ({ page }) => {
  await page.goto('/')
  const zone = page.getByRole('button', { name: 'Browse files to upload a PDF resume' })
  await zone.focus()
  await expect(zone).toBeFocused()
  const picker = page.waitForEvent('filechooser')
  await zone.press('Enter')
  await picker
  await page
    .locator('input[type=file]')
    .setInputFiles({ name: 'bad.txt', mimeType: 'text/plain', buffer: Buffer.from('not PDF') })
  await expect(page.getByRole('alert')).toContainText('PDF')
  await expect(page.getByRole('button', { name: 'Upload and extract profile' })).toBeDisabled()
})
test('cancel requires confirmation and does not offer a new upload', async ({ page }) => {
  await upload(page)
  await confirm(page)
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click()
  await page.getByRole('button', { name: 'Yes, cancel run' }).click()
  await expect(page.getByText('Run cancelled.', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Upload new resume', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Delete my data', exact: true })).toHaveCount(0)
})
for (const scenario of ['zero', 'scrape-failure'])
  test(`${scenario} has a recovery state`, async ({ page }) => {
    await upload(page, `?scenario=${scenario}`)
    await page.evaluate((value) => sessionStorage.setItem('mock-scenario', value), scenario)
    await confirm(page)
    if (scenario === 'zero')
      await expect(page.getByRole('heading', { name: 'No jobs found' })).toBeVisible()
    else await expect(page.getByRole('heading', { name: 'Search needs attention' })).toBeVisible()
  })

test('a model skipped as unavailable is reported with the results', async ({ page }) => {
  await upload(page, '?scenario=model-skipped')
  await page.evaluate(() => sessionStorage.setItem('mock-scenario', 'model-skipped'))
  await confirm(page)
  // Warnings start collapsed in one panel so the job list stays near the top.
  const notices = page.getByText('1 search notice', { exact: true })
  await expect(notices).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Some models were skipped' })).toBeHidden()
  await notices.click()
  await expect(page.getByRole('heading', { name: 'Some models were skipped' })).toBeVisible()
  await expect(page.getByText('Google Gemini · gemini-4-argon was skipped')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry skipped models' })).toBeEnabled()
})

test('a rate-limited board gets a calm note, not an error', async ({ page }) => {
  await upload(page, '?scenario=board-busy')
  await page.evaluate(() => sessionStorage.setItem('mock-scenario', 'board-busy'))
  await confirm(page)
  await page.getByText('1 search notice', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Fewer jobs from some boards' })).toBeVisible()
  await expect(page.getByText('Nothing needs to change on your side.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry scraping' })).toBeHidden()
})

test('polling fallback produces results when event streaming fails', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.setItem('mock-scenario', 'polling'))
  await upload(page)
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Python Developer', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/run\/demo\/results/)
})

test('mobile layout fits the viewport and details work by keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await upload(page)
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Python Developer', exact: true })).toBeVisible()
  const details = page.getByText('Assessment details', { exact: true })
  await details.focus()
  await details.press('Enter')
  await expect(page.getByRole('heading', { name: 'About the company' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('table view supports keyboard actions and accessibility', async ({ page }) => {
  await upload(page)
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Python Developer', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Table', exact: true }).click()
  await expect(page.getByRole('table')).toBeVisible()
  const actions = page.getByRole('button', {
    name: 'Actions for Python Developer at Example Co',
    exact: true,
  })
  await actions.focus()
  await actions.press('Enter')
  await expect(
    page.getByRole('button', { name: 'Save: Python Developer at Example Co', exact: true }),
  ).toBeFocused()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.keyboard.press('Escape')
  await expect(actions).toBeFocused()
  await expect(actions).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('columnheader', { name: 'Status', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'No status', exact: true })).toBeVisible()
  await actions.click()
  await page
    .getByRole('button', { name: 'Save: Python Developer at Example Co', exact: true })
    .click()
  await expect(page.getByRole('cell', { name: 'Saved', exact: true })).toBeVisible()
  await page
    .getByRole('button', { name: 'Mark as applied: Python Developer at Example Co', exact: true })
    .click()
  await expect(page.getByRole('cell', { name: 'Applied Saved', exact: true })).toBeVisible()
})

test('timeline navigation preserves search edits and limits new uploads to results', async ({
  page,
}) => {
  await upload(page)
  await expect(page.getByRole('button', { name: 'Upload new resume', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Upload a different resume' })).toHaveCount(0)
  await confirm(page)
  await expect(page.getByRole('button', { name: 'Review your profile', exact: true })).toHaveCount(
    0,
  )
  await expect(page.getByRole('button', { name: 'Upload new resume', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Review your profile', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Find more jobs', level: 2 })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Your job matches' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Upload new resume', exact: true })).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toHaveCount(0)
  await page
    .getByRole('combobox', { name: 'Semantic shortlist size', exact: true })
    .selectOption('15')
  await page.getByRole('button', { name: 'Explore results', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your job matches' })).toBeVisible()
  await page.getByRole('button', { name: 'Review your profile', exact: true }).click()
  await expect(
    page.getByRole('combobox', { name: 'Semantic shortlist size', exact: true }),
  ).toHaveValue('15')
  await page.getByRole('button', { name: 'Explore results', exact: true }).click()
  await page.getByRole('button', { name: 'Upload new resume', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('button', { name: 'Upload and extract profile' })).toBeVisible()
})

test('unified results open full details for not recommended jobs and survive reload', async ({
  page,
}) => {
  await upload(page)
  await confirm(page)
  await expect(page).toHaveURL(/\/run\/demo\/results/)
  await expect(page.getByRole('heading', { name: 'Your job matches' })).toBeVisible()
  await page.evaluate(() => {
    const saved = JSON.parse(localStorage.getItem('career-demo-run')!)
    saved.run.excluded_recommendations = [
      {
        ...saved.run.recommendations[0],
        jobId: 'excluded-job',
        title: 'Senior Architect',
        fit_category: 'not_suitable',
        score: 20,
        mismatch_reason: 'Requires ten years of leadership',
        job_description: 'Full posting: lead the architecture team. <script>unsafe()</script>',
        requirement_verdicts: [
          {
            requirement: 'Ten years of leadership',
            importance: 'must_have',
            verdict: 'not_met',
            job_quote: 'Ten years required',
            resume_quote: '',
            explanation: 'Experience requirement is not met.',
            job_evidence_verified: true,
          },
        ],
      },
    ]
    localStorage.setItem('career-demo-run', JSON.stringify(saved))
  })
  await page.reload()
  await expect(page.getByRole('group', { name: 'Result categories' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Python Developer', exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Senior Architect', exact: true }).click()
  await expect(page).toHaveURL(/\/job\?job=excluded-job/)
  await expect(page.getByRole('heading', { name: 'Job details', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Overall assessment', exact: true })).toBeVisible()
  await expect(page.getByText('20 / 100', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('Date posted', { exact: true })).toBeVisible()
  await expect(page.locator('.job-card')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Actions for Senior Architect at Example', exact: true }),
  ).toHaveCount(0)
  await page.getByRole('button', { name: /^Save: Senior Architect/ }).click()
  await expect(page.getByRole('button', { name: /^Saved: Senior Architect/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('tab', { name: 'Evaluation evidence', exact: true }).click()
  await expect(page.getByText('Experience requirement is not met.', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Evaluation evidence', exact: true }).press('ArrowLeft')
  await expect(
    page.getByText('Full posting: lead the architecture team.', { exact: false }),
  ).toBeVisible()
  await expect(page.locator('main script')).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('tab', { name: 'Job description', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(page.getByRole('heading', { name: 'Senior Architect', exact: true })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.getByRole('link', { name: 'Back to results' }).click()
  await page.getByRole('button', { name: 'Table', exact: true }).click()
  await page.getByRole('link', { name: 'Senior Architect', exact: true }).click()
  await page.getByRole('tab', { name: 'Job description', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Full job description' })).toBeVisible()
  await page.evaluate(() => {
    history.pushState({}, '', '/run/demo/job?job=missing')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(page.getByRole('heading', { name: 'Job not found' })).toBeVisible()
})

test('automatic evaluations show model comparison with readable evidence on mobile', async ({
  page,
}) => {
  await upload(page)
  await expect(page.getByRole('combobox', { name: 'Evaluation model', exact: true })).toHaveCount(0)
  await expect(
    page.getByText('Every shortlisted job is evaluated by each available model.', { exact: false }),
  ).toBeVisible()
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Your job matches' })).toBeVisible()
  await page.evaluate(() => {
    const saved = JSON.parse(localStorage.getItem('career-demo-run')!)
    const job = saved.run.recommendations[0]
    job.assessment_summary =
      '2/3 models complete; 1/2 completed verdicts agree. Provisional average: 73/100. Not a final verdict or confidence estimate.'
    job.model_evaluations = {
      claude: {
        status: 'complete',
        provider: 'claude',
        evaluation_model_id: 'claude-example',
        score: 85,
        fit_category: 'strong_match',
        rationale: 'Claude finds a strong skills match.',
        requirement_verdicts: [
          {
            requirement: 'Python API development',
            importance: 'must_have',
            verdict: 'met',
            explanation: 'The resume demonstrates API development.',
            job_quote: 'Build Python APIs',
            resume_quote: 'Developed Python APIs',
            job_evidence_verified: true,
            resume_evidence_verified: true,
          },
        ],
      },
      gpt: {
        status: 'failed',
        provider: 'gpt',
        evaluation_model_id: 'gpt-example',
        error: 'Provider quota is exhausted.',
      },
      gemini: {
        status: 'complete',
        provider: 'gemini',
        evaluation_model_id: 'gemini-example',
        score: 60,
        fit_category: 'review',
        rationale: 'Gemini recommends reviewing experience.',
        requirement_verdicts: [],
      },
    }
    localStorage.setItem('career-demo-run', JSON.stringify(saved))
  })
  await page.reload()
  await page.getByRole('link', { name: 'Python Developer', exact: true }).click()
  await expect(page.getByText('2/3 models complete;', { exact: false })).toBeVisible()
  await page.getByRole('tab', { name: 'Evaluation evidence', exact: true }).click()
  await expect(
    page.getByText('Compare how models assess each requirement', { exact: true }),
  ).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Other requirements', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Model feedback', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: /OpenAI GPT/ }).click()
  await expect(page.getByText('Provider quota is exhausted.')).toBeVisible()
  await page.getByRole('button', { name: /Google Gemini/ }).click()
  await expect(page.getByText('Gemini recommends reviewing experience.')).toBeVisible()
  await page.getByRole('button', { name: /Anthropic Claude/ }).click()
  await expect(
    page
      .getByRole('region', { name: 'Requirement evidence', exact: true })
      .getByText('Developed Python APIs', { exact: true })
      .first(),
  ).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.screenshot({ path: '/tmp/career-evidence-mobile.png', fullPage: true })
})

test('profiles can be saved, edited, reused without upload, and deleted', async ({ page }) => {
  await upload(page)
  await page.getByRole('textbox', { name: 'Saved resume name' }).fill('Engineering profile')
  await page.getByRole('button', { name: 'Save resume', exact: true }).click()
  await expect(
    page.getByRole('status').filter({ hasText: 'Resume and profile saved' }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Manage saved resumes' }).click()
  await page.getByRole('button', { name: 'table', exact: true }).click()
  await expect(page.getByRole('table')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Download PDF', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Edit profile', exact: true }).click()
  await page.getByRole('textbox', { name: 'Profile name', exact: true }).fill('Updated engineering')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Updated Candidate')
  await page.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(page.getByRole('rowheader', { name: 'Updated Candidate' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'table', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: 'grid', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Updated Candidate' })).toBeVisible()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page).toHaveURL(/\/run\/continued$/)
  await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue(
    'Updated Candidate',
  )
  await page.getByRole('link', { name: 'Manage saved resumes', exact: true }).click()
  await page.getByRole('button', { name: 'table', exact: true }).click()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.getByRole('button', { name: 'Delete saved resume', exact: true }).click()
  await page.getByRole('button', { name: 'Confirm delete', exact: true }).click()
  await expect(page.getByText('No saved resumes yet.', { exact: false })).toBeVisible()
})

test('continuing a saved resume reopens completed recommendations', async ({ page }) => {
  await upload(page)
  await page.getByRole('textbox', { name: 'Saved resume name' }).fill('Retained results')
  await page.getByRole('button', { name: 'Save resume', exact: true }).click()
  await expect(
    page.getByRole('status').filter({ hasText: 'Resume and profile saved' }),
  ).toBeVisible()
  await confirm(page)
  await expect(page).toHaveURL(/\/results$/)
  await page.getByRole('button', { name: 'Upload new resume', exact: true }).click()
  await page.getByRole('link', { name: 'Continue with a saved resume', exact: true }).click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Python Developer', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/run\/demo\/results$/)
})

test('completed search automatically saves a reusable profile without clicking Save', async ({
  page,
}) => {
  await upload(page)
  await expect(page.getByRole('combobox', { name: 'Seniority filter' })).toHaveValue('auto')
  await confirm(page)
  await expect(page).toHaveURL(/\/results$/)
  await expect(
    page.getByRole('status').filter({ hasText: 'profile and search preferences are saved' }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Manage saved resumes' }).click()
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toHaveCount(1)
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page).toHaveURL(/\/results$/)
})

for (const changeRole of [false, true])
  test(`find more jobs preserves results and actions (${changeRole ? 'different role' : 'same role'})`, async ({
    page,
  }) => {
    await upload(page)
    await confirm(page)
    await expect(page).toHaveURL(/\/run\/demo\/results$/)
    await expect(
      page.getByRole('status').filter({ hasText: 'profile and search preferences are saved' }),
    ).toBeVisible()
    await page.reload()
    await expect(page.getByRole('button', { name: 'Find more jobs', exact: true })).toBeEnabled()
    await page
      .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
      .click()
    await page
      .getByRole('button', { name: 'Save: Python Developer at Example Co', exact: true })
      .press('Enter')
    await page
      .getByRole('button', { name: 'Mark as applied: Python Developer at Example Co', exact: true })
      .press('Enter')
    await page.getByRole('button', { name: 'Find more jobs', exact: true }).click()
    await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toHaveCount(0)
    await expect(page.getByText('duplicate postings are skipped.', { exact: false })).toBeVisible()
    await page.getByRole('button', { name: 'Back to results', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Python Developer', exact: true })).toHaveCount(
      1,
    )
    await page.getByRole('button', { name: 'Find more jobs', exact: true }).click()
    if (changeRole) {
      await page.getByRole('button', { name: 'Remove Python Developer', exact: true }).click()
      await page.getByRole('textbox', { name: 'Target roles', exact: true }).fill('Data Analyst')
      await page.getByRole('textbox', { name: 'Target roles', exact: true }).press('Enter')
    }
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    await page.getByRole('button', { name: 'Search for more jobs', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: 'Python Developer', exact: true }).first(),
    ).toBeVisible()
    await expect(page.getByRole('button', { name: 'Find more jobs', exact: true })).toBeEnabled()
    await expect(page.locator('article.job-card')).toHaveCount(2)
    if (changeRole)
      await expect(page.getByRole('heading', { name: 'Data Analyst', exact: true })).toBeVisible()
    await page
      .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
      .first()
      .click()
    await expect(
      page
        .getByRole('button', { name: 'Saved: Python Developer at Example Co', exact: true })
        .first(),
    ).toHaveAttribute('aria-pressed', 'true')
    await expect(
      page
        .getByRole('button', { name: 'Applied: Python Developer at Example Co', exact: true })
        .first(),
    ).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('button', { name: 'Find more jobs', exact: true }).click()
    await page.evaluate(() => sessionStorage.setItem('mock-scenario', 'no-new'))
    await page.getByRole('button', { name: 'Search for more jobs', exact: true }).click()
    await expect(
      page.getByText('No new jobs found. Your existing results are kept.', { exact: false }),
    ).toBeVisible()
    await expect(page.locator('article.job-card')).toHaveCount(2)
    await page.reload()
    await expect(page.locator('article.job-card')).toHaveCount(2)
    await page
      .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
      .first()
      .click()
    await page
      .getByRole('button', { name: 'Dismiss: Python Developer at Example Co', exact: true })
      .first()
      .press('Enter')
    await page.getByRole('button', { name: 'Dismiss job', exact: true }).click()
    await page.getByRole('button', { name: 'Find more jobs', exact: true }).click()
    await page.getByRole('button', { name: 'Search for more jobs', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Find more jobs', exact: true })).toBeEnabled()
    await expect(page.locator('article.job-card')).toHaveCount(1)
    await page.getByRole('combobox', { name: 'Job actions', exact: true }).selectOption('dismissed')
    await expect(page.locator('article.job-card')).toHaveCount(1)
    await page
      .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
      .click()
    await expect(
      page.getByRole('button', { name: 'Dismissed: Python Developer at Example Co', exact: true }),
    ).toHaveAttribute('aria-pressed', 'true')
    await expect(
      page.getByRole('button', { name: 'Applied: Python Developer at Example Co', exact: true }),
    ).toHaveAttribute('aria-pressed', 'true')
    await expect(
      page.getByRole('button', { name: 'Saved: Python Developer at Example Co', exact: true }),
    ).toHaveAttribute('aria-pressed', 'true')
    await page.reload()
    await page.getByRole('combobox', { name: 'Job actions', exact: true }).selectOption('dismissed')
    await expect(page.locator('article.job-card')).toHaveCount(1)
  })

for (const entry of ['timeline', 'button'])
  test(`${entry} repeat search appends 15 jobs to the existing 50`, async ({ page }) => {
    await upload(page)
    await confirm(page)
    await expect(page).toHaveURL(/\/run\/demo\/results$/)
    await expect(
      page.getByRole('status').filter({ hasText: 'profile and search preferences are saved' }),
    ).toBeVisible()
    await page.evaluate(() => {
      const saved = JSON.parse(localStorage.getItem('career-demo-run')!)
      const template = saved.run.recommendations[0]
      saved.run.recommendations = Array.from({ length: 50 }, (_, index) => ({
        ...template,
        jobId: `existing-${index}`,
        title: `Existing role ${index + 1}`,
        apply_url: `https://example.com/existing/${index}`,
      }))
      saved.run.preferences.top_k = 50
      localStorage.setItem('career-demo-run', JSON.stringify(saved))
      sessionStorage.setItem('mock-scenario', 'append-15')
    })
    await page.reload()
    await expect(
      page.getByRole('status').filter({ hasText: 'Showing 1–12 of 50 jobs' }),
    ).toBeVisible()
    await page
      .getByRole('button', {
        name: entry === 'timeline' ? 'Review your profile' : 'Find more jobs',
        exact: true,
      })
      .click()
    await expect(page.getByRole('heading', { name: 'Find more jobs', level: 2 })).toBeVisible()
    await page
      .getByRole('combobox', { name: 'Semantic shortlist size', exact: true })
      .selectOption('15')
    const request = page.waitForRequest(
      (request) => request.url().endsWith('/find-more') && request.method() === 'POST',
    )
    await page.getByRole('button', { name: 'Search for more jobs', exact: true }).click()
    expect((await request).postDataJSON().preferences.top_k).toBe(15)
    await expect(
      page.getByRole('status').filter({ hasText: 'Showing 1–12 of 65 jobs' }),
    ).toBeVisible()
    await expect(page.getByRole('button', { name: 'Find more jobs', exact: true })).toBeEnabled()
    await page.getByRole('searchbox', { name: 'Search jobs', exact: true }).fill('Existing role 50')
    await expect(page.getByRole('link', { name: 'Existing role 50', exact: true })).toBeVisible()
    await page.getByRole('searchbox', { name: 'Search jobs', exact: true }).fill('New role 15')
    await expect(page.getByRole('link', { name: 'New role 15', exact: true })).toBeVisible()
    await page.reload()
    await expect(
      page.getByRole('status').filter({ hasText: 'Showing 1–12 of 65 jobs' }),
    ).toBeVisible()
  })

test('fresh loads of non-home URLs start at home', async ({ page }) => {
  for (const path of ['/run/demo/results', '/profiles', '/privacy']) {
    await page.goto(path)
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { name: 'Start with your resume' })).toBeVisible()
  }
  await page.getByRole('link', { name: 'Privacy & data retention' }).click()
  await expect(page).toHaveURL(/\/privacy$/)
  await page.reload()
  await expect(page).toHaveURL(/\/privacy$/)
})

test('retry scraping starts directly without returning to profile review', async ({ page }) => {
  await upload(page, '?scenario=scrape-failure')
  await page.evaluate(() => sessionStorage.setItem('mock-scenario', 'scrape-failure'))
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Search needs attention' })).toBeVisible()
  const request = page.waitForRequest(
    (req) => req.url().endsWith('/retry-scraping') && req.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Retry scraping', exact: true }).click()
  await request
  await expect(
    page.getByText('Retrying failed sources; keeping your previous results'),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Review your profile', level: 2 })).toHaveCount(0)
})

test('applied action remains set while evaluation snapshots arrive', async ({ page }) => {
  await upload(page, '?scenario=evaluating')
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Results as they arrive' })).toBeVisible()
  await page
    .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
    .click()
  await page
    .getByRole('button', { name: 'Mark as applied: Python Developer at Example Co', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Applied: Python Developer at Example Co', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  await page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/searches/demo') && response.request().method() === 'GET',
  )
  await expect(page.getByRole('heading', { name: 'Results as they arrive' })).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Applied: Python Developer at Example Co', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  await expect
    .poll(() =>
      page.evaluate(() =>
        Object.entries(localStorage).some(
          ([key, value]) =>
            key.startsWith('career-demo-actions:') && value.includes('"applied":true'),
        ),
      ),
    )
    .toBe(true)
})

for (const view of ['Grid', 'Table'] as const) {
  test(`mark applied survives pointer-induced focus loss in the ${view} menu`, async ({ page }) => {
    await upload(page)
    await confirm(page)
    await expect(page).toHaveURL(/\/run\/demo\/results/)
    await page.getByRole('button', { name: view, exact: true }).click()
    await page
      .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
      .click()
    const applied = page.getByRole('button', {
      name: 'Mark as applied: Python Developer at Example Co',
      exact: true,
    })
    // Reproduce a browser that blurs the focused menu item but does not focus buttons on click.
    await applied.evaluate((button) => {
      button.addEventListener(
        'mousedown',
        (event) => {
          event.preventDefault()
          document.body.tabIndex = -1
          document.body.focus({ preventScroll: true })
        },
        { once: true },
      )
    })
    await applied.click()
    await expect(
      page.getByRole('button', { name: 'Applied: Python Developer at Example Co', exact: true }),
    ).toHaveAttribute('aria-pressed', 'true')
    await expect(
      page.getByRole('status').filter({ hasText: 'Job marked as applied.' }),
    ).toBeVisible()
    await page.reload()
    await page
      .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
      .click()
    await expect(
      page.getByRole('button', { name: 'Applied: Python Developer at Example Co', exact: true }),
    ).toHaveAttribute('aria-pressed', 'true')
  })
}

test('dismissal feedback is optional, hidden from results and reversible', async ({ page }) => {
  await upload(page)
  await confirm(page)
  await page
    .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
    .first()
    .click()
  await page
    .getByRole('button', { name: 'Dismiss: Python Developer at Example Co', exact: true })
    .first()
    .click()
  const dialog = page.getByRole('dialog', { name: 'Dismiss this job' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.locator('article.job-card')).toHaveCount(1)
  await page
    .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
    .first()
    .click()
  await page
    .getByRole('button', { name: 'Dismiss: Python Developer at Example Co', exact: true })
    .first()
    .click()
  await dialog.getByLabel('Reason (optional)').selectOption('location')
  await dialog.getByRole('button', { name: 'Dismiss job', exact: true }).click()
  await expect(page.locator('article.job-card')).toHaveCount(0)
  // Reasons are kept for future searches but not listed on the results page.
  await expect(page.getByText(/Dismissal preferences/)).toHaveCount(0)
  await page.reload()
  await expect(page.locator('article.job-card')).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Job actions', exact: true }).selectOption('dismissed')
  await page
    .getByRole('button', { name: 'Actions for Python Developer at Example Co', exact: true })
    .click()
  await page
    .getByRole('button', { name: 'Dismissed: Python Developer at Example Co', exact: true })
    .click()
  await page.getByRole('combobox', { name: 'Job actions', exact: true }).selectOption('all')
  await expect(page.locator('article.job-card')).toHaveCount(1)
})

test('salary dismissal requires explicit pay preferences and supports keyboard cancellation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await upload(page)
  await confirm(page)
  await page.getByRole('link', { name: 'Python Developer', exact: true }).first().click()
  await page
    .getByRole('button', { name: 'Dismiss: Python Developer at Example Co', exact: true })
    .click()
  const dialog = page.getByRole('dialog', { name: 'Dismiss this job' })
  await expect(dialog.getByLabel('Reason (optional)')).toBeFocused()
  await dialog.getByLabel('Reason (optional)').selectOption('salary')
  await dialog.getByRole('button', { name: 'Dismiss job', exact: true }).click()
  await expect(dialog).toBeVisible()
  await dialog.getByLabel('Minimum amount').fill('100000')
  await dialog.getByLabel('Currency', { exact: true }).selectOption('AUD')
  await dialog.getByLabel('Pay period').selectOption('year')
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([])
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Dismiss: Python Developer at Example Co', exact: true }),
  ).toBeFocused()
  await page
    .getByRole('button', { name: 'Dismiss: Python Developer at Example Co', exact: true })
    .click()
  await dialog.getByLabel('Reason (optional)').selectOption('salary')
  await dialog.getByLabel('Minimum amount').fill('100000')
  await dialog.getByRole('button', { name: 'Dismiss job', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Dismissed: Python Developer at Example Co', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  await expect
    .poll(() =>
      page.evaluate(() => {
        return Object.keys(localStorage).some(
          (key) =>
            key.startsWith('career-demo-actions:') &&
            key.endsWith(':feedback') &&
            localStorage.getItem(key)?.includes('100000'),
        )
      }),
    )
    .toBe(true)
})

for (const mode of ['Grid', 'Table'])
  test(`results page and search survive details navigation (${mode})`, async ({ page }) => {
    await upload(page)
    await confirm(page)
    await expect(page).toHaveURL(/\/run\/demo\/results$/)
    await expect(page.getByRole('button', { name: 'Find more jobs', exact: true })).toBeEnabled()
    await page.evaluate(() => {
      const saved = JSON.parse(localStorage.getItem('career-demo-run')!)
      const template = saved.run.recommendations[0]
      saved.run.recommendations = Array.from({ length: 30 }, (_, index) => ({
        ...template,
        jobId: `pagination-${index}`,
        title: `Existing role ${index + 1}`,
        apply_url: `https://example.test/pagination/${index}`,
      }))
      localStorage.setItem('career-demo-run', JSON.stringify(saved))
    })
    await page.reload()
    await page.getByRole('button', { name: mode, exact: true }).click()
    await page.locator('input[type="search"]').fill('Existing role')
    await page.getByRole('button', { name: 'Page 3', exact: true }).click()
    for (const back of ['link', 'browser']) {
      await page.getByRole('link', { name: 'Existing role 25', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Job details', exact: true })).toBeAttached()
      if (back === 'link')
        await page.getByRole('link', { name: 'Back to results', exact: false }).click()
      else await page.goBack()
      await expect(page.getByRole('button', { name: 'Page 3', exact: true })).toHaveAttribute(
        'aria-current',
        'page',
      )
      await expect(page.locator('input[type="search"]')).toHaveValue('Existing role')
      await expect(page.getByRole('link', { name: 'Existing role 25', exact: true })).toBeVisible()
    }
  })
