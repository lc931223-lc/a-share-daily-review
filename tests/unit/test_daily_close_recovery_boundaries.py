import json
from datetime import date, datetime

import pytest

from src.daily_close.orchestrator import DailyCloseOrchestrator
from tests.unit.test_daily_close_orchestrator import _schemas, _calendar, _runners, _write_artifact, SHANGHAI


@pytest.mark.parametrize("now,status", [
    (datetime(2026, 9, 6, 16, tzinfo=SHANGHAI), "NON_TRADING_DAY"),
    (datetime(2026, 9, 8, 14, tzinfo=SHANGHAI), "MARKET_NOT_CLOSED"),
])
def test_default_today_never_creates_prior_date_close(tmp_path, now, status):
    _schemas(tmp_path)
    calls = []
    pipeline = DailyCloseOrchestrator(tmp_path, now=lambda: now,
        calendar_loader=lambda _: _calendar(), runners=_runners(tmp_path, calls))
    result = pipeline.run_today()
    assert result[0]["status"] == status
    assert result[0]["date"] == now.date().isoformat()
    assert calls == []


def test_cli_default_routes_to_today(monkeypatch):
    from tools import run_daily_close_pipeline as cli
    class Pipeline:
        def run_today(self, **kwargs):
            return [dict(date="2026-09-06", status="NON_TRADING_DAY", manifest_path="fixture",
                         blockers=[], credential_health={"tushare_token": "AVAILABLE"})]
        def run_latest(self, **kwargs):
            raise AssertionError("default must not use latest")
    monkeypatch.setattr(cli, "DailyCloseOrchestrator", Pipeline)
    assert cli.main([]) == 2


def test_holes_before_latest_existing_context_are_repaired(tmp_path, monkeypatch):
    _schemas(tmp_path)
    for day in (date(2026, 9, 4), date(2026, 9, 8)):
        _write_artifact(tmp_path, "review_context", day)
    pipeline = DailyCloseOrchestrator(tmp_path,
        now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(), runners={"market_packet": lambda _: None})
    monkeypatch.setattr(pipeline, "_delivery_complete", lambda day: day != date(2026, 9, 7))
    calls = []
    def run(day, **kwargs):
        calls.append(day)
        return {"date": str(day), "status": "PASS"}
    monkeypatch.setattr(pipeline, "run_date", run)
    pipeline.run_latest(backfill_missing=True)
    assert calls == [date(2026, 9, 7)]


def test_all_market_hard_gates_are_enforced(tmp_path):
    _schemas(tmp_path)
    day = date(2026, 9, 8)
    _write_artifact(tmp_path, "market_packet", day)
    path = tmp_path / f"data/market_packets/{day}.json"
    value = json.loads(path.read_text())
    value["data_quality"]["checks"].append({"item": "limit ecology", "status": "FAIL", "hard_gate": True})
    path.write_text(json.dumps(value), encoding="utf-8")
    check = DailyCloseOrchestrator(tmp_path)._validate_artifact("market_packet", day)
    assert not check["valid"]
    assert "production gate" in check["error"]


def test_missing_compact_regenerates_same_date(tmp_path):
    _schemas(tmp_path)
    day = date(2026, 9, 8)
    _write_artifact(tmp_path, "review_intelligence", day)
    (tmp_path / f"data/review_intelligence/{day}_compact.json").unlink()
    calls = []
    pipeline = DailyCloseOrchestrator(tmp_path, runners=_runners(tmp_path, calls))
    result = pipeline._execute_step("review_intelligence", day, force=False)
    assert not result["reused"]
    assert calls == [("review_intelligence", str(day))]


def test_cross_date_compact_is_not_reusable(tmp_path):
    _schemas(tmp_path)
    day = date(2026, 9, 8)
    _write_artifact(tmp_path, "review_intelligence", day)
    path = tmp_path / f"data/review_intelligence/{day}_compact.json"
    path.write_text(json.dumps({"meta": {"trade_date": "2026-09-07"}}), encoding="utf-8")
    assert not DailyCloseOrchestrator(tmp_path)._compact_valid("review_intelligence", day)


def test_waiting_feedback_step_not_overwritten_by_success_envelope(tmp_path):
    pipeline = DailyCloseOrchestrator(tmp_path, runners={"feedback": lambda _: {
        "status": "PASS", "still_waiting_count": 1, "newly_validated_count": 0}})
    assert pipeline._execute_feedback(date(2026, 9, 8))["status"] == "WAITING"
