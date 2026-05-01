# Polymarket Linear Track

Project: `Polymarket: live-state paper automation`

Project URL: `https://linear.app/agentcee/project/polymarket-live-state-paper-automation-a35d6bfcb6fd`

Parent issue: `AGE-396` - `Track: Polymarket live-state paper automation`

## Issue Order

| Issue | State | Purpose | Blocks |
| --- | --- | --- | --- |
| `AGE-397` | Human Review | Set up Polymarket Linear and Symphony control plane. | `AGE-398` |
| `AGE-398` | Backlog | Add same-run suitability brake for paper maker entries. | `AGE-399`, `AGE-400` |
| `AGE-399` | Backlog | Build WebSocket-first public market state engine. | `AGE-400`, `AGE-402` |
| `AGE-400` | Backlog | Add supervised automated paper daemon and kill switch. | `AGE-401`, `AGE-403`, `AGE-404`, `AGE-406` |
| `AGE-401` | Backlog | Expose active daemon state and alerts in the read-only dashboard. | `AGE-406` |
| `AGE-402` | Backlog | Add public trade-tape evidence to fill simulation diagnostics. | Follow-up strategy quality issues |
| `AGE-403` | Backlog | Create run-review command that opens follow-up Linear issues from evidence. | `AGE-406` |
| `AGE-404` | Backlog | Introduce execution adapter boundary with live trading disabled. | `AGE-405` |
| `AGE-405` | Backlog | Implement live-readiness checklist, geoblock check, and explicit opt-in gate. | `AGE-406` |
| `AGE-406` | Backlog | Run multi-session automated paper soak before any live order work. | Future live-order issue only if eligible |

## Trigger Rule

Move only the next unblocked issue to `Ready` or `Todo` when you want Symphony to work it. Keep blocked/future issues in `Backlog`.

## Dynamic Follow-Up Rule

Every issue must create a new Linear child issue under `AGE-396` when implementation or run review exposes an out-of-scope gap. Do not widen the active PR to cover adjacent work.

## Current Next Issue

After `AGE-397` lands, move `AGE-398` to `Ready`.

Do not start `AGE-399` or later before `AGE-398` proves same-run entry braking reduces concentration/open-inventory risk.
