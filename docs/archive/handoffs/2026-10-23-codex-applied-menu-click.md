# Applied menu click handling

- Objective: fix Mark as applied doing nothing when clicked. User confirmed no visible change on click.
- Tool/model: Codex / GPT-6 session. No Git repository/branch is available.
- Files: frontend/src/components/JobActions.vue, frontend/tests/snackbar.spec.ts, frontend/e2e/workflow.spec.ts, frontend/README.md.
- Findings: reproduced focusout with no related target removing the menu before click. Browser regression also reproduced a delayed scroll event closing a newly opened menu after its trigger was brought into view.
- Changes: preserve internal pointer interaction through focus loss; clear pointer state on release/cancel; focus menu without scrolling; ignore queued scroll events when the viewport has not moved since opening. Actual viewport movement/resize, outside clicks, keyboard focus departure and Escape retain dismissal behavior. No API/store/persistence changes.
- Validation: new component regression failed before the fix and passes afterward. Final scripts/check.sh passed (235 Python, 69 frontend, 1 legacy, contracts/typecheck/build). Three mocked browser checks passed: pointer focus loss with Applied retained after refresh; Applied during evaluation; keyboard/table accessibility. No live API/provider calls.
- Skills: frontend-engineer and test-engineer; backend skill read for API inspection. Existing saved-action sync fix preserved.
- Remaining: reload the frontend to use the corrected menu. No backend restart required for this change. Browser test simulates the no-focus click behavior; not a native Safari run.
