"""Pre-generated attack fixtures for the demo.

One rule governs this module:

    Demo attack paths may be synthetic. Authorization decisions may not be.

Every fixture is a REAL mandate, minted through the real propose and approve
path. Where a fixture must look different from an honest mandate (an expired
one, an over-capped one), the mutation is performed by the holder of the
signing key - the server - and the mandate is re-signed, so the refusal can
only come from the guard under attack. The forged fixture is the opposite:
it is mutated by a party that does NOT hold the key, so it stays unsigned,
and the signature check is what stops it.

Execution always goes through actions.execute_action, the same verifier
production uses. There is no demo branch, no pretend flag, and no refusal
that was not produced by a guard.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import actions, store


def _mint(action_id: str = "rightsize-ec2") -> dict:
    proposal = actions.propose_action(action_id)
    token = actions.open_session()["session_token"]
    mandate = actions.approve_action(proposal["proposal_id"], session_token=token)
    if mandate.get("refused"):
        raise RuntimeError(f"fixture minting failed: {mandate['error']}")
    return mandate


def _re_sign(mandate_id: str) -> None:
    """Re-sign a mutated mandate with the server's own key.

    Legitimate here and only here: the server is the key holder, so this
    models 'the mandate really says this' - the broken invariant is whatever
    the caller changed, never the signature.
    """
    state = store.load_state(None)
    record = state["mandates"][mandate_id]
    secret = state.get("mandate_secret") or "x"
    payload = {k: record[k] for k in actions.SIGNED_FIELDS}
    record["signature"] = actions._sign(payload, secret)
    store.save_state(state, None)


def replay_attack() -> dict:
    """Execute a mandate twice: the second call must be refused."""
    mandate = _mint()
    first = actions.execute_action(mandate["mandate_id"])
    second = actions.execute_action(mandate["mandate_id"])
    return {"attack": "replay", "mandate_id": mandate["mandate_id"],
            "first": first, "verdict": second}


def self_approve_attack() -> dict:
    """Approve a real proposal from the MCP surface: no session, no mandate."""
    proposal = actions.propose_action("cancel-figma")
    verdict = actions.approve_action(proposal["proposal_id"], session_token=None)
    return {"attack": "self-approve", "mandate_id": None, "verdict": verdict}


def over_cap_attack() -> dict:
    """The signed cap is real but below the current bill: cap must refuse it.

    The bill is untouched, the proof hash is untouched, the signature is
    valid - the only broken invariant is the cap, so this exercises the cap
    guard and nothing else.
    """
    mandate = _mint()
    state = store.load_state(None)
    state["mandates"][mandate["mandate_id"]]["scope"]["max_monthly_before"] = 1.0
    store.save_state(state, None)
    _re_sign(mandate["mandate_id"])
    verdict = actions.execute_action(mandate["mandate_id"])
    return {"attack": "over-cap", "mandate_id": mandate["mandate_id"],
            "verdict": verdict}


def expired_attack() -> dict:
    """A genuinely expired mandate: expires_at in the past, signature valid."""
    mandate = _mint()
    state = store.load_state(None)
    past = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(timespec="seconds")
    state["mandates"][mandate["mandate_id"]]["expires_at"] = past
    store.save_state(state, None)
    _re_sign(mandate["mandate_id"])
    verdict = actions.execute_action(mandate["mandate_id"])
    return {"attack": "expired", "mandate_id": mandate["mandate_id"],
            "verdict": verdict}


def forged_scope_attack() -> dict:
    """Swap the signed operation without the key: the signature must refuse it.

    This is the one fixture that is NOT re-signed: an attacker cannot sign,
    so an edited mandate is an unsigned mandate, and 'a raised cap becomes an
    unsigned mandate, not a bigger one' applies to the operation too.
    """
    mandate = _mint()
    state = store.load_state(None)
    state["mandates"][mandate["mandate_id"]]["scope"]["operation"] = "billing:DeleteAccount"
    store.save_state(state, None)
    verdict = actions.execute_action(mandate["mandate_id"])
    return {"attack": "forged-scope", "mandate_id": mandate["mandate_id"],
            "verdict": verdict}


ATTACKS = {
    "replay": replay_attack,
    "self-approve": self_approve_attack,
    "over-cap": over_cap_attack,
    "expired": expired_attack,
    "forged-scope": forged_scope_attack,
}


def run_attack(kind: str) -> dict:
    if kind not in ATTACKS:
        return {"error": f"unknown attack '{kind}'", "known": sorted(ATTACKS)}
    result = ATTACKS[kind]()
    verdict = result["verdict"]
    result["refused"] = bool(verdict.get("refused"))
    result["reason"] = verdict.get("error")
    result["ledger_seq"] = verdict.get("ledger_seq")
    return result
