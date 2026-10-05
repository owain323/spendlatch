# Threat Model — SpendLatch

Who attacks an agent that can spend? What does SpendLatch actually defend,
and with which mechanism? This document states both, with pointers to the
code and the tests that prove each defense.

**Scope**: the authorization boundary of the demo's action loop. Provider
adapters are simulated, so this model governs the mandate protocol, not
real money movement.

## Attackers

- **A misaligned or compromised agent** that proposes spend beyond its
  delegated authority (bug, drift, or prompt injection upstream)
- **An attacker with MCP access** to the public surface (the demo exposes
  MCP over Streamable HTTP on the internet)
- **A replay/race attacker** exploiting retries, timeouts, and duplicate
  tool calls — the natural failure mode of agent systems
- **A tamperer** rewriting requests, mandates, evidence, or history

## Threats and defenses

| # | Threat | Primary defense | Proof it works |
|---|---|---|---|
| T1 | Malicious/misaligned agent proposes beyond authority | **Deterministic policy decides — the LLM never owns authorization.** The agent can propose, never approve. | `actions.approve_action` refuses without a web session token (see L1: this is a capability boundary, not an identity boundary) |
| T2 | Prompt injection rewrites the intended action | Canonical spend intent: the proof the human approves is hashed into the mandate; evidence drift rejects execution | `proof_hash` in `SIGNED_FIELDS`; `test_proof_drift_since_approval_refused` |
| T3 | Tampered spend request | Canonical digest of the material facts signed at approval time; any change breaks the hash | same mechanism as T2 |
| T4 | Forged/modified mandate | HMAC-SHA256 over exactly the signed fields; bookkeeping fields live outside the signature | `test_forged_mandate_refused` |
| T5 | Replay of a valid mandate | A per-mandate **consumption claim** written before the adapter runs (`state["consumed"]`, outside the bounded ledger) + nonce + idempotency key on the receipt. The process lock is in-process only; the claim is what holds across processes and restarts | `test_single_use_holds_under_concurrency`, `test_seam.py`, `test_attack_surface.py::test_rollback_of_status_does_not_allow_a_second_execution` |
| T6 | Stale authorization after policy/time change | TTL is server policy (900s, not caller-supplied); expired mandates refuse and log | `test_expired_mandate_refused` |
| T7 | Untrusted surface claims "a human approved" | Surface isolation: only the web session surface can approve; the MCP surface refuses and logs. This stops an agent that speaks MCP — it does not stop a caller that speaks HTTP (see L1) | `test_mcp_surface_cannot_approve` |
| T8 | Duplicate execution after timeout/retry | Transaction identity: every receipt carries request_id / execution_id / idempotency_key derived from mandate+nonce | `test_receipt_carries_transaction_identity` |
| T9 | Tampered decision history | Hash-chained ledger: every entry commits to content and predecessor | `TestHashChain` |
| T11 | Human says "no" and the agent signs anyway | Consent is read off the sentence: a refusal-shaped or interrogative request never reaches the approve path, and the refusal itself is a ledger entry | `test_attack_surface.py::test_refusal_shaped_utterance_never_signs` |
| T12 | A valid mandate executes a different operation | The signed scope is compared against the adapter that would actually run (registry entry + operation table) before dispatch; a swapped adapter refuses and names the difference | `test_attack_surface.py::test_swapped_adapter_cannot_run_under_a_valid_signature` |
| T13 | New spend requested with no mandate at all | Default-deny gate reachable without the LLM: a spend verb plus an amount is denied and logged, so the refusal is recorded even when the planner is off | `test_attack_surface.py::test_new_spend_is_denied_and_logged` |
| T10 | Silent state corruption | Fail-closed persistence: corrupt file preserved, never silently reset | `test_corrupt_state_fails_closed_and_preserves_file` |

## integrity vs authenticity — stated precisely

The hash chain proves **integrity** (nothing in the retained window was
altered). It does NOT by itself prove **authenticity** (who authorized what).
Authenticity lives in the proof bundle: intent + policy version + mandate +
signature + execution receipt + ledger link — verifiable offline:

```
python tools/verify_proof.py proof.json --state data/workspaces/<ws>.json
```

## Out of scope (explicit)

- Real money movement, payment rails, card networks, merchant integrations
- Credential handling (the demo holds no provider credentials by design)
- Byzantine/multiple-signer scenarios (single trust domain; asymmetric
  signatures, key rotation, and third-party verification are the v2 lane)

## Known limitations (stated, not hidden)

### L1 — the approval boundary is a capability boundary, not an identity boundary

`POST /api/session` issues a session token to any caller that reaches the
web surface, with no credential check. The full approve path is therefore
reachable by anyone who can reach the demo:

```
POST /api/session                      -> session_token
POST /api/chat {"message":"approve",  session_token}  -> signed mandate
```

**What this does protect:** an agent driving the MCP surface cannot approve
itself — that path is refused and logged (T7), and a mandate signed on one
surface is not transferable to another.

**What this does not protect:** a caller who speaks HTTP to the web surface
can open its own session and approve. So the property the system actually
provides today is *"approval requires a separate surface and produces a
bounded, single-use, verifiable artifact"* — not *"approval requires a
verified human"*.

**Why it is written down rather than fixed:** the demo holds no identity
provider and no credentials by design, and every identity mechanism that
would fix it (Alexa+ account linking, AP2 verifiable credentials, OAuth 2.1
+ PKCE) is out of scope for a self-contained demo. The mandate format, the
nonce, the cap and the ledger do not change when identity arrives — the
session token simply gains a verified principal behind it, and the signature
becomes non-repudiable.

**Verification once identity lands:** a session token must not be mintable
without presenting a credential; the approving principal must appear in the
mandate and in the receipt.
