# Job action snackbar

- Objective: reusable snackbar feedback for copying links, saving jobs and marking jobs applied.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: frontend/src/stores/snackbar.ts, frontend/src/components/AppSnackbar.vue, frontend/src/App.vue, frontend/src/components/JobActions.vue, frontend/tests/snackbar.spec.ts, frontend/tests/components.spec.ts, frontend/e2e/workflow.spec.ts, frontend/README.md.
- Decisions: global five-second notification with manual close and polite live announcement. New actions replace the current notification. Covers save/applied/dismiss and reversals across all JobActions usages. Clipboard success only follows successful write; failure retains manual copying. Existing browser-storage/server-sync error states remain. No backend or API contract change.
- Skills: agents/skills/frontend-engineer/SKILL.md and agents/skills/test-engineer/SKILL.md, previously read and applied.
- Validation: standard check passed: 219 backend, 64 frontend, 1 legacy test, contract generation and build. Unit coverage includes clipboard behavior, save/applied reversals, replacement timer and dismissal. Browser workflow checks visible save feedback and accessibility using synthetic mocks.
- Remaining: no live service calls or data migration required.
