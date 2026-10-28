# Shared posting index

Implemented 2026-10-15. Validation uses synthetic postings, mocked providers and
local Chroma; no live collection, embedding or evaluation requests were made.

## Collection sources

Greenhouse and Lever discovery and collection were removed at the user's request.
The source options are LinkedIn, Indeed, Glassdoor and SEEK. Existing caches and
saved results are not migrated or deleted by this code change. Old preferences
retain supported boards; feed-only preferences require a new board selection.

## Storage and incremental updates

Web searches publish public posting vectors into `.cache/job_index/`, configurable
with `JOB_INDEX_DIR`. Stable
posting identities and content versions avoid embedding unchanged postings again.
Changed text creates a new version; each search atomically saves `job_scope.json`
with its eligible version IDs. Retrieval filters to those IDs, so unrelated jobs
in the shared store cannot enter that search. Candidate-specific screening hints
are excluded from shared metadata; resumes and profiles remain separate.

Versions unseen for seven days are removed on subsequent index writes. This is
opportunistic cleanup, not a scheduled collector or proof that a job has closed.
Expired scopes require a new search. Existing result snapshots and assessments
remain intact. Find More continues to skip already-assessed postings; changed
postings are not automatically reassessed. Deleting a run does not delete shared
public postings. Existing per-run vector stores and the CLI path remain supported.

## Retrieval and evidence

HNSW and BM25 still contribute rankings through reciprocal rank fusion. Full
posting text is restored for requirement evidence and evaluation. Existing
seniority, experience, shortlist and scoring policies are preserved.

Eligible documents and BM25 statistics are loaded once per cached scope, with
an inverted lexical index reused across query signals. The in-process cache is
bounded to 32 scopes and 20,000 documents in total. Returned evidence is copied
so evaluation cannot mutate the cached retrieval corpus.

The shared HNSW index uses `ef_search=500`. A filtered synthetic benchmark at
100 returned 92% mean ANN recall@20; increasing the search effort improved that
fixture to 100%. A separate seed evaluated after choosing 500 returned 98.33%,
so exact-neighbor recall is still not guaranteed.

## Measurements and limitations

All comparisons use 5,000 synthetic documents, 1,536-dimensional generated vectors,
30 single-signal queries and K=20. There is no embedding provider. The original
hybrid baseline and proposed cached path use the same corpus and query inputs.

| Measurement | Seed 42, ef=500 | Separate seed 84, ef=500 |
| --- | --- | --- |
| Original hybrid p50 / p95 | 59.071 / 62.955 ms | 58.677 / 62.096 ms |
| Warm shared hybrid p50 / p95 | 18.062 / 18.780 ms | 18.036 / 18.828 ms |
| First shared query | 79.220 ms | 79.466 ms |
| Unfiltered mean ANN recall@20 | 100% | 100% |
| Filtered mean / minimum ANN recall@20 | 100% / 100% | 98.33% / 90% |
| Identical ordered hybrid shortlists | 30/30 | 30/30 |

Warm median retrieval was about 3.3 times faster; the first corpus load was slower
than the original baseline. These local timings exclude scraping, network
embeddings and model evaluations. Multiple profile signals and early-career
semantic expansion can cost more than this single-signal fixture. Synthetic
clusters and nondeterministic HNSW construction limit generalization.

There are zero human-labeled cases: suitable-job recall, strong-match precision
and missed suitable jobs remain unknown. Exact-vector agreement and unchanged
synthetic shortlists do not establish real candidate-fit accuracy.

Recorded outputs: [ef=100 baseline](benchmarks/shared-index-ef100-2026-10-15.json),
[ef=500 comparison](benchmarks/shared-index-ef500-2026-10-15.json),
[separate seed](benchmarks/shared-index-seed84-2026-10-15.json).

```bash
python -m scripts.benchmark_retrieval --documents 5000 --dimensions 1536 \
  --queries 30 --k 20 --seed 42 --ef-search 500 --output /tmp/shared-index.json
# Repeat with --ef-search 100 for the baseline or --seed 84 for the separate fixture.
```

The collection flow uses general job boards, incremental indexing, HNSW/BM25
shortlisting, then evidence-based evaluation. More collected postings help only
when they add relevant coverage; collection budgets still constrain coverage.
