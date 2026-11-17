# Development

Setting up, running, configuring and checking Career Tracker. How the system works
is in [Architecture.md](Architecture.md). Agent and contributor working rules are in
[AGENTS.md](../AGENTS.md).

## Setup

Requirements: Python with the backend dependencies (locally the `job-tracker` conda
environment), Node.js with npm, and Tesseract for scanned PDFs
(`brew install tesseract`, or `sudo apt-get install tesseract-ocr`; add language
packs and set `OCR_LANGUAGES` for non-English resumes).

```bash
conda activate job-tracker
python -m pip install -r backend/requirements.txt
python -m pip install -r requirements-dev.txt   # black
cp .env.example .env                            # first install only; add keys
./run_app.sh
```

`run_app.sh` starts the API on http://127.0.0.1:5000 and Vite on
http://localhost:5173 (open it yourself), installing frontend dependencies if
needed. It uses the `job-tracker` conda environment when present, else the active
`python`; set `PYTHON_BIN` to override. Ctrl+C stops both. Restart after backend or
`.env` changes. Swagger UI: http://127.0.0.1:5000/docs.

Run the backend alone with
`python -m uvicorn backend.app:app --host 127.0.0.1 --port 5000`, always with one
worker. `frontend.app:app` and `python run_application.py` remain as compatibility
entry points; prefer `backend.app:app` and `python -m backend.cli`.

## Configuration

All settings are environment variables (see `.env.example`). Restart the backend
after changing them. Never commit `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | Fallback only; set in **Settings** instead (see README). Upload, requirements, GPT, embeddings, HyDE |
| `ANTHROPIC_API_KEY` | — | Fallback only; set in **Settings** instead. Claude evaluation, tailored resume |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | — | Fallback only; set in **Settings** instead. Gemini evaluation (or Vertex AI auth) |
| `SERPAPI_API_KEY` | — | Google Jobs board |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | — | Adzuna board |
| `ADZUNA_MAX_REQUESTS` | 2 | Adzuna requests per search |
| `OPENAI_PROFILE_MODEL` | `gpt-6.1-sol` | Profile extraction, HyDE ads |
| `OPENAI_UPLOAD_MODEL` | profile model | Upload override |
| `OPENAI_RESUME_CHECK_MODEL` | — | Standalone compatibility validator |
| `REQUIREMENT_EXTRACTION_MODEL` | `gpt-4o-mini` | Shared requirements |
| `CLAUDE_EVALUATION_MODEL` | `claude-sonnet-5-5` | Claude evaluator and tailored resume |
| `GPT_EVALUATION_MODEL` | `gpt-6.1-sol` | GPT evaluator |
| `GEMINI_EVALUATION_MODEL` | `gemini-4-argon` | Gemini evaluator |
| `{CLAUDE,GPT,GEMINI}_EVALUATION_WORKERS` | 4 / 4 / 2 | Concurrent jobs per provider (cap 8) |
| `GPT_EVALUATION_TIMEOUT_SECONDS` | 180 | 30–600 |
| `GEMINI_EVALUATION_RPM` | 0 | Proactive pacing; 0 = off |
| `CAREER_EVALUATION_PREFLIGHT` | true | Model availability check |
| `EVALUATION_PROVIDER` | `claude` | Legacy default reported by `/api/config`; web searches use every available model |
| `QUERY_BUILDER` | `hyde` | `hyde`, `evidence`, `skills`, `legacy` |
| `RETRIEVAL_WEIGHTS` | — | JSON override of retrieval weights |
| `JOB_SEARCH_PROVIDER` | `jobspy` | `adzuna` selects the legacy/CLI path |
| `JOB_COLLECTION_MAX_BATCHES` / `_DETAILS` / `_CANDIDATES` / `_SECONDS` | 12 / 60 / 150 / 240 | Adaptive budgets |
| `JOB_COLLECTION_CACHE_TTL_SECONDS` | 900 | 0 disables the collection cache |
| `JOB_COLLECTION_CACHE_MAX_ENTRIES` | 256 | Max 4,096 |
| `JOBSPY_DESCRIPTION_CACHE_TTL_SECONDS` | 604800 | 0 disables description reuse |
| `JOBSPY_SCREEN_POOL_FACTOR` | 3 | Fixed (CLI) collection only, 1–5 |
| `JOB_SEARCH_MAX_WORKERS` | 4 | Fixed (CLI) collection only, max 8 |
| `OCR_LANGUAGES` | `eng` | Tesseract languages |
| `CAREER_LANGSMITH_TRACING` and `LANGSMITH_*` | off | See below |

Cache directories can be moved with `JOB_COLLECTION_CACHE_DIR`, `JOB_INDEX_DIR`,
`JOB_EMBEDDING_CACHE_DIR` and `JOBSPY_DESCRIPTION_CACHE_DIR`; defaults come from
[paths.py](../backend/paths.py).

## Checks

```bash
./scripts/check.sh          # standard verification
./scripts/check.sh --e2e    # plus Playwright browser workflows and axe checks
```

`check.sh` uses the same Python selection as the launcher and stops if dependencies
are missing. It runs the Python tests with tracing, the availability check and live
HyDE calls off (`QUERY_BUILDER=evidence`), regenerates `frontend/openapi.json` and
`frontend/src/types/api.d.ts`, then runs Vitest, the legacy Node tests and the
production build (which type-checks). Install Chromium once for `--e2e`:
`cd frontend && npx playwright install chromium`.

Tests use synthetic data and mocked providers. They prove software behavior, not
live provider availability or matching accuracy. Live provider calls need explicit
authorization.

## Frontend

From `frontend/`:

```bash
npm ci
npm run dev:mock     # MSW mock API: no keys, no paid calls
npm run typecheck
npm test             # Vitest + Vue Test Utils
npm run test:legacy
npm run test:e2e     # Playwright, mocked
npm run build
```

Mock scenarios (`zero`, `scrape-failure`, `polling`) are chosen with the
`mock-scenario` sessionStorage key. MSW loads only with `VITE_MOCK_API=true`.

**API contracts.** Pydantic models in `backend/schemas/` are the source of truth.
After changing them, regenerate (`check.sh` does it, or `npm run types:generate`
with the project Python) and commit both `frontend/openapi.json` and
`frontend/src/types/api.d.ts`. Never edit the generated files by hand.

Main state lives in `stores/pipeline.ts` (API, SSE, polling), `stores/profile.ts`
(profile and preference draft), `stores/jobs.ts` (job actions and sync),
`stores/resultsView.ts` (page/filter/sort per workspace) and `stores/snackbar.ts`.

## Formatting

```bash
black backend tests scripts integrations frontend/app.py frontend/scripts run_application.py
npm --prefix frontend run format        # or format:check
```

Generated contracts, dependencies, saved data and build output are excluded.

## Code layout

```text
backend/        app.py, routers/, schemas/, profiles/, search/, evaluation/,
                runs.py, runs_api.py, exports.py, paths.py, cli.py, observability.py
frontend/       Vue app (src/), tests/, e2e/, openapi.json
scripts/        check.sh and maintenance tools
integrations/   Optional Google Sheets MCP server
tests/          Python regression tests
docs/           These guides, images/, benchmarks/, handoffs/, archive/
```

Import Python modules as `backend.profiles.*`, `backend.search.*`,
`backend.evaluation.*`, `backend.schemas.*`; use `backend/paths.py` for paths.
Routers stay thin and delegate to handlers; no module imports `backend/app.py`.

## Maintenance scripts

Run from the project root.

| Command | Purpose |
| --- | --- |
| `python -m backend.cli --help` | Command-line pipeline (single evaluation provider) |
| `python -m scripts.measure_matching labels.json` | Recall@K, strong-match precision and label coverage on human labels |
| `python -m scripts.compare_query_builders <run_id>` | Replay a saved run under all four query builders (live embeddings; prints private run data, keep it local) |
| `python -m scripts.benchmark_retrieval --documents 5000 --dimensions 1536 --queries 30 --k 20 --seed 42 --ef-search 500 --output /tmp/out.json` | Synthetic index benchmark |
| `python -m scripts.recover_excluded_jobs --help` | Recover excluded jobs |
| `python -m scripts.load_chroma` | Needs a Chroma server on localhost:8000 |
| `python -m integrations.sheets_mcp_server` | Optional Sheets MCP; uses a service-account file in `Credentials/` |

### Measuring matching quality

`measure_matching` takes an array of labeled pools:

```json
[{"query_id": "profile-001", "pool": ["job-a", "job-b", "job-c"],
  "labels": {"job-a": true, "job-b": false, "job-c": true},
  "shortlist": ["job-a", "job-b"], "predicted_strong": ["job-a"]}]
```

It reports recall over labeled positives, precision over labeled strong
predictions, unlabeled counts, missed positives and a random sample from outside
the shortlist to label next. With partial labels this is *observed* recall, not
full-pool recall. Compare baseline and proposal on the same labels, keep tuning
and held-out profiles separate, and never use a model to create the ground truth.
The job-action dataset (`data/evaluation_datasets/`) is a source of labels.

## LangSmith tracing

```dotenv
CAREER_LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-key
LANGSMITH_PROJECT=career-tracker
LANGSMITH_ENDPOINT=https://api.smith.langchain.com   # match your region
LANGSMITH_TRACING=false                              # not needed
```

Restart the backend, run an upload or search, and open the project in LangSmith;
the backend log prints a random trace ID per root operation. Missing credentials
just disable delivery. Delivery is best effort, so a killed process can lose
pending traces. What is traced and what is never exported:
[Architecture.md](Architecture.md#12-observability).

## Data on disk

`frontend/runs/`, `data/`, `.cache/`, `vector_db/`, root CSV/text exports from the
old CLI, `Files/` and `Credentials/` are git-ignored and private. Code changes and
tidying never move or delete them. Remove caches only with the backend stopped,
and restart before the next search.
