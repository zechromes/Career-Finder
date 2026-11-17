# Skills-only query builder

- Tool / model: Claude Code, Opus 5.5
- Branch: improve-seniority-matching (uncommitted, on top of existing uncommitted work)
- Objective: retrieval queries that focus on skills, with experience used only as weight,
  so entry domain words do not steer retrieval and partial skill overlap still ranks.

## Changed paths
- `backend/search/ranking.py`: `QUERY_BUILDER=skills`; `_evidence_votes(..., with_experience=False)`
  drops the experience query family. Unknown `QUERY_BUILDER` values now raise `ValueError`.
- `scripts/compare_query_builders.py`: replays all three builders; `overlap_in_top` is now
  `{"legacy": n, "skills": n}` against evidence.
- Playground: `RetrievalRequest.query_builder` (default `evidence`) and a Queries select in
  `frontend/src/views/EvalView.vue`; regenerated `openapi.json` and `api.d.ts`.
- `tests/test_matching_improvements.py`, `tests/test_playground.py`, `.env.example`,
  `docs/application-workflow-technical-guide.md`, `docs/matching-improvements.md`.

## Decisions
- `evidence` stays the default; `skills` is opt-in for comparison.
- Skill weights unchanged (listed 0.5 + entry strength, ×1.5 when a role names it).
- Under `skills`, entry-only hard skills (in `entry_evidence`, not `tech_skills`) join the
  skill pool, placed in the group the same entries use most ("Other skills" only when none);
  `evidence` is unchanged.
- Under `skills`, skills no entry shows are kept at `listed_only` (0.2).
- Skill-name matching (`skill_names`, `skill_label`, `_stem` in ranking.py) is shared by both
  builders, so `evidence` now proves more skills than before (for example "Docker (basics)").

## Checks
- `./scripts/check.sh`: exit 0.
- No labeled comparison run (needs live embeddings and labels).

## Unresolved / next
- Evaluation manager: compare `evidence` vs `skills` with `scripts/measure_matching.py` on
  labeled cases before changing the default.
- Alias text (for example "JavaScript (JS)") for BM25 not added.
