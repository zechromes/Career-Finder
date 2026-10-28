# Career Tracker: workflow and technical guide

Verified against the repository code on **26 October 2026**.

This guide explains the web application's main workflow, the components behind
it, the data they exchange, and the decisions that affect the result. The CLI has
an explicit provider selector; the normal web workflow evaluates with all three
providers. Configuration defaults below describe the code, not a guarantee of
provider availability or this machine's environment overrides.

Quick navigation:

- [Architecture](#2-the-architecture-in-plain-language) and [upload](#3-upload-and-extract-a-candidate-profile)
- [Collection](#5-collect-jobs-and-build-an-eligible-pool) and [ranking](#6-index-and-rank-jobs)
- [Shared requirements](#7-extract-and-freeze-shared-requirements), [providers](#8-assess-with-claude-gpt-and-gemini), and [scoring](#9-validate-evidence-and-compute-the-fit-score)
- [Failures and retries](#11-failures-retries-and-cancellation), [storage](#12-storage-and-cache-boundaries), and [API routes](#13-main-http-interactions)

## 1. Start with the animated flowchart

- [Interactive animated flowchart](images/application-workflow-flowchart.html): open in a browser, then use Play/Pause, previous/next, the slider, or click a box. On a small screen, scroll the diagram horizontally.
- [Shareable animated GIF](images/application-workflow-flowchart.gif).

Solid arrows show normal processing. Dashed amber arrows show recovery or another
search. Green boxes and moving dots highlight the current explanatory stage.
The animation is a conceptual model, not a live recording or latency benchmark.

After shortlisting, the diagram describes **one posting's path**. Other postings
may be at different stages at the same time. There is no global requirement that
every job finish extraction before any job can be assessed. Provider results are
validated and published as they arrive, without waiting for the whole batch.

```mermaid
flowchart TD
    U[Upload PDF] --> P[Local text / OCR and OpenAI profile extraction]
    P --> C[User reviews profile and confirms preferences]
    SP[Reopen saved profile] --> C
    C --> B[Collect, constrain and deduplicate postings]
    B --> R[Hybrid retrieval: semantic + BM25]
    R --> S[Shortlist and publish pending rows]
    S --> Q[Load validated requirements or extract with OpenAI]
    Q --> A[Claude assessment or private cache]
    Q --> G[GPT assessment or private cache]
    Q --> M[Gemini assessment or private cache]
    A --> V[Validate and score each arriving provider result]
    G --> V
    M --> V
    V --> J[Merge compatible results and update UI]
    J --> W[Save / reopen / export]
    J --> F[Find more jobs]
    F --> B
    Q -. persistent failure .-> E[Visible failure checkpoint]
    V -. persistent failure .-> E
    E --> T[Retry failed provider/jobs; preserve successes]
    T -. reuse valid shared requirements .-> Q
```

Upload failures stop before workspace creation. An empty collected pool finishes
without evaluation. Failed board searches have their own **Retry scraping** path
back to collection. These exceptions are explained below rather than adding every
edge to the main diagram.

## 2. The architecture in plain language

| Component | Responsibility | Main files |
| --- | --- | --- |
| Vue + TypeScript | Upload/review screens, preferences, results and job actions | `frontend/src/` |
| Pinia store | Keep the browser synchronized with the current run | `frontend/src/stores/pipeline.ts` |
| FastAPI routes | Validate HTTP requests and dispatch to handlers | `backend/app.py`, `backend/routers/` |
| Profile service | Read PDFs, extract profiles, save and reopen profiles | `backend/profiles/` |
| Search service | Collect jobs, apply constraints, index and retrieve | `backend/search/` |
| Evaluation service | Share requirements, run providers, validate, score and retry | `backend/evaluation/` |
| Runtime state | Coordinate active workers, cancellation, snapshots and retention | `backend/runs.py`, `backend/runs_api.py` |
| Schema models | Define allowed request, response, profile and assessment shapes | `backend/schemas/` |

`run_app.sh` launches FastAPI on `127.0.0.1:5000` and Vite on `localhost:5173`.
Vite proxies `/api` requests to FastAPI. The launcher no longer opens a browser
tab automatically. Use one Uvicorn worker: active run state and coordination locks
are held in that process. This restriction does __not__ mean evaluation requests
are sequential; thread pools still overlap provider calls inside the process.

Routes are thin adapters. For example:

```text
POST /api/resumes/upload
  → backend/routers/uploads.py
  → backend/profiles/upload.py
  → local PDF extraction + OpenAI classification/profile extraction
  → create and persist the workspace after successful extraction
```

The optional Sheets integration and optional tracing are not required steps in
the user workflow. No service in this diagram automatically applies to jobs.

## 3. Upload and extract a candidate profile

**Input:** a PDF resume. **Output:** a structured profile and workspace/run ID.

The upload handler checks the filename, content type, PDF signature and content.
The code accepts up to 5 MB and 1–20 pages, and rejects unreadable/encrypted or
oversized-page PDFs. Local extraction reads text; OCR supports scanned documents.
OpenAI receives the extracted text to classify the document and produce a profile.

The current upload path combines classification and extraction into one logical
structured request. SDK retries can still mean more than one HTTP call. The upload
request waits for extraction; it does not return a placeholder ID while an
untracked extraction thread continues.

A successful response uses HTTP 201. Invalid documents can return 400, 413 or 422,
depending on the failed check; provider/extraction verification failures return
503. Rejected documents and failed classification do not create a saved workspace
PDF. Temporary extraction resources are cleaned up.

The profile is an interpretation of the resume and can contain mistakes. The user
therefore reviews it before searching. Academic study and personal projects do
not count as professional employment years in the documented experience rules.

Source: [upload.py](../backend/profiles/upload.py),
[extraction.py](../backend/profiles/extraction.py).

## 4. Review the profile and confirm preferences

The user checks or edits the candidate profile and chooses target roles, locations,
boards, work arrangement, exclusions, seniority and shortlist size. Confirmation
starts the search worker. Uploading alone does not search job boards.

A saved profile keeps the resume and extracted profile independently of a temporary
run. Reopening it can recover an existing linked workspace rather than extracting
the PDF again. Reopening does not automatically begin a new search. Where available,
an assessment journal can restore missing history without replacing existing rows.

`top_k` controls the shortlist: it does not set how many jobs each board collects.
`top_k=0` means all retrieved jobs. Automatic seniority prioritizes compatible titles
during ranking; explicit seniority selection can filter the collected pool.

Source: [search/service.py](../backend/search/service.py),
[profiles/service.py](../backend/profiles/service.py).

## 5. Collect jobs and build an eligible pool

**Input:** confirmed preferences. **Output:** unique postings with available text.

The default board collection uses JobSpy for supported boards and a dedicated SEEK
path. A configured Adzuna alternative also exists. Only selected sources are
searched. The collector uses small batches and expands sources that return useful,
eligible, unique jobs.

Default adaptive limits are 12 search batches, 60 fallback description fetches,
150 eligible candidates and a 120-second soft deadline. A soft deadline prevents
new work after the budget is reached; it does not guarantee an already-running
network call finishes within that time. JobSpy's own description requests are
outside the fallback-fetch counter.

Collection and subsequent screening handle location/date constraints, requested
filters and duplicates. Work-arrangement, title/company exclusions and explicit
seniority constraints can remove jobs before retrieval. Cross-board duplicate
checks combine identities and description similarity; these remain heuristics.

A board failure is recorded while other sources can continue. If no jobs remain,
the flow ends without extraction or evaluation. **Retry scraping** reuses confirmed
preferences and targets failed sources, retaining existing results. Availability of
a collected posting is not independently verified.

Source: [collection.py](../backend/search/collection.py),
[filters.py](../backend/search/filters.py),
[provider guide](job-search-providers.md).

## 6. Index and rank jobs

**Input:** eligible postings and candidate search context. **Output:** a shortlist.

An embedding is a numeric representation of text used to compare meaning. The
application uses OpenAI `text-embedding-3-small` for the posting-vector path and
Chroma to store/search shared public posting versions. Unchanged posting vectors
can be reused. Each search keeps its own eligibility scope so it does not suddenly
retrieve every job ever added to the shared index.

Retrieval creates queries from selected roles, technical skills and recent work.
Each query contributes two rankings:

- **Semantic ranking:** similarity of embedding vectors.
- **BM25 ranking:** lexical relevance based on words and their distribution.

**Reciprocal rank fusion (RRF)** combines positions rather than pretending the two
ranking scores have the same units. With constant 60, a ranking contributes
`weight / (60 + rank)` to a candidate's combined ordering. Role, skill and
recent-work query groups are balanced by the configured query weights.

Before shortlist selection, explicit dismissal preferences can move matching jobs
below other retrieved jobs while preserving relevance order within each group.
Automatic early-career title prioritization remains primary. This is owner-scoped
preference ordering, not provider training; see [dismissal preferences](dismissal-preferences.md).

The resulting ranking is a way to choose what to assess. It is not the final fit
score or a hiring probability. Automatic seniority can prioritize appropriate
unmarked/early-career titles before top-K selection. Other eligible levels can
remain in the pool.

The shortlist is published as **pending result rows** before remote assessments
finish. This is why jobs can appear before their scores do.

Source: [ranking.py](../backend/search/ranking.py),
[retrieval.py](../backend/search/retrieval.py),
[shared_index.py](../backend/search/shared_index.py),
[matching guide](matching-improvements.md).

## 7. Extract and freeze shared requirements

**Input:** posting text only, with no candidate resume. **Output:** a `RequirementSet`.

This stage gives the providers a common set of questions. Without it, independent
models could invent different denominators by assessing different requirements.

The current extraction policy is `requirements-v5`:

1. Number the original posting lines.
2. Ask OpenAI for structured requirements with inclusive `source_start` and
   `source_end` line references. Strict JSON-schema enforcement is explicitly enabled.
3. Validate the schema and bounds. Reject reversed, nonexistent or blank-only ranges.
4. Copy selected text from the __original posting__ into `job_quote`. The model does
   not reproduce the quote itself.
5. Validate nonempty criteria, quote provenance and duplicate criteria. Clear an
   unsupported optional section label instead of blocking an otherwise valid quote.
6. Assign stable source-ordered IDs such as `req_001` and freeze the shared list.

A persisted criterion contains `requirement_id`, `requirement`, `importance`,
`job_quote`, `section` and `type`. Importance is `must_have`, `nice_to_have` or
`unclear`; types distinguish skills, experience, education, eligibility,
responsibilities and other criteria. Source coordinates are extraction inputs,
not extra fields in the saved criterion.

Concurrent providers share one loader result per posting, including a shared
extraction failure. Valid public-cache hits skip the extraction call. Invalid
output receives one automatic correction retry. A persistent failure blocks that
posting's assessments; the system does not silently let each provider invent its
own list.

Line references guarantee where the quote came from. They do not prove that the
model summarized it correctly, classified importance correctly, or found every
requirement. A single-line posting may produce a broad quote. Frozen historical
lists are validated and retained rather than silently rewritten.

Source: [requirements.py](../backend/evaluation/requirements.py),
[evaluation schemas](../backend/schemas/evaluation.py).

## 8. Assess with Claude, GPT and Gemini

Each provider receives the same frozen criteria plus candidate context, posting
and selected roles. Each must return exactly one verdict for each requirement ID
and preserve its canonical fields. It cannot add, drop, split, merge or reclassify
requirements. Verdicts are `met`, `partial`, `not_met` or `unknown`, with resume
quotes and explanations.

The three provider batches run concurrently. Each advances independently in waves
of 15 and uses its own per-job concurrency. One provider's negative verdict never
skips another provider. Provider-tagged retries run only the failed provider/job.

| Setting | Default in code |
| --- | --- |
| Requirement extractor | `gpt-4o-mini`; override `REQUIREMENT_EXTRACTION_MODEL` |
| Resume upload | `OPENAI_UPLOAD_MODEL`, otherwise profile model default `gpt-4o-mini` |
| Claude evaluator | `claude-sonnet-5-5` |
| GPT evaluator | `gpt-6.1-sol` |
| Gemini evaluator | `gemini-4-argon` |
| Concurrent jobs per provider | Claude 4, GPT 4, Gemini 2; configured counts capped at 8 |
| Extraction timeout | 90 seconds per request |
| Evaluation timeout | Claude/Gemini 90 seconds; GPT 180 seconds by default |
| GPT timeout override | `GPT_EVALUATION_TIMEOUT_SECONDS`, clamped to 30–600 |
| Gemini proactive RPM | 0 by default; pacing can be enabled, backoff still applies |
| Claude output limit | 8,192 tokens |

GPT's configured default uses low reasoning; Gemini's configured default uses low
thinking. These options apply to the supported model IDs in code, not arbitrary
overrides. Environment overrides can change actual runtime choices.

OpenAI uses native JSON-schema dictionaries with `strict=True`, followed by local
Pydantic validation. This avoids the SDK typed-`parsed` serialization path that
previously warned about a `JobEvaluation` value. Claude's raw response envelope is
checked for parsing failures and output truncation. No provider is silently
substituted when another fails.

Source: [providers.py](../backend/evaluation/providers.py),
[orchestration.py](../backend/evaluation/orchestration.py),
[provider configuration guide](EVALUATION_MODELS.md).

## 9. Validate evidence and compute the fit score

The backend first checks schema validity, exact shared IDs and unchanged canonical
fields. It then verifies job and resume quotes against their source text, ignoring
case and whitespace. Missing or invalid evidence becomes **unknown** rather than
a proven inability. Only criteria with verified job evidence enter the score's
denominator.

The backend computes the score; the provider's proposed numeric score is ignored.

| Importance | Weight | Verdict | Credit |
| --- | ---: | --- | ---: |
| Mandatory | 2 | Met | 1 |
| Preferred | 1 | Partial | 0.5 |
| Unclear | 1 | Unknown or not met | 0 |

The importance and verdict columns are separate lookup tables: every criterion
uses one importance weight and one verdict credit.

```text
raw score = round(100 × Σ(weight × credit) / Σ(weight))
```

For example, one mandatory criterion met and one preferred criterion partial
produce `100 × (2×1 + 1×0.5) / 3 ≈ 83`. That number alone is insufficient for a
strong recommendation; the category and experience rules still apply.

- An evidenced mandatory mismatch excludes the job and caps the score at 39.
- The requirement rubric allows strong match only with mandatory criteria present
   and all met, no unclear importance, verified job evidence and score at least 80.
- Otherwise, the rubric keeps the job for review and caps the score at 79.
- No usable verified job evidence produces no score.
- Additional professional-experience and seniority guards can exclude a job or
   require review. A strong result also needs experience alignment to be met.

A separate mandatory-years field cannot turn a preferred requirement into a hard
prerequisite. If `minimum_professional_years` is supplied, its evidence must be
supported by a shared `must_have` quote. Otherwise the model must correct its
claim; when there is no explicit supported minimum, it must use null and empty
evidence. The application does not bypass that guard simply to make a retry pass.

These are explicit policy rules, not calibrated hiring probabilities. Passing
software tests does not establish matching accuracy on human-labeled cases.

Source: [evidence.py](../backend/evaluation/evidence.py),
[candidate_fit.py](../backend/evaluation/candidate_fit.py),
[requirements.py](../backend/evaluation/requirements.py).

## 10. Combine results and update the interface

The orchestrator merges completed provider results into the pending job row.
Combination is allowed only when completed assessments use compatible requirement
lists. An old assessment and a new-list assessment must not silently produce a
misleading shared score.

- A **final score** requires three completed, comparable assessments with numeric
   scores, and is their rounded average.
- At least two available comparable scores may produce a **provisional average**
   while the full set is incomplete. It is labeled as provisional.
- A final category requires all three completed assessments to agree. Otherwise,
   the combined category is **For review**.
- Completion counts and agreement counts are shown separately. Agreement does not
   measure confidence or establish correctness.

The frontend uses **server-sent events (SSE)** for progress and snapshot polling as
a recovery path. SSE is a one-way stream from server to browser. Polling means the
browser periodically asks for the latest complete state; it repairs missed events
or a disconnected stream. Reading or refreshing a snapshot does not rerun failed
model calls.

Source: [orchestration.py](../backend/evaluation/orchestration.py),
[pipeline.ts](../frontend/src/stores/pipeline.ts).

## 11. Failures, retries and cancellation

| Failure | What happens | Recovery |
| --- | --- | --- |
| Invalid PDF or failed classification | No workspace PDF is created | Correct the upload or resolve provider failure |
| A board fails | Other sources can continue; source error is retained | Retry scraping |
| Extraction schema or source range is invalid | One correction retry; persistent failure blocks posting assessments | Retry failed evaluations |
| Shared IDs, fields or mandatory evidence are inconsistent | One correction retry for that assessment | Retry failed provider/job |
| Provider rate limit | Pacing/backoff and provider policy apply | Retry after quota/cooldown permits |
| Permanent quota, credentials or model access failure | Affected provider submissions stop/skip under its policy | Fix configuration or quota before retrying |
| Cancel requested | Later work and late persistence are blocked | Existing completed results remain available |

There are separate retry layers: an SDK may retry transport failures, the
application retries invalid output once, and a user can explicitly retry saved
failures. One logical extraction or evaluation is therefore not necessarily one
HTTP request. Cancellation cannot instantly interrupt an already-running remote
request.

Safe validation errors identify schema-defined nested fields, array indices and
controlled error descriptions. They exclude returned values and arbitrary extra
keys. Retry prompts receive that feedback so they can correct the response.
Retries preserve successes, reuse valid frozen requirements and do not switch
providers silently.

If an old error still appears after a code fix, restarting loads the new backend
code but does not erase historical errors. Use the failed-evaluation action to
actually recompute failed work. Do not delete saved data or all caches as a routine
repair step.

Source: [runtime.py](../backend/evaluation/runtime.py),
[structured_output.py](../backend/evaluation/structured_output.py),
[evaluation/service.py](../backend/evaluation/service.py),
[runs.py](../backend/runs.py).

## 12. Storage and cache boundaries

Persistence occurs throughout the workflow. The final save box in the diagram
represents user actions and revisiting work, not a claim that nothing was saved
earlier.

| Location | Contents and purpose | Reuse / lifecycle |
| --- | --- | --- |
| `frontend/runs/<id>/` | Run snapshots, resume/context, assessment journal, failed-job checkpoints, exports and search-specific artifacts | Existing seven-day run retention; cancellation/deletion respects active workers |
| `data/profiles/` | Saved profile metadata and separately stored resume/context | Managed separately from temporary run expiry |
| Run or saved-profile `evaluations/` | Private structured assessments with candidate evidence | Seven days; bounded to 1,000 entries per owner |
| `.cache/job_requirements/` | Validated public posting requirements; no candidate context | Seven days; at most 1,000 entries |
| `.cache/job_collections/` | Collected public postings keyed by search parameters | Default 15 minutes; bounded cache |
| `.cache/job_descriptions/`, `.cache/linkedin_descriptions/` | Reusable public posting descriptions | Provider-specific description-cache policy |
| `.cache/job_index/` | Shared versioned public posting vectors | Shared index maintenance policy; per-search eligibility scopes |
| `.cache/job_embeddings/` | Content-addressed public text vectors | Default 30-day vector reuse; candidate query vectors are not cached here |
| Browser localStorage | Job-action flags such as Save/Dismiss/Applied | Browser-local persistence; saved-profile actions also integrate with server storage |

Requirement-cache identity includes posting content, extraction model, prompt,
schema and policy version. Private assessment identity additionally includes
candidate context/profile, roles, provider/model and assessment policy/settings.
Changing relevant inputs creates a different key. Failed or cancelled assessments
are not cached as successes. Cache hits are rechecked by current validation paths.

Saved-profile deletion and temporary-run deletion have separate responsibilities.
The application currently has no user accounts or account isolation: saved
profiles are server-wide and run URLs should be treated as private.

Source: [paths.py](../backend/paths.py), [cache.py](../backend/evaluation/cache.py),
[storage.py](../backend/profiles/storage.py), [runs.py](../backend/runs.py),
[shared index guide](shared-job-index.md).

## 13. Main HTTP interactions

The table lists current web routes, not every compatibility alias. `run_id` is the
workspace identifier used to read state, follow progress or retry work.

| Method and path | Purpose |
| --- | --- |
| `POST /api/resumes/upload` | Upload, classify and extract a resume; create workspace on success |
| `PUT /api/searches/{run_id}/confirm-profile` | Confirm profile/preferences and start searching |
| `GET /api/searches/{run_id}` | Read the authoritative snapshot; does not start work |
| `GET /api/searches/{run_id}/progress` | Stream progress events |
| `POST /api/searches/{run_id}/find-jobs` | Start collection/evaluation from supported form inputs |
| `POST /api/searches/{run_id}/find-more` | Append newly found jobs using revised preferences |
| `POST /api/searches/{run_id}/retry-scraping` | Retry failed board sources |
| `POST /api/searches/{run_id}/retry-evaluations` | Retry failed provider/job checkpoints |
| `POST /api/searches/{run_id}/cancel` | Request cancellation |
| `GET /api/searches/{run_id}/exports/{file_name}` | Download an allowed export |
| `GET/PUT /api/searches/{run_id}/actions` | Read/update flags and optional dismissal feedback |
| `DELETE /api/searches/{run_id}` | Delete a run, deferring removal while active |
| `GET/POST /api/profiles` | List/save profiles |
| `PUT/DELETE /api/profiles/{profile_id}` | Update/delete a saved profile |
| `POST /api/profiles/{profile_id}/searches` | Reopen linked workspace; `fresh=true` creates a new one without automatically searching |

FastAPI's `/docs` and the generated OpenAPI file describe the exact request and
response fields. Python schema models are authoritative; generated frontend types
are regenerated from them rather than manually edited. Historical `/api/runs`
aliases remain for supported compatibility paths.

Source: [routers](../backend/routers/),
[OpenAPI export](../frontend/openapi.json).

## 14. Find more jobs, export and revisit

**Find more jobs** is a loop back to collection. It forces fresh collection,
filters previously seen postings and adds the new shortlist to the same workspace.
The selected shortlist size applies to the **new batch**, not the total combined
results. Existing assessments and job-action flags remain.

Once a workspace contains assessments, confirming a changed candidate profile is
rejected with HTTP 409; create a new search for a changed profile so existing
assessments are not silently mixed with a different candidate context.

Exports provide data for manual review. Save, Dismiss and Applied track user
choices; Applied is a tracking flag, not proof that the application submitted
anything. Deleting/expiring a temporary run does not automatically delete its
independently saved profile.

## 15. Observability, verification and limits

Optional LangSmith tracing records stage timing, counts and safe failure
categories. It is designed not to export resume or posting text. See
[tracing setup](langsmith-tracing.md) for the exact configuration and coverage.

For application changes, `./scripts/check.sh` runs Python regressions, contract
generation, frontend tests, type checking and a production build. Add `--e2e` for
affected browser workflows. Mocked providers verify software behavior, not live
availability or human matching accuracy.

For this documentation task, the flowchart is checked in a real headless browser
for rendering, controls, keyboard node selection and mobile scrolling. Local
source links are checked. The animation uses no real candidate or posting data
and makes no provider requests.

Remaining limits include unverified vacancy availability, incomplete or ambiguous
job descriptions, potentially missed retrieval matches and model interpretation
errors. Shared extraction makes criteria consistent across providers, but also
shares any extraction mistake. Human-labeled evaluation remains necessary to
measure relevance, missed matches and strong-match precision.
