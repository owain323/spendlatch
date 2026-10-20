"""SL-003: an approval must name the action it authorizes.

A bare "approve" next to several open proposals used to sign the newest
one. That turns an ambiguous word into an authorization, which is the
single error this product exists to prevent. These tests pin the rule:
>1 open proposal -> nothing is signed, the human is asked to name an id;
an id -> exactly that proposal is signed; choice/negation language ->
nothing is signed.
"""
from __future__ import annotations

import pytest

from agent import brain
from mcp_server import actions


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDLATCH_STATE", str(tmp_path / "state.json"))


def _two_open() -> tuple[str, str, str]:
    a = actions.propose_action("rightsize-ec2")
    b = actions.propose_action("cancel-figma")
    token = actions.open_session()["session_token"]
    return a["proposal_id"], b["proposal_id"], token


def _mandate_cards(out: dict) -> list[dict]:
    return [c for c in out.get("cards", []) if c.get("type") == "mandate"]


def test_bare_approve_with_two_open_proposals_signs_nothing():
    p1, p2, token = _two_open()
    out = brain.handle("approve", "s1", token)
    assert _mandate_cards(out) == [], "an ambiguous approve issued a mandate"
    assert p1 in out["reply"] and p2 in out["reply"], "the reply must list what is open"
    assert "approve p-" in out["reply"]
    assert actions.mandate_status()["mandates"] == []


def test_naming_a_proposal_signs_exactly_that_one():
    p1, p2, token = _two_open()
    out = brain.handle(f"approve {p2}", "s1", token)
    cards = _mandate_cards(out)
    assert len(cards) == 1
    assert cards[0]["proposal_id"] == p2
    status = actions.mandate_status()
    assert len(status["mandates"]) == 1
    still_open = {p["proposal_id"] for p in status["proposals"] if p["status"] == "proposed"}
    assert still_open == {p1}, "approving one proposal must not touch the other"


def test_choice_language_without_an_id_signs_nothing():
    actions.propose_action("rightsize-ec2")
    token = actions.open_session()["session_token"]
    out = brain.handle("approve the second one instead", "s1", token)
    assert _mandate_cards(out) == []
    assert actions.mandate_status()["mandates"] == []


def test_single_open_proposal_still_accepts_a_plain_yes():
    actions.propose_action("rightsize-ec2")
    token = actions.open_session()["session_token"]
    out = brain.handle("approve", "s1", token)
    assert len(_mandate_cards(out)) == 1, "one candidate + a plain yes must still sign"
