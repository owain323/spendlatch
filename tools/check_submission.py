"""Submission copy gate — the text a judge reads must name things that exist.

Every other gate in this repo checks code, tests or evidence. The submission
copy is the one artifact a judge may follow literally: connect to the demo
and call a tool by the name printed here. When it lived outside the repo,
nothing here could see it, and two tool names in it did not exist.

This checks the copy against the code:
  - every tool it names is a registered MCP tool
  - it does not credit a stack the repository does not contain
  - it does not describe the approval session as authenticated
  - the test count it quotes matches docs/evidence/test-count.txt

Usage: python tools/check_submission.py     # exit 1 on any mismatch
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPY = ROOT / "submission" / "devpost.md"
SERVER = ROOT / "mcp_server" / "server.py"
COUNT = ROOT / "docs" / "evidence" / "test-count.txt"

# Tokens that make a snake_case identifier look like a tool name. Prose words
# do not contain these; tool names almost always do. A tight rule here is what
# keeps the gate useful: a check that cries wolf gets switched off.
TOOLISH = ("action", "anomalies", "saving", "ledger", "status", "budget",
           "overview", "subscriptions", "economics", "briefing", "proof", "card")
# Words that would mean claiming a dependency the repo does not have.
NOT_IN_REPO = ("Rust", "React", "TypeScript", "DuckDB", "Axum", "SQLite")
# Identifiers in the copy that are not tools and are allowed to look like one.
ALLOWED_NON_TOOLS = {
    "authorization_boundary", "agentic_payment", "spend_intent", "read_only",
    "read_only_analysis", "web_session", "streamable_http", "product_feedback_set",
    "hash_chained", "single_use", "scope_capped", "default_deny", "cost_per_task",
}


def registered_tools() -> set[str]:
    src = SERVER.read_text(encoding="utf-8")
    # match any decorator form, including one carrying metadata
    return set(re.findall(r"@mcp\.tool[^\n]*\n(?:[^\n]*\n)?def (\w+)", src))


def repo_lacks(word: str) -> bool:
    """True when no source file in the repo mentions `word`.

    tools/ is skipped on purpose: this file lists the words it forbids, and
    a gate that finds its own constant list has proved nothing.
    """
    for pattern in ("*.py", "*.toml", "*.json"):
        for p in ROOT.rglob(pattern):
            if any(part in {".git", "node_modules", "__pycache__", "build", "tools"}
                   for part in p.parts):
                continue
            try:
                if re.search(rf"\b{re.escape(word)}\b", p.read_text(encoding="utf-8", errors="ignore")):
                    return False
            except OSError:
                continue
    return True


def main() -> int:
    if not COPY.exists():
        print("submission/devpost.md is missing — the copy must live in the repo")
        return 1
    text = COPY.read_text(encoding="utf-8")
    tools = registered_tools()
    problems: list[str] = []

    # 1. every tool-shaped identifier the copy names must be registered.
    #    Scanned bare, not just inside backticks: the copy once named two
    #    tools that do not exist in running prose, and a judge would have
    #    called them.
    for name in sorted(set(re.findall(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b", text))):
        if name in tools or name in ALLOWED_NON_TOOLS:
            continue
        if any(tok in name for tok in TOOLISH):
            problems.append(f"names a tool that is not registered: {name}")

    # 2. no credit for a stack this repository does not contain
    for word in NOT_IN_REPO:
        if re.search(rf"\b{re.escape(word)}\b", text) and repo_lacks(word):
            problems.append(f"credits a dependency the repo does not have: {word}")

    # 3. the approval session is self-issued; calling it authenticated is the
    #    claim THREAT-MODEL L1 exists to correct
    for m in re.finditer(r"[^.\n]{0,70}authenticated[^.\n]{0,70}", text):
        problems.append(f"describes the session as authenticated: ...{m.group(0).strip()[:90]}...")

    # 4. the quoted test count must be the measured one
    if COUNT.exists():
        truth = COUNT.read_text(encoding="utf-8").split("\n", 1)[0].strip()
        for quoted in set(re.findall(r"\b(\d{2,4})\s+(?:pytest\s+|automated\s+)?tests\b", text)):
            if quoted != truth:
                problems.append(f"quotes {quoted} tests; the measured count is {truth}")

    if problems:
        print("SUBMISSION COPY GATE FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"submission copy: OK ({len(tools)} registered tools, {len(text)} chars checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
