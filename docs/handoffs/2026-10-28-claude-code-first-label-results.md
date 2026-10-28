# First human-label results (pilot)

- Objective: interpret the user's first quick labels; no application changes.
- Tool/model: Claude Code, Claude Opus 5.5. Branch unavailable: no Git repository.
- Skills: agents/skills/evaluation-manager/SKILL.md.
- Evidence: 41 human fit labels (none AI-assisted) on a 158-job pilot snapshot, single profile; 14 good fit, 16 not a fit, 11 not sure. Observed shortlist recall 8/14 (57%); precision on labeled shortlisted jobs 8/18 (44%); label coverage 19%.
- Finding 1: all 6 missed good fits have senior-level titles (senior/staff/lead/principal). The source search used automatic seniority with a mid-level profile, so the documented seniority rule ranked them lower. None of the 6 postings states an explicit years requirement (regex check on posting text). Product decision pending: keep the rule, or soften title-only seniority penalties when no years requirement is stated. Not changed.
- Finding 2: 10 of 18 labeled shortlisted jobs were judged not a fit, including at least one clearly unrelated trade role; this retrieval noise needs failure analysis before any tuning.
- Limitations: small pilot, one profile, no held-out split; percentages have wide uncertainty. Any rule change needs baseline vs proposed comparison on the same labels plus separate held-out labels.
- Next owner: user decides on finding 1; evaluation manager for any change.
