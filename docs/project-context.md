# Career Tracker — Current Project Context

Updated: 28 October 2026 (Australia/Sydney); seniority rule uses stated years for mid-level profiles.

This document describes the implemented application.
The product is displayed as **Career Signal**; the repository is **Career Tracker**.

## Purpose and scope

Candidates upload a PDF resume, review the extracted profile, search selected job
boards, rank postings against their background, and compare independent model
assessments. Saved resume workspaces allow candidates to reuse their PDF and
profile or return to existing search results.

The application does not automatically apply to jobs, generate resumes or cover
letters, verify that postings remain live, or provide user accounts. Saved resume
management is implemented; account isolation is not. Anyone with access to the
application server can access its saved resumes, and run URLs expose run data.

## Architecture and startup

- Frontend: Vue 3 Composition API, TypeScript, Vue Router, Pinia, Tailwind CSS,
  Heroicons, and Vite.
- Backend: FastAPI, Pydantic contracts, background Python worker threads, and
  persisted JSON state. Use one Uvicorn worker because active-run coordination is
  process-local.
- Resume extraction: PDF text extraction with local OCR support for scanned pages,
  followed by structured model extraction. Tesseract must be installed for OCR.
- Collection: JobSpy for LinkedIn, Indeed, and Glassdoor; the existing Apify SEEK
  actor for SEEK. An optional Adzuna provider remains configurable.
- Matching: OpenAI embeddings, local Chroma, BM25, and reciprocal rank fusion.
- Evaluation: LangChain provider adapters for Anthropic Claude, OpenAI GPT, and
  Google Gemini. Model IDs come from backend configuration.
- Tests: Python unittest, Vitest/Vue Test Utils, and Playwright with MSW fixtures
  and accessibility checks. Mocked tests do not establish live provider availability.

`./run_app.sh` starts FastAPI at `http://127.0.0.1:5000` and Vite at
`http://localhost:5173/` without opening a browser tab. Open that URL manually. Set `PYTHON_BIN` when the
required dependencies are installed in a specific environment. Ctrl+C stops the
launcher’s services. Restart after backend changes. Swagger is at
`http://127.0.0.1:5000/docs`.

## Browser routes

| Route | Purpose |
| --- | --- |
| `/` | Upload a PDF, continue with a saved resume, or return to the prior run |
| `/profiles` | Saved resume management |
| `/run/:runId` | Extraction, editable profile review, and search progress |
| `/run/:runId/results` | Unified job results |
| `/run/:runId/job?job=<jobKey>` | Job details and model evidence |
| `/privacy` | Processing, retention, and access information |
| `/eval` | Isolated retrieval and job-fit generation experiments |

Job details use a `section` query parameter for Overview, Job description, and
Evaluation evidence. The selected tab survives refresh. Unknown routes return to
`/`. Startup opens the home URL; this does not force existing deep links home.

## User workflow

### 1. Upload or continue

New uploads accept PDF resumes with backend validation, including a 5 MB size
limit and a 20-page limit. The user selects a resume-extraction provider; this is
separate from job evaluation, which always uses all three evaluation providers.

Extraction produces a structured profile and a text representation. Missing
profile information remains editable rather than being presented as established
fact. The pipeline pauses at profile review before searching job boards.

The home page also links to Saved resumes. Successful search completion automatically
saves the profile, preferences, and available PDF, including when no jobs match.
An upload alone does not create a permanent workspace. Manual saving is also available.
A continued saved profile is updated rather than duplicated; saving failures leave
results available and show a retry message.

### 2. Review the profile and choose search inputs

Users can edit their name, summary, skills, experience, career level, work history,
and education. They choose target roles, locations, boards, posting age, work
arrangement, seniority, excluded title/company terms, and semantic shortlist size.

- At least one target role and one job board are required.
- Empty locations normalize to Worldwide; a location is not mandatory.
- Location autocomplete begins at two characters and waits **500 milliseconds
  after typing stops**. New input cancels superseded requests.
- Suggestions come from the backend’s Photon integration. Keyboard arrows and
  Enter or mouse selection are supported; custom locations still work if the
  provider fails. Commas within a location do not split it into separate chips.
- Seniority defaults to automatic early-career preference: clearly experienced-level
  titles are ranked after other titles for graduate/entry/junior profiles. For a
  profile that is early-career only by years, senior titles are ranked later only
  when the posting states more years than the profile, or the title is executive. They remain
  in the pool and can fill remaining shortlist slots. Explicit levels override this
  preference; saved `any` choices remain All levels. Unknown experience stays broad.
- Shortlist choices are 15, 50, 100, or all retrieved jobs (`top_k=0`).
- Confirming saves edits and starts collection. Merely fetching a status snapshot
  or choosing a location suggestion does not start a search.

### 3. Collect and filter postings

The confirmed target-role queries drive board searches. Resume experience does
not replace the requested role, allowing users to explore career changes.

JobSpy collects general-board postings and requests descriptions. SEEK retains
its `saswave/seek-scraper` actor and existing URL/proxy configuration. Source
records are normalized, duplicates removed, and requested constraints applied
before matching. Partial board failures are reported while other work continues.

Indeed and Glassdoor each share one `n_result` budget across queries, locations,
and country indexes; its default is **50 jobs per board**. Requests use the
remaining budget and stop when it is filled. Duplicates and records removed by
location/date filtering do not consume that budget. Title/company exclusions,
work-arrangement, and seniority filters run afterward and can reduce the pool
without fetching replacements. This is not a universal 50-job limit across all boards.

The user's **15, 50, 100, or all** choice controls the later ranked shortlist,
not this per-board collection limit. After collection and filtering, matching
selects up to the chosen number of jobs across the combined pool for evaluation.
Choosing all (`top_k=0`) retains all retrieved jobs; choosing 100 does not guarantee
100 results when fewer jobs remain available.

Worldwide Indeed/Glassdoor searches visit supported country indexes until the
budget is exhausted. They do not guarantee coverage of every country. SEEK’s
worldwide behavior remains tied to its existing source.

Missing descriptions are a source-data limitation. The UI explains that reliable
requirement and gap assessment may not be possible without them.

### 4. Embed and rank matches

1. Prepare job text for embedding, preserving full posting text in metadata.
2. Embed job text with OpenAI `text-embedding-3-small` and store documents in the
   search’s local Chroma database. A shared job-embedding cache can avoid repeat
   embedding requests.
3. Construct queries from target roles, skills, and recent work history.
4. Embed those queries for semantic retrieval and also run BM25 over job text.
5. Combine rankings with reciprocal rank fusion and select up to the user's
   chosen 15, 50, or 100 jobs, or all retrieved jobs when `top_k=0`.
6. Restore full available posting text for evaluation.

The profile is persisted as JSON/text, **not as a separate persistent web-profile
vector collection**. Query embeddings are transient. BM25 operates on words, not
vectors. Retrieval selects jobs; the model then evaluates each selected posting.

LangChain provides document, embedding, vector-store, prompt, and model adapters.
The RAG pattern here means retrieving relevant jobs and supplying their text plus
the profile to an evaluation prompt. It does not train or fine-tune a model.

### 5. Evaluate shortlisted jobs

Every shortlisted job is evaluated independently by Claude, GPT, and Gemini.
The user no longer selects one evaluation model. Provider execution currently
runs **Claude, GPT, and Gemini concurrently**. Within each provider, job requests
remain subject to configured worker counts, pacing, and retries. The full ranked
shortlist is published with pending assessments before provider requests begin,
so postings can be inspected while model results arrive.

Each assessment contains its own score, fit category, rationale, missing skills,
requirement verdicts, supporting posting/resume quotes, and evidence-verification
flags. Model rows distinguish pending, complete, and failed states.

- Requirement verdicts: met, partially met, not met, or unknown.
- Overall score: average only when all three completed assessments have scores.
- Overall category: use the shared category when all three completed assessments
  agree; otherwise use For review.
- Failed assessments can be retried independently, preserving successful results.
- Updates become available progressively as model assessments settle.

### 6. Explore results

Recommended and non-recommended jobs share one results collection in the UI.
Non-recommended entries are labeled rather than placed in a separate tab. Backend
recommendation/exclusion arrays remain separate for compatibility.

The dashboard supports cards and table views, filters, sorting, and browser-local
Save, Dismiss, and Applied flags. Best match is the default sort: scored strong
matches, review jobs, and not-recommended jobs, with descending scores within
each category; unscored jobs appear last. Numeric score, date, and company sorting
remain available. Source links open the original application page.
Posting dates are explicitly labeled; availability is unverified.

Clicking a job opens a dedicated expanded details page with:

- Job title/company and labeled location, arrangement, salary, and posting date.
- Individual Save, Dismiss, Applied, and Copy link icons.
- Keyboard-accessible Overview, Job description, and Evaluation evidence tabs.
- Readable posting headings, paragraphs, lists, bold text, and safe HTTP(S) links.
  Source HTML is not executed. Section spacing and restrained line width improve
  readability without an extra centered padded description container.
- Per-model comparison and assessment summaries.
- A requirement carousel with Previous/Next controls, arrow-key navigation, and
  an item counter. Each slide compares posting evidence with resume evidence.

**Find more jobs** opens a prefilled search-preferences editor from results.
Keep the same roles or change roles, locations, boards, and other filters, then
choose **Search for more jobs**. **Back to results** returns without starting
work. Additional searches use the same run and confirmed profile; existing jobs,
assessments, and saved-profile Save/Dismiss/Applied flags are retained. Existing
assessments are not recomputed for new role preferences. To change the candidate
profile itself after results exist, start a new search from the saved resume
(or upload a different resume). Existing assessments stay tied to their original
profile.

Previously shortlisted postings, including pending, failed, and excluded jobs,
are skipped before indexing and evaluation. Previously collected postings that
were never shortlisted remain eligible, so another search can consider more of
the original pool. A search with no new eligible jobs keeps existing results and
reports that outcome. Results remain accessible while additional work proceeds.

The timeline allows profile/results navigation when the run is not active.
Once results exist, returning to the profile/search step opens the same
preferences-only additional-search editor. The shortlist size applies to each
new batch, not the accumulated results: 50 jobs followed by a 15-job request
keeps the original jobs and adds up to 15 new eligible jobs.
The Upload new resume action in the run view appears at the completed results
stage. Navigating away does not itself delete the existing search.

## Saved resume management and continuation

The Saved resumes page offers editing/renaming, PDF download, deletion, Continue,
and Start a new search. Compact cards use the candidate’s name as the heading,
Last updated at the top right, a PDF-status badge, summary, experience, location,
target roles, and skill tags. There is no avatar/headline block or Resume workspace
label. The header does not show a Saved resumes link beside the theme toggle;
management remains accessible from home and the save section.

New saves made from a run include the original PDF, edited profile, preferences,
and profile context. Older profile-only entries remain usable and are labeled as
having no original PDF. A missing source PDF cannot be reconstructed from JSON.

**Continue** returns an existing linked search when available, preserving its
recommendations, exclusions, evaluations, and progress. It considers the original
`source_run_id` and searches linked by `saved_profile_id`, prefers searches that
have progressed beyond profile review, then selects the most recently created.
If no linked run remains, it creates a fresh profile-review workspace and restores
the PDF when available.

**Start a new search** explicitly creates a new review workspace using the saved
profile and preferences. Editing a saved profile does not overwrite old search
results; use a new search to apply the revised profile. The app does not rerun
extraction or evaluation merely because a saved resume or result is opened.

## API request sequence

Canonical endpoints appear in Swagger. Older `/api/runs` routes remain hidden
compatibility aliases.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/config` | Runtime UI configuration |
| GET | `/api/models/resume` | Extraction-provider options and model IDs |
| GET | `/api/models/evaluation` | Automatic evaluation providers and model IDs |
| GET | `/api/locations/suggest?q=...` | Location suggestions |
| POST | `/api/searches` | Upload PDF and start extraction |
| PUT | `/api/searches/{run_id}/confirm-profile` | Save profile/preferences and start searching |
| POST | `/api/searches/{run_id}/find-jobs` | Explicit search-start endpoint |
| POST | `/api/searches/{run_id}/find-more` | Append new jobs using supplied search preferences |
| GET | `/api/searches/{run_id}` | Current snapshot |
| GET | `/api/searches/{run_id}/progress` | Server-Sent Events stream |
| POST | `/api/searches/{run_id}/cancel` | Cancel further work |
| POST | `/api/searches/{run_id}/retry-evaluations` | Retry failed model assessments |
| DELETE | `/api/searches/{run_id}` | Delete temporary search and derived files |
| GET | `/api/searches/{run_id}/exports/{file_name}` | CSV or Excel download |
| GET / POST | `/api/profiles` | List or save resume workspaces |
| PUT / DELETE | `/api/profiles/{profile_id}` | Edit or delete a saved workspace |
| GET | `/api/profiles/{profile_id}/resume` | Download saved original PDF |
| POST | `/api/profiles/{profile_id}/searches` | Continue linked search or create review workspace |
| POST | `/api/profiles/{profile_id}/searches?fresh=true` | Explicitly start a new search |

The frontend normally sends confirm-profile once; that handler invokes the
search-start function internally, rather than requiring a second browser POST.
With existing results, confirm-profile appends when the validated profile is
unchanged and returns 409 if the profile changed; use a fresh search for a new
profile. The legacy form search endpoint also appends when results exist.
The worker calls boards, embeddings, and evaluation providers in the background.

The frontend maintains SSE plus snapshot polling while a worker is active.
Normal polling is approximately every 1.5 seconds, with backoff on errors. Repeated
GETs only read state; they do not re-evaluate jobs. Different client ports in
Uvicorn access logs identify browser connections, not different API servers.

Snapshot polling stops when work is complete/inactive. Failed model requests,
partial scraping, cancellation, missing jobs, and reconnecting have explicit UI
states. Cancellation preserves completed work; deletion blocks further updates.
If a worker is active, DELETE returns `deletion_pending: true` without waiting
for it to finish; run files are removed when that worker exits.

## Persistence and retention

| Location | Contents | Lifetime |
| --- | --- | --- |
| `frontend/runs/<run_id>/state.json` | Profile, preferences, progress, recommendations, evaluations | Seven-day run retention |
| `frontend/runs/<run_id>/shortlisted_jobs.json` | Previously shortlisted posting identities used to deduplicate additional searches | Same as run |
| `frontend/runs/<run_id>/resume.pdf` | Uploaded or restored PDF | Same as run |
| `frontend/runs/<run_id>/resume_context.txt` | Profile text used for matching/evaluation | Same as run |
| `frontend/runs/<run_id>/vector_db_search_*/` | Chroma job documents and vectors | Same as run |
| `frontend/runs/<run_id>/retrieved_jobs.csv` | Retrieved job export | Same as run |
| `frontend/runs/<run_id>/relevant_jobs.xlsx` | Recommended-job export | Same as run |
| `frontend/runs/<run_id>/failed_jobs.json` | Failed evaluation retry checkpoints | Same as run |
| `frontend/runs/<run_id>/job_assessments.jsonl` | Assessment log appended during evaluations and retries | Same as run |
| `data/profiles/<profile_id>.json` | Saved profile, preferences, name, timestamps, source link, job-action flags | Until explicitly deleted |
| `data/profiles/<profile_id>/resume.pdf` | Saved original PDF, when available | Until saved workspace is deleted |
| `data/profiles/<profile_id>/resume_context.txt` | Saved profile context | Same as saved workspace |
| `.cache/job_embeddings/` | Reusable job embeddings | Default 30-day reuse TTL; no proactive purge by the cache class |
| Browser localStorage | Local action copies and pending synchronization edits | Until browser storage is cleared; server copies remain |
| Owner workspace `evaluations/` | Private structured assessments | Seven-day reuse TTL, 1,000 entries per owner; cleanup on writes or owner deletion |

Run retention is measured from creation, not last access. Expiry is checked on
API requests and when persisted runs are loaded at server startup; there is no
scheduled run-cleanup worker. Expired embedding-cache entries are recomputed when
requested, rather than proactively deleted when their reuse TTL expires.

Run cleanup removes search results, even if the associated resume is permanently
saved. Deleting a saved resume does not delete previously created searches; deleting
a run does not delete its separately saved resume. A temporary-data cleanup must
preserve application code and saved resume storage unless explicitly asked otherwise.

Excel has a 32,767-character cell limit. Long export values are split into
continuation columns rather than silently truncated. Structured values are
serialized for export; the application retains the original structured results.

## Key code ownership

| File/module | Responsibility |
| --- | --- |
| `backend/app.py` | FastAPI assembly, middleware, and frontend asset mounting |
| `backend/routers/` | HTTP route declarations delegating to feature handlers |
| `backend/runs.py`, `backend/runs_api.py` | Shared run state and lifecycle; status, progress, cancellation, and exports |
| `backend/profiles/upload.py`, `backend/profiles/service.py` | Resume upload/extraction and saved-profile continuation/autosaving |
| `backend/search/service.py` | Search confirmation, execution, and find-more handling |
| `backend/evaluation/service.py` | Assessment updates and targeted evaluation retries |
| `backend/profiles/storage.py` | Saved resume JSON/PDF persistence and management APIs |
| `backend/schemas/contracts.py` | Public request/response schemas |
| `backend/profiles/extraction.py` | PDF/OCR and structured profile extraction |
| `backend/search/collection.py` | Board collection, normalization, filtering, and indexing |
| `backend/search/retrieval.py`, `backend/search/ranking.py` | Retrieval and rank fusion |
| `backend/evaluation/providers.py` | Provider-specific candidate-fit assessments |
| `backend/evaluation/orchestration.py` | Three-model orchestration, merging, and overall verdict |
| `backend/evaluation/evidence.py` | Requirement evidence and scoring |
| `backend/evaluation/runtime.py` | Provider pacing, retries, and failure classification |
| `backend/exports.py` | Excel-safe exports |
| `frontend/src/stores/pipeline.ts` | API calls, snapshot polling, and SSE |
| `frontend/src/stores/profile.ts` | Editable profile/preferences draft |
| `frontend/src/stores/jobs.ts` | Browser-local job action flags |
| `frontend/src/views/ProfilesView.vue` | Saved resume cards and management |
| `frontend/src/components/LocationInput.vue` | Debounced location lookup |
| `frontend/src/views/JobDetailView.vue` | Detail tabs and expanded job information |
| `frontend/src/components/EvaluationEvidence.vue` | Model comparison and requirement carousel |

The previous flat backend modules remain compatibility imports; new domain code
uses `backend.profiles.*`, `backend.search.*`, and `backend.evaluation.*`. API
handler names and OpenAPI operation IDs describe searches and their actions;
public URLs and hidden legacy aliases retain their existing contracts.

OpenAPI exports and generated TypeScript types must stay synchronized with the
backend schemas. `scripts/check.sh` runs the core checks; `--e2e` adds browser
workflows. The OpenAPI export is `frontend/openapi.json`, regenerated by `scripts/check.sh`.

## Performance status and boundaries

Implemented: bounded board requests, Indeed/Glassdoor shared collection limits,
embedding caching, hybrid shortlisting, concurrent provider batches, per-provider
job concurrency, early pending-shortlist visibility, progress updates, and targeted
evaluation retries. Provider quotas still bound throughput; concurrency does not
reduce the number of assessments or establish a measured live speedup.

Each provider now processes successive waves of 15; a provider does not wait for
other providers to advance. Successful structured assessments are cached privately
for seven days (1,000 entries per owner) using profile/posting/model/prompt/schema
identity. Current evidence and experience checks rerun on hits. New or changed jobs
still require three independent assessments plus potential retries. Uploads use one
combined OpenAI classification/profile request before allocating a workspace.
Saved-profile job actions now persist across runs, with local offline retry. See
[the review follow-up](review-follow-up.md) for contracts, filtering, weighting,
partial agreement, storage and measurement limitations.

## Decisions

- 17 October 2026: At the owner’s request, address supported review findings across
  upload, collection, retrieval, evaluation and saved actions. Preserve unknown
  evidence and independent models; no human-labeled accuracy claim.

- 14 October 2026: Removed the 14 import-only compatibility modules at the user’s
  request. Use canonical `backend.schemas`, `backend.profiles`, `backend.search`,
  and `backend.evaluation` imports; earlier notes preserving those wrapper files
  are superseded. Executable launchers and package markers remain.

- 14 October 2026: Validation models moved to `backend/schemas/` with separate
  contracts, resume, saved-profile and evaluation modules. Old imports remain
  compatibility exports; API fields and validation behavior are unchanged.

- 13 October 2026: HTTP declarations now live in `backend/routers/`, grouped by
  feature. Injected router handlers delegate to the existing application and
  profile-storage functions; URLs, schemas and legacy aliases are unchanged.

- 13 October 2026: Resume upload now waits for extraction before returning HTTP 201.
  No detached extraction thread is launched; blocking work is awaited in the managed
  thread pool. Job collection and evaluation retain their background lifecycle.

- 10 October 2026: Resume uploads use `POST /api/resumes/upload` with the API label
  **Upload resume**. Original upload URLs remain hidden compatibility aliases.
  Black and Prettier standardize maintained source formatting without moving files.

- 7 October 2026 — At the owner's request, corrected the documented assessment
  log, browser flag removal, embedding-cache TTL, run-expiry triggers, and deferred
  deletion response to match the code review. Left the collection-budget wording
  unchanged as requested. No application behavior changed.
- 7 October 2026 — At the owner's follow-up request, verified the shortlist
  selection against the code and clarified how 15/50/100/all differs from the
  per-board collection limit. Qualified which filters run before and after that
  limit. The earlier collection-budget wording is superseded; application
  behavior is unchanged.

- 7 October 2026 — At the owner's request to reduce evaluation waiting, run the
  three provider batches concurrently and publish pending shortlist entries early.
  Preserve scoring, per-provider limits, and targeted retries; validate with mocked
  concurrency and lifecycle checks rather than live provider calls.

- 7 October 2026 — At the owner's request, grouped backend code into profiles,
  search, and evaluation domains and made API handler/operation names readable.
  Preserve compatibility imports, public and legacy URLs, saved data, scoring,
  and evaluation concurrency; limit the work to organization and naming.

- 7 October 2026 — At the owner's request, save profiles automatically on successful
  search completion and prioritize early-career-compatible titles in automatic
  seniority mode, preserving explicit level choices and broad candidate pools.

- 7 October 2026 — Added Best match as the default card/table sort at the owner's
  request, preserving separate numeric score, date, and company options.

- 8 October 2026 — At the owner's request, added Find more jobs within an
  existing search, with editable role/search preferences, retained results and
  browser actions, and deduplication of previously shortlisted postings. The
  confirmed profile and previous assessments are preserved; fresh saved-profile
  searches remain a separate workflow.

- 8 October 2026 — At the owner's regression report (50 jobs followed by 15),
  made repeat-search navigation and compatibility API paths append consistently.
  Retain prior results; reject changed profiles in a search with assessments
  instead of replacing its history. No scoring rules changed.

- 28 October 2026 — At the owner's request, moved this document to
  `docs/project-context.md` and the PRD to `docs/PRD.md`, and removed the
  superseded Reverse-RAG frontend drafts. No application behavior changed.

## Dismissal preferences — 26 October 2026

The user requested learning from dismissed jobs and chose lower ranking rather
than exclusion. Optional dismissal reasons now persist with the workspace/saved
profile and reorder future shortlists before top-K. They do not change fit scoring,
train providers, or alter canonical requirement evidence. Restoration or removing
a preference reverses its future effect. Existing dismissals without reasons do
not acquire inferred preferences. See [behavior and limits](dismissal-preferences.md).

## Evaluation experiments — 27 October 2026

At the owner’s request, `/eval` compares selected embedding models and the configured
Claude/GPT/Gemini job-fit assessments using existing workspace datasets. Human labels
are optional; partial-label metrics remain explicitly observed. Experiments do not
change production ranking or saved results. A separate in-memory worker supports
polling and cancellation, with 24-hour/latest-20 result retention and JSON export.
See the [experiment guide](evaluation-experiments.md) for exact scope and limitations.

## Human review datasets — 28 October 2026

At the owner’s request, existing workspace data can be frozen for human review of
fit, shared requirement extraction, and semantic evidence support. The /eval page
links to /eval/datasets/:id. Private snapshots and separate labels persist under
data/evaluation_datasets until deleted from the Experiments page, independently of
workspace expiry. Reviews marked AI-assisted are kept but excluded from all metrics.
Metrics require reviewed labels; legacy criteria remain distinguished from shared
extraction. Production scoring is unchanged. See the
[human evaluation guide](human-evaluation-datasets.md).


## Guided dataset review — 28 October 2026

At the user's request, dataset review now starts with plain-language instructions,
an expanded candidate profile and worked examples for fit decisions. Users can
save fit-only reviews and optionally check job requirements or model evidence in
separate views. Switching these views preserves draft answers. Metrics are
expandable; a save bar displays unsaved status. Label contracts, existing saved
judgments and production scoring are unchanged.

## Quick labeling — 28 October 2026

At the user's request, /eval now explains the evaluation steps in plain language,
puts review datasets first and moves the model comparison into a collapsed
Advanced section. Review datasets open in Quick labeling: one job at a time in a
fixed random order, three answers with 1/2/3 shortcuts, autosave, a 30-label
target and a plain-language results summary. Shortlist membership is hidden while
labeling. Detailed review remains available via ?mode=detailed. Frontend only;
label contracts and production scoring are unchanged.
