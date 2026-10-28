# Integrated requirement sections

- Objective: remove standalone model comparison card, place feedback below requirements, and add Qualifications/Nice to have-style headings.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: frontend/src/components/EvaluationEvidence.vue, frontend/src/components/RequirementComparison.vue, frontend/src/views/JobDetailView.vue, frontend/src/utils/requirementSections.ts, frontend/tests/job-actions.spec.ts, frontend/tests/requirement-sections.spec.ts, frontend/e2e/workflow.spec.ts, frontend/README.md.
- Decisions: retain selected model's requirement evidence, with same-verified-quote model feedback directly underneath. Group by matching original posting sections into Qualifications, Nice to have, Responsibilities; ambiguous/unrecognized sections use Other requirements. Each group navigates independently. No scoring, provider calls, API or persisted schema changes.
- Skills: frontend/test skills previously read and applied.
- Checks: standard check passed (219 backend, 65 frontend, 1 legacy test, contracts and build). Tests retain quote-verification and model-evidence separation checks and add heading/ambiguous-quote cases. Mocked mobile/browser workflow checks integrated feedback and accessibility.
- Limitations: heading recognition is conservative and cannot recover section names absent from the source description. No live provider calls.
