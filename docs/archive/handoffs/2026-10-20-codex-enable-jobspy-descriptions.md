# Enable JobSpy descriptions

- Objective: set fetch_description=True as explicitly requested.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: `backend/search/collection.py`; four affected collection/description test files; README and provider guide.
- Behavior: all JobSpy searches request descriptions directly from JobSpy. Collection cache policy bumped to v11 so old entries cannot mask the setting. Inline descriptions are reused; existing cache/fallback behavior remains for missing text. SEEK's separate staged collector is unchanged. JobSpy internal per-posting calls occur before application screening and are outside the fallback-detail budget; 429s remain possible.
- Validation: standard check passed: 201 backend, 60 frontend, 1 legacy test, contract generation and build. Updated tests assert the explicitly requested flag. No live provider calls or browser rerun for this backend-only setting change.
- Skills: backend-engineer and test-engineer. No remaining work.
