// The playground runs one stage at a time and shows its output without saving anything.
import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('upload stage shows the extracted profile and its check', async ({ page }) => {
  await page.goto('/eval')
  await expect(page.getByRole('heading', { name: 'Pipeline playground' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '1. Upload' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await page.getByLabel('Resume PDF').setInputFiles({
    name: 'resume.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 mock fixture'),
  })
  await page.getByRole('button', { name: 'Run upload' }).click()
  await expect(page.getByRole('heading', { name: 'Alex Example' })).toBeVisible()
  await expect(page.getByText('Python and SQL work at a junior level.')).toBeVisible()
  // Entries are split into title, then company and dates.
  await expect(page.getByText('Example Co · March 2024 – Present')).toBeVisible()
  await expect(page.getByRole('listitem').filter({ hasText: 'Junior Data Analyst' })).toBeVisible()
  await expect(page.getByText('Kubernetes').last()).toBeVisible()
  await expect(page.getByText('Certifications').last()).toBeVisible()
  // Let the button's 200 ms fade back from disabled finish before checking contrast.
  await expect(page.getByRole('button', { name: 'Run upload' })).toBeEnabled()
  await page.waitForTimeout(300)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('ingestion stage shows kept and dropped jobs and stays linkable', async ({ page }) => {
  await page.goto('/eval')
  await page.getByRole('tab', { name: '2. Ingestion' }).click()
  await expect(page).toHaveURL(/stage=ingestion/)
  const roles = page.getByRole('textbox', { name: 'Target roles', exact: true })
  await roles.fill('Data Analyst')
  await roles.press('Enter')
  // No location means worldwide, as in a real search, and the hint sits under the field.
  await expect(page.getByRole('button', { name: 'Run ingestion' })).toBeEnabled()
  const hint = page.getByText('Leave empty to search worldwide.')
  const field = page.getByRole('combobox', { name: 'Locations', exact: true })
  expect((await hint.boundingBox())!.y).toBeGreaterThan((await field.boundingBox())!.y)
  expect(Math.abs((await hint.boundingBox())!.x - (await field.boundingBox())!.x)).toBeLessThan(40)
  const locations = page.getByRole('combobox', { name: 'Locations', exact: true })
  await locations.fill('Sydney')
  await locations.press('Enter')
  await page.getByRole('button', { name: 'Run ingestion' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'eligible postings' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Junior Data Analyst' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'posted too long ago' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Filtered out' })).toBeVisible()
  // Dropped jobs are grouped by reason, each group opening to job cards.
  await page.getByText('Filtered out: posted too long ago · 1').click()
  await expect(page.getByRole('link', { name: 'Old Analyst Role' })).toBeVisible()
  await expect(page.getByText('Kept for matching')).toBeVisible()
  // linkedin: 3 collected, 1 kept, 2 dropped.
  await expect(page.getByRole('row', { name: 'linkedin 3 1 2' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run ingestion' })).toBeEnabled()
  await page.waitForTimeout(300)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.reload()
  await expect(page.getByRole('tab', { name: '2. Ingestion' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
})

test('retrieval stage ranks the ingestion jobs against the uploaded profile', async ({ page }) => {
  await page.goto('/eval')
  await page.getByRole('tab', { name: '3. Retrieval' }).click()
  // It needs the other two stages' results first.
  await expect(page.getByText('Run Upload and Ingestion (with at least one kept job) first')).toBeVisible()
  await page.getByRole('tab', { name: '1. Upload' }).click()
  await page.getByLabel('Resume PDF').setInputFiles({
    name: 'resume.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 mock fixture'),
  })
  await page.getByRole('button', { name: 'Run upload' }).click()
  await expect(page.getByRole('heading', { name: 'Alex Example' })).toBeVisible()
  await page.getByRole('tab', { name: '2. Ingestion' }).click()
  const roles = page.getByRole('textbox', { name: 'Target roles', exact: true })
  await roles.fill('Junior Data Analyst')
  await roles.press('Enter')
  await page.getByRole('button', { name: 'Run ingestion' }).click()
  await expect(page.getByRole('link', { name: 'Junior Data Analyst' })).toBeVisible()
  await page.getByRole('tab', { name: '3. Retrieval' }).click()
  await expect(page).toHaveURL(/stage=retrieval/)
  await page.getByRole('button', { name: 'Run retrieval' }).click()
  await expect(page.getByRole('heading', { name: 'Shortlist: 1 of 1 jobs' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Python SQL' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Junior Data Analyst' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run retrieval' })).toBeEnabled()
  await page.waitForTimeout(300)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
