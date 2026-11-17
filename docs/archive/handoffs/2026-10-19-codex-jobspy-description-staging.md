# Generalize JobSpy description staging

- Tool/model: Codex / GPT-6 session. Branch: unavailable; workspace is not a Git repository, so no commit/worktree was created.
- Objective: share title screening and cached/deferred descriptions across supported JobSpy boards.
- Changed: `backend/search/jobspy_details.py` (new), `collection.py`, `backend/paths.py`; regression tests in `tests/test_jobspy_details.py`, `test_linkedin_requests.py`, `test_jobspy_migration.py`; `.env.example`, README and provider/matching documentation.
- Behavior: LinkedIn/Indeed/Glassdoor share bounded screening; inline descriptions win over cache, then supported selected-job details load. Indeed has inline text rather than a separate detail endpoint. Glassdoor reuses JobSpy country/session setup and its internal detail parser. LinkedIn cache/settings remain compatible. New description caches contain only public posting text. Pool settings participate in collection cache identity.
- Errors: preserve partial rows, stop detail network requests after search/detail 429, report missing descriptions and exclude incomplete collections from full-result caching. Cancellation retained.
- Contracts: no API/schema or frontend changes. SEEK/Adzuna unchanged.
- Validation: standard `scripts/check.sh` passed with 182 backend tests, 54 frontend tests, one compatibility test and production build. A subsequent cache-identity regression and affected collection tests passed. No live services were called.
- Evaluation review: same title-overlap heuristic now applies to all supported JobSpy boards. No human labels are available; no recall/precision or live latency gains claimed. Expanded pools may increase search-page requests; explicit filter allowances still compound with pool factor. Shared cross-run board cooldown remains a follow-up.
- Compatibility limitation: Glassdoor adapter depends on installed JobSpy internals; mocked adapter checks do not establish live endpoint availability. No site-package files modified.
- Next owner: none required for this request; use labeled matching cases before tuning screening and separately authorize any live board validation.
