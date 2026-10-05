# SpendLatch — Devpost submission copy

Paste-ready. The submission is the Alexa+ Developer Track plus the Open Source
mini challenge. Every claim here is checkable against the repository, and
`python run_checks.py` is the single command that proves it.

This file is the single source for the submission text. If it drifts from the
code, `tools/check_submission.py` fails the build.

---

## 1. Project tagline

```
The authorization boundary between an AI agent and a consequential action.
```

---

## 2. Project Story

### Inspiration

**You are giving an AI permission to spend your money.** That sentence is easy to say and surprisingly hard to make true.

I kept asking AI assistants to do things for me — move money, buy things, run cloud jobs. And every time, the same uncomfortable question came back: what exactly is this agent allowed to spend? Dashboards can show me what already happened. That is not the same as deciding what is allowed to happen. So I built the thing that was missing: a small, verifiable boundary that sits between an AI agent and any action that costs money. You let it decide for you; you did not hand it an unlimited amount of your money.

### What it does

SpendLatch is the authorization boundary between an AI agent and a consequential action. The agent watches spending data, proves a saving opportunity with evidence, and proposes an exact action — then stops. Nothing runs until a human approves a signed mandate: this exact action, on this provider, capped at this dollar amount, once, for fifteen minutes. If the request no longer matches the signed proof, it is rejected. Replaying the mandate fails — the nonce is single-use. Asking the agent to approve itself through MCP is refused and logged. Every approval exports a proof bundle that can be verified offline, without trusting the running system.

### The boundary, stated as seven invariants

"We take this seriously" is not checkable. This is:

1. **Approval and execution are different surfaces.** The MCP tool surface cannot approve its own proposals — it is refused and logged.
2. **No mandate, no motion.** An action without a valid mandate is refused, never queued.
3. **A mandate is single-use**, and single-use is not bookkeeping: it lives outside the bounded ledger, so log trimming or a status rewind cannot re-arm a spent mandate.
4. **An issued mandate is immutable.** Raise the cap after approval and the signature breaks — it becomes an unsigned mandate, not a bigger one.
5. **Approval expires** in fifteen minutes, a server constant no caller can set.
6. **The evidence you approved is the evidence that runs.** Proof, cap, and adapter-registry drift are each refused separately.
7. **Front-end visibility is never an authorization primitive.** Hide or disable any control and the server refuses exactly the same way — and records it either way.

Every one of these has a test that fails when the guard behind it is deleted, and `tools/mutation_check.py` proves that by deleting them.

### How we built it

- A deterministic policy gate (Python) parses every request into a SpendIntent and decides — the LLM never owns financial authority.
- A plan-check-execute ledger keeps the hash-chained decision ledger: every alert, hold, suppression and refusal is recorded with evidence.
- A sandbox AWS adapter runs the approved action and issues a receipt bound to the mandate.
- An MCP server (2025-11-25, Streamable HTTP) exposes the same tools to agent surfaces, but approval only exists on the human web surface.
- The web demo (FastAPI backend, zero-build vanilla JS frontend) runs live at https://spendlatch.owain32380.cn — you can run the full loop yourself: ask, prove, approve, execute, replay.

### Challenges we ran into

The hardest part was not the agent — it was making the boundary boring and precise. Defining what a mandate can and cannot express took several iterations. Making replay protection work under a single-use nonce plus a 15-minute expiry, and proving it with a real rejected replay, took care. The AWS sandbox adapter had to be labeled honestly: the receipt says "simulated adapter" today, and the real API path is designed but not yet switched on.

### Accomplishments that we're proud of

- The agent proposes but cannot authorize itself — demonstrated live, including a logged refusal.
- Every ID is chained: execution → mandate → proposal → the evidence the human actually read.
- The demo is reproducible from open-source code, and the proof bundle verifies offline.

### What we learned

Authorization is a product surface, not a middleware detail. The moment you make it visible — mandate cards, receipts, a decision ledger — people start asking for it everywhere.

### What's next

Bring SpendLatch to Alexa+: a human approves on the phone, the voice agent can then execute exactly what was approved — once, within the cap. Real AWS API calls through the adapter. Conformance tests for anyone building their own boundary.

---

## 3. Product Feedback Set

The track asks five questions per tool. Two surfaces are covered here: the web
experience and the MCP server. Replace each `[TOOL]` heading with the surface
name when pasting.



### [TOOL] = SpendLatch Web Chat

**Q1. How does the user invoke this tool?**
User opens https://spendlatch.owain32380.cn and types plain questions like "anything unusual?" or "prove the saving". The agent opens the conversation itself — it does not wait to be asked.

**Q2. How does the user provide input to this tool?**
Plain language in a chat box. The planner parses it into a SpendIntent; the same deterministic policy gate handles typed phrases and agent proposals alike.

**Q3. How does the tool communicate results back to the user?**
Structured cards in the conversation: anomaly cards with severity and evidence, a proposal card, an approval card with the full mandate scope, a receipt card, and a decision ledger panel that records every decision with its evidence.

**Q4. How does the user provide feedback on the response?**
The user can ask "why didn't you tell me?" — the agent answers from its decision ledger, including what it held back and why. Rejections are logged as ledger entries, not silent failures.

**Q5. Give an example of the end-to-end user flow.**
User: "anything unusual?" → agent shows 4 evidence cards (including one that says do NOT cut). User: "prove the saving" → agent attaches observations, assumptions, and pricing basis to the claim. User: "approve" → a signed mandate is issued. User: "execute" → the action runs once through the adapter and a receipt is recorded. User: "execute" again → refused, and the refusal is in the ledger.

### [TOOL] = SpendLatch MCP Server

**Q1. How does the user invoke this tool?**
The MCP server (protocol 2025-11-25, Streamable HTTP) is exposed at https://spendlatch.owain32380.cn/mcp. An agent surface (Claude Desktop, any MCP client) connects and lists 13 tools: spending_overview, detect_anomalies, simulate_saving, set_budget, budget_status, list_subscriptions, unit_economics, proactive_briefing, decision_ledger, propose_action, approve_action, execute_action, mandate_status.
Run `python tools/mcp_roundtrip.py` to reproduce this list over the wire, against a real server subprocess.

**Q2. How does the user provide input to this tool?**
The agent calls the tools with structured arguments on the user's behalf. Approval is the exception: approve_action only exists on the human web surface — the MCP surface can execute, but cannot approve itself.

**Q3. How does the tool communicate results back to the user?**
The same structured cards and receipts as the web surface, plus the hash-chained ledger entry. A refused execution returns the refusal reason and the ledger sequence number.

**Q4. How does the user provide feedback on the response?**
Every refusal is a first-class ledger entry ("refuse"), so "why did you not act" always has an answer the user can verify.

**Q5. Give an example of the end-to-end user flow.**
The agent asks the server for anomalies, gets evidence, tries to execute without a mandate, and is refused with "I hold no valid mandate, so I will not act" — the refusal is recorded in the ledger as a first-class entry. The human approves on the web surface; only then does the same MCP execution path succeed, once.

### [TOOL] = MCP Python SDK (`mcp>=1.12,<2`)

**Q1. How does the user invoke this tool?**
It is imported and called at runtime by the MCP server entry point, which
builds a `FastMCP` instance and serves it over Streamable HTTP at
`https://spendlatch.owain32380.cn/mcp`. Not a README mention — the package is
imported and the server is booted from it.

**Q2. How does the user provide input to this tool?**
Python decorators plus typed signatures: each of the 13 tools declares its own argument types, and the SDK derives the schema and validates the call. `propose_action` additionally carries MCP Apps metadata (`_meta.ui.resourceUri`) pointing at the approval card.

**Q3. How does the tool communicate results back to the user?**
Structured content per tool call, plus structured errors on the refusal paths — a refusal is a typed response with a reason and a ledger sequence number, not an exception with a traceback.

**Q4. How does the user provide feedback on the response?**
The wire probe (`tools/mcp_roundtrip.py`) is the feedback channel we actually use: eight assertions over a real client against a real server subprocess, run inside both pytest and CI.

**Q5. Give an example of the end-to-end user flow.**
Client calls `initialize` → protocol 2025-11-25 negotiated → `tools/list` returns 13 tools → `tools/call` on the read-only surface returns valid structured content → `set_budget` then `budget_status` agree over the wire → an `approve_action` call carrying no session credential is refused, and that refusal appears in `decision_ledger`.

### [TOOL] = FastAPI

**Q1. How does the user invoke this tool?**
`agent/backend.py` is a FastAPI application serving the web surface: `/` returns the page, `/static/*` the assets, and `/api/*` the chat, session, ledger and health endpoints.

**Q2. How does the user provide input to this tool?**
`POST /api/chat` with a message plus the browser session's identifier and token; a request model validates the shape.

**Q3. How does the tool communicate results back to the user?**
A `ChatResponse` carrying the reply text plus zero or more structured cards (anomaly, saving, proposal, mandate, receipt, denial), each rendered by the front end.

**Q4. How does the user provide feedback on the response?**
`GET /api/ledger` and `GET /api/ledger/verify` let the user audit every decision, including every refusal, and check the hash chain themselves.

**Q5. Give an example of the end-to-end user flow.**
Browser posts a session → posts a message → receives cards → the mandate card is signed by the same session → `GET /api/ledger/verify` confirms the chain covers the refusal produced when the same mandate was replayed.

---

## 4. Why these tracks

```
Alexa+ Developer Track: agentic voice workflows need a spending boundary more than any other surface — a voice agent that can move money without a human-approved cap is the exact failure mode SpendLatch removes. The MCP surface is already built to the 2025-11-25 protocol with Streamable HTTP; the human approval surface is live. The remaining work is wiring the two together inside the Alexa+ skill flow, which is what the track credits would fund.

Open Source mini challenge: the whole boundary — policy gate, ledger, adapters, verifier — is MIT-licensed and reproducible from https://github.com/owain323/spendlatch. Anyone can clone, run, break, and verify it.

**Open Source mini challenge — required fields**

- **Project repository URL:** https://github.com/owain323/spendlatch
- **Contribution URL:** https://github.com/owain323/spendlatch (new repository, created 2026-09-18 — inside the hackathon window)
- **GitHub username:** `owain323`
- **What we did:** Built and published a new open-source project: the authorization boundary between an AI agent and a consequential action. A deterministic policy gate parses every request into a spend intent and decides; a hash-chained ledger records every decision including every refusal; a mandate (HMAC-SHA256, single-use, scope-capped, 15-minute expiry) is the only thing that unlocks execution; an offline verifier re-checks an exported proof bundle against seven consistency checks. Thirteen tools are exposed over MCP 2025-11-25 / Streamable HTTP, with an MCP Apps approval card served as a `ui://` resource.
- **How it works:** `python run_checks.py` runs the whole thing — 197 pytest tests (195 in the pytest step plus 2 wire round-trip tests), a sealed three-tier benchmark 12/12, an MCP wire probe 8/8, and a mutation check that kills 12 of 12 guards, a real MCP client round trip against a real server subprocess, an integrity manifest, an evidence-freshness check, and a mutation check that disables each of ten guards one at a time and requires the suite to go red. A judge can reproduce every claim in the README in about five minutes with zero credentials.
- **Why it matters:** Agentic-payment protocols (AP2, ACP, x402) all converged on the same shape — an agent that touches money must carry proof of human authorization, bounded in scope and time, with an audit trail. That shape is infrastructure, not product surface, and it is currently rebuilt from scratch by everyone who needs it. Publishing it under MIT means the next team can adopt the boundary instead of reinventing it — and, more useful still, attack it: the refusal paths are the part worth stealing, and they only earn trust by being broken at publicly.
```

---

## 5. Fields to fill at submission time

- **Video link** — added when the final cut is ready.
- **Third Product Feedback set** — added when the Alexa+ integration runs live.
- **Built with** — Python 3.11+, FastAPI, MCP SDK (2025-11-25), Streamable HTTP, vanilla JS, pytest, GitHub Actions
