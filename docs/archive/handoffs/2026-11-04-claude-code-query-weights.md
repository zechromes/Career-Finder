# Normalized retrieval query weights

- Tool / model: Claude Code, Opus 5.5
- Branch: improve-seniority-matching (uncommitted, on top of existing uncommitted work)
- Objective: stop soft skills, the role title and long skill lists from dominating retrieval.

## Changed paths
- `backend/search/ranking.py`: votes roles 0.5, soft_skills 0.0 (zero-vote families are
  skipped); skill groups weigh the average of their skills' evidence, not the sum; weights
  are scaled to sum to 1; the `skills` builder also uses the extracted group sentence.
- `tests/test_matching_improvements.py`: updated expected weights; new tests for sum to 1,
  no soft-skill queries, and group share independent of list length.
- `frontend/src/views/EvalView.vue` (playground description only),
  `docs/application-workflow-technical-guide.md`, `docs/matching-improvements.md`.

## Decisions
- Model-generated query builder (spec in `docs/query_extraction.md`) not built: retrieval
  only decides the shortlist; fit is judged by requirement evaluation.
- Legacy builder weights unchanged.

## Checks
- `./scripts/check.sh`: exit 0. E2E not run. No labeled comparison run.

## Unresolved / next
- Evaluation manager: measure shortlist recall with `scripts/measure_matching.py`.
- If good jobs are shortlisted but ranked low: requirement-coverage score on the shortlist.
