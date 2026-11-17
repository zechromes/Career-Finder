# Results table statuses

- Objective: show Applied, Saved and Dismissed states directly in the results table.
- Tool/model: Codex, GPT-6 session. Branch unavailable: workspace has no Git repository.
- Skills: agents/skills/frontend-engineer/SKILL.md and agents/skills/test-engineer/SKILL.md.
- Changed: frontend/src/components/JobDashboard.vue, frontend/tests/components.spec.ts, frontend/e2e/workflow.spec.ts, frontend/README.md.
- Decisions: Status column displays every active flag from the existing jobs store, or No status. Dismissed jobs retain the existing Dismissed filter. Actions menu and API contracts unchanged.
- Validation: standard scripts/check.sh with job-tracker Python passed (249 Python, 77 frontend, 1 legacy test, generated contracts, typecheck/build). Focused table browser test passed including keyboard and axe checks. Initial browser assertion incorrectly reopened an already open menu; corrected test sequence and reran successfully. No live providers used.
- Remaining: none for this scope. Full browser suite was not rerun. Next owner: user review.
