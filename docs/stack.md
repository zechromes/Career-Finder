# Tech stack

What Career Finder is built with, where each piece is used, and why it was
chosen. Exact versions live in [backend/requirements.txt](../backend/requirements.txt)
and [frontend/package.json](../frontend/package.json); how the pieces fit together
is in [Architecture.md](Architecture.md), and the history behind the choices is in
[DECISIONS.md](DECISIONS.md).

## Backend (`backend/`)

| Area | Technology | Why |
| --- | --- | --- |
| Language | Python (conda env `job-tracker`) | The LLM, PDF, scraping and data libraries below are all Python-first. |
| API server | FastAPI on Uvicorn, port 5000 | Pydantic models double as the API contract: FastAPI turns them into the OpenAPI schema the frontend's types are generated from. Runs as **one Uvicorn worker** because active runs, locks and cancellation flags live in process memory; work is still concurrent through thread pools. |
| Schemas | Pydantic models in `backend/schemas/` | One definition validates requests, model outputs (strict JSON schemas) and saved files. |
| LLM access | LangChain: `langchain-openai`, `langchain-anthropic`, `langchain-google-genai` | One interface (`with_structured_output`, retries, timeouts) for all three evaluation providers, so they answer the same prompt and schema and can run side by side. `langchain-mistralai` is still installed but no code uses it. |
| Vector index | Chroma (`langchain-chroma`) with OpenAI `text-embedding-3-small` | Local and file-based (no database server) with persistence and recovery. Metadata filters restrict retrieval to each search's posting versions in the shared index. Replacing it with NumPy was rejected: no relevance gain and it would lose persistence. HNSW `ef_search=500` after a benchmark showed 92% recall@20 at 100 and 100% at 500. |
| Lexical ranking | In-house BM25 (`backend/search/ranking.py`) | Dense embeddings capture meaning but can miss exact terms (tool and skill names); BM25 catches them. The two rankings are fused with reciprocal rank fusion. The index is small enough to keep in-house. |
| Resume reading | pdfplumber (renders pages through pypdfium2 and Pillow); Tesseract OCR for scanned PDFs | Text and OCR run locally, so page images are never sent to another service; only the extracted text goes to OpenAI. OCR runs only on pages with almost no text layer. |
| Job collection | python-jobspy (LinkedIn, Indeed), direct SEEK collection, BeautifulSoup; optional SerpApi (Google Jobs) and Adzuna | JobSpy needs no account or API key (it replaced the paid Apify collector). JobSpy doesn't cover SEEK, so SEEK has its own rate-limited collector. LinkedIn descriptions are fetched by the app itself with a 2 s gap because JobSpy's back-to-back requests drew HTTP 429s. BeautifulSoup parses those SEEK and LinkedIn pages. SerpApi is paid per page and Adzuna needs registration, so both are opt-in. |
| Excel export | pandas, openpyxl | Results export to `.xlsx` for use outside the app. |
| Tracing (optional) | LangSmith | Stage timings and token counts for debugging latency and cost. Counts only: prompts, resumes and postings are never sent. Off by default. |
| Config | python-dotenv, `.env` (see `.env.example`); model API keys on the Settings page | `.env` holds non-secret tuning (model IDs, limits, caches). Model API keys are entered in Settings, verified with the provider before saving, and stored in `data/api_keys.json`. |

## Models

Model IDs are backend configuration in `.env`; see `.env.example` for the
current defaults.

| Job | Provider | Why |
| --- | --- | --- |
| Resume extraction | OpenAI (`OPENAI_PROFILE_MODEL`, optional `OPENAI_UPLOAD_MODEL`) | One call classifies the document and extracts the profile, using a strict JSON schema. |
| Requirement extraction | OpenAI (`REQUIREMENT_EXTRACTION_MODEL`) | Runs once per posting without the resume, so every evaluator answers the same requirements and their verdicts can be compared. A small model keeps the per-posting cost low. |
| Candidate-fit evaluation | Claude, GPT or Gemini (`EVALUATION_PROVIDER`) | Three independent providers make disagreement visible instead of trusting one model; each can be switched off when unavailable. |
| HyDE retrieval queries | OpenAI (`OPENAI_PROFILE_MODEL`) | Model-written job ads for each target role match posting language better than bare role titles. Cached with no expiry. |
| Embeddings | OpenAI `text-embedding-3-small` | One embedding per posting version, cached by model, so cost stays low as the shared index grows. |

## Frontend (`frontend/`)

| Area | Technology | Why |
| --- | --- | --- |
| Framework | Vue 3 with TypeScript | Typed components consume the generated API types, so contract changes fail the build instead of breaking at runtime. |
| Build / dev server | Vite, port 5173 | Fast dev server, with a proxy to the API during development. |
| State | Pinia | Run polling, profile and job-action state are shared across views and kept when moving between results and job details. |
| Routing | Vue Router | Every run, results view and job detail tab has a URL that can be reloaded or shared. |
| Styling | Tailwind CSS (PostCSS, Autoprefixer) | Shared primitives (`.panel`, `.btn-primary`, …) in `style.css` plus utilities, with a built-in dark mode. |
| Icons | Heroicons | Matches Tailwind's look; components are imported individually, so only the icons used are bundled. |
| API types | Generated from FastAPI's OpenAPI schema with `openapi-typescript` into `src/types/api.d.ts` (do not edit by hand) | The backend's Pydantic models stay the single source of truth for the contract. |
| Mock API | MSW (`npm run dev:mock`) | Develop and run browser tests with no API keys and no paid calls. Production builds leave it out. |

## Storage

No database server. State is JSON and other files on disk (`frontend/runs/`,
`data/profiles/`), caches under `.cache/`, the Chroma index in
`.cache/job_index/`, and per-browser `localStorage`. Why: it's a single-user app
on one machine, and plain files are easy to inspect, back up and delete when
private data must go. Locations and lifetimes are listed in
[Architecture.md §9](Architecture.md#9-storage-and-caches).

## Testing and tooling

| Area | Technology | Why |
| --- | --- | --- |
| Python tests | `unittest` (`tests/`) | Standard library, so the tests need no extra dependency. External services are mocked. |
| Frontend unit tests | Vitest, Vue Test Utils, jsdom | Shares Vite's config and TypeScript handling. |
| Browser tests | Playwright with axe-core accessibility checks | Runs full workflows against MSW and fails on accessibility violations. |
| Formatting | Black (Python), Prettier (frontend) | Consistent formatting with no style debates in review. |
| Type checking | `vue-tsc` | Type-checks `.vue` files, which `tsc` alone can't. |
| All checks | `./scripts/check.sh` (add `--e2e` for browser tests) | One command runs tests, contract regeneration and the build in the right order. |
| Launcher | `./run_app.sh` starts backend and frontend | One command to start both services and stop them together. |

## Optional integration

`integrations/sheets_mcp_server.py` is an MCP server (FastMCP + gspread) that
logs applied jobs to Google Sheets. It's an MCP server so an AI assistant can call
it as a tool; it's kept outside `backend/` so the app runs without it.
