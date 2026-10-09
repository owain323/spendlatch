# SpendLatch

[![CI](https://github.com/owain323/spendlatch/actions/workflows/ci.yml/badge.svg)](https://github.com/owain323/spendlatch/actions/workflows/ci.yml)

**Live demo:** https://spendlatch.owain32380.cn — the web experience and the
MCP endpoint (`/mcp`, Streamable HTTP) are both served publicly. All
providers are simulated; no credentials exist anywhere.

**MCP protocol & compatibility**

| | |
|---|---|
| Protocol | MCP 2025-11-25 (the track minimum) over Streamable HTTP |
| SDK | mcp>=1.12,<2 - pinned: mcp-sdk 2.0.0 removed mcp.server.fastmcp (upgrade = boot failure) |
| Verified | against our own wire round-trip probe (`tools/mcp_roundtrip.py`) — a real client against a real server subprocess; not a probe against Alexa+ itself |
| Upgrade path | 2026-07-28 revision (MCPServer rename, stateless model) planned post-hackathon - the legacy negotiation path is a safety valve, not a permanent home |

**The authorization boundary between an AI agent and a consequential action.**

An agentic spend-remediation copilot for AI and cloud teams — it watches your bills across providers, proves the next move before proposing it, and executes only inside a mandate the server issues after a human session approves. Every decision, including every refusal, is recorded.

> It doesn't wait for you to ask. It proves before it proposes. And it never moves a cent without your signed authorization.

### The one-line version

**"You are giving an AI permission to spend your money."**

Say *"buy me a replacement charger"* and the agent will find one, prove the
price is what it says, and then stop — because the decision is yours. What
you sign is not "yes". It is **this much, for this, once, until this time**,
recorded where neither of us can quietly edit it afterwards.

> *You let it decide for you. You did not hand it an unlimited amount of your money.*
> That gap — between "I trust you" and "here is an unbounded line of credit" —
> is the product. Everything below is how we make the gap mechanically real.

Built for the Amazon *Build, Ship, Shape* Hackathon (Alexa+ track). The tool
layer is a self-hosted **MCP server over Streamable HTTP** (spec 2025-11-25)
with an **MCP Apps** approval surface (SEP-1865); the web app is a
**simulated Alexa+ experience** — structured cards, spoken replies, voice
input where the browser exposes `SpeechRecognition`, and state that survives
across sessions. **Voice is progressive enhancement as of this commit, not
yet the primary path**: the mic button only appears where `SpeechRecognition`
exists (Chromium-family today), and reply speech is a toggle that starts off.
Making it voice-first is tracked work, not a shipped claim.

---

## Why 2026 needs this

Token prices fell ~280x in two years, yet AI bills kept climbing — agents fan
out into 10-200 metered calls per task. The bill problem is no longer per-token
price; it is **usage patterns and unit economics**. SpendLatch watches cost per
task (the canary), not just total spend (the smoke alarm) — and it does the same
for the rest of the team's stack: cloud, SaaS seats, trials, subscriptions.

And in 2026 the bar for agents moved again: agentic-payment protocols (AP2,
ACP, x402) all converged on the same shape — an agent that touches money must
carry **proof of human authorization, bounded in scope and time, with an audit
trail**. SpendLatch implements that shape end to end.

## The action loop — the part most demos skip

```
detect -> prove -> propose -> [human approves] -> signed mandate -> execute -> receipt
```

- **propose** — the agent attaches its proof to a concrete, bounded action
  (one provider, one operation, a dollar cap).
- **approve** — approval lives on a separate surface from execution. The
  browser mints a session token, and ONLY a request carrying it can approve;
  the MCP surface refuses approval by design (a caller self-reporting
  "approver=human" proves nothing), and the refusal is logged. The mandate —
  HMAC-SHA256, single-use, scope-capped, 15-minute expiry — records the
  approving session fingerprint and the proof hash of exactly what was
  approved. **What this is today:** a *capability* boundary (which surface may
  approve), not an *identity* boundary — the demo's session endpoint issues
  tokens without credential verification, so anyone who can reach the web
  surface can open a session and approve. **What it becomes with a real
  identity provider:** the same mandate, signed by an Alexa+ account-linked
  session (OAuth 2.1 + PKCE) or an AP2 verifiable credential, with the
  session token bound to a verified principal. The mandate format, the
  single-use nonce, the scope cap and the ledger are unchanged by that
  upgrade — only the proof of *who* approved becomes non-repudiable.
- **execute** — the provider adapter runs ONLY if the mandate verifies:
  signature, expiry, single-use under concurrency (process lock), proof
  hash still matching the approved evidence, and scope drift (if reality
  moved past the cap, execution is refused and re-approval is required).
- **receipt** — the adapter's report lands in the decision ledger.
- **every refusal is logged** — unknown, forged, expired, replayed, or
  drifted mandates all produce structured refusals with ledger entries.
  Nothing executes on trust.

## Authorization invariants

Seven properties the system must never lose, each with the code that holds
it and the test that fails if it stops holding. They are written down
because "we take security seriously" is not a claim anyone can check.

| # | Invariant | Held by | Fails when |
|---|---|---|---|
| **I1** | **Approval and execution are different surfaces.** The MCP tool surface cannot approve its own proposals. | `actions.approve_action` requires an authenticated web session token; the MCP tool calls with none and is refused and logged | `TestAuthorizationBoundary`, `test_approving_without_a_session_is_denied_and_logged` |
| **I2** | **No mandate, no motion.** A request to act without a valid mandate is refused, not queued and not performed. | `actions.execute_action` | `test_execute_with_no_mandate_is_denied_and_logged` |
| **I3** | **A mandate can produce at most one successful execution.** (The invariant is stated as an outcome, not as a field: `consumed == true` is the implementation, "at most one execution" is the promise.) | The claim is written *before* the provider runs and lives in `state["consumed"]`, deliberately *outside* the bounded ledger, so it cannot evaporate under log trimming or be re-armed by rewinding `status`. The whole check-claim-execute section runs under a process lock | `test_the_identical_request_twice_produces_one_receipt`, `test_rollback_of_status_does_not_allow_a_second_execution`, `test_ten_concurrent_executes_produce_exactly_one_receipt` (10 concurrent callers → 1 execution, 9 single-use refusals) |
| **I4** | **An issued mandate is immutable.** | Scope (provider, operation, cap) is inside `SIGNED_FIELDS`; editing it invalidates the HMAC — a raised cap becomes an *unsigned* mandate, not a bigger one | `test_raising_the_cap_after_approval_does_not_take_effect` |
| **I5** | **Approval expires.** | `MANDATE_TTL_SECONDS = 900`, a server constant, never a caller parameter | `test_a_truly_expired_mandate_is_refused` |
| **I6** | **The evidence you approved is the evidence that runs.** | `proof_hash` is signed into the mandate and re-derived at execution; drift, cap drift, and adapter-registry swaps are each refused separately | `test_proof_drift_since_approval_refused`, `test_bill_above_the_approved_cap_is_refused` |
| **I7** | **Front-end visibility is never an authorization primitive.** (The one most demos get wrong.) Hiding, disabling, or relabeling a control changes nothing on the server: every one of the checks above runs in `actions.*`, and every refusal is appended to the hash-chained ledger whether or not any UI ever showed it. | `tests/test_authorization_invariants.py` drives the HTTP route and asserts on server state, never on the DOM | the invariant suite is in the mutation set — deleting a guard turns it red |

The demo obeys one rule that follows from I7:

> **Demo attack paths may be synthetic. Authorization decisions may not be.**

An attack scenario may be staged (we can choose which attack to walk through,
and pre-generate its fixture). The refusal it produces is never staged: it is
computed by the same function the product runs in production, and it is
recorded in the same ledger. A truly expired mandate is one whose
`expires_at` is genuinely in the past — **never** a `if demo_mode: pretend_expired()`.

### What "single-use" does and does not mean

The precise claim is **single-use authorization with idempotent execution
semantics** — not "exactly once external spending".

- **What is enforced:** at most one execution per mandate, under sequential
  replay, status rollback, and 10-way concurrency; the claim is written
  *before* the provider runs, keyed by a nonce-derived `idempotency_key`, and
  a crash between claim and receipt leaves the mandate spent rather than
  silently re-armed.
- **What is not claimed:** the provider adapters are simulated. Against a real
  payment API, `state` and the external charge are **not** one atomic
  transaction — that needs the idempotency key to be honoured *downstream*
  (the receipt already carries it, which is the seam where it belongs).
- **Scope of the atomicity, stated so it is never over-read:** the
  serialization lock is **per process**. The deployed topology runs one
  process per service and mandates are workspace-scoped, so no two processes
  can execute the same mandate today. A multi-worker deployment would need a
  store-level lock; that is tracked work, not a shipped guarantee.

## Why it is not another expense tracker

- **Proactive, not reactive** — open the app and the agent speaks first: it has
  already swept your providers and found what needs attention.
- **Proof before proposals** — every saving suggestion ships with a
  before/after scenario estimate, a computed confidence level, a risk note, and
  the evidence chain. Estimates are never presented as realized savings.
- **Judgment, including refusal** — when spend growth tracks real value (API
  costs scaling with a launch), the agent says *do not cut this* and shows why.
- **Silence is auditable** — low-confidence findings are held, repeats are
  suppressed, and **every decision is logged with a reason** in the decision
  ledger. Ask "why didn't you tell me?" and get a real answer. Overrule any
  entry (`challenge #3`) and your overrule becomes context.
- **Cross-session memory** — budgets, acknowledgements, challenges, mandates,
  receipts, and the ledger persist server-side. Close the page, come back
  tomorrow: it remembers.
- **MCP Apps native** — `propose_action` links an interactive approval card
  (`ui://spendlatch/approval-card`, `text/html;profile=mcp-app`) that hosts
  render inline; the same HTML speaks the postMessage JSON-RPC bridge.
- **The MCP server is the product** — 13 typed tools, 201 pytest tests, a sealed
  benchmark; not a thin wrapper around an existing API.

  *The four numbers, stated so they cannot be confused:*
  **201** pytest tests collected — of which the gate's pytest step runs
  **199** and the remaining **2** (`tests/test_mcp_roundtrip.py`) run as the
  separate MCP step, because they spawn a real server subprocess.
  On top of that: **12/12** sealed benchmark cases, **8/8** MCP wire-probe
  steps, and **12/12** mutation guards killed. Those three are not pytest
  tests, and are never counted as such.

## Architecture

```
web/ (simulated Alexa+ experience)
  │  chat UI (typed + voice where supported) · evidence-chain cards · mandate/receipt cards · ledger panel
  ▼
agent/backend.py (FastAPI)  +  agent/brain.py (deterministic intent routing;
  │                                        LLM loop is an optional layer)
  ▼
mcp_server/server.py — MCP over Streamable HTTP (spec 2025-11-25, 13 tools)
  │                   + MCP Apps resource ui://spendlatch/approval-card (SEP-1865)
  ▼
mcp_server/tools.py (pure analysis — single source of truth)
  ├── sample_data.py  synthetic multi-provider bills, 6 months + task volumes
  ├── store.py        local JSON persistence = cross-session state
  ├── ledger.py       decision event stream (alert / suppress / hold / refuse / ...)
  ├── actions.py      mandate-gated loop: propose -> approve -> execute
  └── adapters.py     simulated provider adapters (aws / figma / zoom / openai)

benchmarks/           two-phase evaluation (predictions sealed before gold
                      labels are opened), three honestly-labeled tiers:
                      12 public regression fixtures + 14 independent
                      hand-written cases + a 24-case derived invariance
                      suite (mechanical transformations, labels gitignored)
docs/                 CLAIMS.md · SCOPE-FREEZE.md · JUDGE-REPRODUCTION.md · EVIDENCE.md
                      THREAT-MODEL.md (T1-T10 threats, defense, proof pointers)
                      PATTERNS.md (reusable modules for the next project)
                      LLM-PLANNER.md (optional Bedrock planner, off by default)
                      skills/ — one page per MCP tool: activation, flow, refusals
SHA256SUMS.txt        whole-repo integrity manifest
```

`tools.py` is implemented once and exposed three ways: over MCP, in-process
for the web agent, and inside the sealed benchmark. One implementation, three
surfaces.

Annotated walkthrough with figures: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
(system diagram, the mandate loop, and the claims-to-evidence map).

## Interface notes

- Icons: [Lucide](https://lucide.dev) (ISC license), inlined as SVG — no
  icon font, no build step, no npm. The app itself is three static files.
- Voice input is deliberately not surfaced in the UI: Web Speech API
  support varies by browser, and a control that only works sometimes is
  worse than no control. The keyboard is the primary path (the demo
  video shows voice running in Chrome).

## Quickstart

Requires Python ≥ 3.11. Zero credentials needed.

```bash
pip install -e .            # or: pip install mcp fastapi uvicorn pytest
python run_checks.py        # tests + sealed benchmark + MCP wire roundtrip + integrity + language

# Surface 1: the MCP server (Streamable HTTP)
python -m mcp_server.server          # http://127.0.0.1:8101/mcp
python tools/mcp_roundtrip.py        # or let a real MCP client prove it end to end

# Surface 2: the simulated Alexa+ web experience
python -m agent.backend              # http://127.0.0.1:8200
python tools/e2e_flow.py             # or let the probe drive the full flow
```

Open http://127.0.0.1:8200 — the agent opens the conversation. Try:

- `anything unusual?`
- `prove the saving` — then `approve` — then `execute`
- `execute` again — watch the replay get refused and logged
- `cost per task`
- `set a $300 budget for home`
- close the tab, reopen it — your budget is still there
- `why didn't you tell me?`

Judges: see [docs/JUDGE-REPRODUCTION.md](docs/JUDGE-REPRODUCTION.md) for the
5-minute, zero-credential reproduction protocol with pass criteria.

## Verification status

| Claim | Evidence |
|---|---|
| 201 automated tests pass — 199 in the pytest step + 2 wire round-trip run separately (tools, ledger, store, actions, planner, API, MCP wire) | `docs/evidence/test-run.txt` |
| Detection, three honestly-labeled tiers: public regression 12/12; independent hand-written suite 14/14 (boundary values, split verdicts, cross-rule interactions); derived invariance suite 24/24 (mechanical transformations of the public fixtures — proves invariance, NOT generalization) | `benchmarks/results/metrics.json`, `benchmarks/results/independent-metrics.json`, `benchmarks/results/derived-metrics.json` |
| Real MCP client roundtrip: protocol 2025-11-25, 13/13 tools, action loop + ui:// resource over the wire | `docs/evidence/mcp-roundtrip.txt` |
| End-to-end web flow (9 criteria, incl. mandate replay refusal) | `docs/evidence/e2e-flow.txt` |
| Proof bundle export + offline consistency check (7 checks over the bundle vs. the state file; same-secret self-verification — NOT independent attestation) | `tools/verify_proof.py`, `tests/test_verify.py` |
| Bill crossfoot: derived line items, internal consistency verified (demo-mode check on synthetic data — never "independently verified") | `mcp_server/crossfoot.py`, `tests/test_crossfoot.py` |

Full claim-to-evidence binding: [docs/CLAIMS.md](docs/CLAIMS.md).
Graded evidence register (what is NOT verified is marked so): [docs/EVIDENCE.md](docs/EVIDENCE.md).

## What "simulated" covers - and what it does not

The word "simulated" on this page is a scope statement, and it is narrower
than it looks. It covers exactly two things:

- the **front experience**: this is a simulated Alexa+ surface (the official
  submission path does not expose the Alexa+ toolkits to participants);
- the **provider adapters and billing data**: every bill is synthetic, no
  provider call ever leaves the machine, and receipts say so.

It does **not** cover the authorization machinery, which is real and runs
locally: mandates are signed with **HMAC-SHA256** under a per-installation
key that never leaves the server; the decision ledger is a **SHA-256 hash
chain** that detects any edit; exported proof bundles verify **offline**
with `tools/verify_proof.py`, without trusting the running system. The
attack page is the proof: the forged-scope attack is refused by the
signature check itself - a frontend string cannot fail that way.

## Security & privacy

- All billing data is **synthetic sample data**; no real accounts, credentials,
  or network calls to providers. Adapters are labeled `simulated: true`.
- State lives in one local JSON file (`data/state.json`, overridable via the
  `SPENDLATCH_STATE` env var). Nothing leaves your machine.
- The agent proposes; the human decides. Execution requires a signed,
  single-use, scope-capped, expiring mandate — and every refusal is logged.

## Roadmap (post-hackathon)

- **Standing mandates**: time-boxed, capped, revocable authorization for
  recurring low-risk operations - the deliberate-friction model stays for
  consequential actions, but "re-approve every few cents" is not the shape
  for a hundred calls a day.
- **Batch approval** with risk-based thresholds: one explicit yes covers a
  batch of mandates whose risk scores fall under a stated line; everything
  above it still asks.
- **Audit export** to SIEM formats (the ledger already is a hash chain; the
  export is a formatter, not a redesign).

- ~~Optional LLM loop~~ **Landed, off by default**: an LLM planner (Strands +
  Bedrock, `SPENDLATCH_LLM=bedrock`) converts free-form language into a
  structured SpendIntent — the deterministic brain routes it, policy still
  decides, and new spend is default-deny. See
  [docs/LLM-PLANNER.md](docs/LLM-PLANNER.md). Next: richer planner coverage
  and AgentCore deployment.
- Import real usage snapshots (CSV / provider exports) behind an explicit,
  local-only ingest path
- Production mandate signing bound to device keys / AP2 verifiable credentials,
  and real provider adapters behind the same mandate gate

## License

MIT — see [LICENSE](LICENSE).
