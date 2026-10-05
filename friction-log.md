# Friction Log — SpendLatch build

Format per entry follows the hackathon's requirement exactly: **task
attempted · steps taken · expected vs actual result · severity rating ·
workaround used · actionable suggestion.**

> **Who reads this.** The rules say Amazon's internal review team assesses
> friction log entries during Stage 1 downselection and passes a recommended
> bonus — up to 10% — to the Stage 2 panel. So Section A is written for the
> teams that own MCP, Alexa+ and the AWS SDKs: every entry names a thing
> Amazon ships and asks for something concrete. Section B is our own
> engineering log, included for completeness.

---

## A · Amazon-ecosystem entries

### A1 · MCP SDK: a floating minor floor pulled a breaking major release

- **Severity:** High
- **Task attempted:** Serve the tool layer as MCP over Streamable HTTP,
  negotiating protocol 2025-11-25 (the Alexa+ track minimum).
- **Steps taken:** Declared `mcp>=1.12` in `pyproject.toml`, installed in CI,
  booted `mcp.server.fastmcp`, then drove it with a real client over the wire.
- **Expected:** The floor admits only compatible releases; a minor-level bump
  keeps the server bootable.
- **Actual:** CI resolved `mcp` **2.2.0**, a breaking major.
  `mcp.server.fastmcp` no longer exists; the server exited at boot. The probe
  had been discarding child stderr, so the cause was invisible for one full
  CI cycle.
- **Workaround:** Pin `mcp>=1.12,<2`, and surface the child stderr tail in
  probe failures so the next occurrence is diagnosable on the first run.
- **Actionable suggestion:** MCP is now the declared integration standard for
  Alexa+, and a bare `>=` floor on it is a live reproducibility hazard for
  every team in this ecosystem. Publish a **supported-version window in the
  quickstart** (not just "latest"), and treat removal of a public module path
  as something the SDK should surface at import time with a migration
  pointer, rather than as a failure at boot.

### A2 · Streamable HTTP probe: the OS proxy captures loopback

- **Severity:** High
- **Task attempted:** Drive the local MCP server with a real client to prove
  the transport the track requires.
- **Steps taken:** Start the server on `127.0.0.1`, connect an official-SDK
  client, negotiate the protocol version.
- **Expected:** Loopback traffic never leaves the machine, so no proxy is
  involved and the handshake succeeds.
- **Actual:** The client inherited the OS system proxy and routed
  `127.0.0.1` through it, returning **502** — a failure that reads like a
  server bug and costs an hour before anyone suspects the proxy.
- **Workaround:** Force `NO_PROXY=127.0.0.1,localhost` in the probe before any
  HTTP client builds its trust environment.
- **Actionable suggestion:** SDK HTTP clients should **exempt loopback by
  default**, and the transport docs should say so in one line. Every team that
  writes a conformance probe against a local MCP server hits this once, and
  each one loses the same hour.

### A3 · Probing a long-lived MCP server: an undrained stderr pipe deadlocks it

- **Severity:** High
- **Task attempted:** Capture MCP server startup errors in an automated probe
  so CI failures carry a cause.
- **Steps taken:** Launch the server as a subprocess with
  `stderr=subprocess.PIPE`, then read the pipe after the probe finished.
- **Expected:** The pipe buffers startup errors; reading it at the end yields
  the traceback.
- **Actual:** A Streamable HTTP server logs continuously. The undrained pipe
  filled, the server blocked on write, and the probe **hung for five
  minutes** — a deadlock that looks like a broken server, not a broken probe.
- **Workaround:** Redirect child stderr to a temp file and read it only on
  failure; never hold an undrained pipe on a chatty long-lived server.
- **Actionable suggestion:** This is a general Python trap, but MCP servers
  are exactly the workload that triggers it (persistent, chatty, launched by
  probes). A **one-line warning in the MCP server-authoring docs** — "do not
  attach an undrained PIPE to a long-lived server" — would save it.

### A4 · MCP Apps (SEP-1865): "supported by the host" is not verifiable

- **Severity:** Medium
- **Task attempted:** Ship an interactive approval card as an MCP Apps
  resource and describe it honestly in the submission.
- **Steps taken:** Serve `ui://spendlatch/approval-card` with the
  `text/html;profile=mcp-app` mime profile, link it from `propose_action`
  through `_meta.ui.resourceUri`, and assert both over the wire in an
  automated probe.
- **Expected:** Serving the resource with the right profile proves the
  integration works.
- **Actual:** The **protocol half is verifiable** — resource served, mime
  profile correct, postMessage bridge present in the HTML, all asserted in
  `docs/evidence/mcp-roundtrip.txt` step 7. The **host half is not**: whether
  a given host actually renders the card, and how, cannot be checked from our
  side. We graded that claim unverified rather than imply it.
- **Workaround:** Claim the protocol half, refuse to claim the rendering
  half, and say which is which in the evidence register.
- **Actionable suggestion:** Publish a **per-host MCP Apps compatibility
  matrix** (Claude / ChatGPT / Goose / Alexa+) with a reference client. Until
  "works over MCP" means more than "worked on the one host we tried," every
  team either under-claims or over-claims, and both lose.

### A5 · Alexa+ track: no account-linking sandbox, so mandates cannot bind to a real identity

- **Severity:** High
- **Task attempted:** Bind an approved mandate to a real identity, so that
  "who approved" is non-repudiable and not merely "which surface approved."
- **Steps taken:** Designed the mandate as HMAC-SHA256 over
  `(mandate_id, proposal_id, action_id, scope, issued_at, expires_at,
  approver, nonce, proof_hash, approval)`, single-use, 15-minute TTL; then
  looked for a public Alexa+ account-linking sandbox or an AP2
  verifiable-credential test harness to mint the approver binding.
- **Expected:** A hackathon-scale way to bind a mandate to a real IdP exists.
- **Actual:** None is publicly available. The demo's session credential is
  self-issued and its holder is not cryptographically proven, so the mandate
  is honestly a **capability boundary** (which surface may approve), not an
  **identity boundary**. We documented this as L1 in `docs/THREAT-MODEL.md`,
  stated it in the README, and put it in the first paragraph the MCP server
  tells any connecting agent — rather than let a judge discover it.
- **Workaround:** Keep the authorization semantics real (single-use nonce,
  scope cap, expiry, hash-chained ledger) and label the identity gap
  explicitly. The mandate format is unchanged by a future IdP upgrade; only
  the proof of *who* approved becomes non-repudiable.
- **Actionable suggestion:** Ship a **public Alexa+ account-linking sandbox**
  (or an AP2 verifiable-credential test harness) that hackathon and prototype
  projects can call without a production skill submission. Every team
  building an agent that touches money will otherwise invent the same honest
  local stand-in, and every one of them will ship the same caveat.

---

## B · Engineering log (our own stack, included for completeness)

| Date | Task | Expected vs actual | Severity | Workaround | Suggestion |
|---|---|---|---|---|---|
| 2026-09-18 | Bootstrap MCP server over Streamable HTTP | Expected: client negotiates 2025-11-25 on first connect. Actual: the probe inherited the OS system proxy, which routed 127.0.0.1 through it and returned 502 | High | Force `NO_PROXY=127.0.0.1,localhost` before any HTTP client builds its trust_env | SDK HTTP clients should exempt loopback by default (see A2) |
| 2026-09-18 | Capture MCP server stderr in a probe | Expected: `subprocess.PIPE` captures startup errors. Actual: an SSE server logs continuously; the undrained pipe filled and deadlocked the server mid-probe (hung 5 minutes) | High | Redirect child stderr to a temp file, read only on failure | Python docs should warn that PIPE + long-lived servers = deadlock (see A3) |
| 2026-09-18 | Repo-wide SHA256 manifest on Windows | Expected: manifest hashes match a fresh clone. Actual: 8 files had CRLF on disk while git stores LF — the CI integrity gate went red on bytes no clone could reproduce | High | Normalize everything to LF; add a CRLF hard-gate that skips binaries (PNGs legitimately contain 0x0D0A) | Byte-stable reproducibility needs `.gitattributes` AND a generator that refuses CRLF, not editor discipline |
| 2026-09-18 | CI installed mcp 2.2.0 (pinned `>=1.12`) | Expected: latest SDK is compatible. Actual: 2.x is a breaking major — the server exited at boot, and discarded stderr made it undiagnosable for one cycle | High | Pin `mcp>=1.12,<2`; surface child stderr tail | Major-version floats on a security-sensitive dependency are a hazard (see A1) |
| 2026-09-18 | Bind approval to an authenticated session | Expected: the token→workspace registry could live inside the token's own workspace file. Actual: `approve` looked up the registry in the wrong file twice (anonymous workspace, then wrong lookup order) — two rounds of chicken-and-egg | Medium | Move the registry to a neutral file (`data/auth-sessions.json`) readable before any workspace is known | Identity/lookup tables must exist outside the resource they grant access to; document the resolution order |
| 2026-09-18 | Hidden holdout generator for the benchmark | Expected: rescaling amounts preserves judgment structure. Actual: per-month random jitter destroyed the cost-per-task drift shape one case is built on (23/24 on first run) | Medium | One scale factor per provider so trend SHAPE survives transformation | Derived-benchmark generators must transform levels, not trends — trend shape IS the label |

---

## Status note on the AWS Builder path (Bedrock + Strands)

An optional LLM planner (Strands SDK + Bedrock) that converts free-form
language into a structured `SpendIntent` is **implemented and OFF by default**
(`SPENDLATCH_LLM=bedrock`). Its behaviour is covered by 22 tests against a
mocked Bedrock layer (`tests/test_planner.py`), and the boundary is asserted
in code: no planner path ever mints a proposal or a mandate.

**Live Bedrock calls have not been run as of this file's last edit** — the
account and model access were not yet in place. An earlier draft of this log
answered "would we use it again: yes" on the strength of the mocked layer
alone. That overstated what we had actually done, and it is corrected here:
the honest answer is *not yet run*. This section will be rewritten from the
real smoke output (`tools/aws_smoke.py`, `docs/evidence/aws-live.txt`) once
the live call lands, and a friction entry will be added only for what
actually happened.

---

*Every entry above describes something that happened. Nothing was written
forward from what we expect to encounter.*
