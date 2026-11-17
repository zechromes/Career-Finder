# Documentation consolidation

- Tool / model: Claude Code, Opus 5.5
- Branch: improve-seniority-matching (uncommitted, on top of existing uncommitted work)
- Objective: consolidate every guide into README.md + docs/{PRD, Architecture,
  DEVELOPMENT, DECISIONS, ROADMAP}.md, checked against code; archive the originals.

## Changed paths
- New: `README.md`, `docs/PRD.md`, `docs/Architecture.md`, `docs/DEVELOPMENT.md`,
  `docs/DECISIONS.md`, `docs/ROADMAP.md`, `docs/archive/README.md` (old → new map).
- Moved to `docs/archive/`: old root and frontend READMEs (`root-README.md`,
  `frontend-README.md`), 13 docs guides, 65 handoff notes (`archive/handoffs/`),
  stale `docs/images/openapi.json`.
- Links repointed: `AGENTS.md`, `agents/skills/{evaluation-manager,project-manager,
  frontend-engineer,structure-tidier}/SKILL.md`. No rules changed.

## Decisions
- Code wins over old docs: collection deadline 240 s (docs said 120), Claude 180 s /
  16,000 tokens (docs said 90 s / 8,192), shortlist default Automatic (docs said 50).
- PRD gains FR-15 (job-action dataset) describing shipped behavior.

## Checks
- Documentation only; no application tests run. All links and heading anchors in the
  new docs resolve.

## Unresolved / next
- Project manager: confirm FR-15 and the tailored resume in PRD scope. The
  project-manager skill still lists "generating resumes" as out of scope and cites
  old limits ("50 jobs per board", "15/50/100/all"); left unchanged.
- Code leftovers in ROADMAP §4: `/eval/datasets/{id}` page route, unused
  `ReviewGuide.vue`, flowchart showing pre-30 Oct scoring.
