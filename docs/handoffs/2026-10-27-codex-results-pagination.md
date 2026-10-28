# Preserve results page after detail navigation

- Objective: keep the chosen result page when returning from job details.
- Tool/model: Codex / GPT-6 session; no Git repository/branch available. Frontend-engineer and test-engineer skills applied.
- Changed: frontend/src/stores/resultsView.ts (new), frontend/src/components/JobDashboard.vue, frontend/tests/components.spec.ts, frontend/e2e/workflow.spec.ts, frontend/README.md.
- Cause: dashboard pagination/filters were local refs discarded when the details route unmounted the dashboard.
- Fix: retain page, filters and sorting in per-workspace Pinia state. Bound the displayed page without deleting the requested page during temporary empty snapshots or action synchronization. User filter/sort changes still reset to page 1. Grid/table preference remains on the existing path. No API or backend behavior changes.
- Checks: standard scripts/check.sh passed (249 Python tests, 76 frontend tests, legacy, generated contracts, typecheck and build). Two mocked Chromium scenarios passed: grid/table return via Back to results and browser Back retains page 3, search text and the selected job. Component coverage also verifies remount, empty-then-loaded data, workspace isolation, shrinking page counts and filter reset.
- Limits: results-view state is in memory; a full browser reload starts with defaults. No live providers or private data used. No claim of scroll-position restoration.
- Next: reload the frontend once to load this fix; subsequent results/detail navigation preserves pagination. No backend restart needed.
