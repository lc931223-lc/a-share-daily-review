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
    ([], "EMPTY_RESPONSE"),
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
    assert result["failed_step"] == "credential_preflight"
    assert result["blocker"] == ["TUSHARE_DAILY_PERMISSION_DENIED"]
    stored = json.loads((tmp_path / "data/daily_runs/2026-09-08.json").read_text(encoding="utf-8"))
    assert stored["source_health"]["tushare_daily_api"] == "PERMISSION_DENIED"
    assert "fixture-only-secret" not in json.dumps(stored)
    assert not (tmp_path / "data/review_context").exists()
