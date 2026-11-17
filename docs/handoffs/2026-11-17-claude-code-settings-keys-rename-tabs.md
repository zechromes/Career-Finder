# Settings API keys, Career Finder rename, segmented tabs

- Tool/model: Claude Code, claude-opus-5-5. Branch: improve-seniority-matching (uncommitted).
- Objective: store and validate provider API keys from a Settings page; rename the
  user-facing app to Career Finder; redesign tabs.

## Changed
- `backend/api_keys.py`, `backend/routers/api_keys.py`, `backend/schemas/contracts.py`
  (`ApiKeyInput`, `ApiKeyStatus`), `backend/paths.py` (`API_KEYS_FILE` = `data/api_keys.json`,
  mode 0600), `backend/app.py` and `backend/cli.py` call `api_keys.load()`.
- Routes: `GET /api/settings/keys`, `PUT|DELETE /api/settings/keys/{openai|anthropic|google}`.
  PUT verifies with the provider's list-models endpoint (no tokens spent) before saving; 422 on
  rejected key, 502 when unreachable. Keys are never returned, only the last 4 characters.
- Saved keys override `.env`; removing one restores the `.env`/shell value.
- `frontend/src/views/SettingsView.vue`, `/settings` route, header link, MSW handlers.
- `frontend/src/components/Tabs.vue` (segmented pills, roving focus) used by JobDetailView and
  both EvalView tab strips.
- Rename: header, footer, `<title>`, FastAPI title, README, PRD, `run_app.sh` messages.

## Checks
- `./scripts/check.sh`: pass (includes new `tests/test_api_keys.py`).
- `npm run test:e2e`: 35 pass, 1 fail (`workflow.spec.ts:342`, evaluation evidence). Also fails
  with the HEAD JobDetailView, so it predates this change (uncommitted EvaluationEvidence edits).

## Open
- Mistral (resume model option), SerpApi, Adzuna and LangSmith keys still come from `.env` only.
- Next: frontend/evaluation owner for the failing e2e test.
