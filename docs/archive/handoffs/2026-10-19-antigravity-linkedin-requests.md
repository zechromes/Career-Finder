# 2026-10-19 — Antigravity — LinkedIn request reduction

- Tool/model: Antigravity, Claude Opus (Low). Branch: none (workspace is not a git repository).
- Objective: fewer LinkedIn requests and faster collection (user-requested items 1–4).

## Changed paths
- `backend/search/collection.py`: LinkedIn joins Indeed/Glassdoor shared board budget;
  `fetch_description` disabled for LinkedIn; 429 observer stops remaining LinkedIn
  searches; collection cache policy bumped to `collection-v8-linkedin-screen`.
- `backend/search/linkedin_details.py` (new): title screen, description cache, detail fetch, 429 stop.
- `backend/paths.py`: `LINKEDIN_DESCRIPTION_CACHE_DIR`.
- `tests/test_linkedin_requests.py` (new); `tests/test_description_capture.py` updated to new contract.
- `docs/job-search-providers.md`: documented flow and settings.

## Checks
- `./scripts/check.sh`: pass (175 Python tests, 54 frontend tests, build). Mocked only; no live LinkedIn calls.

## Unresolved
- Evaluation manager: title screening can drop relevant jobs before descriptions are read.
  No labeled baseline/proposed comparison has been run (`scripts/measure_matching.py`).
- Detail fetch uses LinkedIn public job pages and JobSpy's markdown helpers; page layout changes would yield empty descriptions.
