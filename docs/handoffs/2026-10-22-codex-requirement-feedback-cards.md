# Requirement feedback cards

- Objective: use the user's example layout for requirement comparisons and display feedback underneath each requirement.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: frontend/src/components/RequirementComparison.vue, frontend/tests/job-actions.spec.ts, frontend/e2e/workflow.spec.ts, frontend/README.md.
- Decisions: navigate one verified quote group at a time with Previous/Next buttons and arrow keys. Render each model's requirement, importance, verdict and explanation above posting/resume evidence columns. Maintain independent model feedback and explicit unavailable/unverified evidence states. Preserve grouping by verified quote; no new inferred posting-section labels or scoring changes.
- Skills: frontend and test skills previously read and applied.
- Checks: standard check passed (219 backend, 64 frontend, 1 legacy test, contracts and build). Affected mocked mobile/browser accessibility workflow passed. Tests cover navigation, bounds, grouping, absent feedback and separation of model evidence.
- Remaining: none; no live model calls or data changes.
