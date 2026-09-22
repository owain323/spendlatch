"""Crash-injection tests for the execute -> record seam.

The seam: adapters.execute succeeds, then the mandate is marked consumed and
the ledger entry is written. If the process dies between the adapter call and
the ledger write, the action happened (money moved) but the books never saw
it - and the mandate still says "issued", so it can run again. These tests
prove the seam exists (red) and then prove it is closed (green).
"""
from __future__ import annotations

import pytest

from mcp_server import actions, store


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDLATCH_STATE", str(tmp_path / "state.json"))


def _approved_flow() -> str:
    """Build a proposal + mandate; returns mandate_id."""
    proposal = actions.propose_action("rightsize-ec2")
    token = actions.open_session()["session_token"]
    mandate = actions.approve_action(proposal["proposal_id"], session_token=token)
    return mandate["mandate_id"]


def test_execute_record_seam_causes_double_execute(monkeypatch):
    """Crash after the adapter ran but before the ledger write. With the seam
    closed, the mandate must be treated as consumed (execute_started recorded)
    - no double execution."""
    mandate_id = _approved_flow()

    crashed_once = {"hit": False}
    real_save = store.save_state

    def boom(state, path=None):
        # crash ONLY on the save that persists the receipt (after the adapter
        # ran) - the started record's save has no receipt yet and must pass.
        if state.get("receipts") and not crashed_once["hit"]:
            crashed_once["hit"] = True
            raise RuntimeError("simulated crash after adapter execute")
        return real_save(state, path)

    monkeypatch.setattr(store, "save_state", boom)

    try:
        actions.execute_action(mandate_id)
    except RuntimeError:
        pass

    monkeypatch.undo()

    second = actions.execute_action(mandate_id)
    assert second.get("refused"), (
        "SEAM OPEN: mandate ran twice after a crash between adapter execute "
        "and ledger write - the action (and the money) can happen twice"
    )
