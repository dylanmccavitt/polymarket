# Paper Maker Risk Controls And Fill Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the paper maker system so the 60-second quote policy can be evaluated with concentration controls, post-fill adverse-selection evidence, and a required follow-up 30-minute session.

**Architecture:** Keep the paper engine read-only and evidence-backed. `risk.py` owns runtime fill/exposure limits, `simulator.py` keeps fill decisions conservative, and `report.py` remains the single replay path used by both `summary.md` and the dashboard. Run data stays under ignored `data/runs/` directories.

**Tech Stack:** Python standard library, `unittest`, JSONL replay, local read-only HTTP dashboard.

---

## Baseline Evidence

Use this as the comparison target after implementation:

- Baseline run directory: `data/runs/2026-05-01-expiry60`.
- Quote mode: `one_tick_inside`.
- Quote expiry: `60` seconds.
- Book events: `1,080`.
- Virtual quotes: `1,000`.
- Simulated fills: `46`.
- Denied fills: `0`.
- Mark-to-mid PnL: `2.825`.
- Fills by market:
  - `2090808`: `23`.
  - `2116590`: `18`.
  - `2074236`: `4`.
  - `2119381`: `1`.
- Concentration problem: `41 / 46` fills came from two markets.
- Policy replay problem: every quote policy was assessed as aggressive on adverse-selection evidence.
- Evidence limitation: fill evidence is `book_move_only`; public trade tape is not yet integrated.

## File Map

- Modify `polymarket_paper/risk.py`: add paper-only per-market and per-token fill caps, fill-count accounting, and structured denial reasons.
- Modify `polymarket_paper/simulator.py`: pass fill count decisions through `RiskState` and keep denied fills journalable with cited evidence.
- Modify `polymarket_paper/runner.py`: wire fill cap config into `RiskState`.
- Modify `polymarket_paper/cli.py`: add CLI options for the new paper-only caps.
- Modify `polymarket_paper/report.py`: add post-fill markout/adverse-selection replay and market suitability summaries.
- Modify `polymarket_paper/dashboard.py`: surface fill quality, market suitability, and concentration warnings from `build_run_state`.
- Modify `tests/test_simulator.py`: add cap-denial and no-optimistic-fill tests.
- Modify `tests/test_replay_dashboard.py`: add fixture replay tests for fill markout, adverse selection, concentration, and report/dashboard parity.
- Modify `docs/architecture.md`: document the new risk controls and fill-quality replay.
- Modify `docs/handoffs/polymarket-paper-maker-arb-run.md`: record checks, run result, dashboard URL, and next experiment after implementation.

## Task 1: Add Failing Tests For Fill Caps

**Files:**
- Modify: `tests/test_simulator.py`
- Modify later: `polymarket_paper/risk.py`
- Modify later: `polymarket_paper/simulator.py`

- [ ] **Step 1: Add a market fill cap test**

Add this test to `SimulatorTrustTests`:

```python
def test_market_fill_cap_denies_additional_bid_fills(self):
    risk = RiskState(max_total_exposure=100, max_market_fills=1, max_token_fills=10)
    sim = PaperSimulator(risk=risk, quote_size=5, quote_expiry_seconds=60)

    sim.generate_quotes(snapshot(event_id="book-1"), now=NOW)
    fills, _ = sim.process_snapshot(
        snapshot(event_id="book-fill-1", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
        now=NOW + timedelta(seconds=5),
    )
    self.assertEqual(fills[0]["type"], "simulated_fill")

    sim.generate_quotes(snapshot(event_id="book-2"), now=NOW + timedelta(seconds=6))
    denied, _ = sim.process_snapshot(
        snapshot(event_id="book-fill-2", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
        now=NOW + timedelta(seconds=10),
    )

    self.assertEqual(denied[0]["type"], "fill_denied")
    self.assertEqual(denied[0]["reason"], "market_fill_cap")
    self.assertEqual(denied[0]["evidence_event_id"], "book-fill-2")
```

- [ ] **Step 2: Add a token fill cap test**

Add this test to `SimulatorTrustTests`:

```python
def test_token_fill_cap_denies_additional_outcome_fills(self):
    risk = RiskState(max_total_exposure=100, max_market_fills=10, max_token_fills=1)
    sim = PaperSimulator(risk=risk, quote_size=5, quote_expiry_seconds=60)

    sim.generate_quotes(snapshot(event_id="book-1"), now=NOW)
    fills, _ = sim.process_snapshot(
        snapshot(event_id="book-fill-1", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
        now=NOW + timedelta(seconds=5),
    )
    self.assertEqual(fills[0]["type"], "simulated_fill")

    sim.generate_quotes(snapshot(event_id="book-2"), now=NOW + timedelta(seconds=6))
    denied, _ = sim.process_snapshot(
        snapshot(event_id="book-fill-2", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
        now=NOW + timedelta(seconds=10),
    )

    self.assertEqual(denied[0]["type"], "fill_denied")
    self.assertEqual(denied[0]["reason"], "token_fill_cap")
    self.assertEqual(denied[0]["evidence_event_id"], "book-fill-2")
```

- [ ] **Step 3: Run the tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_simulator.SimulatorTrustTests.test_market_fill_cap_denies_additional_bid_fills tests.test_simulator.SimulatorTrustTests.test_token_fill_cap_denies_additional_outcome_fills
```

Expected: both tests fail because `RiskState` does not accept `max_market_fills` or `max_token_fills`.

## Task 2: Implement Paper Fill Caps

**Files:**
- Modify: `polymarket_paper/risk.py`
- Modify: `polymarket_paper/runner.py`
- Modify: `polymarket_paper/cli.py`
- Test: `tests/test_simulator.py`

- [ ] **Step 1: Add fill cap fields to `RiskState`**

In `polymarket_paper/risk.py`, add these dataclass fields:

```python
max_market_fills: int = 8
max_token_fills: int = 4
fill_counts_by_market: dict[str, int] = field(default_factory=dict)
fill_counts_by_token: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 2: Add a reusable fill count decision**

Add this method to `RiskState`:

```python
def can_add_fill_count(self, market_id: str, token_id: str) -> RiskDecision:
    market_count = self.fill_counts_by_market.get(market_id, 0)
    token_key = self.token_key(market_id, token_id)
    token_count = self.fill_counts_by_token.get(token_key, 0)
    if market_count >= self.max_market_fills:
        return RiskDecision(
            False,
            "market_fill_cap",
            {"market_count": market_count, "cap": self.max_market_fills},
        )
    if token_count >= self.max_token_fills:
        return RiskDecision(
            False,
            "token_fill_cap",
            {"token_count": token_count, "cap": self.max_token_fills},
        )
    return RiskDecision(
        True,
        "allowed",
        {"market_count_after": market_count + 1, "token_count_after": token_count + 1},
    )
```

- [ ] **Step 3: Enforce fill caps before exposure checks**

Update `can_fill_bid`:

```python
def can_fill_bid(self, market_id: str, token_id: str, price: float, size: float) -> RiskDecision:
    fill_count = self.can_add_fill_count(market_id, token_id)
    if not fill_count.allowed:
        return fill_count
    return self.can_add_exposure(market_id, token_id, price * size)
```

Update `can_fill_ask`:

```python
def can_fill_ask(self, market_id: str, token_id: str, size: float) -> RiskDecision:
    fill_count = self.can_add_fill_count(market_id, token_id)
    if not fill_count.allowed:
        return fill_count
    held = self.shares(market_id, token_id)
    if held < size:
        return RiskDecision(False, "insufficient_inventory_for_ask", {"held": held, "size": size})
    return RiskDecision(True, "allowed")
```

- [ ] **Step 4: Increment fill counts in `record_fill`**

At the end of `record_fill`, before the return:

```python
self.fill_counts_by_market[market_id] = self.fill_counts_by_market.get(market_id, 0) + 1
self.fill_counts_by_token[key] = self.fill_counts_by_token.get(key, 0) + 1
```

Include counts in the returned exposure payload:

```python
"market_fill_count": self.fill_counts_by_market.get(market_id, 0),
"token_fill_count": self.fill_counts_by_token.get(key, 0),
```

- [ ] **Step 5: Wire CLI options**

In `polymarket_paper/cli.py`, add:

```python
run.add_argument("--max-fills-per-market", type=int, default=8)
run.add_argument("--max-fills-per-token", type=int, default=4)
```

Pass the args into `run_paper_session`.

- [ ] **Step 6: Wire runner config**

In `polymarket_paper/runner.py`, add parameters:

```python
max_fills_per_market: int = 8,
max_fills_per_token: int = 4,
```

Write them into the `run_started` event and create risk state with:

```python
risk = RiskState(
    max_total_exposure=max_virtual_exposure,
    max_market_fills=max_fills_per_market,
    max_token_fills=max_fills_per_token,
)
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
python3 -m unittest tests.test_simulator
```

Expected: all simulator tests pass.

- [ ] **Step 8: Commit**

Run:

```bash
git add polymarket_paper/risk.py polymarket_paper/runner.py polymarket_paper/cli.py tests/test_simulator.py
git commit -m "Add paper fill concentration caps"
```

## Task 3: Add Fill Markout And Adverse-Selection Replay

**Files:**
- Modify: `tests/test_replay_dashboard.py`
- Modify: `polymarket_paper/report.py`
- Modify: `polymarket_paper/dashboard.py`

- [ ] **Step 1: Add a fill markout replay test**

Add a fixture test that writes one bid fill at `0.50`, then later books with midpoints `0.48`, `0.47`, and `0.46`.

Assertion shape:

```python
state = build_run_state(run_dir)
quality = state["fill_quality"]

self.assertEqual(quality["fills_analyzed"], 1)
self.assertEqual(quality["adverse_selection_flags"], 1)
self.assertEqual(quality["horizons"]["30s"]["average_markout"], -0.02)
self.assertEqual(quality["horizons"]["60s"]["average_markout"], -0.03)
self.assertEqual(quality["horizons"]["120s"]["average_markout"], -0.04)
```

- [ ] **Step 2: Verify test failure**

Run:

```bash
python3 -m unittest tests.test_replay_dashboard.ReplayDashboardParityTests.test_fill_quality_reports_post_fill_markout
```

Expected: fail with missing `fill_quality`.

- [ ] **Step 3: Implement fill markout replay**

In `polymarket_paper/report.py`, add a helper that:

- Groups books by token.
- For each simulated fill, finds the first book at or after `fill_timestamp + horizon`.
- For bid fills, computes `midpoint - fill_price`.
- For ask fills, computes `fill_price - midpoint`.
- Counts an adverse-selection flag when markout is less than `-1 * tick_size`.

The state shape must be:

```python
"fill_quality": {
    "fills_analyzed": 46,
    "adverse_selection_flags": 0,
    "missing_markouts": 0,
    "horizons": {
        "30s": {"average_markout": 0.0, "adverse_count": 0, "sample_count": 0},
        "60s": {"average_markout": 0.0, "adverse_count": 0, "sample_count": 0},
        "120s": {"average_markout": 0.0, "adverse_count": 0, "sample_count": 0},
    },
}
```

- [ ] **Step 4: Add summary output**

In `render_summary`, add:

```markdown
## Fill Quality

- Fills analyzed: `{state["fill_quality"]["fills_analyzed"]}`
- Adverse-selection flags: `{state["fill_quality"]["adverse_selection_flags"]}`
- Missing markouts: `{state["fill_quality"]["missing_markouts"]}`
- 30s average markout: `{state["fill_quality"]["horizons"]["30s"]["average_markout"]}`
- 60s average markout: `{state["fill_quality"]["horizons"]["60s"]["average_markout"]}`
- 120s average markout: `{state["fill_quality"]["horizons"]["120s"]["average_markout"]}`
```

- [ ] **Step 5: Add dashboard output**

Add a dashboard panel named `Fill Quality` that renders `state.fill_quality`.

- [ ] **Step 6: Run focused replay tests**

Run:

```bash
python3 -m unittest tests.test_replay_dashboard
```

Expected: all replay/dashboard tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add polymarket_paper/report.py polymarket_paper/dashboard.py tests/test_replay_dashboard.py
git commit -m "Add fill quality markout replay"
```

## Task 4: Add Market Suitability Summary

**Files:**
- Modify: `tests/test_replay_dashboard.py`
- Modify: `polymarket_paper/report.py`
- Modify: `polymarket_paper/dashboard.py`

- [ ] **Step 1: Add a market suitability test**

Create a replay fixture with:

- Market `m-concentrated` with 9 fills and 6 adverse-selection flags.
- Market `m-balanced` with 2 fills and 0 adverse-selection flags.

Assert:

```python
state = build_run_state(run_dir)
suitability = {row["market_id"]: row for row in state["market_suitability"]}

self.assertEqual(suitability["m-concentrated"]["classification"], "risky_concentrated")
self.assertEqual(suitability["m-balanced"]["classification"], "candidate")
```

- [ ] **Step 2: Verify test failure**

Run:

```bash
python3 -m unittest tests.test_replay_dashboard.ReplayDashboardParityTests.test_market_suitability_classifies_concentration
```

Expected: fail with missing `market_suitability`.

- [ ] **Step 3: Implement market suitability**

In `polymarket_paper/report.py`, compute one row per watched market:

```python
{
    "market_id": "2090808",
    "quote_count": 0,
    "fill_count": 0,
    "fill_share": 0.0,
    "adverse_selection_flags": 0,
    "avg_ticks_missed": None,
    "expired_quotes": 0,
    "classification": "candidate",
    "reason": "balanced_fill_activity",
}
```

Classification rules:

- `insufficient_evidence`: fewer than `20` quotes.
- `risky_concentrated`: fill share is greater than `0.35` or fill count is greater than the configured market cap.
- `too_adverse`: adverse-selection flags are at least half of fills.
- `too_static`: market is already in `fill_opportunity["markets_too_static"]`.
- `candidate`: none of the above.

- [ ] **Step 4: Add summary output**

Add a `## Market Suitability` section listing each market id, classification, fill count, fill share, adverse flags, and reason.

- [ ] **Step 5: Add dashboard output**

Add a dashboard panel named `Market Suitability` that renders the same rows from `state.market_suitability`.

- [ ] **Step 6: Run focused replay tests**

Run:

```bash
python3 -m unittest tests.test_replay_dashboard
```

Expected: all replay/dashboard tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add polymarket_paper/report.py polymarket_paper/dashboard.py tests/test_replay_dashboard.py
git commit -m "Add market suitability replay"
```

## Task 5: Full Verification Before New Session

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/handoffs/polymarket-paper-maker-arb-run.md`

- [ ] **Step 1: Update architecture**

Document:

- Fill caps are paper-only runtime risk controls.
- Fill quality is replayed from JSONL and is not a profitability claim.
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

- [ ] **Step 3: Verify no live-trading path was added**

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
git commit -m "Document paper risk control improvements"
```

## Task 6: Required Post-Implementation 30-Minute Session

**Files:**
- Read: `data/runs/2026-05-01-risk-controls/summary.md`
- Read: `data/runs/2026-05-01-risk-controls/dashboard_state.json`
- Modify: `docs/handoffs/polymarket-paper-maker-arb-run.md`

- [ ] **Step 1: Run the improved 30-minute session**

Run this only after Tasks 1-5 pass:

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
  --out-dir data/runs/2026-05-01-risk-controls \
  --poll-seconds 30
```

- [ ] **Step 2: Generate the report**

Run:

```bash
python3 -m polymarket_paper report \
  --date 2026-05-01 \
  --data-dir data/runs/2026-05-01-risk-controls \
  --dashboard-url http://127.0.0.1:8768
```

- [ ] **Step 3: Start the dashboard**

Run:

```bash
python3 -m polymarket_paper dashboard \
  --data-dir data/runs/2026-05-01-risk-controls \
  --host 127.0.0.1 \
  --port 8768
```

- [ ] **Step 4: Verify dashboard state**

Run in another terminal:

```bash
python3 - <<'PY'
import json
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8768/state.json", timeout=5) as response:
    state = json.load(response)

assert state["status"] == "completed"
assert "fill_quality" in state
assert "market_suitability" in state
assert state["counts"]["fills_denied"] >= 0
print(state["counts"])
print(state["fill_quality"])
print(state["market_suitability"][:5])
PY
```

Expected: completed state with `fill_quality` and `market_suitability`.

- [ ] **Step 5: Compare against expiry-60 baseline**

Use these baseline numbers:

- `data/runs/2026-05-01-expiry60`: `46` fills.
- Top two market concentration: `41 / 46` fills.
- Mark-to-mid PnL: `2.825`.
- Adverse policy flags:
  - `best_bid`: `89`.
  - `one_tick_inside`: `96`.
  - `midpoint_when_spread_allows`: `96`.

Record whether the improved run:

- Keeps every fill evidence-backed.
- Reduces top-two market fill concentration.
- Produces `fill_denied` rows for concentration caps when applicable.
- Adds post-fill markout and adverse-selection counts.
- Avoids increasing quote aggressiveness.
- Preserves report/dashboard parity.

- [ ] **Step 6: Update handoff**

Append to `docs/handoffs/polymarket-paper-maker-arb-run.md`:

- Run command.
- Report command.
- Dashboard URL.
- Counts.
- Fill quality.
- Market suitability.
- Concentration comparison.
- Checks run.
- Blockers or risks.
- Next experiment.

- [ ] **Step 7: Commit handoff**

Run:

```bash
git add docs/handoffs/polymarket-paper-maker-arb-run.md
git commit -m "Record risk control paper run"
```

## Definition Of Done

- `make lint typecheck test` passes.
- Guardrail scan passes.
- No live trading, signing, wallet, allowance, credential, or private endpoint path is added.
- Fill caps can deny fills with cited evidence and structured reasons.
- Report and dashboard both show fill quality and market suitability from `build_run_state`.
- The required 30-minute post-implementation run completes in `data/runs/2026-05-01-risk-controls`.
- The post-implementation report compares concentration and adverse-selection evidence against `data/runs/2026-05-01-expiry60`.
- Handoff is updated and committed.

## Completion Notes For The Next Thread

Do not run a longer session until the 30-minute `risk-controls` run has been reviewed. A lower fill count is acceptable if concentration and adverse-selection risk improve. Do not treat positive PnL as proof of strategy quality while fees, rebates, rewards, and public trade evidence remain incomplete.
