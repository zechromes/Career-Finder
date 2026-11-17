# Career Finder

Upload a resume, check the extracted profile, search job boards, and see how well
each job fits, with every verdict backed by quotes from the posting and your
resume.

- **Vue 3** frontend, **FastAPI** backend.
- Jobs from LinkedIn, Indeed, SEEK, Google Jobs and Adzuna.
- Hybrid retrieval (OpenAI embeddings in Chroma + BM25).
- Each shortlisted job assessed independently by Claude, GPT and Gemini.

## Quick start

```bash
conda activate job-tracker                 # or any Python env with the deps
python -m pip install -r backend/requirements.txt
cp .env.example .env                       # first time: optional settings
./run_app.sh
```

Open http://localhost:5173. The API runs on http://127.0.0.1:5000 (Swagger at
`/docs`). Scanned resumes need Tesseract (`brew install tesseract`). Full setup,
configuration and checks: [DEVELOPMENT.md](docs/DEVELOPMENT.md).

### API keys

Model API keys are entered in the app, not in `.env`:

1. Open **Settings** in the top-right corner (or http://localhost:5173/settings).
2. Paste a key into each provider's field and press **Verify & save**. The key is
   checked with the provider first and saved only if it is accepted.

| Provider | Needed for | Get a key |
| --- | --- | --- |
| OpenAI | Resume upload, requirement extraction, embeddings, GPT evaluation (**required**) | https://platform.openai.com/api-keys |
| Anthropic | Claude evaluation, tailored resumes | https://console.anthropic.com/settings/keys |
| Google Gemini | Gemini evaluation | https://aistudio.google.com/apikey |

Keys are stored on this computer in `data/api_keys.json` (gitignored, readable only by
your user) and the page shows only the last 4 characters. **Remove** deletes a saved
key. A key set as an environment variable is still used when none is saved.

## Using it

1. **Upload** a PDF resume (≤ 5 MB, ≤ 20 pages). OpenAI extracts a profile.
2. **Review** the profile, then choose target roles, locations, boards, filters
   and shortlist size (Automatic by default).
3. **Search.** Boards are searched within a shared budget, jobs are ranked
   against your profile, and the shortlist appears right away while Claude, GPT
   and Gemini assess each job against the same requirement list.
4. **Read the results.** Each job shows the models' verdicts and, per requirement,
   met / partial / not met / unknown with quotes. If the models disagree, the job
   is marked For review.
5. **Act.** Save, Dismiss (optionally with a reason, which lowers similar jobs in
   future searches) or mark Applied. Generate a **Tailored resume** for a job: it
   reorders and rewords only what your resume already says, and flags anything
   to check before sending. Export to CSV or Excel.
6. **Continue.** Find more jobs, retry failed boards or evaluations, or reopen a
   saved resume later from **Saved resumes**.

The `/eval` page is a pipeline playground for running one stage on its own.

**Privacy.** There are no user accounts: anyone who can reach the server can see
saved resumes, so keep run URLs private. Runs expire after seven days; saved
resumes stay until you delete them. Resume and posting text are sent to OpenAI,
Anthropic and Google for extraction and evaluation. See the app's `/privacy` page.

**Limits.** Matching accuracy hasn't been measured on held-out human labels.
Postings are never checked for being still open. Board coverage depends on rate
limits and the collection budget.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/PRD.md](docs/PRD.md) | Product requirements and acceptance criteria |
| [docs/Architecture.md](docs/Architecture.md) | How the pipeline, storage and API work |
| [docs/stack.md](docs/stack.md) | Languages, frameworks, libraries and models used |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Setup, configuration, checks, scripts, tracing |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Dated decisions and rejected proposals |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Open work |
| [AGENTS.md](AGENTS.md) | Rules for coding agents and contributors |
| [docs/archive/](docs/archive/) | Superseded guides and old handoff notes |

API reference: [frontend/openapi.json](frontend/openapi.json).
