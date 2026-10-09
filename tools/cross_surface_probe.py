"""Cross-surface probe: MCP proposes -> Web approves -> MCP executes.

This is the SL-001 acceptance probe (work orders, 2026-10-09). It spawns the
MCP server and the Web backend as TWO SEPARATE PROCESSES with a shared
SPENDLATCH_DATA_DIR and NO SPENDLATCH_STATE single-file shortcut - the real
production topology (web on 8201, mcp on 8101, per-workspace files) - and
walks the loop the product's core claim depends on:

  [2/5] MCP client proposes an action over the wire
  [3/5] a Web session tries to approve THAT proposal id
  [4/5] MCP executes the mandate and gets exactly one receipt
  [5/5] a second Web session (another workspace) cannot see any of it

Verdict line (machine-checkable):
  CROSS_SURFACE_OK                  the loop closes across processes
  CROSS_SURFACE_BROKEN:<step>       the loop does not close; <step> is where
                                    (approval | execution)

Isolation is asserted independently: even when the loop is broken, no
second workspace may read or approve the proposal. A broken loop is a
finding, not a crash - the probe always exits 0; the verdict line is the
evidence (docs/evidence/cross-surface.txt).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_ready(port: int, proc: subprocess.Popen, err_path: Path,
                timeout: float = 30.0) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if proc.poll() is not None:
            tail = ""
            try:
                tail = err_path.read_bytes().decode("utf-8", "replace")[-2000:]
            except OSError:
                pass
            raise RuntimeError(f"server exited early ({proc.returncode}); stderr:\n{tail}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return time.monotonic() - start
        except OSError:
            time.sleep(0.25)
    raise TimeoutError(f"no listener on {port} within {timeout}s")


def _web(port: int, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))


def _unwrap(result) -> dict:
    """SDKs that do not emit structuredContent serialize the dict as JSON
    text content - accept both forms (same as tools/mcp_roundtrip.py)."""
    assert not result.isError, "tool call returned isError"
    data = result.structuredContent
    if data is None:
        import json
        assert result.content, "empty result"
        data = json.loads(result.content[0].text)
    assert isinstance(data, dict), f"unexpected result shape: {str(data)[:120]}"
    return data


async def _mcp_propose(url: str) -> str:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "propose_action", {"action_id": "rightsize-ec2"})
            data = _unwrap(result)
            pid = data.get("proposal_id")
            assert pid, f"no proposal_id in propose response: {str(data)[:200]}"
            return pid


async def _mcp_execute(url: str, mandate_id: str) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "execute_action", {"mandate_id": mandate_id})
            return _unwrap(result)


def main() -> int:
    log = print
    mcp_port, web_port = _free_port(), _free_port()
    tmp = Path(tempfile.mkdtemp(prefix="spendlatch-cross-"))
    verdict = "CROSS_SURFACE_BROKEN:unknown"
    procs: list[subprocess.Popen] = []
    try:
        base_env = {**os.environ,
                    "SPENDLATCH_DATA_DIR": str(tmp),
                    "NO_PROXY": "127.0.0.1,localhost",
                    "no_proxy": "127.0.0.1,localhost"}
        env_mcp = {**base_env, "SPENDLATCH_PORT": str(mcp_port)}
        env_web = {**base_env, "SPENDLATCH_WEB_PORT": str(web_port)}
        # deliberately NO SPENDLATCH_STATE: the default per-workspace file
        # topology IS the configuration under test.

        log("[1/5] spawning MCP server and Web backend as separate processes")
        err_mcp = tmp / "mcp-stderr.log"
        err_web = tmp / "web-stderr.log"
        with open(err_mcp, "w+b") as f1, open(err_web, "w+b") as f2:
            p_mcp = subprocess.Popen([sys.executable, "-m", "mcp_server.server"],
                                     cwd=ROOT, env=env_mcp,
                                     stdout=subprocess.DEVNULL, stderr=f1)
            p_web = subprocess.Popen([sys.executable, "-m", "agent.backend"],
                                     cwd=ROOT, env=env_web,
                                     stdout=subprocess.DEVNULL, stderr=f2)
            procs = [p_mcp, p_web]
            _wait_ready(mcp_port, p_mcp, err_mcp)
            _wait_ready(web_port, p_web, err_web)
            log(f"      ready: mcp :{mcp_port}  web :{web_port}  "
                f"(shared data root: {tmp}, no SPENDLATCH_STATE)")

            log("[2/5] MCP client: propose_action over the wire")
            pid = asyncio.run(_mcp_propose(f"http://127.0.0.1:{mcp_port}/mcp"))
            log(f"      proposal_id = {pid}")

            log("[3/5] Web session: approve that exact proposal id")
            tok = _web(web_port, "/api/session", {})["session_token"]
            reply = _web(web_port, "/api/chat",
                         {"message": f"approve {pid}", "session_token": tok})
            mandate_id = None
            for card in reply.get("cards", []):
                if card.get("type") == "mandate":
                    mandate_id = card["mandate_id"]
            if mandate_id:
                log(f"      mandate issued: {mandate_id}")
            else:
                log(f"      NO mandate - web reply: {reply['reply'][:110]}")

            if mandate_id:
                log("[4/5] MCP executes the mandate over the wire")
                ex = asyncio.run(_mcp_execute(
                    f"http://127.0.0.1:{mcp_port}/mcp", mandate_id))
                if ex.get("refused"):
                    log(f"      execute refused: {ex.get('error', '')[:100]}")
                    verdict = "CROSS_SURFACE_BROKEN:execution"
                else:
                    log(f"      receipt: {ex.get('execution_id', '?')}")
                    verdict = "CROSS_SURFACE_OK"
            else:
                verdict = "CROSS_SURFACE_BROKEN:approval"

            log("[5/5] isolation: a second web session must see nothing of it")
            tok2 = _web(web_port, "/api/session", {})["session_token"]
            r2 = _web(web_port, "/api/chat",
                      {"message": f"approve {pid}", "session_token": tok2})
            leak = any(c.get("type") == "mandate" for c in r2.get("cards", []))
            assert not leak, "ISOLATION FAILED: another session approved the proposal"
            log("      ISOLATION_OK (second session issued no mandate)")

            try:
                ledger = _web(web_port, f"/api/ledger?session_token={tok}", {})
                log(f"      web-ledger entries: {len(ledger.get('entries', []))}")
            except Exception as exc:  # informational only - never mask the verdict
                log(f"      web-ledger probe skipped: {type(exc).__name__}")
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for _ in range(50):
            try:
                shutil.rmtree(tmp)
                break
            except PermissionError:
                time.sleep(0.2)
    log(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
