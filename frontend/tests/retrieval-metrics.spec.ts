// Check retrieval metrics against hand-computed values; unmarked jobs must stay unknown.
import { expect, it } from 'vitest'
import { jobKey, retrievalMetrics } from '../src/utils/retrievalMetrics'

const pool = ['a', 'b', 'c', 'd', 'e', 'f']

it('computes recall at each cut, rank-aware precision and relevance over marked jobs', () => {
  // Ranked a..e is the shortlist; f was marked relevant earlier but was not retrieved.
  const marks = { a: true, b: false, d: true, f: true }
  const result = retrievalMetrics(['a', 'b', 'c', 'd', 'e'], pool, marks, [2])
  expect(result.recall).toEqual([
    { k: 2, value: 1 / 3 },
    { k: 5, value: 2 / 3 },
  ])
  // Marked order a(+), b(-), d(+): precision 1/1 at a and 2/3 at d; c and e are skipped.
  expect(result.contextPrecision).toBeCloseTo((1 + 2 / 3) / 2)
  expect(result.contextRelevance).toBeCloseTo(2 / 3)
  expect(result).toMatchObject({ markedInShortlist: 3, markedInPool: 4, relevantInPool: 3 })
})

it('reports no value instead of zero when nothing relevant is marked', () => {
  const result = retrievalMetrics(['a', 'b'], pool, { a: false })
  expect(result.recall).toEqual([{ k: 2, value: null }])
  expect(result.contextPrecision).toBeNull()
  expect(result.contextRelevance).toBe(0)
})

it('keys jobs without a URL by title and company on both sides', () => {
  expect(jobKey({ url: 'No URL provided', title: 'Dev', company: 'Acme' })).toBe('Dev|Acme')
  expect(jobKey({ url: '', title: 'Dev', company: 'Acme' })).toBe('Dev|Acme')
  expect(jobKey({ url: 'https://example.test/1', title: 'Dev', company: 'Acme' })).toBe(
    'https://example.test/1',
  )
})
