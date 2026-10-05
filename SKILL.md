---
name: spendlatch
description: Investigate cloud, AI and SaaS spend, prove a saving, and execute a cost action — but only inside a capped, single-use mandate that a human session approved. Use when asked to review bills, find waste, or cancel/rightsize a paid resource. Never use it to authorize your own action.
license: MIT
---

# SpendLatch

SpendLatch is the **authorization boundary between an AI agent and a
consequential action**. It is exposed as a self-hosted MCP server
(spec 2025-11-25, Streamable HTTP) with 13 tools.

## The one rule that matters

**You can propose. You cannot authorize yourself.**

`approve_action` exists on the tool list, but it refuses every call that does
not carry a browser session credential, and this surface exposes no credential
parameter at all. A refusal is not a bug to route around and not a permission
to ask the user to relax. It is the product working.

If you find yourself trying to approve, sign, or "just this once" execute
something — stop and hand it back to the human.

## The loop

```
detect  ->  prove  ->  propose  ->  [human approves]  ->  execute  ->  receipt
```

Each step produces an ID that chains to the previous one:
`execution -> mandate -> proposal -> the evidence the human actually read`.
Anything that skips a step is refused and logged.

## Tools

### Read (safe, call freely)

| Tool | What it answers |
|---|---|
| `spending_overview` | Where the money went this month |
| `detect_anomalies` | What looks wrong, with severity and evidence |
| `unit_economics` | Cost per task — the canary, not the smoke alarm |
| `list_subscriptions` | Recurring commitments |
| `budget_status` | Category budgets against actuals |
| `proactive_briefing` | What the agent would say unprompted |
| `decision_ledger` | Every decision, including everything it refused |

### Prove and propose

| Tool | What it does |
|---|---|
| `simulate_saving(action_id)` | Attach observations, assumptions and a pricing basis to a claim |
| `propose_action(action_id)` | Bind the proof to one concrete, bounded action — one provider, one operation, a dollar cap |

`propose_action` also links an interactive approval card as an MCP Apps
resource (`ui://spendlatch/approval-card`). If your host renders MCP Apps,
show it; the human signs there.

### Act (only inside a mandate)

| Tool | What it does |
|---|---|
| `mandate_status()` | Is there a live mandate, what is it scoped to |
| `execute_action(mandate_id)` | Run it — once |

`execute_action` re-checks the signature, expiry, single-use state, proof
hash and scope binding before anything runs. A mandate that has already been
spent, that expired (15-minute TTL), or whose facts drifted since approval is
refused.

### Do not call

`approve_action` — it resolves to a refusal on this surface by design.
Calling it to "check whether approval works" just writes another refusal to
a ledger a human will read.

## Reading a refusal

Refusals come back with a reason and a ledger sequence number. The common
ones:

- **no valid mandate** — nothing was approved yet. Propose, then wait.
- **already spent** — the mandate is single-use. Ask for a new approval; do
  not retry the same `mandate_id`.
- **expired** — 15-minute TTL. The proof may also have moved; re-propose.
- **scope drifted** — the adapter registry changed since approval. The
  mandate no longer describes the same action.
- **above cap** — the bill exceeds the approved amount.

Report the reason to the human in plain words. Never paper over it.

## Honest limits

- Provider adapters are **simulated**. Receipts say so (`simulated: true`).
  The mandate gate around them is real; the money movement is not.
- The proof bundle is a **same-secret self-verification** — it proves internal
  consistency with the server's own records, not independent attestation.
- The demo session credential is **self-issued**; its holder is not
  cryptographically proven. The mandate is a capability boundary (which
  surface may approve), not an identity boundary. See `docs/THREAT-MODEL.md`
  item L1.

Do not restate any of these as stronger than they are.

## Repository

`https://github.com/owain323/spendlatch` — MIT. `python run_checks.py`
reproduces every claim in the README.
