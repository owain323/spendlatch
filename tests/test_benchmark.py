"""Tests for the sealed two-phase benchmark harness."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks"


def _run_benchmark() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BENCH / "run.py")],
        capture_output=True, text=True, cwd=ROOT,
    )


class TestBenchmarkIntegrity:
    def test_cases_and_gold_cover_each_other(self):
        cases = json.loads((BENCH / "cases.json").read_text(encoding="utf-8"))["cases"]
        gold = json.loads((BENCH / "gold" / "labels.json").read_text(encoding="utf-8"))
        case_ids = {c["id"] for c in cases}
        assert case_ids == set(gold), "every case needs a gold label and vice versa"

    def test_benchmark_passes(self):
        result = _run_benchmark()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "BENCHMARK_OK" in result.stdout

    def test_metrics_file_matches_claims(self):
        _run_benchmark()
        metrics = json.loads((BENCH / "results" / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["cases"] == 12
        assert metrics["flag_precision"] == 1.0
        assert metrics["flag_recall"] == 1.0
        assert metrics["keep_accuracy"] == 1.0
        assert metrics["hold_accuracy"] == 1.0
        assert metrics["cases_fully_correct"] == 12

    def test_predictions_sealed_before_scoring(self):
        """Two-phase protocol: predictions.json must exist as a sealed artifact
        and contain one prediction per case."""
        _run_benchmark()
        predictions = json.loads((BENCH / "results" / "predictions.json").read_text(encoding="utf-8"))
        assert len(predictions) == 12
        for pred in predictions:
            assert set(pred) >= {"case_id", "flag", "keep", "hold"}

    def test_benchmark_detects_regression(self, tmp_path, monkeypatch):
        """Negative control: if detection breaks, the benchmark MUST go red."""
        import importlib

        from mcp_server import tools

        original = tools.analyze_dataset
        monkeypatch.setattr(tools, "analyze_dataset", lambda providers, months: [])
        try:
            # Inline re-run with the broken analyzer
            cases = json.loads((BENCH / "cases.json").read_text(encoding="utf-8"))
            predictions = []
            for case in cases["cases"]:
                findings = tools.analyze_dataset(case["providers"], cases["months"])
                predictions.append({"case_id": case["id"],
                                    "flag": sorted(f["id"] for f in findings if f["verdict"] == "flag")})
            gold = json.loads((BENCH / "gold" / "labels.json").read_text(encoding="utf-8"))
            fn = sum(len(set(gold[p["case_id"]]["flag"]) - set(p["flag"])) for p in predictions)
            assert fn > 0, "broken analyzer must produce false negatives"
        finally:
            importlib.reload(tools)
