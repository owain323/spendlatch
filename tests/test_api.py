"""API surface tests (FastAPI TestClient, in-process, offline)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent.backend import app
from mcp_server import store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDLATCH_STATE", str(tmp_path / "state.json"))
    return TestClient(app)


class TestOpening:
    def test_agent_speaks_first(self, client):
        res = client.get("/api/opening")
        assert res.status_code == 200
        body = res.json()
        assert "found" in body["reply"]
        assert body["cards"]  # unprompted anomaly cards
        assert body["stats"]["saving_potential"] > 0

    def test_session_id_created_and_stable(self, client):
        first = client.get("/api/opening").json()
        second = client.get("/api/opening", params={"session_id": first["session_id"]}).json()
        assert second["session_id"] == first["session_id"]
        assert "Welcome back" in second["reply"]


class TestChat:
    def test_prove_returns_labeled_estimate(self, client):
        res = client.post("/api/chat", json={"message": "prove the saving"})
        card = res.json()["cards"][0]
        assert card["type"] == "saving"
        assert card["monthly_before"] > card["monthly_after"]
        assert "scenario estimate" in card["estimate_basis"]

    def test_budget_roundtrip_and_memory(self, client):
        sid = client.get("/api/opening").json()["session_id"]
        res = client.post("/api/chat", json={"message": "set a $300 budget for home", "session_id": sid})
        card = res.json()["cards"][0]
        assert card["type"] == "budget"
        assert card["monthly_limit"] == 300.0
        assert card["status"] == "warn"
        # cross-session memory: reopening the same session remembers
        reopen = client.get("/api/opening", params={"session_id": sid}).json()
        assert "Welcome back" in reopen["reply"]
        assert any(c["type"] == "budget" for c in reopen["cards"])

    def test_ledger_intent(self, client):
        client.post("/api/chat", json={"message": "anything unusual?"})
        res = client.post("/api/chat", json={"message": "why didn't you tell me?"})
        # The full trail lives in the side rail now; the chat answer stays
        # light and points there.
        assert "Decision ledger panel" in res.json()["reply"]
        assert res.json()["cards"] == []

    def test_challenge_unknown_seq(self, client):
        res = client.post("/api/chat", json={"message": "challenge #9999"})
        assert "don't have" in res.json()["reply"]

    def test_provider_mention_pins_the_prove_action(self, client):
        """Prove the openai api must prove OPENAI's action - not whoever has
        the largest headline number."""
        res = client.post("/api/chat", json={"message": "prove the openai api"})
        card = res.json()["cards"][0]
        assert card["title"] == "Route short OpenAI classification calls to a smaller model"

    def test_bare_provider_mention_answers_with_numbers(self, client):
        """A single provider mention gets a dedicated trend card, not the
        all-provider overview."""
        res = client.post("/api/chat", json={"message": "how is Anthropic API doing"})
        card = res.json()["cards"][0]
        assert card["type"] == "provider-detail"
        assert card["id"] == "anthropic"
        assert "Anthropic" in res.json()["reply"]
        assert len(card["monthly"]) >= 4  # a real series, not a stub

    def test_unknown_message_gets_help(self, client):
        res = client.post("/api/chat", json={"message": "flibbertigibbet"})
        assert "Try:" in res.json()["reply"]

    def test_unit_economics_intent(self, client):
        res = client.post("/api/chat", json={"message": "cost per task"})
        card = res.json()["cards"][0]
        assert card["type"] == "unit"
        assert any(p["canary"] for p in card["providers"])


    def test_crossfoot_endpoint_and_intent(self, client):
        v = client.get("/api/crossfoot").json()
        assert v["ok"] is True and v["lines_checked"] > 0
        res = client.post("/api/chat", json={"message": "do the numbers add up"})
        assert res.json()["cards"][0]["type"] == "crossfoot"
        assert res.json()["cards"][0]["ok"] is True


class TestLedgerApi:
    def test_ledger_verify_reports_chain_ok(self, client):
        client.post("/api/chat", json={"message": "anything unusual?"})
        v = client.get("/api/ledger/verify").json()
        assert v["ok"] is True and v["entries"] >= 1 and v["broken_at"] is None
    def test_ledger_grows_with_actions(self, client):
        before = client.get("/api/ledger").json()["count"]
        client.post("/api/chat", json={"message": "set a $300 budget for home"})
        after = client.get("/api/ledger").json()["count"]
        assert after > before

    def test_unit_endpoint(self, client):
        body = client.get("/api/unit-economics").json()
        assert body["metric"] == "cost per 1K tasks"


class TestStatic:
    def test_index_served(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "SpendLatch" in res.text

    def test_health(self, client):
        assert client.get("/api/health").json() == {"status": "ok"}


# ------------------------------------------- approval handoff (cross-surface)

class TestApprovalHandoff:
    """A one-time code is the bridge from the MCP surface to a human approval."""

    def _mint_handoff(self, expired: bool = False) -> tuple[str, str]:
        from datetime import datetime, timedelta, timezone
        mcp_path = store.workspace_path("mcp")
        state = store.load_state(mcp_path)
        pid = "p-handf00d"
        state["proposals"][pid] = {"proposal_id": pid, "status": "proposed",
                                   "title": "Handoff fixture"}
        expires = (datetime.now(timezone.utc) + timedelta(
            minutes=-1 if expired else 15)).isoformat(timespec="seconds")
        state["handoffs"]["abc123"] = {"proposal_id": pid, "expires_at": expires,
                                       "used": False, "created_at": expires}
        store.save_state(state, mcp_path)
        return pid, "abc123"

    def test_unknown_code_is_refused(self, client):
        token = client.post("/api/session").json()["session_token"]
        out = client.post("/api/handoff", json={"code": "nope", "session_token": token}).json()
        assert out["ok"] is False and "unknown" in out["error"]

    def test_expired_code_is_refused(self, client):
        pid, code = self._mint_handoff(expired=True)
        token = client.post("/api/session").json()["session_token"]
        out = client.post("/api/handoff", json={"code": code, "session_token": token}).json()
        assert out["ok"] is False and "expired" in out["error"]

    def test_code_is_one_time(self, client):
        pid, code = self._mint_handoff()
        token = client.post("/api/session").json()["session_token"]
        first = client.post("/api/handoff", json={"code": code, "session_token": token}).json()
        assert first["ok"] is True and first["proposal_id"] == pid
        second = client.post("/api/handoff", json={"code": code, "session_token": token}).json()
        assert second["ok"] is False and "already used" in second["error"]


# ------------------------------------- bearer token + public-demo guards

@pytest.fixture()
def clean_limits():
    import agent.backend as backend
    backend._rate_state.clear()
    yield
    backend._rate_state.clear()


class TestTokenTransportAndGuards:
    """The approval token is a bearer credential: header, never the URL."""

    def test_ledger_accepts_the_bearer_header(self, client, clean_limits):
        token = client.post("/api/session").json()["session_token"]
        out = client.get("/api/ledger", headers={"Authorization": f"Bearer {token}"})
        assert out.status_code == 200 and "entries" in out.json()

    def test_oversized_body_is_rejected_before_parsing(self, client, clean_limits):
        token = client.post("/api/session").json()["session_token"]
        big = {"message": "x" * 40000, "session_token": token}
        out = client.post("/api/chat", json=big)
        assert out.status_code == 413

    def test_rate_limit_returns_429(self, client, monkeypatch):
        import agent.backend as backend
        monkeypatch.setattr(backend, "RATE_LIMIT", 3)
        monkeypatch.setattr(backend, "_rate_state", {})
        codes = [client.post("/api/session").status_code for _ in range(5)]
        assert 429 in codes, f"no rate limiting: {codes}"
        monkeypatch.undo()


@pytest.fixture()
def workspace_client(tmp_path, monkeypatch):
    """Workspace topology (`data/workspaces/*.json`), not single-file mode.

    The Bearer-vs-query defect is only observable when workspaces are separate
    files. In single-file mode every caller shares one state file, so a
    misrouted token looks exactly like a correct one - which is how the
    `/api/opening` regression stayed green while production was wrong.
    """
    monkeypatch.delenv("SPENDLATCH_STATE", raising=False)
    monkeypatch.setenv("SPENDLATCH_DATA_DIR", str(tmp_path / "data"))
    return TestClient(app)


class TestTokenTransportMatrix:
    def test_token_transport_matrix_lands_in_same_workspace(
            self, workspace_client, tmp_path, clean_limits):
        """Header and query must resolve to the SAME workspace, on every route.

        One route at a time is how this broke: `/api/ledger` and
        `/api/ledger/verify` read the header, `/api/opening` did not, so a
        Bearer-authenticated caller silently landed in the shared anonymous
        workspace and read other visitors' suppressed state.
        """
        session = workspace_client.post("/api/session").json()
        token, workspace = session["session_token"], session["workspace"]
        header = {"Authorization": f"Bearer {token}"}

        # Header form, brand-new workspace: the agent must speak first.
        by_header = workspace_client.get("/api/opening", headers=header).json()
        assert by_header["stats"]["saving_potential"] > 0
        assert sum(1 for c in by_header["cards"] if c["type"] == "anomaly") == 3, \
            f"header-authenticated opening saw {[c['type'] for c in by_header['cards']]}"

        for path in ("/api/opening", "/api/ledger", "/api/ledger/verify"):
            by_h = workspace_client.get(path, headers=header)
            by_q = workspace_client.get(path, params={"session_token": token})
            assert by_h.status_code == 200 and by_q.status_code == 200, path

        # The opening's alert entries landed in the caller's own workspace ...
        workspaces = tmp_path / "data" / "workspaces"
        own = workspaces / f"{workspace}.json"
        assert own.exists(), "the caller's own workspace was never written"
        assert len(workspace_client.get(
            "/api/ledger", headers=header).json()["entries"]) >= 3
        # ... and nothing leaked into the shared anonymous one.
        assert not (workspaces / "anonymous.json").exists(), \
            "a Bearer-authenticated call wrote to the shared anonymous workspace"

    @pytest.mark.xfail(
        strict=False,
        reason="known defect F-05: attacks._mint() mints a real session and a "
               "real mandate inside the caller's workspace, so the attack "
               "fixture leaves an executed mandate behind. Pending the "
               "authorization-model round; not fixed by touching attacks.py.")
    def test_attack_endpoints_do_not_mint_a_mandate_in_the_callers_workspace(
            self, workspace_client, tmp_path, clean_limits):
        session = workspace_client.post("/api/session").json()
        token, workspace = session["session_token"], session["workspace"]
        body = workspace_client.post("/api/attack/replay",
                                     json={"message": "attack",
                                           "session_token": token}).json()
        assert body["refused"] is True
        state = json.loads((tmp_path / "data" / "workspaces" / f"{workspace}.json")
                           .read_text(encoding="utf-8"))
        executed = [m for m in state["mandates"].values()
                    if m.get("status") == "executed"]
        assert executed == [], \
            f"the attack fixture left {len(executed)} executed mandate(s) in the caller's workspace"


# ------------------------------- the contract the browser's error path reads

class TestErrorContractTheClientDependsOn:
    """app.js turns a failed call into a sentence, and it reads `detail`.

    These pin the shape, not the wording: the client maps 413/429/5xx to its
    own copy, and falls back to `detail` for anything else. If a guard starts
    returning HTML or an empty body, the browser would show a bare status code
    with no explanation - so the shape is part of the contract.
    """

    def test_oversized_body_carries_a_json_detail(self, client, clean_limits):
        token = client.post("/api/session").json()["session_token"]
        out = client.post("/api/chat", json={"message": "x" * 40000,
                                             "session_token": token})
        assert out.status_code == 413
        assert out.headers["content-type"].startswith("application/json")
        assert out.json().get("detail")

    def test_rate_limit_carries_a_json_detail(self, client, monkeypatch):
        import agent.backend as backend
        monkeypatch.setattr(backend, "RATE_LIMIT", 2)
        monkeypatch.setattr(backend, "_rate_state", {})
        last = None
        for _ in range(4):
            last = client.post("/api/session")
            if last.status_code == 429:
                break
        assert last is not None and last.status_code == 429
        assert last.headers["content-type"].startswith("application/json")
        assert last.json().get("detail")
        monkeypatch.undo()


class TestConcurrentSessionMinting:
    """The registry is one JSON file read-modify-write; two first-time visitors
    arriving together must not drop one another's token."""

    def test_ten_concurrent_sessions_all_survive(self):
        import threading
        from mcp_server import actions, store

        tokens: list[str] = []
        lock = threading.Lock()

        def mint() -> None:
            tok = actions.open_session()["session_token"]
            with lock:
                tokens.append(tok)

        threads = [threading.Thread(target=mint) for _ in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(tokens) == 10
        assert len(set(tokens)) == 10, "two sessions minted the same token"
        registry = store._auth_map()   # the auth file, not the workspace state
        present = [t for t in tokens if store._token_hash(t) in registry]
        assert len(present) == len(tokens), (
            f"only {len(present)} of {len(tokens)} tokens reached the registry")
