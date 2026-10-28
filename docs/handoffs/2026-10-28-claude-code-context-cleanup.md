# Project context cleanup

- Objective: remove obsolete context documents, relocate current ones, fix the evaluation-manager skill mismatch, and archive older handoffs.
- Tool/model: Claude Code, Claude Opus 5.5. Branch unavailable: this workspace has no Git repository.
- Skills: agents/skills/structure-tidier/SKILL.md, agents/skills/project-manager/SKILL.md.
- Removed: docs/archive/project_context.md and docs/archive/career_tracker_ui.md (near-identical superseded Reverse-RAG drafts); the now-empty docs/archive/.
- Moved: docs/archive/PRD.md → docs/PRD.md; docs/archive/modified_project_context.md → docs/project-context.md (decision logged there); 2026-10-19/20 handoffs → docs/handoffs/archive/.
- Changed: agents/skills/evaluation-manager/SKILL.md rewritten from the AGENTS.md Evaluation manager rules; removed the "Known mismatch" note from AGENTS.md and the matching workaround in .codex/agents/evaluation-manager.toml; updated references in README.md, project-manager and structure-tidier skills; fixed the README API reference link to docs/images/openapi.json.
- Checks: reference search for old paths (none remain outside archived handoffs); linked paths verified to exist. Documentation-only change; no application tests run.
- Unresolved: archived and remaining handoffs still mention old docs/archive/ paths as historical records.
- Next owner: project manager, for content review of docs/project-context.md against docs/PRD.md.
