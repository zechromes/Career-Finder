# Collection caching, freshness, and retrieval measurement

Implemented 2026-10-15. No live job boards, embedding providers, or evaluation
providers were called for validation or benchmarking.

## Behavior

`backend/search/collection_cache.py` stores complete, non-empty collection results
in `.cache/job_collections/`. Keys hash the collection policy version, provider,
ordered roles/locations/boards, collection limit, adaptive settings, previously seen posting identities, remote flag,
explicit search filters and posting-age limit.
Order matters because some board budgets are consumed by earlier queries first.
The key contains no credentials or candidate profile. Cache payloads contain public
posting records and their collection timestamp, not the search parameters.

A fresh hit skips collection and rechecks posting-age eligibility against the
current date. Different scopes get separate entries. Expiry recollects the search
and replaces its entire result set, so changed descriptions and removed search
results are not merged into the new batch. Existing embedding caching reuses
unchanged content; changed descriptions produce new embedding cache keys.

**Find more jobs** always requests fresh collection. Python callers may pass
`force_refresh=True` to `fetch_job_vacancies`. Normal identical searches share
cached results across runs. This cache provides exact-search reuse alongside the
[shared posting index](shared-job-index.md); neither continuously discovers all vacancies. Constrained searches now use the bounded allowance described below.

- Default TTL: 900 seconds (15 minutes), capped at 24 hours.
- Default bound: 256 entries, configurable up to 4,096.
- `JOB_COLLECTION_CACHE_TTL_SECONDS=0` or `JOB_COLLECTION_CACHE_MAX_ENTRIES=0`
  disables reuse and writes. Existing files are not deleted by disabling it.
- `JOB_COLLECTION_CACHE_DIR` overrides the directory. The default is resolved
  through `backend/paths.py`.
- Writes are atomic. Expired/overflow hashed entries are removed on successful
  writes; this is opportunistic cleanup, not a background retention scheduler.
- Identical concurrent requests share one collection within the supported single
  API process. Waiting searches check cancellation. Unrelated hash-lock collisions
  can briefly serialize requests; there is no distributed locking.
- Empty results, exceptions, reported source errors and cancelled collections are
  not cached. An expired entry is not used as a fallback when refreshing fails.
- JobSpy can emit an ERROR and return partial rows. The wrapper observes selected
  board loggers, reports the affected board and suppresses cache writes. Explicit
  HTTP 429 and 403 statuses are identified as rate limiting and blocking; other
  errors have an unconfirmed cause. Raw log details are not exposed. Partial
  results are retained. A rate limit is recognized where the HTTP 429 is seen (a
  JobSpy log status, a description request or a SEEK response) and passed on as a
  marked message, not by matching words in error text; a SEEK 403 block stays a
  visible error. Rate-limit (429) messages go to the server log, not the
  page; the page instead shows a calm note under "Fewer jobs from some boards"
  naming the board, with no retry prompt. A listing request that returns 429 with no rows is retried once after a
  30-second pause. Overlapping
  searches on the same board conservatively share this error signal; an error
  may also prevent caching another concurrent search on that board. This observer
  cannot detect failures the library neither raises nor logs.
- An unavailable/corrupt cache falls back to collection. Logs added by the wrapper
  contain cache-hit status, row count and duration, not resume text or queries.

A recent collection timestamp does **not** verify that a posting remains open.
Unknown posting dates retain the existing handling; results remain unverified.
Deleting a run removes its private workspace, not this shared public-posting cache.

## Initial measurement (before shared indexing)

Reproduce the offline benchmark in the application environment:

```bash
python -m scripts.benchmark_retrieval --documents 2000 --dimensions 128 \
  --queries 30 --k 20 --seed 42 --output /tmp/retrieval-benchmark.json
```

[Recorded output](benchmarks/retrieval-2026-10-15.json) includes dependency versions,
HNSW configuration, sizes and limitations. The benchmark uses real persistent
Chroma with seeded synthetic clustered vectors, no embedding model. It uses the
same corpus for exact L2 and HNSW queries; it also exercises the actual application
hybrid retrieval function with a local fixed embedding adapter. One warmup vector
query is excluded. Query timings exclude network embedding/evaluation requests.

| Measurement | Result |
| --- | --- |
| Synthetic documents / queries / vector dimensions | 2,000 / 30 / 128 |
| HNSW settings | L2; M=16; construction ef=100; search ef=100 |
| Mean/minimum ANN recall@20 vs exact vectors | 100% / 100% |
| Missed exact neighbors across 30 queries | 0 |
| Exact vector ranking p50 / p95 | 0.257 / 0.315 ms |
| Chroma vector search p50 / p95 | 0.556 / 0.684 ms |
| Application hybrid retrieval p50 / p95 | 23.009 / 24.949 ms |
| Index construction | 294.687 ms |
| Two identical searches: source calls without/with cache | 2 / 1 |
| Cached versus uncached synthetic posting pool | Identical |

A second run used 5,000 documents and 1,536-dimensional synthetic vectors,
with the same seed, 30 queries, K=20 and HNSW configuration:

```bash
python -m scripts.benchmark_retrieval --documents 5000 --dimensions 1536 \
  --queries 30 --k 20 --seed 42 --output /tmp/retrieval-large.json
```

[Recorded larger-vector output](benchmarks/retrieval-5000-1536-2026-10-15.json):

| Measurement | Result |
| --- | --- |
| Mean/minimum ANN recall@20; missed exact neighbors | 100% / 100%; 0 |
| Exact ranking p50 / p95 | 6.208 / 8.233 ms |
| Chroma vector search p50 / p95 | 1.058 / 1.291 ms |
| Application hybrid retrieval p50 / p95 | 55.350 / 113.472 ms |
| Index construction | 1,132.102 ms |

Both corpus size and dimensionality differ, so these two runs do not isolate the
effect of corpus size. HNSW was faster than exhaustive ranking in this second
configuration; the application hybrid path was much slower than vector lookup.
Synthetic clusters can be easier to search than real embeddings. The larger
vector size is representative of the configured embedding model's default size,
but these are still generated vectors, not that model's output.

Exact ranking uses in-memory NumPy; Chroma timings include database/document
retrieval overhead. This is not an isolated algorithm speed comparison. At this
small size, exact ranking was faster; changing index implementations is not
justified by this result. The original hybrid path fetched the corpus and rebuilt
BM25 statistics per query signal. Its latency will grow with corpus size and the
number of role/skill/work queries. The benchmark uses one signal per query.

Collection-call reduction is a deterministic synthetic check, not a measured
production scrape speedup. There are **zero human-labeled cases**: label coverage
is zero; candidate-fit recall, strong-match precision and missed suitable jobs
are unknown. ANN recall is not relevance recall, and the synthetic vectors do not
measure OpenAI embeddings. No ranking improvement is claimed.

When human labels are available, export baseline and proposed shortlists over the
same pool and run `python -m scripts.measure_matching labels.json` for each. Include
outside-shortlist jobs, seniority gaps, transferable skills, missing evidence and
conflicting requirements; keep tuning profiles separate from held-out profiles.
Report labeled-pool coverage, observed recall@K, strong-match precision on labeled
predictions and missed known positives. Do not infer full recall from partial labels.

## Implemented collection and retrieval follow-up

Versioned shared indexing, retained HNSW/BM25 evidence retrieval, and reusable
lexical statistics are implemented. Greenhouse/Lever feeds were subsequently removed.
See [behavior, updated benchmarks and limitations](shared-job-index.md). The
initial timings above describe the earlier baseline, not the optimized shared path.

Sources: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html),
[Lever public postings](https://github.com/lever/postings-api),
[Chroma collection configuration](https://docs.trychroma.com/docs/collections/configure),
[JobSpy](https://github.com/speedyapply/JobSpy).

## Explicit filters and collection allowance

Work arrangement and seniority use the same matcher during collection and before
retrieval. Structured work type takes precedence; contextual phrases distinguish
remote work from unrelated uses such as remote-control equipment, and negative
phrases do not establish remote eligibility. Unknown work arrangement does not pass
an explicit arrangement filter. Seniority uses title word boundaries; unmarked
roles remain possible entry/mid candidates, not verified entry/mid positions.

Web searches use the [combined adaptive budgets](job-search-providers.md#adaptive-web-collection),
with early filtering before description requests. Budget-limited successful pools
can be cached; complete means no detected source failure, not exhaustive coverage.

For legacy fixed collection, when work type, seniority or exclusions constrain a search, the collector requests
up to three times the normal per-query/provider allowance, then caps eligible
records to the requested count per source. This is one bounded collection pass,
not an unbounded refill/retry loop. Provider pagination and available records can
still leave fewer results. General-location matching remains unchanged.
