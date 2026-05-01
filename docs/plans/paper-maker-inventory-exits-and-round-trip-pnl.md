# Paper Maker Inventory Exits And Round Trip PnL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the paper maker system from evidence-backed entries into evidence-backed inventory exits, realized round-trip PnL, and a repeatable run/review loop for deciding which strategy changes actually worked.

**Architecture:** Keep the engine paper-only and read-only. `simulator.py` should generate entry bids and inventory exit asks, `risk.py` should protect new inventory without blocking de-risking exits, and `report.py` remains the single JSONL replay path for realized PnL, open inventory, stuck lots, summaries, and dashboard state.

**Tech Stack:** Python standard library, `unittest`, JSONL replay, local read-only HTTP dashboard.

---

## Why This Exists

The risk-controls run proved that concentration caps can reduce entry concentration:

- Baseline expiry-60 run: `46` fills, top two markets produced `41 / 46` fills, denied fills `0`.
- Risk-controls run: `26` fills, top two markets produced `13 / 26` fills, denied fills `19`.
- Risk-controls run also showed the next gap: a bid fill is only an entry. Mark-to-mid PnL is not the same as flipping inventory for realized profit.

This plan makes the next question measurable:

> Can the paper maker recycle inventory into evidence-backed exits, or is it only accumulating positions and relying on marks?

## Goals

- Generate explicit inventory exit ask quotes after bid fills.
- Require exit ask quotes to meet a configurable minimum profit target over average entry cost.
- Make entry concentration caps protect new inventory without blocking exit fills that reduce inventory.
- Replay bid-to-ask round trips from `fills.jsonl` and report realized PnL only when an evidence-backed ask fill exists.
- Track open inventory age, stuck inventory, fill-to-flip rate, average hold time, and unmatched exit anomalies.
- Add report and dashboard panels that separate realized round-trip PnL from mark-to-mid PnL.
- Run a short paper session after implementation and use the evidence to decide what strategy to improve next.

## Non-Goals

- No live trading.
- No signing, wallet, allowance, account, credential, or real order endpoint code.
- No claim that mark-to-mid PnL proves the strategy works.
- No directional probability model.
- No public trade-tape integration in this slice; book-move evidence remains acceptable but must be labeled.
- No longer session until the first exit/run review is complete.

## Current Behavior To Preserve

- `run` remains paper-only and requires `--maker-only`.
- Every simulated fill keeps an `evidence_event_id`.
- Reports and dashboard both use `report.build_run_state`.
- Run data stays under ignored `data/runs/` directories.
- Existing fill quality and market suitability output remains available.
- `make lint typecheck test` and `python3 -m polymarket_paper.guardrails` must pass.

## File Map

- Modify `polymarket_paper/risk.py`: separate entry fill caps from exit fills, add average entry price helpers, and preserve structured risk decisions.
- Modify `polymarket_paper/simulator.py`: add profit-targeted inventory ask quote generation and exit fill metadata.
- Modify `polymarket_paper/runner.py`: wire exit strategy config into `PaperSimulator` and journal it in `run_started`.
- Modify `polymarket_paper/cli.py`: add CLI options for exit profit target and stuck-inventory age threshold.
- Modify `polymarket_paper/report.py`: replay FIFO round trips, open inventory, stuck lots, realized PnL, and exit metrics.
- Modify `polymarket_paper/dashboard.py`: surface round-trip PnL, open inventory, stuck lots, and fill-to-flip metrics.
- Modify `tests/test_simulator.py`: add exit-quote target and cap-bypass tests.
- Modify `tests/test_replay_dashboard.py`: add round-trip replay, stuck inventory, and dashboard/report parity tests.
- Modify `docs/architecture.md`: document inventory exits and realized PnL boundaries.
- Modify `docs/handoffs/polymarket-paper-maker-arb-run.md`: record checks, run command, results, and review notes after the first run.

## Data Contract

### Exit Quote

Inventory exit ask quotes should remain normal `virtual_quote` rows with additional context:

```json
{
  "type": "virtual_quote",
  "side": "ask",
  "reason": "paper_maker_inventory_exit_one_tick_inside",
  "price": 0.53,
  "size": 5.0,
  "exit_context": {
    "average_entry_price": 0.51,
    "min_exit_price": 0.52,
    "min_exit_profit_ticks": 1,
    "available_inventory": 5.0,
    "expected_profit_per_share": 0.02
  }
}
```

### Exit Fill

Evidence-backed ask fills should remain normal `simulated_fill` rows with exit context:

```json
{
  "type": "simulated_fill",
  "side": "ask",
  "reason": "book_bid_traded_through_ask",
  "evidence_event_id": "book-exit-fill",
  "exit_context": {
    "average_entry_price": 0.51,
    "min_exit_price": 0.52,
    "min_exit_profit_ticks": 1
  }
}
```

### Round Trip Replay State

`build_run_state` must include:

```python
"round_trip_pnl": {
    "entry_fill_count": 0,
    "exit_fill_count": 0,
    "round_trip_count": 0,
    "entry_size": 0.0,
    "exit_size": 0.0,
    "realized_pnl": 0.0,
    "average_profit_per_share": 0.0,
    "average_hold_seconds": None,
    "fill_to_flip_rate": 0.0,
    "open_inventory_size": 0.0,
    "open_inventory_lots": 0,
    "stuck_inventory_lots": 0,
    "oldest_open_seconds": None,
    "unmatched_exit_size": 0.0,
}
```

`build_run_state` must also include `round_trips` and `open_inventory_lots` lists for dashboard detail.

## Task 1: Add Failing Simulator Tests For Inventory Exits

**Files:**
- Modify: `tests/test_simulator.py`
- Modify later: `polymarket_paper/risk.py`
- Modify later: `polymarket_paper/simulator.py`

- [ ] **Step 1: Add an exit quote profit-target test**

Add this test to `SimulatorTrustTests`:

```python
def test_inventory_exit_quote_requires_min_profit_target(self):
    risk = RiskState(max_total_exposure=100)
    risk.record_fill("m1", "yes", "bid", price=0.5, size=5)
    sim = PaperSimulator(
        risk=risk,
        quote_size=5,
        quote_expiry_seconds=60,
        min_exit_profit_ticks=2,
    )

    too_cheap = sim.generate_quotes(
        snapshot(best_bid=0.49, best_ask=0.51, midpoint=0.5, spread=0.02),
        now=NOW,
    )
    self.assertEqual([quote for quote in too_cheap if quote["side"] == "ask"], [])

    profitable = sim.generate_quotes(
        snapshot(event_id="book-profitable", best_bid=0.51, best_ask=0.54, midpoint=0.525, spread=0.03),
        now=NOW + timedelta(seconds=1),
    )
    asks = [quote for quote in profitable if quote["side"] == "ask"]

    self.assertEqual(len(asks), 1)
    self.assertEqual(asks[0]["side"], "ask")
    self.assertGreaterEqual(asks[0]["price"], 0.52)
    self.assertEqual(asks[0]["exit_context"]["average_entry_price"], 0.5)
    self.assertEqual(asks[0]["exit_context"]["min_exit_price"], 0.52)
    self.assertEqual(asks[0]["exit_context"]["min_exit_profit_ticks"], 2)
```

- [ ] **Step 2: Add an exit fill cap-bypass test**

Add this test to `SimulatorTrustTests`:

```python
def test_inventory_exit_fill_is_not_blocked_by_entry_fill_cap(self):
    risk = RiskState(max_total_exposure=100, max_market_fills=1, max_token_fills=1)
    risk.record_fill("m1", "yes", "bid", price=0.5, size=5)
    sim = PaperSimulator(
        risk=risk,
        quote_size=5,
        quote_expiry_seconds=60,
        min_exit_profit_ticks=1,
    )

    sim.generate_quotes(
        snapshot(event_id="book-exit-quote", best_bid=0.51, best_ask=0.54, midpoint=0.525, spread=0.03),
        now=NOW,
    )
    fills, risk_events = sim.process_snapshot(
        snapshot(event_id="book-exit-fill", best_bid=0.53, best_ask=0.55, midpoint=0.54, spread=0.02),
        now=NOW + timedelta(seconds=5),
    )

    exit_fills = [fill for fill in fills if fill["side"] == "ask"]
    self.assertEqual(risk_events, [])
    self.assertEqual(len(exit_fills), 1)
    self.assertEqual(exit_fills[0]["type"], "simulated_fill")
    self.assertEqual(exit_fills[0]["reason"], "book_bid_traded_through_ask")
    self.assertEqual(exit_fills[0]["evidence_event_id"], "book-exit-fill")
```

- [ ] **Step 3: Verify the tests fail**

Run:

```bash
python3 -m unittest \
  tests.test_simulator.SimulatorTrustTests.test_inventory_exit_quote_requires_min_profit_target \
  tests.test_simulator.SimulatorTrustTests.test_inventory_exit_fill_is_not_blocked_by_entry_fill_cap
```

Expected: failure because `PaperSimulator` does not accept `min_exit_profit_ticks` and `RiskState.can_fill_ask` still applies fill caps.

## Task 2: Implement Entry/Exit Risk Semantics

**Files:**
- Modify: `polymarket_paper/risk.py`
- Test: `tests/test_simulator.py`

- [ ] **Step 1: Add entry and exit count fields**

In `RiskState`, keep existing fields for compatibility and add exit counters:

```python
exit_counts_by_market: dict[str, int] = field(default_factory=dict)
exit_counts_by_token: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 2: Add average entry price helper**

Add:

```python
def average_entry_price(self, market_id: str, token_id: str) -> float | None:
    key = self.token_key(market_id, token_id)
    shares = self.positions.get(key, 0.0)
    if shares <= 0:
        return None
    return round(self.cash_by_token.get(key, 0.0) / shares, 6)
```

- [ ] **Step 3: Make fill caps entry-only**

Update `can_fill_bid` to keep checking `can_add_fill_count`.

Update `can_fill_ask` so it checks inventory only:

```python
def can_fill_ask(self, market_id: str, token_id: str, size: float) -> RiskDecision:
    held = self.shares(market_id, token_id)
    if held < size:
        return RiskDecision(False, "insufficient_inventory_for_ask", {"held": held, "size": size})
    return RiskDecision(True, "allowed")
```

- [ ] **Step 4: Count entries and exits separately in `record_fill`**

Update `record_fill` so bid fills increment `fill_counts_by_market` / `fill_counts_by_token`, and ask fills increment `exit_counts_by_market` / `exit_counts_by_token`.

The returned exposure payload must include:

```python
"market_fill_count": self.fill_counts_by_market.get(market_id, 0),
"token_fill_count": self.fill_counts_by_token.get(key, 0),
"market_exit_count": self.exit_counts_by_market.get(market_id, 0),
"token_exit_count": self.exit_counts_by_token.get(key, 0),
"average_entry_price": self.average_entry_price(market_id, token_id),
```

- [ ] **Step 5: Run focused risk tests**

Run:

```bash
python3 -m unittest \
  tests.test_simulator.SimulatorTrustTests.test_market_fill_cap_denies_additional_bid_fills \
  tests.test_simulator.SimulatorTrustTests.test_token_fill_cap_denies_additional_outcome_fills \
  tests.test_simulator.SimulatorTrustTests.test_exposure_cap_denies_fill
```

Expected: all three tests pass. The new inventory-exit tests still fail until Task 3 adds simulator support.

## Task 3: Add Profit-Targeted Exit Quote Generation

**Files:**
- Modify: `polymarket_paper/simulator.py`
- Test: `tests/test_simulator.py`

- [ ] **Step 1: Add simulator config**

Add dataclass fields to `PaperSimulator`:

```python
min_exit_profit_ticks: int = 1
```

In `__post_init__`, validate:

```python
if self.min_exit_profit_ticks < 0:
    raise ValueError("min_exit_profit_ticks must be nonnegative")
```

- [ ] **Step 2: Add an exit target helper**

Add:

```python
def _exit_context(self, snapshot: dict[str, Any], *, ask_price: float, held: float) -> dict[str, Any] | None:
    market_id = str(snapshot["market_id"])
    token_id = str(snapshot["token_id"])
    tick = float(snapshot.get("tick_size") or 0.01)
    average_entry = self.risk.average_entry_price(market_id, token_id)
    if average_entry is None:
        return None
    min_exit_price = round(average_entry + self.min_exit_profit_ticks * tick, 6)
    if ask_price < min_exit_price:
        return None
    return {
        "average_entry_price": average_entry,
        "min_exit_price": min_exit_price,
        "min_exit_profit_ticks": self.min_exit_profit_ticks,
        "available_inventory": round(held, 6),
        "expected_profit_per_share": round(ask_price - average_entry, 6),
    }
```

- [ ] **Step 3: Require exit context before writing ask quotes**

In `generate_quotes`, after computing `ask_price` and `ask_size`, call `_exit_context`.

Only append the ask quote when the context is present:

```python
exit_context = self._exit_context(snapshot, ask_price=ask_price, held=held)
if exit_context is not None:
    ask_quote = {
        **quote,
        "quote_id": ask_id,
        "side": "ask",
        "price": ask_price,
        "size": ask_size,
        "reason": f"paper_maker_inventory_exit_{self.quote_mode}",
        "placement_context": _placement_context(snapshot, side="ask", price=ask_price, mode=self.quote_mode),
        "exit_context": exit_context,
    }
    self.active_quotes[ask_id] = ask_quote
    quotes.append(ask_quote)
```

- [ ] **Step 4: Copy exit context into ask fills**

In `_try_fill`, include this key on returned fills:

```python
"exit_context": quote.get("exit_context"),
```

Keep this key present on bid fills too with `None`; that keeps downstream parsing simple.

- [ ] **Step 5: Run focused simulator tests**

Run:

```bash
python3 -m unittest tests.test_simulator
```

Expected: all simulator tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add polymarket_paper/risk.py polymarket_paper/simulator.py tests/test_simulator.py
git commit -m "Add profit-targeted inventory exits"
```

## Task 4: Add CLI And Runner Exit Config

**Files:**
- Modify: `polymarket_paper/cli.py`
- Modify: `polymarket_paper/runner.py`
- Test: `tests/test_simulator.py`

- [ ] **Step 1: Add CLI options**

In `cli.py`, add to the `run` parser:

```python
run.add_argument("--min-exit-profit-ticks", type=int, default=1)
run.add_argument("--stuck-inventory-minutes", type=float, default=20.0)
```

- [ ] **Step 2: Pass CLI config into runner**

Pass:

```python
min_exit_profit_ticks=args.min_exit_profit_ticks,
stuck_inventory_minutes=args.stuck_inventory_minutes,
```

- [ ] **Step 3: Add runner parameters**

In `run_paper_session`, add:

```python
min_exit_profit_ticks: int = 1,
stuck_inventory_minutes: float = 20.0,
```

Write both into the `run_started` event.

- [ ] **Step 4: Wire simulator**

Instantiate:

```python
simulator = PaperSimulator(
    risk=risk,
    quote_size=quote_size,
    quote_mode=quote_mode,
    quote_expiry_seconds=quote_expiry_seconds,
    min_exit_profit_ticks=min_exit_profit_ticks,
)
```

- [ ] **Step 5: Run CLI help check**

Run:

```bash
python3 -m polymarket_paper run --help
```

Expected: help includes `--min-exit-profit-ticks` and `--stuck-inventory-minutes`.

- [ ] **Step 6: Commit**

Run:

```bash
git add polymarket_paper/cli.py polymarket_paper/runner.py
git commit -m "Wire inventory exit run config"
```

## Task 5: Add Round-Trip Replay Tests

**Files:**
- Modify: `tests/test_replay_dashboard.py`
- Modify later: `polymarket_paper/report.py`

- [ ] **Step 1: Add a round-trip realized PnL fixture test**

Add a test to `ReplayDashboardParityTests` that writes one bid fill and one ask fill for the same token:

```python
def test_round_trip_replay_reports_realized_exit_pnl(self):
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = ensure_run_dir(Path(tmp))
        append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_started", "timestamp": "2026-05-01T12:00:00+00:00"})
        append_jsonl(
            run_dir / "markets.jsonl",
            {
                "type": "market_filter",
                "selected": True,
                "normalized": {
                    "market_id": "m1",
                    "question": "Round trip fixture?",
                    "slug": "round-trip-fixture",
                    "token_ids": ["yes"],
                    "outcomes": ["Yes"],
                },
            },
        )
        append_jsonl(
            run_dir / "fills.jsonl",
            {
                "type": "simulated_fill",
                "quote_id": "entry-q",
                "timestamp": "2026-05-01T12:00:00+00:00",
                "market_id": "m1",
                "token_id": "yes",
                "side": "bid",
                "price": 0.50,
                "size": 5,
                "evidence_event_id": "book-entry",
            },
        )
        append_jsonl(
            run_dir / "fills.jsonl",
            {
                "type": "simulated_fill",
                "quote_id": "exit-q",
                "timestamp": "2026-05-01T12:03:00+00:00",
                "market_id": "m1",
                "token_id": "yes",
                "side": "ask",
                "price": 0.53,
                "size": 5,
                "evidence_event_id": "book-exit",
            },
        )

        state = build_run_state(run_dir)
        round_trip = state["round_trip_pnl"]

        self.assertEqual(round_trip["entry_fill_count"], 1)
        self.assertEqual(round_trip["exit_fill_count"], 1)
        self.assertEqual(round_trip["round_trip_count"], 1)
        self.assertEqual(round_trip["realized_pnl"], 0.15)
        self.assertEqual(round_trip["average_profit_per_share"], 0.03)
        self.assertEqual(round_trip["average_hold_seconds"], 180.0)
        self.assertEqual(round_trip["fill_to_flip_rate"], 1.0)
        self.assertEqual(round_trip["open_inventory_size"], 0.0)
        self.assertEqual(state["round_trips"][0]["entry_evidence_event_id"], "book-entry")
        self.assertEqual(state["round_trips"][0]["exit_evidence_event_id"], "book-exit")
```

- [ ] **Step 2: Add a stuck inventory fixture test**

Add:

```python
def test_round_trip_replay_reports_stuck_open_inventory(self):
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = ensure_run_dir(Path(tmp))
        append_jsonl(
            run_dir / "risk_events.jsonl",
            {
                "type": "run_started",
                "timestamp": "2026-05-01T12:00:00+00:00",
                "stuck_inventory_minutes": 20,
            },
        )
        append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_completed", "timestamp": "2026-05-01T12:45:00+00:00"})
        append_jsonl(
            run_dir / "markets.jsonl",
            {
                "type": "market_filter",
                "selected": True,
                "normalized": {
                    "market_id": "m1",
                    "question": "Stuck fixture?",
                    "slug": "stuck-fixture",
                    "token_ids": ["yes"],
                    "outcomes": ["Yes"],
                },
            },
        )
        append_jsonl(
            run_dir / "fills.jsonl",
            {
                "type": "simulated_fill",
                "quote_id": "entry-q",
                "timestamp": "2026-05-01T12:00:00+00:00",
                "market_id": "m1",
                "token_id": "yes",
                "side": "bid",
                "price": 0.50,
                "size": 5,
                "evidence_event_id": "book-entry",
            },
        )

        state = build_run_state(run_dir)
        round_trip = state["round_trip_pnl"]

        self.assertEqual(round_trip["entry_fill_count"], 1)
        self.assertEqual(round_trip["exit_fill_count"], 0)
        self.assertEqual(round_trip["open_inventory_size"], 5.0)
        self.assertEqual(round_trip["open_inventory_lots"], 1)
        self.assertEqual(round_trip["stuck_inventory_lots"], 1)
        self.assertEqual(round_trip["oldest_open_seconds"], 2700.0)
        self.assertEqual(state["open_inventory_lots"][0]["status"], "stuck")
```

- [ ] **Step 3: Verify the tests fail**

Run:

```bash
python3 -m unittest \
  tests.test_replay_dashboard.ReplayDashboardParityTests.test_round_trip_replay_reports_realized_exit_pnl \
  tests.test_replay_dashboard.ReplayDashboardParityTests.test_round_trip_replay_reports_stuck_open_inventory
```

Expected: failure because `round_trip_pnl`, `round_trips`, and `open_inventory_lots` are missing.

## Task 6: Implement FIFO Round-Trip Replay

**Files:**
- Modify: `polymarket_paper/report.py`
- Test: `tests/test_replay_dashboard.py`

- [ ] **Step 1: Add run end and stuck-threshold helpers**

Add helpers that derive run end time from the latest `run_completed` timestamp or latest fill/book/risk timestamp. Derive `stuck_inventory_minutes` from the latest `run_started` event, defaulting to `20.0`.

- [ ] **Step 2: Add FIFO lot replay helper**

Add a helper named `_round_trip_replay(fills, risk_events)` that:

- Treats `side == "bid"` simulated fills as entry lots.
- Treats `side == "ask"` simulated fills as exits.
- Matches exits against open lots for the same `market_id` and `token_id` FIFO.
- Computes realized PnL only for matched size: `(exit_price - entry_price) * matched_size`.
- Carries `entry_evidence_event_id` and `exit_evidence_event_id` into each round-trip row.
- Leaves unmatched bid size in `open_inventory_lots`.
- Records unmatched ask size as `unmatched_exit_size`.

- [ ] **Step 3: Use this round-trip row shape**

Each row in `round_trips` must include:

```python
{
    "market_id": "m1",
    "token_id": "yes",
    "entry_quote_id": "entry-q",
    "exit_quote_id": "exit-q",
    "entry_timestamp": "2026-05-01T12:00:00+00:00",
    "exit_timestamp": "2026-05-01T12:03:00+00:00",
    "entry_price": 0.5,
    "exit_price": 0.53,
    "size": 5.0,
    "realized_pnl": 0.15,
    "profit_per_share": 0.03,
    "hold_seconds": 180.0,
    "entry_evidence_event_id": "book-entry",
    "exit_evidence_event_id": "book-exit",
}
```

- [ ] **Step 4: Use this open lot shape**

Each row in `open_inventory_lots` must include:

```python
{
    "market_id": "m1",
    "token_id": "yes",
    "entry_quote_id": "entry-q",
    "entry_timestamp": "2026-05-01T12:00:00+00:00",
    "entry_price": 0.5,
    "open_size": 5.0,
    "age_seconds": 2700.0,
    "status": "stuck",
    "entry_evidence_event_id": "book-entry",
}
```

- [ ] **Step 5: Add aggregate state to `build_run_state`**

Add:

```python
"round_trip_pnl": round_trip_summary,
"round_trips": round_trips[-50:],
"open_inventory_lots": open_lots,
```

The aggregate must round numeric values to 6 decimals where useful.

- [ ] **Step 6: Run focused replay tests**

Run:

```bash
python3 -m unittest tests.test_replay_dashboard
```

Expected: all replay/dashboard tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add polymarket_paper/report.py tests/test_replay_dashboard.py
git commit -m "Add round trip PnL replay"
```

## Task 7: Add Summary And Dashboard Output

**Files:**
- Modify: `polymarket_paper/report.py`
- Modify: `polymarket_paper/dashboard.py`
- Test: `tests/test_replay_dashboard.py`

- [ ] **Step 1: Add report summary section**

In `render_summary`, add `## Round Trip PnL` after `## PnL Components`:

```markdown
## Round Trip PnL

- Entry fills: `...`
- Exit fills: `...`
- Round trips: `...`
- Realized round-trip PnL: `...`
- Average profit per share: `...`
- Average hold seconds: `...`
- Fill-to-flip rate: `...`
- Open inventory size: `...`
- Open inventory lots: `...`
- Stuck inventory lots: `...`
- Oldest open seconds: `...`
- Unmatched exit size: `...`
```

- [ ] **Step 2: Add dashboard panels**

In `dashboard.py`, add panels named:

- `Round Trip PnL`
- `Open Inventory`
- `Recent Round Trips`

Use `state.round_trip_pnl`, `state.open_inventory_lots`, and `state.round_trips`.

- [ ] **Step 3: Add parity assertion**

In the round-trip test, after `generate_report`, assert:

```python
summary = (run_dir / "summary.md").read_text(encoding="utf-8")
self.assertIn("## Round Trip PnL", summary)
self.assertIn("Realized round-trip PnL", summary)
self.assertEqual(generate_report(run_dir)["round_trip_pnl"], build_run_state(run_dir)["round_trip_pnl"])
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
python3 -m unittest tests.test_replay_dashboard
```

Expected: all replay/dashboard tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add polymarket_paper/report.py polymarket_paper/dashboard.py tests/test_replay_dashboard.py
git commit -m "Surface inventory exits in reports"
```

## Task 8: Full Verification And Documentation

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/handoffs/polymarket-paper-maker-arb-run.md`

- [ ] **Step 1: Update architecture**

Document:

- Entry bids open inventory.
- Exit asks reduce inventory and are not blocked by entry concentration caps.
- Realized round-trip PnL requires matched bid and ask fills with evidence IDs.
- Mark-to-mid PnL remains diagnostic and separate from realized round-trip PnL.
- Dashboard and report still share `build_run_state`.

- [ ] **Step 2: Run full checks**

Run:

```bash
make lint typecheck test
```

Expected:

```text
paper-only guardrail scan passed
Ran the discovered unittest suite
OK
```

- [ ] **Step 3: Run explicit guardrail scan**

Run:

```bash
python3 -m polymarket_paper.guardrails
```

Expected:

```text
paper-only guardrail scan passed
```

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/architecture.md docs/handoffs/polymarket-paper-maker-arb-run.md
git commit -m "Document inventory exit metrics"
```

## Task 9: Required Exit Strategy Paper Run

**Files:**
- Read: `data/runs/2026-05-01-risk-controls/summary.md`
- Read: `data/runs/2026-05-01-exit-v1/summary.md`
- Read: `data/runs/2026-05-01-exit-v1/dashboard_state.json`
- Modify: `docs/handoffs/polymarket-paper-maker-arb-run.md`

- [ ] **Step 1: Run a 30-minute exit-v1 session**

Run only after Tasks 1-8 pass:

```bash
python3 -m polymarket_paper run \
  --minutes 30 \
  --max-markets 10 \
  --max-virtual-exposure 100 \
  --quote-size 5 \
  --maker-only \
  --quote-mode one_tick_inside \
  --quote-expiry-seconds 60 \
  --max-fills-per-market 8 \
  --max-fills-per-token 4 \
  --min-exit-profit-ticks 1 \
  --stuck-inventory-minutes 20 \
  --out-dir data/runs/2026-05-01-exit-v1 \
  --poll-seconds 30
```

- [ ] **Step 2: Generate the report**

Run:

```bash
python3 -m polymarket_paper report \
  --date 2026-05-01 \
  --data-dir data/runs/2026-05-01-exit-v1 \
  --dashboard-url http://127.0.0.1:8769
```

- [ ] **Step 3: Start the dashboard**

Run:

```bash
python3 -m polymarket_paper dashboard \
  --data-dir data/runs/2026-05-01-exit-v1 \
  --host 127.0.0.1 \
  --port 8769
```

- [ ] **Step 4: Verify dashboard state**

Run in another terminal:

```bash
python3 - <<'PY'
import json
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8769/state.json", timeout=5) as response:
    state = json.load(response)

assert state["status"] == "completed"
assert "round_trip_pnl" in state
assert "round_trips" in state
assert "open_inventory_lots" in state
assert "fill_quality" in state
assert "market_suitability" in state
print(state["counts"])
print(state["round_trip_pnl"])
print(state["round_trips"][:5])
print(state["open_inventory_lots"][:5])
PY
```

Expected: completed state with round-trip and open-inventory metrics.

- [ ] **Step 5: Compare against risk-controls run**

Use these comparison targets:

- `data/runs/2026-05-01-risk-controls`: `26` fills, `19` denied fills, top two markets `13 / 26`, mark-to-mid PnL `1.475`, no realized round-trip metric.

Record whether the exit-v1 run:

- Preserves evidence-backed fills.
- Produces ask exit fills.
- Produces realized round-trip PnL.
- Improves fill-to-flip rate above `0`.
- Reduces open inventory size or age.
- Avoids increasing top-two concentration.
- Keeps denied-fill reasons structured.
- Preserves report/dashboard parity.

- [ ] **Step 6: Decide next strategy change from evidence**

Use these rules:

- If entries occur but exits are rare, test lower `--min-exit-profit-ticks` only if adverse-selection flags are acceptable.
- If entries occur and exits lose money, widen the exit target or block `too_adverse` markets.
- If exits are profitable but fill-to-flip rate is low, test shorter quote expiry before increasing quote aggressiveness.
- If stuck inventory dominates, reduce entry size or require market suitability `candidate` before new entries.
- If round trips are profitable and inventory recycles cleanly, run one more 30-minute confirmation before any longer session.

- [ ] **Step 7: Update handoff**

Append:

- Run command.
- Report command.
- Dashboard URL.
- Counts.
- Round-trip PnL.
- Fill-to-flip rate.
- Open inventory and stuck inventory.
- Fill quality.
- Market suitability.
- Comparison against `2026-05-01-risk-controls`.
- Checks run.
- What worked.
- What did not work.
- Next strategy change.

- [ ] **Step 8: Commit handoff**

Run:

```bash
git add docs/handoffs/polymarket-paper-maker-arb-run.md
git commit -m "Record inventory exit paper run"
```

## Definition Of Done

- `make lint typecheck test` passes.
- `python3 -m polymarket_paper.guardrails` passes.
- No live trading, signing, wallet, allowance, credential, or private endpoint path is added.
- Inventory exit ask quotes are generated only when they meet the configured minimum profit target.
- Entry concentration caps do not block inventory-reducing exit fills.
- Realized PnL is counted only from matched bid-entry and ask-exit fills with evidence IDs.
- Mark-to-mid PnL and realized round-trip PnL are reported separately.
- Report and dashboard both show round-trip PnL, fill-to-flip rate, open inventory, stuck inventory, fill quality, and market suitability from `build_run_state`.
- The required 30-minute exit-v1 run completes in `data/runs/2026-05-01-exit-v1`.
- The exit-v1 report compares realized exits, open inventory, concentration, and adverse-selection evidence against `data/runs/2026-05-01-risk-controls`.
- Handoff is updated and committed with what worked, what did not work, and the next strategy change.

## Completion Notes For The Next Thread

Do not optimize for more entries until exits are measured. A lower fill count is acceptable if the strategy recycles inventory and produces evidence-backed realized PnL. Do not treat mark-to-mid PnL as profit. Do not run a longer session until the first exit-v1 run has been reviewed.
