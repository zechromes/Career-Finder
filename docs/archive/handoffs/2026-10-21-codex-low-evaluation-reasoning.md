# Lower evaluation reasoning

- Objective: lower reasoning effort for GPT-6.1 Sol and Gemini 4 Argon evaluations.
- Tool/model: Codex / GPT-6 session. Branch unavailable: workspace is not a Git repository.
- Changed: backend/evaluation/providers.py, tests/test_evaluation_models.py, docs/EVALUATION_MODELS.md.
- Decisions: pass reasoning_effort=low to GPT-6.1 Sol and thinking_level=low to Gemini 4 Argon. Apply only to these exact model IDs to preserve legacy model overrides. Include reasoning settings in assessment cache identity so prior default-effort results are not reused for new calls. Saved results remain intact. No API contract changes.
- Checks: 13 focused tests passed, including actual installed SDK request configuration using synthetic keys without network calls. Standard scripts/check.sh passed: 218 backend, 60 frontend, 1 legacy test, contract generation and production build.
- Skills: agents/skills/backend-engineer/SKILL.md, agents/skills/test-engineer/SKILL.md and OpenAI Docs.
- Limitations: no live latency measurement or human-labeled quality evaluation; low reasoning can affect assessment quality. No UI changes or browser checks needed.
- Next action: restart backend; new evaluations and targeted failed-evaluation retries use low reasoning. No remaining implementation work.
