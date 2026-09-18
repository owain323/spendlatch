"""Persistent JSON state for SpendPilot.

This is the cross-session memory of the product: budgets, acknowledged
alerts, and per-session conversation bookmarks survive restarts. State lives
in a single local JSON file; nothing leaves the machine.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULT_STATE: dict = {
    "budgets": {},          # category -> {"monthly_limit": float}
    "acknowledged": [],     # anomaly ids the human has already seen
    "sessions": {},         # session_id -> {"history": [...], "created": str}
    "ledger": [],           # decision event stream (see ledger.py)
    "alerts_fired": {},     # anomaly_id -> month last surfaced (suppression)
    "suppressed": {},       # anomaly_id -> month a suppression was logged
    "challenges": [],       # human overrules, fed back as context
    "proposals": {},        # proposal_id -> bounded action awaiting approval
    "mandates": {},         # mandate_id -> signed, scoped, expiring authorization
    "receipts": [],         # execution receipts (adapter reports)
    "mandate_secret": None, # per-installation HMAC key, generated on first approval
}

_ENV_KEY = "SPENDPILOT_STATE"


def state_path() -> Path:
    """Resolve the state file location (env-overridable for tests)."""
    raw = os.environ.get(_ENV_KEY)
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent / "data" / "state.json"


def load_state(path: Path | None = None) -> dict:
    """Load state, falling back to defaults for any missing key."""
    path = path or state_path()
    state = json.loads(json.dumps(DEFAULT_STATE))
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                state.update(stored)
        except (json.JSONDecodeError, OSError):
            pass  # corrupt state must never crash the agent; start clean
    return state


def save_state(state: dict, path: Path | None = None) -> None:
    """Atomically persist state (write-temp-then-replace)."""
    path = path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def set_budget(category: str, monthly_limit: float, path: Path | None = None) -> dict:
    if monthly_limit <= 0:
        raise ValueError("monthly_limit must be positive")
    state = load_state(path)
    state["budgets"][category] = {"monthly_limit": round(float(monthly_limit), 2)}
    save_state(state, path)
    return state["budgets"][category]


def acknowledge(anomaly_id: str, path: Path | None = None) -> None:
    state = load_state(path)
    if anomaly_id not in state["acknowledged"]:
        state["acknowledged"].append(anomaly_id)
        save_state(state, path)


def remember_turn(session_id: str, role: str, text: str, path: Path | None = None) -> None:
    """Append one conversation turn to a session (cross-session memory)."""
    state = load_state(path)
    session = state["sessions"].setdefault(session_id, {"history": []})
    session["history"].append({"role": role, "text": text})
    session["history"] = session["history"][-50:]  # bound growth
    save_state(state, path)


def session_history(session_id: str, path: Path | None = None) -> list[dict]:
    return load_state(path)["sessions"].get(session_id, {}).get("history", [])
