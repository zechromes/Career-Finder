# Ingestion recording and stage checks (Phases 2 and 3)

- Objective: measure the ingestion stage in /eval, plus a duplicate-merge check, a search-text check and the embedding comparison in the Retrieval tab.
- Tool/model: Claude Code, Claude Opus 5.5. Branch: improve-seniority-matching.
- Skills: backend-engineer, frontend-engineer, test-engineer, evaluation-manager (agents/skills/).
- Backend: new backend/search/ingestion_log.py (context-scoped, bounded per stage; workspace duplicates counted only). Hooks in adaptive.collect (collected, no description, candidate limit, unprocessed pending), collection.py (early/final filter reasons via new filters.filter_reason, duplicate recording, age filter, cache-hit flag) and service.py (re-filtering, append dedup, save to run_dir/ingestion.json). Behavior of filtering/ranking unchanged.
- Contract: ReviewDataset.ingestion + dropped_jobs; JobReview.duplicate_correct; StageFunnel.lost_at_ingestion; StageMetrics.ingestion (by_reason, by_board, labeled/good_fits, duplicates, search_text). Pool-only labels feed retrieval metrics and fit_reviewed.
- Frontend: QuickLabel dropped queue (?mode=dropped), DuplicateCheck.vue, RetrievalComparison.vue (uses existing experiments API, retrieval phase), StageResults ingestion tab; mocks save per job id (fixes a job1-only mock bug).
- Evidence on the user's pilot dataset: ingestion unavailable (search predates recording); search-text check 1853/1872 requirement quotes survive cleaning (99%), so cleaning is not the cause of retrieval misses.
- Checks: ./scripts/check.sh --e2e passed (279 Python, 79 frontend, legacy, build, 40 Playwright). Mocked providers only; no live search run.
- Unresolved: ingestion measurement needs a new search; /eval Advanced still also offers retrieval comparison; the dropped-job sample is capped, so per-reason good-fit counts are a sample, not totals.
- Next owner: user runs a new search, creates a dataset, labels ~30 pool and ~20 dropped jobs.
