from datetime import date
import json

import pandas as pd
import pytest

from src.daily_close.credentials import daily_api_health
from src.market_packet.collector import MarketPacketCollector


@pytest.mark.parametrize("message,status", [
    ("invalid token", "AUTH_FAILED"),
    ("permission denied", "PERMISSION_DENIED"),
    ("connection timeout", "NETWORK_FAILED"),
    ("rate limit", "RATE_LIMITED"),
    ("unexpected failure", "API_FAILED"),
])
def test_provider_error_is_classified_without_leak(message, status):
    class Client:
        def daily(self, **kwargs):
            raise RuntimeError(message)
    assert daily_api_health(date(2026, 9, 9), Client()) == status


@pytest.mark.parametrize("rows,status", [
    ([], "DATA_NOT_READY"),
    ([{"trade_date": "20260908"}], "SOURCE_DATE_MISMATCH"),
    ([{"trade_date": "20260909"}], "AVAILABLE"),
])
def test_daily_probe_checks_response_date(rows, status):
    class Client:
        def daily(self, **kwargs):
            assert kwargs == {"trade_date": "20260909"}
            return pd.DataFrame(rows)
    assert daily_api_health(date(2026, 9, 9), Client()) == status


def test_old_previous_daily_cache_never_falls_back(tmp_path):
    collector = MarketPacketCollector(raw_root=tmp_path)
    assert collector.reference_root.is_relative_to(tmp_path)
    collector._write_cache(date(2026, 9, 9), "tushare_previous_daily_all", "tushare.daily", date(2026, 9, 4), [{"trade_date": "20260904"}])
    calls = []
    class Client:
        def daily(self, trade_date):
            calls.append(trade_date)
            return pd.DataFrame()
    result = collector._collect_tushare_previous_daily(Client(), date(2026, 9, 9), date(2026, 9, 8))
    assert calls == ["20260908"]
    assert result.quality == "FAIL" and not result.rows


def test_native_api_failure_persists_and_stops_collection(tmp_path, monkeypatch):
    from tests.unit.test_daily_close_orchestrator import _schemas, _calendar, SHANGHAI
    from src.daily_close.orchestrator import DailyCloseOrchestrator
    from datetime import datetime
    _schemas(tmp_path)
    monkeypatch.setenv("TUSHARE_TOKEN", "fixture-only-secret")
    monkeypatch.setattr("src.daily_close.orchestrator.daily_api_health", lambda _: "PERMISSION_DENIED")
    pipeline = DailyCloseOrchestrator(tmp_path, now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI), calendar_loader=lambda _: _calendar())
    result = pipeline.run_date(date(2026, 9, 8))
    assert result["status"] == "FAILED"
    assert result["failed_step"] == "daily_data_preflight"
    assert result["blocker"] == ["TUSHARE_DAILY_PERMISSION_DENIED"]
    stored = json.loads((tmp_path / "data/daily_runs/2026-09-08.json").read_text(encoding="utf-8"))
    assert stored["source_health"]["tushare_daily_api"] == "PERMISSION_DENIED"
    assert "fixture-only-secret" not in json.dumps(stored)
    assert not (tmp_path / "data/review_context").exists()


@pytest.mark.parametrize("health_sequence,expected,delays", [
    (["DATA_NOT_READY"] * 4, "DATA_NOT_READY", [1, 2, 3]),
    (["DATA_NOT_READY", "AVAILABLE"], "AVAILABLE", [1]),
    (["AUTH_FAILED"], "AUTH_FAILED", []),
])
def test_data_not_ready_retries_without_credential_failure(tmp_path, monkeypatch, health_sequence, expected, delays):
    from datetime import datetime
    from src.daily_close.orchestrator import DailyCloseOrchestrator
    from tests.unit.test_daily_close_orchestrator import _schemas, _calendar, SHANGHAI
    from tools.publish_daily_close_failure import failed_manifests
    _schemas(tmp_path)
    monkeypatch.setenv("TUSHARE_TOKEN", "fixture-only-secret")
    states = iter(health_sequence)
    monkeypatch.setattr("src.daily_close.orchestrator.daily_api_health", lambda _: next(states))
    waits = []
    path = tmp_path / "data/daily_runs/2026-09-08.json"

    def sleep(delay):
        pending = json.loads(path.read_text(encoding="utf-8"))
        assert pending["status"] == "DATA_NOT_READY"
        assert pending["credential_health"] == {"tushare_token": "AVAILABLE"}
        waits.append(delay)

    pipeline = DailyCloseOrchestrator(tmp_path,
        now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(), data_retry_delays=(1, 2, 3), sleep=sleep)
    calls = []
    def market(name, target, **kwargs):
        calls.append(name)
        return pipeline._step_record("FAILED", None, target, None, pipeline.now(), 0,
            "FIXTURE_STOP_AFTER_RECOVERED_PREFLIGHT", False, None)
    monkeypatch.setattr(pipeline, "_execute_step", market)
    result = pipeline.run_date(date(2026, 9, 8))
    assert waits == delays
    assert result["source_health"]["tushare_daily_api"] == expected
    assert result["credential_health"] == {"tushare_token": "AVAILABLE"}
    assert result["retry_count"] == len(delays)
    assert result["failed_step"] != "credential_preflight"
    assert calls == (["market_packet"] if expected == "AVAILABLE" else [])
    assert "fixture-only-secret" not in path.read_text(encoding="utf-8")
    assert not (tmp_path / "data/review_context").exists()
    if expected == "DATA_NOT_READY":
        assert result["status"] == "DATA_NOT_READY"
        assert failed_manifests(tmp_path, result["run_id"], result["workflow_run_attempt"]) == [path]
    if expected == "AVAILABLE":
        assert not any(row["step"] == "daily_data_preflight" for row in result["degraded_inputs"])


def test_data_not_ready_has_distinct_cli_exit(monkeypatch):
    from tools import run_daily_close_pipeline as cli
    class Pipeline:
        def run_date(self, *args, **kwargs):
            return dict(date="2026-09-11", status="DATA_NOT_READY", manifest_path="fixture",
                        blockers=[{"error": "TUSHARE_DAILY_DATA_NOT_READY"}],
                        credential_health={"tushare_token": "AVAILABLE"})
    monkeypatch.setattr(cli, "DailyCloseOrchestrator", Pipeline)
    assert cli.main(["--date", "2026-09-11"]) == 4


def test_delayed_workflow_schedule_and_exit_boundary():
    from pathlib import Path
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/daily-close.yml").read_text(encoding="utf-8")
    for cron in ("45 7", "15 8", "0 9", "0 12"):
        assert f'{cron} * * 1-5' in workflow
    assert '[[ "$code" == "4" ]] && exit 4' in workflow
