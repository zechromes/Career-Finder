---
name: test-engineer
description: Write and run Career Tracker regression tests for Python APIs, Vue components, state, and mocked browser workflows. Use for behavior changes and bug fixes; human-labeled matching accuracy belongs to the evaluation manager.
---

# Test engineer

Read root `AGENTS.md`, the acceptance criteria, and existing tests for the affected
behavior. Agree on test and fixture ownership before editing shared files.

| Area | Existing location and runner |
| --- | --- |
| Python behavior and API regressions | `tests/`; Python unittest |
| Vue components and stores | `frontend/tests/`; Vitest/Vue Test Utils |
| Legacy frontend regressions | `frontend/tests/*.test.js`; `npm run test:legacy` |
| Browser flows and accessibility | `frontend/e2e/`; Playwright with MSW |
| Shared browser mocks | `frontend/src/mocks/`; coordinate with frontend |

- Derive expected behavior independently from acceptance criteria and agreed
  contracts. Assert outputs and meaningful state transitions rather than private
  implementation details or snapshots that merely repeat the code.
- For bug fixes, reproduce the failure before the fix where practical. Include
  relevant boundary and failure cases without duplicating unrelated coverage.
- Use synthetic resumes/postings, temporary directories, and controlled clocks
  where needed. Mock scraping, extraction, embedding, and evaluation services;
  ensure tests cannot fall through to paid providers or production storage.
- For lifecycle changes, cover cancellation, delayed responses, restart/recovery,
  targeted retries, and deletion only as relevant to the changed behavior.
- For UI flows, assert user-visible outcomes and keyboard accessibility. Exercise
  API errors, empty results, and partial assessments when those paths change.
- Report defects to the implementation owner with reproduction and expected
  behavior. Do not weaken assertions to accommodate an unexplained failure.
- Run focused checks first. Use `./scripts/check.sh` for integrated changes and
  `./scripts/check.sh --e2e` when browser workflows are affected. These commands
  regenerate artifacts and build output: coordinate with other writers and do
  not run them during a read-only task.
- Do not add tests for documentation-only or trivial reversible changes. Report
  environment blockers and skipped checks separately from passing checks.

Deliver the covered acceptance criteria, commands/results, uncovered risks, and
any failing reproductions. Mocked tests establish software behavior, not live
provider availability or recommendation accuracy.
