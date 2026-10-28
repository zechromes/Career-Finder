# Evaluation retry loading

- Objective: show loading when retrying failed evaluations.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: frontend/src/stores/pipeline.ts, frontend/src/views/RunView.vue, frontend/src/components/JobDashboard.vue, frontend/tests/components.spec.ts, frontend/tests/pipeline.spec.ts, frontend/README.md.
- Decisions: track the action during submission, then use the authoritative running snapshot and existing retry message. Show a spinner, busy button label and accessible status text. Disable repeat submissions. Clear submission state after success or error. No API contract changes or invented progress percentage.
- Validation: standard check passed (218 backend, 62 frontend, 1 legacy test, contracts and build). One mocked browser workflow with accessibility checks passed. Component tests cover loading and restoration; store test covers duplicate prevention and rejected requests. No live provider calls.
- Skills: agents/skills/frontend-engineer/SKILL.md and agents/skills/test-engineer/SKILL.md.
- Remaining: user reported a rate-limit log during verification; the same exact message occurs in mocked tests. Asked whether it came from a real search or checks; source not yet established. Loading implementation complete.
