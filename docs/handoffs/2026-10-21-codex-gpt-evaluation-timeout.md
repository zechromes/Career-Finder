# GPT evaluation timeout

- Objective: address the reported GPT evaluation timeout after the evaluation model upgrade.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed paths: backend/evaluation/providers.py, tests/test_evaluation_models.py, .env.example, docs/EVALUATION_MODELS.md.
- Decision: raise the GPT SDK request timeout from 60 to 180 seconds. GPT_EVALUATION_TIMEOUT_SECONDS accepts integer overrides bounded to 30–600 seconds; invalid values use 180. Retain one SDK retry and existing targeted evaluation retries. No API contract, scoring, model, or concurrency changes.
- Validation: standard scripts/check.sh passed with 216 backend tests, 60 frontend tests, 1 legacy test, contract generation and frontend build. Tests cover the default, override, bounds and invalid configuration. No live provider calls; the error alone does not establish the underlying cause, and the longer timeout does not guarantee completion.
- Skills: agents/skills/backend-engineer/SKILL.md and agents/skills/test-engineer/SKILL.md.
- Remaining action: restart the backend to load the new default, then retry failed evaluations. SDK retries can extend total elapsed time beyond the per-request timeout. No implementation work remains.
