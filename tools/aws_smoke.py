"""AWS live smoke — one real Bedrock call through the production code path.

Three states, and they are never merged (see docs/EVIDENCE.md and the
three-state discipline in CONTRIBUTING.md):

  OK          Bedrock answered and the answer parsed into a SpendIntent — or
              the model cleanly ABSTAINed, which is still a completed
              roundtrip against a real endpoint, not a failure.
  UNAVAILABLE no credentials, unreachable endpoint, or any exception. NO
              conclusion about Bedrock was reached. Exit 3.

`docs/evidence/aws-live.txt` is written on OK only. A run that does not
reach Bedrock never leaves an artifact behind that could be read as proof.

Why this calls a private function: `planner.plan()` deliberately swallows
every exception and returns None so that a planner outage degrades to the
deterministic router instead of breaking the product. That is correct for
production and useless for a smoke test, which must be able to tell "the
model answered no" apart from "we never reached the model".

Usage:
    pip install -e ".[llm]"
    export AWS_REGION=ap-northeast-1
    export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
    export SPENDLATCH_LLM=bedrock
    python tools/aws_smoke.py                # writes docs/evidence/aws-live.txt
    python tools/aws_smoke.py --check        # no write; exit 0 (OK) or 3 (UNAVAILABLE)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs" / "evidence" / "aws-live.txt"

PROMPT = "buy 200 dollars of API credits for the eval pipeline"

EXIT_OK = 0
EXIT_UNAVAILABLE = 3


def _redacted_env() -> dict:
    """What we report about the environment — never the secrets themselves."""
    keys = ("AWS_REGION", "AWS_DEFAULT_REGION", "SPENDLATCH_BEDROCK_MODEL",
            "SPENDLATCH_LLM", "AWS_PROFILE")
    present = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
    out = {k: os.environ.get(k) or "(unset)" for k in keys}
    out["credentials"] = ", ".join(
        f"{k}={'set' if os.environ.get(k) else 'MISSING'}" for k in present)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="do not write the evidence artifact")
    args = ap.parse_args()

    # This tool imports the package it tests; run as `python tools/aws_smoke.py`,
    # so the repo root is not on sys.path yet.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from mcp_server import planner  # noqa: PLC0415 - after env is read

    env = _redacted_env()
    region = env["AWS_REGION"]
    model = planner.MODEL_ID
    started = time.monotonic()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # --- reach the model -------------------------------------------------
    try:
        raw = planner._strands_complete(PROMPT)
    except Exception as exc:  # noqa: BLE001 - the classification IS the point
        elapsed = time.monotonic() - started
        print("AWS SMOKE: UNAVAILABLE")
        print(f"  model      {model}")
        print(f"  region     {region}")
        print(f"  credentials {env['credentials']}")
        print(f"  elapsed    {elapsed:.2f}s")
        print(f"  exception  {type(exc).__name__}: {exc}")
        print()
        print("  No conclusion about Bedrock was reached. This is NOT the same as")
        print("  'Bedrock said no'. Nothing was written to docs/evidence/.")
        return EXIT_UNAVAILABLE

    elapsed = time.monotonic() - started
    intent = planner.parse_intent(raw)
    verdict = "OK" if intent else "OK (model abstained — roundtrip completed)"

    lines = [
        f"# AWS live smoke {stamp}",
        f"# generator: tools/aws_smoke.py (real Bedrock call via Strands; billed)",
        f"",
        f"region      {region}",
        f"model       {model}",
        f"prompt      {PROMPT}",
        f"elapsed     {elapsed:.2f}s",
        f"verdict     {verdict}",
        f"",
        f"raw response (first 600 chars):",
        f"{(raw or '')[:600]}",
        f"",
        f"parsed SpendIntent:",
    ]
    lines.append(f"  {intent.as_dict()}" if intent else "  None — strict parse declined the "
                                                      "output; the product falls back to the "
                                                      "deterministic router.")
    lines += [
        f"",
        f"boundary: the planner produced data only. It minted no proposal and no",
        f"          mandate; new spend is default-deny in actions.evaluate_spend_intent.",
        f"",
        f"credentials were never printed by this script.",
    ]

    print("AWS SMOKE: " + verdict)
    print(f"  model   {model}")
    print(f"  region  {region}")
    print(f"  elapsed {elapsed:.2f}s")
    if intent:
        print(f"  intent  {intent.as_dict()}")

    if not args.check:
        EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"  wrote   {EVIDENCE.relative_to(ROOT)}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
