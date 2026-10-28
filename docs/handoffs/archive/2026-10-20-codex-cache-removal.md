# Cache removal

- Tool/model: Codex / GPT-6; no Git branch available.
- Objective: remove all persisted application caches as requested.
- Removed: 11 existing cache locations, 893 files, 29.2 MiB: application .cache data, private assessment caches and legacy run vector indexes where present. Configured cache directory overrides were checked.
- Preserved: saved profiles, resumes, run history, assessments and exports.
- Verification: no targeted cache locations remained immediately after removal. Data-only maintenance; application tests not needed.
- Limitation: a running backend can hold in-memory cache or recreate files. Browser storage and development dependencies were not changed. Restart backend before next search to discard process-local cache state.
- Remaining work: none.
