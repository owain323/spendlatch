# Scope Freeze

> Effective 2026-09-18. **No additional detection classes will be added before submission.**

## Supported — and only these

Detection classes (5):

1. Month-over-month spend spike (pct + absolute thresholds)
2. Sustained multi-month trend
3. Silent trial-to-paid conversion
4. Zombie subscription (unused >= 45 days while billing)
5. Cost-per-task drift for AI API providers (the canary metric)

Tool surface (9 MCP tools): `spending_overview`, `detect_anomalies`,
`simulate_saving`, `set_budget`, `budget_status`, `list_subscriptions`,
`unit_economics`, `proactive_briefing`, `decision_ledger`.

## Safety invariants

1. The agent never modifies, cancels, or purchases anything. It proposes; the human decides.
2. Missing or insufficient evidence is held and logged — never fabricated into a verdict.
3. A provider with fewer than 3 months of history returns `eligible: false` with a reason, not a guess.
4. All savings figures are labeled "scenario estimate".
5. Suppressed and held decisions are recorded in the ledger with reasons.

## Explicitly out of scope

- Real bank / card / provider API connections (synthetic data + future snapshot import only)
- Persistent monitoring dashboards (the agent pushes cards; there is no chart wall)
- Automatic cancellations, payments, or purchases
- Multi-currency conversion, tax advice, investment advice
- "Supports 50 providers" breadth claims — we do high-confidence detection on a declared surface
