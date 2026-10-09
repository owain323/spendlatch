"""SL-001: the MCP -> Web -> MCP loop, in the REAL production topology.

Two separate server processes, a shared data root, and deliberately NO
SPENDLATCH_STATE single-file shortcut: the per-workspace file mode is the
configuration the product ships in, and the loop the core claim depends on
must be tested exactly there.

SL-001 finding (2026-10-09, see docs/evidence/cross-surface.txt): the loop
does NOT close - proposals minted by the MCP surface land in its workspace
and are invisible to web approval sessions ("I don't have an open proposal
p-..."). This test pins the two properties that hold today:

  1. isolation: a second web session can neither see nor approve another
     workspace's proposal (the security property, asserted for real);
  2. the documented verdict is CROSS_SURFACE_BROKEN:approval - recorded so
     the breakage cannot silently regress further or silently disappear.

When SL-002 (approval handoff) lands, the expected verdict flips to
CROSS_SURFACE_OK and the assertion below is updated WITH the fix in the
same commit - not before, not by relaxing this test.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_probe() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cross_surface_probe.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=180,
    )


def test_cross_surface_isolation_holds_and_verdict_matches_documented_state():
    result = _run_probe()
    assert "ISOLATION_OK" in result.stdout, result.stdout + result.stderr
    # The documented SL-001 finding: the loop is open at the approval step.
    # This assertion is the pin; SL-002 flips it together with the fix.
    assert "CROSS_SURFACE_BROKEN:approval" in result.stdout, (
        "the cross-surface verdict changed without the documentation moving: "
        + result.stdout[-400:])


def test_cross_surface_steps_are_auditable():
    result = _run_probe()
    for step in ("[1/5]", "[2/5]", "[3/5]", "[5/5]"):
        assert step in result.stdout, f"missing probe step {step}"
    assert "proposal_id = p-" in result.stdout
