// Exercise assessment display behavior with controlled fixtures and explicit assertions.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import { renderToString } from 'vue/server-renderer'

test('dashboard renders configured models, assessment sections and historical fallbacks', async () => {
  const server = await createServer({
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, hmr: false, ws: false },
  })
  try {
    const { default: Dashboard } = await server.ssrLoadModule('/src/components/JobDashboard.vue')
    const job = {
      title: 'Engineer',
      company: 'Example',
      about_company: 'Builds software.',
      candidate_requirements: ['SQL required', 'Python preferred'],
      salary: 'AUD 100,000 per year',
      evaluation_model_id: 'gpt-4o-mini',
    }
    const options = ['gemini-custom', 'claude-custom', 'gpt-custom'].map((label, i) => ({
      value: ['gemini', 'claude', 'gpt'][i],
      label,
    }))
    const html = await renderToString(
      createSSRApp(Dashboard, {
        jobs: [job],
        evaluationOptions: options,
        evaluationChoice: 'gpt',
      }).use(createPinia()),
    )
    for (const text of [
      'About the company',
      'What the company needs from the candidate',
      'Salary',
      'Builds software.',
      'SQL required',
      'Python preferred',
      'AUD 100,000 per year',
      'gpt-4o-mini evaluated',
    ]) {
      assert.ok(html.includes(text), text)
    }
    const legacy = await renderToString(
      createSSRApp(Dashboard, { jobs: [{ title: 'Older job' }] }).use(createPinia()),
    )
    assert.ok(legacy.includes('Company information is unavailable'))
    assert.ok(legacy.includes('Candidate requirements are unavailable'))
    assert.doesNotMatch(legacy, /<h4[^>]*>Salary<\/h4>/)
    assert.ok(!legacy.includes('No skill gaps identified'))
  } finally {
    await server.close()
  }
})
