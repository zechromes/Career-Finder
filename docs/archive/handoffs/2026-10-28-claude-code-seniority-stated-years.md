# Seniority rule: stated years for mid-level profiles

- Objective: stop senior titles alone from excluding jobs for a profile that is early-career only by years (user decision: change ranking, model instructions and scoring together).
- Tool/model: Claude Code, Claude Opus 5.5. Branch: improve-seniority-matching.
- Skills: evaluation-manager, backend-engineer, test-engineer (agents/skills/).
- Changed: backend/evaluation/candidate_fit.py (stated_experience_years, posting_exceeds_candidate_level; guard and RECRUITER_PROMPT rule 3), backend/search/retrieval.py (ranking key); tests/test_seniority_priority.py (+2), tests/test_evaluation_reliability.py (+1); docs EVALUATION_MODELS.md, matching-improvements.md, project-context.md.
- Decision: graduate/entry/junior profiles and director/head-of/chief titles keep the title rule. Other early-career-by-years profiles are held back by senior/lead/staff/principal titles only when the posting states more years than the profile. Prompt text is in the assessment cache key, so old assessments are not reused.
- Evidence (pilot, 82 human labels, single profile, also used to design the rule): senior-titled good fits held back 15 -> 0; senior-titled not-a-fit 15 -> 11; pool held back 71 -> 31 of 158. No live search or model calls; final shortlist recall not re-measured.
- Checks: ./scripts/check.sh passed (270 Python, 79 frontend, legacy, build). E2E not needed (no UI/API change).
- Unresolved: needs held-out labels from a fresh search to confirm; 4 senior not-a-fit jobs without stated years now rank normally.
- Next owner: user runs a new search and labels a fresh dataset; then improvement #3 (irrelevant shortlist jobs).
