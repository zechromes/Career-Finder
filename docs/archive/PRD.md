# Product Requirements Document — Career Signal

**Repository:** Career Tracker  
**Updated:** 28 October 2026 (Australia/Sydney)  
**Scope:** Current agreed product requirements and release acceptance criteria

## 1. Product purpose

Career Signal helps candidates discover relevant jobs and assess their suitability
using their own resume evidence. Candidates upload a resume, verify the extracted
profile, select search preferences, retrieve a shortlist and review independent
model assessments. Saved workspaces support returning to results and tracking
application decisions without repeatedly uploading a resume.

This document defines required behavior. Acceptance criteria are verification
conditions, not claims that live job-board availability or matching accuracy has
already been established.

## 2. User problem and intended users

Job seekers face fragmented job sources, duplicate postings, inconsistent location
labels and lengthy descriptions. Keyword searches alone can miss transferable
skills, while unsupported fit scores can hide important experience gaps.

Primary users are candidates comparing their background against available roles,
including students, early-career applicants and career changers. An operator also
needs to understand pipeline failures without exposing private candidate data in
debugging systems, and to measure matching quality against human judgments.
Request-cost accounting is a separate product decision (section 11).

## 3. Product goals

- Reduce repeated resume entry and manual review of duplicate job postings.
- Let candidates express role and location preferences in familiar language.
- Explain suitability through job requirements and documented candidate evidence.
- Preserve useful results when a source, model or network request fails.
- Make progress, retries, uncertainty and collection limits understandable.
- Support repeat searches and saved application decisions without losing history.
- Provide optional, structured operational tracing for troubleshooting.

## 4. Scope boundaries

### Included

Resume intake and extraction; editable profile review; saved resume management;
multi-source job discovery; filtering and deduplication; hybrid retrieval;
independent candidate-fit evaluations; results and job details; application flags;
exports; incremental searches; targeted retries; cancellation; cache reuse;
operational tracing; dismissal-based shortlist preferences; a pipeline playground
for running the upload, ingestion and retrieval stages on their own; a per-job
tailored resume rewritten only from the uploaded resume's facts; a labeled dataset
built from Applied and Dismiss actions.

### Future Development

Automatic job applications; cover-letter generation; guarantees that
postings remain open; exhaustive collection of every matching vacancy; guaranteed
employment outcomes; user accounts, tenant isolation and production authorization;
new agent hosting or deployment through LangSmith Studio.

Greenhouse and Lever are not selectable collection sources. Apify is not required
for the current SEEK option. PostgreSQL is not a prerequisite for the supported
application workflow.

## 5. Primary user journey

1. Open the application at the home page or continue a saved workspace.
2. Upload a PDF and receive clear validation or extraction feedback.
3. Review and correct the extracted candidate profile.
4. Select target roles, generalized locations, boards and search filters.
5. Start job collection and observe progress with explanatory status text.
6. Review shortlisted jobs as independent assessments become available.
7. Inspect requirements, evidence, gaps and model disagreements.
8. Save, dismiss or mark a job as applied; export results when needed.
9. Find additional jobs or retry failed work without losing completed results.

## 6. Functional requirements

Priority **P0** denotes a core workflow or correctness requirement. **P1** denotes
a supporting usability or operational requirement within the agreed scope.

### FR-01 — Resume intake and extraction · P0

- Accept PDF uploads through file selection and drag-and-drop.
- Enforce the supported 5 MB and 20-page limits, rejecting invalid, encrypted,
   unreadable or unsupported files with an actionable message.
- Support local text extraction and OCR for scanned PDFs when OCR dependencies
   are installed.
- Classify whether the document is a resume/CV during upload, before allocating
   a run identifier or storing the uploaded PDF.
- Use OpenAI for profile extraction only; show “Powered by OpenAI” and provide no
   extraction-model dropdown.
- Combine resume classification and structured profile extraction in the normal
   upload request. Provider-level retries may still result in additional calls.
- Reject unrelated or uncertain documents without creating a saved upload or run.
   Distinguish document rejection from provider or structured-response failures.
- Extract the profile once and reuse its confirmed context for job evaluation.
   Do not reopen or reclassify the PDF for every job.

**Acceptance:** A valid upload reaches profile review. A non-resume creates no
workspace or saved PDF. Repeated evaluations use stored profile context. Provider
failure is displayed as a failure rather than a fabricated profile.

### FR-02 — Profile review and search preferences · P0

- Allow candidates to review and correct extracted information before searching.
- Support target roles, generalized locations, selected boards, posting age,
   work arrangement, seniority, exclusions and semantic shortlist size.
- Normalize provider-specific location formats internally. Do not require users
   to supply board-specific location identifiers or administrative hierarchies.
- Treat empty locations as worldwide, subject to provider and collection limits.
- Offer shortlist sizes of 15, 50, 100 or all retrieved eligible jobs; default to 50.
- Present the automatic evaluation-model comparison card below the other search
   preferences. Evaluation uses the configured Claude, GPT and Gemini providers.
- Preserve explicit user selections when applying automatic seniority preferences.

**Acceptance:** The same generalized location input can be translated for supported
sources. Preferences survive navigation. The shortlist setting controls retrieval,
not a promised number of jobs or a separate quota for every board.

### FR-03 — Bounded adaptive collection · P0

- Offer LinkedIn, Indeed, SEEK, Google Jobs and Adzuna as supported sources. Glassdoor was removed on 3 November 2026.
- Use JobSpy for LinkedIn and Indeed, with `fetch_description=True` for Indeed.
   Use the separate direct SEEK collector for SEEK.
- Collect small batches across board/role combinations before expanding visited
   combinations, where the remaining budget permits.
- Prefer further collection from streams yielding eligible, unique postings.
   This heuristic does not establish candidate suitability.
- Apply these default combined web-search limits:

| Limit | Default | Interpretation |
| --- | ---: | --- |
| Search batches | 12 | Collector calls across sources and search combinations |
| Fallback description fetches | 60 | Application-managed missing-description attempts |
| Eligible candidates | 150 | Maximum collected pool for subsequent retrieval |
| Collection time | 120 seconds | Soft deadline; an in-flight call may finish later |

- Keep these settings configurable independently of semantic shortlist size.
- Do not represent collector calls as exact HTTP-request counts. JobSpy can make
   internal requests for pagination, setup, retries and descriptions.
- Stop exhausted or repeated-page streams. Allow full pages of previously seen
   postings to advance so incremental searches can discover later postings.
- Preserve supported fixed-collection compatibility paths and the optional Adzuna
   backend configuration without presenting them as new web source selections.

**Acceptance:** Multiple selected boards share a bounded collection budget. The
application may return fewer candidates than requested and must not claim full
coverage of unvisited roles, locations or country indexes.

### FR-04 — Filtering, descriptions and deduplication · P0

- Normalize posting fields and missing values before retrieval.
- Apply location, posting-age, exclusions, seniority and work-arrangement rules
   using available evidence. Recheck description-dependent eligibility afterward.
- Remove duplicate postings and previously collected identities before additional
   application-managed description processing.
- Prioritize title overlap when selecting description-processing candidates,
   reserving approximately 25% of selections for exploration outside top title
   matches. Process at most 10 candidates per pass, subject to available capacity.
- Reuse inline descriptions and valid cached descriptions before fallback requests.
   Queue remaining candidates for later processing within the same budgets.
- Deduplicate merged results again after descriptions are available, including
   sufficiently supported cross-board duplicates. Do not merge jobs by title alone.
- Preserve SEEK description structure such as paragraphs, headings and lists.
- Exclude postings without usable descriptions from the adaptive retrieval pool.

**Acceptance:** Duplicate checks do not trigger board or model requests. The two
passes have distinct roles: incoming-history exclusion and final result merging.
JobSpy-internal description fetching can precede application filtering; the product
must not claim that all description requests occur after screening.

### FR-05 — Retrieval and indexing · P0

- Create or reuse embeddings for eligible posting versions and index them in Chroma.
- Use HNSW-backed semantic retrieval together with BM25 lexical retrieval and
   reciprocal-rank fusion.
- Use selected role intent, relevant skills and recent work to form retrieval queries.
- Keep each search's eligible posting scope separate from other indexed searches.
- Apply the semantic shortlist limit to eligible retrieved results; “all” means
   the available eligible pool, not every job on the internet.
- Keep ranking values distinct from calibrated probabilities of suitability.

**Acceptance:** Unrelated indexed postings cannot enter a search solely because
they exist in the shared index. Changed content can produce new posting versions.
A larger collection pool is not presented as proof of better relevance.

### FR-06 — Evidence-based evaluation · P0

- Obtain independent assessments from configured Claude, GPT and Gemini models.
- Evaluate providers concurrently, using successive per-provider waves of 15 and
   bounded provider-specific request concurrency and pacing.
- Validate structured responses and apply evidence and scoring rules consistently.
- Distinguish missing evidence from demonstrated mismatch. Do not invent skills,
   compensation, qualifications, employer facts or work experience.
- Do not count academic study or projects as professional employment years.
- Preserve seniority and experience checks when calculating suitability.
- Present per-model outcomes and disagreement; incomplete model coverage must not
   imply unanimous agreement.
- Allow one application-level retry for malformed assessments. Keep persistent
   failures visible and independently retryable.
- Reuse valid private assessment cache entries for unchanged inputs while rerunning
   current evidence checks. Do not cache failures as successful assessments.

**Acceptance:** A failed provider does not erase successful assessments or silently
switch providers. Unknown evidence remains explicit. Retrying one failure does not
rerun successful provider/job assessments unnecessarily.

### FR-07 — Results, details and actions · P0

- Show results progressively as evaluations complete, including pending states.
- Provide grid and table views, accessible sorting and filtering, and job-detail views.
- Show company, role, location, description, application link, fit assessment,
   requirement evidence, gaps and independent model outcomes when available.
- Support Save, Dismiss and Applied actions; preserve them through repeat searches
   and saved-workspace continuation. Dismiss accepts an optional reason (FR-13).
- Record Date added when a job first enters the workspace and preserve it on retries.
   Show “Not recorded” for historical records without that timestamp.
- Order pagination controls as first page, previous page, page numbers with ellipses
   when appropriate, next page and last page.
- Support CSV/Excel exports without silently truncating long content or treating
   user-provided text as spreadsheet formulas.
- Label posting availability as unverified.
- On request, generate a tailored resume for one job (one Claude call) that selects,
   orders and rewords only what the uploaded resume says. List skills or figures not
   found in the resume as "Check before sending" and unmet requirements separately.
   Save it with the job; it can be previewed, copied as text or printed to PDF.

**Acceptance:** Switching views preserves the underlying results and action state.
Pagination boundaries are disabled appropriately. Completed assessments remain
visible when other jobs or providers fail.

### FR-08 — Saved resumes and navigation · P1

- Save reusable profiles and preferences after successful search completion.
- Support listing, editing, continuing and deleting saved resume workspaces.
- Offer grid/table switches as icon buttons aligned to the right of the saved-resume
   controls; keep table actions compact, accessible and identifiable.
- Avoid redundant “Original” and “Name not provided” display clutter. Use meaningful
   workspace labels without inventing candidate identity.
- Fresh application entry starts at `/`. Browser refresh retains the current route.
- Opening a workspace or navigating between pages must not silently start a new
   search, extraction or evaluation.
- Preserve saved resumes independently of temporary run deletion or expiry.

**Acceptance:** A saved profile can be reused without uploading the PDF again.
Refresh preserves the current view; a fresh application entry follows the home-page
behavior. Deleting a run does not delete its independently saved resume.

### FR-09 — Repeat searches and recovery · P0

- Find more jobs opens editable search preferences and appends new unique results
   to the existing workspace using the confirmed profile.
- Apply the selected shortlist size to newly retrieved jobs, preserving old results.
- Retry scraping starts directly from the current page with confirmed inputs.
   Target identified failed boards; older source-less warnings may require retrying
   the originally selected scope.
- Preserve the user's full board preferences when retrying only a subset of sources.
- Retry failed evaluations without collecting jobs again.
- Block overlapping work on the same run and reject inappropriate retry requests.
- Keep cancellation cooperative: stop new work while allowing in-flight operations
   to finish safely, preserving completed results.

**Acceptance:** A 50-result workspace followed by a 15-job incremental search keeps
its original results and adds up to 15 new eligible jobs. Direct scraping retry does
not redirect to profile review. Cancellation and retries preserve successful work.

### FR-10 — Source failures and rate limits · P0

- Preserve usable partial results when a board fails or rate-limits requests.
- Handle rate limits behind the scenes: log them on the server, never show them
   as search errors (including those saved in older runs), and suppress redundant
   missing-description warnings caused by that same pause. If a rate limit leaves
   a search with no jobs at all, show "Job boards are busy right now. Try
   again in a few minutes." Otherwise show a calm note that names the board and
   says the user may see fewer jobs from it, with nothing to fix on their side.
- When a job-listing request returns a 429 with no rows, pause 30 seconds and
   retry it once. After that, stop further application-managed requests to the
   board in the current collection. Requests already executing inside a provider may finish.
- Do not enforce a timed local cooldown between LinkedIn or Indeed searches.
   A user may manually retry immediately; another 429 remains possible.
- Preserve SEEK's separate request pacing and backoff behavior.
- Retain historical warnings with incomplete results. A new search resets its current
   warning state; a saved warning is not evidence of ongoing requests.

**Acceptance:** A failed board does not prevent unaffected sources from completing.
Immediate manual retry is not presented as removal of the provider's own rate limit.

### FR-11 — Progress and accessibility · P1

- Show a loading bar with explanatory text below it during collection and matching.
- Use indeterminate progress when total work is unknown and measured completion
   for evaluation where counts are available.
- Indicate cancellation, connection recovery, empty results, partial completion,
   upload rejection and provider failure distinctly.
- Support keyboard interaction, visible focus, accessible control names, responsive
   layouts, readable contrast and reduced-motion preferences.

**Acceptance:** Progress is visible during long-running work without invented
percentages. Polling or stream reconnection does not launch duplicate searches.

### FR-12 — LangSmith observability · P1

- Offer opt-in LangSmith tracing, disabled by default and configured server-side.
- Group collection traces by provider-labelled batch, with search, filtering,
   incoming deduplication, description selection/loading and result merging nested
   beneath each batch.
- Group deferred description processing separately when it spans multiple sources.
- Trace resume intake, indexing, retrieval, provider batches, individual job
   evaluations, model attempts and evaluation retries.
- Preserve parent/child identity across worker threads and trace completion updates.
- Export fixed stage names, timing, numeric counts, allowlisted source/provider
   labels and sanitized outcomes. Do not export private inputs, prompts, document
   content, raw exceptions, attachments, paths or private application run identifiers.
- Keep implicit prompt tracing disabled within instrumented operations.
- Let missing credentials or telemetry failures leave application work unaffected.

**Acceptance:** New traces show completed stage outcomes and valid parent links.
A handled source/provider failure is distinguishable from complete success. Mocked
serialization tests verify that private payloads are absent. The current stage
integration does not provide native LLM token counts, cost estimates or prompt
inspection; these are not implied by an evaluation-model-request span.

### FR-13 — Dismissal preferences · P1

- Let Dismiss record an optional reason: role, location, seniority, salary or other.
   No reason only hides the job.
- Derive title, location and seniority from the job stored in the workspace, not
   from client-supplied attributes. Salary preferences require a positive minimum,
   a supported currency and an hourly or yearly period.
- In future searches, move retrieved postings that match a preference below those
   that do not, before applying the shortlist size. Do not compound repeated reasons,
   exclude jobs, change explicit search constraints or rewrite existing fit scores.
- Match conservatively: exact normalized role or location, explicit title-level
   seniority, and explicitly stated comparable pay wholly below the minimum. Unknown
   or ambiguous data has no effect; "Other" has no ranking effect.
- Keep feedback with the owning saved resume or temporary run. Never send it to
   evaluation models, the shared index or training.
- Do not list saved reasons on the results page; keep them for future searches and
   later reference. Restoring a job removes its feedback.

**Acceptance:** A preference changes only the ordering of later shortlists. A
different saved profile does not inherit it. "All jobs" still retains every
retrieved job. No matching-accuracy improvement is claimed without labeled
comparison (section 9).

### FR-14 — Pipeline playground · P1

- Provide a playground at `/eval` that runs one pipeline stage on its own: Upload
   (PDF to profile, with a label-free check against the resume text) and Ingestion
   (live collection with kept and dropped jobs and reasons) and Retrieval (the
   ingestion jobs ranked against the uploaded profile, with the queries and weights).
- Runs are explicit, make live calls, are never saved and never change searches.

**Acceptance:** Opening the page makes no calls. A run creates no workspace or file.

FR-15 (human review datasets) was removed on 2 November 2026.

## 7. Data, caching and lifecycle

| Data category | Required lifecycle |
| --- | --- |
| Temporary runs, uploaded PDFs and run-derived results | Seven days from run creation; cleanup on supported lifecycle checks |
| Independently saved profiles and resumes | Retain until explicitly deleted |
| Successful identical collection results | Default reuse for 15 minutes; bounded cache |
| Public descriptions | Default seven-day reuse where supported |
| Job embeddings | Default 30-day reuse; recompute expired or changed entries |
| Shared indexed posting versions | Refresh observations and age out inactive versions under retention policy |
| Private structured assessments | Seven-day reuse, bounded per owning workspace |
| Saved-profile job actions | Persist with the saved workspace, with local synchronization support |
| Dismissal preferences | Persist with the owning saved resume or temporary run |
| Ingestion drop records | Bounded per search; kept with the run for seven days |
| Tailored resumes | Saved on the job's result row; follow the run or saved profile |
| Job-action labeled dataset | `data/evaluation_datasets/`, one per saved profile or run; kept until deleted by hand |
| Generated query ads (`hyde`) | `.cache/hyde_queries/`, keyed by prompt |

- Cache keys must separate materially different inputs and policy versions.
- Empty, cancelled or detected failed collections must not be cached as complete.
- Successful budget-limited collections may be cached; completeness does not mean
   exhaustive discovery of every vacancy.
- Find more jobs requests fresh collection while retaining reusable descriptions,
   embeddings and valid assessments where applicable.
- Remove database caches only after relevant workers/connections are stopped.
   Restart the backend after database-cache deletion before collecting again.
- Cache maintenance must preserve profiles, resumes and run history unless their
   deletion is explicitly requested.
- Deleting a run with an active worker blocks further updates and defers physical
   cleanup until the worker exits safely.

## 8. Operational and non-functional requirements

- Run the supported FastAPI backend with a single worker because active search,
   cancellation and coordination state are process-local.
- Use typed request/response contracts between the Vue interface and backend.
- Keep snapshot state authoritative; use event streaming and polling recovery for
   progress delivery.
- Preserve supported executable and API compatibility paths.
- Keep credentials server-side and outside source control. Do not include private
   data in test fixtures, logs, documentation, tracing or exports without explicit
   authorization for the relevant use.
- Treat resume and posting contents as untrusted evidence, not executable model
   instructions; render descriptions safely.
- Acknowledge that saved data is server-wide and run URLs expose private run data.
   The current product is not an authenticated multi-tenant service.
- Provide a privacy and data-retention page explaining what is stored, for how
   long, what is shared with model providers and how to delete it.
- Keep collection limits explicit; do not promise a fixed end-to-end duration when
   external boards and model providers determine response time.

## 9. Success measures and validation

| Area | Measurement | Acceptance interpretation |
| --- | --- | --- |
| Upload correctness | Valid-resume acceptance, non-resume rejection, malformed-response handling | Validate with synthetic and authorized representative inputs; model classification is fallible |
| Result preservation | Lost/duplicated results and changed action flags after retry or append | No unintended loss or duplicate insertion in regression scenarios |
| Failure isolation | Retained usable results after board/provider failure | Successful work remains usable and incomplete coverage is visible |
| Collection efficiency | Batch calls, fallback fetches, cache reuse, eligible unique yield | Stay within configured application budgets; distinguish internal provider HTTP calls |
| Retrieval quality | Observed recall at k and missed labeled positives | Requires human-labeled relevant postings, including candidates outside the shortlist |
| Assessment quality | Strong-match precision and evidence correctness | Evaluate against held-out human labels; model agreement is not ground truth |
| Performance | Collection/retrieval/evaluation latency distributions and cache-hit timing | Compare equivalent workloads; no unmeasured speedup claims |
| Observability | Valid hierarchy, completion updates and payload exclusion | Verify with mocked transport and separately authorized live delivery |
| Accessibility | Keyboard, responsive-layout and accessibility checks | Core workflows remain operable across supported views |

Human review tooling was removed on 2 November 2026 and no labeled baseline has
been established; earlier review datasets were pilots from a single profile, with
no credible held-out split. Relevance recall, strong-match precision and
missed-suitable-job rates therefore remain unverified.
Synthetic HNSW recall against exact vector search measures approximate-neighbor
behavior, not job suitability. Do not invent accuracy targets or claim full recall
from partially labeled pools.

Release verification must include relevant backend, frontend, contract and build
checks, plus browser checks for changed user workflows. External provider tests
must be explicitly authorized; mocked tests establish software behavior, not live
availability, permission to collect data or guaranteed service performance.

## 10. Risks and limitations

- Board blocking, rate limits, schema changes and incomplete descriptions can reduce
   coverage even when the application behaves correctly.
- JobSpy description fetching can increase internal request volume before filtering.
- Adaptive source yield and title-based selection can miss unusual relevant jobs;
   the exploration quota does not establish recall.
- Inconsistent source locations, missing dates and ambiguous work arrangements can
   affect eligibility decisions.
- Models may disagree, omit evidence or return invalid structured responses.
- Local cache freshness does not establish that a vacancy is still open.
- Deleting database files while the backend is running can leave stale connections.
- Best-effort tracing delivery can leave old traces incomplete after ingestion
   failures or process termination; it must not be confused with active PDF work.
- No user-account isolation is provided by the current application.

## 11. Changes requiring separate product decisions

The following are not part of this requirement baseline: full trace payload logging;
native LLM token/cost accounting; additional data providers; production authentication
and tenancy; automatic applications; and new accuracy or latency service-level
commitments. Each requires explicit scope, acceptance criteria and appropriate
validation before being represented as a delivered capability.
