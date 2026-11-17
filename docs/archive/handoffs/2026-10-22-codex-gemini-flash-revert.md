# Gemini evaluation default revert

- Objective: revert Gemini to the previous Gemini 3.6 Flash model after real evaluation rate-limit failures; keep GPT unchanged.
- Tool/model: Codex / GPT-6 session; no Git repository or branch available.
- Changed: backend/evaluation/providers.py, tests/test_evaluation_models.py, frontend/src/mocks/handlers.ts, .env.example, docs/EVALUATION_MODELS.md.
- Decisions: Gemini defaults to gemini-3.6-flash with low thinking, preserving the user's reasoning preference. Explicit Argon overrides retain low thinking. No local Gemini model override was set, so no .env mutation was necessary. GPT, Claude, pacing, retries, saved results and scoring rules remain unchanged. Existing model/cache identity prevents cross-model reuse.
- Validation: standard scripts/check.sh passed: 218 backend tests, 62 frontend tests, 1 legacy test, generated contracts and build. Installed SDK serialization test covers low thinking for Flash. No browser workflow changes or live provider calls.
- Skills: agents/skills/backend-engineer/SKILL.md and agents/skills/test-engineer/SKILL.md.
- Limits: quota availability, actual latency and assessment accuracy remain unverified; changing models does not guarantee resolution of 429 errors.
- Next action: restart backend and retry failed evaluations. No implementation work remains.
