# Requirement extraction validation recovery

- Objective: address failed shared extraction caused by empty criteria, unsupported quotes or invented section headings.
- Tool/model: Codex / GPT-6; branch unavailable (workspace has no Git repository).
- Changed: backend/evaluation/requirements.py, tests/test_shared_requirements.py, docs/EVALUATION_MODELS.md.
- Decision: retain strict source validation; specify continuous verbatim quotes and real headings in the prompt, and provide indexed field-specific correction feedback on the existing single validation retry. Bump extraction policy version to v2. No API or scoring changes; frozen historical criteria remain supported.
- Verification: 14 focused tests passed. Standard scripts/check.sh passed using /opt/homebrew/anaconda3/envs/job-tracker/bin/python: 237 Python tests, 70 frontend tests, legacy checks, contract generation, typecheck and build. Initial check with base Python failed due to missing jobspy and broken SQLite linkage; project environment resolves these failures.
- Skills: agents/skills/backend-engineer/SKILL.md and agents/skills/test-engineer/SKILL.md; read evaluation skill but used AGENTS.md evaluation rules due to documented mismatch.
- Limitations: synthetic mocked provider cases only; no live extraction or labeled accuracy comparison. Persistent invalid output remains an explicit failure. No private postings inspected.
- Next: restart backend and retry failed evaluations to use corrected extraction requests.

## Follow-up: optional section metadata and SDK serialization

- User reported continued section rejection and an SDK parsed-object serialization warning.
- Fresh extraction now clears unverified optional section labels before freezing; valid labels and all criteria/quotes remain. Frozen saved lists are still strictly validated without mutation. Policy version v3 separates extraction caches.
- OpenAI extraction and GPT evaluation now receive JSON-schema dictionaries and validate returned dictionaries locally, avoiding the SDK typed parsed-object path without warning suppression. Additional changed paths: backend/evaluation/providers.py, tests/test_evaluation_models.py.
- Checks: standard check passed (238 Python, 70 frontend, legacy, contracts/typecheck/build); strengthened dictionary-response provider regression then passed all 13 provider tests. No live requests; actual provider warning disappearance remains unverified.
- Next: restart backend and retry failed evaluations. Scoring and mandatory evidence checks remain unchanged; optional metadata clearing is not a measured matching-quality improvement.

## Follow-up: remove model quote transcription

- Continued quote rejection showed prompt-only recovery was insufficient. Fresh extraction v4 selects inclusive numbered source-line ranges instead of generating quote strings. Backend copies exact original text and validates the resulting persisted criteria using the existing strict validator.
- Changed: backend/schemas/evaluation.py (extraction-only reference models), backend/evaluation/requirements.py, tests/test_shared_requirements.py, README.md, docs/EVALUATION_MODELS.md. Persisted/API requirement shapes and frozen historical criteria are unchanged; source ranges are not persisted or exposed as a new API contract.
- Checks: 18 focused tests passed; full scripts/check.sh passed using job-tracker Python (241 backend tests, 70 frontend tests, legacy, contract generation, typecheck/build). Coverage includes original numbered prompt reconstruction, multiline CRLF/Markdown/Unicode evidence, alternatives/negation, invalid/reversed/blank source ranges, bounded retry, cache and cancellation.
- Evidence limitation: source references establish provenance, not semantic entailment, completeness or matching accuracy; a one-line posting produces a broader quote. No private postings or live provider calls used, no labeled baseline available.
- Next: restart backend and retry failed evaluations; no cache deletion or saved-data migration needed.

## Diagnosis of repeated message after v4

- Read-only inspection found latest failed checkpoint/state written at 15:30 Sydney time, before requirements.py v4 modification at 15:34. Current backend PID start was 15:37, in this workspace. No newer retry checkpoint exists.
- Aggregate-only inspection: 21 saved failures; 9 quote and 9 section messages; 18 entries have no frozen criteria and 3 retain v2 criteria. All 3 frozen criteria pass current validation. No private input, job identifiers or response text logged.
- Conclusion: evidence points to persisted pre-fix errors, not a demonstrated v4 extraction failure. Reloading does not rerun evaluation. User should use Retry failed evaluations; no additional backend restart appears necessary. Did not invoke paid provider requests or mutate saved results.
