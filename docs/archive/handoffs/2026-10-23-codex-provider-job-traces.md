# Provider-labeled evaluation job traces

- Objective: rename evaluation.job to evaluation.claude, evaluation.gpt or evaluation.gemini according to the selected provider.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: backend/evaluation/providers.py, docs/langsmith-tracing.md.
- Decision: use the already validated provider name in the per-job stage decorator. Model request child spans, hierarchy, privacy policy and execution behavior remain unchanged. No API changes.
- Skills: backend/test skills previously read and applied.
- Validation: standard scripts/check.sh passed: 231 backend tests, 65 frontend tests, 1 legacy test, contracts and production build. No live LangSmith/model calls or browser changes.
- Next action: restart backend; names apply to newly created traces only.
