# Polymarket Paper Maker And Arbitrage Run Handoff

## Status

Research and plan are drafted for a paper-only Polymarket morning run. The project now lives outside the Alpaca repo at `/Users/dylanmccavitt/polymarket`. No Polymarket implementation exists yet.

The plan favors maker-first CLOB simulation plus no-arbitrage scanning over directional prediction. This is based on Polymarket's current docs for orderbooks, fees, maker rebates, liquidity rewards, market discovery, WebSockets, and geoblocking, plus the 2025 Polymarket arbitrage paper.

The active plan now has Codex-ready execution goals, explicit failure definitions, blocker-avoidance rules, paper-trading signal tests, and a lightweight local dashboard in scope. It treats polling, observation-only reports, no fills, and no arbitrage alerts as valid soft outcomes when the tests, logs, dashboard, and report are complete.

## Next

Start with `docs/plans/polymarket-paper-maker-arb-run.md`, then execute Goal 0 and Goal 1.

If executing Friday morning, May 1, 2026, implement the smallest paper-only CLI plus local dashboard path that can:

1. run `python -m polymarket_paper --help`
2. provide `make lint`, `make typecheck`, and `make test`
3. run fixture-based paper-trading signal tests for filters, fill evidence, risk stops, PnL replay, arbitrage math, and dashboard/report parity
4. refuse live-trading behavior by default
5. discover active markets with raw and normalized JSONL evidence
6. poll top-of-book data if WebSocket setup blocks progress
7. write all required JSONL files
8. produce `summary.md` from logs
9. serve `python -m polymarket_paper dashboard --data-dir data/runs/YYYY-MM-DD --host 127.0.0.1 --port 8765`

After Goal 0 and Goal 1, continue through the plan in order: discovery journal, market data loop, paper quote simulator, risk module, report/replay, light local dashboard, then short smoke run before any 60 to 90 minute session.

## Risks

- This project was split out of the Alpaca repo; do not wire Polymarket into Alpaca broker/order paths.
- `/Users/dylanmccavitt/polymarket` is not currently a git repository, so branch/worktree/PR flow is blocked until repo initialization or remote setup happens.
- The user's environment appears to be in the United States. The plan must stay paper-only unless eligibility and platform rules are verified. Do not suggest or implement restriction bypassing.
- Live API spot checks showed some high-volume markets with stale or near-expired dates, so market selection must hard-filter expiry and closed/resolution state.
- Polymarket fees/rewards can vary by market; query per-market metadata rather than hard-coding fee assumptions.
- Do not let dependency, WebSocket, frontend tooling, live API volatility, or too-few-markets issues block the whole path. Use offline fixtures, polling, observation mode, structured skip reasons, a dependency-light local dashboard, and partial-log reports as defined in the plan.

## Files

- `AGENTS.md`
- `docs/plans/polymarket-paper-maker-arb-run.md`
- `docs/handoffs/polymarket-paper-maker-arb-run.md`

## Checks

Doc-only change. No tests were run because no implementation or harness exists yet.

Checked current repo shape:

- `rg --files`
- `find docs -maxdepth 3 -type f | sort`
- `rg -n "dashboard|CLI path|CLI-only|only usable output|Goal 7|Goal 8" AGENTS.md docs`
- `rg -n "signal tests|paper-trading signal|fill-evidence|dashboard/report parity" AGENTS.md docs`
- `git status --short --branch` failed because this folder is not a git repository.
