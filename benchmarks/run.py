"""Sealed two-phase benchmark for SpendPilot's detection engine.

Phase 1 (agent-visible): only case inputs are opened. The analysis runs and
predictions are SEALED to predictions.json.

Phase 2 (evaluation): gold labels are opened ONLY AFTER predictions are
sealed. There is no way to go back and change an answer.

Usage:  python benchmarks/run.py     # writes results/metrics.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_server import tools  # noqa: E402

BENCH = Path(__file__).resolve().parent
RESULTS = BENCH / "results"


def phase1_predict() -> list[dict]:
    cases = json.loads((BENCH / "cases.json").read_text(encoding="utf-8"))
    predictions = []
    for case in cases["cases"]:
        # Agent-visible phase: only case inputs are opened.
        findings = tools.analyze_dataset(case["providers"], cases["months"])
        predictions.append({
            "case_id": case["id"],
            "flag": sorted(f["id"] for f in findings if f["verdict"] == "flag"),
            "keep": sorted(f["id"] for f in findings if f["verdict"] == "keep"),
            "hold": sorted(f["id"] for f in findings if f["verdict"] == "hold"),
            "confidence": {f["id"]: f.get("confidence") for f in findings},
        })
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "predictions.json").write_text(
        json.dumps(predictions, indent=2), encoding="utf-8")
    return predictions


def phase2_score(predictions: list[dict]) -> dict:
    # Evaluation phase starts only after predictions are sealed.
    gold = json.loads((BENCH / "gold" / "labels.json").read_text(encoding="utf-8"))

    tp = fp = fn = 0
    keep_correct = keep_missed = 0
    hold_correct = hold_missed = 0
    per_case = []
    for pred in predictions:
        g = gold[pred["case_id"]]
        pred_flag, gold_flag = set(pred["flag"]), set(g["flag"])
        tp += len(pred_flag & gold_flag)
        fp += len(pred_flag - gold_flag)
        fn += len(gold_flag - pred_flag)
        keep_ok = set(pred["keep"]) == set(g["keep"])
        hold_ok = set(pred["hold"]) == set(g["hold"])
        keep_correct += keep_ok
        keep_missed += not keep_ok
        hold_correct += hold_ok
        hold_missed += not hold_ok
        per_case.append({
            "case_id": pred["case_id"],
            "flag_ok": pred_flag == gold_flag,
            "keep_ok": keep_ok,
            "hold_ok": hold_ok,
            "extra_flags": sorted(pred_flag - gold_flag),
            "missed_flags": sorted(gold_flag - pred_flag),
        })

    metrics = {
        "cases": len(predictions),
        "flag_precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "flag_recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "flag_tp": tp, "flag_fp": fp, "flag_fn": fn,
        "keep_accuracy": round(keep_correct / len(predictions), 4),
        "hold_accuracy": round(hold_correct / len(predictions), 4),
        "cases_fully_correct": sum(1 for c in per_case if c["flag_ok"] and c["keep_ok"] and c["hold_ok"]),
        "per_case": per_case,
        "basis": "12 synthetic held-out cases with planted ground truth; sealed two-phase protocol",
    }
    (RESULTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> int:
    predictions = phase1_predict()
    metrics = phase2_score(predictions)
    print(f"cases: {metrics['cases']}")
    print(f"flag precision: {metrics['flag_precision']}  recall: {metrics['flag_recall']}")
    print(f"keep accuracy: {metrics['keep_accuracy']}  hold accuracy: {metrics['hold_accuracy']}")
    print(f"cases fully correct: {metrics['cases_fully_correct']}/{metrics['cases']}")
    for case in metrics["per_case"]:
        if not (case["flag_ok"] and case["keep_ok"] and case["hold_ok"]):
            print(f"  MISMATCH {case['case_id']}: extra={case['extra_flags']} missed={case['missed_flags']}")
    ok = metrics["cases_fully_correct"] == metrics["cases"]
    print("BENCHMARK_" + ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
