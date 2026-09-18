"""Tests for the decision ledger (observability surface)."""

from __future__ import annotations

import pytest

from mcp_server import ledger


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDPILOT_STATE", str(tmp_path / "state.json"))


class TestRecord:
    def test_appends_with_seq_and_timestamp(self):
        entry = ledger.record("alert", "AWS", "spike detected")
        assert entry["seq"] == 1
        assert entry["kind"] == "alert"
        assert entry["subject"] == "AWS"
        assert entry["ts"]
        assert entry["evidence"] == []

    def test_seq_increments(self):
        ledger.record("alert", "A", "r1")
        second = ledger.record("hold", "B", "r2")
        assert second["seq"] == 2

    def test_bounded_growth(self):
        for i in range(ledger.MAX_ENTRIES + 50):
            ledger.record("alert", f"s{i}", "r")
        entries = ledger.entries()
        assert len(entries) == ledger.MAX_ENTRIES
        assert entries[-1]["subject"] == f"s{ledger.MAX_ENTRIES + 49}"

    def test_filter_by_kinds(self):
        ledger.record("alert", "A", "r")
        ledger.record("hold", "B", "r")
        only_holds = ledger.entries(kinds={"hold"})
        assert [e["subject"] for e in only_holds] == ["B"]


class TestSuppression:
    def test_mark_and_check_fired(self):
        assert ledger.has_fired("spike-aws", "2026-08") is False
        ledger.mark_fired("spike-aws", "2026-08")
        assert ledger.has_fired("spike-aws", "2026-08") is True

    def test_fired_is_scoped_to_month(self):
        ledger.mark_fired("spike-aws", "2026-08")
        assert ledger.has_fired("spike-aws", "2026-09") is False


class TestChallenge:
    def test_challenge_records_and_logs(self):
        entry = ledger.record("hold", "Figma", "low confidence")
        record = ledger.challenge(entry["seq"], "show me anyway")
        assert record["subject"] == "Figma"
        assert "Figma" in ledger.challenged_subjects()
        kinds = [e["kind"] for e in ledger.entries()]
        assert "challenge" in kinds

    def test_challenge_unknown_seq_raises(self):
        with pytest.raises(KeyError):
            ledger.challenge(9999, "nothing there")
