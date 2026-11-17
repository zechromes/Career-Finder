# Docs refresh for current application

- Tool / model: Claude Code, Opus 5.5
- Branch: improve-seniority-matching (uncommitted, on top of existing uncommitted work)
- Objective: bring `docs/` in line with the app after the 3–16 November changes.

## Changed paths
- `docs/PRD.md`: scope adds retrieval playground stage, tailored resume, job-action dataset;
  "resume generation" removed from Future Development; FR-07 tailored resume bullet; data table
  drops stale "Experiment results", adds tailored resumes, job-action dataset, hyde cache.
- `docs/application-workflow-technical-guide.md`: retry progress (§11), storage rows for
  `.cache/hyde_queries` and `data/evaluation_datasets` (§12), tailored-resume route (§13),
  job-action dataset and tailored resume (§14), playground relevance metrics (§16).
- `docs/project-context.md`: two dead links to deleted guides replaced; entries for query
  builders, playground metrics, job-action dataset, results/retry UI, tailored resume.
- `docs/EVALUATION_MODELS.md`: `CLAUDE_EVALUATION_MODEL` also drives the tailored resume.

## Checks
- Documentation only: claims checked against code; local Markdown links resolve. No app tests run.

## Unresolved / next
- Project manager: confirm tailored resume and job-action dataset belong in PRD scope as written.
- The job-action dataset is never deleted automatically; decide whether it should follow profile deletion.
