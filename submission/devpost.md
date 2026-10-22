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

SpendLatch is the authorization boundary between an AI agent and a consequential action. The agent watches spending data, proves a saving opportunity with evidence, and proposes an exact action — then stops. Nothing runs until a human approves a signed mandate: this exact action, on this provider, capped at this dollar amount, once, for fifteen minutes. If the request no longer matches the signed proof, it is rejected. Replaying the mandate fails — the nonce is single-use. Asking the agent to approve itself through MCP is refused and logged. A proposal made on the tool surface crosses to the human on a one-time, fifteen-minute handoff code, so the agent can propose and the person can approve without either side sharing a state file. Every approval exports a proof bundle that can be verified offline, without trusting the running system.

### The boundary, stated as seven invariants

Seven invariants, each one checkable against the repository:

1. **Approval and execution are different surfaces.** The tool surface cannot *submit* an approval: `approve_action` carries no session credential, so the call is refused and logged. Signing requires a web session token issued to the web surface. This is a capability boundary, not an identity boundary — the one-time handoff code is returned in the `propose_action` result, so the calling host is trusted to hand it to a person, and the server cannot verify who redeems it.
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
- An MCP server (2025-11-25, Streamable HTTP) exposes the same tools to agent surfaces, but signing requires a web session token — an `approve_action` call carrying none is refused and logged.
- The web demo (FastAPI backend, zero-build vanilla JS frontend) runs live at https://spendlatch.owain32380.cn — you can run the full loop yourself: ask, prove, approve, execute, replay.

### Challenges we ran into

The hardest part was not the agent — it was making the boundary boring and precise. Defining what a mandate can and cannot express took several iterations. Making replay protection work under a single-use nonce plus a 15-minute expiry, and proving it with a real rejected replay, took care. The AWS sandbox adapter had to be labeled honestly: the receipt says "simulated adapter" today, and the real API path is designed but not yet switched on.

### Accomplishments that we're proud of

- The agent proposes but cannot authorize itself — demonstrated live, including a logged refusal.
- Every ID is chained: execution → mandate → proposal → the evidence the human actually read.
- The demo is reproducible from open-source code, and the proof bundle verifies offline.

### What we learned

Authorization is a product surface, not a middleware detail. The moment you make it visible — mandate cards, receipts, a decision ledger — people start asking for it everywhere.

### What we got wrong

The strongest claims in this project came from people trying to break it, so we ran that on ourselves before submitting. Three findings changed the code:

- **The evidence gate could not fail.** CI checks out a single commit, so `git log -1 -- <path>` always returns the tip, and "evidence must not predate the code" was trivially true — green for months, proving nothing. With `fetch-depth: 0` the same commit went red: five artifacts were older than the code they describe. They are refreshed now, and the gate demonstrably fails when it should.
- **A gate graded its own homework.** The test-count step rewrites an evidence file and ran before the integrity check, so it compared the manifest against a file it had just rewritten. It runs last now.
- **One invariant was true in the code and false in the system.** `approve_action` refuses without a web session — but the one-time handoff code travels back through `propose_action` to whoever called it, and a session token costs nothing to mint. An agent that speaks both MCP and HTTP can therefore walk the whole loop without a human. We did not paper over it: `docs/THREAT-MODEL.md` (L1) states it plainly, and the invariant is worded as a capability boundary rather than an identity boundary. Closing it needs an identity provider, which this build does not have.

We would rather hand in a submission that names its own worst case than one that has to be caught.

### What's next

Bring SpendLatch to Alexa+: a human approves on the phone, the voice agent can then execute exactly what was approved — once, within the cap. Real AWS API calls through the adapter. Conformance tests for anyone building their own boundary.

---

## 3. Product Feedback Set

The track asks five questions per tool. Four surfaces were used in this build,
and each is answered below in its own words rather than with one merged answer.



### The web chat (the simulated Alexa+ experience)

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

### The MCP server

**Q1. How does the user invoke this tool?**
The MCP server (protocol 2025-11-25, Streamable HTTP) is exposed at https://spendlatch.owain32380.cn/mcp. An agent surface (Claude Desktop, any MCP client) connects and lists 13 tools: spending_overview, detect_anomalies, simulate_saving, set_budget, budget_status, list_subscriptions, unit_economics, proactive_briefing, decision_ledger, propose_action, approve_action, execute_action, mandate_status.
Run `python tools/mcp_roundtrip.py` to reproduce this list over the wire, against a real server subprocess.

**Q2. How does the user provide input to this tool?**
The agent calls the tools with structured arguments on the user's behalf. Approval is the exception: `approve_action` is registered on the tool surface, but it refuses unless a web session token is presented, so this surface can execute what a person signed and cannot sign anything itself.

**Q3. How does the tool communicate results back to the user?**
The same structured cards and receipts as the web surface, plus the hash-chained ledger entry. A refused execution returns the refusal reason and the ledger sequence number.

**Q4. How does the user provide feedback on the response?**
Every refusal is a first-class ledger entry ("refuse"), so "why did you not act" always has an answer the user can verify.

**Q5. Give an example of the end-to-end user flow.**
The agent asks the server for anomalies, gets evidence, tries to execute without a mandate, and is refused with "I hold no valid mandate, so I will not act" — the refusal is recorded in the ledger as a first-class entry. The human approves on the web surface; only then does the same MCP execution path succeed, once.

### The MCP Python SDK (`mcp>=1.12,<2`)

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

### FastAPI

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

### Why the Alexa+ track

An agentic voice surface is the case where a spending boundary matters most: a voice agent that can move money has no screen on which a person can read a diff, and "it sounded like it agreed" is not consent. SpendLatch puts the approval where a screen still exists — a signed mandate the person confirms — and lets the voice agent execute that exact mandate once.

Where the integration actually stands: the MCP server and the approval surface are built and live at protocol 2025-11-25 over Streamable HTTP. The voice conversation in the demo is a faithful simulation, because the Alexa+ skill runtime is not exposed to hackathon entrants — there is no sandbox in which a submission could exercise it. So the tool layer, the mandate gate, the ledger and the refusals are real code doing real work; the speech layer in front of them is a stand-in, and it is labelled as one on the page and in the UI. Wiring it to the real skill flow is integration, not invention: both sides already speak MCP.

### What this would use on AWS

The provider adapter is a simulated AWS adapter today — it names the API it would call, labels the receipt `simulated adapter`, and refuses to pretend otherwise. A real deployment swaps one adapter module; the mandate gate, the ledger and the verifier are unchanged, because none of them know what a provider is.

### Why the Open Source mini challenge

The whole boundary — policy gate, hash-chained ledger, provider adapters, offline verifier — is MIT-licensed and reproducible from https://github.com/owain323/spendlatch. It is a new repository created on 2026-09-18, inside the hackathon window, and the contribution is the project itself.

- **Repository and contribution URL:** https://github.com/owain323/spendlatch
- **GitHub username:** `owain323`
- **What was published:** a deterministic policy gate that turns a request into a spend intent and decides; a SHA-256 hash-chained ledger that records every decision including every refusal; a mandate (HMAC-SHA256, single-use, scope-capped, 15-minute expiry) as the only thing that unlocks execution; an offline verifier that re-checks an exported proof bundle; thirteen tools over MCP 2025-11-25 / Streamable HTTP with the approval card served as a `ui://` resource.
- **Not only fixtures:** `tools/analyze_usage.py` reads a real usage export (10,901 requests across 137 days) and applies the same credits-per-call canary the demo uses. Seven of the 23 anonymized model ids carry enough history to judge, and all seven drift. The export stays local; the tool and its output are what we ship.
- **How to check it:** `python run_checks.py` is the whole gate and takes about two minutes: byte-compile, 239 pytest tests, the sealed benchmark in all three tiers (12 public / 24 derived / 14 independent), an MCP wire probe 8/8, a real MCP client round trip against a real server subprocess, an integrity manifest over 122 files, an evidence-freshness check, the recorded test count, the submission copy, and a mutation check that deletes each of twelve guards one at a time and requires the suite to go red (single-process operators: a coverage claim, not a cross-process one). Two checks run as separate commands because they need the outside world. The first is `python tools/host_conformance.py --url https://spendlatch.owain32380.cn/mcp`: a client that is not ours, from the public internet, prints `HOST_CONFORMANCE_OK` when protocol 2025-11-25 is negotiated and the approval-card resource is served with the mcp-app profile. The second is `python benchmarks/run.py --independent`, for a single detection tier on its own. Zero credentials.

### The friction log

The build log is published in the required format — task attempted, steps taken, expected versus actual, severity, workaround, suggestion — at https://github.com/owain323/spendlatch/blob/main/friction-log.md. Two entries that cost the most time:

- **MCP Python SDK 2.0.0 removed `mcp.server.fastmcp`.** An unpinned install boots and dies, so the version has to be pinned below 2. Suggestion: keep the import path stable across a major, or ship a deprecation shim.
- **Tool schemas are generated from docstrings, so the safety annotations a host relies on drift silently.** We wrote a conformance probe to catch it, and it immediately found four gaps. Suggestion: make `readOnly`/`destructive`/`idempotent` first-class fields rather than prose.

## 5. Fields to fill at submission time

- **Video link** — https://youtu.be/QvWt17Li7U8 (public, 2:37, 1280x720)
- **Product feedback** — four tool entries are written below (web chat, MCP server, MCP Python SDK, FastAPI). A fifth set will be added if the Alexa+ skill runtime ever becomes available to entrants; it is not, so nothing here claims it ran.
- **Built with** — Python 3.11+, FastAPI, MCP SDK (2025-11-25), Streamable HTTP, vanilla JS, pytest, GitHub Actions
