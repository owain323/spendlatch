"""Decision ledger — the agent's accountability trail.

Every decision the agent makes is appended here with a one-line reason:
what it surfaced (alert), what it held back and why (suppress / hold),
what it refused to do (refuse), what the human overruled (challenge).
Cancelled or withheld items are ALWAYS recorded — silence is also a decision.

The ledger is the observability surface of the product: "why did you bother
me — and why did you NOT bother me" must be answerable line by line.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import store

MAX_ENTRIES = 500


def record(kind: str, subject: str, reason: str, evidence: list[str] | None = None,
           path: Path | None = None) -> dict:
    """Append one decision entry. `kind` in alert|suppress|hold|propose|refuse|challenge|budget."""
    state = store.load_state(path)
    entry = {
        "seq": len(state["ledger"]) + 1,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "subject": subject,
        "reason": reason,
        "evidence": evidence or [],
    }
    state["ledger"].append(entry)
    state["ledger"] = state["ledger"][-MAX_ENTRIES:]
    store.save_state(state, path)
    return entry


def entries(path: Path | None = None, kinds: set[str] | None = None) -> list[dict]:
    ledger = store.load_state(path)["ledger"]
    if kinds:
        ledger = [e for e in ledger if e["kind"] in kinds]
    return ledger


def has_fired(anomaly_id: str, month: str, path: Path | None = None) -> bool:
    """True if this anomaly was already surfaced for this month (suppression)."""
    fired = store.load_state(path)["alerts_fired"]
    return fired.get(anomaly_id) == month


def mark_fired(anomaly_id: str, month: str, path: Path | None = None) -> None:
    state = store.load_state(path)
    state["alerts_fired"][anomaly_id] = month
    store.save_state(state, path)


def challenge(entry_seq: int, note: str, path: Path | None = None) -> dict:
    """The human overrules a decision. Challenges flow back as context —
    the challenged subject will not be suppressed the same way again."""
    state = store.load_state(path)
    target = next((e for e in state["ledger"] if e["seq"] == entry_seq), None)
    if target is None:
        raise KeyError(f"no ledger entry with seq={entry_seq}")
    challenge_record = {"seq": entry_seq, "subject": target["subject"], "note": note,
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    state["challenges"].append(challenge_record)
    store.save_state(state, path)
    record("challenge", target["subject"], f"Human overruled: {note}", path=path)
    return challenge_record


def challenged_subjects(path: Path | None = None) -> set[str]:
    return {c["subject"] for c in store.load_state(path)["challenges"]}
