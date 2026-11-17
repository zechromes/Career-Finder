// Retrieval metrics from the user's relevance marks. An unmarked job is unknown: it never
// counts as a hit or a miss, so the numbers describe the marked jobs only.
export type RelevanceMarks = Record<string, boolean>

export interface RetrievalMetrics {
  recall: { k: number; value: number | null }[]
  contextPrecision: number | null
  contextRelevance: number | null
  markedInShortlist: number
  markedInPool: number
  relevantInPool: number
}

// Same identity on both sides: retrieval reports a missing URL as "No URL provided".
export function jobKey(job: { url: string; title: string; company: string }) {
  return job.url && !job.url.startsWith('No URL') ? job.url : `${job.title}|${job.company}`
}

export function retrievalMetrics(
  shortlist: string[],
  pool: string[],
  marks: RelevanceMarks,
  ks = [15, 50, 100],
): RetrievalMetrics {
  const isMarked = (key: string) => key in marks
  const relevantInPool = pool.filter((key) => marks[key] === true).length
  // Past the shortlist nothing more is retrieved, so the last cut is the shortlist itself.
  const cuts = [...new Set([...ks.filter((k) => k < shortlist.length), shortlist.length])]
  const recall = cuts.map((k) => ({
    k,
    value: relevantInPool
      ? shortlist.slice(0, k).filter((key) => marks[key] === true).length / relevantInPool
      : null,
  }))
  // Rank-aware context precision (as in RAGAS): mean precision@i at each relevant rank i,
  // with precision taken over the marked jobs ranked at or above i.
  let marked = 0
  let hits = 0
  let precisionSum = 0
  for (const key of shortlist) {
    if (!isMarked(key)) continue
    marked += 1
    if (marks[key]) {
      hits += 1
      precisionSum += hits / marked
    }
  }
  return {
    recall,
    contextPrecision: hits ? precisionSum / hits : null,
    contextRelevance: marked ? hits / marked : null,
    markedInShortlist: marked,
    markedInPool: pool.filter(isMarked).length,
    relevantInPool,
  }
}
