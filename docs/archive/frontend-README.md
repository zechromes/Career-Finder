# Career Tracker web application

Vue 3 + TypeScript + Vue Router + Pinia, backed by FastAPI. Upload a PDF, correct the extracted profile, confirm search preferences, and review results as each assessment completes. Fresh opens and saved URLs start at `/`; browser refreshes retain the current page. Navigate through saved profiles to reopen work; SSE updates are backed by snapshot polling. Job actions are local to the browser.

## Run

Use the project's Python environment (locally: `conda activate job-tracker`), then install `pip install -r backend/requirements.txt` and run `./run_app.sh`. The server is designed for one Uvicorn worker: active threads and cancellation flags are process-local. Do not deploy multiple workers without a shared job queue and state store.

For scanned PDFs install Tesseract: `brew install tesseract` on macOS or `sudo apt-get install tesseract-ocr` on Debian/Ubuntu. English OCR runs locally, without sending page images to another service. Set `OCR_LANGUAGES` and install the matching language packs for additional languages. PDFs must be non-empty, valid, at most 5 MB and 20 pages. Very large page dimensions and encrypted/unreadable files are rejected before model calls.

Resume extraction uses OpenAI only, with no provider selector; job evaluation automatically runs Claude, GPT and Gemini. The upload page displays “Powered by OpenAI”; the automatic evaluation summary fetches model labels from the API. See `.env.example` for overrides. Claude evaluation uses native JSON-schema output and omits unsupported sampling overrides. The Sonnet default was verified against [Anthropic's model documentation](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).

## API and data

![Technical application workflow](../docs/images/application-workflow.png)

- `POST /api/resumes/upload`: validated PDF upload; waits for extraction, then returns HTTP 201 with `id` and `runId`. The snapshot contains the ready profile or extraction error.
- `GET /api/searches/{id}`: typed snapshot; `GET /api/searches/{id}/progress`: SSE.
- `PUT /api/searches/{id}/confirm-profile`: edited profile and preferences; starts search.
- `POST /api/searches/{id}/cancel`: cooperative cancellation; completed data is retained.
- `POST /api/searches/{id}/retry-scraping`: retries identified failed boards directly with confirmed inputs, appending unique results. JobSpy retries can start immediately after a rate limit. Historical generic warnings retry the selected board scope.
- `POST /api/searches/{id}/retry-evaluations`: retries saved failures only, without scraping again.
- `DELETE /api/searches/{id}`: deletes run data; an active worker defers physical deletion until in-flight calls finish. The run is immediately inaccessible.
- Legacy `POST /api/searches/{id}/find-jobs` remains available.

Retry failed evaluations shows a spinner and status text while the request is
submitted and while the retry runs. The button is disabled during submission or
active work; request errors restore the action and remain visible.

Job actions show a shared snackbar for copying links, saving, dismissing and
marking jobs as applied, including reversed actions. Notifications last five
seconds, replace the previous message, and can be dismissed manually. Clipboard
failures keep a manual-copy field available; persistence and sync errors remain
visible in the existing error state.
Job action menus preserve pointer clicks when focus moves without a new focused
button, and ignore delayed scroll events from bringing the menu trigger into view.
Job actions remain available during evaluation. Dismiss opens an optional reason dialog;
feedback can lower future shortlist priority and is reversible through restoring the job
or the Dismissal preferences panel. See [behavior and matching limits](../docs/dismissal-preferences.md).
 A delayed synchronization response
cannot overwrite an action whose save completed while that response was in flight.

SSE publishes `phase_update`, `profile_extracted`, `scrape_progress`, `job_evaluated`, `run_completed`, and `run_failed`. Snapshots are authoritative and repair missed events. Results retain snake-case fields for compatibility and expose camel-case aliases for the example event contract. Numeric fit scores are assessments, not calibrated probabilities. Historical scores remain unknown. Postings are always `unverified`: the application does not claim to check live availability.

Run data lives under `frontend/runs/{id}`. Retention is 7 days; cleanup occurs on the next request or server startup. The deletion API can remove data sooner; the final results view offers Upload new resume. The app has no accounts: treat run URLs as private capabilities. See `/privacy` for provider sharing and deletion behavior. Requests that start work are rate-limited to 30 per minute per client address.

The semantic shortlist defaults to 50 jobs; choose 15, 100 or all retrieved jobs in Profile Review.

Successful searches automatically save the profile, preferences, and available PDF;
continued workspaces update their saved profile. Save failures leave results intact.
Seniority defaults to automatic early-career preference; explicit All levels or
specific levels override it. Previously saved `any` preferences remain All levels.

Specific work-type filters require matching text in the posting; specific seniority filters require a matching title term. Exclusions match title/company text. Empty/unrecognized fields are not inferred. A new search reuses the confirmed profile, publishes an eligible posting scope in the shared index, and can make new paid requests. Partial scrape failures retain other sources' results.

## Development and verification

From `frontend/`:

```sh
npm ci
npm run dev:mock        # MSW browser fixtures; no credentials or paid calls
npm run types:generate # use the project's Python environment
npm run typecheck
npm test               # Vitest + Vue Test Utils
npm run test:legacy    # existing regression checks
npx playwright install chromium
npm run test:e2e       # MSW-backed browser flows and axe accessibility checks
npm run build
```

From the project root: `python -m unittest discover -s tests`. Tests include an actual scanned PDF through Tesseract when installed. CI runs OCR, contract regeneration, unit/component tests, browser tests, and accessibility checks. The mock supports `zero`, `scrape-failure`, and `polling` scenarios using the `mock-scenario` sessionStorage key.

`backend/contracts.py` and `ResumeProfile` generate OpenAPI; `openapi-typescript` generates `src/types/api.d.ts`. Regenerate after changing API schemas and commit both generated files. MSW is loaded only with `VITE_MOCK_API=true`; production builds omit it.

### Focused embedding inputs

Retrieval embeds headline, summary, technical skills, preferred domains and the three most recent work entries (dated roles first; original order breaks ties). Name, soft skills, education and explicit experience/career-level fields are omitted from the query. These fields remain available to candidate-fit evaluation. Free-text summaries and work entries are not anonymized or rewritten.

Job vectors contain the title and description with recognized company-introduction, benefits, legal and application sections removed. Company and location stay in metadata. Cleaning is deterministic and heading-based, so unusual or unstructured boilerplate may remain. Original postings are retained in metadata and restored after retrieval for evaluation; degree and experience requirements remain available.

New web searches reuse a shared versioned posting index with per-search eligibility scopes. Legacy vector stores remain readable. CLI profile vectors remain separate. See [shared posting indexing](../docs/shared-job-index.md).

### Hybrid retrieval and evidence scoring

New requirement assessments use source sections from the shared posting extraction.
Historical requirements are grouped under Qualifications, Responsibilities and Nice
to have when their quotes match recognized headings in the posting. Ambiguous matches or
unrecognized sections appear under Other requirements. Each section has its own
Previous/Next navigation. Each selected model's requirement includes its verdict,
explanation and supporting posting/resume quotes. There is no additional Model
feedback section. Unverified resume quotes are labeled explicitly.

Selected-role, skills and recent-experience queries now contribute semantic and BM25 rankings, merged with reciprocal rank fusion. Job embeddings use a model/content-hash cache. Evaluation scores are computed from quoted requirement verdicts, with source verification and explicit unknown handling; the model's numeric score is ignored. The API retains each model’s assessment; the job details page compares verdicts and supporting evidence.

See [matching improvements and proposal review](../docs/matching-improvements.md) for the scoring rubric, cache behavior, limitations, deferred proposals and human-label measurement workflow. Start a new search to use the new ranking and scoring behavior.

The active frontend uses `stores/pipeline.ts`, `JobDashboard.vue`, and
`ApplicationStepper.vue`. Superseded standalone search-store, results-helper, and
progress-component implementations and their dedicated tests have been removed.

Application startup opens `/` for fresh opens and direct URLs. Browser refreshes retain the current page.
Navigation after startup works normally. This does not delete saved profiles or results.

Saved resumes offers Grid and Table views. The selected view is remembered in browser storage; both layouts support editing, continuing, starting a new search, PDF download and confirmed deletion.

### Returning from job details

Results retain their selected page, filters and sort order per workspace while
navigating within the app. Back to results and browser Back restore that view in
both grid and table modes. The visible page is bounded when the result count
changes; temporary empty snapshots do not erase the saved position. Changing a
filter or sort still starts at page 1. This view state stays in memory and resets
on a full browser reload; it does not change saved jobs or server data.

The results table includes a Status column showing all active Applied, Saved and
Dismissed flags. Jobs with no flags show No status. Dismissed jobs remain under
the Dismissed filter; the Actions menu changes these flags.

### Experiment page

`/eval` supports direct visits and refreshes, with model selection, dataset labels,
progress, cancellation and JSON export. Its settings are independent of normal
searches. See [evaluation experiments](../docs/evaluation-experiments.md).

`/eval/datasets/:datasetId` provides frozen-evidence review with separate persistent
human labels, quality metrics, revision-checked saves and JSON export. A guided
fit-first flow includes examples, optional requirement/evidence review steps, and
partial-review saving. See the
[human evaluation guide](../docs/human-evaluation-datasets.md).
