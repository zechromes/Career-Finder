# Disable automatic browser tab at startup

- Objective: stop the launcher opening a browser tab when starting the app.
- Tool/model: Codex / GPT-6; no Git repository/branch available.
- Changed: run_app.sh, README.md, docs/archive/modified_project_context.md.
- Decision: remove Vite --open /; keep the printed frontend URL and existing service startup/shutdown behavior. No API changes.
- Validation: bash -n run_app.sh passed; inspected Vite configuration and npm dev script for additional automatic-open settings (none). Application suite not run for this launcher flag/documentation-only change. Did not launch services or open a browser.
- Next: next launcher start will no longer automatically open a tab; access http://localhost:5173/ manually.
