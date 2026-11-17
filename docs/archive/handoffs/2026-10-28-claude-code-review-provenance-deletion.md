# AI-assisted review flag and review dataset deletion

- Objective: items 2 and 3 of the PRD alignment review: keep AI-assisted labels out of human metrics, and let users delete review datasets.
- Tool/model: Claude Code, Claude Opus 5.5. Branch unavailable: no Git repository.
- Skills: backend-engineer, frontend-engineer, test-engineer, evaluation-manager (all under agents/skills/).
- Contract: `JobReview.ai_assisted: bool = false` (stored reviews without it load as human). `ReviewMetrics.ai_assisted_reviews: int` counts excluded reviews; `fit_reviewed` and all retrieval, extraction and evidence metrics now use non-assisted reviews only. `DELETE /api/review-datasets/{id}` returns `{deleted: true}`, 404 when missing; removes dataset.json and reviews.json only.
- Changed: backend/schemas/review_datasets.py, backend/evaluation/review_datasets.py, backend/routers/review_datasets.py; frontend/src/views/ReviewDatasetView.vue (checkbox, excluded count), frontend/src/components/ReviewDatasets.vue (inline delete confirmation), frontend/src/mocks/reviewDatasets.ts; regenerated frontend/openapi.json and src/types/api.d.ts; tests/test_review_datasets.py (+2), frontend/e2e/review-datasets.spec.ts (+2). Docs: human-evaluation-datasets.md, PRD.md FR-15, project-context.md.
- Also fixed: project-context.md relative links broken by its move out of docs/archive/; API reference links now point to frontend/openapi.json because docs/images/openapi.json is a stale 15 Oct export that nothing regenerates (file left in place).
- Checks: `./scripts/check.sh --e2e` passed: 267 Python tests, 79 frontend tests, legacy tests, build, 36 Playwright tests including the two new ones. Mocked providers only.
- Unresolved: whether to delete docs/images/openapi.json. The flag is self-reported; it cannot detect undisclosed AI help. Assisted reviews still count in the dataset list's "fit labels saved" progress figure.
- Next owner: evaluation manager, once human labels exist, to establish the labeled baseline (review item 1).
