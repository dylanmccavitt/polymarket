# Polymarket Paper Architecture

## Current System Shape

This repo contains a paper-only Polymarket research scaffold. It has no wallet, signing, allowance, private endpoint, or live trading path.

The runtime is a standard-library Python package exposed through `python3 -m polymarket_paper`.

## Major Components

- `polymarket_paper.cli`: command parser for `discover`, `run`, `report`, and `dashboard`.
- `polymarket_paper.adapters`: read-only public HTTP adapters for Gamma market discovery and CLOB orderbook polling.
- `polymarket_paper.filters`: market normalization and deterministic filter decisions.
- `polymarket_paper.runner`: orchestration for discovery, polling, quote generation, arbitrage scans, and report refresh.
- `polymarket_paper.risk`: central exposure, paper-only fill concentration, stale-feed, quote-expiry, spread-widening, and midpoint-move checks.
- `polymarket_paper.simulator`: virtual maker quotes, paper-only quote policy variants, configurable quote expiry, and conservative fill simulation.
- `polymarket_paper.arbitrage`: binary and multi-outcome no-arbitrage scanner math.
- `polymarket_paper.journal`: JSONL append/read helpers and required run-log files.
- `polymarket_paper.report`: JSONL replay, quote lifecycle diagnostics, fill-opportunity analysis, quote-policy comparison, PnL components, summary generation, and dashboard state.
- `polymarket_paper.dashboard`: local read-only HTTP server over replayed run evidence.
- `polymarket_paper.guardrails`: repository scan for live-trading code patterns.

## Main Flows

### Discovery

`discover` fetches public Gamma markets, normalizes each candidate, evaluates strict filters, and writes one row per candidate to `markets.jsonl`.

Every row keeps the raw API record, normalized fields, filter decision, and skip reason.

### Paper Run

`run` loads existing `markets.jsonl` or discovers markets, selects the filtered watchlist, records polling fallback mode, and polls public CLOB orderbooks.

Each snapshot is written to `books.jsonl`. The simulator generates paper maker quotes into `quotes.jsonl` only after risk checks pass. Quote records include the selected paper-only quote mode, expiry seconds, source book event, and placement context. Supported quote modes are `best_bid`, `one_tick_inside`, and `midpoint_when_spread_allows`; all remain maker-only.

Fills are written to `fills.jsonl` only when a later book event makes the virtual quote plausibly fillable. Paper-only per-market and per-token fill caps are enforced before exposure changes, and denied fills keep the same cited market-data evidence as simulated fills. Risk stops, quote cancellations, fetch failures, observation mode, public trade-evidence status, and run start/complete events go to `risk_events.jsonl`.

If fewer than three markets pass filters, the run enters observation mode instead of relaxing filters.

### Replay And Dashboard

`report` and `dashboard` both use `report.build_run_state`, so the terminal summary and browser UI derive from the same JSONL evidence.

Quote lifecycle diagnostics are reconstructed from `quotes.jsonl`, `books.jsonl`, `fills.jsonl`, and `risk_events.jsonl`. For each quote, replay records placement context, close reason, closest book approach, ticks missed, subsequent best book levels, and whether a longer expiry would have made the quote fillable under the same book-move evidence.

Fill quality is replayed from JSONL after the run. Post-fill markouts compare each simulated fill against later midpoint evidence at 30, 60, and 120 seconds, and adverse-selection flags are evidence diagnostics only, not profitability claims. Market suitability is also replayed from the same state, combining quote count, fill share, adverse-selection flags, expired quotes, static-market evidence, and configured paper fill caps.

The dashboard is local and read-only. It displays market names, outcomes, public book levels, mid-price history, virtual quote counts, fills, risk events, skipped-market reasons, fill-opportunity analysis, fill quality, market suitability, quote-policy comparison, and PnL components.

## Important Invariants

- Paper simulation is the only command path.
- Public market discovery and public orderbook polling are read-only.
- No command accepts credentials or account identifiers.
- Every selected market must pass explicit filters before quoting.
- Every simulated fill must cite an evidence event ID from the market-data log.
- Paper fill concentration caps must remain runtime risk controls only; they do not imply any live order or account capability.
- Quote diagnostics and policy comparisons must be replayable from persisted JSONL evidence.
- Fill quality, market suitability, reports, and the dashboard must continue to share `build_run_state`.
- Reports and dashboard state must be reproducible after process exit from JSONL logs.
- Missing metadata is conservative: skip or report `unknown`, never assume favorable values.
- Dashboard rendering must not mutate run logs, strategy decisions, or trading behavior.
