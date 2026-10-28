# Feedback-only model cards

- Objective: keep only feedback inside the Model feedback cards.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: frontend/src/components/RequirementComparison.vue, frontend/tests/job-actions.spec.ts, frontend/e2e/workflow.spec.ts.
- Decisions: retain model attribution and explanation (or missing-feedback message); remove duplicate requirement, verdict/importance badges, resume evidence and explanatory preamble from feedback cards. Parent requirement evidence remains. No API or scoring changes.
- Skills: frontend/test skills previously read and applied.
- Validation: standard checks passed: 219 backend, 65 frontend, 1 legacy test, contracts and build. Mocked mobile/accessibility workflow passed.
- Remaining: none.
