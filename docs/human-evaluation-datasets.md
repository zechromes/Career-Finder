# Review datasets: fit, extraction quality and evidence support

The application now supports human review of the first three evaluation-quality
improvements: a frozen evaluation dataset, requirement-extraction measurement,
and semantic evidence-support review. Open `/eval` in the browser (there is no header link), choose a
finished search, select **Create review dataset**, then open the dataset.
Restart the backend after installing this change.

## Quick start: label about 30 jobs

The dataset page opens in **Quick labeling**. It shows one job at a time; answer
**Good fit**, **Not sure** or **Not a fit** (or press 1, 2 or 3). Each answer is
saved immediately and the next job appears. Enter your name or initials once; the
browser remembers it. A reason is optional. **Skip for now** and **Change previous
answer** are available.

Jobs appear in a fixed random order derived from the dataset ID, so the first
jobs you label form a random sample of the whole pool, including jobs outside the
app's shortlist. Whether the app shortlisted a job is hidden while you label, so
it cannot influence the answer. About 30 labels give a first, rough result; the
page says so when you reach 30. You do not need to label every job.

**Results so far** explains the outcome in plain words: how many of your good
fits the app's shortlist included, what share of the labeled jobs it shortlisted
were good fits, and which good fits it missed. Not sure answers and AI-assisted
reviews are not counted. With fewer than 20 decisive labels, the page warns that
the numbers are rough.

## Results by RAG stage

### Ingestion recording

Searches started after 28 October 2026 save `ingestion.json` in the run folder:
board totals, exact drop counts by stage/reason/board, and up to 120 filtered,
60 description, 60 limit and 50 duplicate postings (descriptions truncated to
6,000 characters). It is private run data, removed with the run after 7 days, and
never sent to the browser's live search snapshot. A search served from the
collection cache records no drops and marks the record incomplete. A review
dataset copies the record and its dropped postings, excluding any later found in
the search pool. Dropped-job labels are kept separate from pool metrics.

The results have four tabs. All of them use only your Good fit and Not a fit
labels; the reference is human judgment (supervised evaluation). The app is not
trained on these labels.

- **Overview** traces each of your good fits: recommended as a strong match,
  shown as needs review, rejected by the AI, shortlisted without a saved verdict,
  or not shortlisted.
- **1. Ingestion** shows how many postings each board returned, how many reached
  the search pool, and why the rest were dropped (location, posting age, search
  filters, no usable description, collection limits, duplicates). **Label dropped
  jobs** opens a quick-labeling queue of postings dropped by filters, missing
  descriptions or limits (about 20 is enough); the table then shows how many good
  fits each drop reason removed. Jobs already in the workspace are counted, not
  stored or labeled. A **duplicate check** asks whether merged pairs were really
  the same job. A label-free **search text check** reports how many of the AI's
  requirement quotes survive the cleaning applied before indexing.
- **2. Retrieval** reports observed shortlist recall and precision, and lists good
  fits that were not shortlisted, flagging titles the seniority rule treats as
  experienced-level for the profile. Rank positions were not saved, so
  rank-based measures are unavailable. **Compare embedding models (paid)** re-ranks
  the source workspace's pool with each OpenAI embedding model and scores the top
  K (up to 20) against your labels; it needs the original search (7 days) and
  isolates the embedding model, without seniority or dismissal adjustments.
  **Replay with each seniority rule** (`POST /api/review-datasets/{id}/replay`)
  re-runs the production ranking of each recorded search on its frozen pool, then
  applies the earlier title-only rule and the current stated-years rule with the
  original shortlist size, and scores both against the same labels. It reports
  observed recall, precision on labeled jobs, labeled good fits and not-fits each
  rule adds, and how much of the original shortlist the rule reproduces (a
  fidelity check for the title-only rule; dismissals made before the original
  search are not replayed). The first replay embeds the role and profile queries
  once with `text-embedding-3-small`, which needs the original search; the
  relevance order is then saved as `relevance.json` in the dataset folder, and
  later replays make no provider calls. No assessments run: jobs a rule adds to
  the shortlist have no model verdict.
- **3. Generation** compares each model's saved verdict, and the app's combined
  verdict, with your labels on shortlisted jobs: agreement on your good fits
  (strong match / your good fits), strong-match accuracy (your good fits / model
  strong matches) and good fits rejected (model not suitable). Failed assessments
  are counted separately, never as disagreement. Only shortlisted jobs were
  assessed, so generation results say nothing about jobs outside the shortlist.

Snapshots created from 28 October 2026 store each provider's saved verdict and the
app's combined verdict. For an older snapshot, add them once from the source
workspace (while it has not expired):

```sh
python scripts/add_review_verdicts.py            # the only dataset
python scripts/add_review_verdicts.py --dataset-id <id>
```

A row is used only when its URL, title and company identify one frozen job and its
requirement verdicts equal the evidence frozen in the snapshot, so a later
re-evaluation is never attached. Labels are not modified. If nothing matches, the
dataset is left unchanged; `verdicts_added_at` records when verdicts were added.

**Detailed review** (`?mode=detailed`) keeps the full workflow below for checking
extracted requirements and model evidence. Quick labels keep any detailed
judgments already saved for a job.

## What is generated

A snapshot contains the workspace profile and profile text, target roles, the
entire available posting pool, an input fingerprint, capture time, source URLs,
previous-shortlist membership, and saved per-provider requirement assessments.
This uses the same scope loader as `/eval`, including its explicit limits and
saved-results-only fallback. A snapshot does not invent missing postings or call
models to generate human ground truth. It does not start new scraping or inference.

Jobs outside the earlier shortlist remain included. Tags identify explicit
seniority titles, provider disagreement and missing assessments for review
navigation; tags are heuristics, not judgments of suitability. Use **Jump to a
posting** to find outside-shortlist jobs. The full frozen pool is retained, rather
than selecting only favorable examples.

Snapshots keep saved assessments only when the posting description matches the
frozen posting. Missing or changed assessments are marked unavailable. Shared
extractor criteria are deduplicated across evaluators by their requirement-set
identity and canonical fields. Older provider-defined criteria are marked legacy
and excluded from shared-extraction metrics. Evidence support can be reviewed for
both formats. No missing extractor output is fabricated.

The capture timestamp records snapshot creation, not the original posting or
collection date. Source collection timestamps and historical prompt/configuration
versions are not reconstructed when unavailable. Historical outputs may reflect
earlier target-role preferences. This is a review of saved evidence, not a claim
that every historical model call had identical settings.

## Detailed review workflow and labeling guide

The review page starts with a three-step guide and an expanded candidate profile.
Start with **Candidate fit** and its worked examples; enter your name or initials,
choose a label, explain the evidence, and select **Save job review**. A fit-only
review is valid. Unanswered requirement/evidence fields stay unreviewed, and you
can return to them later.

For a deeper review, reveal the saved model outputs and choose **Check job
requirements** or **Check model evidence**. Each step explains its judgments with
examples; switching steps preserves unsaved answers. Model outputs remain hidden
on each newly opened posting. Save before navigating to another posting. The save
bar identifies unsaved changes, and the progress/quality metrics are expandable
so they do not distract from the first decision. Metrics use saved reviews only.

Read the **frozen candidate profile** and full posting first. Model outputs are
hidden until you explicitly reveal them.

1. **Candidate fit:** Strong fit requires evidence for mandatory requirements;
   For review covers uncertainty or missing evidence; Not suitable requires a
   demonstrated mismatch. Explain the decision. Missing information does not
   establish inability. Unreviewed is a separate state.
2. **Requirement extraction:** For each criterion, judge whether it is valid,
   correctly stated, and not a duplicate. Check qualifications, responsibilities,
   eligibility, experience, alternatives, quantities, and negation. Record the
   correct importance independently: mandatory, preferred, or unclear.
3. **Omissions:** Add missing requirements with supporting posting quotes.
   Review the entire posting before checking the extraction-completeness box.
   Every shared criterion must have a correctness judgment before this box can
   be saved. A quote must occur in the posting after case/whitespace normalization.
4. **Evidence support:** Decide whether the quotes actually justify the model's
   verdict and explanation. Supported means the evidence entails the claim;
   Unsupported means it does not; Uncertain means you cannot decide. Separately
   record your own met/partial/not met/unknown verdict and correction notes.
   A found quote can still be irrelevant or misleading. For unknown verdicts,
   absent profile evidence can justify uncertainty, not a claimed mismatch.
5. Enter reviewer initials/name and **Save job review** before moving on. If an AI
   suggestion informed any judgment for this job, tick **I used an AI suggestion for
   this review**. The review is kept but excluded from every metric.
   Download the saved dataset, labels and metrics when finished.

Ask a second reviewer to independently assess difficult cases, and document
resolved disagreements in notes. This version records the latest reviewer per job,
not a multi-reviewer adjudication history. Each dataset is currently marked
**pilot**. With one profile, there is no credible profile-level held-out split.
Add independent, consented profiles before claiming generalization; keep future
tuning and held-out cases separate. Do not label synthetic examples as real cases.

## Metrics

Metrics use saved human labels only. Empty denominators are displayed as
**Not reviewed**, not zero accuracy.

| Metric | Definition |
| --- | --- |
| Observed shortlist recall | Human strong fits in the previous shortlist / all human strong fits in the pool |
| Retrieval label coverage | Binary strong-fit/not-suitable labels / pool size; For review is excluded |
| Extraction precision | Human-correct shared criteria / shared criteria with a correctness judgment |
| Extraction recall on complete reviews | Human-correct shared criteria / (human-correct shared criteria + human-recorded omissions), only on jobs marked completeness-reviewed |
| Importance accuracy | Correct importance assignments / human-judged importance assignments on accepted criteria |
| Support rate | Supported judgments / (supported + unsupported judgments), per provider and model |
| Verdict agreement | Model verdicts matching human verdicts / human-reviewed verdicts |

Metrics also exclude every review marked AI-assisted and report how many were
excluded. Reviews saved before this flag existed count as human reviews.

Reports include coverage, uncertain-support counts, omissions and missed labeled
positives. Unreviewed and uncertain support are never silently treated as negative.
Quote-presence flags are shown separately from semantic support judgments.
Extraction scores aggregate available shared outputs; model/version provenance
remains in the snapshot. Partial review cannot establish full-pool recall, and
saved-results-only snapshots cannot measure recall over the original collection.

These instruments do not change production scores or prompts. Actual quality
improvements require reviewing the dataset, identifying failures, then comparing
proposed changes on the same labeled cases with held-out evidence. No quality gain
has been established simply by generating the dataset or passing regression tests.

## Persistence and privacy

`data/evaluation_datasets/<id>/dataset.json` is the frozen evidence;
`reviews.json` holds human judgments, reviewer attribution, revision and update
time. Files are written atomically with restrictive permissions, and the directory
is excluded from Git. Concurrent stale saves return HTTP 409 rather than replacing
newer reviews. Human reviews never rewrite the dataset or original workspace.

Review datasets survive server restarts, workspace deletion and workspace expiry.
They contain private profile text and assessment evidence and stay until deleted.
Use **Delete review dataset** under Review datasets on `/eval`; it asks
for confirmation, removes the snapshot and all its reviews, and leaves the source
workspace unchanged. Downloaded JSON is also private. Access
follows the existing local application model: there is no account isolation.

## Implementation and commands

- Schemas: `backend/schemas/review_datasets.py`.
- Snapshotting, validation and metrics: `backend/evaluation/review_datasets.py`.
- UI: `frontend/src/views/ReviewDatasetView.vue`, `ReviewDatasets.vue`,
  `QuickLabel.vue` and `StageResults.vue`.
- `GET/POST /api/review-datasets`: list or create snapshots.
- `GET /api/review-datasets/{id}`: read immutable evidence and separate labels.
- `DELETE /api/review-datasets/{id}`: delete the snapshot and its reviews.
- `PUT /api/review-datasets/{id}/jobs/{job_id}`: save a revision-checked review;
  `ai_assisted: true` keeps it out of metrics.
- `GET /api/review-datasets/{id}/metrics`: compute metrics from human labels.
- `/eval/datasets/{id}`: browser review page, including direct links and refresh.

The CLI can prepare the only saved-profile workspace without importing the app or
expiring other workspaces:

```sh
python scripts/prepare_evaluation_dataset.py
# If several saved-profile workspaces exist:
python scripts/prepare_evaluation_dataset.py --source-id <workspace-id>
```

It prints counts and the review URL, never profile or posting contents. Generated
snapshots begin with zero human labels. Testing uses synthetic fixtures and mock
providers; tests do not establish real-world recommendation accuracy.
