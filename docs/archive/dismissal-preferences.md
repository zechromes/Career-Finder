# Dismissal preferences

Dismissal feedback personalizes **future shortlists**. It does not train the model
weights, change candidate-fit scores, modify shared requirements or prove that a
candidate is unsuitable. The user chose lower ranking rather than exclusion.

## How to use it

1. Choose **Dismiss** on a job card, table row or job detail page.
2. Optionally select a reason. Leaving the reason blank only hides that job.
3. For salary, enter a positive minimum amount, currency and hourly/yearly period.
4. Choose **Dismiss job**, or Cancel/Escape to leave everything unchanged.
5. Future searches (including Find more jobs) use feedback saved on the server.

Saved reasons are not listed on the results page; they are kept for future
searches and for later reference or evaluation. Restoring the job from the
Dismissed filter removes its feedback and restores visibility. The API can still
clear one job's feedback (`dismissal: null`) without restoring the job.

Feedback follows the owning saved resume into subsequent workspaces. A different
saved profile does not inherit it. Existing dismissed jobs with no recorded reason
do not silently acquire a preference. Current results and successful assessments
are not recomputed when a preference changes.

## Exactly what matches

| Reason | Lower-priority matches | Unknown / ambiguous behavior |
| --- | --- | --- |
| Role | Same title after case/whitespace normalization | Does not infer related roles, synonyms or transferable skills |
| Location | Same stated location after case/whitespace normalization | Does not infer a city from a suburb or penalize unknown locations |
| Seniority | Same explicit title-level group: graduate, entry, junior, mid or senior | Unmarked or mixed-level titles have no effect; senior group includes lead/staff/principal/director terms from existing filters |
| Salary | Explicit comparable stated pay wholly below the supplied minimum | Unknown pay, currency or period stays unaffected |
| Other | Reason recorded for reference only | No ranking effect |
| No reason | Original job hidden only | No ranking effect |

Salary recognition is intentionally narrow. It requires a salary/pay/rate label
nearby, an explicit supported currency code (AUD, USD, GBP, EUR, CAD or NZD),
a fixed amount or closed range, and an explicit hourly/yearly period. For example,
`Salary AUD 70k–90k per year` is below an AUD 100,000/year preference; a range ending
at AUD 110,000 is not. Bare dollar signs, open-ended ranges, missing periods,
multiple offers and mixed currencies are not interpreted. There is no exchange-rate
conversion, hourly-to-annual conversion, estimated pay or inferred currency.

## Where ordering changes

Feedback is read once when a search worker starts. Later edits apply on the next
search. After semantic/BM25 retrieval and location filtering, matching postings
move below nonmatching postings in the retrieved candidate pool. Ordering within
each group remains unchanged, and repeated matching reasons do not compound a
penalty. Existing automatic early-career title prioritization remains primary.
Top-K is applied after these steps. Choosing All jobs retains every retrieved job.

Feedback does not expand board collection or change explicit search constraints.
It can change which jobs fit into a limited shortlist. The results dashboard still
uses candidate-fit scores and its selected sort mode; it does not rewrite old
scores to simulate preference learning. No improvement in human matching accuracy
has been measured; tests use synthetic cases, not a human-labeled held-out set.

## Persistence and API

`PUT /api/searches/{run_id}/actions` retains the existing `key`, `action` and `value`
fields and accepts optional `dismissal` details for a true dismissal:

```json
{
  "key": "https://example.test/job",
  "action": "dismissed",
  "value": true,
  "dismissal": { "reason": "location" }
}
```

Salary details use `minimum_salary`, `currency` and `period` (`year` or `hour`).
The server derives title/location/seniority from a job actually in the workspace;
it does not trust client-supplied posting attributes. Invalid feedback returns 422
without updating the action. An explicit `dismissal: null` clears feedback without
restoring the job. Setting `dismissed` false also clears it. Legacy updates that
omit feedback continue to work and do not invent reasons.

GET/PUT responses add `dismissal_feedback` alongside the existing `actions` map.
Saved profiles add the same optional map with an empty default. Profile editing,
creation from a source workspace and subsequent workspaces preserve it. Public
posting caches and provider assessment caches are unchanged; feedback is never
stored in the shared index or included in model prompts.

The browser keeps local pending updates when synchronization fails and retries
when the workspace is reopened. A visible sync error means server-side search
may not yet use the local choice. Queued edits retain the latest reason; delayed
responses cannot replace newer edits. Runs retain existing expiry behavior;
saved-profile feedback persists with that profile. There are still no accounts.

## Verification and limits

Regression coverage checks profile isolation and persistence, undo/remove behavior,
legacy requests, invalid salary input, strict unknown-data handling, pending-write
races, real local retrieval before top-K, All-jobs retention, shared-index isolation
and the existing early-career safeguard. Browser checks cover optional reasons,
cancellation, reload, salary fields, keyboard controls, accessibility and continued
searches. No paid provider requests are necessary for this feature.

Implementation: [API](../backend/runs_api.py),
[schemas](../backend/schemas/contracts.py),
[preference matching](../backend/search/preferences.py),
[retrieval](../backend/search/retrieval.py),
[browser state](../frontend/src/stores/jobs.ts),
[dialog](../frontend/src/components/DismissJobDialog.vue).
