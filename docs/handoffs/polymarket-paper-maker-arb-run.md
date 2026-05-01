# Polymarket Paper Maker And Arbitrage Run Handoff

## Status

Implemented the first usable paper-only Polymarket system in `/Users/dylanmccavitt/polymarket` on branch `paper-maker-arb-run`.

The repo is now a local git repository. The original docs were committed first on `main`, then this work continued on a dedicated branch. No git remote is configured, so PR creation is blocked on adding a remote.

Implemented:

- Python package scaffold with `python3 -m polymarket_paper`.
- `make lint`, `make typecheck`, and `make test`.
- Paper-only CLI commands: `discover`, `run`, `report`, and `dashboard`.
- Read-only public Gamma market discovery and CLOB orderbook polling.
- JSONL journals for markets, books, quotes, fills, arbitrage alerts, and risk events.
- Strict market filters with skip reasons.
- Conservative paper maker quote simulator.
- Centralized risk checks for stale feeds, quote expiry, spread widening, midpoint moves, and exposure caps.
- Binary and multi-outcome arbitrage scanner math.
- JSONL replay report and `summary.md` generation.
- Local read-only dashboard at `http://127.0.0.1:8765`.
- Dashboard redesign after review feedback: market/outcome names, bid/ask/mid/spread blocks, quote/fill/risk badges, and mid-price history charts.
- Architecture doc at `docs/architecture.md`.

Important environment note: this machine has `python3`, but no `python` shim. Commands were run with `python3`.

## Next

Review the completed dashboard and `data/runs/2026-05-01/summary.md`.

Recommended next implementation slice:

1. Split smoke and long sessions into separate run IDs or subdirectories so aggregate reports do not mix short-run and long-run counters.
2. Add richer fill-opportunity diagnostics: quote distance from touch, subsequent book movement, and why no conservative fills occurred.
3. Decide whether to support optional WebSocket collection after polling has proven stable.

Do not loosen fill rules just to create activity. The no-fill outcome is useful evidence that the current bid-only maker simulator is conservative.

## Risks

- No remote is configured; PR creation and push are blocked until a remote is added.
- Run data is intentionally ignored by git under `data/runs/`.
- The run used polling mode. WebSocket support remains a later optimization.
- Exact user-provided `python -m ...` commands cannot run on this machine until a `python` shim exists; use `python3 -m ...`.
- The 2026-05-01 run produced no fills and no arbitrage alerts. This is a valid soft outcome, not a system failure.
- Fees, rebates, and rewards are still reported as `unknown`; the engine preserves metadata but does not yet compute those components.

## Files

- `.gitignore`
- `Makefile`
- `pyproject.toml`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/handoffs/polymarket-paper-maker-arb-run.md`
- `polymarket_paper/__init__.py`
- `polymarket_paper/__main__.py`
- `polymarket_paper/adapters.py`
- `polymarket_paper/arbitrage.py`
- `polymarket_paper/cli.py`
- `polymarket_paper/dashboard.py`
- `polymarket_paper/filters.py`
- `polymarket_paper/guardrails.py`
- `polymarket_paper/journal.py`
- `polymarket_paper/report.py`
- `polymarket_paper/risk.py`
- `polymarket_paper/runner.py`
- `polymarket_paper/simulator.py`
- `polymarket_paper/timeutils.py`
- `tests/test_arbitrage.py`
- `tests/test_filters.py`
- `tests/test_replay_dashboard.py`
- `tests/test_simulator.py`

Run outputs, ignored by git:

- `data/runs/2026-05-01/markets.jsonl`
- `data/runs/2026-05-01/books.jsonl`
- `data/runs/2026-05-01/quotes.jsonl`
- `data/runs/2026-05-01/fills.jsonl`
- `data/runs/2026-05-01/arb_alerts.jsonl`
- `data/runs/2026-05-01/risk_events.jsonl`
- `data/runs/2026-05-01/dashboard_state.json`
- `data/runs/2026-05-01/summary.md`

## Checks

Passed:

- `python3 -m polymarket_paper --help`
- `python3 -m polymarket_paper dashboard --help`
- `make lint`
- `make typecheck`
- `make test`
- `python3 -m polymarket_paper discover --limit 100 --out data/runs/2026-05-01/markets.jsonl`
- `python3 -m polymarket_paper run --minutes 10 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --out-dir data/runs/2026-05-01 --poll-seconds 30`
- `python3 -m polymarket_paper run --minutes 90 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --out-dir data/runs/2026-05-01`
- `python3 -m polymarket_paper report --date 2026-05-01 --data-dir data/runs/2026-05-01 --dashboard-url http://127.0.0.1:8765`
- `curl http://127.0.0.1:8765/state.json`
- Headless Chrome screenshot of `http://127.0.0.1:8765`
- Repo-wide guardrail scan found no live order, signing, wallet key, allowance, or private endpoint path.

Offline tests are fixture-based and cover:

- market filters and skip reasons
- conservative fill evidence
- stale feed behavior
- quote expiry
- spread-widening cancellation
- midpoint-move cancellation
- exposure stops
- PnL replay
- arbitrage math
- dashboard/report parity
- active-vs-completed dashboard state across multiple runs in one directory

## Smoke Run

Command:

`python3 -m polymarket_paper run --minutes 10 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --out-dir data/runs/2026-05-01 --poll-seconds 30`

Result:

- Completed.
- Markets total: 100.
- Markets watched: 5.
- Markets skipped: 95.
- Book events after smoke: 190.
- Virtual quotes after smoke: 148.
- Simulated fills: 0.
- Arbitrage alerts: 0.
- Dashboard opened from replayed JSONL state.

## Long Run

Command:

`python3 -m polymarket_paper run --minutes 90 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --out-dir data/runs/2026-05-01`

Result after aggregating the smoke run and long run in the same run directory:

- Completed.
- Markets total: 100.
- Markets watched: 5.
- Markets skipped: 95.
- Book events: 1,880.
- Virtual quotes: 1,474.
- Simulated fills: 0.
- Denied fills: 0.
- Risk events: 1,475 after recording checks.
- Arbitrage alerts: 0.
- Mark-to-mid PnL: 0.0.
- Spread-capture PnL: 0.0.
- Open exposure: none.
- Data mode: polling.
- Observation mode: false.

Skipped market reasons:

- `negative_risk_skipped`: 31.
- `expired`: 27.
- `resolution_source_unmonitorable`: 23.
- `low_liquidity`: 6.
- `invalid_best_bid_ask`: 3.
- `metadata_missing:best_bid_ask`: 2.
- `stale_metadata`: 2.
- `metadata_missing:end_date`: 1.

## Dashboard

URL:

`http://127.0.0.1:8765`

The dashboard server is running locally and reads from `data/runs/2026-05-01`. It is read-only over JSONL replay state.
