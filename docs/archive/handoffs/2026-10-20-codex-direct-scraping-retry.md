# Direct scraping retry

- Objective: make Retry scraping start failed-source collection without reopening profile review or replacing results.
- Tool/model: Codex / GPT-6 session; no branch (workspace is not a Git repository).
- Changed: `backend/search/service.py`, `backend/routers/searches.py`; frontend RunView, pipeline store, mocked handlers; backend incremental-search tests and browser workflow test; README and frontend README; generated frontend OpenAPI and API types.
- Contract: POST `/api/searches/{run_id}/retry-scraping`, no body, returns 202 RunCreated. Reuses stored confirmed preferences/profile and append lifecycle. Failed boards are identified from existing warning prefixes; historical generic warnings fall back to the selected board scope. Stored board preferences remain intact. Returns 409 for active work, missing profile, no failed searches or all failed boards cooling down. Existing collection guards skip individual cooling-down sources if others can proceed. No automatic retries.
- UI: Retry scraping calls the new endpoint in place, disables while submitting, and displays request errors. Removed redundant review action when source-error retry is available. Review/Find more remains separately accessible.
- Validation: standard check passed: 201 backend, 60 frontend, 1 legacy test, generated contracts and production build. Four mocked browser checks passed, including direct retry without profile review and existing-result retention. No live provider calls.
- Skills: frontend-engineer, backend-engineer, test-engineer under `agents/skills/`.
- Limitations: older source-less failures cannot target a specific board. Provider cooldown expiration does not guarantee acceptance. No remaining implementation work.
