# Task: Replace the profile query builder with evidence-based extraction and weighting

## Context
Career Signal matches a candidate profile (extracted from a resume PDF) against job postings using hybrid retrieval: Chroma vector search + BM25, fused with weighted reciprocal rank fusion (RRF). Roles, skills and experience each get one vote, split among their queries.

The current query builder has these problems:
1. **Role query is too thin**: a single short title (e.g. "AI Engineer") carries a full vote but embeds as a vague point.
2. **Skill clusters are grouped by category, not evidence**: core skills (Vue, FastAPI) sit in the same cluster as barely-used ones (Unity, Laravel, Flutter, Base44), so off-target jobs (mobile, game dev) get pulled in. Every skill in the skills section counts as much as skills proven in real work.
3. **Cluster text is label + keyword list** ("AI applications and retrieval: RAG, ..."), which doesn't resemble job-posting language. Some clusters are lists of names that job ads rarely mention (CSRNet, U-Net, VGG-19).
4. **Experience queries contain noise**: header lines ("Project | personal/academic/employer context not specified | September 2026 – Present"), company names, dates and figures ("$3,600 per scope leak") get embedded.

## Goal
Build the queries from **structured, evidence-based extraction of each experience**, so a skill's weight reflects where and how recently it was actually used.

## Before you start
- Read `AGENTS.md` and follow its roles and conventions.
- Locate the current profile extraction, query building, retrieval/RRF and job-ingest code. Summarize the current flow and the files involved.
- **Propose a short implementation plan and wait for my approval before changing code.**

## Phase 1: Structured experience extraction
Extend profile extraction so each experience (job, internship, project, hackathon) becomes:

```json
{
  "title": "string",
  "type": "job | internship | project | hackathon",
  "start": "YYYY-MM",
  "end": "YYYY-MM | present",
  "actions": ["capability statement, no names/dates/figures"],
  "hard_skills": ["normalized skill names"],
  "soft_skills": ["only if explicitly evidenced"],
  "domain": "string"
}
```

Extraction rules (put them in the LLM prompt and validate the output):
- Only extract skills **stated or clearly demonstrated** in the text. Do not infer or inflate (e.g. "used Claude" ≠ "prompt engineering expert").
- `actions` are rewritten as job-posting-style capability statements: no company names, no dates, no monetary figures, no award names, and no extractor boilerplate such as "context not specified".
- Normalize skills through a single shared vocabulary/alias map (e.g. "JS" → "JavaScript", "LLMs" → "Large Language Models"). Put the map in one module so job-side extraction can reuse it.
- Validate with a schema (Pydantic). On failure, retry boundedly; then fall back to the current behaviour rather than crashing.

## Phase 2: Evidence-based skill weights
Compute a weight per hard skill from the extracted experiences:

```
weight[skill] = Σ over experiences using skill: type_factor[type] * recency(end)
              + listed_only_bonus (if the skill appears only in the skills section)
```

Starting defaults (put them in config, not hard-coded):
- `type_factor`: job 1.0, internship 0.8, project 0.8, hackathon 0.6
- `recency`: ≤12 months (or present) 1.0, 1–3 years 0.6, older 0.3
- `listed_only_bonus`: 0.3

Soft skills are **excluded** from skill weights and from retrieval queries.

## Phase 3: Rebuild the queries
1. **Skill clusters**: group skills into clusters (LLM/RAG, backend, frontend, ML/data, databases, tooling), then **split clusters by evidence**: high-weight skills form the cluster query; low-weight skills (below a configurable threshold) are dropped from dense queries.
   - Each cluster's vote share = sum of its skill weights, normalized within the skills vote.
   - Write each cluster as a **requirement-style sentence**, e.g. "Experience building LLM applications and RAG pipelines with LangChain, ChromaDB and hybrid retrieval (BM25 + reciprocal rank fusion)."
2. **Experience queries**: one query per experience, built **only from `actions`** (no header line). Vote share = `type_factor * recency`, normalized within the experience vote. Experiences with no relevant hard skills (e.g. HR administration) get near-zero weight for retrieval but stay in the profile.
3. **Role queries**: replace the single title with 2–3 hypothetical job descriptions (HyDE), generated from the top-weighted skills and most recent actions, written like a short job ad (title, 3–4 sentences of responsibilities and requirements, seniority). Split the role vote across them (e.g. 0.4 / 0.35 / 0.25).
4. **BM25**: keep the full, unfiltered skill list (including low-weight skills and model names like CSRNet, U-Net) as BM25 input only.
5. Keep the existing weighted RRF fusion; only the queries and weights feeding it change.

## Phase 4 (separate step, after Phases 1–3 are merged): job-side skills
- At job ingest, extract `required_skills`, `nice_to_have` and `seniority` using the **same vocabulary module**. Cache by `job_id`.
- Add `skill_score = Σ candidate_weight[s] for s in required_skills ∩ candidate_skills / len(required_skills)`.
- Return the missing required skills for the JobCard.
- Do not change job text cleaning or add chunking. Jobs stay embedded as one cleaned document. Keep raw job text stored for BM25 and the Claude fit evaluation.

## Constraints
- Don't change the embedding model or the vector collection in this task.
- Put the new builder behind a config flag (`query_builder: legacy | evidence`) so both can run side by side.
- Update the "Queries built from the profile" UI to show the new queries and weights (group, query text, weight), with low-weight/BM25-only skills shown separately.
- Keep functions small and typed; add docstrings where the logic isn't obvious.

## Tests and evaluation
- Unit tests: extraction schema validation, boilerplate/date/figure stripping in `actions`, skill normalization, weight calculation, vote normalization (each group sums to 1), and fallback on extraction failure.
- Add an evaluation script that runs the same profile through `legacy` and `evidence` builders and prints, for each, the top 20 jobs with titles and scores, plus counts of off-target categories (mobile, game dev, HR/admin) in the top 20.

## Done when
- Plan approved, Phases 1–3 implemented behind the flag, tests passing.
- Evaluation output shared, with a short note on what changed in the top 20.
- `AGENTS.md` / project context docs updated to describe the new query-building method.