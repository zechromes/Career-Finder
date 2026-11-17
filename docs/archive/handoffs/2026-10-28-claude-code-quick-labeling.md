# Quick labeling and simpler eval page

- Objective: make /eval understandable and make building a labeled evaluation set fast (full per-job review of 158 jobs was impractical).
- Tool/model: Claude Code, Claude Opus 5.5. Branch unavailable: no Git repository.
- Skills: frontend-engineer, test-engineer, evaluation-manager (all under agents/skills/).
- Changed: frontend/src/components/QuickLabel.vue (new); frontend/src/views/ReviewDatasetView.vue (quick/detailed modes, `?mode=detailed`, plain "Results so far"); frontend/src/views/EvalView.vue (plain step list, workspace picker and review datasets first, model comparison collapsed under Advanced); frontend/src/components/ReviewDatasets.vue (wording); e2e/review-datasets.spec.ts (+1 test, existing tests switch to detailed mode), e2e/experiments.spec.ts (opens Advanced). Docs: human-evaluation-datasets.md, project-context.md.
- Decisions: no backend or contract change. Order is a seeded shuffle of the dataset ID so labeled prefixes are a random sample of the pool. Shortlist membership is hidden during quick labeling to avoid bias. No AI pre-filled labels: they would measure the models against themselves. Quick answers merge into any existing detailed review for the job. Target of 30 is a usability prompt, not a statistical guarantee.
- Checks: `./scripts/check.sh --e2e` passed: 267 Python tests, 79 frontend tests, legacy tests, build, 37 Playwright tests (mocked providers).
- Unresolved: 30 labels give wide uncertainty; percentages are labeled rough below 20 decisive labels. Model-vs-human fit agreement per provider is not shown (snapshots do not store provider fit categories).
- Next owner: user labels about 30 jobs; evaluation manager then reviews results and misses.
