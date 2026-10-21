"""Host conformance probe — what a THIRD-PARTY host relies on, checked over the wire.

The MCP round-trip probe answers "does the server work". This probe answers a
different question: "can a host we do not control mount this server and drive
it safely". A host decides four things from metadata alone, before any call:

  1. protocol  - can I speak to it (version negotiation)
  2. tools     - what can I call, and what arguments does each need
  3. hints     - must I confirm before calling, and is a retry safe
     (readOnlyHint / destructiveHint / idempotentHint / openWorldHint)
  4. apps      - is there a UI resource I can render inline

Every one of those is asserted here against an expectation table that lives in
THIS file, not in the server. If a hint drifts from behaviour, this probe turns
red instead of the host silently confirming the wrong things.

Usage
    python tools/host_conformance.py                  # spawn a local server
    python tools/host_conformance.py --url https://.../mcp   # against a live host

Prints HOST_CONFORMANCE_OK (exit 0) or HOST_CONFORMANCE_FAILED:<n> failures.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PROTOCOL = "2025-11-25"
UI_URI = "ui://spendlatch/approval-card"
MCP_APP_MIME = "text/html;profile=mcp-app"

# --- the expectation table (host's point of view, independent of the server) --

EXPECTED_TOOLS = {
    "spending_overview", "detect_anomalies", "simulate_saving", "set_budget",
    "budget_status", "list_subscriptions", "unit_economics", "proactive_briefing",
    "decision_ledger", "propose_action", "approve_action", "execute_action",
    "mandate_status",
}

READ_ONLY = {
    "spending_overview", "simulate_saving", "budget_status", "list_subscriptions",
    "unit_economics", "decision_ledger", "mandate_status",
}

# A host must confirm before these: one authorizes a consequential action, the
# other performs it. Everything else may run without a confirmation prompt.
DESTRUCTIVE = {"approve_action", "execute_action"}

# Retrying these is not free: a second call sees a different world.
NOT_IDEMPOTENT = {
    "detect_anomalies", "proactive_briefing", "propose_action",
    "approve_action", "execute_action",
}

REQUIRED_ARGS = {
    "propose_action": "action_id",
    "approve_action": "proposal_id",
    "execute_action": "mandate_id",
}

# The claim "the tool exposes no credential parameter at all" is only true if
# no tool accepts one. A host that saw such a parameter would be right to
# distrust the whole boundary.
CREDENTIAL_KEYS = {"token", "session_token", "approver", "approved_by", "password",
                   "api_key", "secret", "mandate_secret", "credential"}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_ready(port: int, proc: subprocess.Popen, err_path: Path,
                timeout: float = 25.0) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if proc.poll() is not None:
            tail = ""
            try:
                tail = err_path.read_bytes().decode("utf-8", "replace")[-2000:]
            except OSError:
                pass
            raise RuntimeError(f"server exited early ({proc.returncode}):\n{tail}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return time.monotonic() - start
        except OSError:
            time.sleep(0.25)
    raise TimeoutError(f"server did not listen on {port} within {timeout}s")


class Checks:
    """Collect every failure instead of dying on the first one."""

    def __init__(self, log) -> None:
        self.log = log
        self.failures: list[str] = []

    def ok(self, cond: bool, msg: str) -> bool:
        if cond:
            return True
        self.failures.append(msg)
        self.log(f"      FAIL  {msg}")
        return False

    def note(self, msg: str) -> None:
        self.log(f"      {msg}")


async def _probe(url: str, checks: Checks) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            checks.note(f"server: {init.serverInfo.name} {init.serverInfo.version}")
            checks.ok(init.protocolVersion == EXPECTED_PROTOCOL,
                      f"protocol {init.protocolVersion} != {EXPECTED_PROTOCOL}")
            caps = init.capabilities
            checks.ok(caps.tools is not None, "server declares no tools capability")
            checks.ok(caps.resources is not None,
                      "server declares no resources capability (MCP Apps cannot render)")
            checks.note(f"protocol {init.protocolVersion}; tools={bool(caps.tools)} "
                        f"resources={bool(caps.resources)}")

            listed = await session.list_tools()
            by_name = {t.name: t for t in listed.tools}
            names = set(by_name)
            checks.ok(names == EXPECTED_TOOLS,
                      f"tool set mismatch: missing={EXPECTED_TOOLS - names} "
                      f"extra={names - EXPECTED_TOOLS}")
            checks.note(f"{len(names)} tools")

            # ---- hints: the part a host actually branches on ----
            for name in sorted(names & EXPECTED_TOOLS):
                tool = by_name[name]
                ann = tool.annotations
                if not checks.ok(ann is not None, f"{name}: no annotations at all"):
                    continue
                want_ro = name in READ_ONLY
                want_destr = name in DESTRUCTIVE
                want_idem = name not in NOT_IDEMPOTENT
                checks.ok(ann.readOnlyHint is not None,
                          f"{name}: readOnlyHint unset (host cannot tell read from write)")
                checks.ok(ann.readOnlyHint is want_ro,
                          f"{name}: readOnlyHint={ann.readOnlyHint}, behaviour says {want_ro}")
                checks.ok(ann.destructiveHint is want_destr,
                          f"{name}: destructiveHint={ann.destructiveHint}, expected {want_destr}")
                checks.ok(ann.idempotentHint is want_idem,
                          f"{name}: idempotentHint={ann.idempotentHint}, expected {want_idem}")
                checks.ok(ann.openWorldHint is False,
                          f"{name}: openWorldHint={ann.openWorldHint}; every adapter is simulated")
                checks.ok(bool(tool.description and tool.description.strip()),
                          f"{name}: empty description (a host shows this to the user)")

            # ---- argument contracts ----
            for name, arg in REQUIRED_ARGS.items():
                schema = (by_name[name].inputSchema or {}) if name in by_name else {}
                required = set(schema.get("required") or [])
                checks.ok(arg in required,
                          f"{name}: '{arg}' is not a required argument ({sorted(required)})")

            # ---- no tool accepts a credential ----
            for name, tool in by_name.items():
                props = set(((tool.inputSchema or {}).get("properties") or {}))
                leaked = props & CREDENTIAL_KEYS
                checks.ok(not leaked,
                          f"{name}: accepts credential-shaped argument(s) {sorted(leaked)}")

            # ---- MCP Apps resource ----
            resources = await session.list_resources()
            uris = {str(r.uri) for r in resources.resources}
            checks.ok(UI_URI in uris, f"{UI_URI} not listed; got {sorted(uris)}")
            if UI_URI in uris:
                card = next(r for r in resources.resources if str(r.uri) == UI_URI)
                checks.ok(card.mimeType == MCP_APP_MIME,
                          f"card mime {card.mimeType!r} != {MCP_APP_MIME!r}")
                read = await session.read_resource(UI_URI)
                html = "".join(getattr(c, "text", "") for c in read.contents)
                checks.ok("ui/notifications/tool-input" in html,
                          "card does not subscribe to tool-input (host cannot pass arguments)")
                checks.ok('"tools/call"' in html or "'tools/call'" in html,
                          "card cannot call tools back over the bridge")
                checks.ok(len(html) > 2000, f"card HTML suspiciously small ({len(html)} chars)")
                meta_ui = (by_name.get("propose_action").meta or {}).get("ui", {})
                checks.ok(meta_ui.get("resourceUri") == UI_URI,
                          f"propose_action does not link the card: {meta_ui}")
                checks.note(f"card: {len(html)} chars, mcp-app profile, bridge present")

            # ---- refusals must be renderable, not crashes ----
            async def call(name: str, args: dict):
                try:
                    return await session.call_tool(name, args)
                except Exception as exc:  # a host sees this as a transport failure
                    checks.failures.append(f"{name} raised over the wire: {type(exc).__name__}")
                    checks.log(f"      FAIL  {name} raised {type(exc).__name__}")
                    return None

            overview = await call("spending_overview", {})
            if overview is not None:
                checks.ok(not overview.isError, "spending_overview returned isError")
                checks.ok(bool(overview.structuredContent or overview.content),
                          "spending_overview returned no renderable content")

            approve = await call("approve_action", {"proposal_id": "p-00000000"})
            if approve is not None:
                text = " ".join(c.text for c in approve.content if hasattr(c, "text")).lower()
                checks.ok("approval" in text and ("web" in text or "session" in text),
                          f"approve_action refusal does not explain the web-session rule: {text[:120]}")
                checks.ok(not approve.isError,
                          "approve_action surfaced as a protocol error; a host renders refusals")

            execute = await call("execute_action", {"mandate_id": "m-doesnotexist"})
            if execute is not None:
                checks.ok(not execute.isError,
                          "execute_action surfaced a bogus mandate as a protocol error")
                text = " ".join(c.text for c in execute.content if hasattr(c, "text")).lower()
                checks.ok("refus" in text or "unknown" in text or "no such" in text
                          or "error" in text,
                          f"bogus mandate was not clearly refused: {text[:120]}")
            checks.note("refusals render as content (a host can show them), not transport errors")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None,
                    help="live MCP endpoint; default spawns a local server")
    args = ap.parse_args()
    log = print
    checks = Checks(log)

    log("host conformance: what a third-party host can rely on")

    if args.url:
        log(f"[1/1] against live endpoint {args.url}")
        asyncio.run(_probe(args.url, checks))
    else:
        port = _free_port()
        tmp = Path(tempfile.mkdtemp(prefix="spendlatch-hostconf-"))
        try:
            env = {**os.environ, "SPENDLATCH_PORT": str(port),
                   "SPENDLATCH_STATE": str(tmp / "state.json")}
            err_path = tmp / "server-stderr.log"
            log(f"[1/1] spawning server on 127.0.0.1:{port} (isolated state)")
            with open(err_path, "w+b") as err_file:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "mcp_server.server"],
                    cwd=ROOT, env=env,
                    stdout=subprocess.DEVNULL, stderr=err_file,
                )
                try:
                    checks.note(f"ready in {_wait_ready(port, proc, err_path):.1f}s")
                    asyncio.run(_probe(f"http://127.0.0.1:{port}/mcp", checks))
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
        finally:
            for _ in range(50):
                try:
                    shutil.rmtree(tmp)
                    break
                except PermissionError:
                    time.sleep(0.2)

    if checks.failures:
        log(f"HOST_CONFORMANCE_FAILED:{len(checks.failures)} checks")
        return 1
    log("HOST_CONFORMANCE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
