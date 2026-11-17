# Cache removal

- Tool/model: Codex / GPT-6; branch: unavailable (not a Git repository).
- Objective: remove all stored application caches at the user's request.
- Removed: public collection, embedding, shared-index and LinkedIn-description caches; private evaluation caches; legacy run vector indexes.
- Preserved: resumes, saved profiles, run snapshots, assessment history and exports.
- Verification: 20 cache locations, 969 files, approximately 54.1 MiB removed; no targeted locations remained immediately after deletion.
- Contracts/code: unchanged. Application tests were unnecessary for data-only removal.
- Limitation: a running backend may retain in-memory state or recreate caches; restart before the next search. Browser storage was not cleared.
- Next role: none; maintenance request completed.
