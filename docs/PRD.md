# Product Requirements — Career Finder

**Repository:** Career Tracker
**Updated:** 17 November 2026
**Scope:** Agreed product requirements and acceptance criteria. How they are
implemented is in [Architecture.md](Architecture.md); planned work is in
[ROADMAP.md](ROADMAP.md).

## 1. Purpose

Career Finder helps candidates find relevant jobs and judge their fit using their
own resume evidence. Candidates upload a resume, check the extracted profile,
choose search preferences, get a ranked shortlist and review independent model
assessments. Saved workspaces let them return to results and track decisions
without uploading again.

Acceptance criteria are verification conditions, not claims that live job-board
availability or matching accuracy has been established.

## 2. Users and problem

Job seekers face scattered sources, duplicate postings, inconsistent location
labels and long descriptions. Keyword search misses transferable skills, and an
unexplained fit score can hide real experience gaps. Primary users are students,
early-career applicants and career changers. An operator also needs to diagnose
pipeline failures without exposing candidate data, and to measure matching
quality against human judgments.

## 3. Goals

- Reduce repeated resume entry and manual review of duplicate postings.
- Let candidates express role and location preferences in familiar language.
- Explain suitability through job requirements and quoted resume evidence.
- Keep useful results when a source, model or network request fails.
- Make progress, retries, uncertainty and collection limits understandable.
- Support repeat searches and saved decisions without losing history.

## 4. Scope

**Included:** resume intake and extraction; editable profile review; saved
resumes; multi-board collection; filtering and deduplication; hybrid retrieval;
independent fit assessments by three models; results and job details; job
actions; exports; incremental searches; targeted retries; cancellation; cache
reuse; optional tracing; dismissal-based shortlist ordering; a pipeline
playground; a per-job tailored resume; a labeled dataset built from job actions.

**Not included:** automatic job applications; cover letters; guarantees that
postings are open or that every matching vacancy is found; employment outcomes;
user accounts, tenant isolation and production authorization; hosting through
LangSmith Studio; Greenhouse, Lever or Glassdoor as sources.

## 5. Primary journey

1. Open the home page or continue a saved workspace.
2. Upload a PDF and get clear validation or extraction feedback.
3. Review and correct the extracted profile.
4. Choose target roles, locations, boards and filters.
5. Start the search and follow progress with explanatory status text.
6. Review shortlisted jobs as assessments arrive.
7. Inspect requirements, evidence, gaps and model disagreement.
8. Save, dismiss or mark jobs applied; tailor the resume for a job; export.
9. Find more jobs or retry failed work without losing completed results.

## 6. Functional requirements

**P0** is core workflow or correctness; **P1** is supporting usability or operations.

### FR-01 — Resume intake and extraction · P0

- Accept PDFs by file picker and drag-and-drop; enforce 5 MB and 20 pages; reject
  invalid, encrypted or unreadable files with an actionable message.
- Extract text locally, with OCR for scanned PDFs when Tesseract is installed.
- Classify the document as a resume and extract the profile in one OpenAI request,
  before allocating a run or storing the PDF. Show "Powered by OpenAI"; no model picker.
- Reject non-resumes without creating a run; distinguish rejection from provider failure.
- Extract once and reuse the confirmed context for every evaluation.

**Acceptance:** A valid upload reaches profile review. A non-resume creates no
workspace or saved PDF. A provider failure is shown as a failure, never as an
invented profile.

### FR-02 — Profile review and preferences · P0

- Let the candidate correct every extracted field before searching.
- Support target roles, locations, boards, posting age, work arrangement,
  seniority, exclusions and shortlist size.
- Normalize locations internally; never ask for board-specific location codes.
  Empty location means worldwide, within board and budget limits.
- Offer shortlist sizes Automatic (default: the whole pool up to 200 jobs, else the
  top 100), 15, 50, 100 or all retrieved jobs.
- Keep explicit seniority choices over the automatic early-career ordering.

**Acceptance:** One location input works across boards. Preferences survive
navigation. The shortlist size controls evaluation, not per-board collection.

### FR-03 — Bounded adaptive collection · P0

- Offer LinkedIn, Indeed, SEEK, Google Jobs and Adzuna.
- Share one budget across selected boards: 12 collector batches, 60 app
  description fetches, 150 eligible candidates, 240-second soft deadline, each
  configurable separately from shortlist size.
- Visit each board/role combination before expanding; then prefer streams that
  yield eligible unique postings. Stop exhausted or repeating streams.
- Never present collector calls as exact HTTP-request counts.
- Keep paid boards (Google Jobs, Adzuna) bounded per search and skip unsupported
  countries without a request.

**Acceptance:** Selected boards share the budget. The app may return fewer jobs
than requested and must not claim coverage of unvisited roles, locations or countries.

### FR-04 — Filtering, descriptions and deduplication · P0

- Normalize fields; apply location, age, exclusions, seniority and work-arrangement
  rules on available evidence; recheck after descriptions load.
- Remove duplicates and previously collected postings before fetching descriptions.
- Select descriptions by title overlap with about 25% exploration; reuse inline and
  cached text first.
- Merge cross-board duplicates only on strong evidence, never by title alone.
- Preserve SEEK description structure. Drop postings without a usable description.
- Record dropped postings with stage and reason, without changing eligibility.

**Acceptance:** Duplicate checks make no board or model requests.

### FR-05 — Retrieval and indexing · P0

- Embed eligible posting versions and index them in Chroma; reuse unchanged vectors.
- Combine dense and BM25 rankings with weighted reciprocal rank fusion, using
  queries built from target roles, evidenced skills and resume entries.
- Keep each search's eligible scope separate from the shared index.
- Keep ranking values distinct from probabilities of suitability.

**Acceptance:** Unrelated indexed postings cannot enter a search. A larger pool is
not presented as proof of better relevance.

### FR-06 — Evidence-based evaluation · P0

- Extract each posting's requirements once, without the resume, with quotes copied
  from the posting; every model assesses that same list.
- Get independent assessments from Claude, GPT and Gemini, concurrently, in waves of 15.
- Each model returns a per-requirement verdict with resume quotes and decides the
  fit category; the app validates schema, requirement IDs and quotes.
- Distinguish missing evidence from a demonstrated mismatch. Never invent skills,
  pay, qualifications, employer facts or experience.
- Academic study and projects never count as professional years. Seniority rules
  are defaults a model may set aside only with a quoted reason.
- Show per-model outcomes; the combined verdict requires agreement of every model
  the job was sent to, otherwise For review.
- Retry malformed output once; keep persistent failures visible and retryable.
- Skip models that are out of quota or misconfigured, report them, and never
  substitute another provider.
- Reuse valid private assessments for unchanged inputs; never cache failures.

**Acceptance:** A failed provider doesn't erase other results or switch providers.
Unknown evidence stays explicit. Retrying one failure doesn't rerun successes.

### FR-07 — Results, details and actions · P0

- Show results progressively, including pending rows.
- Grid and table views with accessible sorting, filtering and pagination
  (first, previous, numbered pages with ellipses, next, last).
- Job details: company, role, location, description, link, verdicts, requirement
  evidence and per-model outcomes.
- Save, Dismiss (optional reason, FR-13) and Applied; keep them across repeat
  searches and saved workspaces.
- Show Date added, preserved on retries ("Not recorded" for old jobs).
- CSV/Excel exports without silent truncation or formula injection.
- Label posting availability as unverified.
- On request, generate a tailored resume for one job (one Claude call) using only
  facts in the uploaded resume; flag unverified skills or figures and list unmet
  requirements separately; save it with the job; allow copy and PDF print.

**Acceptance:** Switching views keeps results and action state. Completed
assessments stay visible when other jobs or providers fail.

### FR-08 — Saved resumes and navigation · P1

- Save the profile, preferences and PDF automatically after a search; support
  list, edit, continue, new search and delete, in grid or table view.
- Fresh opens start at `/`; refresh keeps the current page.
- Opening a workspace never starts a search, extraction or evaluation by itself.
- Saved resumes are independent of run deletion or expiry.

**Acceptance:** A saved profile is reusable without uploading again. Deleting a run
leaves its saved resume.

### FR-09 — Repeat searches and recovery · P0

- Find more jobs opens editable preferences and appends new unique results using
  the confirmed profile; the shortlist size applies to the new batch.
- Retry scraping reruns failed boards in place with confirmed inputs.
- Retry failed evaluations without collecting again, with its own progress.
- Block overlapping work on one run; cancellation is cooperative and keeps results.
- Reject a changed profile in a workspace that already has assessments.

**Acceptance:** A 50-job workspace followed by a 15-job search keeps its jobs and
adds up to 15 new ones. Retries and cancellation keep successful work.

### FR-10 — Source failures and rate limits · P0

- Keep partial results when a board fails or rate-limits.
- Handle rate limits quietly: log them, retry an empty 429 listing once after
  30 seconds, then stop that board for the current search. Show a calm note naming
  the board, or "Job boards are busy right now. Try again in a few minutes." when
  nothing was found. No timed cooldown between searches.
- Keep SEEK's own pacing and backoff.

**Acceptance:** A failed board doesn't stop the others.

### FR-11 — Progress and accessibility · P1

- Loading bar with status text; indeterminate during collection and matching,
  measured counts during evaluation and retries.
- Distinct states for cancellation, reconnection, empty results, partial
  completion, upload rejection and provider failure.
- Keyboard use, visible focus, accessible names, responsive layout, contrast and
  reduced motion.

**Acceptance:** No invented percentages. Reconnecting never launches duplicate work.

### FR-12 — LangSmith observability · P1

- Opt-in, server-side, off by default. Trace upload, collection batches,
  indexing, retrieval, requirement extraction, provider batches, jobs, model
  attempts and retries, with correct parent links across threads.
- Export only stage names, timings, counts, allowlisted labels, outcomes and
  provider-reported token usage. Never export resumes, postings, prompts, raw
  errors, paths or private IDs.
- Telemetry failure never affects application work.

**Acceptance:** Mocked serialization tests show private payloads are absent.

### FR-13 — Dismissal preferences · P1

- Optional reason: role, location, seniority, salary (positive minimum, supported
  currency, hourly or yearly) or other.
- In later searches, move matching postings below the others before the shortlist
  cut. Never exclude jobs, compound penalties, change verdicts or send feedback to
  models, the shared index or training.
- Match conservatively; unknown data has no effect. Take job attributes from the
  stored job, not the client.
- Feedback follows the saved resume; restoring the job removes it.

**Acceptance:** Only later shortlist ordering changes. Another profile doesn't
inherit it. "All jobs" keeps every retrieved job.

### FR-14 — Pipeline playground · P1

- `/eval` runs Upload (profile plus a check against the resume text), Ingestion
  (live collection with kept and dropped jobs) or Retrieval (ranking with queries
  and weights, optional relevance marks and metrics) on its own.
- Runs are explicit, may make live calls, are never saved and never change searches.

**Acceptance:** Opening the page makes no calls. A run creates no workspace or file.

### FR-15 — Labeled dataset from job actions · P1

- Each Applied or Dismiss action updates a private per-profile dataset: applied is
  a strong match; role or seniority dismissal is not suitable; other dismissals
  carry no fit label. Undo removes the label; hand labels are never overwritten.
- A dataset failure never blocks the action.

**Acceptance:** Labels track the latest action state; the action is saved even if
the dataset write fails.

## 7. Data lifecycle

| Data | Lifecycle |
| --- | --- |
| Runs, uploaded PDFs, run results | 7 days from creation |
| Unsearched, unsaved uploads | Memory only |
| Saved profiles and resumes | Until deleted |
| Identical collection results | 15 minutes, bounded |
| Public descriptions | 7 days |
| Job embeddings | 30-day reuse |
| Shared posting versions | Removed 7 days after last seen |
| Shared requirement lists | 7 days, bounded |
| Private assessments | 7 days, ≤ 1,000 per owner |
| Job actions and dismissal feedback | With the saved profile, else the run |
| Ingestion drop records | With the run |
| Tailored resumes | On the job row |
| Job-action datasets | Until deleted by hand |

- Cache keys separate materially different inputs and policy versions.
- Empty, cancelled or failed collections are never cached as complete.
- Remove database caches only with workers stopped, then restart.
- Cache maintenance preserves profiles, resumes and run history.

## 8. Non-functional requirements

- One FastAPI worker; process-local run state.
- Typed contracts between frontend and backend; generated types, never hand-edited.
- Snapshots authoritative; SSE plus polling recovery.
- Keep compatibility entry points and API aliases.
- Credentials stay server-side and out of source control; no private data in
  fixtures, logs, docs, traces or exports.
- Treat resume and posting text as untrusted evidence; render it safely.
- State plainly that there are no accounts and run URLs are private capabilities;
  provide a privacy page on storage, retention, provider sharing and deletion.
- Rate-limit work-starting requests; don't promise end-to-end durations.

## 9. Success measures

| Area | Measure |
| --- | --- |
| Upload | Valid acceptance, non-resume rejection, malformed-response handling |
| Preservation | No lost or duplicated results or flags after retry or append |
| Failure isolation | Usable results kept; incomplete coverage visible |
| Collection | Within budgets; cache reuse; eligible unique yield |
| Retrieval quality | Observed recall@K and missed positives on human labels, including outside the shortlist |
| Assessment quality | Strong-match precision and evidence correctness on held-out labels |
| Performance | Latency distributions on equivalent workloads |
| Accessibility | Keyboard, layout and axe checks on core workflows |

No held-out labeled baseline exists yet; the only labels are a one-profile pilot.
Recall, precision and missed-job rates are unverified. Synthetic ANN recall
measures the index, not suitability. Don't claim full recall from partial labels.

Releases need the standard checks plus browser checks for changed workflows. Live
provider tests need explicit authorization.

## 10. Risks

- Board blocking, rate limits, format changes and short descriptions reduce coverage.
- Title-based selection and budgets can miss unusual relevant jobs.
- Inconsistent locations, dates and work arrangements affect eligibility.
- Models disagree, omit evidence or return invalid output; shared extraction
  mistakes affect all three.
- Cache freshness doesn't mean a vacancy is open.
- No account isolation.

## 11. Decisions needed before building

Full trace payload logging; LLM cost accounting in the app; new data providers;
authentication and tenancy; automatic applications; accuracy or latency
commitments. Each needs explicit scope, acceptance criteria and validation.
