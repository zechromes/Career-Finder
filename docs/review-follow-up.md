# Review findings — October 2026

This change addresses the supported findings in the supplied review. Existing
stored assessments are not rewritten. No live model or job-board calls were used.

| Finding | Resolution |
| --- | --- |
| Missing resume evidence downgraded to unknown | Retained deliberately: absence is not proof of inability. Verified negative evidence and deterministic employment/seniority guards still reject demonstrated mismatches. Academic study/projects remain excluded from professional years. |
| Useful partial agreement hidden | Display completed/agreeing counts and a clearly provisional average for two completed scores. Preserve the conservative final verdict; agreement is not confidence. |
| Independent requirement denominators | Added source-quote comparison in job details. Only identical verified passages are aligned; each model retains its independent evidence. No claim that denominators are now equivalent or that extraction is shared. |
| Substring work-type/seniority matching | Shared contextual work-type and title-boundary matching replaces broad substring decisions. Unknown work arrangement stays unknown; unmarked titles remain eligible for explicit entry/mid searches. |
| Role count changes retrieval weighting | Fixed total weight per role/skills/work signal group; lexical and semantic results each receive half of a query's contribution. |
| Filtering consumes collection budget | One bounded collection allowance of up to 3× for constrained searches; filter before retaining the requested per-source count. No unbounded refill or extra rate-limit retries. |
| Sequential upload model requests | One structured OpenAI classification-and-profile request, validated before run allocation or PDF persistence. Invalid, refused or inconsistent outputs remain errors. |
| Repeated assessments and long batches | Private, bounded seven-day assessment cache keyed by all substantive inputs; per-provider waves of 15. Cancellation and targeted retries remain supported. Do not use one model's rejection to bypass independent assessments. |
| Actions lost on new run | Saved/applied/dismissed flags persist with the saved resume, keyed by normalized posting URL. Browser flags migrate and pending offline edits retry on reopening. Temporary runs remain the owner until saved. |

## API and storage

`GET /api/searches/{run_id}/actions` returns `{"actions": {key: flags}}`.
`PUT` to the same path accepts `{"key": "https://example.test/job", "action":
"saved", "value": true}`; actions are `saved`, `dismissed` or `applied`.
The saved profile owns flags when linked; otherwise the run owns them. A maximum
of 10,000 distinct action keys per owner prevents unbounded growth. The browser
normalizes tracking URLs and preserves older job-ID flags for migration. Clients
should use the same canonical key for the same posting.

Private assessment caches live at `data/profiles/<profile_id>/evaluations/` or
`frontend/runs/<run_id>/evaluations/` before profile saving. They are distinct from
public collection/embedding caches. Profile edits invalidate reuse through the
content-based key, rather than silently using an old assessment. Deleting an owner
removes its cache; deleting a run does not delete its independent saved profile.
Clearing browser storage alone does not delete server action flags.

## Evidence and limitations

Regression tests use synthetic documents, temporary owner directories and mocked
providers. They cover combined upload validation, cache hits/expiry/corruption and
failed/cancelled requests, bounded waves, permanent provider failures, partial
agreement, collection filtering, action continuity and browser synchronization.
Existing evidence/experience tests cover missing evidence and demonstrated gaps.
Browser checks cover server-restored actions and accessible model comparisons.

No human-labeled dataset is available: observed job-match recall@k, strong-match
precision, label coverage and missed relevant jobs cannot be estimated. The
weighting tests establish stable signal budgets, not greater relevance. Previously
recorded synthetic HNSW recall measures approximation to exact vectors, not human
job suitability. Provider latency, token savings and classification accuracy need
a separately authorized live benchmark. Duplicate postings with different canonical
URLs may still retain separate action flags; cross-board identity is not inferred
from title alone.

## Verification — 18 October 2026

- Standard `scripts/check.sh`: passed (backend, generated contracts, frontend,
  compatibility test and production build).
- Final backend suite: 168 tests passed; provider cache integration and exhausted
  rate-limit wave stopping were also checked directly.
- Frontend: 54 tests plus one legacy compatibility test passed.
- Mocked browser suite: 22 workflows passed, including accessibility checks,
  server-restored job actions and the requirement comparison view.
- No live provider calls or human-labeled matching evaluations were performed.
