import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('eval deep link compares chosen models, displays labels and survives refresh', async ({
  page,
}) => {
  let starts = 0
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/experiments')) starts++
  })
  await page.goto('/eval')
  await expect(
    page.getByRole('heading', { name: 'Check how well the app matches jobs' }),
  ).toBeVisible()
  await page.getByLabel('Workspace', { exact: true }).selectOption('a'.repeat(32))
  await page.getByText('Advanced: compare AI models').click()
  await expect(page.getByText('Dataset & optional human labels (2 jobs)')).toBeVisible()
  expect(starts).toBe(0)
  await page.getByLabel('text-embedding-3-large', { exact: true }).check()
  await page.getByLabel('Anthropic Claude · claude-demo', { exact: true }).check()
  await page.getByText('Dataset & optional human labels (2 jobs)').click()
  await page.getByLabel('Human label for Python Developer').selectOption('positive')
  await page.getByRole('button', { name: 'Run experiment', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Retrieval · text-embedding-3-small', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Retrieval · text-embedding-3-large', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Generation · gpt-demo' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Generation · claude-demo' })).toBeVisible()
  await expect(page.getByText(/Label coverage: 50.0% · Observed recall@K: 100.0%/)).toHaveCount(2)
  expect(starts).toBe(1)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Generation · claude-demo' })).toBeVisible()
  expect(starts).toBe(1)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('eval supports cancellation and reports rejected starts', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('mock-scenario', 'eval-slow'))
  await page.goto('/eval')
  await page.getByLabel('Workspace', { exact: true }).selectOption('a'.repeat(32))
  await page.getByText('Advanced: compare AI models').click()
  await page.getByRole('button', { name: 'Run experiment', exact: true }).click()
  await page.getByRole('button', { name: 'Cancel experiment', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('cancelled')
  await page.evaluate(() => sessionStorage.setItem('mock-scenario', 'eval-failure'))
  await page.getByRole('button', { name: 'Run experiment', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Another experiment is still running')
})
