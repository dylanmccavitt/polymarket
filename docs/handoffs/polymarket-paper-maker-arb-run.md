# Polymarket Paper Maker And Arbitrage Run Handoff

## Status

Implemented the first usable paper-only Polymarket system in `/Users/dylanmccavitt/polymarket` on branch `paper-maker-arb-run`.

The repo is now a local git repository with private GitHub remote `origin` at `https://github.com/DylanMcCavitt/polymarket.git`. The original docs were committed first on `main`, then this work continued on dedicated branch `paper-maker-arb-run`. Draft PR: `https://github.com/DylanMcCavitt/polymarket/pull/1`.

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
- Prior-replay entry gating via `--entry-gating-data-dir`, blocking new bid entries on markets classified `risky_concentrated` or `too_adverse`.
- Strategy comparison report over the same placement/book evidence, without profitability claims.
- Architecture doc at `docs/architecture.md`.

Important environment note: this machine has `python3`, but no `python` shim. Commands were run with `python3`.

## Next

Review the entry-gated dashboard at `http://127.0.0.1:8770` and `data/runs/2026-05-01-entry-gated-v1/summary.md`.

Recommended next implementation slice:

1. Add a same-run suitability brake so markets that become `risky_concentrated` or `too_adverse` during the active run stop receiving new bid entries without waiting for the next replay.
2. Keep inventory-reducing exits enabled on gated markets.
3. Preserve the current prior-replay entry gate and use `data/runs/2026-05-01-entry-gated-v1` as the next prior-state source.
4. Do not loosen quote placement or lower the exit profit target until open inventory and stuck lots improve.

## Risks

- Private remote is configured and `main` plus `paper-maker-arb-run` were pushed to `origin`.
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
- `tests/test_entry_gating.py`
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

## Inventory Exit Implementation Checkpoint

Status:

- Added profit-targeted inventory exit ask quotes with `exit_context`.
- Entry fill caps now apply to bid entries only; ask exits require inventory but bypass entry concentration caps.
- Added separate entry and exit counters in risk exposure payloads.
- Added CLI/run config for `--min-exit-profit-ticks` and `--stuck-inventory-minutes`.
- Added FIFO round-trip replay from `fills.jsonl` with realized PnL, fill-to-flip rate, open inventory, stuck inventory, and unmatched exit size.
- Added `Round Trip PnL`, `Open Inventory`, and `Recent Round Trips` dashboard panels from `build_run_state`.
- Updated architecture docs to keep mark-to-mid PnL separate from realized round-trip PnL.

Checks:

- `python3 -m unittest tests.test_simulator`: passed.
- `python3 -m unittest tests.test_replay_dashboard`: passed.
- `python3 -m polymarket_paper run --help`: passed and includes exit config flags.
- `make lint typecheck test`: passed; guardrail scan passed and 28 tests passed.
- `python3 -m polymarket_paper.guardrails`: passed.

Next:

- Run the required 30-minute `data/runs/2026-05-01-exit-v1` paper session with `--min-exit-profit-ticks 1` and `--stuck-inventory-minutes 20`.
- Generate the report, start the read-only dashboard on `http://127.0.0.1:8769`, verify `/state.json`, and compare realized exits, open inventory, concentration, and adverse-selection evidence against `data/runs/2026-05-01-risk-controls`.

## Inventory Exit V1 Run

Run command:

`python3 -m polymarket_paper run --minutes 30 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --quote-mode one_tick_inside --quote-expiry-seconds 60 --max-fills-per-market 8 --max-fills-per-token 4 --min-exit-profit-ticks 1 --stuck-inventory-minutes 20 --out-dir data/runs/2026-05-01-exit-v1 --poll-seconds 30`

Report command:

`python3 -m polymarket_paper report --date 2026-05-01 --data-dir data/runs/2026-05-01-exit-v1 --dashboard-url http://127.0.0.1:8769`

Dashboard:

- URL: `http://127.0.0.1:8769`
- `/state.json` verification passed with `status == completed`, `round_trip_pnl`, `round_trips`, `open_inventory_lots`, `fill_quality`, and `market_suitability`.
- Dashboard HTML includes `Round Trip PnL`, `Open Inventory`, and `Recent Round Trips`.

Counts:

- Markets total: 100.
- Markets watched: 12.
- Markets skipped: 88.
- Book events: 1,080.
- Virtual quotes: 966.
- Simulated fills: 23.
- Denied fills: 21.
- Risk events: 890.
- Arbitrage alerts: 0.
- Mark-to-mid PnL: -0.805.
- Spread-capture PnL: 0.883333.
- Inventory mark PnL: -1.688333.

Round-trip PnL:

- Entry fills: 17.
- Exit fills: 6.
- Round trips: 6.
- Realized round-trip PnL: 1.05.
- Average profit per share: 0.035.
- Average hold seconds: 303.253398.
- Fill-to-flip rate: 0.352941.
- Open inventory size: 55.0.
- Open inventory lots: 11.
- Stuck inventory lots: 8.
- Oldest open seconds: 1695.8706.
- Unmatched exit size: 0.0.

Fill quality:

- Fills analyzed: 23.
- Adverse-selection flags: 15.
- Missing markouts: 0.
- 30s average markout: -0.008478, adverse count 12, sample count 23.
- 60s average markout: -0.006739, adverse count 12, sample count 23.
- 120s average markout: -0.004565, adverse count 10, sample count 23.

Market suitability:

- `2128129`: risky_concentrated, 12 fills, fill share 0.521739, 8 adverse flags.
- `2090808`: risky_concentrated, 10 fills, fill share 0.434783, 7 adverse flags.
- `2116427`: candidate, 1 fill, fill share 0.043478, 0 adverse flags.
- `2077451`: insufficient_evidence, 0 fills, fewer than 20 quotes.
- `2074235`: insufficient_evidence, 0 fills, fewer than 20 quotes.

Comparison against `2026-05-01-risk-controls`:

- Risk-controls target: 26 fills, 19 denied fills, top two markets 13 / 26, mark-to-mid PnL 1.475, and no original realized round-trip metric.
- Exit-v1: 23 fills, 21 denied fills, top two markets 22 / 23, mark-to-mid PnL -0.805, realized round-trip PnL 1.05.
- Evidence-backed fills were preserved; every simulated fill had an `evidence_event_id`.
- Ask exit fills occurred: 6 exit fills, 6 matched round trips, unmatched exit size 0.0.
- Fill-to-flip rate improved above 0 at 0.352941.
- Open inventory was still material: 55.0 open size and 8 stuck lots.
- Top-two concentration worsened materially: 22 / 23 versus 13 / 26.
- Denied-fill reasons stayed structured: `token_fill_cap` 11 and `market_fill_cap` 10.
- Report/dashboard parity was preserved through `build_run_state`.
- Retrospective replay with the new round-trip code can derive old ask exits from `2026-05-01-risk-controls`, but that run's original report did not expose realized round-trip metrics.

Checks:

- `python3 -m unittest tests.test_simulator`: passed.
- `python3 -m unittest tests.test_replay_dashboard`: passed.
- `python3 -m polymarket_paper run --help`: passed.
- `make lint typecheck test`: passed.
- `python3 -m polymarket_paper.guardrails`: passed.
- `python3 -m polymarket_paper report --date 2026-05-01 --data-dir data/runs/2026-05-01-exit-v1 --dashboard-url http://127.0.0.1:8769`: passed.
- Dashboard verification script against `http://127.0.0.1:8769/state.json`: passed.
- `curl http://127.0.0.1:8769/ | rg "Round Trip PnL|Open Inventory|Recent Round Trips|Polymarket Paper Desk"`: passed.

What worked:

- The engine generated profit-targeted exit asks and evidence-backed ask fills.
- Realized round-trip PnL was measurable and positive on matched exits.
- Replay separated realized round-trip PnL from mark-to-mid PnL.
- Dashboard/report state included round trips, open inventory, stuck lots, fill quality, and market suitability from the same replay path.

What did not work:

- Open and stuck inventory still dominated the run.
- Concentration worsened sharply into two markets.
- Adverse-selection flags increased to 15 / 23 fills.
- Mark-to-mid PnL was negative despite positive realized round-trip PnL.

Next strategy change:

- Do not lower the exit profit target or increase quote aggressiveness yet.
- Add entry gating from prior replay evidence: block new entries on markets classified `risky_concentrated` or `too_adverse`, while still allowing inventory-reducing exits.
- Keep exit asks enabled and retest with the same 30-minute window after candidate-only entry gating; if exits remain profitable but fill-to-flip stays low, test shorter quote expiry before any more aggressive placement.

## Entry-Gated V1 Implementation Checkpoint

Status:

- Created private GitHub remote `DylanMcCavitt/polymarket` and pushed `main` plus `paper-maker-arb-run`.
- Opened draft PR `https://github.com/DylanMcCavitt/polymarket/pull/1`.
- Added `--entry-gating-data-dir` to `run`.
- Added prior-replay suitability loading from `dashboard_state.json`, falling back to JSONL replay when needed.
- The gate blocks new bid entries for markets classified `risky_concentrated` or `too_adverse`.
- Inventory-reducing ask exits remain allowed on gated markets.
- Run start and `entry_gating_status` events record the source data dir, blocked classifications, and blocked market map.

Checks:

- `python3 -m unittest tests.test_simulator.SimulatorTrustTests.test_prior_replay_entry_gate_blocks_bid_but_allows_inventory_exit tests.test_simulator.SimulatorTrustTests.test_prior_replay_entry_gate_blocks_empty_inventory_market tests.test_entry_gating.EntryGatingTests.test_loads_blocked_markets_from_prior_dashboard_state`: failed before implementation, then passed.
- `python3 -m polymarket_paper run --help`: passed and includes `--entry-gating-data-dir`.
- `python3 -m unittest tests.test_simulator tests.test_entry_gating`: passed.
- `make lint typecheck test`: passed; guardrail scan passed and 31 tests passed.
- `python3 -m polymarket_paper.guardrails`: passed.

## Entry-Gated V1 Run

Run command:

`python3 -m polymarket_paper run --minutes 30 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --quote-mode one_tick_inside --quote-expiry-seconds 60 --max-fills-per-market 8 --max-fills-per-token 4 --min-exit-profit-ticks 1 --stuck-inventory-minutes 20 --entry-gating-data-dir data/runs/2026-05-01-exit-v1 --out-dir data/runs/2026-05-01-entry-gated-v1 --poll-seconds 30`

Report command:

`python3 -m polymarket_paper report --date 2026-05-01 --data-dir data/runs/2026-05-01-entry-gated-v1 --dashboard-url http://127.0.0.1:8770`

Dashboard:

- URL: `http://127.0.0.1:8770`
- `/state.json` verification passed with `status == completed`, `round_trip_pnl`, `fill_quality`, and completed counts.
- Dashboard HTML includes `Polymarket Paper Desk`, `Round Trip PnL`, `Open Inventory`, and `Market Suitability`.

Entry gate verification:

- Prior source: `data/runs/2026-05-01-exit-v1`.
- Blocked markets loaded: `2090808` and `2128129`, both `risky_concentrated`.
- Direct JSONL check found `0` bid quotes in blocked prior markets.
- Direct JSONL check found `0` simulated fills in blocked prior markets.

Counts:

- Markets total: 100.
- Markets watched: 16.
- Markets skipped: 84.
- Book events: 1,060.
- Virtual quotes: 955.
- Simulated fills: 51.
- Denied fills: 41.
- Risk events: 868.
- Arbitrage alerts: 0.
- Mark-to-mid PnL: -1.725.
- Spread-capture PnL: 1.391667.
- Inventory mark PnL: -3.116667.

Round-trip PnL:

- Entry fills: 39.
- Exit fills: 12.
- Round trips: 12.
- Realized round-trip PnL: 1.3.
- Average profit per share: 0.021667.
- Average hold seconds: 567.810568.
- Fill-to-flip rate: 0.307692.
- Open inventory size: 135.0.
- Open inventory lots: 27.
- Stuck inventory lots: 12.
- Oldest open seconds: 1762.931878.
- Unmatched exit size: 0.0.

Fill quality:

- Fills analyzed: 51.
- Adverse-selection flags: 21.
- Missing markouts: 3.
- 30s average markout: -0.00951, adverse count 13, sample count 51.
- 60s average markout: -0.0042, adverse count 11, sample count 50.
- 120s average markout: -0.000918, adverse count 8, sample count 49.

Market suitability:

- `2077451`: risky_concentrated, 13 fills, fill share 0.254902, 4 adverse flags.
- `2128120`: risky_concentrated, 12 fills, fill share 0.235294, 8 adverse flags.
- `2128134`: risky_concentrated, 11 fills, fill share 0.215686, 3 adverse flags.
- `2129025`: candidate, 8 fills, fill share 0.156863, 3 adverse flags.
- `2129021`: too_adverse, 6 fills, fill share 0.117647, 3 adverse flags.

Comparison against `2026-05-01-exit-v1`:

- Exit-v1: 23 fills, 6 exits, 6 round trips, realized round-trip PnL 1.05, fill-to-flip rate 0.352941, open inventory 55.0, stuck lots 8, top two markets 22 / 23, mark-to-mid PnL -0.805.
- Entry-gated-v1: 51 fills, 12 exits, 12 round trips, realized round-trip PnL 1.3, fill-to-flip rate 0.307692, open inventory 135.0, stuck lots 12, top two markets 25 / 51, mark-to-mid PnL -1.725.
- Prior bad-market repeat was fixed: old blocked markets had no bid quotes or fills.
- Concentration improved by share but not by absolute risk; new markets became `risky_concentrated` during the same run.
- Realized exits improved in count and total PnL, but open inventory and stuck lots worsened.
- Adverse-selection flags rose in count but fell by rate: 15 / 23 in exit-v1 versus 21 / 51 in entry-gated-v1.

What worked:

- Prior replay gating prevented re-entering the two known bad markets.
- Exit asks still fired under the gate.
- Report/dashboard parity stayed intact through `build_run_state`.

What did not work:

- A static prior blocklist is too slow; new concentration emerged in `2077451`, `2128120`, and `2128134`.
- Open inventory and stuck lots worsened despite positive realized round-trip PnL.
- Mark-to-mid PnL remained negative and got worse versus exit-v1.

Next strategy change:

- Add same-run suitability gating from live replay state or runtime counters so a market that crosses concentration/adverse thresholds stops receiving new bid entries immediately.
- Keep inventory-reducing exits enabled on those same-run gated markets.
- Do not lower the exit profit target or increase quote aggressiveness until open inventory and stuck lots improve.

## Linear And Symphony Track Setup

Status:

- Created Linear project `Polymarket: live-state paper automation`.
- Project URL: `https://linear.app/agentcee/project/polymarket-live-state-paper-automation-a35d6bfcb6fd`.
- Parent track issue: `AGE-396`.
- Current setup issue: `AGE-397`, `Human Review`.
- Next implementation issue after setup lands: `AGE-398`, `Add same-run suitability brake for paper maker entries`.
- Added labels `track:polymarket` and `symphony`.
- Added repo-local Symphony config at `WORKFLOW.md`.
- Added guarded launcher at `scripts/symphony/start`; it sources `/Users/dylanmccavitt/.config/symphony/env`, requires `LINEAR_API_KEY`, and uses `--i-understand-that-this-will-be-running-without-the-usual-guardrails`.
- Added `scripts/open-symphony-workspace` and `scripts/setup-linear-workflow-states.mjs`.
- Added docs at `docs/SYMPHONY.md` and `docs/linear-track.md`.
- Updated `AGENTS.md` so future issue work requires Linear workpad, follow-up issue creation for out-of-scope findings, checks, handoff, commit, push, and PR.
- Disabled review-state comment dispatch after `AGE-397` was accidentally picked up in `Human Review` because the workpad comment included the configured trigger text while describing the setup.
- Stopped the accidental Polymarket Symphony run and its spawned Codex worker; port `4003` is no longer listening.

Linear issue graph:

- `AGE-396`: parent track issue.
- `AGE-397`: setup Linear/Symphony control plane, `Human Review`.
- `AGE-398`: same-run suitability brake, blocked by `AGE-397`.
- `AGE-399`: WebSocket-first public market state engine, blocked by `AGE-398`.
- `AGE-400`: supervised automated paper daemon and kill switch, blocked by `AGE-398` and `AGE-399`.
- `AGE-401`: active daemon state and alerts in read-only dashboard, blocked by `AGE-400`.
- `AGE-402`: public trade-tape evidence diagnostics, blocked by `AGE-399`.
- `AGE-403`: run-review command that opens follow-up Linear issues from evidence, blocked by `AGE-400`.
- `AGE-404`: execution adapter boundary with live trading disabled, blocked by `AGE-400`.
- `AGE-405`: live-readiness checklist, geoblock check, and explicit opt-in gate, blocked by `AGE-404`.
- `AGE-406`: multi-session automated paper soak, blocked by `AGE-400`, `AGE-401`, `AGE-403`, and `AGE-405`.

Startup command:

`cd /Users/dylanmccavitt/polymarket && scripts/symphony/start`

Validation command:

`cd /Users/dylanmccavitt/polymarket && scripts/symphony/start --check`

Trigger rule:

- Keep future issues in `Backlog` until ready.
- After setup PR lands, move `AGE-398` to `Ready` or `Todo` to let Symphony pick up the next slice.
- Comments do not trigger Symphony for this repo; review states are passive until the issue is moved back to an active state.
- If a run or implementation uncovers a material out-of-scope gap, create a new child issue under `AGE-396` before moving the active issue to `Human Review`.
