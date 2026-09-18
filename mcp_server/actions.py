"""Mandate-gated action loop — the step from "watching bills" to "acting".

This is SpendPilot's answer to the 2026 agentic-payments discipline (AP2 /
ACP / x402 all converge on the same shape): an agent that touches money must
carry PROOF OF HUMAN AUTHORIZATION, bounded in scope and time, and leave an
audit trail. We implement that shape honestly:

  propose  -> the agent attaches its proof to a concrete, bounded action
  approve  -> the human authorizes; the server issues a signed mandate
              (HMAC-SHA256 over a canonical payload — a local stand-in for
              AP2's verifiable credentials; labeled as such everywhere)
  execute  -> the provider adapter runs ONLY if the mandate verifies:
              signature valid, not expired, not already consumed, and the
              real-world scope has not drifted past what was approved

Every step — including every refusal — is recorded in the decision ledger.
An agent that can act must be MORE auditable than one that only advises.

Honesty boundary: the signature proves integrity and non-forgery inside this
local demo. Production would bind the mandate to a device key or an AP2
verifiable credential; the control flow is identical.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import adapters, ledger, store, tools

MANDATE_TTL_SECONDS = 900  # 15 minutes: approval is a decision, not a blank check

# Exactly these fields are signed. Status and execution metadata live OUTSIDE
# the signed payload, so bookkeeping mutations can never invalidate (or fake)
# a signature.
SIGNED_FIELDS = ("mandate_id", "proposal_id", "action_id", "scope",
                 "issued_at", "expires_at", "approver", "nonce")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _secret(state: dict) -> str:
    """Per-installation HMAC secret, generated once and persisted in state."""
    if not state.get("mandate_secret"):
        state["mandate_secret"] = secrets.token_hex(32)
    return state["mandate_secret"]


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(payload: dict, secret: str) -> str:
    return hmac.new(secret.encode(), _canonical(payload), hashlib.sha256).hexdigest()


def _refuse(subject: str, reason: str, state_path: Path | None, **extra) -> dict:
    """A refusal is a first-class decision: logged, structured, returned."""
    entry = ledger.record("refuse", subject, reason, path=state_path)
    return {"refused": True, "error": reason, "ledger_seq": entry["seq"], **extra}


# ------------------------------------------------------------------ propose

def propose_action(action_id: str, state_path: Path | None = None) -> dict:
    """Attach the proof to a concrete, bounded action and put it on the table.

    Idempotent per action: re-proposing an already-open proposal returns the
    existing one instead of duplicating.
    """
    proof = tools.simulate_saving(action_id)
    if "error" in proof:
        return proof
    state = store.load_state(state_path)
    for proposal in state["proposals"].values():
        if proposal["action_id"] == action_id and proposal["status"] == "proposed":
            return {**proposal, "proof": proof, "note": "already proposed — awaiting approval"}

    proposal_id = f"p-{secrets.token_hex(4)}"
    operation = adapters.operation_for(action_id)
    if operation is None:
        return {"error": f"action '{action_id}' has no provider adapter; refusing to propose"}
    proposal = {
        "proposal_id": proposal_id,
        "action_id": action_id,
        "title": proof["title"],
        "provider": proof["provider"],
        "operation": operation,
        "status": "proposed",
        "created_at": _iso(_now()),
        "proof_snapshot": {
            "monthly_before": proof["monthly_before"],
            "monthly_after": proof["monthly_after"],
            "expected_saving_pct": proof["expected_saving_pct"],
        },
    }
    state["proposals"][proposal_id] = proposal
    store.save_state(state, state_path)
    ledger.record(
        "propose", proof["provider"],
        f"Proposed '{proof['title']}' ({proof['expected_saving_pct']}% scenario saving, "
        f"proof attached) — awaiting human approval.",
        evidence=[action_id, proposal_id], path=state_path,
    )
    return {**proposal, "proof": proof}


# ------------------------------------------------------------------ approve

def approve_action(proposal_id: str, approver: str = "human",
                   ttl_seconds: int = MANDATE_TTL_SECONDS,
                   state_path: Path | None = None) -> dict:
    """The human authorizes. The server issues a signed, scope-capped mandate.

    The mandate's scope is captured from a FRESH proof at approval time, so
    the human approves what is true now — not what was true when proposed.
    """
    state = store.load_state(state_path)
    proposal = state["proposals"].get(proposal_id)
    if proposal is None:
        return _refuse(proposal_id, f"unknown proposal '{proposal_id}'", state_path)
    if proposal["status"] != "proposed":
        return _refuse(proposal["title"],
                       f"proposal is '{proposal['status']}', not 'proposed' — cannot approve again",
                       state_path)

    proof = tools.simulate_saving(proposal["action_id"])
    if "error" in proof:
        return _refuse(proposal["title"], "proof can no longer be produced; approval refused",
                       state_path)

    issued = _now()
    payload = {
        "mandate_id": f"m-{secrets.token_hex(4)}",
        "proposal_id": proposal_id,
        "action_id": proposal["action_id"],
        "scope": {
            "provider": proposal["provider"],
            "operation": proposal["operation"],
            "max_monthly_before": proof["monthly_before"],  # hard cap: refuse if reality drifted up
            "expected_saving_pct": proof["expected_saving_pct"],
        },
        "issued_at": _iso(issued),
        "expires_at": _iso(issued + timedelta(seconds=ttl_seconds)),
        "approver": approver,
        "nonce": secrets.token_hex(8),
    }
    secret = _secret(state)
    mandate = {**payload, "signature": _sign(payload, secret), "status": "issued"}
    state["mandates"][payload["mandate_id"]] = mandate
    proposal["status"] = "approved"
    store.save_state(state, state_path)
    ledger.record(
        "approve", proposal["provider"],
        f"{approver} approved '{proposal['title']}'; mandate {payload['mandate_id']} "
        f"scoped to {proposal['operation']} (cap ${proof['monthly_before']:.2f}/mo), "
        f"expires in {ttl_seconds}s.",
        evidence=[payload["mandate_id"], proposal_id], path=state_path,
    )
    return {k: v for k, v in mandate.items()}  # full record incl. signature (local demo)


# ------------------------------------------------------------------ execute

def execute_action(mandate_id: str, state_path: Path | None = None) -> dict:
    """Execute through the provider adapter — only through a valid mandate.

    Verification order is deliberate and each failure is logged separately:
    unknown -> forged -> consumed -> expired -> scope drifted -> execute.
    """
    state = store.load_state(state_path)
    mandate = state["mandates"].get(mandate_id)
    if mandate is None:
        return _refuse(mandate_id, f"unknown mandate '{mandate_id}' — nothing executes on trust",
                       state_path)

    secret = _secret(state)
    payload = {k: mandate[k] for k in SIGNED_FIELDS}
    if not hmac.compare_digest(_sign(payload, secret), mandate["signature"]):
        return _refuse(mandate["scope"]["provider"],
                       f"mandate {mandate_id} failed signature verification — "
                       "payload was tampered with; execution refused and logged",
                       state_path, mandate_id=mandate_id)

    if mandate["status"] == "executed":
        return _refuse(mandate["scope"]["provider"],
                       f"mandate {mandate_id} was already consumed — mandates are single-use",
                       state_path, mandate_id=mandate_id)
    if mandate["status"] != "issued":
        return _refuse(mandate["scope"]["provider"],
                       f"mandate {mandate_id} is '{mandate['status']}' — not executable",
                       state_path, mandate_id=mandate_id)

    if _now() > datetime.fromisoformat(mandate["expires_at"]):
        mandate["status"] = "expired"
        store.save_state(state, state_path)
        return _refuse(mandate["scope"]["provider"],
                       f"mandate {mandate_id} expired at {mandate['expires_at']} — "
                       "approval is a decision, not a blank check",
                       state_path, mandate_id=mandate_id)

    proof = tools.simulate_saving(mandate["action_id"])
    if "error" in proof:
        return _refuse(mandate["scope"]["provider"],
                       "the action's proof disappeared since approval; execution refused",
                       state_path, mandate_id=mandate_id)
    cap = mandate["scope"]["max_monthly_before"]
    if proof["monthly_before"] > cap + 1e-9:
        return _refuse(
            mandate["scope"]["provider"],
            f"scope drifted: bill is now ${proof['monthly_before']:.2f}/mo, above the approved "
            f"cap of ${cap:.2f}/mo — re-approval required",
            state_path, mandate_id=mandate_id)

    receipt = adapters.execute(mandate["action_id"])
    if "error" in receipt:
        return _refuse(mandate["scope"]["provider"], receipt["error"], state_path,
                       mandate_id=mandate_id)

    mandate["status"] = "executed"
    mandate["executed_at"] = receipt["executed_at"]
    receipt["mandate_id"] = mandate_id
    receipt["approver"] = mandate["approver"]
    state["receipts"].append(receipt)
    store.save_state(state, state_path)
    ledger.record(
        "execute", mandate["scope"]["provider"],
        f"Executed '{receipt['operation']}' via the {receipt['adapter']} adapter (simulated); "
        f"mandate {mandate_id} consumed. Monthly scenario saving ${receipt['monthly_saving']:.2f}.",
        evidence=[mandate_id, mandate["action_id"]], path=state_path,
    )
    return receipt


# ------------------------------------------------------------------- status

def mandate_status(state_path: Path | None = None) -> dict:
    """All proposals, mandates, and receipts — the action accountability view."""
    state = store.load_state(state_path)
    now = _now()
    mandates = []
    for m in state["mandates"].values():
        row = {k: v for k, v in m.items() if k != "signature"}
        row["signature_short"] = m["signature"][:12] + "..."
        if m["status"] == "issued" and now > datetime.fromisoformat(m["expires_at"]):
            row["status"] = "expired (pending sweep)"
        mandates.append(row)
    mandates.sort(key=lambda m: m["issued_at"], reverse=True)
    proposals = sorted(state["proposals"].values(), key=lambda p: p["created_at"], reverse=True)
    return {
        "proposals": proposals,
        "mandates": mandates,
        "receipts": list(reversed(state["receipts"])),
        "counts": {
            "proposals_open": sum(1 for p in proposals if p["status"] == "proposed"),
            "mandates_issued": sum(1 for m in mandates if m["status"] == "issued"),
            "executed": len(state["receipts"]),
        },
    }
