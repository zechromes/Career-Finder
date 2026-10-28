# Preserve job actions during evaluation

- Objective: fix Applied/Saved/Dismissed state reverting while evaluation is active. User clarified the click works but its state does not stick.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: frontend/src/stores/jobs.ts, frontend/tests/job-actions.spec.ts, frontend/src/mocks/handlers.ts, frontend/e2e/workflow.spec.ts, frontend/README.md.
- Finding: a synchronization GET started after a local click but before its PUT completed could deliver stale server flags after the pending edit was cleared. The original edit-version comparison then allowed stale values to replace the confirmed edit.
- Fix: increment the edit version when a write is confirmed, before clearing its pending entry. Older synchronization responses preserve the newer local flags. No API, backend, sorting or action-menu layout changes.
- Validation: reproduced three failing regression cases (saved/applied/dismissed) before fixing. Standard check passed afterward: 231 backend, 68 frontend, 1 legacy test, generated contracts and build. New mocked browser workflow passed: mark Applied while evaluation stays running, receive another snapshot, verify Applied remains pressed and saved. Tests also verify browser persistence after reopening. No live model calls.
- Skills: frontend/test skills previously read and applied.
- Remaining: reload frontend to use the fix; no backend restart needed for this frontend change.
