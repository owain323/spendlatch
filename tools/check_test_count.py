"""One authoritative test count, and the docs must agree with it.

A number that only a human can keep in sync is a number that will be
wrong. This collects the suite the way CI runs it, writes the result to
docs/evidence/test-count.txt, and fails if any document quotes a different
number.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "test-count.txt"
# Documents that quote the count, and the phrasing they use.
DOCS = ["README.md", "docs/CLAIMS.md", "docs/EVIDENCE.md", "CONTRIBUTING.md"]


def collect() -> int:
    """Count the suite the way CI counts it: the wire roundtrip included."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "--collect-only"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    m = re.search(r"(\d+) tests? collected", r.stdout)
    if not m:
        # pytest omits the word "tests" for a single test
        m = re.search(r"(\d+) test collected", r.stdout)
    if not m:
        print(r.stdout[-500:])
        raise SystemExit("could not read the collected test count from pytest")
    return int(m.group(1))


def main() -> int:
    count = collect()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    # This file is written whole, on every run, by design: the number and the
    # notes explaining it move together. A gate that rewrites half a file
    # silently deletes the other half, and the next reader is left guessing.
    EVIDENCE.write_text(
        f"{count}\n\n"
        f"Collected by tools/check_test_count.py: pytest --collect-only over\n"
        f"tests/ with no exclusions. This is the only test count the docs may\n"
        f"quote, and this gate fails if any of them drifts.\n\n"
        f"Two numbers are correct, and you may meet either one. This file is the\n"
        f"whole suite. `run_checks.py` prints a smaller number in its pytest step\n"
        f"because it excludes tests/test_mcp_roundtrip.py: that one spawns a real\n"
        f"server subprocess, so it is covered by the separate `MCP roundtrip` step\n"
        f"instead of running twice. Nothing is missing from either.\n",
        encoding="utf-8", newline="\n",
    )

    bad: list[str] = []
    # Only phrases that claim the TOTAL. "22 mocked tests" describes a subset
    # and must not be dragged into the comparison.
    total_claim = re.compile(
        r"\b(\d{2,4})\s+(?:pytest\s+)?(?:automated\s+)?tests\b(?!\s+in\b)"
    )
    subset = re.compile(r"(\d{2,4})\s+(?:pytest\s+)?automated\s+tests?\s+pass")
    for rel in DOCS:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        claims = set(total_claim.findall(text)) | set(subset.findall(text))
        for quoted in sorted(claims):
            if quoted != str(count):
                bad.append(f"{rel}: quotes {quoted}, the suite has {count}")

    if bad:
        print(f"test count drift — docs/evidence/test-count.txt says {count}:")
        for item in bad:
            print(f"  - {item}")
        print("\nUpdate the quote, or update the suite and re-run this check.")
        return 1
    print(f"test count consistent: {count} (docs/evidence/test-count.txt)")
    # Say the quiet part out loud. This gate runs 8 tests fewer than the
    # headline number, and anyone who notices that gap and is not told the
    # reason will conclude the project cannot add up.
    print(f"  the {count} above is the whole suite; the pytest step inside "
          f"run_checks prints fewer because it skips")
    print("  tests/test_mcp_roundtrip.py, which spawns a real server and is "
          "covered by the separate")
    print("  MCP roundtrip step instead. Both numbers are correct, and "
          "docs/evidence/test-count.txt says so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
