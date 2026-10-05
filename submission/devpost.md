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

I kept asking AI assistants to do things for me — move money, buy things, run cloud jobs. And every time, the same uncomfortable question came back: what exactly is this agent allowed to spend? Dashboards can show me what already happened. That is not the same as deciding what is allowed to happen. So I built the thing that was missing: a small, verifiable boundary that sits between an AI agent and any action that costs money.

### What it does

SpendLatch is the authorization boundary between an AI agent and a consequential action. The agent watches spending data, proves a saving opportunity with evidence, and proposes an exact action — then stops. Nothing runs until a human approves a signed mandate: this exact action, on this provider, capped at this dollar amount, once, for fifteen minutes. If the request no longer matches the signed proof, it is rejected. Replaying the mandate fails — the nonce is single-use. Asking the agent to approve itself through MCP is refused and logged. Every approval exports a proof bundle that can be verified offline, without trusting the running system.

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

---

## 4. Why these tracks

```
Alexa+ Developer Track: agentic voice workflows need a spending boundary more than any other surface — a voice agent that can move money without a human-signed cap is the exact failure mode SpendLatch removes. The MCP surface is already built to the 2025-11-25 protocol with Streamable HTTP; the human approval surface is live. The remaining work is wiring the two together inside the Alexa+ skill flow, which is what the track credits would fund.

Open Source mini challenge: the whole boundary — policy gate, ledger, adapters, verifier — is MIT-licensed and reproducible from https://github.com/owain323/spendlatch. Anyone can clone, run, break, and verify it.
```

---

## 5. Fields to fill at submission time

- **Video link** — added when the final cut is ready.
- **Third Product Feedback set** — added when the Alexa+ integration runs live.
- **Built with** — Python 3.11+, FastAPI, MCP SDK (2025-11-25), Streamable HTTP, vanilla JS, pytest, GitHub Actions
