# Consolidated rate-limit warnings

- Objective: explain and fix repeated LinkedIn rate-limit warnings from one collection.
- Tool/model: Codex / GPT-6 session; branch unavailable (not a Git repository).
- Changed: `backend/search/collection.py` deduplicates rate-limit causes per board across batches; `jobspy_details.py` suppresses missing-description warnings caused by the same pause; `board_cooldown.py` explicitly dates cooldown information to the search, avoiding a misleading saved countdown. Provider documentation and `tests/test_jobspy_details.py` updated.
- Contracts: no API changes. Preserve one actionable warning and partial results. Existing saved run warnings are not rewritten. No provider bypass, automatic retries or cooldown reduction.
- Verification: standard check passed: 199 backend, 60 frontend, 1 legacy test, contract generation and production build. One mocked browser failure/recovery check passed. New integration regression proves one detail call and one warning across multiple LinkedIn batches after a 429; existing cache/cooldown tests pass. No live provider calls.
- Skills: backend-engineer and test-engineer under `agents/skills/`.
- Remaining limitations: the app cannot guarantee LinkedIn acceptance after its local cooldown. Historical result warnings remain valid records of incomplete searches; a new search resets run warnings and checks cooldown again. No remaining implementation work for this fix.
