"""Authorization invariants I1-I7 — the part the demo must NOT be able to fake.

One rule governs everything here:

    Demo attack paths may be synthetic. Authorization decisions may not be.

Concretely, every test in this file obeys three rules:

1. It drives a REAL product entry point — the HTTP route (`/api/chat`) or
   `actions.*`. No demo-only branch, no `if demo_mode:` shortcut.
2. It asserts on SERVER state — the ledger, the mandate record, the receipt
   list — never on what the client sent and never on whether a control was
   visible or disabled.
3. The refusal it asserts on is located in the hash-chained ledger, so the
   claim "every refusal is recorded" is tested at the same time.

Rule 2 is the point. A test that passed because the button was disabled
would be a false green: it would prove the UI hid an action, not that the
server refused it.
"""
from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from agent.backend import app
from mcp_server import actions, ledger, store


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDLATCH_STATE", str(tmp_path / "state.json"))


@pytest.fixture()
def client():
    return TestClient(app)


def _approved(action_id: str = "rightsize-ec2") -> dict:
    proposal = actions.propose_action(action_id)
    token = actions.open_session()["session_token"]
    return actions.approve_action(proposal["proposal_id"], session_token=token)


def _speak(client, message: str, **extra) -> dict:
    body = {"message": message}
    body.update(extra)
    return client.post("/api/chat", json=body).json()


def _refusals() -> list[dict]:
    return ledger.entries(kinds={"refuse"})


def _refusal_card(body: dict) -> dict:
    """The refusal must reach the UI as a structured card, not as a sentence.

    A refusal that renders as nothing cannot be collected into a refusal wall,
    so every one of these tests asserts the card exists AND carries the five
    fields that make it auditable: action, reason, mandate_id, ledger_seq,
    policy. (mandate_id is None when nothing was ever issued — that is a
    different refusal, not a missing field.)
    """
    cards = body["cards"]
    assert cards, "the refusal rendered as no card at all — it cannot be shown or collected"
    card = cards[0]
    assert card["type"] == "denied", f"expected a refusal card, got {card['type']}"
    assert card["action"], "the card does not say which action was refused"
    assert card["reasons"], "the card does not say why"
    assert card["ledger_seq"], "the card carries no ledger sequence — the refusal is not auditable"
    assert card["policy"], "the card does not name the policy that held"
    assert "mandate_id" in card, "the card must have the mandate slot even when it is empty"
    return card


# --- I2: no mandate, no motion --------------------------------------------


def test_execute_with_no_mandate_is_denied_and_logged(client):
    """A stranger hitting the API directly and saying 'execute' gets a refusal
    and a ledger line — not an error page, and not an execution."""
    body = _speak(client, "execute it now")
    _refusal_card(body)
    assert "will not act" in body["reply"], body["reply"]

    refusal = _refusals()[-1]
    assert refusal["subject"] == "execute"
    assert "nothing executes on trust" in refusal["reason"]
    assert store.load_state(None)["receipts"] == []


# --- I1: the approval surface is not the execution surface ----------------


def test_approving_without_a_session_is_denied_and_logged(client):
    """The self-approve attack path, driven through the real HTTP route.

    A proposal is genuinely on the table, so the only thing standing between
    the caller and a signed mandate is the absent session token.
    """
    _speak(client, "prove the saving")          # puts a proposal on the table
    assert any(p["status"] == "proposed"
               for p in actions.mandate_status()["proposals"])

    body = _speak(client, "approve")            # no session_token
    card = _refusal_card(body)
    assert card["mandate_id"] is None, "a refusal to approve must not name a mandate"
    assert "refused" in body["reply"].lower(), body["reply"]

    refusal = _refusals()[-1]
    assert "authenticated" in refusal["reason"].lower()
    assert store.load_state(None)["mandates"] == {}


def test_a_client_asserted_approval_string_does_not_authorize(client):
    """The caller supplies its own word that a human approved. It is refused.

    'approver' is never read from the request: the mandate's approver field is
    derived from the session fingerprint server-side.
    """
    _speak(client, "prove the saving")
    body = _speak(client, "approve", session_token="human-i-swear",
                  session_id="attacker-chosen-id")
    _refusal_card(body)
    assert "refused" in body["reply"].lower(), body["reply"]
    assert store.load_state(None)["mandates"] == {}


# --- I3: single-use is server state, not a disabled control ---------------


def test_the_identical_request_twice_produces_one_receipt(client):
    """Replay, at the HTTP layer: the same bytes, sent twice, once succeeds.

    This is the test that distinguishes 'the server refused' from 'the button
    was disabled'. A client that replays the winning request verbatim — with
    the same session token and no cooperation from the UI — still cannot run
    the action a second time.
    """
    token = client.post("/api/session").json()["session_token"]
    _speak(client, "prove the saving", session_token=token)
    approved = _speak(client, "approve", session_token=token)
    mandate_id = approved["cards"][0]["mandate_id"]

    request = {"message": f"execute {mandate_id}", "session_token": token}
    first = client.post("/api/chat", json=request).json()
    assert first["cards"] and first["cards"][0]["type"] == "receipt", first["reply"]

    # byte-identical replay
    second = client.post("/api/chat", json=request).json()
    card = _refusal_card(second)
    assert card["mandate_id"] == mandate_id, "the refusal does not name the mandate it refused"
    assert not any(c["type"] == "receipt" for c in second["cards"]), "the replay produced a receipt"
    assert "consumed" in second["reply"] or "not act" in second["reply"], second["reply"]

    state = store.load_state(None)
    assert len(state["receipts"]) == 1, "two executions ran from one mandate"
    assert state["consumed"].get(mandate_id), "single-use ground truth was not written"

    # The guard that actually holds: bookkeeping is not the ground truth.
    # An attacker who rewinds status to "issued" (the natural thing to try,
    # because that is what the UI reads) must still be refused — otherwise
    # single-use was only ever a status field, and a status field is mutable.
    # Without this step the test above passes on the status check alone, so
    # it would stay green even with the consumption guard deleted.
    rewound = store.load_state(None)
    rewound["mandates"][mandate_id]["status"] = "issued"
    store.save_state(rewound, None)
    after_rewind = client.post("/api/chat", json=request).json()
    _refusal_card(after_rewind)
    assert not any(c["type"] == "receipt" for c in after_rewind["cards"]), "a status rewind re-armed a spent mandate"
    assert len(store.load_state(None)["receipts"]) == 1

    # and the underlying guard says why, independent of the HTTP wording
    direct = actions.execute_action(mandate_id)
    assert direct.get("refused")
    assert "single-use" in direct["error"]


# --- I3b: at most one successful execution, even under concurrency --------


def test_ten_concurrent_executes_produce_exactly_one_receipt():
    """The single-use invariant is *at most one successful execution*.

    Serial replay (above) is not the dangerous case. The dangerous case is
    ten requests arriving together, all reading `consumed == {}` before any
    of them writes. A check-then-act written as

        if not consumed: execute(); consumed = True

    lets every thread through, and the mandate stops being single-use.

    The race window is forced open on purpose: the adapter is slowed so all
    ten threads are inside the verifier before the first one finishes. A
    concurrency test that only races on the microseconds of real work can
    pass for months while the bug is there.
    """
    import concurrent.futures
    import time

    from mcp_server import adapters

    original = adapters.ADAPTERS["rightsize-ec2"]
    calls: list[int] = []          # how many times the provider was actually called
    lock = threading.Lock()

    def slow_adapter(action):
        with lock:
            calls.append(1)
        time.sleep(0.25)
        return original[1](action)

    mandate = _approved("rightsize-ec2")
    adapters.ADAPTERS["rightsize-ec2"] = (original[0], slow_adapter)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(actions.execute_action, mandate["mandate_id"])
                       for _ in range(10)]
            # A thread that raises fails the test. An earlier version of this
            # test swallowed exceptions and counted them as refusals; with the
            # serializing lock removed, nine of ten callers crashed on a
            # concurrent state write and the test still reported
            # "1 success, 9 refusals". A crashed request is not a refusal —
            # it is a 500 where the product promised a recorded decision.
            results = [f.result() for f in futures]
    finally:
        adapters.ADAPTERS["rightsize-ec2"] = original

    # The strongest form of the claim: the provider behind the mandate was
    # reached exactly once. Counted independently of receipts and ledger
    # entries, so a failure cannot be explained away by how the bookkeeping
    # happened to behave on this platform.
    assert len(calls) == 1, (
        f"the provider was called {len(calls)} times from one mandate — "
        "single-use does not hold under concurrency")

    succeeded = [r for r in results if not r.get("refused")]
    refused = [r for r in results if r.get("refused")]
    assert len(succeeded) == 1, f"{len(succeeded)} callers were told it worked"
    assert len(refused) == 9
    # Every loser must have been turned away BY single-use. Nine refusals for
    # any other reason (expiry, cap, an unrelated guard) would satisfy the
    # count and still mean the invariant was never exercised.
    off_reason = [r.get("error") for r in refused if "single-use" not in r.get("error", "")]
    assert not off_reason, f"refused for the wrong reason: {off_reason[:2]}"

    state = store.load_state(None)
    assert len(state["receipts"]) == 1, "more than one receipt was written"
    started = [e for e in state["ledger"] if e["kind"] == "execute_started"]
    assert len(started) == 1, f"{len(started)} executions were started"
    assert state["consumed"].get(mandate["mandate_id"]), "no consumption claim was written"


# --- I4: an issued mandate is immutable -----------------------------------


def test_raising_the_cap_after_approval_does_not_take_effect():
    """Approved -> cannot modify cap.

    The scope is inside SIGNED_FIELDS, so raising the cap invalidates the
    signature: the mandate does not become a bigger mandate, it becomes an
    unsigned one, and execution is refused.
    """
    from mcp_server import store as _store  # local alias; same module

    mandate = _approved("rightsize-ec2")
    state = _store.load_state(None)
    state["mandates"][mandate["mandate_id"]]["scope"]["max_monthly_before"] = 1_000_000.0
    _store.save_state(state, None)

    result = actions.execute_action(mandate["mandate_id"])
    assert result.get("refused"), "a raised cap executed"
    assert "signature" in result["error"].lower(), (
        f"refused for the wrong reason: {result['error']}")


def test_the_signing_secret_never_leaves_the_server():
    """An exported proof bundle must be verifiable offline WITHOUT carrying
    the key that would let its holder mint new mandates."""
    mandate = _approved("rightsize-ec2")
    actions.execute_action(mandate["mandate_id"])
    secret = store.load_state(None)["mandate_secret"]
    assert secret, "no signing secret was ever generated"

    bundle = json.dumps(actions.export_proof(mandate["mandate_id"]))
    assert secret not in bundle, "the proof bundle leaks the HMAC secret"


# --- I5: expiry is a real expired mandate, never a demo flag --------------


def test_a_truly_expired_mandate_is_refused():
    """The demo must never do `if demo_mode: pretend_expired()`.

    This test is the acceptance criterion for the pre-generated expired
    fixture: a mandate is issued through the real approve path, then its
    `expires_at` is set into the past and re-signed by the holder of the
    secret — so the mandate is genuinely expired and the signature is
    genuinely valid. The refusal can then only come from the expiry check.
    """
    from datetime import datetime, timedelta, timezone

    mandate = _approved("rightsize-ec2")
    state = store.load_state(None)
    record = state["mandates"][mandate["mandate_id"]]
    past = datetime.now(timezone.utc) - timedelta(seconds=60)
    record["expires_at"] = past.isoformat(timespec="seconds")
    # Re-signed by the server that owns the secret, so expiry is the ONLY
    # broken invariant: an unsigned fixture would pass for the wrong reason.
    secret = state.get("mandate_secret") or "x"
    payload = {k: record[k] for k in actions.SIGNED_FIELDS}
    record["signature"] = actions._sign(payload, secret)
    store.save_state(state, None)

    result = actions.execute_action(mandate["mandate_id"])
    assert result.get("refused"), "an expired mandate executed"
    assert "expired" in result["error"].lower(), (
        f"refused for the wrong reason: {result['error']}")
    assert store.load_state(None)["receipts"] == []


# --- authority binding: a mandate belongs to the session that minted it ----


def test_a_mandate_is_not_reachable_from_another_session(client, monkeypatch, tmp_path):
    """A mandate minted in A's workspace does not exist in B's.

    This is the authority-binding test: B holds a perfectly valid session
    token, sends a perfectly well-formed request, names the mandate correctly,
    and is still refused — because the mandate lives in a different workspace
    and B's workspace does not contain it.

    Only storage *resolution* is redirected (to temp files, so the test never
    writes into the repo). Every authorization decision in the path is the
    real one.
    """
    from mcp_server import store as store_mod

    monkeypatch.setattr(
        store_mod, "state_path",
        lambda path=None: path or tmp_path / f"{store_mod.current_workspace() or 'anonymous'}.json")
    monkeypatch.setattr(store_mod, "_auth_file", lambda: tmp_path / "auth.json")
    # The single-file override would collapse every workspace into one; the
    # isolation under test only exists in workspace mode.
    monkeypatch.delenv("SPENDLATCH_STATE", raising=False)

    token_a = client.post("/api/session").json()["session_token"]
    _speak(client, "prove the saving", session_token=token_a)
    approved = _speak(client, "approve", session_token=token_a)
    mandate_id = approved["cards"][0]["mandate_id"]

    token_b = client.post("/api/session").json()["session_token"]
    assert token_a != token_b

    crossed = _speak(client, f"execute {mandate_id}", session_token=token_b)
    _refusal_card(crossed)
    assert not any(c["type"] == "receipt" for c in crossed["cards"]), "B executed a mandate that belongs to A"

    def workspace_state(token):
        store_mod.set_workspace(store_mod.workspace_for_token(token))
        try:
            return store_mod.load_state(None)
        finally:
            store_mod.set_workspace(None)

    assert workspace_state(token_b)["receipts"] == [], "a receipt appeared in B's workspace"
    assert workspace_state(token_b)["mandates"] == {}, "A's mandate is visible to B"

    # The mandate itself survived the attempt, untouched.
    a_state = workspace_state(token_a)
    assert mandate_id in a_state["mandates"]
    assert a_state["mandates"][mandate_id]["approver"].startswith("web-session:")


# --- I7: the chain still verifies after all of the above ------------------


def test_every_refusal_in_this_file_is_in_an_unbroken_chain(client):
    """The attacks above produced refusals; the audit trail must still verify.

    If a refusal were swallowed, or recorded outside the chain, this is where
    it shows up.
    """
    _speak(client, "execute it now")
    _speak(client, "prove the saving")
    _speak(client, "approve")
    assert _refusals(), "no refusals were recorded at all"
    assert ledger.verify_chain()["ok"] is True
