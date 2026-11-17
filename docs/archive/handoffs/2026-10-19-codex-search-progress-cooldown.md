# Search progress and repeated rate-limit handling

- Tool/model: Codex / GPT-6 session. Branch: unavailable (workspace has no Git repository).
- Objective: show a frontend loading bar with descriptive text; prevent immediate new JobSpy requests after a reported 429.
- Changed: `ApplicationStepper.vue`, collection/service/detail status callbacks, new `backend/search/board_cooldown.py`, related Python/component/browser regressions, README, provider guide and `.env.example`.
- Contract: optional internal `on_status` callbacks feed the existing run `message` field; no public schema changes. Collection and matching remain indeterminate, evaluation uses measured settled-job counts. Terminal states stop loading; reduced-motion and accessible labels are supported.
- Cooldown: per-board, process-wide default 600 seconds after explicit HTTP 429. Skip new search/detail requests during the pause while permitting cache reads and other boards. No automatic retry or bypass. Existing warnings are historical snapshots; restarting clears the in-memory pause. In-flight requests can finish.
- Checks: standard project check passed: 187 backend tests, 60 frontend tests, one legacy compatibility test, production build. Five affected mocked browser workflows passed, including desktop/mobile accessibility and cancellation/error recovery. No live model or board calls.
- Limits: no ETA or collection-wide percentage is invented; simultaneous board status updates can alternate. Cooldown duration is a local policy, not a confirmed provider reset time. No scoring or matching-policy changes.
- Next owner: none required. Restart the backend to load these changes; do not interpret old saved warning text as a new request.
