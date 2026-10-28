# Readable requirement comparison

- Objective: improve readability of the quoted-requirement comparison section.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: frontend/src/components/RequirementComparison.vue, frontend/tests/job-actions.spec.ts, frontend/e2e/workflow.spec.ts.
- Decisions: preserved the existing revised heading; separate each verified posting quote from model cards, use full provider names, readable verdict badges and Required/Preferred labels. Stack on narrow screens and use three columns on wide screens. Simplified explanatory copy while retaining cautions about differing requirements and model agreement. Grouping and evaluation logic unchanged.
- Skills: frontend/test responsibilities applied; existing skill contents read earlier in session.
- Validation: 219 backend, 64 frontend, 1 legacy test, contracts and build passed. Updated assertions for intentional readable wording; retained verified-quote grouping checks. Affected browser/mobile accessibility workflow passed on rerun; initial attempt timed out during unrelated upload navigation before reaching the section.
- Remaining: no implementation work remains; no live model calls.
