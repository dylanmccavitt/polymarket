# Project Flow

## How To Run

- Work from `/Users/dylanmccavitt/polymarket`.
- This project is currently a paper-only Polymarket research scaffold. There is no runnable implementation yet.
- First implementation should add a local setup command, a test/lint/typecheck harness, paper-only CLI/data commands, and a lightweight local dashboard for viewing runs.
- Prefer module execution until console scripts exist:
  - `python -m polymarket_paper discover --limit 100 --out data/runs/YYYY-MM-DD/markets.jsonl`
  - `python -m polymarket_paper run --minutes 90 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --out-dir data/runs/YYYY-MM-DD`
  - `python -m polymarket_paper report --date YYYY-MM-DD --data-dir data/runs/YYYY-MM-DD`
  - `python -m polymarket_paper dashboard --data-dir data/runs/YYYY-MM-DD --host 127.0.0.1 --port 8765`

## How To Test, Lint, And Typecheck

- Add these commands with the first code scaffold:
  - Tests: `make test`
  - Lint: `make lint`
  - Typecheck/syntax check: `make typecheck`
- Until the harness exists, document missing checks in the handoff.
- Run touched execution paths directly when changing market-data, simulation, risk, or reporting code.
- The test suite should include paper-trading signal tests, not only import/unit tests:
  - market normalization and filter decisions from fixtures
  - conservative fill simulation with required evidence events
  - stale-feed, quote-expiry, spread-widening, midpoint-move, and exposure-stop behavior
  - PnL replay from JSONL logs
  - arbitrage-alert math on synthetic binary and multi-outcome books
  - dashboard/report parity over the same fixture run
- Tests may signal data quality, simulator conservatism, replayability, and risk-control coverage. They must not claim the strategy is profitable.

## Coding Rules

- Paper simulation is the only allowed default path.
- Keep Polymarket API access read-only unless a later issue explicitly adds live trading support.
- Keep order signing, wallet keys, allowances, and real order endpoints out of the paper engine.
- Strategy code should return virtual quote or alert objects; it should not submit orders.
- Dashboard code must be read-only over run logs/state; it must not mutate strategy behavior or submit anything.
- Prefer deterministic, testable math over assistant-driven decisions.
- Every simulated fill must cite the market-data event that made it plausible.
- Do not commit credentials, private keys, account identifiers, raw wallet data, or large market-data dumps.

## Guardrails

- Do not bypass geographic or platform restrictions.
- No live trading path may exist without explicit config and environment opt-in.
- No live order code may share the same command path as paper simulation.
- Market selection must filter closed, expired, stale, and non-orderbook markets.
- Fee, reward, tick-size, and order-size assumptions must come from market metadata when available.
- Every run must write enough JSONL evidence to reconstruct selection, quotes, fills, risk events, and PnL.
- The dashboard must display from the same JSONL/run-state evidence used by reports, and it must clearly distinguish live, stale, missing, and completed data.
- New strategies need a documented thesis, risk assumptions, and validation plan before live use.

## Definition Of Done

- The relevant paper-only path runs from this repo.
- A local read-only dashboard can display the active or completed run from run logs.
- `make lint`, `make typecheck`, and `make test` pass or blockers are documented.
- Paper-trading signal tests cover market selection, fill plausibility, risk stops, PnL replay, and dashboard/report parity.
- Docs or handoff are updated when workflow, risk, or market-data behavior changes.
- Paper/live behavior is explicit and cannot be confused by default config.
