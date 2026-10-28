# Evaluation streaming telemetry

- Objective: capture per-provider TTFT, TPOT and reported token/cache usage; explain assessment concurrency.
- Tool/model: Codex / GPT-6 session; workspace has no Git repository/branch.
- Files: backend/observability.py, backend/evaluation/telemetry.py, backend/evaluation/providers.py, tests/test_evaluation_telemetry.py, docs/langsmith-tracing.md.
- Decision: when optional tracing is enabled with credentials, enable internal model streaming and attach a per-request callback. Preserve aggregated structured responses, validation, caches, cancellation and retries. No API contract changes.
- Each evaluation.model_request is now an LLM span with provider/model labels, usage_metadata, payload-free first-token event and ttft/tpot seconds. Only numeric allowlisted provider usage leaves the app. No prompts, messages, exceptions or token strings are exported.
- Limitations: TPOT is a client-observed chunk-based average, excluding reported reasoning tokens, not exact decoder timing. Missing provider fields remain missing. Single-chunk responses omit TPOT. SDK retries cannot be independently accounted for. Extraction stages are unchanged. LangSmith cost requires matching model pricing. No live delivery/provider compatibility verification.
- Concurrency: three provider threads, per-provider defaults GPT4/Claude4/Gemini2, waves15; no asyncio.gather needed for overlapping synchronous SDK calls.
- Checks: standard scripts/check.sh passed (234 backend, 68 frontend, 1 legacy, generated contracts, TypeScript/build). Subsequently added streaming-chain integration test: all 4 telemetry tests pass, confirming invoke aggregates chunks and parsed results while retaining usage. Existing observability suite passed with telemetry tests (16 at that point).
- Skills: backend-engineer and test-engineer applied sequentially. No scoring/evidence policy change.
- Next: restart backend; inspect new non-cached evaluations in LangSmith. No remaining implementation dependency.
