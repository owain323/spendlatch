"""Evidence for the authorization boundaries, not just the happy path.

Every test in this file corresponds to a row in docs/THREAT-MODEL.md. They
exist because a boundary that is not demonstrated is not a boundary: if one
of these guards is deleted, the test fails rather than the count changing.
"""
from __future__ import annotations

import pytest

from mcp_server import actions, adapters


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDLATCH_STATE", str(tmp_path / "state.json"))


def _approved(action_id: str = "rightsize-ec2") -> dict:
    proposal = actions.propose_action(action_id)
    token = actions.open_session()["session_token"]
    return actions.approve_action(proposal["proposal_id"], session_token=token)


# --- T12: the signed operation is what runs ------------------------------


def test_normal_execution_runs_the_signed_operation():
    mandate = _approved("rightsize-ec2")
    receipt = actions.execute_action(mandate["mandate_id"])
    assert receipt["operation"] == mandate["scope"]["operation"]
    assert not receipt.get("refused")


def test_swapped_adapter_cannot_run_under_a_valid_signature(monkeypatch):
    mandate = _approved("cancel-figma")
    assert mandate["scope"]["provider"] == "figma"
    assert mandate["scope"]["operation"] == "admin:RemoveSeat"
    monkeypatch.setitem(adapters.ADAPTERS, "cancel-figma",
                        adapters.ADAPTERS["rightsize-ec2"])
    receipt = actions.execute_action(mandate["mandate_id"])
    assert receipt.get("refused"), "a signed mandate executed an unauthorized operation"
    assert "scope drifted" in receipt["error"]


def test_receipt_reports_the_registered_operation():
    """The receipt's operation comes from the registry, not from a literal in
    the adapter body, so the two can never disagree."""
    receipt = actions.execute_action(_approved("rightsize-ec2")["mandate_id"])
    assert receipt["operation"] == adapters.OPERATIONS["rightsize-ec2"]


# --- T11: consent must be an explicit yes --------------------------------


@pytest.mark.parametrize("phrase", [
    "I do NOT approve this",
    "don't approve",
    "never approve anything without asking me",
    "should I approve?",
    "what happens if I approve?",
    "why should I approve?",
    "cancel that",
    "stop",
])
def test_refusal_shaped_utterance_never_signs(phrase):
    from agent import brain
    actions.propose_action("rightsize-ec2")
    token = actions.open_session()["session_token"]
    brain.handle(phrase, f"sess-consent-{phrase[:6]}", session_token=token)
    issued = [m for m in actions.mandate_status()["mandates"] if m["status"] == "issued"]
    assert not issued, f"{phrase!r} was read as consent"


def test_refusal_is_logged_as_a_decision():
    from agent import brain
    from mcp_server import ledger
    actions.propose_action("rightsize-ec2")
    token = actions.open_session()["session_token"]
    before = len(ledger.entries())
    brain.handle("I do not approve this", "sess-consent-log", session_token=token)
    after = [e["kind"] for e in ledger.entries()]
    assert len(after) == before + 1 and after[-1] == "refuse"


@pytest.mark.parametrize("phrase", ["approve", "yes, do it", "go ahead"])
def test_explicit_approval_still_signs(phrase):
    from agent import brain
    actions.propose_action("rightsize-ec2")
    token = actions.open_session()["session_token"]
    brain.handle(phrase, f"sess-yes-{phrase[:4]}", session_token=token)
    issued = [m for m in actions.mandate_status()["mandates"] if m["status"] == "issued"]
    assert issued, f"explicit {phrase!r} no longer issues a mandate"


# --- T13: new spend is denied without the LLM ----------------------------


@pytest.mark.parametrize("phrase", [
    "buy $200 of API credits",
    "purchase 50 dollars of compute",
    "recharge the openai account with $100",
    "order a new GPU for $5000",
])
def test_new_spend_is_denied_and_logged(phrase):
    from agent import brain
    token = actions.open_session()["session_token"]
    result = brain.handle(phrase, f"sess-spend-{phrase[:6]}", session_token=token)
    card = (result.get("cards") or [{}])[0]
    assert card.get("type") == "denied" and card.get("ledger_seq")


@pytest.mark.parametrize("question", [
    "how much did I spend this month",
    "show me the overview",
])
def test_ordinary_questions_are_not_mistaken_for_spend_requests(question):
    from agent import brain
    token = actions.open_session()["session_token"]
    result = brain.handle(question, f"sess-q-{question[:6]}", session_token=token)
    assert (result.get("cards") or [{}])[0].get("type") != "denied"


# --- T5: single-use does not depend on mutable bookkeeping ---------------


def test_rollback_of_status_does_not_allow_a_second_execution():
    from mcp_server import store
    mandate = _approved("rightsize-ec2")
    assert not actions.execute_action(mandate["mandate_id"]).get("refused")
    state = store.load_state(None)
    state["mandates"][mandate["mandate_id"]]["status"] = "issued"
    store.save_state(state, None)
    second = actions.execute_action(mandate["mandate_id"])
    assert second.get("refused"), "a status rollback re-armed a spent mandate"
    assert len(store.load_state(None)["receipts"]) == 1


def test_consumption_survives_ledger_trimming():
    from mcp_server import ledger
    mandate = _approved("rightsize-ec2")
    actions.execute_action(mandate["mandate_id"])
    for i in range(ledger.MAX_ENTRIES + 20):
        ledger.record("alert", "aws", f"filler {i}", path=None)
    assert actions.execute_action(mandate["mandate_id"]).get("refused"), (
        "trimming the audit window revived a spent mandate"
    )


def test_adapter_failure_releases_the_claim():
    """A claim must not become a permanent lock when the adapter itself
    refuses: the honest outcome is 'nothing ran', not 'spent'."""
    mandate = _approved("rightsize-ec2")
    original = adapters.ADAPTERS["rightsize-ec2"]
    adapters.ADAPTERS["rightsize-ec2"] = ("aws", lambda action: {"error": "simulated outage"})
    try:
        first = actions.execute_action(mandate["mandate_id"])
        assert first.get("refused"), "a failing adapter should refuse, not execute"
    finally:
        adapters.ADAPTERS["rightsize-ec2"] = original
    # nothing ran, so the mandate must still be usable
    second = actions.execute_action(mandate["mandate_id"])
    assert not second.get("refused"), "an adapter outage permanently burned the mandate"


# --- exported proofs stay verifiable --------------------------------------


def test_old_proof_bundle_still_verifies_after_later_actions(tmp_path):
    """An audit archive must not expire when the system is used again."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    first = _approved("rightsize-ec2")
    actions.execute_action(first["mandate_id"])
    bundle = tmp_path / "first.json"
    bundle.write_text(json.dumps(actions.export_proof(first["mandate_id"])), encoding="utf-8")

    for action_id in ("cancel-figma", "annual-zoom"):
        mandate = _approved(action_id)
        actions.execute_action(mandate["mandate_id"])

    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(repo / "tools" / "verify_proof.py"),
                             str(bundle)], capture_output=True, text=True, cwd=str(repo))
    assert result.returncode == 0, (
        "an exported proof stopped verifying after later executions:\n" + result.stdout
    )
