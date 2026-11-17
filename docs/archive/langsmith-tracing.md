# LangSmith pipeline debugging

Tracing is optional and disabled by default. Install updated backend dependencies
with `python -m pip install -r backend/requirements.txt`, then configure `.env`:

```dotenv
CAREER_LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-key
LANGSMITH_PROJECT=career-tracker
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_TRACING=false
```

Keep the real key in your local environment, never in source control. Choose the
endpoint matching your LangSmith workspace region or self-hosted deployment.
Restart the backend, upload a resume or run a search, then open the configured
project in LangSmith. The backend log includes a random LangSmith trace ID for
each root operation. Upload, search and evaluation retry are separate roots;
existing historical runs are not backfilled. No application run capability URL
or private run ID is exported.

## Coverage

- `resume.upload`: PDF text extraction, classification/profile extraction.
- `search.pipeline`: collection, location/age filtering, history deduplication,
  adaptive description selection/loading, vector indexing, semantic/BM25 retrieval
  and experience screening.
- `jobspy.search` and `seek.collect`: source collection timing. JobSpy's internal
  HTTP calls are not separately instrumented.
- `evaluation.all_providers`, `evaluation.provider_batch`, `evaluation.provider`,
  `evaluation.claude`, `evaluation.gpt`, `evaluation.gemini`,
  `evaluation.model_request`: provider waves, provider-labeled per-job work and
  individual model attempts, including application retries. Cached assessments
  have a job span but no model-request span.
- `evaluation.retry`: targeted failed-assessment retries.

Concurrent collection and evaluation work carries parent context into each worker.
The UI is unchanged; inspect traces in LangSmith. This is stage instrumentation,
not a full HTTP profiler: HNSW/BM25 internals are timed within retrieval, and
individual SDK-internal retries are not separate spans.

## Data and failure handling

Spans export fixed stage names, generated trace identifiers, timestamps, result
counts for list/tuple results, allowlisted provider/board identifiers, and outcomes.
Unhandled exceptions export their class name only. Handled source/provider failures
mark the containing stages partial; handled pipeline failures mark them failed.
Explicit pipeline cancellation handlers mark cancellation. Other early exits can
appear completed; consult the application's status for the definitive run state.

Function arguments, returned documents, resume text, prompts, completions, raw
error messages, stack traces, attachments, paths, profile IDs and job URLs are
not exported. Implicit LangChain tracing is disabled within instrumented operations
and inherited worker contexts even if global automatic tracing was enabled. Prompt inspection remains unavailable. Evaluation LLM spans export only provider-reported
usage and timing; cost calculation depends on LangSmith recognizing the model
or a configured custom pricing entry.
The custom application toggle controls explicit SDK run creation; standard
`LANGSMITH_TRACING=true` is not needed.

Missing credentials disable delivery. SDK setup/delivery exceptions produce a
sanitized warning and do not fail or repeat application operations. Delivery is
best effort through the SDK batch queue; a killed process can lose pending traces.
Local tests use a mock client and synthetic data. No live LangSmith delivery has
been verified as part of implementation.

Built using LangSmith's [custom instrumentation](https://docs.langchain.com/langsmith/annotate-code)
and [tracing context control](https://reference.langchain.com/python/langsmith/run_helpers/tracing_context).


## Collection batch hierarchy

New adaptive searches group all processing for a round under its provider-labelled
batch. Batch metadata includes the source, collection round number and page offset;
queries and locations remain private. Example:

```text
search.pipeline
  jobs.collect
    jobs.adaptive_collection
      jobs.batch.linkedin
        jobspy.search
        jobs.filter_cards
        jobs.deduplicate_incoming
          jobs.deduplicate_history
        jobs.select_descriptions
        jobs.descriptions
        jobs.filter_descriptions
        jobs.merge_unique_results
          jobs.deduplicate_history
      jobs.batch.indeed
        ...
      jobs.deferred_batch.mixed
        jobs.select_descriptions
        jobs.descriptions
        jobs.filter_descriptions
        jobs.merge_unique_results
```

Deferred batches process remaining collected candidates and may contain multiple
boards. They do not issue another board search. Batch result counts represent
newly retained postings; merge-step counts represent the accumulated pool.
Every batch closes on normal completion, exception or early loop exit. These
groups apply to adaptive web collection; legacy fixed collection retains its
existing stage traces. Older traces are not reorganized.

Shared requirement identification appears as `job.identify_requirements` before
candidate assessment requests. A cache hit avoids the extractor call; concurrent
providers share extraction for the same posting. This stage follows the existing
counts-only payload policy and does not export posting or candidate text.

## Evaluation token and streaming metrics

With tracing enabled, evaluation calls use streaming internally while retaining
complete, validated structured results for the application. Each
`evaluation.model_request` is an LLM span with `ls_provider` and `ls_model_name`.
Its output contains:

- `usage_metadata.input_tokens`: provider-reported total prompt tokens.
- `usage_metadata.input_token_details.cache_read`: cached prompt tokens, when reported;
  these are part of input tokens, not additional tokens. Cache creation is also retained.
- `usage_metadata.output_tokens`: generated tokens, including reasoning where reported.
- `ttft`: seconds from the model-start callback to the first nonempty content or
  tool-argument chunk. A payload-free `new_token` event enables LangSmith's TTFT display.
- `tpot`: average seconds between first and last content chunks, divided by
  non-reasoning output tokens minus one. This is a client-observed approximation,
  not precise server decoding time; chunks may contain multiple tokens. It is
  omitted for a single chunk, missing usage or fewer than two output tokens.

Missing usage/cache fields remain absent, not fabricated zeros. Failed streams
may have TTFT without final token counts. SDK-internal retries are not individually
accounted for; schema/policy retries create separate model spans. Application
cache hits make no model request and generate no token metrics. Historical traces
are unchanged. Resume/shared-requirement extraction retain their existing stage
traces; these new metrics cover the three assessment providers.

Assessments are already concurrent using a three-provider `ThreadPoolExecutor`,
with per-provider defaults of four GPT, four Claude and two Gemini workers, in
waves of 15 jobs. This is threaded I/O concurrency, not `asyncio.gather` or a single
batched provider API request. Shared requirement extraction and rate-limit waits
can delay individual assessment requests.

Implementation follows [LangSmith LLM instrumentation](https://docs.langchain.com/langsmith/log-llm-trace).
