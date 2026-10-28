# Results three-dot menu follow-up

- Objective: Mark as applied works inline on job details but not in the results three-dot menu.
- Tool/model: Codex / GPT-6 session; no Git repository/branch available.
- Files: frontend/src/components/JobActions.vue, frontend/tests/snackbar.spec.ts, frontend/e2e/workflow.spec.ts.
- Finding: previous guard preserved pointer focus loss only for a null relatedTarget. Focus moving to the document body still closed the menu before click. Modified regression failed on the previous implementation.
- Fix: preserve menu during any internal pointer focus transition; focus dismissal still works after pointer release. No API, store or inline action changes.
- Checks: standard scripts/check.sh passed: 235 backend, 70 frontend, 1 legacy, generated contracts/typecheck/build. Four mocked browser tests passed: grid and table three-dot Applied clicks with body focus and refresh persistence, actions during evaluation, keyboard/table accessibility. Native Safari not installed; no claim of native Safari validation.
- Skills: frontend-engineer and test-engineer, read in this ongoing task.
- Next: reload frontend to use the updated component; no backend restart needed. Browser-specific behavior beyond reproduced focus sequence remains unverified.
