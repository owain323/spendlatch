"""Quality gate: tests, sealed benchmarks (all three tiers), repo integrity,
evidence freshness, submission copy, and the mutation check.

Usage:  python run_checks.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def run(step: str, argv: list[str]) -> bool:
    print(f"== {step} ==")
    return subprocess.run(argv, cwd=ROOT).returncode == 0


def main() -> int:
    # Byte-compile everything first: a syntax error in a tool is a broken
    # gate, and a broken gate is worse than no gate because it looks green.
    print("== compile check ==")
    compile_r = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "mcp_server", "agent", "tools", "tests",
         "benchmarks", "run_checks.py"],
        cwd=ROOT, capture_output=True, text=True)
    if compile_r.returncode != 0:
        print(compile_r.stdout[-2000:])
        print(compile_r.stderr[-2000:])
        print("GATE FAILED at: compile check")
        return 1

    steps = [
        ("pytest", [sys.executable, "-m", "pytest", "tests", "-q", "--ignore=tests/test_mcp_roundtrip.py"]),
        ("sealed benchmark", [sys.executable, "benchmarks/run.py"]),
        ("MCP roundtrip over the wire", [sys.executable, "tools/mcp_roundtrip.py"]),
        # The other two benchmark tiers were previously quoted in the README
        # and in the submission copy but never re-run by any gate: a
        # regression there stayed green. They are cheap (~1s each) and
        # `benchmarks/derived/` is gitignored, so it is generated first.
        ("derived suite (generate)", [sys.executable, "tools/make_derived.py"]),
        ("sealed benchmark — derived 24", [sys.executable, "benchmarks/run.py", "--derived"]),
        ("sealed benchmark — independent 14", [sys.executable, "benchmarks/run.py", "--independent"]),
        ("integrity manifest", [sys.executable, "tools/make_sha256sums.py", "--check"]),
        ("evidence freshness", [sys.executable, "tools/check_evidence_freshness.py"]),
        ("test count", [sys.executable, "tools/check_test_count.py"]),
        ("submission copy", [sys.executable, "tools/check_submission.py"]),
        # Last, because it is the slowest (~50s): it copies the repo, disables
        # one guard at a time in the copy, and requires the covering tests to
        # go red. A guard nobody covers is a guard that is not there.
        ("mutation check", [sys.executable, "tools/mutation_check.py"]),
    ]
    for step, argv in steps:
        if not run(step, argv):
            print(f"GATE FAILED at: {step}")
            return 1
    print("ALL GATES GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
