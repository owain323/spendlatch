"""Analyze a real WorkBuddy usage export (daily x model aggregate).

Input CSV columns: date,model,calls,credits
  - date      YYYY-MM-DD
  - model     anonymized model id (the export hides vendor names)
  - calls     request count that day for that model
  - credits   platform credits consumed (NOT currency)

What it reports, per model, over the whole window:
  - monthly credits and calls
  - credits-per-call month over month drift
  - the largest single month-over-month credit jump, with the two months

This is deliberately the same shape as the demo's cost-per-task canary: the
unit is credits-per-call instead of dollars-per-task, because that is what a
real export contains. No currency conversion is invented anywhere.

Usage:  python tools/analyze_usage.py path/to/usage.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


def load(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append({"date": r["date"].strip(), "model": r["model"].strip(),
                         "calls": int(float(r["calls"])),
                         "credits": float(r["credits"])})
    return rows


def month_of(date: str) -> str:
    return date[:7]


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    rows = load(path)
    months = sorted({month_of(r["date"]) for r in rows})
    days = sorted({r["date"] for r in rows})
    total_calls = sum(r["calls"] for r in rows)
    total_credits = sum(r["credits"] for r in rows)
    print(f"rows={len(rows)} days={len(days)} months={len(months)} "
          f"({months[0]} .. {months[-1]}) calls={total_calls} credits={total_credits:.2f}")

    per_model_month: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"calls": 0, "credits": 0.0}))
    for r in rows:
        m = per_model_month[r["model"]][month_of(r["date"])]
        m["calls"] += r["calls"]
        m["credits"] += r["credits"]

    findings = []
    for model, by_month in sorted(per_model_month.items()):
        seq = [m for m in months if m in by_month and by_month[m]["calls"] > 0]
        if len(seq) < 3:
            continue
        per_call = {m: by_month[m]["credits"] / by_month[m]["calls"] for m in seq}
        worst = None
        for prev, cur in zip(seq, seq[1:]):
            if per_call[prev] <= 0:      # a zero-credit month is not a baseline
                continue
            drift = (per_call[cur] - per_call[prev]) / per_call[prev] * 100
            if worst is None or drift > worst[0]:
                worst = (drift, prev, cur, per_call[prev], per_call[cur])
        if worst is None:            # no usable baseline anywhere in the window
            continue
        credits_jump = None
        for prev, cur in zip(seq, seq[1:]):
            if by_month[prev]["credits"] > 0:
                j = (by_month[cur]["credits"] - by_month[prev]["credits"]) / by_month[prev]["credits"] * 100
                if credits_jump is None or j > credits_jump[0]:
                    credits_jump = (j, prev, cur)
        findings.append({
            "model": model, "months": len(seq),
            "credits_per_call": round(per_call[seq[-1]], 4),
            "worst_drift_pct": round(worst[0], 1), "drift_window": f"{worst[1]}..{worst[2]}",
            "biggest_credit_jump_pct": round(credits_jump[0], 1),
            "jump_window": f"{credits_jump[1]}..{credits_jump[2]}",
        })

    findings = [f for f in findings if f["worst_drift_pct"] == f["worst_drift_pct"]]
    findings.sort(key=lambda f: f["worst_drift_pct"], reverse=True)
    print("\nper-model (worst credits-per-call drift, months present):")
    for f in findings:
        print(f"  {f['model']:>10}  months={f['months']:>2}  "
              f"credits/call={f['credits_per_call']:<8} "
              f"drift={f['worst_drift_pct']:>6}% ({f['drift_window']})  "
              f"biggest credit jump={f['biggest_credit_jump_pct']:>6}% ({f['jump_window']})")

    top = findings[0] if findings else None
    if top:
        print(f"\nfinding: {top['model']} credits-per-call rose {top['worst_drift_pct']}% "
              f"across {top['drift_window']} (real export, no synthetic input)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
