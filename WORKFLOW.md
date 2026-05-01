---
tracker:
  kind: linear
  api_key: $LINEAR_API_KEY
  project_slug: polymarket-live-state-paper-automation-a35d6bfcb6fd
  active_states:
    - Ready
    - Todo
    - In Progress
    - Needs Fixes
    - Rework
    - Merging
  terminal_states:
    - Done
    - Closed
    - Canceled
    - Cancelled
    - Duplicate
  comment_trigger: "symphony:"
  comment_trigger_states: []
polling:
  interval_ms: 30000
workspace:
  root: /Users/dylanmccavitt/.codex/symphony-workspaces/polymarket
hooks:
  after_create: |
    git clone "${POLYMARKET_REPO_URL:-git@github.com:DylanMcCavitt/polymarket.git}" . || git clone https://github.com/DylanMcCavitt/polymarket.git .
    git fetch origin main --prune || true
  before_run: |
    git fetch origin main --prune || true
  timeout_ms: 120000
agent:
  max_concurrent_agents: 2
  max_turns: 20
  max_retry_backoff_ms: 300000
  max_concurrent_agents_by_state:
    Merging: 1
codex:
  command: /opt/homebrew/bin/codex --config shell_environment_policy.inherit=all app-server
  approval_policy: never
  thread_sandbox: danger-full-access
  turn_sandbox_policy:
    type: dangerFullAccess
  turn_timeout_ms: 3600000
  stall_timeout_ms: 300000
---

You are working on Linear ticket `{{ issue.identifier }}` for Polymarket paper automation.

{% if attempt %}
Continuation context:
- This is retry or continuation attempt #{{ attempt }} because the ticket is still active.
- Resume from the current workspace, branch, Linear workpad, PR state, and repo handoff.
- Do not repeat completed investigation or validation unless new code, new market evidence, or review feedback requires it.
{% endif %}

Issue context:
- Identifier: `{{ issue.identifier }}`
- Title: `{{ issue.title }}`
- State: `{{ issue.state }}`
- Labels: `{{ issue.labels }}`
- URL: `{{ issue.url }}`

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
No issue description was provided. Treat that as a blocker for implementation work and record the missing packet fields in the workpad.
{% endif %}

## Project Contract

This repo is a paper-only Polymarket research and automation scaffold. The current goal is live-state paper automation, not live order placement.

Keep all default behavior read-only and paper-only. Do not add wallet keys, signing, allowances, account identifiers, private endpoints, or real order submission unless a future live-readiness issue explicitly changes that boundary and its acceptance criteria are complete.

Work only inside this issue workspace. Preserve unrelated local changes. Do not commit secrets, API keys, account identifiers, raw wallet data, or large market-data dumps.

## Read Order

1. The Linear issue, including acceptance criteria, blockers, labels, links, and parent issue `AGE-396`.
2. The persistent `## Codex Workpad` comment on the Linear issue.
3. Any attached or open PR and all review comments.
4. `docs/handoffs/polymarket-paper-maker-arb-run.md`.
5. Any active plan under `docs/plans/`.
6. `AGENTS.md`.
7. `docs/architecture.md`.
8. `docs/linear-track.md`.
9. Code and tests.

The Linear issue and PR are the active per-issue handoff. Repo handoff files are durable resume context, not scratchpads.

Symphony dispatch is controlled by Linear state. Comments are context only and must not wake the workflow in review states. If a comment should wake the workflow, move the issue back to an active state.

## Status Routing

- `Backlog`, `Blocked`, or other inactive states: do not work.
- `Ready` or `Todo`: move the issue to `In Progress`, then create or refresh the workpad before code changes.
- `In Progress`: continue from the existing workspace, workpad, branch, and PR state.
- `Needs Fixes` or `Rework`: read all Linear and PR feedback first, add each actionable item to the workpad, fix in the same PR when possible, then revalidate.
- `Human Review`, `In Review`, or `Review`: do not modify code unless new feedback moved the issue back to an active state.
- `Merging`: merge only if a PR is attached, review feedback is resolved or explicitly answered, required checks/evidence are current, and the human moved the issue to this state.
- `Done`, `Closed`, `Canceled`, `Cancelled`, or `Duplicate`: do nothing.

## Workpad

Find or create one persistent Linear comment with this marker:

```md
## Codex Workpad
```

Use that one comment for all progress and handoff notes. Do not scatter separate progress comments.

Keep these sections current:

```md
## Codex Workpad

### Environment
`<host>:<abs-workdir>@<short-sha>`

### Plan
- [ ] ...

### Acceptance Criteria
- [ ] ...

### Validation
- [ ] ...

### Notes
- ...

### Blockers
- None

### Follow-Up Issues Created
- None

### Handoff
- Branch:
- PR:
- Files touched:
- Checks:
- Run/report/dashboard evidence:
- Review state:
- Next recommended issue:
```

## Execution Rules

1. Reproduce or inspect current behavior before changing code when the issue is a bug, regression, or review fix.
2. Sync with `origin/main` before edits. If the remote is unexpectedly unavailable, record that as a PR/push blocker instead of pretending review is complete.
3. Use one issue branch and one issue workspace. Branch names should be shaped like `feat/<issue-id>-short-scope` unless continuing an attached PR branch.
4. Keep scope inside the issue. If an out-of-scope problem appears, create or recommend a child Linear issue under `AGE-396` instead of widening the PR.
5. Keep paper/live behavior explicit and impossible to confuse by default.
6. Stage specific files only.
7. Commit with the project style: `[age-123]: describe change`. Keep messages short. No co-author trailers.
8. Push/open/update the PR when a remote exists and the issue is ready for human review.
9. Attach/link the PR to the Linear issue when possible.
10. Before `Human Review`, update the workpad with final files, checks, run/report/dashboard evidence, blockers, reviewer test notes, and any follow-up issues created.
11. During `Merging`, after the PR is merged and the issue is closed, update the workpad or final issue notes with the merged result and the next recommended issue. Do not activate the next issue from this run by default.

## Checks

Run the smallest checks that prove the changed surface, plus the baseline checks when dependencies are available:

```sh
make lint
make typecheck
make test
python3 -m polymarket_paper.guardrails
git diff --check
```

When changing market-data, simulation, risk, reporting, dashboard, or automation behavior, run the touched command path directly with `python3 -m polymarket_paper ...`. For paper-run issues, record the run command, report command, dashboard URL, and direct JSONL assertions in the workpad and handoff.

## Exit States

Move to `Human Review` only when:

- PR is open or a concrete remote/push blocker is explicitly documented.
- Workpad is current.
- Acceptance criteria are checked or explicitly blocked.
- Required validation has been run or the blocker is documented.
- Run/report/dashboard evidence is attached or summarized in PR/Linear/docs as appropriate.
- Follow-up issues were created for material out-of-scope findings.
- Review notes explain how Dylan should inspect or test the change.

Move to `Merging` only by human decision. Move to `Done` only after merge, final workpad closeout, and any needed project-level handoff updates are complete.
