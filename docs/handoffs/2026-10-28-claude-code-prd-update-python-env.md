# PRD update and Python environment selection

- Objective: bring docs/PRD.md up to date with implemented features (items 4 and 5 of the PRD alignment review) and make checks use the project environment by default.
- Tool/model: Claude Code, Claude Opus 5.5. Branch unavailable: no Git repository.
- Skills: agents/skills/project-manager/SKILL.md.
- Changed: docs/PRD.md (date; section 2 cost wording now defers to section 11; scope list; FR-07 link; new FR-13 dismissal preferences, FR-14 experiments, FR-15 human review datasets; section 7 lifecycle rows; section 8 privacy page; section 9 labeled-data status). scripts/check.sh and run_app.sh prefer the job-tracker conda env when PYTHON_BIN is unset; check.sh fails fast if dependencies are missing. README.md describes both.
- Decisions: PRD additions describe implemented behavior from the feature guides, not new requirements. The env is located through CONDA_EXE, so machines without that env fall back to the active `python` as before.
- Checks: `./scripts/check.sh` with no PYTHON_BIN passed using the job-tracker env (265 Python tests, 79 frontend tests, legacy tests, build). With PYTHON_BIN set to Anaconda base it exits 1 with the dependency message. run_app.sh syntax-checked only; not launched. E2E not run.
- Unresolved: items 2 and 3 of the review (AI-assisted label marking, review dataset deletion) remain.
- Next owner: backend engineer, then frontend and test engineers, for items 2 and 3.
