# Gemini without proactive RPM pacing

- Objective: remove the application Gemini RPM restriction at user request.
- Tool/model: Codex / GPT-6 session; branch unavailable (no Git repository).
- Changed: backend/evaluation/providers.py, backend/evaluation/runtime.py, tests/test_evaluation_reliability.py, .env.example, docs/EVALUATION_MODELS.md.
- Decision: GEMINI_EVALUATION_RPM defaults to 0, disabling proactive request spacing. Positive values retain configurable spacing. Two workers, rate-limit backoff, bounded retries and repeated-error batch stopping remain. No local RPM override was present. No API contract changes.
- Validation: standard check passed: 219 backend tests, 62 frontend tests, 1 legacy test, contracts and build. New fake-clock test verifies immediate unpaced starts and a 75-second provider-requested backoff without live calls.
- Skills: backend and test skills previously read and applied. No browser workflow changes.
- Remaining: restart backend to apply. Provider quotas still apply; no live latency or quota verification performed.
