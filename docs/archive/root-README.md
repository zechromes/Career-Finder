# Career Tracker

Upload a resume, review your profile, search job boards, rank matches, and evaluate candidate fit. Vue provides the interface; FastAPI coordinates extraction, JobSpy/SEEK collection, Chroma retrieval, and model evaluation.

## Quick start

Use the Python environment containing the project dependencies (locally, `conda activate job-tracker`):

```bash
python -m pip install -r backend/requirements.txt
# For a new installation only: copy .env.example to .env and configure keys.
./run_app.sh
```

The launcher starts the API on http://127.0.0.1:5000 and the interface on http://localhost:5173 without opening a browser tab. Open the interface URL manually. It installs frontend dependencies if needed. It uses the `job-tracker` conda environment when it exists, otherwise the active `python`; set `PYTHON_BIN=/path/to/python` to choose another interpreter. Ctrl+C stops both services. Restart after backend changes.

API documentation: http://127.0.0.1:5000/docs. Use one Uvicorn worker: active jobs and cancellation state are process-local. Scanned resumes require Tesseract (`brew install tesseract` on macOS).

## Project layout

```text
backend/                 Python application package
  app.py                 FastAPI assembly, middleware and frontend assets
  routers/               HTTP routes grouped by feature; delegate to backend handlers
  schemas/               API contracts, resume, saved-profile and evaluation models
  runs.py                Shared run state, locking, persistence and worker lifecycle
  runs_api.py            Run status, progress, cancellation, deletion and exports
  configuration.py       Provider defaults and location suggestions
  pages.py               Frontend page serving
  paths.py               Stable repository and runtime paths
  cli.py                 Command-line pipeline
  profiles/              Upload/extraction, saved-profile continuation and storage
  search/                Search service, collection, retrieval, ranking and embeddings
  evaluation/            Retry service, provider orchestration and evidence scoring
  exports.py             Excel-safe exports
  requirements.txt       Backend dependencies
frontend/                Vue app, components, state, tests, build config
scripts/                 Maintenance tools and verification launcher
integrations/            Optional Google Sheets MCP service
tests/                  Python regression tests
docs/                   Guides and archived design notes
  images/                Workflow image, API reference and OpenAPI export
run_app.sh               Start API and frontend together
run_application.py       Compatibility CLI launcher
requirements.txt         Convenience include for backend dependencies
```

Python imports use `backend.profiles.*`, `backend.search.*`, `backend.evaluation.*`,
and `backend.schemas.*`. Import-only compatibility wrappers have been removed.
The executable server alias `frontend.app:app` and CLI launcher remain available;
prefer `backend.app:app` and `python -m backend.cli` for new usage.

While searching, the timeline shows a loading bar with collection/description status
text below it; evaluation shows measured completion progress.

Web searches collect small batches across boards and roles, then expand sources
returning eligible, unique postings. Defaults are 12 search batches, 60 fallback
description fetches and 150 eligible candidates across all boards, with a
120-second soft deadline. JobSpy uses `fetch_description=True`; its internal
description requests are outside the fallback-fetch limit. These limits are separate from semantic shortlist size.
See [adaptive collection](docs/job-search-providers.md#adaptive-web-collection)
for configuration and coverage limitations.

From results, choose **Find more jobs** to reuse or change roles and search
preferences, then **Search for more jobs**. New shortlisted jobs join the same
results; previous assessments and saved-profile Save/Dismiss/Applied flags remain.
The shortlist size applies to the new batch: choosing 15 after a 50-job search
keeps the original jobs and adds up to 15 new eligible jobs.

A job's **Tailored resume** tab asks Claude (`CLAUDE_EVALUATION_MODEL`, one live call)
to rewrite your uploaded resume for that posting: it selects, orders and rewords what
your resume already says and never adds skills, years or results. Skills or figures
it writes that are not in your resume are listed under **Check before sending**, and
requirements your resume does not show are listed separately, outside the resume.
The result is saved with the job. It follows the UNSW Employability resume guide: name
and contact line (no date of birth, gender or marital status), a 3–5 point Career Profile,
relevance-ordered sections (Relevant Experience, Additional Experience, Relevant Projects,
Education — first for early careers — and so on), achievement-statement bullets, Technical
Skills, then Interests and Referees last. It stays ATS-friendly: one column, bold capital
headings, Arial, no tables or graphics. **Download PDF** prints only the sheet, titled with
your name, on pages with no margin left for the browser's date, title and URL headers.

When dismissing a job, you can optionally give a reason. Matching jobs rank lower
in future shortlists without changing candidate-fit scores or excluding postings.
Role and location feedback match the same normalized title/location; seniority
feedback uses explicit title levels. Salary feedback requires your minimum,
currency and pay period and only affects clearly comparable stated pay.
Saved reasons are not shown on the results page; they are kept for future
searches and later reference. Restoring a job removes its feedback. Preferences follow the saved resume across searches. This is local
preference-based ordering, not model training. See [dismissal preferences](docs/dismissal-preferences.md).

**Retry scraping** starts failed sources directly using the confirmed profile and
preferences, preserving existing results. It stays on the current page. LinkedIn and Indeed retries have no
local cooldown. Rate limits (429) are handled quietly: a listing request is retried
once after a 30-second pause, then that board stops for the current search, and the
message goes to the server log instead of the page.
Older warnings without a source name retry the selected board scope.

Before candidate evaluation, a shared OpenAI extraction identifies the posting's
requirements without the resume. It selects numbered source lines; the backend
copies the original text as quotes so model transcription cannot alter evidence.
Source ranges, quotes and duplicate criteria are validated;
all evaluation models must assess the same IDs and preserve the criteria exactly.
Public posting requirements are reused across profiles in `.cache/job_requirements/`
for seven days (bounded to 1,000 entries). `REQUIREMENT_EXTRACTION_MODEL` defaults
to `gpt-4o-mini`. Failed extraction stops that posting's assessment, without an
independent-extraction fallback. No human-labeled quality improvement is claimed.

Malformed model assessments receive one automatic retry for that job and provider,
with the same validation and request pacing. Persistent failures remain visible
and can be retried through the failed-evaluation action; successful assessments
are retained.

Loading a saved profile also recovers missing jobs from that workspace's local
assessment journal if an older search replaced its result snapshot. Recovery
preserves current rows, skips duplicates, and saves a backup before changing the
snapshot. Deleted or expired journals cannot be recovered this way.
Claude assessments allow up to 8,192 output tokens; validation errors distinguish
truncation, parsing failures, and invalid schema fields without exposing model
response content. Persistent failures remain failures rather than inferred scores.

## Debugging with LangSmith

Optional stage tracing covers resume intake, job collection, filtering, description
loading, indexing, retrieval and provider/job evaluation. It records timings,
counts and failure categories without exporting resume or job text. See
[LangSmith setup and trace coverage](docs/langsmith-tracing.md).

## Data locations

Web searches reuse versioned public posting vectors in `.cache/job_index/`.
See [shared posting indexing](docs/shared-job-index.md)
for retention, coverage and measured retrieval performance.

Collected public postings are cached in `.cache/job_collections/` for 15 minutes
by exact search parameters. Entries are bounded and removed opportunistically;
saved resumes and candidate text are not stored in this cache.
JobSpy boards share title screening and description reuse; Indeed/SEEK public
description caches live in `.cache/job_descriptions/`, while LinkedIn retains
`.cache/linkedin_descriptions/`. See [provider behavior](docs/job-search-providers.md). **Find more jobs**
forces a fresh collection. See [collection caching and measurement](docs/collection-caching.md).

Existing data remains in place: `frontend/runs/` contains persisted web runs, `.cache/job_embeddings/` contains cached job vectors, and `vector_db/` plus root CSV/text exports may contain older CLI output. `Files/` and `Credentials/` are local private inputs. These paths are ignored by version control. Code reorganization does not migrate or delete them.

An uploaded resume and its extracted profile stay in server memory only until you
start a search or save the profile; an upload you abandon is never written to disk,
and is lost if the backend restarts first. Runs expire after seven days under the existing lifecycle rules. There are no user accounts; keep run URLs private. Browser job-action flags remain in localStorage.

## Commands

```bash
# Backend only
python -m uvicorn backend.app:app --host 127.0.0.1 --port 5000

# CLI help (the old python run_application.py command also works)
python -m backend.cli --help

# Maintenance tools: run from the project root
python -m scripts.recover_excluded_jobs --help
python -m scripts.measure_matching --help
python -m scripts.load_chroma  # requires a Chroma server on localhost:8000

# Optional Sheets integration uses the job-tracker conda environment (gspread, fastmcp already installed)
conda activate job-tracker
python -m integrations.sheets_mcp_server
```

The optional Sheets integration uses the existing local service-account file in `Credentials/`. It is not required by the web app and is not started by `run_app.sh`.

## Verification

```bash
./scripts/check.sh
# Also run mocked browser workflows and accessibility checks:
./scripts/check.sh --e2e
```

Like the launcher, checks use the `job-tracker` conda environment when it exists (or `PYTHON_BIN`) and stop early if project dependencies are missing. Install Playwright Chromium once with `cd frontend && npx playwright install chromium`. Checks cover Python regressions, API schema generation, TypeScript, frontend unit/regression tests, and the production build. Browser tests use mocked providers; these checks do not prove live third-party availability.

## Documentation

- [Animated workflow flowchart](docs/images/application-workflow-flowchart.html) · [GIF](docs/images/application-workflow-flowchart.gif)
- [Technical workflow guide](docs/application-workflow-technical-guide.md)

- [API reference (OpenAPI)](frontend/openapi.json)
- [Frontend development](frontend/README.md)
- [Shared posting index](docs/shared-job-index.md)
- [Job search providers](docs/job-search-providers.md)
- [Collection caching, freshness, and retrieval measurements](docs/collection-caching.md)
- [Evaluation model configuration](docs/EVALUATION_MODELS.md)
- [Matching behavior](docs/matching-improvements.md)
- [Review findings and implemented fixes](docs/review-follow-up.md)
- [Product requirements](docs/PRD.md)
- [Current project context](docs/project-context.md)

Job cards and the results table show **Date added** in your browser’s local time.
The timestamp records when a job first appears in the workspace and stays unchanged
on evaluation retries. Older jobs without a recorded timestamp show **Not recorded**.

### Resume upload API

Profile extraction is powered by OpenAI and uses it exclusively. Uploads classify
and extract a profile in one structured request, before generating a run ID or
saving the PDF. `OPENAI_UPLOAD_MODEL` overrides the upload model; otherwise it
uses `OPENAI_PROFILE_MODEL` (default `gpt-6.1-sol`, at low reasoning effort). The
model lists every resume heading first, keeps sections beyond work and education
(projects, certifications, volunteering and so on) under their own headings, and
suggests target roles with a reason. The original resume text is kept with the
profile so evaluators can quote evidence that extraction missed. The standalone compatibility
validator still uses `OPENAI_RESUME_CHECK_MODEL`. PDF/OCR extraction is local.
Unrelated or unclear documents return HTTP 422; provider failures, invalid or
inconsistent structured responses return HTTP 503. These failures create no run
or saved PDF. Temporary OCR images are removed after processing. A normal
readable upload uses one model invocation; SDK retries can issue another request.
Classification remains model-based and can make mistakes.
The optional upload `model` field accepts only `openai`.

`POST /api/resumes/upload` (**Upload resume**) accepts a PDF and waits for profile
extraction before returning HTTP 201 with the workspace ID. The next snapshot
contains the profile or extraction error. Blocking extraction uses an awaited
managed thread-pool call, with no detached task. Job collection starts
only after profile confirmation. Older `POST /api/searches` and `POST /api/runs`
clients remain supported through hidden compatibility routes.

### Code formatting

Install the Python formatter with `python -m pip install -r requirements-dev.txt`.
Run `black backend tests scripts integrations frontend/app.py frontend/scripts run_application.py`
for Python, and `npm --prefix frontend run format` for maintained frontend files.
Use `npm --prefix frontend run format:check` to check without writing.
Generated contracts, dependencies, saved data, and build output are excluded.

### Backend routing

HTTP requests pass through `backend/routers/` before reaching backend handlers:

```text
POST /api/resumes/upload
  → routers/uploads.py: upload_resume()
  → profiles/upload.py: upload_resume()
  → profiles/upload.py: execute_profile()
```

`uploads.py` declares resume-upload routes; `searches.py` declares search, progress,
retry, cancellation and export routes; `profiles.py` declares saved-profile CRUD;
`profile_searches.py` declares saved-profile continuation; `configuration.py`
provides models, defaults and location suggestions; `pages.py` serves frontend pages.
`app.py` registers the routers with their feature modules. Search handlers live in
`search/service.py`, evaluation retries in `evaluation/service.py`, and saved-profile
continuation in `profiles/service.py`. All services share `runs.py` for run state
and persistence; none import `app.py`. Storage functions stay in `backend/profiles/storage.py`; its
`router` export remains available for older imports. Internal Python calls can
still invoke handlers directly—only incoming HTTP requests pass through routers.

Schema definitions live in `backend/schemas/`: `contracts.py` for API requests and
responses, `resume.py` for extracted profiles, `saved_profiles.py` for persisted
profile models, and `evaluation.py` for assessment and requirement models. Import
these models directly from `backend.schemas.*`.

Application startup opens `/` for fresh opens and direct URLs. Browser refreshes retain the current page.
Navigation after startup works normally. This does not delete saved profiles or results.

### Pipeline playground

Open `/eval` in the browser (there is no header link) for the pipeline playground: run
one stage on its own and inspect its output. **Upload** reads a PDF into a profile
exactly as an upload does (one OpenAI call) and checks it against the resume's own
text. **Ingestion** searches the selected boards live, bypassing the collection
cache, and lists kept and dropped jobs with reasons. **Retrieval** ranks the Ingestion tab's kept jobs against the Upload tab's profile
with the same queries, weights and fusion as a search, in a throwaway index (OpenAI
embeddings unless cached), and shows the queries and the ranked shortlist. Marking
shortlisted jobs Relevant or Not relevant shows Recall@k, context precision and context
relevance computed from those marks; unmarked jobs count as unknown, and the marks are
kept in this browser only, by job URL. Runs are never saved and never touch searches. The tab is kept in the URL as
`?stage=upload|ingestion|retrieval`.

Review datasets, labeling, model-comparison experiments and retrieval replay were
removed on 2 November 2026. Files already under `data/evaluation_datasets/` are left
on disk but nothing reads them.

Since 12 November 2026, applying to or dismissing a job also labels it in a dataset in
the same format, one per saved profile (`data/evaluation_datasets/<id>/dataset.json` and
`reviews.json`, `source: "job_actions"`): applied is `strong_match`, dismissed for role or
seniority is `not_suitable`, and location, salary or other dismissals keep their reason with
no fit label. Undoing an action removes its label; labels edited by hand are never replaced.
Job IDs use the same formula as the earlier datasets. The folder is git-ignored and private.
