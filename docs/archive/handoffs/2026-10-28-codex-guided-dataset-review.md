# Guided dataset review

- Objective: help users understand how to review datasets, with a fit-first path and optional deeper checks.
- Tool/model: Codex, GPT-6 session; no subagents. Branch unavailable in this workspace (no Git repository).
- Skills: agents/skills/frontend-engineer/SKILL.md, test-engineer/SKILL.md, project-manager/SKILL.md; evaluation guidance follows AGENTS because of the documented evaluation skill mismatch.
- Changed: frontend/src/views/ReviewDatasetView.vue, new frontend/src/components/ReviewGuide.vue, frontend/e2e/review-datasets.spec.ts; docs/human-evaluation-datasets.md, frontend/README.md, docs/archive/modified_project_context.md and this note. Standard checks regenerated public contracts/build artifacts.
- Behavior: three-step introduction, expanded profile, plain-language examples for fit/extraction/evidence, optional separate requirement/evidence views retaining drafts, collapsed metrics and a save bar. Fit-only reviews remain valid; unanswered judgments remain unreviewed. Existing labels and model outputs are preserved.
- Contracts: no API/schema/scoring changes. No model calls or private data inspection.
- Validation: standard scripts/check.sh passed (265 Python, 79 frontend, 1 legacy; contract generation, typecheck/build). Focused browser tests passed, then full mocked browser suite passed 34/34, including mobile width and axe checks. Changed frontend files formatted. Local browser server required sandbox escalation and was approved.
- Limitations: usability guidance and software behavior verified; no claim of human-labeled accuracy improvement or live provider availability.
- Next owner: user; open Experiments → Human review datasets, start with one fit decision, save, and optionally review requirements/evidence.
