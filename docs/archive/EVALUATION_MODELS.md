# Job evaluation providers

New web searches evaluate shortlisted jobs independently with Claude, GPT, and
Gemini against one candidate-independent requirement list. An OpenAI extractor
(default `gpt-4o-mini`, override `REQUIREMENT_EXTRACTION_MODEL`) processes each
uncached posting once; resume content is never included in this extraction.
Their provider batches run concurrently; each retains its own worker
limits, pacing, and retries. Resume uploads use OpenAI exclusively.
The ranked shortlist is published with pending assessments before provider calls,
so candidates can inspect postings while evaluations continue. Scores remain
unknown until every scored assessment the job was sent for completes; incomplete verdicts remain
For review. Existing saved assessments are not automatically reevaluated.

Before each search, the app checks every model with one tiny request that
contains no resume or posting text (cached for ten minutes). The check starts
in the background when the search begins, so it normally finishes during job
collection; evaluation waits at most 20 seconds for an unfinished check and then
treats that model as available. A model whose
quota or spend cap is exhausted, whose credentials are rejected, or whose
configured model is unavailable is skipped, and the results page lists it under
"Some models were skipped". A quota, credential or model failure during an
evaluation also marks that model unavailable for the next search. Timeouts and
brief rate limits do not skip a model; the normal retry policy applies. A
skipped model is reported, never silently replaced by another provider. Its row
is marked skipped and saved with the failed jobs, so "Retry skipped models" (or
"Retry failed evaluations") assesses it later, and the completed row then joins
the combined verdict. A later skip never replaces a completed assessment. If no
model is available, a new search evaluates anyway so every failure is recorded.

A retry first checks only the models it would call, discarding their cached
answers so a model whose quota was just restored is used straight away. Jobs for
a model that is still unavailable are not re-sent: they stay saved for the next
retry and the page lists the model under "Some models were skipped".
`CAREER_EVALUATION_PREFLIGHT=false` turns the check off (the test script does).

The combined verdict needs a unanimous verdict from every model the
job was sent to, so a job evaluated while Gemini was skipped needs Claude and
GPT only.

Concurrency removes the wait for earlier provider batches; it does not reduce the
number of assessments or bypass quotas. Gemini has no proactive RPM limit by
default, retaining two concurrent evaluations and shared backoff after failures.
Actual completion time depends on provider latency and retries. No live speedup
has been measured.

## Configuration

The installed Google client supports `GOOGLE_API_KEY` / `GEMINI_API_KEY`, or its
configured Vertex AI authentication. Claude uses `ANTHROPIC_API_KEY`; GPT uses `OPENAI_API_KEY`.

Optional environment overrides:

GPT-6.1 Sol evaluations use `reasoning_effort="low"`; Gemini 4 Argon uses
`thinking_level="low"`. An explicit Gemini 3.6 Flash override also retains low
thinking. These settings apply to those exact model IDs; other
model overrides retain their provider defaults for compatibility. New assessment
cache keys include these settings; existing saved results are retained.
Lower reasoning aims to reduce latency, but latency and assessment quality have
not been measured against labeled cases. Supported settings are documented by
[OpenAI](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
[Google](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon).

| Variable | Default |
| --- | --- |
| `GEMINI_EVALUATION_MODEL` | `gemini-4-argon` |
| `CLAUDE_EVALUATION_MODEL` | `claude-sonnet-5-5` |
| `GEMINI_EVALUATION_WORKERS` | `2` |
| `GEMINI_EVALUATION_RPM` | `0` (no proactive pacing) |
| `CLAUDE_EVALUATION_WORKERS` | `4` |
| `GPT_EVALUATION_MODEL` | `gpt-6.1-sol` |
| `GPT_EVALUATION_WORKERS` | `4` |
| `GPT_EVALUATION_TIMEOUT_SECONDS` | `180` |

`CLAUDE_EVALUATION_MODEL` also writes the per-job tailored resume (one call per
request, outside the evaluation workers).

Worker counts are capped at 8. Set Gemini RPM to a positive integer to enable
request spacing, or 0 to disable proactive pacing; increasing workers does not increase provider quota. Gemini
requests have a 90-second timeout, a shared pacing/cooldown policy and up to two
retries. Three consecutive rate-limit responses stop further requests for that
evaluation batch. Explicit daily-quota, credentials, model-access and invalid-request
errors stop further submissions immediately. Already in-flight requests may finish.
Failed/skipped jobs and safe error categories are saved as `evaluation_errors`.
Claude uses a 180-second timeout and up to 16,000 output tokens (adaptive thinking
counts toward that limit); GPT uses 180 seconds by default, configurable with
`GPT_EVALUATION_TIMEOUT_SECONDS` (integer seconds, clamped to 30–600; invalid values
use 180). This is an SDK request timeout, not a total evaluation deadline; a retry
can extend elapsed time. Cancellation stops subsequent work but cannot instantly
interrupt an in-flight request. Both use one SDK retry. No automatic fallback sends
a failed request to another provider.

Assessments read every resume section from the profile under its own heading, and
since 30 October 2026 also the original resume text, marked as evidence that the
reviewed profile overrides where they differ; profiles uploaded before then have no
original text until the resume is uploaded again. Projects were added on 29 October
2026. On the 82-label pilot, 1,048 mandatory-criterion verdicts were unknown
because the model had no resume text to quote; the resume's projects section had
been dropped during profile extraction. Projects are evidence for skills only.
Each requirement verdict lists every supporting resume passage in `resume_quotes`
(usually one to three, from any section). Each quote is checked against the resume
on its own (`resume_quotes_verified`); one verified quote supports the verdict, and
`resume_quote` keeps the first verified quote for older consumers and saved results.
A requirement the resume does not mention is `not_met` with no resume
quotes; the prompt says that on its own it makes a job review, not not_suitable.

Since 30 October 2026 each model decides its own fit category, and the app uses it
as given (`score_method` `model-decision-v1`). Models no longer return a numeric
score: new jobs show only the verdict and are ordered by verdict, then shortlist
position (`shortlist_rank`); older saved jobs keep their scores. The prompt's
career-level and seniority rules are defaults a model may set aside only when the
posting gives a clear reason, stated with a quote in `rule_exception` and shown on
the job's evidence. The code rubric
below and the seniority/experience guards no longer change a verdict: they are
computed on the same assessment and saved as `rubric_score`, `rubric_category`
and `rubric_reason` for comparison against human labels (the reassessment
script that did this was removed with review datasets on 2 November 2026). The combined verdict is unchanged: every model
must agree. The prompt and schema are part of the assessment cache key. The
effect on strong-match rates has not been measured yet; compare on the same labels.

Matching prioritizes professional experience and responsibility over skills.
The prompt tells each model the seniority rules; the code guards below now feed
only the comparison rubric and the shortlist ordering. In the rubric,
graduate/entry/junior profiles cannot receive strong/review recommendations for
explicitly mid/senior roles. A profile that is early-career only by its years
(two years or fewer, with a mid or unknown career level) is held back by a senior,
lead, staff or principal title only when the posting states more years of
experience than the profile records; director, head-of and chief titles are always
held back. This change (28 October 2026) followed a pilot of 82 human labels in which
all 15 senior-titled good fits stated no years requirement; see
`docs/matching-improvements.md`. Unknown experience alignment requires review; a clear
mandatory experience gap is excluded. Academic study and projects do not count as
professional employment years. Older profiles use their saved years until regenerated.

The CLI accepts `--evaluation-model gemini`, `--evaluation-model claude`, or `--evaluation-model gpt`.
The web API retains the legacy `evaluation_model` field for compatibility, but
new web searches use every available provider. Tagged retries call only the
provider whose assessment failed and preserve successful assessments.
The old Python function `evaluate_jobs_with_claude` remains available for callers
that explicitly need Claude.

Dependencies are listed in `backend/requirements.txt`. Restart the backend after
changing configuration. Existing embeddings still use the project's embedding
provider; these settings affect only the job assessment stage.

New assessments include company information, a list of candidate requirements,
and salary only when stated in the posting. Missing company/requirements details
have explicit fallbacks; salary is hidden when absent. Older saved assessments
need a new search to populate these fields. Fit decisions and exclusion reasons
remain in the saved results. `/api/models/evaluation` supplies the configured model
IDs for display; `/api/evaluation-models` remains a compatibility alias.

## Partial results, scheduling and private reuse

Each provider processes the ranked shortlist in successive waves of 15. Providers
advance independently, retaining their existing request concurrency and pacing.
Cancellation stops later waves. Exhausted rate-limit retries and permanent quota,
credential, model and request failures mark the remaining provider jobs as failed/skipped for targeted retry;
other providers continue. A model's unfavorable verdict never skips another model.

Cards and details show completed-model and largest agreement counts. Two completed
scores can produce a separately labeled provisional average; the final score still
requires every evaluated model's score and the final category requires unanimous verdicts.
Agreement is not a calibrated confidence estimate. Requirement comparison groups
only identical, whitespace/case-normalized **verified job quotes**. Different quotes
remain separate; independent models can still produce different score denominators.

Successful structured assessments are reused for seven days under the saved profile
(or temporary run before saving), with at most 1,000 entries per owner. Keys cover
candidate context/profile, roles, posting content/version/URL, provider/model,
request template, output schema and policy version. Current evidence and experience
checks run again on each hit. Errors and cancellation are not cached. Entries are
private, contain candidate evidence, and are deleted with their owner. Expired and
excess entries are removed opportunistically on writes. Single-process locks prevent
simultaneous identical calls and coordinate writes with owner deletion. No live
cost/latency improvement or model-quality gain has been measured.


## Evaluation tier update — 21 October 2026

Defaults now pair Claude Sonnet 5.5 with GPT-6.1 Sol and Gemini 4 Argon.
Gemini was switched back to Argon at user request, retaining low thinking and
no proactive RPM limit. Provider quotas and rate-limit backoff still apply. No human-labeled dataset is available to establish
accuracy gains. Existing environment overrides remain authoritative; resume
extraction and embedding models are unchanged. Existing saved assessments remain
historical, and model identity separates new assessment-cache entries.

GPT evaluation explicitly uses native JSON-schema structured output rather than
tool calling. No sampling overrides are added. Access, costs, latency and quotas
can differ from the previous smaller models; no live paid requests were made.

Official capability references:
- [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [Gemini 4 Argon](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon)

## Shared requirement identification

The extractor receives the posting as numbered original lines and returns requirement
text, an inclusive source-line range, source section, importance (`must_have`, `nice_to_have`, `unclear`) and type (skill, experience,
education, eligibility, responsibility, other). Code copies the selected source lines
directly into the persisted quote, preserving Markdown, punctuation and line breaks.
Out-of-range, reversed and blank-only ranges are rejected. The model does not write
quote text. Code assigns source-ordered IDs,
verifies quotes against the posting, clears unsupported optional section labels
before freezing new criteria, and rejects empty or exactly duplicate
criteria. The extraction prompt preserves alternatives, numbers and negation,
excludes benefits/marketing and distinguishes responsibilities from prerequisites.
Semantic equivalence, completeness and interpretation still need human review;
substring verification alone does not establish them. Line references guarantee
source provenance, not that a selected line entails the summarized criterion.
Single-line postings yield broader quotes; no semantic accuracy gain is claimed.

All evaluators receive the frozen list plus the same candidate context and posting.
Missing, duplicated or invented IDs and changed canonical fields are invalid
assessments, retried once under the existing validation policy; the retry note names
the requirement ID and field. Canonical fields are compared after Unicode (NFKC)
normalization, whitespace collapsing and straightening curly quotes and dashes, so a
model echoing a non-breaking space as a normal space is not a change; the stored
verdict always keeps the shared wording exactly. Any other rewording still fails. Candidate requirement
summaries are populated from the shared list. Existing experience/seniority guards
remain. Unclear importance has weight 1, cannot cause a mandatory mismatch rejection,
and keeps the final verdict For review. Required/preferred weights remain 2/1.

The public extraction cache `.cache/job_requirements/` is keyed by full posting
content, extractor model, prompt, schema and version. It reuses successful validated
results for seven days, bounded to 1,000 entries; it contains no candidate data.
Concurrent evaluation providers share one extraction result or failure for each
posting in a batch. One schema retry and one SDK retry are possible, so one logical
extraction is not a guarantee of exactly one HTTP request. Extraction uses a
90-second request timeout. On validation failure, the extraction retry receives
field-specific correction guidance (including the criterion index for invalid
source ranges or empty-text errors). Quotes are copied from continuous posting spans;
headings should be copied from the posting or left empty when absent. Unsupported
section labels are cleared during fresh extraction; frozen lists remain strictly
validated and unchanged. Persistent
invalid evidence still fails rather than being dropped or accepted. The extraction
policy version separates the updated prompt from older cached extractions.
Cancellation prevents late cache/result persistence.
The optional LangSmith stage is `job.identify_requirements`.

Failed-evaluation checkpoints retain the frozen criteria for targeted retries;
successful providers are retained. Existing historical results are not rewritten.
When a legacy assessment is combined with one using a new requirement list, or
list identities differ, no combined/provisional score is shown. Start a new search
for a fresh comparable set. Extraction errors remain explicit and retryable; there
is no silent fallback to independently identified requirements.

Tests use synthetic data and mocked providers. No labeled dataset or paid live
comparison was available; extraction accuracy, recall, latency and cost are unmeasured.

OpenAI extraction and GPT assessment requests use JSON-schema dictionaries, with
local Pydantic validation of returned data. OpenAI requests explicitly enable
`strict=True` so dictionary schemas are enforced by the provider. Local validation
still checks source bounds and evidence. Safe errors identify nested fields and
failure types without including returned values. This avoids SDK typed `parsed` object
serialization warnings without suppressing warnings or relaxing local validation.

Assessment validation retries receive the previous safe validation error and request
a complete corrected assessment. Unsupported mandatory years must be corrected to
an explicit minimum backed by a shared `must_have` quote, or null/empty when no such
minimum exists. Preferred/unclear criteria cannot become mandatory through this
field. The validator still rejects a persistent unsupported claim. Retry feedback
is local to the job and is not added to assessment cache identities.

Dismissal reasons can adjust shortlist ordering before evaluations begin. They are
not included in extraction or assessment prompts, do not change fit scores, and
do not train the providers. See [dismissal preferences](dismissal-preferences.md).
