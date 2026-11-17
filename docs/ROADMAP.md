# Roadmap

Open work gathered from earlier handoff notes, reviews and specs, as of
17 November 2026. These are candidates, not commitments; product items need a
decision first ([PRD.md](PRD.md#11-decisions-needed-before-building)). Items are
removed when done and recorded in [DECISIONS.md](DECISIONS.md).

## 1. Measure matching quality (highest priority)

Nothing about ranking or assessment accuracy is established beyond one pilot.

- **Build a labeled baseline.** Use the job-action dataset and hand labels across
  several profiles, including jobs outside the shortlist. Keep tuning and held-out
  profiles separate. Report recall@K, strong-match precision, label coverage and
  missed matches with `scripts/measure_matching.py`. Owner: evaluation manager.
- **Review the `hyde` default.** It became default without a measured gain. Compare
  `hyde` vs `evidence` (and `skills`) on held-out labels before keeping it.
- **Confirm the 28 Oct seniority rule** on a fresh search; four senior-titled
  unsuitable jobs without stated years now rank normally.
- **Check the 30 Oct model-decision change.** Strong-match rates before and after
  on the same labels; models were very conservative in the pilot.
- **Automatic shortlist cost.** Measure duration and model cost of evaluating
  whole pools up to 200, and read the strong matches still missed.
- **Irrelevant shortlist jobs.** Pilot shortlists included clearly unrelated roles;
  needs failure analysis before tuning. If good jobs are shortlisted but ranked low,
  consider a requirement-coverage score on the shortlist.
- **Title screening** in collection can drop relevant jobs before descriptions are
  read; measure on labels.

### Cost experiments (from the 17 Nov pipeline review)

Each one trades recall for cost, so each needs the labeled baseline first and
runs alongside the real pipeline without deciding anything (shadow mode) until
measured. Pilot evidence against cutting early: a 100-job shortlist missed 8–10 of
27 strong matches, and similarity ranking did worse than random order.

- **Cross-encoder rerank after RRF.** Rerank the retrieved pool alongside the
  current order and compare recall at 15/50/100 on held-out labels. Shrink the
  shortlist only if strong matches are not lost. Needs a decision between a local
  model (adds sentence-transformers/torch) and a paid rerank API.
- **Cheap gatekeeper in shadow mode.** Run `gpt-4o-mini` beside the full evaluation
  and record how often it would have rejected a job the full evaluation rated a
  strong match. Adopt only if that rate is near zero. Revisits the rejected
  "cheap model rejects first" proposal ([DECISIONS.md](DECISIONS.md#proposals-not-adopted)).
- **Years as a hard filter.** Only for a quoted `must_have` years requirement far
  above the profile; measure false rejections on labels first. Missing years must
  never filter. Revisits the rejected pre-retrieval facts filter.
- Until measured, cost can be cut without losing recall by choosing a fixed
  shortlist (50/100) and a single evaluation model (the default).

## 2. Retrieval

- **Job-side skills** (unbuilt Phase 4 of the Nov query spec): extract required and
  nice-to-have skills and seniority per posting with one shared skill vocabulary,
  cache by posting, add a skill-overlap score and show missing required skills on
  the job card.
- **Skill alias map** shared by profile and job extraction ("JS" → JavaScript),
  plus alias text for BM25.
- **BM25-only low-weight skills:** feed dropped low-evidence skills (and model names
  such as U-Net) to BM25 only, instead of dropping them.

## 3. Product

- **Job-action datasets are never deleted.** Decide whether deleting a profile or
  run should delete its dataset.
- **Expiry visibility:** show when a run's results will expire (7 days).
- **Repeat-search coverage:** better scheduling and clearer budget explanations.
- **Uncertainty vs mismatch:** present unknown evidence separately from a
  demonstrated gap in the UI.
- **Tailored resume:** page footer ("Name, page 2") skipped; check printing in
  Safari and against a real ATS parser.
- Out of scope until decided: user accounts, LLM cost accounting, live link checks,
  cover letters, automatic applications.

## 4. Cleanup

- `/eval/datasets/{dataset_id}` is still served as a page route although review
  datasets were removed (`backend/routers/pages.py`).
- `frontend/src/components/ReviewGuide.vue` is unused.
- The [animated flowchart](images/application-workflow-flowchart.html) and GIF show
  the pre-30 Oct computed score as the verdict; redraw or retire them.
- Live checks never done: LangSmith delivery, Google Jobs and Adzuna end to end,
  browser checks of the tailored resume, full e2e run after the November changes.
