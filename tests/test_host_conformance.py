"""Host conformance, pinned inside pytest.

These two tests are deliberately thin: the probe itself prints the verdict and
the failure list, and it is what a reviewer runs by hand. The tests exist so
the *gate* fails when host-facing metadata drifts - an annotation that stops
matching behaviour is a safety regression a host cannot see.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_probe() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "host_conformance.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=180,
    )


def test_a_third_party_host_can_rely_on_the_metadata():
    result = _run_probe()
    assert "HOST_CONFORMANCE_OK" in result.stdout, (
        "host conformance failed:\n" + result.stdout[-2000:] + result.stderr[-800:])


def test_every_tool_carries_safety_hints():
    """A tool without annotations is invisible to a host's confirmation logic."""
    result = _run_probe()
    assert "FAIL" not in result.stdout, result.stdout[-2000:]
    assert "13 tools" in result.stdout
