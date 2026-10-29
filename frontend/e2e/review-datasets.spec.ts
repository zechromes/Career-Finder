import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('human reviews stay separate from model evidence, persist and update metrics', async ({
  page,
}) => {
  await page.goto('/eval')
  await page.getByRole('link', { name: /Review dataset ·/ }).click()
  await page.getByRole('button', { name: 'Detailed review' }).click()
  await expect(page.getByRole('heading', { name: 'Dataset review', exact: true })).toBeVisible()
  await expect(
    page.getByLabel('Candidate fit', { exact: true }).locator('option:checked'),
  ).toHaveText('Unreviewed')
  await expect(page.getByText('Python skills align.', { exact: true })).toHaveCount(0)
  await page.getByLabel('Reviewer name or initials').fill('Reviewer A')
  await page.getByLabel('Candidate fit', { exact: true }).selectOption('strong_match')
  await page.getByLabel('Show saved model outputs for extraction and evidence review').check()
  await page
    .getByLabel('Criterion 1 correctness', { exact: true })
    .selectOption({ label: 'Correct' })
  await page.getByLabel('Criterion 1 importance', { exact: true }).selectOption('must_have')
  await page.getByLabel('I reviewed all shared criteria').check()
  await page.getByRole('button', { name: 'Check model evidence', exact: true }).click()
  await expect(page.getByText('Python skills align.', { exact: true })).toBeVisible()
  await page.getByLabel('Evidence 1 support', { exact: true }).selectOption('unsupported')
  await page.getByLabel('Evidence 1 verdict', { exact: true }).selectOption('partial')
  await page.getByRole('button', { name: 'Save job review', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Review saved')
  await page.getByText(/Review progress and quality metrics/).click()
  await expect(page.getByText(/support rate 0.0%/)).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Candidate fit', { exact: true })).toHaveValue('strong_match')
  await page.getByLabel('Show saved model outputs for extraction and evidence review').check()
  await page.getByRole('button', { name: 'Check model evidence', exact: true }).click()
  await expect(page.getByLabel('Evidence 1 support', { exact: true })).toHaveValue('unsupported')
  await expect(page.getByText('Python skills align.', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('a beginner can save only a fit decision and leave deeper judgments unreviewed', async ({
  page,
}) => {
  await page.goto('/eval')
  await page.getByRole('link', { name: /Review dataset ·/ }).click()
  await page.getByRole('button', { name: 'Detailed review' }).click()
  await expect(
    page.getByRole('heading', { name: 'Start with one job and one decision' }),
  ).toBeVisible()
  await expect(page.getByText('1. Read the candidate profile')).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'fit review help' })).toContainText(
    'Missing a preferred skill alone does not rule this out',
  )
  await expect(page.getByRole('region', { name: 'Requirement extraction review' })).toHaveCount(0)
  await page.getByLabel('Reviewer name or initials').fill('Reviewer B')
  await page.getByLabel('Candidate fit', { exact: true }).selectOption('review')
  await page
    .getByLabel('Fit explanation')
    .fill('The profile does not establish all mandatory requirements.')
  await page.getByRole('button', { name: 'Save job review', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Review saved')
  await page.reload()
  await expect(page.getByLabel('Candidate fit', { exact: true })).toHaveValue('review')
  await page.getByLabel('Show saved model outputs for extraction and evidence review').check()
  await expect(page.getByLabel('Criterion 1 correctness').locator('option:checked')).toHaveText(
    'Unreviewed',
  )
  await expect(page.getByRole('complementary', { name: 'requirements review help' })).toContainText(
    'Python or Java',
  )
  await page.getByLabel('Criterion 1 correctness').selectOption({ label: 'Correct' })
  await page.getByRole('button', { name: 'Check model evidence', exact: true }).click()
  await expect(page.getByRole('complementary', { name: 'evidence review help' })).toContainText(
    'five years of paid Python work',
  )
  await expect(page.getByLabel('Evidence 1 support').locator('option:checked')).toHaveText(
    'Unreviewed',
  )
  await page.getByRole('button', { name: 'Check job requirements', exact: true }).click()
  await expect(page.getByLabel('Criterion 1 correctness').locator('option:checked')).toHaveText(
    'Correct',
  )
  await expect(page.getByLabel('Candidate fit', { exact: true })).toHaveValue('review')
})

test('AI-assisted reviews are saved but excluded from quality metrics', async ({ page }) => {
  await page.goto('/eval')
  await page.getByRole('link', { name: /Review dataset ·/ }).click()
  await page.getByRole('button', { name: 'Detailed review' }).click()
  await page.getByLabel('Reviewer name or initials').fill('Reviewer C')
  await page.getByLabel('Candidate fit', { exact: true }).selectOption('strong_match')
  await page.getByLabel('I used an AI suggestion for this review').check()
  await page.getByRole('button', { name: 'Save job review', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Review saved')
  await expect(page.getByText(/0\/1\s+fit decisions saved/)).toBeVisible()
  await page.getByText(/Review progress and quality metrics/).click()
  await expect(page.getByText('AI-assisted reviews excluded from all metrics: 1')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('I used an AI suggestion for this review')).toBeChecked()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('a review dataset is deleted only after inline confirmation', async ({ page }) => {
  await page.goto('/eval')
  const datasetLink = page.getByRole('link', { name: /Review dataset ·/ })
  await expect(datasetLink).toBeVisible()
  await page.getByRole('button', { name: /Delete review dataset from/ }).click()
  await expect(page.getByRole('alert')).toContainText('This cannot be undone')
  await page.getByRole('button', { name: 'Keep dataset' }).click()
  await expect(datasetLink).toBeVisible()
  await page.getByRole('button', { name: /Delete review dataset from/ }).click()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.getByRole('button', { name: 'Confirm delete' }).click()
  await expect(datasetLink).toHaveCount(0)
  await expect(page.getByText('No review datasets yet.')).toBeVisible()
})

test('quick labeling saves a fit with one key press and explains the result', async ({ page }) => {
  await page.goto('/eval')
  await expect(
    page.getByRole('heading', { name: 'Check how well the app matches jobs' }),
  ).toBeVisible()
  await page.getByRole('link', { name: /Review dataset ·/ }).click()
  await expect(page.getByRole('button', { name: 'Quick labeling (recommended)' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByText('No results yet.')).toBeVisible()
  await expect(page.getByText('Previously shortlisted')).toHaveCount(0)
  await page.getByRole('button', { name: /Good fit/ }).click()
  await expect(page.getByRole('alert')).toContainText('Enter your name or initials first')
  await page.getByLabel('Your name or initials').fill('Reviewer D')
  await page.getByRole('heading', { name: /Python Developer/ }).click()
  await page.keyboard.press('1')
  await expect(page.getByText('Every job in this dataset is labeled.')).toBeVisible()
  await expect(page.getByText('1 labeled · aim for 30')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Results so far' })).toContainText(
    'included 1 of your 1',
  )
  await page.getByRole('button', { name: 'Change previous answer' }).click()
  await expect(page.getByText('Current answer: Good fit')).toBeVisible()
  await page.getByRole('button', { name: /Not a fit/ }).click()
  await expect(page.getByRole('region', { name: 'Results so far' })).toContainText(
    '0 jobs as Good fit, 1 as Not a fit',
  )
  await page.reload()
  await expect(page.getByLabel('Your name or initials')).toHaveValue('Reviewer D')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('results explain each RAG stage and which models rejected good fits', async ({ page }) => {
  await page.goto('/eval')
  await page.getByRole('link', { name: /Review dataset ·/ }).click()
  await page.getByLabel('Your name or initials').fill('Reviewer E')
  await page.getByRole('button', { name: /Good fit/ }).click()
  const results = page.getByRole('region', { name: 'Results so far' })
  await expect(results).toContainText('Where your 1 good fits ended up')
  await expect(results).toContainText('Shown as needs review: 1')
  await results.getByRole('button', { name: '1. Ingestion' }).click()
  await expect(results).toContainText('reached the search pool')
  await results.getByRole('button', { name: '2. Retrieval' }).click()
  await expect(results).toContainText('1 of 1 were shortlisted')
  await results.getByRole('button', { name: '3. Generation' }).click()
  const table = results.getByRole('table', { name: 'AI model verdicts compared with your labels' })
  await expect(table.getByRole('row', { name: /GPT/ })).toContainText('1 of 1 (100%)')
  await expect(table.getByRole('row', { name: /Claude/ })).toContainText('0 of 1 (0%)')
  await results.getByText('Good fits rejected by Claude (synthetic)').click()
  await expect(results.getByRole('listitem').filter({ hasText: 'Python Developer' })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('ingestion shows drop reasons, labels dropped jobs and checks duplicates', async ({
  page,
}) => {
  await page.goto('/eval')
  await page.getByRole('link', { name: /Review dataset ·/ }).click()
  await page.getByLabel('Your name or initials').fill('Reviewer F')
  await page.getByRole('button', { name: /Good fit/ }).click()
  const results = page.getByRole('region', { name: 'Results so far' })
  await results.getByRole('button', { name: '1. Ingestion' }).click()
  await expect(results).toContainText('Collected 6 postings')
  const reasons = results.getByRole('table', { name: 'Why postings were dropped before ranking' })
  await expect(reasons.getByRole('row', { name: /location does not match/ })).toContainText('3')
  await expect(results).toContainText('1 of 1 requirement quotes survived')
  await results.getByRole('button', { name: 'Same job' }).click()
  await expect(results).toContainText('1 of 1 checked merges were the same job')
  await results.getByRole('button', { name: /Label dropped jobs/ }).click()
  await expect(page).toHaveURL(/mode=dropped/)
  const queue = page.getByRole('region', { name: 'Label dropped jobs' })
  await expect(queue.getByRole('heading', { name: /Data Analyst/ })).toBeVisible()
  await queue.getByRole('button', { name: /Good fit/ }).click()
  await expect(page.getByText('Every recorded dropped job is labeled.')).toBeVisible()
  await results.getByRole('button', { name: 'Overview' }).click()
  await expect(results).toContainText('Dropped before ranking (ingestion): 1')
  await expect(results).toContainText('included 1 of your 1 good fits in the search pool')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('retrieval tab compares embedding models only after confirmation', async ({ page }) => {
  let starts = 0
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/experiments')) starts++
  })
  await page.goto('/eval')
  await page.getByRole('link', { name: /Review dataset ·/ }).click()
  await page.getByLabel('Your name or initials').fill('Reviewer G')
  await page.getByRole('button', { name: /Good fit/ }).click()
  const results = page.getByRole('region', { name: 'Results so far' })
  await results.getByRole('button', { name: '2. Retrieval' }).click()
  await results.getByRole('button', { name: 'Set up a comparison' }).click()
  await expect(results).toContainText('may cost a few cents')
  expect(starts).toBe(0)
  await results.getByLabel('text-embedding-3-large').uncheck()
  await results.getByRole('button', { name: 'Run comparison' }).click()
  await expect(results.getByRole('status')).toContainText('complete')
  await expect(results).toContainText('text-embedding-3-small: found')
  await expect(results).not.toContainText('text-embedding-3-large:')
  expect(starts).toBe(1)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('label-free results are visible before any labels', async ({ page }) => {
  await page.goto('/eval')
  await page.getByRole('link', { name: /Review dataset ·/ }).click()
  const results = page.getByRole('region', { name: 'Results so far' })
  await expect(results).toContainText('need no labels')
  await results.getByRole('button', { name: '1. Ingestion' }).click()
  await expect(results).toContainText('Collected 6 postings')
  await expect(results).toContainText('1 of 1 requirement quotes survived')
  await results.getByRole('button', { name: '3. Generation' }).click()
  await expect(results).toContainText('GPT: 1 strong match · 0 needs review · 0 not suitable')
  await expect(results).toContainText('App overall: 0 strong match · 1 needs review')
  await expect(results.getByRole('table')).toHaveCount(0)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
