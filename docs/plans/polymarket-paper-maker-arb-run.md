# Polymarket Paper Maker And Arbitrage Run

## Goal

Set up a paper-only automated Polymarket morning run that tests structural, measurable edges instead of discretionary "I think this event happens" trading.

Default run date is Friday, May 1, 2026, America/New_York.

## Research Takeaway

The best non-larp first strategy is not directional day trading. It is a maker-first market-structure strategy with an arbitrage scanner running beside it:

1. Passive maker simulation on liquid CLOB markets where the bot quotes just inside or at the current top of book, earns virtual spread, and accounts for adverse selection.
2. Fee/rebate/reward-aware scoring, because takers can pay fees while makers are fee-free and may earn rebates or rewards on eligible markets.
3. Hard no-arbitrage checks for binary and mutually exclusive markets. These are scanner alerts on day one, not live executions.
4. Order-flow imbalance and event-catalyst signals are data-collection-only until enough tick history exists for backtesting.

Avoid chart-pattern trading, LLM news vibes, whale-wall following, and any strategy that cannot be expressed as deterministic math over market data.

## Sources

- Polymarket CLOB/orderbook docs: `https://docs.polymarket.com/trading/orderbook`
- Polymarket fees docs: `https://docs.polymarket.com/trading/fees`
- Polymarket maker rebates docs: `https://docs.polymarket.com/market-makers/maker-rebates`
- Polymarket liquidity rewards docs: `https://docs.polymarket.com/market-makers/liquidity-rewards`
- Polymarket market WebSocket docs: `https://docs.polymarket.com/market-data/websocket/market-channel`
- Polymarket market discovery docs: `https://docs.polymarket.com/market-data/fetching-markets`
- Polymarket geographic restrictions docs: `https://docs.polymarket.com/api-reference/geoblock`
- Arbitrage paper: `https://arxiv.org/abs/2508.03474`

## Strategy Math

### Directional expected value

For buying one YES share at price `p` with estimated true probability `q`:

```text
gross_ev = q - p
taker_fee_per_share = fee_rate * p * (1 - p)
net_ev = q - p - taker_fee_per_share - expected_slippage
```

Trade only if `net_ev` is materially positive after a safety buffer. The first paper run should not use directional EV for entries unless a deterministic external fair-value model is present.

### Maker quote value

For a maker bid at `b` and ask at `a` around midpoint `m`:

```text
round_trip_spread = a - b
maker_fee = 0
expected_quote_value = fill_probability * round_trip_spread
                       + expected_rebate_or_reward
                       - adverse_selection_cost
                       - inventory_risk_cost
```

Paper fills must be conservative. Count a virtual maker fill only when the live stream shows trade-through or a top-of-book move that plausibly would have taken the resting quote. Do not count fills just because the virtual quote was displayed at the best price.

### Binary arbitrage

For a standard YES/NO market:

```text
buy_both_cost = yes_best_ask + no_best_ask + fees_and_slippage
arb_if = buy_both_cost < 1.00 - min_edge
```

The reverse side requires inventory or a valid short/merge workflow and should be scanner-only for now.

### Multi-outcome arbitrage

For mutually exclusive exhaustive outcomes:

```text
basket_cost = sum(best_ask_yes_i) + fees_and_slippage
arb_if = basket_cost < 1.00 - min_edge
```

Negative-risk markets need explicit `negRisk` handling and should be skipped for simulated execution on the first run unless the implementation models conversion mechanics.

## Market Selection

Fetch active markets dynamically on Friday morning. Do not hard-code Thursday's top-volume markets.

Required filters:

- `active = true`
- `closed = false`
- `acceptingOrders = true`
- `enableOrderBook = true`
- `endDate` at least 6 hours in the future unless the market is intentionally an intraday market with a known external feed
- `volume24hr >= 50000`
- `liquidityNum >= 10000`
- `spread <= 0.03` or `spread <= 3 * tick_size`
- `orderMinSize <= 20`
- both CLOB token IDs are present
- skip markets with missing best bid/ask unless collecting data only
- skip augmented negative-risk placeholder/Other outcomes
- skip any market whose resolution source cannot be monitored

Priority categories for the first paper run:

- Crypto and sports markets with high volume, tight spread, and objective real-time external references.
- Fee-enabled markets where maker rebates can be modeled.
- Reward-configured markets where the reward metadata is available, but only if quotes remain close to midpoint and inventory limits are small.

Lower priority:

- Politics/geopolitics/news markets without a reliable real-time external feed.
- Very long-dated markets near 0 or 1 unless the goal is only reward/rebate study.
- Recently expired or stale markets even if `volume24hr` is high.

## Paper Engine Scope

The run must not submit real orders. It should only:

- fetch Gamma market/event metadata
- fetch CLOB market info and orderbooks
- subscribe to public market WebSocket streams
- maintain local top-of-book state
- generate virtual maker quotes
- simulate conservative fills
- scan no-arbitrage constraints
- write all inputs and decisions to local logs
- produce an end-of-run report
- serve a lightweight local read-only dashboard for viewing active or completed runs

No private keys, wallet signing, real order endpoints, allowance checks, or funded-wallet flows belong in this slice.

## Codex Execution Goals

Run these as small, ordered goals. A later goal should not depend on guessing what an earlier goal meant.

### Goal 0: Repo scaffold and guardrails

Create the minimum Python project shape that makes the paper path runnable:

- `pyproject.toml`
- `Makefile`
- `polymarket_paper/__main__.py`
- `polymarket_paper/` modules for adapters, filters, journal, simulator, report, and dashboard
- `tests/` with fixture-based tests
- `.gitignore` entries for local envs, caches, and `data/runs/`

Done when:

- `python -m polymarket_paper --help` works.
- `make lint`, `make typecheck`, and `make test` exist.
- `make test` runs fixture-based paper-trading signal tests, not just import checks.
- The CLI refuses any mode other than paper/read-only behavior.
- `python -m polymarket_paper dashboard --help` works and describes a local read-only viewer.
- A repository scan finds no wallet, private-key, signing, allowance, or order-submit code.

Failure looks like:

- The first scaffold requires credentials or a funded account.
- The CLI can be confused with a live-trading path.
- The dashboard is treated as a separate product before the run logs and report data model exist.
- Tests only prove modules import or help text renders.
- Tests require live Polymarket network access instead of fixtures.

Avoid blockers by:

- Prefer standard-library HTTP first if dependency setup slows the first run.
- If lint/typecheck tools are not installed yet, add the commands and document the exact install/setup blocker in the handoff.
- Keep WebSocket support optional until polling discovery and journaling work.
- Keep the first dashboard dependency-light: a local HTTP server plus static HTML/JS is enough if a heavier frontend stack would slow the paper run.
- Create tiny fixture runs before live API work so tests can validate the journal, report, and dashboard paths offline.

### Goal 1: Paper-trading signal tests

Build the tests that tell Codex whether the paper system is trustworthy enough to run longer sessions. These tests are part of the implementation goal, not cleanup after the fact.

Done when:

- Market fixtures cover active, closed, expired, stale, non-orderbook, missing-token, missing-metadata, tight-spread, wide-spread, and negative-risk cases.
- Filter tests assert both the selected watchlist and every skip reason.
- Simulator tests prove quotes expire, stale data stops quoting, spread widening cancels quotes, midpoint moves cancel quotes, exposure caps deny fills, and ambiguous fill evidence stays unfilled.
- Fill tests require a cited book or trade event ID for every simulated fill.
- PnL replay tests compute `summary.md` from JSONL logs after process exit.
- Dashboard/report parity tests show the dashboard state and report agree on markets watched, quotes, fills, risk events, arbitrage alerts, exposures, and PnL components.
- Synthetic arbitrage tests cover binary no-arb, binary arb, multi-outcome no-arb, and multi-outcome arb examples.

Paper-trading signals to report from tests:

- filter pass/reject coverage
- fill-evidence coverage
- stale-feed and reconnect handling coverage
- exposure-stop coverage
- PnL replay parity
- dashboard/report parity

Failure looks like:

- Tests assert the bot made money instead of proving accounting, evidence, and risk behavior.
- Tests depend on current live market data and fail when Polymarket fields or volumes change.
- Fill tests allow optimistic fills without a trade-through or plausible book-move event.
- Report and dashboard tests use different parsers and can drift.
- There is no synthetic adverse-selection or stale-data scenario.

Avoid blockers by:

- Keep live API smoke checks separate from `make test`; fixture tests must run offline.
- Use small JSONL fixture files that can be read by the same code paths as real runs.
- Treat profitability, fill frequency, and arbitrage frequency as observations, not pass/fail criteria.
- Add one fixture per failure mode before adding broader strategy behavior.

### Goal 2: Market discovery journal

Implement read-only market discovery and filter journaling before any strategy logic.

Done when:

- `discover` writes one JSONL row per candidate market.
- Each row records raw metadata, normalized fields, filter decision, and skip reason.
- At least 20 active candidates are fetched during a live run, or the report says why not.

Failure looks like:

- Markets silently disappear from the candidate set.
- Closed, expired, stale, non-orderbook, or missing-token markets reach the watchlist.
- Missing metadata is treated as favorable instead of unknown or rejected.

Avoid blockers by:

- Store raw API records beside normalized fields so field drift can be debugged later.
- If an expected field is missing, skip the market with `metadata_missing:<field>` rather than crashing the whole run.
- If fewer than 3 markets pass strict filters, keep running in observation mode and report the filter bottleneck.

### Goal 3: Market data loop

Build top-of-book collection that can run through either WebSocket or polling.

Done when:

- `books.jsonl` records timestamped top-of-book snapshots or stream events.
- Every watched market has freshness tracking.
- Disconnects, stale data, parse failures, and fallback mode are written to `risk_events.jsonl`.

Failure looks like:

- The process appears to run but writes no book data.
- Book updates cannot be tied back to market and token IDs.
- WebSocket failure stops the entire run when polling could still collect data.

Avoid blockers by:

- Implement polling as the reliable baseline, then add WebSocket as an optimization.
- Use short, explicit timeouts and keep the run moving after per-market failures.
- Stop quoting a market when its data is stale, but keep the report path alive.

### Goal 4: Paper quote simulator

Generate deterministic virtual maker quotes with strict fill evidence.

Done when:

- `quotes.jsonl` records side, token, price, size, midpoint, spread, reason, expiry, and risk caps.
- `fills.jsonl` records only conservative simulated fills.
- Every fill cites a prior book/trade event ID that made the fill plausible.

Failure looks like:

- A quote is counted as filled merely because it was displayed at the best price.
- Fills lack evidence or cannot be reproduced from logs.
- The simulator accumulates exposure after quote expiry, stale data, or risk cap breach.

Avoid blockers by:

- Start with maker quotes only.
- If fill evidence is ambiguous, leave the quote unfilled and log the ambiguity.
- Treat no fills as a valid conservative outcome, not a reason to loosen rules mid-run.

### Goal 5: Risk and stop conditions

Centralize paper exposure limits, stale-feed checks, and hard safety stops.

Done when:

- All quote and fill decisions pass through one risk module.
- Exposure is tracked by market, token, side, and total run.
- Any real trading endpoint/signing path detection stops the run.

Failure looks like:

- Risk checks are copied into strategy code and drift.
- A market keeps quoting after the data feed is stale.
- The run cannot explain why it stopped.

Avoid blockers by:

- Make the risk module return structured allow/deny decisions instead of raising for normal skips.
- Log stop conditions before exiting.
- Include a small fixture test for every stop condition.

### Goal 6: Report and replay

Make the report derive from JSONL evidence, not in-memory state.

Done when:

- `report` can be run after the collector exits.
- `summary.md` includes watched/skipped markets, quotes, fills, PnL, exposures, stale-feed counts, arbitrage alerts, checks run, and next experiment.
- Reported PnL can be traced to `quotes.jsonl`, `fills.jsonl`, and final book marks.

Failure looks like:

- The report uses counters that were never journaled.
- PnL cannot be recomputed after process exit.
- The next recommendation is discretionary rather than testable from the logs.

Avoid blockers by:

- Build the report against tiny fixture JSONL files before live data exists.
- If a component is unknown, report `unknown` with the missing source instead of silently using zero.
- Keep the report generation independent from network access.

### Goal 7: Light local dashboard

Build a real browser surface for watching and reviewing the paper run. The dashboard is in scope for the first usable system, but it must remain local, read-only, and evidence-backed.

Done when:

- `python -m polymarket_paper dashboard --data-dir data/runs/$RUN_DATE --host 127.0.0.1 --port 8765` serves a local page.
- The dashboard can load both an active partial run and a completed run.
- The dashboard shows run status, watched markets, skipped-market counts, top-of-book freshness, virtual quotes, simulated fills, exposure, PnL components, risk events, and arbitrage alerts.
- Stale, missing, polling fallback, and completed states are visually distinct.
- The dashboard reads from JSONL logs or derived read-only run state; it does not become a second source of accounting truth.

Failure looks like:

- The only usable output is terminal text or `summary.md`.
- The dashboard shows stale cached data as if it were live.
- The dashboard hides missing feeds, missing metadata, skipped markets, or risk events.
- The dashboard mutates quotes, strategy decisions, market selection, or any trading path.
- A frontend build tool or framework setup blocks the paper run when a simpler local page would work.

Avoid blockers by:

- Start with a single local page that polls a small JSON endpoint or reads a generated `dashboard_state.json`.
- Render from the same parser used by `report` so accounting and UI cannot drift.
- If live updating is not ready, serve completed-run review first and document live refresh as the next slice.
- Keep controls limited to local viewer actions such as refresh, run selection, and filters.

### Goal 8: Review gate before longer runs

Use the first short run as a system validation gate.

Done when:

- A 10 to 15 minute smoke run writes all required files.
- The local dashboard can open that run and correctly show active/completed state from the logs.
- The report identifies data gaps and skipped markets without crashing.
- Only then run the 60 to 90 minute morning paper session.

Failure looks like:

- The first long run is also the first end-to-end test.
- Codex keeps adding strategy features while the journal/report path is unproven.
- The dashboard is postponed so failures are only visible after reading raw files.

Avoid blockers by:

- Do not start arbitrage or reward modeling until discovery, data, quote journaling, and report replay work.
- Do not polish the dashboard before it faithfully shows the core run state.
- Prefer a boring complete run over a clever partial run.

## Blocker Avoidance Rules

- If the repo is not a git repository yet, keep edits doc/scaffold-local and say that branch/worktree/PR flow is blocked on repo initialization.
- If `make` targets are missing, create the harness before implementing strategy code.
- If package dependency setup blocks progress, use standard-library code or mark that dependency as optional for the first paper run.
- If WebSocket setup blocks progress, use polling and record `fallback_mode=polling`.
- If dashboard live refresh blocks progress, ship completed-run viewing first and keep run collection unblocked.
- If live API requests fail, retry with bounded backoff, write the failure to `risk_events.jsonl`, and keep the report command usable from any partial logs.
- If API field names drift, journal raw records, skip affected markets, and add a fixture for the new shape before normalizing it.
- If too few markets pass filters, do not relax safety filters during the run. Produce an observation-mode report that identifies which filter removed candidates.
- If fee, reward, tick-size, or min-size metadata is missing, use conservative behavior and record `unknown`, never optimistic defaults.
- If negative-risk or conversion mechanics are unclear, skip simulated execution and only log scanner context.
- If no fills occur, keep the result. Conservative no-fill evidence is better than fabricated activity.
- If a future task wants live trading, stop and create a separate explicit issue. Do not extend this command path.

## Runbook For Friday, May 1, 2026

From repo root:

```bash
cd /Users/dylanmccavitt/polymarket
export RUN_DATE=2026-05-01
```

If `python -m polymarket_paper --help` fails, do Goal 0 before running the rest of this runbook. If `make test` only checks imports or CLI help, do Goal 1 before trusting longer paper runs.

Preflight after Goal 0 and Goal 1 exist:

```bash
make lint
make typecheck
make test
curl -s "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume_24hr&ascending=false&limit=20" > /tmp/polymarket-events-preflight.json
curl -s "https://clob.polymarket.com/sampling-markets?limit=20" > /tmp/polymarket-sampling-preflight.json
```

Build or run the paper-only Polymarket path:

```bash
python -m polymarket_paper discover --limit 100 --out data/runs/$RUN_DATE/markets.jsonl
python -m polymarket_paper run --minutes 90 --max-markets 10 --max-virtual-exposure 100 --quote-size 5 --maker-only --out-dir data/runs/$RUN_DATE
python -m polymarket_paper report --date $RUN_DATE --data-dir data/runs/$RUN_DATE
python -m polymarket_paper dashboard --data-dir data/runs/$RUN_DATE --host 127.0.0.1 --port 8765
```

If the project scaffold or these commands do not exist yet, the first Codex tasks for Friday, May 1, 2026 are Goal 0 and Goal 1: implement the smallest version of the paper-only path and fixture-based signal tests behind paper-only guardrails. A standalone script under `scripts/` is allowed only as a same-day fallback if it writes the same output files and the handoff says it must be moved into module commands later.

## Required Outputs

The run directory must contain:

- `markets.jsonl`: discovered markets and filter decisions
- `books.jsonl`: orderbook snapshots or top-of-book stream events
- `quotes.jsonl`: virtual quotes with reason, side, price, size, and expiry
- `fills.jsonl`: conservative simulated fills with evidence event IDs
- `arb_alerts.jsonl`: binary or multi-outcome no-arb violations
- `risk_events.jsonl`: skipped markets, stale feeds, exposure caps, stop conditions
- `dashboard_state.json`: optional derived read-only snapshot for the local viewer
- `summary.md`: human-readable report

The report must include:

- markets watched
- markets skipped and why
- virtual quote count
- simulated fill count
- mark-to-mid PnL
- spread-capture PnL
- estimated fee/rebate/reward components
- max virtual exposure by market and side
- stale feed/disconnect count
- arbitrage alerts found
- exact checks run
- dashboard URL or dashboard verification result
- one recommended next experiment

## Risk Limits

- Paper only.
- Max virtual exposure: `$100` total.
- Max virtual exposure per market: `$25`.
- Max quote size: `5` shares unless min order size requires larger paper sizing.
- No market orders in the strategy.
- No taker simulation unless explicitly labeled as an arbitrage scanner calculation.
- Quote expiry: 30 seconds.
- Cancel virtual quote when spread widens beyond `0.05`, midpoint moves by more than `2` ticks, market is stale for more than `20` seconds, or market is within 30 minutes of resolution.
- Stop the whole run if websocket data is stale for more than 120 seconds, if more than 3 reconnects occur in 10 minutes, or if any real order/signing endpoint is called.

## Definition Of Done

The plan is done when all of these are true:

- Discovery fetches at least 20 active markets and records every filter decision.
- The selected watchlist contains at least 3 valid markets after filters, or the report explains why not.
- WebSocket or polling data runs for at least 60 continuous minutes.
- Every virtual quote has a deterministic reason and expiry.
- Every simulated fill cites the market-data event that caused it.
- Arbitrage scanner evaluates YES/NO sums for all watched binary markets.
- No real order endpoint, signing code, wallet key, or credential is used.
- End-of-run `summary.md` can reproduce PnL from the JSONL logs.
- Local dashboard opens the run and shows the same core counts and PnL components as `summary.md`.
- Paper-trading signal tests cover market filtering, conservative fill evidence, stale data, exposure stops, PnL replay, arbitrage math, and dashboard/report parity.
- `make lint`, `make typecheck`, and `make test` pass once the harness exists, or blockers are documented.
- Codex produces one next-step recommendation based only on the run logs.

## What Failure Looks Like

Safety failure:

- any live order, signing, wallet, allowance, or funded-account path is touched
- geoblock says trading is unavailable and code attempts to place or simulate real orders anyway
- the same CLI path can run both paper and live behavior
- credentials, wallet identifiers, private keys, account data, or raw funding details are required or logged

Data failure:

- no market data is written
- quotes or fills are generated without source orderbook/trade evidence
- expired or closed markets are selected for execution
- paper PnL cannot be reconstructed from logs
- raw API records are not preserved well enough to debug normalization errors
- missing fee/reward/tick-size/min-size metadata is silently treated as zero or favorable

Completeness failure:

- `discover`, `run`, or `report` cannot execute from a clean checkout after setup
- `dashboard` cannot display a completed run from existing logs
- a run exits without writing `summary.md`
- the process crashes on one malformed market instead of skipping and journaling the issue
- tests do not exercise paper-trading behavior or quality signals
- checks are skipped without a handoff note explaining the blocker

Soft outcomes that are not blockers:

- fewer than 3 markets pass filters
- websocket disconnects force a polling-only run
- no fills occur because the simulator is conservative
- no arbitrage alerts are found
- PnL is negative but all data, risk, and accounting are correct

Learning failure:

- the report only says profit/loss without decomposing spread capture, inventory mark, fees, rebates, rewards, and adverse selection
- the dashboard only shows vanity totals and does not expose skipped markets, stale data, risk events, and evidence-backed fill details
- Codex recommends a discretionary trade rather than a deterministic strategy change
- the next experiment cannot be tested with the same logs
- the run produces activity but no clearer decision about filters, data quality, simulator conservatism, or market class suitability

Operational failure:

- Codex is blocked because the next goal is too broad or depends on unknown external setup
- implementation skips fixture tests and depends on live API behavior for every check
- a dependency or WebSocket issue prevents the whole paper path from running when polling/reporting would have been enough
- frontend tooling blocks the paper system when a local read-only dashboard could have been served from static files and JSON
- handoff omits the next concrete command to run

## Next Implementation Slice

Implement the read-only Polymarket adapter first:

1. Fixture-based signal tests and tiny run-log examples.
2. Market discovery client for Gamma events/markets.
3. CLOB orderbook/top-of-book fetcher.
4. Public WebSocket subscriber with heartbeat.
5. Filter/scoring module.
6. Paper quote simulator.
7. JSONL journal and report.
8. Local read-only dashboard over the run directory.

Keep this project separate from the Alpaca repo. Do not import the existing `trades` package unless a later issue deliberately extracts a shared utility package.
