# RAG stage results (Phase 1)

- Objective: evaluate retrieval and generation separately in /eval using human fit labels; ingestion explained but not yet measured.
- Tool/model: Claude Code, Claude Opus 5.5. Branch: improve-seniority-matching.
- Skills: backend-engineer, frontend-engineer, test-engineer, evaluation-manager (agents/skills/).
- Contract: ReviewJob.model_verdicts {provider: {model, status, fit_category, score}} and app_verdict (defaults keep old snapshots valid); ReviewDataset.verdicts_added_at; ReviewMetrics.stages {verdicts_available, funnel, retrieval_missed, generation, app}.
- Changed: backend/schemas/review_datasets.py, backend/evaluation/review_datasets.py (_verdicts, add_verdicts, _generation, _stages), scripts/add_review_verdicts.py (new), frontend StageResults.vue (new), ReviewDatasetView.vue, mocks, regenerated contract/types; tests (+3 Python, +1 e2e); docs human-evaluation-datasets.md, project-context.md.
- Backfill: the user's dataset gained verdicts for 100/100 shortlisted jobs (URL+title+company plus frozen-evidence equality). First attempt matched 0 on posting text and was restored from a backup; add_verdicts now refuses without writing when nothing matches. Labels verified byte-identical. Backups dataset.before-verdicts.json / reviews.before-verdicts.json remain beside the dataset (private, git-ignored).
- Finding (pilot, 27 good fits, search predates the seniority change): 13 lost at retrieval (all experienced-level titles); of 14 shortlisted good fits, the app recommended 0 as strong match, 12 needs review, 2 rejected. Models almost never output strong_match (Gemini 1/14, Claude 0, GPT 0) yet reject human not-fits well (Claude 22/23). Generation is conservative, not inaccurate on negatives; investigate the strong-match threshold/caps before changing.
- Checks: ./scripts/check.sh --e2e passed (273 Python, 79 frontend, legacy, build, 38 Playwright).
- Unresolved: rank positions not stored; ingestion losses not recorded (Phase 2).
- Next owner: evaluation manager for the strong-match finding; Phase 2 ingestion tracking.
