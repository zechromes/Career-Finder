# Retrieval and evidence review

## Implemented

- LinkedIn, Indeed and Glassdoor now share title-overlap screening before optional
  detail requests. This is a request-budget heuristic, not evidence of candidate
  fit. It can omit relevant jobs with different titles before semantic retrieval;
  no labeled baseline/held-out comparison is available. See the JobSpy staging
  and pool controls in [provider behavior](job-search-providers.md).

- Collection and retrieval share normalized location matching, including a curated
  Australian metro lookup, full place-name matching and explicit geographic conflict
  checks. Inputs and original posting text are unchanged. See
  [location matching scope and limitations](job-search-providers.md#general-location-input).
  Synthetic geographic cases pass; there is no human-labeled job-match recall estimate.

- Automatic seniority now prioritizes unmarked/early-career titles ahead of clearly experienced-level titles for early-career profiles before applying top-K. Since 28 October 2026, for profiles that are early-career only by years (mid or unknown career level), a senior, lead, staff or principal title is held back only when the posting states more years of experience than the profile; graduate/entry/junior profiles and director/head-of/chief titles keep the title rule. On a single-profile pilot (82 human labels, also used to design the rule), all 15 senior-titled good fits stopped being held back while 11 of 15 senior-titled not-a-fit jobs still were; across that pool, held-back jobs fell from 71 to 31 of 158. No held-out evaluation exists yet. Other levels remain in the candidate pool and can fill spare shortlist slots. Explicit levels and All levels override this preference. This uses the existing experience guard; it is not a measured improvement in recommendation accuracy.

- Focused embeddings already exclude explicit profile name/soft-skill/education/seniority fields and job company/location fields. Heading-based boilerplate cleaning remains intentionally conservative; unstructured boilerplate can remain.
- Retrieval now queries each selected target role, technical skills, and recent work separately. Each query contributes an embedding ranking and BM25 ranking over the cleaned job text. Reciprocal rank fusion (constant 60) combines their positions. Role intent, skills and recent-work groups each receive total weight 1 when present; role weight is divided across distinct selected roles, and each query splits its contribution equally between semantic and lexical rankings. Candidate windows are up to 3 × K, with a floor of 50, bounded by corpus size. “All jobs” still returns the entire pool. Location filtering remains separate. RRF values are not probabilities or similarity scores.
- Job vectors are cached by embedding model, text-policy version and cleaned-content SHA-256. URL alone is insufficient: postings can change at the same URL. Files live in `.cache/job_embeddings` (override `JOB_EMBEDDING_CACHE_DIR`), expire for reuse after 30 days, and can be removed safely. Candidate query vectors are not cached. Original job text remains available to evaluation.
- Deduplication retains canonical-URL matching and adds cross-board normalized company/title/location matching plus description similarity of at least 0.95. Descriptions shorter than 100 characters are not merged by this heuristic. Distinct similar openings can still exist; tune against labeled duplicates.
- Posting requirements are now identified once without a resume, cached by content/model/extraction policy, and supplied as shared IDs to every evaluator. Evaluators cannot add, omit or redefine criteria. Evaluation requests include per-requirement verdicts, mandatory/preferred/unclear classification, job and profile quotes, and explanations. Quotes are checked against the supplied source text, ignoring case and whitespace. Missing/invalid evidence becomes unknown, not an automatic rejection. Strict output schemas reject unexpected fields. Job content is delimited and explicitly treated as untrusted evidence.
- The application computes scores: mandatory weight 2, preferred/unclear weight 1; unclear importance requires review and cannot trigger mandatory mismatch rejection; met earns 1, partial 0.5, unknown/not met 0. A verified mandatory mismatch excludes a job; all mandatory criteria must be met and score ≥80 for strong match. Missing mandatory criteria/uncertain experience require review. Category caps remain 79 for review and 39 for excluded. No usable evidence gives no score. The model's original numeric score is ignored. These are transparent policy thresholds, not calibrated hiring probabilities.
- Result details display each requirement and verified quote. The resume/selected-role prompt prefix stays identical between jobs to permit automatic provider caching where supported; no cache-hit or billing guarantee is made.

Quote substring checks verify provenance, not semantic entailment or completeness. The shared extractor can still omit a requirement, misclassify its importance, or interpret a valid quote incorrectly; every evaluator then shares that extraction limitation. Human precision measurement is still required. Existing persisted results retain their original scores; start a new search for the new rubric.

## Suggestions that need more work or evidence

| Suggestion | Decision and reason |
|---|---|
| Separate cheap structured posting extractor + per-job facts cache | Shared candidate-independent requirement extraction and its cache now run before evaluation. They are not a pre-retrieval facts filter; salary/work-type fact extraction remains in evaluation. Adding a new call for every posting may increase total cost. Before enabling it, benchmark extraction accuracy, quote coverage and provider costs; only use source-verified facts for hard filtering. Current work-type/seniority text filters remain a limitation. |
| Cheap model rejects first; stronger model assesses survivors | Not enabled. An erroneous early rejection permanently harms recall. Start with shadow-mode decisions and measure false negatives before making this a hard gate. Each shortlisted job is independently evaluated by Claude, GPT and Gemini, with successful assessment reuse when inputs are unchanged. |
| Explicit provider prompt-cache controls | Not enabled. Providers differ in cache eligibility, minimum lengths, lifetimes and charging. An identical profile prefix makes reuse possible but does not ensure concurrent first requests share a cache entry. Verify provider behavior and usage counters before promising savings. |
| Adaptive stopping after N matches or a budget | Not enabled. Current top-K is an explicit upper bound on jobs evaluated, not a token/currency budget. Stopping on uncalibrated “strong” predictions can conceal retrieval/evaluation errors. Implement a visible user-selected cap with bounded scheduling after precision is measured. |
| Replace Chroma with NumPy | Not necessary for this improvement. Chroma preserves existing persistence/recovery integration. A small-corpus cosine index is viable, but migration itself does not improve relevance. |
| Adjacent-title query expansion | Not silently enabled. Selected roles remain the user's search scope. Suggested adjacent titles need an opt-in UI and measured expansion recall; selected-role multi-query retrieval is implemented now. |
| Check live links / ghost jobs | Results remain explicitly unverified. HTTP 200 does not prove a vacancy exists; login pages, anti-bot challenges and closed-job pages complicate checks. A future bounded checker should report reachable/closed/unknown and prevent requests to private network addresses. |
| Prefer permitted official sources | JobSpy is the default for general boards; SEEK uses direct collection. Adzuna remains available with `JOB_SEARCH_PROVIDER=adzuna`. This change does not assert permission to scrape any board. Review each source's current terms before deployment. |

## Measure quality before claiming improvement

Create human labels for 50–100 representative profile/job pairs, including career changes, unknown experience, hard mismatches and jobs outside the shortlist. Prefer labeling full candidate pools for exact recall. Keep held-out profiles separate from tuning examples. Do not use the same model to generate the human ground truth.

`python scripts/measure_matching.py labels.json` accepts an array like:

```json
[
  {
    "query_id": "profile-001",
    "pool": ["job-a", "job-b", "job-c"],
    "labels": {"job-a": true, "job-b": false, "job-c": true},
    "shortlist": ["job-a", "job-b"],
    "predicted_strong": ["job-a"]
  }
]
```

Compare old single-query and new hybrid rankings at the same K. The script reports recall over labeled positives, precision over labeled strong predictions, unlabeled counts, missed known positives and a reproducible random sample outside the shortlist. Partial labels produce **observed** recall, not unbiased full-pool recall. Label the outside sample and report uncertainty; collect latency, requests, token usage and actual cost alongside relevance.

No quality gain or cost reduction has been measured on real labeled data yet. Unit tests validate logic and boundaries, not recommendation accuracy.

References: [Elastic RRF documentation](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion), [Anthropic contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval). Their findings motivate hybrid retrieval; they do not establish performance on this application's jobs.

## Collection reuse and offline retrieval benchmark (2026-10-15)

The collection cache now reuses complete identical searches without changing
ranking, scoring or the collection budget. See [implementation and measured
results](collection-caching.md). Synthetic HNSW recall against exact vector
neighbors was measured; human-labeled job-match recall and strong-match precision
remain unavailable. These measurements do not establish a matching-quality gain.


## Adaptive collection (2026-10-20)

Web collection now uses shared batch, detail-fetch, candidate and soft time limits
instead of a fixed per-board quota. Early filters, posting-history deduplication,
title-prioritized description selection with exploration, and eligible-yield
expansion bound the pool before the existing hybrid retrieval runs. See
[provider behavior](job-search-providers.md#adaptive-web-collection).
Ranking weights, HNSW settings and evaluation policy are unchanged. The collected
corpus can differ; no human-labeled baseline is available to establish relevance
recall, precision or missed suitable jobs. Mocked regression checks establish
budget/filter/pagination behavior, not real-world speed or matching quality.

## Explicit dismissal preferences (26 October 2026)

Future shortlists can use owner-scoped dismissal reasons as a stable partition of
the retrieved candidate pool: matching postings move below other postings, with
existing relevance order retained within each group. Automatic early-career title
prioritization remains the primary partition. Top-K is applied afterward; All jobs
still retains every retrieved job. No changes to evidence scoring, provider prompts,
shared requirements, or experience/seniority guards are made.

Matching is deliberately explicit: normalized exact role title or location,
unambiguous title-level group, or a clearly stated comparable salary below a user
minimum. Unknown/ambiguous data is not penalized. See
[dismissal preferences](dismissal-preferences.md) for parser limits and reversibility.
No human-labeled baseline/held-out set was available; synthetic tests demonstrate
ordering and isolation, not improved recall or recommendation accuracy.
