# Career Tracker — agent working rules

## Purpose and scope

Career Tracker helps users upload a resume, review their profile, search job
boards, rank matches, and evaluate candidate fit. Read `README.md` before making
changes and consult the relevant documentation in `docs/`.

This file is tool-neutral. It is read by every coding agent used on this
project (Codex, Antigravity, and others listed under "Tool setup"). Tool-specific
configuration lives only in the Tool setup section and in each tool's own
config files; do not duplicate these rules elsewhere.

- Keep work tied to the user's requested outcome and explicit acceptance criteria.
- Prefer the smallest coherent change that solves the problem.
- Do not add unrelated features, dependencies, architectural rewrites, or cleanup.
- Record useful follow-up ideas separately instead of expanding the current task.
- Preserve existing user changes, saved data, and supported compatibility paths.
- Never expose credentials, environment secrets, resumes, or private run data in
  logs, documentation, test fixtures, handoff notes, or commits. Use synthetic
  examples.

## Role and model assignments

These are development roles. Their model tiers are separate from the
application's Gemini, Claude, and GPT job-evaluation provider settings.
The user chooses the concrete model for each role in the tool being used; this
document does not configure or launch models automatically. Role definitions
do not automatically launch agents.

| Role | Model tier | Responsibility |
| --- | --- | --- |
| Project manager | Strong reasoning | Keep the task within scope and coordinate acceptance criteria. |
| Evaluation manager | Strongest reasoning available | Verify candidate-fit accuracy and evaluation reliability. |
| Project structure maintainer | Fast, low-cost | Keep files organized and maintenance predictable. |
| Frontend engineer | Strong coding | Implement accessible Vue interfaces, state, and API integration. |
| Backend engineer | Strong coding | Implement FastAPI contracts, pipeline behavior, and persistence. |
| Test engineer | Strong coding | Write behavior-focused regression tests and report validation evidence. |

Choose the concrete model per tier in each tool's own model selector. Record
the model actually used in handoffs when it matters (for example, evaluation
comparisons).

## Tool setup

One shared set of rules and skills serves every tool. Only the items in this
table differ per tool.

| Tool | Rules file | Skills | Role / agent definitions | Model selection | MCP servers |
| --- | --- | --- | --- | --- | --- |
| Codex | Root `AGENTS.md` | `agents/skills/`, read explicitly | `.codex/agents/*.toml` (one per role, each loads its skill) | Set in the agent definition or session; applies to newly spawned agents, not the current conversation | Codex config under `.codex/` (TOML) |
| Antigravity | Root `AGENTS.md` (do not add `GEMINI.md`, which would override this file) | `agents/skills/`, read explicitly; `.agents/skills` may be a symlink to it | No definition file; start one agent per role from the Manager view and pass the skill path, owned files, and acceptance criteria | Model picker in the app | `.agents/mcp_config.json` (JSON) |
| Other tools | Add a row when adopted. If a tool does not read `AGENTS.md`, point its own rules file at this one instead of copying it. | `agents/skills/` | Tool-specific | Tool-specific | Tool-specific |

- When adding or changing a server, update the MCP configuration of every tool
  in the table so they stay equivalent, and note any intentional difference.
- Tool-specific files may reference this document; they must not restate or
  contradict it.

## Load role skills

Before starting role-specific work, read the assigned skill from
`./agents/skills/`, relative to the repository root:

| Role | Skill file |
| --- | --- |
| Project manager | [Project manager skill](agents/skills/project-manager/SKILL.md) |
| Evaluation manager | [Evaluation skill](agents/skills/evaluation-manager/SKILL.md) |
| Project structure maintainer | [Structure tidier skill](agents/skills/structure-tidier/SKILL.md) |
| Frontend engineer | [Frontend skill](agents/skills/frontend-engineer/SKILL.md) |
| Backend engineer | [Backend skill](agents/skills/backend-engineer/SKILL.md) |
| Test engineer | [Test-writing skill](agents/skills/test-engineer/SKILL.md) |

- Read the actual file contents before applying a skill; do not infer its
  instructions from the filename alone.
- Apply the relevant skill together with this document. If covering multiple
  roles, read each applicable skill. Include the skill path in role handoffs.
- `agents/skills/` is the single project skill directory for every tool. Do not
  create a second copy under a tool-specific folder such as `.agents/skills/`;
  use a symlink if a tool needs auto-discovery. Do not move the directory merely
  because a skill suggests another convention.
- If a skill is missing or its contents describe a different role, report the
  mismatch and use the matching role rules below for work that can proceed.
- The user's instructions take precedence. For conflicts between this document
  and a skill, follow this document; clarify unresolved material ambiguity.

### Project manager

- State the requested outcome, in-scope work, and observable acceptance criteria
  before substantial implementation. Keep this brief for small tasks.
- Identify dependencies and assign clear file ownership when multiple agents are
  explicitly requested. Avoid concurrent edits to the same files.
- Resolve routine implementation choices autonomously within the agreed scope.
- Ask for clarification when a decision would materially change product behavior
  or expand scope; continue independent work while awaiting an answer.
- Check the final result against acceptance criteria and report remaining gaps.
- Do not override evaluation failures or bundle unrelated restructuring just to
  declare a task complete.

### Evaluation manager

- Own the quality of retrieval, ranking, requirement evidence, and candidate-fit
  assessments. Consult `docs/EVALUATION_MODELS.md` and
  `docs/matching-improvements.md` before changing matching behavior.
- Base assessments on resume and job-posting evidence. Distinguish missing
  information from a demonstrated mismatch; do not invent experience, salary,
  qualifications, or company facts.
- Preserve documented experience and seniority rules unless the user requests a
  change. Academic study and projects do not count as professional employment years.
- For accuracy changes, compare a baseline and the proposed behavior on the same
  human-labeled cases. Keep tuning cases separate from held-out evaluation cases.
- Use `scripts/measure_matching.py` when applicable. Report observed recall at k,
  strong-match precision on labeled cases, label coverage, and missed matches.
  Do not claim full recall from a partially labeled pool.
- Include representative seniority gaps, transferable skills, missing evidence,
  and conflicting requirements. Investigate false positives and false negatives.
- Check schema compliance, persistence, retries, rate limits, cancellation, and
  provider failures when the change affects them. Failures must not become
  successful assessments or silently switch providers.
- Record the model/provider, relevant configuration, dataset size, and limitations
  for comparisons. Model agreement and passing mocked tests do not establish
  real-world accuracy. If labels are unavailable, report that limitation explicitly.

### Project structure maintainer

- Follow the existing layout: Python application code in `backend/`, Vue code in
  `frontend/`, maintenance commands in `scripts/`, optional services in
  `integrations/`, Python regression tests in `tests/`, guides in `docs/`, and
  cross-tool handoff notes in `docs/handoffs/`.
- Use `backend.*` for new Python imports and `backend/paths.py` for shared path
  handling. Preserve documented compatibility entry points.
- Keep structure-only changes behavior-preserving. Update affected imports,
  launchers, tests, and documentation together when moving files.
- Do not delete or migrate private inputs, saved runs, caches, databases, or
  exports as part of tidying. Follow the data-location guidance in `README.md`.
- Avoid speculative abstractions, mass renaming, and unrelated formatting.
- Own documentation arrangement: organize current guides and historical archives,
  maintain the README documentation index, and update links and image paths when
  documents move. Follow the documentation arrangement task in the tidy skill;
  refer factual discrepancies and behavior changes to the project manager.
- Verify entry points and affected checks after restructuring.

### Frontend engineer

- Own Vue components, views, routing, styling, and Pinia state in `frontend/src/`.
- Preserve accessibility, responsive layouts, deep links, and partial/error states.
- Coordinate API changes with the backend engineer; consume generated types
  rather than editing them manually. Coordinate test-file ownership with the
  test engineer before editing tests or shared mocks.

### Backend engineer

- Own Python application behavior in `backend/`, including API contracts,
  collection, retrieval, evaluation integration, and persistence.
- Preserve cancellation, targeted retries, saved-resume independence, existing
  entry points, and the single-worker lifecycle unless the task changes them.
- Own contract generation for API changes and provide the frontend and test
  engineers with request, response, error, and compatibility details.
- Obtain evaluation-manager review for scoring, ranking, or evidence changes.

### Test engineer

- Own assigned Python, frontend, and browser regression tests and fixtures.
- Derive assertions from acceptance criteria and observable behavior; report
  implementation defects to the responsible engineer rather than weakening tests.
- Use synthetic inputs, temporary storage, and mocked external services by
  default. Live provider checks require explicit task authorization.
- Distinguish software correctness from human-labeled matching accuracy, which
  remains the evaluation manager's responsibility.

## Orchestration

The primary agent coordinates delivery. The project manager supplies scope and
documentation review; it remains a documentation-only role. For a small task,
one agent may apply the relevant skills sequentially. Role definitions do not
automatically launch agents or select models.

1. **Scope:** establish the outcome, acceptance criteria, affected areas, and
   constraints. Honor requests such as dry-run only or no live calls throughout
   every handoff.
2. **Route:** assign UI work to frontend, API/pipeline work to backend, and
   meaningful regression coverage to the test engineer. Add evaluation-manager
   review for matching changes and the tidier for requested layout work.
3. **Agree on contracts:** for cross-stack work, backend defines the proposed
   request/response/error contract first. Frontend and tests may then work against
   agreed fixtures while backend implementation proceeds.
4. **Assign ownership:** when multi-agent work is requested, give each agent its
   skill path, objective, acceptance criteria, input dependencies, writable files,
   and required checks. Parallelize only independent work with disjoint file
   ownership. Shared mocks, generated schemas/types, dependencies, and lockfiles
   have one designated writer. Never overwrite another agent's work.
5. **Integrate:** the primary agent resolves handoff issues and coordinates
   sequential edits to shared files. Backend generates contracts once schema
   changes settle; frontend and tests reconcile against those outputs. Do not
   run schema generation concurrently with schema edits.
6. **Verify:** the test engineer reports checks and failures; the implementation
   owner fixes defects, followed by affected checks. Run the standard project
   checks for integrated code changes and browser checks for affected workflows.
   Documentation-only work needs content/link review, not application tests.
7. **Review and deliver:** project manager checks scope and documentation;
   evaluation manager reviews relevant quality evidence. The primary agent
   reports completed behavior, checks run, and remaining limitations. Missing
   evidence must not be presented as a pass.

If delegation is unavailable or not requested, follow the same dependency order
within one agent. Do not block routine work on assembling every role. Escalate
only unresolved product decisions or material scope changes to the user.

Each handoff includes: objective, owned/changed paths, contract decisions,
checks with outcomes, unresolved issues, and the next responsible role.

## Working across tools

Different tools cannot read each other's conversations, so collaboration goes
through git and files in the repository.

- **Isolation:** each tool works on its own branch or git worktree. Never have two
  tools write to the same working directory at the same time. Merge through git.
- **Ownership:** split work by area (for example backend and tests in one tool,
  frontend in another) rather than having two tools edit the same files.
  Shared mocks, generated schemas/types, dependencies, and lockfiles keep a
  single designated writer, regardless of tool.
- **Clean switches:** commit or stash before handing work to another tool. Do
  not leave uncommitted changes across a tool switch.
- **Read first:** before starting, read the latest note in `docs/handoffs/` and
  `git log` for the current branch.
- **Write last:** before stopping, write a handoff note to
  `docs/handoffs/YYYY-MM-DD-<tool>-<topic>.md` using the handoff format above,
  plus the tool and model used and the branch name. Keep notes short, synthetic,
  and free of secrets or private resume data.
- Handoff notes are working records, not documentation. The structure maintainer
  may archive or prune old ones.

## Working and handoff rules

1. Inspect the relevant code and existing tests before editing.
2. Identify the applicable role responsibilities; a single agent may cover
   multiple roles. This document does not require parallel agents for every task.
3. Implement the scoped change and update documentation when behavior changes.
4. Run checks appropriate to the change. `./scripts/check.sh` is the standard
   project verification command; add `--e2e` for affected browser workflows.
   Documentation-only edits require a content review, not application tests.
5. Report what changed, verification results, and any unresolved limitations.
   Never describe checks as passing if they were skipped or could not run.

For a role handoff, include the objective, files changed, decisions made,
validation evidence, and remaining work. Evaluation concerns belong to the
evaluation manager; scope decisions belong to the project manager; file-layout
concerns belong to the structure maintainer. The user's instructions take
precedence over this document.