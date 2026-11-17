# Decisions

Why Career Tracker works the way it does, newest first. Each entry gives the
decision, the reason or evidence, and whether it still holds. Current behavior is
in [Architecture.md](Architecture.md). The original handoff notes and guides these
entries come from are in [archive/](archive/).

"At the user's request" marks product choices made by the owner rather than
measured improvements. Unless stated, no change below was validated on held-out
human labels.

## November 2026

**Mid-Nov (after 12 Nov) — Tailored resume per job.** At the user's request, a job's Tailored
resume tab makes one Claude call that rewrites the uploaded resume for that
posting using only its facts; unverified skills and figures are flagged and unmet
requirements are listed apart. Layout follows the UNSW Employability resume
guide in a single ATS-friendly column, and printing uses zero page margins so
browser headers don't appear. The guide's page footer was skipped because browser
header/footer handling makes it unreliable. *Current.*

**12 Nov — Labeled dataset from job actions.** Applied and Dismiss actions write
labels into `data/evaluation_datasets/` in the old review-dataset format, so
labels accumulate without a separate labeling tool. Location, salary and other
dismissals are preferences, not fit, so they get no fit label. Nothing was
backfilled. *Current.*

**12 Nov — `hyde` is the default query builder.** At the user's request. The pilot
replay showed no gain over `evidence` (within one strong match at each cut), so
this is not an accuracy-backed change and evaluation-manager review has not
happened. Tests pin `QUERY_BUILDER=evidence` so they make no live calls. *Current;
review pending ([ROADMAP.md](ROADMAP.md)).*

**Mid-Nov (after 12 Nov) — Retry progress, failure grouping, evidence list, verdict chips.**
Retries got their own counters instead of reusing search-wide ones; failures are
grouped by model and reason; the per-section evidence carousel was replaced by a
sorted, filterable list; one shared verdict chip style. *Current.*

**10 Nov — Automatic shortlist is the default.** Pools of ≤ 200 indexed jobs are
evaluated whole, larger ones keep the top 100. Motivation: on the pilot replay a
100-job shortlist still missed 8–10 of 27 strong matches. *Current.*

**9 Nov — Default shortlist 100 (was 50); HyDE builder added.** On the one labeled
pilot pool (158 jobs, 27 strong), every builder shortlisted 5–6 strong matches at
50 and 17–19 at 100, below a random order with the same seniority step (10.6 and
21.3). Similarity ranking didn't separate strong from unsuitable postings there,
so more of the judgment was left to evaluation. Superseded by Automatic on 10 Nov.

**4 Nov — Normalized query weights.** Roles get half a vote, soft skills none
(most postings ask for teamwork), skill groups weigh the average rather than the
sum of their skills, all weights sum to 1. Reason: soft skills, role titles and
long skill lists dominated retrieval. A model-generated query builder spec was
not built at the time, because retrieval only picks the shortlist and fit is judged
by evaluation (HyDE later covered the role part). *Current.*

**3 Nov — Evidence-weighted queries, `skills` builder, job-ad style sentences.**
Skills are weighted by the resume entries that show them (recency × entry type),
off-target skills are dropped, skill groups are searched as job-ad sentences, each
entry is its own experience query. `skills` was added for comparison so entry
domain words (for example HR records) stop pulling in that domain. Suggested target
roles may include title variants but stay user-edited suggestions; adjacent titles
are never added silently. *Current.*

**3 Nov — Google Jobs and Adzuna as boards; Glassdoor removed.** Google Jobs via
SerpApi is off by default because every page is a paid search, and doesn't serve
Australia or New Zealand. Adzuna is capped at 2 requests per search to protect the
free tier and returns snippets only. *Current.*

**2 Nov — Pipeline playground replaced review tooling.** At the user's request,
`/eval` became a per-stage playground (Upload, Ingestion, later Retrieval with
relevance marks), and review datasets, quick labeling, model-comparison
experiments, retrieval replay and their scripts were deleted. *Current.*

**2 Nov — LinkedIn descriptions via the app's own fetch.** JobSpy opened every job
on a results page back to back and LinkedIn answered with 429. The app now fetches
LinkedIn pages itself with a 2 s gap, the description cache and the budget. *Current.*

## October 2026

**30 Oct — Models decide the fit category.** Models return a category and no
numeric score (`model-decision-v1`); seniority rules become defaults a model can
set aside with a quoted reason. The code rubric is still computed but only stored
for comparison. Also: a requirement the resume doesn't mention is `not_met`
(it was `unknown`), which alone can't reject a job; evaluators receive the
original resume text. Reason: in the pilot, models almost never said strong match
and 1,048 mandatory verdicts were unknown because extraction had dropped the
resume's projects. Effect on strong-match rates not yet measured. *Current.*

**29 Oct — Projects in the profile.** Projects are extracted and passed to
evaluators as skill evidence; they never add professional years. *Current.*

**28 Oct — Seniority uses stated years for profiles early-career only by years.**
Senior, lead, staff and principal titles hold such a profile back only when the
posting states more years than it has; graduate/entry/junior profiles and
director/head-of/chief titles keep the title rule. Evidence: in an 82-label pilot
(one profile, also used to design the rule) all 15 senior-titled good fits stated
no years; held-back good fits went 15 → 0, held-back unsuitable 15 → 11, held-back
pool 71 → 31 of 158. Needs held-out confirmation. *Current.*

**28 Oct — Ingestion drops recorded.** Each search records dropped postings by
stage and reason, to see whether good jobs are lost before retrieval. Observes
only. *Current.* (Requirement quotes survived job-text cleaning 1,853/1,872 times in
the pilot, so cleaning isn't the cause of retrieval misses.)

**27–28 Oct — Review datasets, experiments, quick labeling.** Built to measure
quality with human labels; AI-assisted labels were excluded from metrics so models
weren't measured against themselves. *Removed 2 Nov.*

**27 Oct — Dismissal reasons lower future ranking.** The user chose lower ranking
over exclusion, so a wrong preference can't hide a job. Matching is exact and
conservative; feedback never reaches models or the shared index. *Current.*

**27 Oct — Results page state kept across job details; Status column in table.**
*Current.*

**26 Oct — Requirement quotes copied by code from line ranges** (policy v4–v5).
Prompt fixes didn't stop the model from paraphrasing quotes, so it now picks line
ranges and the backend copies the text. OpenAI calls use `strict=True` JSON
schemas because the SDK default was non-strict. Unsupported section labels are
cleared instead of failing. Retries get field-specific feedback. *Current.*

**26 Oct — Launcher no longer opens a browser tab.** *Current.*

**23 Oct — Evaluation streaming telemetry; action race fixes.** Token usage, TTFT
and TPOT recorded on model spans when tracing is on. A stale sync response could
revert Applied/Saved during evaluation; confirmed writes now bump the edit
version. Menu clicks survive focus loss. *Current.*

**22 Oct — Shared requirement extraction.** Requirements are extracted once without
the resume, so all three models answer the same questions and denominators match.
No fallback to per-model extraction on failure. *Current.*

**22 Oct — Gemini: no proactive pacing; back to Argon.** Gemini was briefly reverted
to 3.6 Flash after rate-limit failures, then restored to Argon at the user's
request; RPM pacing defaults to off, backoff still applies. *Current.*

**22 Oct — Requirement evidence UI simplified.** Model feedback cards removed;
evidence grouped by posting section. *Superseded 12 Nov by the evidence list.*

**21 Oct — Stronger evaluation tier, low reasoning, GPT timeout 180 s.** At the
user's request GPT moved to `gpt-6.1-sol` and Gemini to `gemini-4-argon` beside
Claude Sonnet 5.5, with low reasoning/thinking to cut latency. GPT's timeout went
60 → 180 s after timeouts. Model and reasoning settings are part of the
assessment cache key. Quality and latency effects unmeasured. *Current.*

**21 Oct — Optional LangSmith stage tracing.** Counts-only: payloads, prompts and
text never leave the app. Child spans repeat `parent_run_id` on update (the SDK
otherwise cleared it). *Current.*

**20 Oct — Adaptive collection replaced fixed per-board quotas.** One shared budget
across boards, visit-all-first, yield-based expansion, early filtering. The soft
deadline was 120 s then; it is 240 s now. *Current.*

**20 Oct — JobSpy `fetch_description=True`; no timed cooldown.** At the user's
request. A 429 stops that board for the current collection only, so a manual retry
can start immediately. Retry scraping reruns failed boards in place. *Current,
except LinkedIn descriptions (2 Nov).*

**19 Oct — Shared title screening and description cache for JobSpy boards.** Cuts
detail requests; may drop relevant jobs with unusual titles (unmeasured). *Current.*

**17 Oct — Review findings addressed.** Partial agreement shown with a provisional
average; contextual work-type and title-boundary seniority matching replaced
substring checks; fixed per-group retrieval weights; one combined upload request;
private 7-day assessment cache and per-provider waves of 15; job actions persist
with the saved profile. *Current (missing evidence later changed on 30 Oct).*

**15 Oct — Collection cache and shared posting index.** Identical searches reuse
results for 15 minutes; postings are indexed once and versioned, with per-search
scopes. HNSW `ef_search` raised 100 → 500 after a filtered synthetic benchmark
gave 92% ANN recall@20 at 100 and 100% at 500 (98.33% on a separate seed). Warm
retrieval ~3.3× faster on synthetic data. *Current.*

**13–14 Oct — Code organization.** Routes moved to `backend/routers/`, schemas to
`backend/schemas/`; import-only compatibility wrappers removed; upload waits for
extraction instead of returning a placeholder ID. *Current.*

**7–8 Oct — Workflow foundations.** Three providers run concurrently and the
shortlist is published as pending rows; profiles auto-save after a search;
automatic early-career seniority ordering; Best match default sort; Find more jobs
appends to the same run, and a changed profile in a run with assessments is
rejected rather than mixed. *Current.*

## Proposals not adopted

| Proposal | Decision |
| --- | --- |
| Cheap model rejects first, strong model assesses survivors | No. An early false rejection permanently loses recall. Would need shadow-mode false-negative measurement first. |
| Pre-retrieval facts extractor (salary, work type) as a hard filter | Not yet. Adds a call per posting; needs accuracy and cost measurement; only source-verified facts could filter. |
| Explicit provider prompt-cache controls | No. Providers differ in eligibility and pricing; savings unverified. A stable prompt prefix allows automatic caching. |
| Stop after N matches or a budget | No. Would hide errors behind uncalibrated "strong" predictions. |
| Replace Chroma with NumPy | No. Doesn't improve relevance; Chroma keeps persistence and recovery. |
| Silent adjacent-title expansion | No. Selected roles are the user's scope; suggestions are editable instead. |
| Live link / ghost-job checks | Not built. HTTP 200 doesn't prove a vacancy; login walls and bot checks interfere. |
| Model-generated query builder (Nov spec) | Partly built: HyDE role ads. Job-side skill extraction is on the roadmap. |
