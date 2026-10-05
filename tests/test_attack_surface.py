"""Attack-surface regression tests.

Each test here corresponds to a boundary claim the product makes. They are
written so that removing the guard makes them fail, not merely change a
number: if a future edit drops one of these checks, the test goes red.

Scope: the authorize -> execute path, the consent check, and the
default-deny gate for new spend.
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


# --- the signed operation is what must run -------------------------------


def test_normal_execution_still_runs_the_signed_operation():
    mandate = _approved("rightsize-ec2")
    receipt = actions.execute_action(mandate["mandate_id"])
    assert receipt["operation"] == mandate["scope"]["operation"]
    assert not receipt.get("refused")


def test_swapped_adapter_cannot_run_under_a_valid_signature(monkeypatch):
    """A mandate signed for one provider/operation must not execute another,
    even when the signature is intact and the cap is untouched."""
    mandate = _approved("cancel-figma")
    assert mandate["scope"]["provider"] == "figma"
    assert mandate["scope"]["operation"] == "admin:RemoveSeat"

    # Repoint the action at a different adapter - the exact move an attacker
    # with registry access would make.
    monkeypatch.setitem(adapters.ADAPTERS, "cancel-figma",
                        adapters.ADAPTERS["rightsize-ec2"])

    receipt = actions.execute_action(mandate["mandate_id"])
    assert receipt.get("refused"), (
        "a signed mandate executed an operation it was not signed for"
    )
    assert "scope drifted" in receipt["error"]


def test_rollback_of_status_does_not_allow_a_second_execution():
    """Single-use must not depend on the mutable status field. An attacker (or
    a buggy restore) that flips status back to "issued" must still be refused."""
    from mcp_server import store
    mandate = _approved("rightsize-ec2")
    first = actions.execute_action(mandate["mandate_id"])
    assert not first.get("refused")

    state = store.load_state(None)
    state["mandates"][mandate["mandate_id"]]["status"] = "issued"
    store.save_state(state, None)

    second = actions.execute_action(mandate["mandate_id"])
    assert second.get("refused"), (
        "rolling the status field back to 'issued' allowed a second execution"
    )
    assert len(store.load_state(None)["receipts"]) == 1, "a second receipt was written"


def test_consumption_survives_ledger_trimming():
    """The single-use guard must not live in the bounded ledger: once the claim
    is recorded, trimming audit history cannot make a spent mandate live again."""
    from mcp_server import ledger, store
    mandate = _approved("rightsize-ec2")
    actions.execute_action(mandate["mandate_id"])

    # Force the ledger past its retention window.
    for i in range(ledger.MAX_ENTRIES + 20):
        ledger.record("alert", "aws", f"filler {i}", path=None)

    second = actions.execute_action(mandate["mandate_id"])
    assert second.get("refused"), (
        "a spent mandate became executable again after the ledger was trimmed"
    )


# --- consent must be an explicit yes -------------------------------------


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
    brain.handle(phrase, "sess-consent", session_token=token)
    issued = [m for m in actions.mandate_status()["mandates"] if m["status"] == "issued"]
    assert not issued, f"{phrase!r} was treated as consent and signed a mandate"


def test_refusal_is_logged_as_a_decision():
    from agent import brain
    from mcp_server import ledger
    actions.propose_action("rightsize-ec2")
    token = actions.open_session()["session_token"]
    before = len(ledger.entries())
    brain.handle("I do not approve this", "sess-consent-log", session_token=token)
    # entries() returns the ledger in append order, so the newest is last.
    after = [e["kind"] for e in ledger.entries()]
    assert len(after) == before + 1, "the refusal was not appended to the ledger"
    assert after[-1] == "refuse", (
        f"the newest ledger entry should be the refusal, got {after[-1]!r}"
    )


@pytest.mark.parametrize("phrase", ["approve", "yes, do it", "go ahead"])
def test_explicit_approval_still_signs(phrase):
    from agent import brain
    actions.propose_action("rightsize-ec2")
    token = actions.open_session()["session_token"]
    brain.handle(phrase, f"sess-yes-{phrase[:4]}", session_token=token)
    issued = [m for m in actions.mandate_status()["mandates"] if m["status"] == "issued"]
    assert issued, f"explicit {phrase!r} no longer issues a mandate"


# --- new spend is denied by default, without the LLM ---------------------


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
    assert card.get("type") == "denied", f"{phrase!r} was not denied"
    assert card.get("ledger_seq"), "the denial was not written to the ledger"


@pytest.mark.parametrize("question", [
    "how much did I spend this month",
    "show me the overview",
])
def test_ordinary_questions_are_not_mistaken_for_spend_requests(question):
    from agent import brain
    token = actions.open_session()["session_token"]
    result = brain.handle(question, f"sess-q-{question[:6]}", session_token=token)
    card = (result.get("cards") or [{}])[0]
    assert card.get("type") != "denied", "a question was misread as a spend request"
