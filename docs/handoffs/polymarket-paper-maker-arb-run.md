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
- Quote lifecycle diagnostics replayed from JSONL logs.
- Fill-opportunity analysis in `summary.md`, `dashboard_state.json`, and the local dashboard.
- Paper-only quote modes: `best_bid`, `one_tick_inside`, and `midpoint_when_spread_allows`.
- Configurable paper quote expiry via `--quote-expiry-seconds`.
- Strategy comparison report over the same placement/book evidence, without profitability claims.
- Architecture doc at `docs/architecture.md`.

Important environment note: this machine has `python3`, but no `python` shim. Commands were run with `python3`.

## Next

Review the 30-minute expiry-60 dashboard at `http://127.0.0.1:8767` and `data/runs/2026-05-01-expiry60/summary.md`.

Recommended next implementation slice:

1. Add per-market and per-outcome concentration controls before running longer sessions; the expiry-60 run concentrated 41 of 46 fills in two markets.
2. Tighten adverse-selection accounting and market suitability scoring before making quotes more aggressive.
3. Decide whether public trade-tape polling is worth adding as optional read-only evidence; current runs deliberately use book-move evidence only.

Do not loosen fill rules just to create activity. The no-fill outcome is useful evidence when the report explains missed ticks, quote lifetime, market movement, and expiry sensitivity.

## Risks

- No remote is configured; PR creation and push are blocked until a remote is added.
- Run data is intentionally ignored by git under `data/runs/`.
- The run used polling mode. WebSocket support remains a later optimization.
- Public trade/event evidence was not integrated in this slice; the runner logs `public_trade_evidence_status` with `book_move_only` so reports do not pretend trade tape evidence exists.
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
- `data/runs/2026-05-01-diagnostics-smoke/markets.jsonl`
- `data/runs/2026-05-01-diagnostics-smoke/books.jsonl`
- `data/runs/2026-05-01-diagnostics-smoke/quotes.jsonl`
- `data/runs/2026-05-01-diagnostics-smoke/fills.jsonl`
- `data/runs/2026-05-01-diagnostics-smoke/arb_alerts.jsonl`
- `data/runs/2026-05-01-diagnostics-smoke/risk_events.jsonl`
- `data/runs/2026-05-01-diagnostics-smoke/dashboard_state.json`
- `data/runs/2026-05-01-diagnostics-smoke/summary.md`
- `data/runs/2026-05-01-expiry60/markets.jsonl`
- `data/runs/2026-05-01-expiry60/books.jsonl`
- `data/runs/2026-05-01-expiry60/quotes.jsonl`
- `data/runs/2026-05-01-expiry60/fills.jsonl`
- `data/runs/2026-05-01-expiry60/arb_alerts.jsonl`
- `data/runs/2026-05-01-expiry60/risk_events.jsonl`
- `data/runs/2026-05-01-expiry60/dashboard_state.json`
- `data/runs/2026-05-01-expiry60/summary.md`

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
- `python3 -m polymarket_paper report --date 2026-05-01 --data-dir data/runs/2026-05-01-diagnostics-smoke --dashboard-url http://127.0.0.1:8766`
- `python3 -m polymarket_paper run --help`
- `python3 -m polymarket_paper run --minutes 10 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --quote-mode one_tick_inside --quote-expiry-seconds 30 --out-dir data/runs/2026-05-01-diagnostics-smoke --poll-seconds 30`
- `python3 -m polymarket_paper run --minutes 30 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --quote-mode one_tick_inside --quote-expiry-seconds 60 --out-dir data/runs/2026-05-01-expiry60 --poll-seconds 30`
- `python3 -m polymarket_paper report --date 2026-05-01 --data-dir data/runs/2026-05-01-expiry60 --dashboard-url http://127.0.0.1:8767`
- `curl http://127.0.0.1:8765/state.json`
- `curl http://127.0.0.1:8766/state.json`
- `curl http://127.0.0.1:8767/state.json`
- `curl http://127.0.0.1:8766/ | rg "Fill Opportunity|Policy Comparison|Polymarket Paper Desk"`
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
- quote lifecycle diagnostics and missed-tick math
- quote policy variants and configurable expiry
- expiry sensitivity and no optimistic fills from policy variants

## Smoke Run

Latest diagnostics smoke command:

`python3 -m polymarket_paper run --minutes 10 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --quote-mode one_tick_inside --quote-expiry-seconds 30 --out-dir data/runs/2026-05-01-diagnostics-smoke --poll-seconds 30`

Latest diagnostics smoke result:

- Completed.
- Markets total: 100.
- Markets watched: 11.
- Markets skipped: 89.
- Book events: 360.
- Virtual quotes: 329.
- Simulated fills: 0.
- Denied fills: 0.
- Risk events: 313.
- Arbitrage alerts: 0.
- Expired quotes: 309.
- Missed by 1 tick: 194.
- Missed by 2 ticks: 20.
- Missed by more: 46.
- Would have filled under longer expiry: 75.
- Policy comparison over the same evidence:
  - `best_bid`: 1 plausible within-expiry fill, 116 longer-expiry opportunities, average 1.066 ticks missed.
  - `one_tick_inside`: 2 plausible within-expiry fills, 117 longer-expiry opportunities, average 1.0 ticks missed.
  - `midpoint_when_spread_allows`: 2 plausible within-expiry fills, 117 longer-expiry opportunities, average 1.0 ticks missed.
- Fill evidence model: `book_move_only`; public trade tape integration is deferred and logged.
- Dashboard verified at `http://127.0.0.1:8766/state.json`; HTML includes Fill Opportunity and Policy Comparison panels.

## Expiry-60 Run

Command:

`python3 -m polymarket_paper run --minutes 30 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --quote-mode one_tick_inside --quote-expiry-seconds 60 --out-dir data/runs/2026-05-01-expiry60 --poll-seconds 30`

Report command:

`python3 -m polymarket_paper report --date 2026-05-01 --data-dir data/runs/2026-05-01-expiry60 --dashboard-url http://127.0.0.1:8767`

Result:

- Completed.
- Markets total: 100.
- Markets watched: 11.
- Markets skipped: 89.
- Book events: 1,080.
- Virtual quotes: 1,000.
- Simulated fills: 46.
- Denied fills: 0.
- Risk events: 922.
- Arbitrage alerts: 0.
- Expired quotes: 703.
- Missed by 1 tick: 644.
- Missed by 2 ticks: 33.
- Missed by more: 95.
- Would have filled under longer expiry: 102.
- Mark-to-mid PnL: 2.825.
- Spread-capture PnL: 1.081528.
- Inventory mark PnL: 1.743472.
- Open exposure by market:
  - `2090808`: 14.5.
  - `2116590`: 11.9.
  - `2074236`: 4.45.
  - `2119381`: 0.02.
- Fills by market:
  - `2090808`: 23.
  - `2116590`: 18.
  - `2074236`: 4.
  - `2119381`: 1.
- All 46 fills had `evidence_event_id`.
- Policy comparison over the same evidence:
  - `best_bid`: 125 plausible within-expiry fills, 207 longer-expiry opportunities, average 1.534 ticks missed, 89 adverse-selection flags.
  - `one_tick_inside`: 133 plausible within-expiry fills, 210 longer-expiry opportunities, average 1.405 ticks missed, 96 adverse-selection flags.
  - `midpoint_when_spread_allows`: 133 plausible within-expiry fills, 210 longer-expiry opportunities, average 1.328 ticks missed, 96 adverse-selection flags.
- Fill evidence model: `book_move_only`; public trade tape integration is deferred and logged.
- Dashboard verified at `http://127.0.0.1:8767/state.json`.

Interpretation:

- Extending expiry from 30 seconds to 60 seconds created real paper fill activity: 46 fills versus 0 in the 10-minute expiry-30 smoke.
- The run also introduced meaningful concentration and adverse-selection risk. Two markets produced 41 of 46 fills, and every quote policy was assessed as more aggressive on adverse-selection evidence.
- Positive mark-to-mid PnL is useful but not conclusive because fees/rebates/rewards are unknown, one mark was missing during replay, and open inventory remains material.
- Do not increase expiry again until per-market/outcome throttles and adverse-selection accounting are improved.

Prior baseline smoke command:

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

`http://127.0.0.1:8766`

The dashboard server is running locally and reads from `data/runs/2026-05-01-diagnostics-smoke`. It is read-only over JSONL replay state.

Current 30-minute dashboard:

`http://127.0.0.1:8767`

This dashboard reads from `data/runs/2026-05-01-expiry60`. It is read-only over JSONL replay state.

## Risk Controls Implementation Checkpoint

Status:

- Implemented paper-only per-market and per-token fill caps.
- Denied fills now remain journalable in `fills.jsonl` with structured reasons and cited evidence events.
- Added post-fill markout replay at 30s, 60s, and 120s.
- Added market suitability replay from quote counts, fill concentration, adverse-selection flags, expired quotes, static-market evidence, and configured fill caps.
- Added `Fill Quality` and `Market Suitability` dashboard panels from `build_run_state`.

Checks:

- `python3 -m unittest tests.test_simulator`: passed.
- `python3 -m unittest tests.test_replay_dashboard`: passed.
- `make lint typecheck test`: passed; guardrail scan passed and 24 tests passed.
- `python3 -m polymarket_paper.guardrails`: passed.

Next:

- Run the required 30-minute `data/runs/2026-05-01-risk-controls` paper session with `--max-fills-per-market 8` and `--max-fills-per-token 4`.
- Generate the report, start the read-only dashboard on `http://127.0.0.1:8768`, verify `/state.json`, and compare concentration against `data/runs/2026-05-01-expiry60`.

## Risk Controls Run

Run command:

`python3 -m polymarket_paper run --minutes 30 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --quote-mode one_tick_inside --quote-expiry-seconds 60 --max-fills-per-market 8 --max-fills-per-token 4 --out-dir data/runs/2026-05-01-risk-controls --poll-seconds 30`

Report command:

`python3 -m polymarket_paper report --date 2026-05-01 --data-dir data/runs/2026-05-01-risk-controls --dashboard-url http://127.0.0.1:8768`

Dashboard:

- URL: `http://127.0.0.1:8768`
- `/state.json` verification passed with `status == completed`, `fill_quality`, `market_suitability`, and nonnegative denied-fill count.

Counts:

- Markets total: 100.
- Markets watched: 11.
- Markets skipped: 89.
- Book events: 1,060.
- Virtual quotes: 932.
- Simulated fills: 26.
- Denied fills: 19.
- Risk events: 859.
- Arbitrage alerts: 0.
- Mark-to-mid PnL: 1.475.
- Spread-capture PnL: 0.766667.
- Inventory mark PnL: 0.708333.

Fill quality:

- Fills analyzed: 26.
- Adverse-selection flags: 10.
- Missing markouts: 10.
- 30s average markout: -0.012917, adverse count 5, sample count 24.
- 60s average markout: -0.009318, adverse count 8, sample count 22.
- 120s average markout: -0.020909, adverse count 6, sample count 22.

Market suitability:

- `2090808`: candidate, 8 fills, fill share 0.307692, 3 adverse flags.
- `2125944`: too_adverse, 5 fills, fill share 0.192308, 4 adverse flags.
- `2116590`: too_adverse, 4 fills, fill share 0.153846, 2 adverse flags.
- `2129025`: candidate, 3 fills, fill share 0.115385, 0 adverse flags.
- `2074236`: candidate, 3 fills, fill share 0.115385, 0 adverse flags.
- `2074235`: too_adverse, 2 fills, fill share 0.076923, 1 adverse flag.
- `2077451`: insufficient_evidence, 0 fills, fewer than 20 quotes.

Concentration comparison:

- Expiry-60 baseline: 46 fills, top two markets produced 41 fills, mark-to-mid PnL 2.825, no denied fills.
- Risk-controls run: 26 fills, top two markets produced 13 fills, mark-to-mid PnL 1.475, 19 denied fills.
- Denied-fill reasons: `market_fill_cap`: 17, `token_fill_cap`: 2.
- Every simulated fill had `evidence_event_id`.
- Quote-policy adverse flags declined versus baseline: `best_bid` 66 vs 89, `one_tick_inside` 68 vs 96, `midpoint_when_spread_allows` 69 vs 96.
- Report/dashboard parity is preserved through `build_run_state`; the report and `/state.json` showed the same completed counts.

Checks:

- `python3 -m unittest tests.test_simulator`: passed.
- `python3 -m unittest tests.test_replay_dashboard`: passed.
- `make lint typecheck test`: passed.
- `python3 -m polymarket_paper.guardrails`: passed.
- Dashboard verification script against `http://127.0.0.1:8768/state.json`: passed.

Blockers or risks:

- Public trade-tape evidence is still not integrated; fill evidence remains `book_move_only`.
- Fees, rebates, and rewards remain `unknown`.
- Two open-position marks were missing during final PnL replay, so mark-to-mid PnL is diagnostic only.
- Several markets still classify as `too_adverse`; do not treat reduced concentration as a strategy-quality proof.

Next experiment:

- Review `too_adverse` markets before changing quote aggressiveness.
- Keep `--max-fills-per-market 8` and `--max-fills-per-token 4` for the next short run unless the review finds the caps are too permissive.
- Do not run a longer session until the 30-minute risk-controls run has been reviewed.
