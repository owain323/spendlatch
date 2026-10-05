"""Mutation check: a guard is only real if removing it turns a test red.

A boundary test can pass for the wrong reason — an earlier check refuses
first, so the assertion is satisfied without the guard ever running. The
only way to know is to break the guard on purpose and watch the suite fail.

This tool copies the repository to a temporary directory, disables one guard
at a time THERE, and runs the tests that claim to cover it. The working tree
is never modified: a crash, a Ctrl-C or a failing mutation cannot leave a
disabled guard behind in the source.

    python tools/mutation_check.py            # every mutation
    python tools/mutation_check.py --verbose  # keep pytest output

Exit 0 = every mutant was killed. Exit 1 = a test is decorative.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (id, file, anchor regex, replacement, tests that must go red)
MUTATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "scope-binding",
        "mcp_server/actions.py",
        r'    if adapter_name != mandate\["scope"\]\["provider"\] or operation != mandate\["scope"\]\["operation"\]:',
        "    if False:",
        ["tests/test_boundaries.py::test_swapped_adapter_cannot_run_under_a_valid_signature"],
    ),
    (
        "consent-check",
        "agent/brain.py",
        r'    if re\.search\(_D \+ r"approve',
        '    if False and re.search(_D + r"approve',
        ["tests/test_boundaries.py::test_refusal_shaped_utterance_never_signs"],
    ),
    (
        "spend-deny-gate",
        "agent/brain.py",
        r"    if _spend and _amt and not planner\.enabled\(\):",
        "    if False:",
        ["tests/test_boundaries.py::test_new_spend_is_denied_and_logged"],
    ),
    (
        "consumption-claim",
        "mcp_server/actions.py",
        r'    claim = state\["consumed"\]\.get\(mandate_id\)\n    if claim:',
        "    claim = None\n    if claim:",
        [
            "tests/test_boundaries.py::test_rollback_of_status_does_not_allow_a_second_execution",
            "tests/test_boundaries.py::test_consumption_survives_ledger_trimming",
        ],
    ),
    (
        "proof-receipt-lookup",
        "tools/verify_proof.py",
        r'        matching = \[r for r in state\["receipts"\] if r\.get\("mandate_id"\) == mandate_id\]',
        '        matching = state["receipts"][-1:]',
        ["tests/test_boundaries.py::test_old_proof_bundle_still_verifies_after_later_actions"],
    ),
    (
        "cap-drift-check",
        "mcp_server/actions.py",
        r"    if proof\[\"monthly_before\"\] > cap \+ 1e-9:",
        "    if False:",
        ["tests/test_boundaries.py::test_bill_above_the_approved_cap_is_refused"],
    ),
    (
        "signature-check",
        "mcp_server/actions.py",
        r"    if not hmac\.compare_digest\(_sign\(payload, secret\), mandate\[\"signature\"\]\):",
        "    if False:",
        ["tests/test_actions.py::TestForgery"],
    ),
    (
        "expiry-check",
        "mcp_server/actions.py",
        r'    if _now\(\) > datetime\.fromisoformat\(mandate\["expires_at"\]\):',
        "    if False:",
        ["tests/test_actions.py::TestExpiry"],
    ),
    (
        "proof-drift-check",
        "mcp_server/actions.py",
        r"    if current_hash != mandate\[\"proof_hash\"\]:",
        "    if False:",
        ["tests/test_actions.py"],
    ),
    (
        # T7: the MCP tool calls approve with no token, so this guard is what
        # makes it refuse. Removing it lets the MCP surface approve anything.
        "mcp-surface-refusal",
        "mcp_server/actions.py",
        r"    if not store\.token_is_authenticated\(session_token\):",
        "    if False:",
        ["tests/test_actions.py::TestAuthorizationBoundary::test_mcp_surface_tool_refuses_and_cannot_be_given_a_token"],
    ),
]


def sandbox() -> Path:
    """A disposable copy of the repo. The working tree stays untouched."""
    tmp = Path(tempfile.mkdtemp(prefix="spendlatch-mutation-"))
    dst = tmp / "repo"
    shutil.copytree(
        ROOT, dst,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache", "build"),
    )
    return dst


def apply(path: Path, pattern: str, replacement: str) -> bool:
    src = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, replacement, src, count=1)
    if n == 0:
        return False
    path.write_text(new, encoding="utf-8", newline="\n")
    return True


def run_tests(repo: Path, targets: list[str], verbose: bool) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(repo),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=900,
    )
    killed = r.returncode != 0
    if verbose or not killed:
        return killed, (r.stdout or "")[-800:]
    return killed, ""


def main() -> int:
    verbose = "--verbose" in sys.argv
    repo = sandbox()
    print(f"sandbox: {repo}\n(working tree untouched — every mutation lands in the copy)\n")

    # Baseline: a test that already fails proves nothing about a guard. If the
    # unmutated suite is red, say so instead of reporting a false survivor.
    # run_tests returns "killed" (i.e. the tests went red), so a healthy
    # baseline is the case where nothing was killed.
    all_tests = sorted({t for _, _, _, _, tests in MUTATIONS for t in tests})
    baseline_failed, baseline_out = run_tests(repo, all_tests, verbose)
    if baseline_failed:
        print("BASELINE RED: these tests fail before any mutation is applied.")
        print("A guard cannot be judged while the suite is broken. Fix the suite first.")
        print("\n" + baseline_out[-1500:])
        shutil.rmtree(repo.parent, ignore_errors=True)
        return 1
    print("baseline green — the suite passes before any mutation\n")

    survivors: list[str] = []
    not_applied: list[str] = []
    try:
        for mut_id, rel, pattern, replacement, tests in MUTATIONS:
            target = repo / rel
            if not target.exists():
                not_applied.append(f"{mut_id} ({rel} missing)")
                print(f"  SKIP  {mut_id}: {rel} not found")
                continue
            if not apply(target, pattern, replacement):
                not_applied.append(f"{mut_id} (pattern no longer matches {rel})")
                print(f"  SKIP  {mut_id}: pattern not found in {rel}")
                continue
            killed, out = run_tests(repo, tests, verbose)
            if killed:
                print(f"  KILL  {mut_id}: the tests went red without the guard")
            else:
                print(f"  LIVE  {mut_id}: tests still passed — the guard is unproven")
                if out:
                    print("        " + out.replace("\n", "\n        ")[:700])
                survivors.append(mut_id)
    finally:
        shutil.rmtree(repo.parent, ignore_errors=True)

    print()
    if not_applied:
        print(f"{len(not_applied)} mutation(s) could not be applied (the code moved):")
        for item in not_applied:
            print(f"  - {item}")
        print("\nAn unapplicable mutation is a silent hole in the check, not a pass.")
        return 1
    if survivors:
        print(f"DECORATIVE: {len(survivors)} test(s) pass without the guard:")
        for item in survivors:
            print(f"  - {item}")
        print("\nA test that passes when the guard is removed does not prove the guard.")
        return 1
    print(f"All {len(MUTATIONS)} mutants killed: every guard in this set is covered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
