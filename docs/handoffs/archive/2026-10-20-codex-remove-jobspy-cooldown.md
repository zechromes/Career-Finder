# Remove timed JobSpy cooldown

- Objective: allow immediate manual retry after LinkedIn rate limiting.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: backend search cooldown compatibility helpers, collection-local blocked-board tracking and retry service; regression tests; README, frontend/provider guides and environment example.
- Behavior: LinkedIn/Indeed/Glassdoor no longer store/enforce cross-search cooldowns. Retry scraping no longer returns a cooldown 409. Adaptive collection tracks blocked boards locally so a new 429 still stops subsequent searches/details in that collection; cached text and other sources remain usable. Existing profiles/results and active-worker guards remain. SEEK's independent collector backoff is unchanged.
- Validation: standard check passed: 201 backend tests, 60 frontend tests, 1 legacy test, contract generation and build. Tests cover immediate new searches, immediate retry, per-collection single-429 behavior and retained results. No live provider calls; browser tests were not rerun for this backend-only behavior change.
- Skills: backend-engineer and test-engineer. No remaining implementation work; actual provider acceptance cannot be guaranteed.
