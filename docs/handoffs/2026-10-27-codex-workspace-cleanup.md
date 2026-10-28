# Workspace cleanup

- Objective: remove workspaces except the current saved profile's workspace, as requested by the user.
- Tool/model: Codex, GPT-6 session. No Git branch available.
- Scope: inventory identified one saved profile, one linked workspace and nine other workspaces. Private identifiers and profile content are intentionally omitted.
- Action: removed the nine other workspaces using the running application's DELETE /api/searches/{id} endpoint. No source code or shared caches changed.
- Verification: all nine deletions completed with no pending workers. Filesystem and experiment source listing both contain only the preserved workspace. Saved-profile JSON and preserved workspace state remained byte-for-byte unchanged.
- Remaining work: none; refresh the application's workspace list.
