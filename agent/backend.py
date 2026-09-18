"""SpendPilot agent backend — bridges the web experience to the tool layer.

Serves the simulated Alexa+ web experience and the chat API. State
(budgets, acknowledgements, session history, decision ledger) persists in a
local JSON file, which is what makes cross-session memory real rather than
staged.

Run:  python -m agent.backend   # serves http://127.0.0.1:8200
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mcp_server import store, tools

from . import brain

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="SpendPilot", version="0.3.0")


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    cards: list[dict]
    stats: dict | None = None


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    session_id = req.session_id or uuid.uuid4().hex[:12]
    store.remember_turn(session_id, "user", req.message)
    result = brain.handle(req.message, session_id)
    store.remember_turn(session_id, "agent", result["reply"])
    return ChatResponse(session_id=session_id, reply=result["reply"], cards=result["cards"])


@app.get("/api/opening", response_model=ChatResponse)
def opening(session_id: str | None = None) -> ChatResponse:
    """Proactive first message; restores context when the session is known."""
    session_id = session_id or uuid.uuid4().hex[:12]
    history = store.session_history(session_id)
    if history:
        status = brain.handle("budget", session_id)
        briefing = tools.proactive_briefing()
        return ChatResponse(
            session_id=session_id,
            reply="Welcome back. I remember our last conversation — your budgets are still on watch, "
                  "and the ledger kept recording while you were away.",
            cards=status["cards"],
            stats={
                "month": briefing["overview"]["month"],
                "total": briefing["overview"]["total"],
                "delta_pct": briefing["overview"]["delta_pct"],
                "anomalies": len(briefing["anomalies"]),
                "saving_potential": briefing["total_monthly_saving_potential"],
            },
        )
    result = brain.opening(session_id)
    store.remember_turn(session_id, "agent", result["reply"])
    return ChatResponse(session_id=session_id, reply=result["reply"],
                        cards=result["cards"], stats=result.get("stats"))


@app.get("/api/ledger")
def get_ledger() -> dict:
    """The full decision ledger — the observability surface."""
    return tools.decision_ledger()


@app.get("/api/unit-economics")
def get_unit_economics() -> dict:
    return tools.unit_economics()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def main() -> None:
    import os

    import uvicorn

    uvicorn.run(app, host="127.0.0.1",
                port=int(os.environ.get("SPENDPILOT_WEB_PORT", "8200")))


if __name__ == "__main__":
    main()
