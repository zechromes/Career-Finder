# Job-ad style extraction queries

- Tool / model: Claude Code, Opus 5.5
- Branch: improve-seniority-matching (uncommitted, on top of existing uncommitted work)
- Objective: extraction writes retrieval queries the way job ads describe the work;
  weights stay computed from resume evidence.

## Changed paths
- `backend/schemas/resume.py`: `SkillGroup.query` now asks for a 15–35 word job-ad
  sentence (mainstream tools, niche models by category, no project details); new
  `ExtractedProfile.keyword_queries` (1–2 lines of 6–12 skill terms); `preferred_domains`
  may include common title variants.
- `backend/search/ranking.py`: keyword lines join the skill queries at the average
  evidence of the kept skills they name; lines naming none are dropped.
- `tests/test_matching_improvements.py`, `docs/application-workflow-technical-guide.md`,
  `docs/matching-improvements.md`; regenerated `openapi.json` and `api.d.ts`.

## Decisions
- Title expansion stays opt-in: suggested titles remain editable Target roles.
- No LLM strength labels; weights stay deterministic.
- No new query builder; profiles extracted before this change behave as before.
- Soft-skill query (0.5 vote) and role vote unchanged.

## Checks
- `./scripts/check.sh`: exit 0. No live extraction or labeled comparison run.

## Unresolved / next
- Evaluation manager: before/after comparison on labeled cases with
  `scripts/measure_matching.py` (re-extract a profile to get the new queries).
