# Restore Gemini Argon

- Objective: switch Gemini evaluation back to Gemini 4 Argon at user request.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: backend/evaluation/providers.py, tests/test_evaluation_models.py, frontend/src/mocks/handlers.ts, .env.example, docs/EVALUATION_MODELS.md.
- Decisions: default gemini-4-argon, low thinking retained, application RPM limit remains disabled. GPT and Claude unchanged. No local model override was present. Saved assessments retained; targeted retries use current model configuration. No API contract changes.
- Skills: backend/test skills previously read and applied.
- Checks: standard scripts/check.sh passed (219 backend, 62 frontend, 1 legacy test, generated contracts and production build). No live model calls or quality comparison.
- Next action: restart backend. Provider quotas still apply. No implementation work remains.
