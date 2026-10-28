# LangSmith child update linkage

- Objective: fix multipart ingestion 400 caused by child dotted_order with null parent_run_id.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: `backend/observability.py` now includes the same parent_run_id on create and update. `tests/test_observability.py` exercises actual SDK update serialization with HTTP intercepted, verifying root and child hierarchy. `scripts/check.sh` disables application tracing during tests to isolate local credentials; tracing-specific tests explicitly enable mocked tracing.
- Evidence: installed SDK update_run inserts parent_run_id=None when omitted. The old completion payload could therefore clear the parent on a nested span. No endpoint/key changes needed.
- Validation: final standard check passed: 212 backend, 60 frontend, 1 legacy test, schema generation and build. Initial check inherited tracing enabled from local env, attempted delivery (blocked by DNS/network restrictions), and conflicted with mocked UUID assertions. Explicit test isolation fixed that; no live ingestion success claimed. Browser unchanged, not rerun.
- Skills: existing backend/test responsibilities. No remaining code work; restart backend and generate new traces to validate live APAC ingestion. Previously rejected traces are not replayed.
