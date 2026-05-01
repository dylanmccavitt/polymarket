# Polymarket Symphony Workflow

## Start Symphony

From the canonical checkout:

```sh
cd /Users/dylanmccavitt/polymarket
scripts/symphony/start
```

The launcher sources `/Users/dylanmccavitt/.config/symphony/env` when present, requires `LINEAR_API_KEY`, and starts Symphony with:

```sh
--i-understand-that-this-will-be-running-without-the-usual-guardrails
```

Use a custom port when needed:

```sh
SYMPHONY_PORT=4003 scripts/symphony/start
```

Use a dry check without starting the long-running process:

```sh
scripts/symphony/start --check
```

## Trigger Work

Linear project: `Polymarket: live-state paper automation`

Project slug in `WORKFLOW.md`: `polymarket-live-state-paper-automation-a35d6bfcb6fd`

Symphony watches these active states:

- `Ready`
- `Todo`
- `In Progress`
- `Needs Fixes`
- `Rework`
- `Merging`

To trigger an issue, move exactly one scoped issue into `Ready` or `Todo`. Later issues should remain `Backlog` until their blockers are complete.

Comments are context only and do not trigger Symphony for this repo. To restart work from review, move the issue back to `Ready`, `Todo`, `In Progress`, `Needs Fixes`, or `Rework`.

## Workspace Layout

Symphony workspaces live under:

```text
/Users/dylanmccavitt/.codex/symphony-workspaces/polymarket/<ISSUE-ID>
```

Open or print a workspace:

```sh
scripts/open-symphony-workspace AGE-398 print
scripts/open-symphony-workspace AGE-398 zed
scripts/open-symphony-workspace AGE-398 terminal
```

## Required Issue Hygiene

Every implementation issue must keep one persistent Linear comment with:

```md
## Codex Workpad
```

The workpad must include plan, acceptance criteria, validation, blockers, branch, PR, files touched, checks, run/report/dashboard evidence, and any follow-up issues created.

If completing an issue reveals a real adjacent gap, create a new Linear issue or child issue under `AGE-396` before moving the current issue to `Human Review`.

## Live-Trading Boundary

This repo is paper-only by default. Do not add live order placement, wallet keys, signing, allowances, private endpoints, or account identifiers unless a future live-readiness issue explicitly authorizes that scope and its safety gate is complete.
