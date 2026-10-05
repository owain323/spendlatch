"""The five demo attacks, driven through the real HTTP route.

Acceptance for the attack surface: every attack ends in a REAL refusal
computed by the guard under attack, recorded in the ledger, and rendered as
a structured refusal card. A fixture may be synthetic; the refusal may not.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.backend import app
from mcp_server import ledger


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDLATCH_STATE", str(tmp_path / "state.json"))


@pytest.fixture()
def client():
    return TestClient(app)


# Each attack must be refused BY ITS OWN GUARD. "Refused for some reason"
# would let a broken cap pass on the strength of an expiry refusal.
EXPECTED_REASON = {
    "replay": "single-use",
    "self-approve": "authenticated",
    "over-cap": "cap",
    "expired": "expired",
    "forged-scope": "signature",
}


@pytest.mark.parametrize("kind", sorted(EXPECTED_REASON))
def test_every_attack_is_refused_by_its_own_guard(client, kind):
    body = client.post(f"/api/attack/{kind}", json={"message": "attack"}).json()
    assert body["refused"] is True, body["reply"]
    assert EXPECTED_REASON[kind] in body["reason"].lower(), body["reason"]

    card = body["cards"][0]
    assert card["type"] == "denied"
    assert card["action"] == f"attack:{kind}"
    assert card["ledger_seq"], "the refusal carries no ledger sequence"
    assert card["policy"], "the refusal does not name the policy that held"

    # The refusal is in the ledger, not only in the response body.
    assert any(e["kind"] == "refuse" for e in ledger.entries()), \
        "the attack refusal never reached the ledger"
    assert ledger.verify_chain()["ok"] is True


def test_unknown_attack_is_named_not_executed(client):
    body = client.post("/api/attack/nuke", json={"message": "x"}).json()
    assert "nuke" in body["reply"]
    assert body["cards"] == []
