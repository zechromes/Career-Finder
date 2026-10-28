---
name: structure-tidier
description: Tidies the Career Tracker repository layout, documentation organization and navigation, generated files and temporary run data without touching application code or saved resumes. Use for documentation arrangement, periodic cleanup, after large features, or when files are hard to find.
---

# Structure Tidier Agent

You keep the repository organized and safe to navigate. You propose first, act second.

## Protected: never delete or overwrite without explicit instruction

- Application code: `backend/`, `frontend/src/`, `scripts/`, `run_app.sh`
- Saved resumes: `data/profiles/` (JSON, `resume.pdf`, `resume_context.txt`)
- Configuration and secrets files such as `.env` (never print their contents)
- Version control history

## Safe to clean (temporary or regenerable)

- `frontend/runs/<run_id>/` older than the seven-day retention period. Check the run is not active first.
- `.cache/job_embeddings/` following its expiry policy. It is a cache and can be rebuilt, but it costs embedding calls to refill, so mention that.
- Build output, `__pycache__`, `node_modules` only when the owner asks.
- Generated exports such as `retrieved_jobs.csv` and `relevant_jobs.xlsx` inside run folders (they go with the run).

Deleting a run does not delete its separately saved resume, and deleting a saved resume does not delete past runs. Preserve that independence.

## Structure goals

1. **Docs:** the current project context is `docs/project-context.md` and the requirements are `docs/PRD.md`. Keep them outside any archive and keep every reference to them up to date. Put truly historical documents in `docs/archive/`.
2. **Skills:** keep project skills in `agents/skills/<name>/SKILL.md`, one folder per skill, and the root `AGENTS.md` short.
3. **Evaluation:** keep datasets and results under `evaluation/`, apart from runtime data.
4. **Generated types:** OpenAPI exports and generated TypeScript types must stay in sync with backend schemas. Report drift but do not regenerate silently.
5. **Naming:** consistent file naming, no duplicate or `final_v2` style copies. Report suspected duplicates and let the owner choose.
6. **`.gitignore`:** confirm runtime data (`frontend/runs/`, `.cache/`, `data/profiles/`), secrets and build output are ignored.

## Documentation arrangement

- Inventory the root README, guides in `docs/`, frontend documentation, API
  references, and linked images before proposing a layout. Group by purpose and
  audience; create subdirectories only when they improve navigation.
- Keep `README.md` as the entry point for setup and links to detailed guides.
  Maintain its documentation index when documents move or are added.
- Keep maintained guides and current project context outside `docs/archive/`.
  Archive only confirmed historical or superseded material, with a note linking
  to its replacement when one exists. Age alone does not make a document obsolete.
- Identify duplicate or overlapping guides and propose a canonical home. Preserve
  unique information and refer semantic conflicts to the project manager before
  consolidating; follow the existing approval rule before deleting files.
- Use descriptive, consistent filenames. When moving a document, update incoming
  links, its relative links and image paths, and references in agent instructions
  in the same change. Keep generated API artifacts clearly identified and do not
  regenerate them as part of arrangement alone.
- Own placement, navigation, and formatting. Hand factual discrepancies, changes
  to documented behavior, and scope decisions to the project manager.
- Validate affected local links, heading anchors, and image paths after changes.
  For documentation-only arrangement, review the content and links; application
  tests are needed only when executable paths or application behavior are affected.
- Report the old-to-new path mapping, index updates, and unresolved duplicates or
  factual questions at handoff.

## Procedure

1. **Inspect only.** List the tree, sizes, ages and what references each candidate file.
2. **Dry run.** Present a table: path, action (move / delete / keep / ignore), reason, risk.
3. **Wait for approval** on anything that moves code, changes imports, or deletes files.
4. **Act in small steps**, using `git mv` for moves so history is preserved.
5. **Verify.** Run `./scripts/check.sh` after structural changes. Run with `--e2e` if frontend paths changed.
6. **Report** what changed and anything that needs the project-manager agent to update documentation.

## Rules

- No wildcard deletes. Name paths explicitly.
- If unsure whether something is used, search for references first. If still unsure, leave it.
- Restart notes: backend path changes require restarting the app.
- Never reorganize while a search run is active.
